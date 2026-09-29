"""Own low-latency radio state only while a C3 QNN session is alive."""
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time

HELPER = Path(__file__).with_name('wifi_power_ctl')
LOCK = '/dev/shm/qnn-radio-power.lock'
STATUS = Path('/dev/shm/qnn-radio-power.json')


def _power(value=None):
  command = (["sudo", "-n"] if value is not None else []) + [str(HELPER), 'wlan0']
  if value is not None:
    command.append(value)
  result = subprocess.run(command, text=True, capture_output=True, timeout=4, check=True).stdout.strip()
  if result not in ('on', 'off') or (value is not None and result != value):
    raise RuntimeError('Radio power-save readback differs')
  return result


def _status(**values):
  values.update(pid=os.getpid(), updated_boottime=time.clock_gettime(time.CLOCK_BOOTTIME))
  temporary = STATUS.with_suffix(f'.{os.getpid()}.tmp')
  temporary.write_text(json.dumps(values) + '\n')
  temporary.replace(STATUS)


def _guard():
  descriptor = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
  original = None
  acquired = False
  def interrupted(*unused):
    raise SystemExit('Radio owner interrupted')
  signal.signal(signal.SIGTERM, interrupted)
  signal.signal(signal.SIGINT, interrupted)
  try:
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    acquired = True
    original = _power()
    _power('off')
    _status(active=True, previous=original, current='off', restored=False)
    print('READY', flush=True)
    # The owning model process is the sole writer. Process death also closes
    # this pipe, so restoration does not depend on Python destructors/atexit.
    while os.read(sys.stdin.fileno(), 1):
      pass
  finally:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
      if acquired and original is not None:
        try:
          actual = _power(original)
          _status(active=False, previous=original, current=actual, restored=True)
        except Exception as error:
          _status(active=False, previous=original, restored=False, error=str(error))
          raise
    finally:
      os.close(descriptor)


class WifiPowerLease:
  def __init__(self):
    self.closed = False
    self.proc = subprocess.Popen(
      [sys.executable, '-m', __name__, '--guard'], stdin=subprocess.PIPE,
      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
      close_fds=True,
    )
    readable, _, _ = select.select([self.proc.stdout], [], [], 12)
    if not readable or self.proc.stdout.readline() != b'READY\n':
      self.close(wait=True)
      raise RuntimeError('QNN radio low-latency lease unavailable; check helper/owner')

  def close(self, *, wait=False):
    if self.closed:
      return
    self.closed = True
    self.proc.stdin.close()
    def reap():
      try:
        self.proc.wait(timeout=12)
      except subprocess.TimeoutExpired:
        self.proc.terminate()
        self.proc.wait(timeout=8)
      finally:
        self.proc.stdout.close()
    if wait:
      reap()
    else:
      threading.Thread(target=reap, name='qnn-radio-restore', daemon=True).start()


if __name__ == '__main__':
  if sys.argv[1:] != ['--guard']:
    raise SystemExit('Private radio lease helper')
  _guard()
