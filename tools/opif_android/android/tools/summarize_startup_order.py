"""Summarize existing isolated startup evidence; this does not run a device test."""
import argparse
import json
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    i = (len(values) - 1) * q
    lo = int(i)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (i - lo)


def summarize(run):
    result = json.loads((run / 'result.json').read_text())
    frames = rows(run / 'frames.jsonl')
    valid = [f for f in frames if f['valid']]
    unique = []
    seen = set()
    for frame in valid:
        identity = (frame['frame_id'], frame['timestamp_eof'])
        if identity not in seen:
            seen.add(identity)
            unique.append(frame)
    gaps = [(b['received_ns'] - a['received_ns']) / 1e6 for a, b in zip(unique, unique[1:])]
    span_s = (unique[-1]['received_ns'] - unique[0]['received_ns']) / 1e9 if len(unique) > 1 else 0
    events = rows(run / 'control-events.jsonl')
    alerts = [{'at': e['at'], 'alert': e['selfdrive']['alertType'], 'phase': e['runtime_phase']}
              for e in events if 'bigModel' in e['selfdrive'].get('alertType', '')]
    physical = rows(run / 'physical-samples.jsonl')
    max_rss = {}
    for sample in physical:
        for name, stats in sample.get('processes', {}).items():
            max_rss[name] = max(max_rss.get(name, 0), stats['rss_bytes'])
    runtime = result['runtime']
    return {
        'run': str(run), 'completed_requested_duration': result['completed_requested_duration'],
        'failure': result['failure'], 'model_alert_observations': alerts,
        'failed_alert_observations': sum('bigModelFailed' in a['alert'] for a in alerts),
        'ready_observed_without_initial_phase': sum('bigModelReady' in a['alert'] and a['phase'] is None for a in alerts),
        'total_model_messages': len(frames), 'valid_model_messages': len(valid),
        'invalid_model_messages': len(frames) - len(valid),
        'invalid_frame_positions': [i for i, f in enumerate(frames) if not f['valid']],
        'duplicate_valid_messages': len(valid) - len(unique),
        'unique_valid_message_span_seconds': span_s,
        'unique_valid_results_hz': (len(unique) - 1) / span_s if span_s else None,
        'max_valid_output_gap_ms': max(gaps, default=None),
        'observer_local_result_age_ms': {f'p{int(q * 100)}': percentile([f['age_ms'] for f in valid], q)
                                         for q in (.5, .95, .99)},
        'observer_age_clock': 'C3 CLOCK_BOOTTIME minus modelV2.timestampEof; observer receipt only',
        'A_use': None, 'A_publish': None,
        'camera_id_gaps': result['progress']['camera_id_gaps'],
        'phone_results_at_last_runtime_sample': runtime['remote_outputs'],
        'local_runs_at_last_runtime_sample': runtime['local_runs'],
        'runtime_failure_reason': runtime['failure_reason'],
        'source': runtime['source'], 'phase': runtime['phase'], 'allow_control': runtime['allow_control'],
        'c3_temperature_c': {'first': physical[0]['temp_c'], 'last': physical[-1]['temp_c'],
                             'maximum': max(s['temp_c'] for s in physical)},
        'max_process_rss_bytes': max_rss,
        'hardware_restored': result['hardware_restored']['complete'],
        'namespace_cleanup': result['namespace_cleanup'],
        'road_control_qualified': result['road_control_qualified'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline, candidate = summarize(args.baseline), summarize(args.candidate)
    output = {
        'scope': 'QNN startup publication order; one baseline and one candidate, 60 seconds requested each',
        'baseline': baseline, 'candidate': candidate,
        'fix_observed': baseline['failed_alert_observations'] > 0 and candidate['failed_alert_observations'] == 0
                        and candidate['ready_observed_without_initial_phase'] == 0,
        'limitations': ['One run per variant does not establish performance significance or thermal stability.',
                       'Live camera inputs are not a fixed numerical replay; the model is unchanged.',
                       'Observer age is for the selected local fallback, not phone age, A_use, or A_publish.',
                       'Runtime output counters update once per second and are not exact shutdown totals.',
                       'No real vehicle output; eligibility and validity checks are unchanged.'],
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'output': str(args.output), 'fix_observed': output['fix_observed']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
