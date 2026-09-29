"""Bounded, fixed-cadence TCP transfer and SHA256 verification; no model inference."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--interface', choices=['opifap0', 'usb0'], required=True)
    parser.add_argument('--bytes', type=int, required=True)
    args = parser.parse_args()
    socket.inet_aton(args.host)
    if not 1 <= args.bytes <= 1048576 or Path(args.name).name != args.name:
        parser.error('Invalid payload/name')
    sys.path[:0] = ['/data/openpilot', str(args.base / 'tools')]
    from normal_startup_recovery_bench import physical_guard
    check = physical_guard(); before = check()
    route = subprocess.check_output(['ip', '-4', 'route', 'get', args.host], text=True)
    if 'dev ' + args.interface + ' ' not in route:
        raise RuntimeError('Unexpected route')
    output = args.base / (args.name + '.json')
    if output.exists():
        raise RuntimeError('Evidence exists')
    subprocess.run(['sudo', '-n', 'touch', str(args.base / 'ap-149/lease')], check=True)
    payload = (bytes(range(256)) * ((args.bytes + 255) // 256))[:args.bytes]
    port = 5566
    command = ['adb', '-s', '3B168600EWF00000', 'shell',
               f'toybox nc -l -s {args.host} -p {port} -W 15 | toybox sha256sum']
    receiver = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    client = None; rows = []; expected = hashlib.sha256(); failure = None
    try:
        deadline = time.monotonic() + 5
        while client is None:
            try: client = socket.create_connection((args.host, port), timeout=1)
            except OSError:
                if time.monotonic() >= deadline: raise
                time.sleep(.1)
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        client.settimeout(2)
        start = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        for frame in range(200):
            target = start + frame * 50_000_000
            time.sleep(max(0, (target-time.clock_gettime_ns(time.CLOCK_BOOTTIME))/1e9))
            begin = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            client.sendall(payload)
            end = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            rows.append({'frame': frame, 'target_ns': target, 'begin_ns': begin, 'send_api_done_ns': end,
                         'send_ms': (end-begin)/1e6, 'schedule_late_ms': (begin-target)/1e6})
            expected.update(payload)
            if frame % 20 == 0:
                check()
        client.shutdown(socket.SHUT_WR)
    except BaseException as error:
        failure = type(error).__name__ + ': ' + str(error)
    finally:
        if client:
            client.close()
        try: stdout, stderr = receiver.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            receiver.terminate(); stdout, stderr = receiver.communicate(timeout=3)
    actual = stdout.strip().split()[0] if stdout.strip() else None
    result = {'scope': 'Pure TCP transfer, no model execution', 'route': route, 'payload_bytes': len(payload),
              'target_hz': 20, 'requested_frames': 200, 'sent_frames': len(rows), 'failure': failure,
              'receiver_command': command, 'receiver_exit_code': receiver.returncode, 'receiver_stderr': stderr,
              'expected_sha256': expected.hexdigest(), 'received_sha256': actual, 'bytes_verified': actual == expected.hexdigest(),
              'before': before, 'after': physical_guard()(), 'frames': rows}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('sent_frames', 'failure', 'bytes_verified', 'receiver_exit_code')}))
    return 0 if len(rows) == 200 and result['bytes_verified'] and failure is None else 1


if __name__ == '__main__':
    sys.exit(main())
