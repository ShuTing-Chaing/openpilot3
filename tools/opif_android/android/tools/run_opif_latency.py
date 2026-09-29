"""One isolated WLAN latency round; keep original source/model eligibility."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def rewrite(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f'Bench source boundary changed: {old!r}')
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--mode', choices=['off', 'minimal', 'full'], required=True)
    parser.add_argument('--variant', choices=['a', 'b', 'untraced', 'wait10', 'wait10b'], default='a')
    parser.add_argument('--seconds', type=int, default=20)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--phone', default='192.168.102.105')
    parser.add_argument('--interface', choices=['wlan0', 'opifap0'], default='wlan0')
    parser.add_argument('--ap-state', default='ap-149')
    parser.add_argument('--io-cores', choices=['inherited', '4,5'], default='inherited')
    args = parser.parse_args()
    if (args.variant == 'untraced') != (args.mode == 'off'):
        parser.error('The untraced baseline must use mode off')
    if Path(args.name).name != args.name or not 10 <= args.seconds <= 3600 or not 0 <= args.warmup <= 60:
        parser.error('Invalid unique name or duration')
    if Path(args.ap_state).name != args.ap_state:
        parser.error('Invalid AP state name')
    if os.environ.get('OPENPILOT_PREFIX'):
        raise RuntimeError('Supervisor must use actual namespace')
    base, run = args.base, args.base / args.name
    if run.exists():
        raise RuntimeError('Evidence already exists')
    sys.path.insert(0, '/data/openpilot')
    sys.path.insert(0, str(base / 'tools'))
    from normal_startup_recovery_bench import physical_guard
    from openpilot.common.params import Params
    from openpilot.sunnypilot.modeld_v2.external_host.probe_lock import exclusive_probe
    check = physical_guard()
    p = Params()
    assert not p.get_bool('C3XLQnnWifiControl')
    before = check()
    route = subprocess.check_output(['ip', '-4', 'route', 'get', args.phone], text=True)
    if 'dev ' + args.interface + ' ' not in route:
        raise RuntimeError('This round must use WLAN, not USB')
    if args.interface == 'opifap0':
        subprocess.run(['sudo', '-n', 'touch', str(base / args.ap_state / 'lease')], check=True)
    adb = ['adb', '-s', '3B168600EWF00000', 'shell']
    package = 'com.example.openpilotinference.android'
    def phone_state():
        result = {}
        for key, command in {'pid': ['pidof', package], 'battery': ['dumpsys', 'battery'],
                             'thermal': ['dumpsys', 'thermalservice'], 'addresses': ['ip', '-4', 'addr'],
                             'display': ['dumpsys', 'power']}.items():
            r = subprocess.run(adb + command, text=True, capture_output=True, timeout=10)
            result[key] = {'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
        return result
    handset = phone_state()
    if not handset['pid']['stdout'].strip():
        raise RuntimeError('OPIF is not running; no restart or keepalive work is allowed')
    code = base / ('code-observe-v2' if args.variant == 'a' else 'code-' + args.variant)
    model = code / 'openpilot/sunnypilot/modeld_v2/modeld.py'
    source = Path('/data/openpilot/openpilot/sunnypilot/modeld_v2/modeld.py')
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    launcher = base / (args.name + '-modeld')
    launch = source.with_name('modeld').read_text()
    launch = rewrite(launch, 'QNN_CONFIG=/data/qnn-host/active-host.json', 'QNN_CONFIG=' + str(run / 'profile.json'))
    launch = rewrite(launch, 'exec "$DIR/modeld.py" "$@"', 'exec "' + str(model) + '" "$@"')
    launcher.write_text(launch); launcher.chmod(0o755); model.chmod(0o755)
    bench = (base / 'tools/normal_startup_recovery_bench.py').read_text()
    bench = rewrite(bench, "  options=subprocess.check_output(['nmcli','-f','DHCP4.OPTION','dev','show','usb0'],text=True)\n  router=re.search(r'\\brouters = ([0-9.]+)',options)\n  if not router or router.group(1)!=a.phone or 'dev usb0' not in subprocess.check_output(['ip','-4','route','get',a.phone],text=True):raise RuntimeError('Phone is not routed through USB DHCP link')\n  if Path('/sys/class/net/usb0/device/driver').resolve().name not in ('rndis_host','cdc_ncm'):raise RuntimeError('USB network driver differs')",
                    "  if 'dev " + args.interface + " ' not in subprocess.check_output(['ip','-4','route','get',a.phone],text=True):raise RuntimeError('Phone is not routed through the selected WLAN interface')")
    bench = rewrite(bench, "(Path(__file__).parent/'startup_observation.py').read_text()", "(Path(__file__).parent/'tools/latency_sitecustomize.py').read_text()")
    # Once-per-second supervisor observations; no new work in model/I/O threads.
    monitor = """     radio_read=subprocess.run([str(wifi_tool),'wlan0'],text=True,capture_output=True,timeout=2)
     radio_state={'power_save':radio_read.stdout.strip(),'exit_code':radio_read.returncode}
     radio_owner=Path('/dev/shm/qnn-radio-power.json')
     if radio_owner.exists():
      try:radio_state['owner']=json.loads(radio_owner.read_text())
      except (OSError,ValueError):pass
     io_threads=[]
     for owner,proc in children:
      if owner!='modeld':continue
      descendants=set()
      identity_path=a.run/'io-process-identity.json'
      if identity_path.exists():
       try:descendants.add(str(json.loads(identity_path.read_text())['worker_pid']))
       except (OSError,ValueError,KeyError):pass
      for task in Path(f'/proc/{proc.pid}/task').glob('*/children'):
       try:descendants.update(task.read_text().split())
       except OSError:pass
      for pid in descendants:
       try:
        if int(pid)!=json.loads(identity_path.read_text()).get('worker_pid'):continue
        for task in Path(f'/proc/{pid}/task').iterdir():
         text= (task/'stat').read_text();fields=text[text.rfind(')')+2:].split()
         status=(task/'status').read_text();allowed=next(x.split(':',1)[1].strip() for x in status.splitlines() if x.startswith('Cpus_allowed_list:'))
         io_threads.append({'pid':int(pid),'tid':int(task.name),'cpu':int(fields[36]),'policy':int(fields[38]),'allowed':allowed,'schedstat':(task/'schedstat').read_text().strip()})
       except (OSError,ValueError,IndexError,StopIteration):pass
