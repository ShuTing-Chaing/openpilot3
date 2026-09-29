#!/usr/bin/env python3
"""C3-only, bounded fixed-input replay against the installed OPIF App."""
import json
from pathlib import Path
import struct
import sys
import time

import numpy as np
sys.path.insert(0, '/data/openpilot')
from openpilot.common.params import Params
from openpilot.sunnypilot.modeld_v2.external_host.probe_lock import exclusive_probe
from openpilot.sunnypilot.modeld_v2.external_host.qnn_client import connect_qnn
from openpilot.sunnypilot.modeld_v2.external_host.session import AsyncSession

BASE = Path('/data/qnn-host/opif-attention-20260928')
params = Params()


def guard():
    if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):
        raise RuntimeError('Stop diagnostic inputs when real device leaves offroad')


def main():
    guard()
    output = BASE / 'app-smoke'
    output.mkdir(exist_ok=False)
    report = {'requested_frames': 200, 'requested_hz': 20, 'fixed_input': True,
              'app': 'com.example.openpilotinference.android', 'passed': False,
              'actual_vehicle_publications': 0}
    session = link = None
    rows = []
    try:
        with exclusive_probe():
            guard()
            profile = json.loads(Path('/data/qnn-host/active-host.json').read_text())
            profile['allow_control'] = False
            link = connect_qnn(profile, 'diagnostic')
            report['hello'] = link.hello()
            session = AsyncSession(link)
            pixels = np.load('/data/qnn-host/deploy-20260926-opif/current-input.npz', allow_pickle=False)['new_img'].tobytes()
            assert len(pixels) == 393216
            scalars = struct.pack('<12f', *([0.] * 8 + [1., 0., .1, .2]))
            sent = 0
            started = time.monotonic()
            while len(rows) < 200:
                guard()
                session.check()
                while (value := session.poll()) is not None:
                    raw, context, wait, stats = value
                    age = (time.clock_gettime_ns(time.CLOCK_BOOTTIME) - context['eof']) / 1e6
                    assert 0 <= age < 200 and context['index'] == len(rows) + 1
                    assert len(raw) == 73808 and np.isfinite(np.frombuffer(raw, dtype='<f4')).all()
                    rows.append({'frame': context['index'], 'age_ms': age, **stats})
                if sent < 200 and time.monotonic() >= started + sent * .05:
                    eof = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
                    sent += 1
                    session.submit(sent, eof, pixels, scalars, {'index': sent, 'eof': eof})
                if time.monotonic() - started > 20:
                    raise TimeoutError('Bounded 200-frame replay exceeded 20 seconds')
                time.sleep(.001)
            report.update(passed=True, elapsed_seconds=time.monotonic() - started)
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if session:
            session.close()
        if link:
            link.close()
        report['completed_frames'] = len(rows)
        if rows:
            for field in ['age_ms', 'inference_ms', 'queue_ms']:
                report[field] = {key: float(np.percentile([r[field] for r in rows], q))
                                 for key, q in [('p50', 50), ('p95', 95), ('p99', 99), ('max', 100)]}
        report['offroad_after'] = params.get_bool('IsOffroad')
        report['engaged_after'] = params.get_bool('IsEngaged')
        report['real_control_request_after'] = params.get_bool('C3XLQnnWifiControl')
        (output / 'frames.json').write_text(json.dumps(rows, indent=2) + '\n')
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
