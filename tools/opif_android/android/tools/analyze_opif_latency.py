"""Recompute phone return/availability/check ages from bounded binary C3 traces."""
from collections import Counter, defaultdict
from bisect import bisect_left
import argparse
import json
from itertools import islice
from pathlib import Path
import struct


def distribution(values):
    values = sorted(x for x in values if x is not None)
    def q(f):
        if not values:
            return None
        x = (len(values) - 1) * f
        i = int(x)
        return values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * (x - i)
    return {'n': len(values), 'p50': q(.5), 'p95': q(.95), 'p99': q(.99), 'max': max(values, default=None)}


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def jsonlines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s] if path.exists() else []


def analyze(run):
    metas, events, problems = [], [], []
    for path in sorted((run / 'trace').glob('*.json')):
        m = load(path); metas.append(m)
        names = {v: k for k, v in m['codes'].items()}
        errors = {e['index']: e for e in m['errors']}
        for thread in m['threads']:
            if thread['dropped']:
                problems.append(f'{path.name}: {thread["dropped"]} dropped records')
            raw = (run / 'trace' / thread['file']).read_bytes()
            if len(raw) != thread['records'] * struct.calcsize(m['record_format']):
                problems.append(f'{thread["file"]}: incomplete binary file')
                continue
            for record in struct.iter_unpack(m['record_format'], raw):
                t, code, worker, rid, a, b, c, d = record
                event = dict(t=t, name=names[code], worker=worker, rid=rid, a=a, b=b, c=c, d=d,
                             pid=m['pid'], thread=thread['name'])
                if event['name'] == 'ERROR':
                    event['error'] = errors[a]
                events.append(event)
    events.sort(key=lambda e: e['t'])
    local_times = {(e['worker'], e['a'], e['name']): e['t'] for e in events if e['name'] in ('LOCAL_BEGIN', 'LOCAL_END')}
    select_open, select_spans = {}, defaultdict(list)
    for e in events:
        key = (e['pid'], e['thread'])
        if e['name'] == 'SELECT_BEGIN':
            select_open[key] = e
        elif e['name'] == 'SELECT_END' and key in select_open:
            begin = select_open.pop(key)
            select_spans[e['worker']].append((begin['t'], e['t'], begin['a'], e['a'], e['b']))
    span_starts = {worker: [s[0] for s in spans] for worker, spans in select_spans.items()}
    sessions = {e['worker']: e['a'] for e in events if e['name'] == 'SESSION'}
    trace_ends = {m['pid']: m['clock_end_boottime_monotonic_ns'][0] for m in metas
                  if m.get('clock_end_boottime_monotonic_ns')}
    grouped = defaultdict(list)
    submissions = [e for e in events if e['name'] == 'SUBMIT']
    for e in events:
        if e['rid']:
            grouped[(e['worker'], e['rid'])].append(e)
    fatal = [e for e in events if e['name'] == 'ERROR' and e['error']['message'] != 'External session closed']
    receipt = load(run.with_name(run.name + '-receipt.json'), {})
    result = load(run / 'result.json', {})
    replay = load(run / 'replay-result.json')
    replay_received = {r['frame'] for r in replay['results']} if replay else set()
    if replay:
        receipt = {'arguments': {'warmup': replay.get('warmup_frames', 0) / replay['target_hz'],
                                'seconds': (replay['requested_frames'] - replay.get('warmup_frames', 0)) / replay['target_hz']},
                   'app_pid_unchanged': replay.get('app_pid_unchanged')}
        result = {'completed_requested_duration': replay['completed'], 'failure': replay['error']}
    profile = load(run / 'profile.json', {})
    maximum_age = float(profile.get('maximum_result_age_seconds', .2)) * 1e9
    ticks = [e for e in events if e['name'] == 'TICK']
    origin = ticks[0]['t'] if ticks else min((e['t'] for e in submissions), default=0)
    if replay:
        origin = min((e['b'] for e in submissions), default=0)
    warmup = receipt.get('arguments', {}).get('warmup', 0)
    steady_start = origin + warmup * 1e9
    steady_end = steady_start + receipt.get('arguments', {}).get('seconds', 0) * 1e9
    requests = []
    for sub in submissions:
        key = (sub['worker'], sub['rid']); own = grouped[key]
        def event(name):
            return next((e for e in own if e['name'] == name and
                         (name != 'FULL' or e['a'] == sessions.get(sub['worker']))), None)
        marks = {name: event(name) for name in ('PAIR_MAIN', 'PAIR_EXTRA', 'FULL', 'PARSED', 'POLL_RESULT', 'PARENT_IPC', 'AVAILABLE', 'MODEL_TAKE', 'CHECKED', 'VALID', 'IPC_SUBMIT', 'WORKER_TAKE', 'WIRE_SUBMIT')}
        queued = next((e for e in own if e['name'] == 'SEND_QUEUED' and e['a'] == 16), None)
        sent = next((e for e in own if e['name'] == 'SEND_DONE' and e['a'] == 16), None)
        failure = next((e for e in fatal if e['worker'] == sub['worker'] and e['t'] >= sub['t']), None)
        parent_end = trace_ends.get(sub['pid'])
        completed_test_end = bool(result.get('completed_requested_duration') and failure
                                  and parent_end is not None and failure['t'] > parent_end)
        def diff(end, start):
            return (end - start) / 1e6 if end is not None and start is not None else None
        def stamp(name):
            return marks[name]['t'] if marks[name] else None
        eof = sub['b']
        local_marks = {name: local_times.get((sub['worker'], sub['a'], name))
                       for name in ('LOCAL_BEGIN', 'LOCAL_END')}
        row = {'worker_pid': key[0], 'session_id': sessions.get(key[0]), 'request_id': key[1], 'frame_id': sub['a'], 'eof_ns': eof,
               'submitted_ns': sub['t'], 'steady': steady_start <= eof < steady_end,
               'times_ns': {name: stamp(name) for name in marks},
               'camera_pair': {name: None if marks[name] is None else {'frame_id': marks[name]['a'], 'sof_ns': marks[name]['b'], 'eof_ns': marks[name]['c'],
                               'readout_offset_ns': marks[name]['c'] - marks[name]['b']} for name in ('PAIR_MAIN', 'PAIR_EXTRA')},
               'A_return_ms': diff(stamp('FULL'), eof), 'A_available_ms': diff(stamp('AVAILABLE'), eof),
               'A_checked_ms': diff(stamp('CHECKED'), eof), 'W_delivery_ms': diff(stamp('AVAILABLE'), stamp('FULL')),
               'W_check_ms': diff(stamp('CHECKED'), stamp('AVAILABLE')),
               'full_to_poll_return_ms': diff(stamp('POLL_RESULT'), stamp('FULL')),
               'parsed_to_poll_return_ms': diff(stamp('POLL_RESULT'), stamp('PARSED')),
               'available_to_model_take_ms': diff(stamp('MODEL_TAKE'), stamp('AVAILABLE')),
               'model_take_to_check_ms': diff(stamp('CHECKED'), stamp('MODEL_TAKE')),
               'eof_to_submit_ms': diff(sub['t'], eof), 'submit_to_worker_ms': diff(stamp('WORKER_TAKE'), sub['t']),
               'send_queue_to_api_done_ms': diff(sent['t'] if sent else None, queued['t'] if queued else None),
               'eof_to_send_api_done_ms': diff(sent['t'] if sent else None, eof),
               'send_api_complete': sent is not None, 'send_queued': queued is not None,
               'ort_run_ms': marks['PARSED']['a'] / 1000 if marks['PARSED'] else None,
               'failure': failure['error']['message'] if failure else None,
               'failure_context': ('after_parent_trace_closed' if completed_test_end else 'session') if failure else None,
               'age_at_session_failure_ms': diff(failure['t'], eof) if failure else None}
        row['local_begin_ns'], row['local_end_ns'] = local_marks['LOCAL_BEGIN'], local_marks['LOCAL_END']
        row['local_execution_span_ms'] = diff(local_marks['LOCAL_END'], local_marks['LOCAL_BEGIN'])
        ready_wait = None
        if marks['PARSED'] and marks['POLL_RESULT']:
            begin, end = stamp('PARSED'), stamp('POLL_RESULT')
            spans = select_spans.get(sub['worker'], [])
            at = bisect_left(span_starts.get(sub['worker'], []), begin)
            ready_wait = 0
            for start, finish, requested, readable, writable in islice(spans, at, None):
                if start > end:
                    break
                if requested > 0 and not readable and not writable:
                    ready_wait += min(finish, end) - start
        row['parsed_ready_empty_select_ms'] = ready_wait / 1e6 if ready_wait is not None else None
        for name in ('AVAILABLE', 'MODEL_TAKE', 'CHECKED'):
            if marks[name] and (marks[name]['a'], marks[name]['b']) != (sub['a'], eof):
                problems.append(f'{name} identity differs for {key}')
        if marks['VALID']:
            disposition = 'checked_valid'
        elif replay and sub['rid'] in replay_received:
            disposition = 'returned_to_replay'
        elif marks['CHECKED']:
            disposition = 'checked_invalid_or_interrupted'
        elif replay and replay.get('error') and 'outstanding frames' in replay['error']:
            # The replay stopped on admission backpressure. A subsequent EOF
            # or bad descriptor is teardown, not evidence of model invalidity.
            disposition = 'session_aborted_on_capture_backpressure'
        elif completed_test_end:
            # Keep the request and its worker error, but do not count a deadline
            # after the completed model process stopped as an operational loss.
            disposition = 'test_end_unfinished'
        elif failure:
            message = failure['error']['message'].lower()
            if 'deadline' in message or 'timeout' in message or 'exceeded' in message:
                disposition = 'timeout' if failure['t'] - eof >= maximum_age else 'session_aborted_before_own_deadline'
            elif any(word in message for word in ('disconnect', 'closed', 'exited')):
                disposition = 'disconnected'
            else:
                disposition = 'invalid_or_session_error'
        else:
            disposition = 'test_end_unfinished'
        row['disposition'] = disposition
        for key2 in ('A_return_ms', 'A_available_ms', 'A_checked_ms', 'W_delivery_ms', 'W_check_ms'):
            if row[key2] is not None and row[key2] < 0:
                problems.append(f'Negative {key2} for {key}')
        if key[0] not in sessions:
            problems.append(f'Missing actual worker session for {key}')
        requests.append(row)
    metric_names = ['A_return_ms', 'A_available_ms', 'A_checked_ms', 'W_delivery_ms', 'W_check_ms', 'full_to_poll_return_ms',
                    'parsed_to_poll_return_ms', 'available_to_model_take_ms', 'model_take_to_check_ms', 'eof_to_submit_ms',
                    'submit_to_worker_ms', 'send_queue_to_api_done_ms', 'eof_to_send_api_done_ms', 'ort_run_ms', 'local_execution_span_ms',
                    'parsed_ready_empty_select_ms']
    frames = jsonlines(run / 'frames.jsonl')
    valid = [f for f in frames if f['valid']]
    def cadence(stamps):
        stamps = sorted(set(stamps))
        return {'n': len(stamps), 'hz': (len(stamps) - 1) * 1e9 / (stamps[-1] - stamps[0]) if len(stamps) > 1 else None,
                'max_gap_ms': max(((b-a)/1e6 for a, b in zip(stamps, stamps[1:])), default=None)}
    for m in metas:
        if m['pid'] in sessions and not m['threads']:
            problems.append('Worker trace not finalized')
    if not events:
        problems.append('No trace events')
    window_start = min((e['t'] for e in submissions), default=None)
    window_end = min((e['t'] for e in fatal if window_start is not None and e['t'] >= window_start), default=None)
    select_time, empty_time, select_calls, select_starts = 0, 0, 0, {}
    window_events = [e for e in events if window_start is not None and window_end is not None and window_start <= e['t'] <= window_end]
    for e in window_events:
        thread_key = (e['pid'], e['thread'])
        if e['name'] == 'SELECT_BEGIN':
            select_starts[thread_key] = e['t']
        if e['name'] == 'SELECT_END' and thread_key in select_starts:
            duration = e['t'] - select_starts.pop(thread_key)
            select_time += duration; select_calls += 1
            if not e['a'] and not e['b']:
                empty_time += duration
    submitted_captures = {(r['worker_pid'], r['frame_id'], r['eof_ns']) for r in requests}
    unsubmitted_ticks = []
    for tick in ticks:
        if (tick['worker'], tick['a'], tick['b']) not in submitted_captures:
            reason = ('latched_local' if tick['d'] else 'startup_not_remote_started' if not tick['c']
                      else 'not_submitted_before_session_abort' if fatal else 'not_submitted_reason_unobserved')
            unsubmitted_ticks.append({'worker_pid': tick['worker'], 'frame_id': tick['a'], 'eof_ns': tick['b'], 'reason': reason})
    summary = {
        'run': str(run), 'complete_device_round': result.get('completed_requested_duration', False), 'device_failure': result.get('failure'),
        'trace_complete': not problems, 'trace_problems': problems, 'all_submitted_accounted_for': len(requests) == len(submissions),
        'requests_submitted': len(requests), 'requests_full': sum(r['A_return_ms'] is not None for r in requests),
        'requests_available': sum(r['A_available_ms'] is not None for r in requests), 'requests_checked': sum(r['A_checked_ms'] is not None for r in requests),
        'steady_requests': sum(r['steady'] for r in requests), 'dispositions': dict(Counter(r['disposition'] for r in requests)),
        'metrics_all_requests': {n: distribution(r[n] for r in requests) for n in metric_names},
        'metrics_steady_requests': {n: distribution(r[n] for r in requests if r['steady']) for n in metric_names},
        'remote_receive_cadence': cadence([r['times_ns']['FULL'] for r in requests if r['times_ns']['FULL'] is not None]),
        'remote_valid_cadence': cadence([r['times_ns']['VALID'] for r in requests if r['times_ns']['VALID'] is not None]),
        'submitted_capture_cadence': cadence([r['eof_ns'] for r in requests]),
        'actual_submission_cadence': cadence([r['submitted_ns'] for r in requests]),
        'unsubmitted_camera_ticks': unsubmitted_ticks,
        'camera_ticks_accounted_for': len(ticks) == len(requests) + len(unsubmitted_ticks),
        'local_valid_cadence': cadence([f['received_ns'] for f in valid]),
        'local_invalid_count': len(frames) - len(valid), 'camera_id_gaps': result.get('progress', {}).get('camera_id_gaps'),
        'old_session_full_results': sum(e['name'] == 'FULL' and e['a'] != sessions.get(e['worker']) for e in events),
        'event_counts': dict(Counter(e['name'] for e in events)), 'errors': [e for e in events if e['name'] == 'ERROR'],
        'process_trace_metadata': metas, 'requests': requests,
        'first_request_to_failure_io_window': {'duration_ms': (window_end-window_start)/1e6 if window_start is not None and window_end is not None else None,
            'select_calls': select_calls, 'select_total_ms': select_time/1e6 if select_calls else None,
            'empty_select_ms': empty_time/1e6 if select_calls else None,
            'poll_calls': sum(e['name'] == 'POLL_BEGIN' for e in window_events)},
        'hardware_restored': result.get('hardware_restored', {}).get('complete'), 'namespace_cleanup': result.get('namespace_cleanup'),
        'app_pid_unchanged': receipt.get('app_pid_unchanged'), 'A_use': None, 'A_publish': None,
        'hypothesis_A': 'insufficient_evidence_no_complete_result' if not any(r['A_return_ms'] is not None for r in requests) else 'inspect_per_request_poll_wait',
        'hypothesis_B': 'insufficient_evidence_no_parent_available_result' if not any(r['A_available_ms'] is not None for r in requests) else 'inspect_per_request_handoff_wait',
    }
    summary['input_time_basis'] = 'C3 camera estimated EOF'
    if replay:
        summary['input_time_basis'] = replay['input_time_basis']
        summary['actual_camera_age_measured'] = False
        summary['source_selection_checked'] = False
        summary['requested_schedule_frames'] = replay['requested_frames']
        summary['schedule_frames_not_submitted_after_stop'] = replay['requested_frames'] - len(replay['submitted'])
        summary['hypothesis_B'] = 'not_exercised_no_local_model_or_source_selector_in_fixed_replay'
        names = {'A_return_ms': 'replay_return_from_schedule_ms', 'A_available_ms': 'replay_available_from_schedule_ms',
                 'A_checked_ms': 'replay_checked_from_schedule_ms'}
        for group in ('metrics_all_requests', 'metrics_steady_requests'):
            summary[group] = {names.get(k, k): v for k, v in summary[group].items()}
        for row in requests:
            for old, new in names.items():
                row[new] = row.pop(old)
            row['scheduled_replay_ns'] = row.pop('eof_ns')
            row['synthetic_pair_identifiers'] = row.pop('camera_pair')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--payload', type=Path)
    args = parser.parse_args()
    summary = {'runs': [analyze(run) for run in args.runs],
               'units': 'milliseconds, C3 CLOCK_BOOTTIME', 'scope': 'Phone return/parent availability/candidate checks; never A_use',
               'phone_queue_us': 'protocol placeholder, not measured', 'one_way_network_latency': None,
               'pure_htp_execution_time': None}
    if args.payload:
        payload = load(args.payload)
        frames = payload['frames']
        summary['independent_tcp_transfer'] = {
            'scope': payload['scope'], 'sent_frames': len(frames), 'bytes_verified': payload['bytes_verified'],
            'payload_bytes': payload['payload_bytes'], 'verified_total_bytes': payload['payload_bytes'] * len(frames),
            'target_hz': payload['target_hz'], 'receiver_exit_code': payload['receiver_exit_code'], 'failure': payload['failure'],
            'send_api_ms': distribution(f['send_ms'] for f in frames),
            'schedule_late_ms': distribution(f['schedule_late_ms'] for f in frames),
            'duration_seconds': (frames[-1]['send_api_done_ns'] - frames[0]['begin_ns']) / 1e9 if frames else None,
            'not_measured': ['remote per-frame arrival time', 'model execution', 'bidirectional inference latency']}
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'output': str(args.output), 'runs': len(summary['runs'])}))


if __name__ == '__main__':
    main()
