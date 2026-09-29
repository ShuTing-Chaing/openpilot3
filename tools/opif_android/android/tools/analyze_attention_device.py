#!/usr/bin/env python3
"""Summarize OPIF's actual offline device pair and production-runtime A/B/A."""
import argparse
import json
from pathlib import Path
import re

import numpy as np
from verify_profile import verify_profile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    a = p.parse_args()
    root = a.directory
    pair = json.loads((root / 'pair/result.json').read_text())
    rows = [json.loads(line) for line in (root / 'pair/frames.jsonl').read_text().splitlines()]
    assert pair['completed'] and pair['measured_frames'] == 410 and pair['different_frames'] == 0
    assert len(rows) == 410 and all(r['all_outputs_bit_exact'] and r['output_byte_differences'] == [0, 0, 0, 0] for r in rows)
    profiles = {f.name: verify_profile(json.loads(f.read_text()))
                for f in (root / 'pair').glob('*_*.json')}
    assert len(profiles) == 2
    performance = {}
    outputs = {}
    for mode in ['a1', 'b1', 'a2']:
        assert (root / f'{mode}-exit-code.txt').read_text().strip() == '0'
        text = (root / f'{mode}.log').read_text()
        samples = [(int(i), int(t) / 1000) for i, t in re.findall(r'^frame=(\d+) inference_us=(\d+)$', text, re.M)]
        assert [i for i, _ in samples] == list(range(240))
        measured = [ms for _, ms in samples[40:]]
        performance[mode] = {k: float(np.percentile(measured, q))
                             for k, q in [('p50_ms', 50), ('p95_ms', 95), ('p99_ms', 99), ('max_ms', 100)]}
        performance[mode].update(warmup_discarded=40, measured_frames=200,
                                 mean_ms=float(np.mean(measured)),
                                 production_runtime='android/native/qnn_runtime.cpp')
        values = (root / f'{mode}-outputs.bin').read_bytes()
        assert len(values) == 240 * 18452 * 4 and np.isfinite(np.frombuffer(values, dtype='<f4')).all()
        outputs[mode] = values
    assert outputs['a1'] == outputs['b1'] == outputs['a2']
    b = performance['b1']['p50_ms']
    report = {'pair_frames': 410, 'four_outputs_bit_exact': True, 'profiles': profiles,
              'aba': performance, 'aba_all_240_main_outputs_bit_exact': True,
              'improvement_vs_a1_percent': 100 * (1 - b / performance['a1']['p50_ms']),
              'improvement_vs_a2_percent': 100 * (1 - b / performance['a2']['p50_ms']),
              'scope': 'Same phone and OPIF libraries; offline NPU graph and production runtime. Not network or road latency.',
              'app_deployed': False}
    (root / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
