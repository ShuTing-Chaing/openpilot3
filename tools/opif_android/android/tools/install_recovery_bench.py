#!/usr/bin/env python3
"""C3-only temporary test APK install; stable rollback is already preserved."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path[:0] = ['/data/openpilot', '/data/qnn-host/attention-mask-20260927']
from normal_startup_bench import physical_guard
from openpilot.common.params import Params
from openpilot.sunnypilot.modeld_v2.external_host.probe_lock import exclusive_probe

p = argparse.ArgumentParser()
p.add_argument('--sha256', required=True)
p.add_argument('--label', required=True)
a = p.parse_args()
assert a.label.replace('-', '').isalnum()
base = Path('/data/qnn-host/opif-result-age-20260928')
apk = base / 'candidate.apk'
with apk.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == a.sha256
check = physical_guard()
check()
params = Params()
adb = ['adb', '-s', '3B168600EWF00000']
receipt = {'label': a.label, 'apk_sha256': a.sha256, 'control_before': params.get_bool('C3XLQnnWifiControl'), 'at': time.time()}
with exclusive_probe():
    check()
    result = subprocess.run(adb + ['install', '-r', str(apk)], capture_output=True, text=True, timeout=150)
    receipt.update(exit_code=result.returncode, output=result.stdout + result.stderr)
    (base / (a.label + '-install.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    if result.returncode or 'Success' not in result.stdout:
        raise RuntimeError(receipt['output'])
    print(subprocess.check_output(adb + ['shell', 'am', 'start', '-n', 'com.example.openpilotinference.android/.MainActivity', '-a', 'android.intent.action.MAIN'], text=True))
print(json.dumps(receipt), flush=True)
