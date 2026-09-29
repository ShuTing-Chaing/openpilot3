#!/usr/bin/env python3
"""Run on C3: bounded offline phone measurements, with OPIF restored afterward."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, '/data/openpilot')
from openpilot.common.params import Params
from openpilot.sunnypilot.modeld_v2.external_host.probe_lock import exclusive_probe

BASE = Path('/data/qnn-host/opif-attention-20260928')
PHONE = '/data/local/tmp/opif-attention-20260928'
ADB = ['adb', '-s', '3B168600EWF00000']
PACKAGE = 'com.example.openpilotinference.android'
params = Params()


def guard():
    if (subprocess.check_output(['hostname'], text=True).strip() != 'comma-9c13c9f5'
            or not params.get_bool('IsOffroad') or params.get_bool('IsEngaged')
            or subprocess.run(['pgrep', '-x', 'camerad'], stdout=subprocess.DEVNULL).returncode == 0):
        raise RuntimeError('Device is not idle offroad; end phone benchmark')


def shell(command, timeout=15):
    return subprocess.check_output(ADB + ['shell', command], text=True, timeout=timeout)


def main():
    guard()
    receipt = {'runs': [], 'real_control_request_before': params.get_bool('C3XLQnnWifiControl'),
               'phone_app': PACKAGE, 'ni_retired': False, 'began_at': time.time()}
    active = None
    suspended = False
    try:
        with exclusive_probe():
            guard()
            shell('am force-stop ai.mile.npuserver')
            receipt['ni_retired'] = True
            # The service is not exported. Stop the idle package through Android's
            # package manager, then restore through its exported launcher.
            shell('am force-stop ' + PACKAGE)
            suspended = True
            deadline = time.monotonic() + 20
            while 'ServiceRecord{' in shell('dumpsys activity services ' + PACKAGE):
                guard()
                if time.monotonic() > deadline:
                    raise RuntimeError('OPIF service did not finish stopping')
                time.sleep(.5)
            for mode in ['pair', 'a1', 'b1', 'a2']:
                guard()
                (BASE / 'progress.json').write_text(json.dumps({'mode': mode, 'started_at': time.time()}) + '\n')
                active = subprocess.Popen(ADB + ['shell', 'sh ' + PHONE + '/run.sh ' + mode],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                started = time.monotonic()
                while active.poll() is None:
                    guard()
                    if time.monotonic() - started > 330:
                        raise RuntimeError('Bounded phone benchmark timeout')
                    time.sleep(1)
                row = {'mode': mode, 'exit_code': active.returncode, 'wall_seconds': time.monotonic() - started}
                receipt['runs'].append(row)
                print(json.dumps(row), flush=True)
                if active.returncode:
                    raise RuntimeError('Phone benchmark failed in ' + mode)
                active = None
            receipt['completed'] = True
    except BaseException as error:
        receipt['completed'] = False
        receipt['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if active is not None and active.poll() is None:
            try:
                shell("pkill -f '^" + PHONE + "/(attention_mask_device_e2e|opif-server)( |$)'", timeout=5)
            except Exception:
                pass
            active.terminate()
            try:
                active.wait(timeout=5)
            except subprocess.TimeoutExpired:
                active.kill()
                active.wait()
        if suspended:
            try:
                receipt['restore_request'] = shell('am start -n ' + PACKAGE +
                                                   '/.MainActivity -a android.intent.action.MAIN')
            except Exception as error:
                receipt['restore_error'] = str(error)
        receipt['real_control_request_after'] = params.get_bool('C3XLQnnWifiControl')
        receipt['offroad_after'] = params.get_bool('IsOffroad')
        receipt['engaged_after'] = params.get_bool('IsEngaged')
        (BASE / 'device-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt), flush=True)
    return 0 if receipt.get('completed') else 1


if __name__ == '__main__':
    sys.exit(main())
