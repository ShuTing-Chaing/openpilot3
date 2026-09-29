"""Bounded OPIF I/O process: Tinygrad's interpreter cannot delay socket pumping."""
from collections import OrderedDict, deque
from multiprocessing.connection import Connection
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time

from .qnn_client import QnnError
from .faults import classify, fault_kind, from_wire, TransportUnavailable, HistoryResetRequired, FatalModelFault


def send(conn, header, payload=b''):
  encoded = json.dumps(header, separators=(',', ':'), allow_nan=False).encode()
  if len(encoded) > 16384 or len(payload) > 393264:
    raise QnnError('OPIF IPC size bound')
  conn.send_bytes(struct.pack('<I', len(encoded)) + encoded + payload)


def receive(conn, *, payload_view=False):
  data = conn.recv_bytes(410000)
  if len(data) < 4:
    raise QnnError('Short OPIF IPC record')
  size = struct.unpack_from('<I', data)[0]
  if size > 16384 or size > len(data) - 4:
    raise QnnError('Invalid OPIF IPC header')
  value = json.loads(data[4:4 + size])
  if not isinstance(value, dict):
    raise QnnError('Invalid OPIF IPC object')
  # recv_bytes owns an immutable record. Keep it alive through a view until
  # OpifLink.submit takes its owned image snapshot, avoiding two large slices.
  payload = memoryview(data) if payload_view else data
  return value, payload[4 + size:]