"""
    bench = rewrite(bench, '     proc_stats={}\n', '     proc_stats={}\n' + monitor)
    bench = rewrite(bench, "'runtime':runtime,'processes':proc_stats}", "'runtime':runtime,'processes':proc_stats,'radio':radio_state,'io_threads':io_threads}")
    benchfile = base / (args.name + '-bench.py')
    benchfile.write_text(bench)
    receipt = {'arguments': vars(args) | {'base': str(base)}, 'before': before, 'route': route,
               'phone_before': handset, 'production_sha256_before': source_sha,
               'startup_sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
               'code_sha256': json.loads((code / 'instrumentation-sha256.json').read_text()),
               'clock': 'All trace stamps C3 CLOCK_BOOTTIME; camera EOF=SOF+sensor.readout_time_ns',
               'carrier': args.interface + '; USB only power/ADB', 'input': 'Real paired cameras at existing 20Hz; not identical pixel replay'}
    watcher = None
    try:
        with exclusive_probe():
            check()
            found = subprocess.check_output(['pgrep', '-fx', 'openpilot.sunnypilot.modeld_v2.external_host.qnn_discoveryd'], text=True).split()
            assert len(found) == 1
            watcher = int(found[0])
            assert Path(f'/proc/{watcher}/stat').read_text().split(') ', 1)[1][0] != 'T'
            os.kill(watcher, signal.SIGSTOP)
        parent = int(Path(f'/proc/{watcher}/stat').read_text().split()[3])
        inherited = dict(x.split(b'=', 1) for x in Path(f'/proc/{parent}/environ').read_bytes().split(b'\0') if b'=' in x)
        env = os.environ.copy()
        env.update(PATH=inherited[b'PATH'].decode(), PYTHONPATH='/data/openpilot',
                   OPIF_LATENCY_CODE=str(code), OPIF_LATENCY_TOOLS=str(base / 'tools'), OPIF_LATENCY_RUN=str(run),
                   OPIF_LATENCY_MODE=args.mode, OPIF_LATENCY_SECONDS=str(args.seconds + args.warmup))
        env['OPIF_LATENCY_IO_CORES'] = args.io_cores
        env.pop('QNN_STAGE_TRACE', None)
        command = ['/usr/local/venv/bin/python', str(benchfile), '--run', str(run), '--seconds', str(args.seconds + args.warmup),
                   '--usb', '--phone', args.phone, '--modeld-launcher', str(launcher)]
        receipt['command'] = command
        with (base / (args.name + '-command.log')).open('w') as log:
            process = subprocess.Popen(command, env=env, cwd='/data/openpilot', stdout=log, stderr=subprocess.STDOUT)
            try:
                receipt['exit_code'] = process.wait(timeout=args.seconds + args.warmup + 220)
            except BaseException:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=60)
                raise
    finally:
        if watcher:
            os.kill(watcher, signal.SIGCONT)
        receipt['after'] = physical_guard()()
        receipt['phone_after'] = phone_state()
        receipt['production_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
        receipt['control_request_after'] = p.get_bool('C3XLQnnWifiControl')
        receipt['app_pid_unchanged'] = handset['pid']['stdout'].strip() == receipt['phone_after']['pid']['stdout'].strip()
        (base / (args.name + '-receipt.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: receipt.get(k) for k in ('exit_code', 'production_unchanged', 'control_request_after', 'app_pid_unchanged')}))
    return receipt.get('exit_code', 1)


if __name__ == '__main__':
    sys.exit(main())
