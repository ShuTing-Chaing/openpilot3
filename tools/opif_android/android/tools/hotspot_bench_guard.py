"""Task-owned, expiring AP + DHCP; preserve the existing C3 management STA."""
import argparse
import json
import os
import pwd
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--channel', type=int, choices=[36, 149], required=True)
    parser.add_argument('--name')
    parser.add_argument('--lease-seconds', type=int, default=600)
    parser.add_argument('--reuse-from')
    args = parser.parse_args()
    base = args.base
    name = args.name or ('ap-' + str(args.channel))
    if Path(name).name != name or not 60 <= args.lease_seconds <= 1800:
        parser.error('Invalid unique name or bounded lease')
    state = base / name
    state.mkdir(exist_ok=False)
    os.chmod(state, 0o700)
    sys.path[:0] = ['/data/openpilot', str(base / 'tools')]
    from normal_startup_recovery_bench import physical_guard
    before = physical_guard()()
    psk = secrets.token_urlsafe(18)
    if args.reuse_from:
        if Path(args.reuse_from).name != args.reuse_from:
            parser.error('Credential source must be an existing task state name')
        previous = json.loads((base / args.reuse_from / 'credentials.json').read_text())
        if previous.get('ssid') != 'C3XL-OPIF-Test':
            raise RuntimeError('Not a task-owned hotspot credential')
        psk = previous['psk']
    credentials = {'ssid': 'C3XL-OPIF-Test', 'psk': psk, 'interface': 'opifap0', 'channel': args.channel, 'width_mhz_requested': 80, 'gateway': '10.42.83.1'}
    (state / 'credentials.json').write_text(json.dumps(credentials) + '\n')
    os.chmod(state / 'credentials.json', 0o600)
    (state / 'lease').touch()
    records, children = [], []
    created = False
    def record(command, check=True):
        proc = subprocess.run(command, capture_output=True, text=True, timeout=20)
        records.append({'command': command, 'exit_code': proc.returncode, 'stdout': proc.stdout.replace(psk, '<redacted>'), 'stderr': proc.stderr.replace(psk, '<redacted>')})
        (state / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
        if check and proc.returncode:
            raise RuntimeError(f'AP command failed: {command[0]}, exit={proc.returncode}')
        return proc
    def stop(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    failure = None
    try:
        record(['/usr/local/venv/bin/python', str(base / 'tools/wifi_ap_probe.py'), '--work', str(base / 'ap-probe'), '--action', 'create'])
        created = True
        # Runtime-only management flag, on a new interface owned by this task.
        record(['nmcli', 'device', 'set', 'opifap0', 'managed', 'no'], check=False)
        record(['ip', 'address', 'add', '10.42.83.1/24', 'dev', 'opifap0'])
        record(['ip', 'link', 'set', 'opifap0', 'up'])
        config = '\n'.join(['interface=opifap0', 'driver=nl80211', 'ssid=' + credentials['ssid'], 'hw_mode=a',
                             'channel=' + str(args.channel), 'ieee80211n=1', 'ieee80211ac=1', 'wmm_enabled=1',
                             'ht_capab=[HT40+]', 'vht_oper_chwidth=1', 'vht_oper_centr_freq_seg0_idx=' + ('42' if args.channel == 36 else '155'),
                             'auth_algs=1', 'wpa=2', 'wpa_key_mgmt=WPA-PSK', 'rsn_pairwise=CCMP', 'wpa_passphrase=' + psk,
                             'ctrl_interface=' + str(state / 'hostapd-control'), 'logger_stdout_level=2', ''])
        conf = state / 'hostapd.conf'; conf.write_text(config); os.chmod(conf, 0o600)
        hlog = (state / 'hostapd.log').open('w')
        children.append(subprocess.Popen(['/usr/sbin/hostapd', str(conf)], stdout=hlog, stderr=subprocess.STDOUT))
        # dnsmasq drops privileges; its own lease file must remain writable.
        account = pwd.getpwnam('nobody')
        lease_file = state / 'dhcp.leases'
        lease_file.touch(); os.chown(lease_file, account.pw_uid, account.pw_gid); os.chmod(lease_file, 0o600)
        os.chmod(state, 0o711)  # traversal only; credentials/config stay 0600
        dlog = (state / 'dnsmasq.log').open('w')
        children.append(subprocess.Popen(['/usr/sbin/dnsmasq', '--keep-in-foreground', '--conf-file=/dev/null', '--interface=opifap0', '--bind-interfaces',
            '--port=0', '--no-hosts', '--no-resolv', '--dhcp-authoritative', '--dhcp-range=10.42.83.20,10.42.83.50,255.255.255.0,1h',
            '--dhcp-option=3', '--dhcp-option=6', '--dhcp-leasefile=' + str(state / 'dhcp.leases'), '--log-dhcp'], stdout=dlog, stderr=subprocess.STDOUT))
        (state / 'processes.json').write_text(json.dumps({'guard': os.getpid(), 'hostapd': children[0].pid, 'dnsmasq': children[1].pid}) + '\n')
        start = time.monotonic()
        while True:
            for child in children:
                if child.poll() is not None:
                    raise RuntimeError(f'AP service exited {child.returncode}')
            if time.time() - (state / 'lease').stat().st_mtime > args.lease_seconds or time.monotonic() - start > 3600:
                raise RuntimeError('AP experiment lease expired')
            # The AP owns no vehicle control configuration. Stop when the
            # physical test boundary changes, without touching existing STA.
            physical_guard()()
            (state / 'status.json').write_text(json.dumps({'running': True, 'channel_requested': args.channel,
                'seconds': time.monotonic() - start, 'interface': 'opifap0'}) + '\n')
            time.sleep(5)
    except BaseException as error:
        failure = type(error).__name__ + ': ' + str(error)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
        if created:
            record(['/usr/local/venv/bin/python', str(base / 'tools/wifi_ap_probe.py'), '--work', str(base / 'ap-probe'), '--action', 'delete'], check=False)
        (state / 'result.json').write_text(json.dumps({'before': before, 'failure_or_stop': failure, 'interface_removed': not Path('/sys/class/net/opifap0').exists(),
            'children_exited': [p.returncode for p in children]}, indent=2) + '\n')


if __name__ == '__main__':
    main()
