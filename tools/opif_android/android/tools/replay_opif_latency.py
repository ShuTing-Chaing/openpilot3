"""Reuse the existing 200-frame OPIF fixture at 20Hz, without camera/GPU load."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--interface', choices=['opifap0', 'usb0'], required=True)
    parser.add_argument('--idle-seconds', type=float, default=0)
    parser.add_argument('--ap-state', default='ap-36')
    parser.add_argument('--variant', choices=['a', 'b'], default='a')
    parser.add_argument('--frames', type=int, default=200)
    parser.add_argument('--warmup-frames', type=int, default=40)
    parser.add_argument('--trace-mode', choices=['minimal', 'full'], default='full')
    parser.add_argument('--radio-profile', choices=['existing', 'onroad'], default='existing')
    args = parser.parse_args()
    if Path(args.name).name != args.name or Path(args.ap_state).name != args.ap_state or not 0 <= args.idle_seconds <= 15:
        parser.error('Invalid name or idle period')
    if not 40 < args.frames <= 72000 or not 0 <= args.warmup_frames < args.frames:
        parser.error('Invalid bounded frame count/warmup')
    base, run = args.base, args.base / args.name
    run.mkdir(exist_ok=False)
    sys.path[:0] = ['/data/openpilot', str(base / 'tools')]
    from normal_startup_recovery_bench import physical_guard
    from openpilot.sunnypilot.modeld_v2.external_host.probe_lock import exclusive_probe
    from openpilot.common.params import Params
    check = physical_guard(); before = check(); params = Params()
    assert not params.get_bool('C3XLQnnWifiControl')
    route = subprocess.check_output(['ip', '-4', 'route', 'get', args.host], text=True)
    assert 'dev ' + args.interface + ' ' in route
    if args.interface == 'opifap0':
        subprocess.run(['sudo', '-n', 'touch', str(base / args.ap_state / 'lease')], check=True)
    code = base / ('code-observe-v2' if args.variant == 'a' else 'code-b')
    os.environ.update(OPENPILOT_PREFIX='qnnbench_replay_' + uuid.uuid4().hex[:8], OPIF_LATENCY_MODE=args.trace_mode,
                      OPIF_LATENCY_SECONDS=str(int(args.frames / 20 + args.idle_seconds + 10)), OPIF_LATENCY_RUN=str(run), OPIF_LATENCY_INPUT_KIND='scheduled_fixed_replay',
                      OPIF_LATENCY_CODE=str(code), OPIF_LATENCY_TOOLS=str(base / 'tools'))
    os.environ['PYTHONPATH'] = str(base / 'replay-observation') + ':/data/openpilot'
    import runpy
    runpy.run_path(str(base / 'tools/latency_sitecustomize.py'))
    from openpilot.sunnypilot.modeld_v2.external_host.qnn_client import connect_qnn
    from openpilot.sunnypilot.modeld_v2.external_host.session import AsyncSession
    import numpy as np
    fixture = Path('/data/qnn-host/deploy-20260926-opif/current-input.npz')
    pixels = np.load(fixture, allow_pickle=False)['new_img'].tobytes(); assert len(pixels) == 393216
    scalars = struct.pack('<12f', *([0.] * 8 + [1., 0., .1, .2]))
    report = {'input_time_basis': 'scheduled replay time, not camera EOF', 'actual_vehicle_publications': 0,
              'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(), 'target_hz': 20, 'requested_frames': args.frames,
              'before': before, 'route': route, 'idle_seconds': args.idle_seconds, 'completed': False,
              'variant': args.variant, 'warmup_frames': args.warmup_frames, 'trace_mode': args.trace_mode,
              'code_sha256': json.loads((code / 'instrumentation-sha256.json').read_text())}
    adb = ['adb', '-s', '3B168600EWF00000', 'shell']
    def phone_snapshot():
        snapshot = {}
        for key, command in {'battery': ['dumpsys', 'battery'], 'wifi': ['cmd', 'wifi', 'status'],
                             'power': ['dumpsys', 'power'], 'pid': ['pidof', 'com.example.openpilotinference.android']}.items():
            p = subprocess.run(adb + command, text=True, capture_output=True, timeout=10)
            snapshot[key] = {'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
        return snapshot
    report['phone_before'] = phone_snapshot()
    if not report['phone_before']['pid']['stdout'].strip():
        raise RuntimeError('OPIF is unavailable; do not restart it in this task')
    def c3_power_snapshot():
        values = {}
        for path in [Path('/sys/devices/system/cpu/online'), *Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_governor'),
                     *Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_max_freq'), *Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_cur_freq')]:
            values[str(path)] = path.read_text().strip()
        from openpilot.sunnypilot.modeld_v2.external_host.wifi_power import _power
        values['wifi_power_save'] = _power()
        return values
    report['power_before'] = c3_power_snapshot()
    report['radio_profile'] = args.radio_profile
    session = link = radio = None; results = []; submitted = []; error = None
    try:
        with exclusive_probe():
            check()
            if args.radio_profile == 'onroad':
                from openpilot.sunnypilot.modeld_v2.external_host.wifi_power import WifiPowerLease
                assert report['power_before']['/sys/devices/system/cpu/online'] == '0-7'
                for policy in (0, 4):
                    prefix = f'/sys/devices/system/cpu/cpufreq/policy{policy}/'
                    assert report['power_before'][prefix + 'scaling_governor'] == 'performance'
                    assert report['power_before'][prefix + 'scaling_max_freq'] == '1689600'
                radio = WifiPowerLease()
            report['power_active'] = c3_power_snapshot()
            if args.radio_profile == 'onroad':
                assert report['power_active']['wifi_power_save'] == 'off'
            profile = json.loads(Path('/data/qnn-host/active-host.json').read_text()); profile.update(host=args.host, allow_control=False)
            (run / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n')
            link = connect_qnn(profile, 'diagnostic'); report['hello'] = link.hello()
            session = AsyncSession(link)
            idle_until = time.monotonic() + args.idle_seconds
            while time.monotonic() < idle_until:
                check(); time.sleep(.02)
            start = time.clock_gettime_ns(time.CLOCK_BOOTTIME); next_guard = time.monotonic()
            while len(results) < args.frames:
                if time.monotonic() >= next_guard:
                    check(); next_guard = time.monotonic() + .2
                session.check()
                while (value := session.poll()) is not None:
                    raw, context, _, stats = value
                    assert context['index'] == len(results) + 1 and len(raw) == 73808
                    assert np.isfinite(np.frombuffer(raw, dtype='<f4')).all()
                    results.append({'frame': context['index'], 'received_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                                    'scheduled_ns': context['eof'], 'sha256': hashlib.sha256(raw).hexdigest(), 'stats': stats})
                due = start + len(submitted) * 50_000_000
                if len(submitted) < args.frames and time.clock_gettime_ns(time.CLOCK_BOOTTIME) >= due:
                    i = len(submitted) + 1
                    meta = SimpleNamespace(frame_id=i, timestamp_sof=due, timestamp_eof=due)
                    context = {'index': i, 'eof': due, 'meta_main': meta, 'meta_extra': meta}
                    at = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
                    session.submit(i, due, pixels, scalars, context)
                    submitted.append({'request': i, 'scheduled_ns': due, 'actual_submit_ns': at, 'late_ms': (at-due)/1e6})
                if time.clock_gettime_ns(time.CLOCK_BOOTTIME) - start > int((args.frames / 20 + 10) * 1e9):
                    raise TimeoutError('Fixed-cadence replay exceeded its bounded duration')
                time.sleep(.001)
            report['completed'] = True
    except Exception as e:
        error = type(e).__name__ + ': ' + str(e)
    finally:
        if session: session.close()
        if link: link.close()
        if radio: radio.close(wait=True)
        os.environ.pop('OPENPILOT_PREFIX', None)
        report.update(error=error, submitted=submitted, results=results, after=check(), control_request_after=params.get_bool('C3XLQnnWifiControl'))
        report['phone_after'] = phone_snapshot()
        report['app_pid_unchanged'] = report['phone_before']['pid']['stdout'].strip() == report['phone_after']['pid']['stdout'].strip()
        report['power_after'] = c3_power_snapshot()
        (run / 'replay-result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'completed': report['completed'], 'submitted': len(submitted), 'results': len(results), 'error': error}))
    return 0 if report['completed'] else 1


if __name__ == '__main__':
    sys.exit(main())
