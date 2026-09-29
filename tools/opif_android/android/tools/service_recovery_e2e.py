#!/usr/bin/env python3
"""On C3: reproduce background-service process death without real vehicle output."""
import argparse
import json
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import time

sys.path[:0] = ['/data/openpilot', '/data/qnn-host/attention-mask-20260927']
from normal_startup_bench import physical_guard
from openpilot.common.params import Params
from openpilot.sunnypilot.modeld_v2.external_host.probe_lock import exclusive_probe
from openpilot.sunnypilot.modeld_v2.external_host.opif import wire

PACKAGE = 'com.example.openpilotinference.android'
ADB = ['adb', '-s', '3B168600EWF00000']


def adb(command, timeout=10):
    return subprocess.check_output(ADB + ['shell', command], text=True, timeout=timeout).strip()


def discover(host, port):
    try:
        with socket.create_connection((host, port), timeout=.3) as s:
            request = secrets.randbits(63) + 1
            message = wire.encode_message(wire.MessageType.DISCOVER, 0, request, b'')
            packet = message.datagrams[0]
            s.sendall(struct.pack('<I', len(packet)) + packet)
            def take(n):
                result = b''
                while len(result) < n:
                    part = s.recv(n - len(result))
                    if not part:
                        raise ConnectionError('EOF')
                    result += part
                return result
            size = struct.unpack('<I', take(4))[0]
            if not wire.HEADER_BYTES <= size <= wire.MAXIMUM_DATAGRAM_BYTES:
                return False
            header, body = wire.Header.decode_datagram(take(size))
            return header.message_type == wire.MessageType.ANNOUNCE and header.request_id == request and len(body) == wire.ANNOUNCEMENT_BODY_BYTES
    except (OSError, ValueError):
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--expect-restart', action='store_true')
    p.add_argument('--seconds', type=int, default=30)
    p.add_argument('--self-exit', action='store_true', help='Requires the explicit dumpsys-only test APK')
    a = p.parse_args()
    if not 10 <= a.seconds <= 120:
        p.error('Use a bounded 10..120 second observation')
    a.out.mkdir(exist_ok=False, parents=True)
    guard = physical_guard()
    profile = json.loads(Path('/data/qnn-host/active-host.json').read_text())
    params = Params()
    receipt = {'before': guard(), 'mode': 'app_self_exit' if a.self_exit else 'android_debug_crash', 'expect_restart': a.expect_restart,
               'control_before': params.get_bool('C3XLQnnWifiControl'), 'samples': [], 'command_outputs': {}}
    killed = False
    try:
        with exclusive_probe():
            guard()
            receipt['command_outputs']['initial_launcher'] = adb('am start -n ' + PACKAGE + '/.MainActivity -a android.intent.action.MAIN')
            ready_deadline = time.monotonic() + 20
            while not discover(profile['host'], profile['port']):
                guard()
                if time.monotonic() > ready_deadline:
                    raise RuntimeError('OPIF was not reachable before fault injection')
                time.sleep(.5)
            receipt['service_before'] = adb('dumpsys activity services ' + PACKAGE)
            receipt['command_outputs']['home'] = adb('input keyevent KEYCODE_HOME')
            time.sleep(1)
            pid = adb('pidof ' + PACKAGE)
            if not pid.isdigit():
                raise RuntimeError('Expected exactly one OPIF process')
            receipt['old_pid'] = int(pid)
            guard()
            begin = time.monotonic()
            # Android exposes this scoped debugging operation to adb shell.
            # It does not force-stop the package or change SELinux/permissions.
            if a.self_exit:
                receipt['command_outputs']['self_exit'] = adb('dumpsys activity service ' + PACKAGE + '/.InferenceService opif-e2e-exit')
                if 'OPIF_E2E scheduled_self_exit' not in receipt['command_outputs']['self_exit']:
                    raise RuntimeError('Test-only self-exit hook did not acknowledge')
            else:
                receipt['command_outputs']['crash'] = adb('am crash --user 0 ' + PACKAGE)
            killed = True
            recovered = False
            while time.monotonic() - begin < a.seconds:
                guard()
                current = adb('pidof ' + PACKAGE) if subprocess.run(ADB + ['shell', 'pidof', PACKAGE], stdout=subprocess.DEVNULL).returncode == 0 else ''
                ready = discover(profile['host'], profile['port'])
                row = {'seconds': time.monotonic() - begin, 'pid': current, 'opif_announce': ready}
                receipt['samples'].append(row)
                if current and current != pid and ready:
                    receipt['recovery_seconds_upper_bound'] = row['seconds']
                    recovered = True
                    break
                time.sleep(.5)
            receipt['recovered'] = recovered
            receipt['observed_seconds'] = time.monotonic() - begin
            receipt['matches_expectation'] = recovered == a.expect_restart
            receipt['service_after'] = adb('dumpsys activity services ' + PACKAGE)
    except Exception as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)
        receipt['matches_expectation'] = False
    finally:
        if killed and not receipt.get('recovered'):
            receipt['restore_launcher'] = adb('am start -n ' + PACKAGE + '/.MainActivity -a android.intent.action.MAIN')
        receipt['control_after'] = params.get_bool('C3XLQnnWifiControl')
        receipt['offroad_after'] = params.get_bool('IsOffroad')
        receipt['engaged_after'] = params.get_bool('IsEngaged')
        (a.out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({k: v for k, v in receipt.items() if k not in ['before', 'samples', 'service_before', 'service_after']}))
    return 0 if receipt.get('matches_expectation') else 1


if __name__ == '__main__':
    sys.exit(main())
