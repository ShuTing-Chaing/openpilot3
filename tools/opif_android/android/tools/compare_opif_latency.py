"""Compare same-fixture OPIF replay stages without claiming camera A_use."""
import argparse
import json
from pathlib import Path

from analyze_opif_latency import analyze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [json.loads((p / 'replay-result.json').read_text()) for p in (args.baseline, args.candidate)]
    a, b = reports
    conditions = {'same_fixture': a['fixture_sha256'] == b['fixture_sha256'],
                  'same_frames_and_warmup': (a['requested_frames'], a.get('warmup_frames')) == (b['requested_frames'], b.get('warmup_frames')),
                  'same_radio_profile': a.get('radio_profile') == b.get('radio_profile') == 'onroad',
                  'wifi_off_both': all(r.get('power_active', {}).get('wifi_power_save') == 'off' for r in reports),
                  'same_trace': a.get('trace_mode') == b.get('trace_mode') == 'full',
                  'both_completed': a['completed'] and b['completed'],
                  'app_unchanged': a.get('app_pid_unchanged') is True and b.get('app_pid_unchanged') is True}
    hashes = [{r['frame']: r['sha256'] for r in report['results']} for report in reports]
    common = sorted(hashes[0].keys() & hashes[1].keys())
    mismatches = [frame for frame in common if hashes[0][frame] != hashes[1][frame]]
    analyzed = [analyze(p) for p in (args.baseline, args.candidate)]
    fields = ['replay_return_from_schedule_ms', 'replay_available_from_schedule_ms', 'W_delivery_ms',
              'parsed_to_poll_return_ms', 'parsed_ready_empty_select_ms']
    changes = {}
    for field in fields:
        left, right = (r['metrics_steady_requests'][field] for r in analyzed)
        changes[field] = {'baseline': left, 'candidate': right,
                          'candidate_minus_baseline': {q: right[q] - left[q] if right[q] is not None and left[q] is not None else None for q in ('p50', 'p95', 'p99')}}
    output = {'scope': 'Fixed input schedule and C3 receive/handoff stages, not real camera age or A_use',
              'conditions': conditions, 'comparable_complete_pair': all(conditions.values()),
              'common_output_frames': len(common), 'output_mismatches': mismatches,
              'all_requested_outputs_bit_exact': len(common) == a['requested_frames'] == b['requested_frames'] and not mismatches,
              'stage_changes': changes, 'baseline': analyzed[0], 'candidate': analyzed[1]}
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'comparable': output['comparable_complete_pair'],
                      'bit_exact': output['all_requested_outputs_bit_exact'], 'W_delivery': changes['W_delivery_ms']}))


if __name__ == '__main__':
    main()
