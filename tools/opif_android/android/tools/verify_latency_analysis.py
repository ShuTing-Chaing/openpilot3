"""Known-time binary evidence fixture, written before the statistics implementation."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    trace = args.output / 'trace'; trace.mkdir()
    names = 'SESSION SUBMIT PAIR_MAIN PAIR_EXTRA FULL AVAILABLE CHECKED VALID ERROR'.split()
    codes = {n: i + 1 for i, n in enumerate(names)}
    # First completes; second has a full reply from an old session only;
    # third is still within deadline when that failure aborts the session.
    events = [
        (1_000_000_000, 'SESSION', 0, 101, 0),
        (1_010_000_000, 'SUBMIT', 1, 10, 1_000_000_000),
        (1_010_000_001, 'PAIR_MAIN', 1, 10, 985_303_000, 1_000_000_000),
        (1_010_000_002, 'PAIR_EXTRA', 1, 20, 985_203_000, 999_900_000),
        (1_090_000_000, 'FULL', 1, 101, 73832),
        (1_095_000_000, 'AVAILABLE', 1, 10, 1_000_000_000),
        (1_110_000_000, 'CHECKED', 1, 10, 1_000_000_000),
        (1_111_000_000, 'VALID', 1, 0, 0),
        (1_060_000_000, 'SUBMIT', 2, 11, 1_050_000_000),
        (1_090_000_000, 'FULL', 2, 100, 73832),
        (1_110_000_000, 'SUBMIT', 3, 12, 1_100_000_000),
        (1_251_000_000, 'ERROR', 0, 1, 0),
    ]
    data = []
    for t, name, rid, *values in events:
        values += [0] * (4 - len(values))
        data.append(struct.pack('<8Q', t, codes[name], 9, rid, *values))
    (trace / '9-1.bin').write_bytes(b''.join(data))
    meta = {'pid': 9, 'link_id': 9, 'mode': 'full', 'codes': codes, 'record_format': '<8Q',
            'threads': [{'file': '9-1.bin', 'records': len(data), 'dropped': 0, 'name': 'fixture'}],
            'errors': [{'index': 1, 'message': 'OPIF absolute frame deadline exceeded', 'type': 'QnnError'}],
            'clock_start_boottime_monotonic_ns': [1_000_000_000, 1_000_000_000],
            'clock_end_boottime_monotonic_ns': [1_300_000_000, 1_300_000_000]}
    (trace / '9.json').write_text(json.dumps(meta))
    receipt = {'arguments': {'warmup': 0, 'seconds': 1}, 'exit_code': 1, 'app_pid_unchanged': True}
    args.output.with_name(args.output.name + '-receipt.json').write_text(json.dumps(receipt))
    from analyze_opif_latency import analyze
    result = analyze(args.output)
    assert result['requests_submitted'] == 3 and result['requests_full'] == 1
    assert result['old_session_full_results'] == 1
    assert result['all_submitted_accounted_for'] is True
    assert result['metrics_all_requests']['A_return_ms']['p50'] == 90
    assert result['metrics_all_requests']['A_available_ms']['p50'] == 95
    assert result['metrics_all_requests']['A_checked_ms']['p50'] == 110
    assert result['metrics_all_requests']['W_delivery_ms']['p50'] == 5
    assert result['metrics_all_requests']['W_check_ms']['p50'] == 15
    assert result['dispositions'] == {'checked_valid': 1, 'timeout': 1, 'session_aborted_before_own_deadline': 1}
    assert result['requests'][1]['A_return_ms'] is None
    meta['threads'][0]['dropped'] = 1
    (trace / '9.json').write_text(json.dumps(meta))
    assert analyze(args.output)['trace_complete'] is False
    meta['threads'][0]['dropped'] = 0
    (trace / '9.json').write_text(json.dumps(meta))
    # A successful test can stop the model thread with requests still in flight.
    # Do not charge a later worker deadline to steady operation or drop the row.
    cleanup = args.output / 'cleanup-case'; (cleanup / 'trace').mkdir(parents=True)
    parent_events = [(2_000_000_000, 'SUBMIT', 1, 11, 1_990_000_000),
                     (2_055_000_000, 'AVAILABLE', 1, 11, 1_990_000_000)]
    worker_events = [(1_900_000_000, 'SESSION', 0, 101, 0),
                     (2_050_000_000, 'FULL', 1, 101, 73832),
                     (2_205_000_000, 'ERROR', 0, 1, 0)]
    for pid, sequence, end in ((99, parent_events, 2_090_000_000), (9, worker_events, 2_210_000_000)):
        packed = []
        for t, name, rid, *values in sequence:
            values += [0] * (4 - len(values))
            packed.append(struct.pack('<8Q', t, codes[name], 9, rid, *values))
        filename = f'{pid}-1.bin'
        (cleanup / 'trace' / filename).write_bytes(b''.join(packed))
        metadata = dict(meta, pid=pid,
                        threads=[{'file': filename, 'records': len(packed), 'dropped': 0, 'name': 'fixture'}],
                        clock_end_boottime_monotonic_ns=[end, end])
        (cleanup / 'trace' / f'{pid}.json').write_text(json.dumps(metadata))
    (cleanup / 'result.json').write_text(json.dumps({'completed_requested_duration': True, 'failure': None}))
    stopped = analyze(cleanup)
    assert stopped['requests_submitted'] == stopped['requests_full'] == stopped['requests_available'] == 1
    assert stopped['dispositions'] == {'test_end_unfinished': 1}
    assert stopped['requests'][0]['failure_context'] == 'after_parent_trace_closed'
    assert stopped['requests'][0]['failure'] == 'OPIF absolute frame deadline exceeded'
    # Without successful completion, preserve the observed deadline disposition.
    (cleanup / 'result.json').write_text(json.dumps({'completed_requested_duration': False, 'failure': 'interrupted'}))
    assert analyze(cleanup)['dispositions'] == {'timeout': 1}
    (args.output / 'verification.json').write_text(json.dumps({'passed': True, 'scope': 'Synthetic binary statistics and request-accounting fixture; no device or HTP performance claim',
                                                             'checks': ['exact age/decomposition', 'old session excluded', 'every submitted request accounted', 'timeout versus collateral cancellation', 'overflow invalidates trace', 'normal test-end versus later worker deadline']}, indent=2) + '\n')
    print(json.dumps({'passed': True, 'artifact': str(args.output / 'verification.json')}))


if __name__ == '__main__':
    main()