class ProcessOpifLink:
  queue_capacity = 4
  supports_soft_expiry = True

  def __init__(self, profile, client_role):
    control = profile.get('control_qualified') is True and profile.get('allow_control') is True
    if client_role not in ('shadow', 'diagnostic', 'modeld') or (client_role == 'modeld' and not control) or (profile.get('allow_control') is True and not control):
      raise QnnError('OPIF control requires verified model outputs, timing and fallback')
    self.profile, self.role = dict(profile), client_role
    self.health = None
    self.result_schema = profile.get('result_schema', 'full_f32')
    if self.result_schema not in ('full_f32', 'control_heads_f32'):
      raise QnnError('Unknown OPIF result schema')
    self.result_bytes = 8272 if self.result_schema == 'control_heads_f32' else 73808
    self.sent = OrderedDict()
    self.lock, self.tx_lock = threading.Lock(), threading.Lock()
    self.sequence = 0
    self.error = None
    self.stopped = threading.Event()
    self.frame_timeout = float(profile.get('result_timeout_seconds', .2))
    self.stage_enabled = os.getenv('OPENPILOT_PREFIX', '').startswith('qnnbench_') and os.getenv('QNN_STAGE_TRACE') == '1'
    self.stage_enabled |= profile.get('diagnostic_stage_trace') is True and client_role == 'shadow'
    self.stages = {}
    self.recent_receipts = deque(maxlen=64)
    if not .05 <= self.frame_timeout <= .2:
      raise QnnError('OPIF deadline must be50..200ms')
    self.sock, child = socket.socketpair()
    self.conn = Connection(os.dup(self.sock.fileno()))
    env = os.environ.copy()
    root = str(Path(__file__).resolve().parents[4])
    env['PYTHONPATH'] = root + os.pathsep + env.get('PYTHONPATH', '')
    try:
      self.proc = subprocess.Popen([sys.executable, '-m', __name__, '--worker-fd', str(child.fileno())],
          pass_fds=(child.fileno(),), env=env, cwd=root, start_new_session=True,
          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except BaseException:
      self.conn.close(); self.sock.close()
      raise
    finally:
      child.close()

  def hello(self, timeout=5):
    try:
      send(self.conn, {'type': 'open', 'profile': self.profile, 'role': self.role, 'timeout': timeout})
      if not self.conn.poll(timeout + 2):
        raise TransportUnavailable('OPIF I/O process startup timeout')
      header, data = receive(self.conn)
      if header.get('type') == 'error':
        raise from_wire(header.get('error_kind'), header.get('error', 'OPIF worker failed to start'))
      if header.get('type') != 'ready' or data:
        raise QnnError(header.get('error', 'OPIF worker did not become ready'))
      self.health = header['health']
      return self.health
    except Exception as error:
      self.close()
      raise classify(error) from error

  def submit(self, frame_id, eof, pixels, scalars, reset_temporal=False):
    if self.stopped.is_set() or self.proc.poll() is not None:
      raise TransportUnavailable('OPIF I/O process is stopped')
    if len(pixels) != 393216 or len(scalars) != 48 or frame_id < 0 or eof <= 0:
      raise QnnError('Invalid OPIF IPC frame')
    with self.lock:
      if len(self.sent) >= self.queue_capacity:
        raise HistoryResetRequired('OPIF IPC capture window full')
      self.sequence += 1
      seq = self.sequence
      self.sent[seq] = (int(frame_id), int(eof), time.monotonic())
    try:
      with self.tx_lock:
        stage = {'t_parent_submit_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME)} if self.stage_enabled else {}
        if self.stage_enabled:self.stages[seq] = stage
        send(self.conn, {'type': 'frame', 'seq': seq, 'frame_id': int(frame_id), 'eof_ns': int(eof),
                         'reset_temporal': bool(reset_temporal), **stage}, bytes(scalars) + bytes(pixels))
        if self.stage_enabled:stage['t_parent_ipc_done_ns'] = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    except Exception as error:
      self.error = error
      self.stopped.set()
      raise classify(error) from error
    return seq

  def result(self, timeout=.2):
    end = time.monotonic() + timeout
    while True:
      if self.stopped.is_set():
        raise TransportUnavailable('OPIF IPC closed')
      if self.conn.poll(min(.02, max(0, end - time.monotonic()))):
        header, raw = receive(self.conn)
        if header.get('type') == 'error':
          raise from_wire(header.get('error_kind'), header.get('error', 'OPIF worker error'))
        if header.get('type') != 'result' or len(raw) != self.result_bytes:
          raise QnnError('Invalid OPIF IPC result')
        seq, fid, eof = (int(header[k]) for k in ('seq', 'frame_id', 'eof_ns'))
        with self.lock:
          if not self.sent or seq != next(iter(self.sent)):
            raise QnnError('OPIF IPC result order mismatch')
          expected = self.sent.pop(seq)
        now = time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time, 'CLOCK_BOOTTIME') else time.monotonic()
        if expected[:2] != (fid, eof):
          raise QnnError('OPIF IPC result identity mismatch')
        stats = header.get('stats', {})
        if (stats.get('result_schema') != self.result_schema or stats.get('opif_session_id') != self.health['opif_session_id'] or
            stats.get('state_epoch') != self.health['state_epoch'] or stats.get('request_id') != seq or
            stats.get('terminal') not in ('executed', 'expired')):
          raise FatalModelFault('OPIF IPC result state/schema identity mismatch')
        if self.stage_enabled:
          self.recent_receipts.append({'seq': seq, 'frame_id': fid, 'eof_ns': eof,
              'parent_observed_ns': int(now * 1e9), 'age_valid': 0 <= now - eof / 1e9 < self.frame_timeout,
              'stats': dict(stats)})
        if now - eof / 1e9 < 0:
          raise QnnError('OPIF IPC result capture is in the future')
        if now - eof / 1e9 >= self.frame_timeout:
          stats = dict(stats, terminal='expired')
        # Local validation boundary, not a phone timestamp or NIC arrival time.
        stats = dict(stats, parent_validated_boottime_ns=int(now * 1e9))
        if self.stage_enabled:
          stats = dict(stats, **self.stages.pop(seq, {}), t_parent_receive_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME))
        return seq, fid, eof, raw, stats
      if self.proc.poll() is not None:
        raise TransportUnavailable('OPIF I/O process exited')
      if time.monotonic() >= end:
        return None

  def close(self, *, wait=True):
    self.stopped.set()
    try:
      self.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
      pass
    self.sock.close()
    def reap():
      try:
        if self.stage_enabled:
          try:
            folder = Path('/data/qnn-host/opif-failure-traces'); folder.mkdir(exist_ok=True)
            snapshot = {'event': 'parent_link_close', 'pid': os.getpid(), 'worker_pid': self.proc.pid,
                        'at_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                        'recent_receipts': list(self.recent_receipts), 'pending_stages': dict(self.stages)}
            (folder / f'parent-{os.getpid()}-{self.proc.pid}-{snapshot["at_ns"]}.json').write_text(json.dumps(snapshot)+'\n')
          except (OSError, ValueError, TypeError, RuntimeError):
            pass
        self.proc.wait(timeout=2)
      except subprocess.TimeoutExpired:
        self.proc.terminate()
        try:
          self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
          self.proc.kill(); self.proc.wait()
      finally:
        self.conn.close()
    if wait:
      reap()
    else:
      threading.Thread(target=reap, name='opif-reap', daemon=True).start()


def worker(fd):
  from .priority import background_thread
  from .opif_client import OpifLink
  background_thread()
  conn = Connection(fd)
  link = None
  stage_enabled = os.getenv('OPENPILOT_PREFIX', '').startswith('qnnbench_') and os.getenv('QNN_STAGE_TRACE') == '1'
  stages = {}
  try:
    header, payload = receive(conn)
    if header.get('type') != 'open' or payload:
      raise QnnError('OPIF worker requires open')
    profile = header['profile']
    stage_enabled |= profile.get('diagnostic_stage_trace') is True and header['role'] == 'shadow'
    link = OpifLink(profile, header['role'])
    health = link.hello(timeout=float(header.get('timeout', 5)))
    send(conn, {'type': 'ready', 'health': dict(health, io_process=True)})
    while True:
      if link.error is not None:
        raise link.error
      if conn.poll(.001):
        header, data = receive(conn, payload_view=True)
        arrived = time.clock_gettime_ns(time.CLOCK_BOOTTIME) if stage_enabled else 0
        if header.get('type') != 'frame' or len(data) != 393264:
          raise QnnError('Invalid OPIF worker request')
        seq = link.submit(header['frame_id'], header['eof_ns'], data[48:], data[:48],
                          reset_temporal=bool(header.get('reset_temporal', False)))
        if stage_enabled:
          stages[seq] = {'t_parent_submit_ns': header['t_parent_submit_ns'], 't_worker_receive_ns': arrived}
        if seq != header.get('seq'):
          raise QnnError('OPIF worker sequence mismatch')
      while not link.completed.empty():
        value = link.result(.01)
        if value is None:
          break
        seq, fid, eof, raw, stats = value
        if stage_enabled:
          stats = dict(stats, **stages.pop(seq, {}), t_worker_forward_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME))
        send(conn, {'type': 'result', 'seq': seq, 'frame_id': fid, 'eof_ns': eof, 'stats': stats}, raw)
  except EOFError:
    pass
  except Exception as error:
    try:
      send(conn, {'type': 'error', 'error_kind': fault_kind(error), 'error': str(error)[:200]})
    except Exception:
      pass
  finally:
    if link is not None:
      link.close()
    conn.close()


if __name__ == '__main__':
  if len(sys.argv) != 3 or sys.argv[1] != '--worker-fd':
    raise SystemExit('Private inherited IPC descriptor required')
  worker(int(sys.argv[2]))
