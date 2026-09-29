"""One normal production launcher test in the existing actuator-isolated bench."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.path[:0] = ['/data/openpilot', '/data/qnn-host/attention-mask-20260927']
from normal_startup_bench import physical_guard
from openpilot.common.params import Params
from openpilot.sunnypilot.modeld_v2.external_host.probe_lock import exclusive_probe

base = Path('/data/qnn-host/opif-result-age-20260928')
parser = argparse.ArgumentParser()
parser.add_argument('--variant', choices=['stable', 'candidate'], default='stable')
parser.add_argument('--run-name', required=True)
parser.add_argument('--seconds', type=int, default=60)
args = parser.parse_args()
if Path(args.run_name).name != args.run_name or not 10 <= args.seconds <= 3600:
    parser.error('A single directory name and 10..3600 seconds are required')
run = base / args.run_name
assert not run.exists(), 'Evidence must not be overwritten'
production = Path('/data/openpilot/openpilot/sunnypilot/modeld_v2/modeld.py')
launcher = production.with_name('modeld')
production_sha = hashlib.sha256(production.read_bytes()).hexdigest()
source_shas = {str(production): production_sha}
if args.variant == 'candidate':
    candidate = base / 'modeld-candidate.py'
    assert candidate.is_file()
    candidate.chmod(0o755)
    original = launcher.read_text()
    old_exec = 'exec "$DIR/modeld.py" "$@"'
    assert original.count(old_exec) == 1 and original.rstrip().endswith(old_exec)
    launcher = base / (args.run_name + '-modeld')
    assert not launcher.exists()
    launcher.write_text(original.replace(old_exec, 'exec "' + str(candidate) + '" "$@"'))
    launcher.chmod(0o755)
    source_shas[str(candidate)] = hashlib.sha256(candidate.read_bytes()).hexdigest()
source_shas[str(launcher)] = hashlib.sha256(launcher.read_bytes()).hexdigest()
check = physical_guard()
receipt = {'before': check(), 'variant': args.variant, 'source_sha256': source_shas}
params = Params()
assert not params.get_bool('C3XLQnnWifiControl')
watcher = None
try:
    with exclusive_probe():
        check()
        found = subprocess.check_output(['pgrep', '-fx', 'openpilot.sunnypilot.modeld_v2.external_host.qnn_discoveryd'], text=True).split()
        assert len(found) == 1
        watcher = int(found[0])
        os.kill(watcher, signal.SIGSTOP)
    parent = int(Path(f'/proc/{watcher}/stat').read_text().split()[3])
    env = dict(x.split(b'=', 1) for x in Path(f'/proc/{parent}/environ').read_bytes().split(b'\0') if b'=' in x)
    os.environ['PATH'] = env[b'PATH'].decode()
    host = json.loads(Path('/data/qnn-host/active-host.json').read_text())['host']
    command = ['/usr/local/venv/bin/python', str(base / 'normal_startup_recovery_bench.py'),
               '--run', str(run), '--seconds', str(args.seconds), '--usb', '--phone', host,
               '--modeld-launcher', str(launcher)]
    receipt['command'] = command
    p = subprocess.run(command, cwd='/data/openpilot', timeout=args.seconds + 220)
    receipt['exit_code'] = p.returncode
finally:
    if watcher:
        os.kill(watcher, signal.SIGCONT)
    receipt['after'] = physical_guard()()
    receipt['control_request_after'] = params.get_bool('C3XLQnnWifiControl')
    receipt['production_source_unchanged'] = hashlib.sha256(production.read_bytes()).hexdigest() == production_sha
    (base / (args.run_name + '-receipt.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('before', 'after')}), flush=True)
sys.exit(receipt['exit_code'])
