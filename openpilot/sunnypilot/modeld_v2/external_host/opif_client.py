"""One OPIF TCP client for both Android Apps; source-ABI compatibility is not trust."""
from collections import OrderedDict
from collections import deque
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import socket
import struct
import threading
import time

from .qnn_client import CINQUE_SHA, QnnError
from .priority import background_thread
from .opif import wire
from .opif.tcp_wire import TCPClient
from .opif.transport import Frame, Pipeline
from .faults import classify, TransportUnavailable, HistoryResetRequired, FatalModelFault

ABI = f'sha256:{CINQUE_SHA};op-supercombo-18452-f32-d33-s4-v1'
COMPACT_ABI = f'sha256:{CINQUE_SHA};op-supercombo-2068-f32-d33-s4-v2'


class OpifLink:
  supports_soft_expiry = True
  def __init__(self, profile, client_role):
    if profile.get('transport') != 'qnn_wifi' or profile.get('wire_protocol') != 'opif_tcp':
      raise QnnError('OPIF requires an explicitly selected OPIF TCP profile')
    control = profile.get('control_qualified') is True and profile.get('allow_control') is True
    if client_role not in ('shadow', 'diagnostic', 'modeld') or (client_role == 'modeld' and not control) or (profile.get('allow_control') is True and not control):
      raise QnnError('OPIF control requires verified model outputs, timing and fallback')
    self.profile = dict(profile)
    if profile.get('model_sha256') != CINQUE_SHA:
      raise QnnError('OPIF source model differs from Cinque v3')
    self.frame_timeout = float(profile.get('result_timeout_seconds', .2))
    self.result_schema = profile.get('result_schema', 'full_f32')
    if self.result_schema not in ('full_f32', 'control_heads_f32'):
      raise QnnError('Unknown OPIF result schema')
    self.result_bytes = 8272 if self.result_schema == 'control_heads_f32' else 73808
    self.health = None
    if not .05 <= self.frame_timeout <= .2:
      raise QnnError('OPIF result deadline must be 50..200ms')
    host = str(ipaddress.IPv4Address(profile['host']))
    port = int(profile.get('port', 5555))
    if not 1 <= port <= 65535:
      raise QnnError('Invalid OPIF port')
    if client_role != "diagnostic" and not wire.native_codec.AVAILABLE:
      raise QnnError("Native CRC32C is required for C3; build the OPIF codec helper")
    try:
      self.client = TCPClient(host, port, timeout=float(profile.get('connect_timeout', 5.0)))
    except OSError as error:
      raise TransportUnavailable(str(error)) from error
    self.sock = self.client.socket
    self.queue_capacity = 4  # 200ms at20Hz; phone admission remains D2.
    self.pending = queue.Queue(maxsize=self.queue_capacity)
    self.completed = queue.Queue(maxsize=self.queue_capacity)
    self.sent = OrderedDict()
    self.lock = threading.Lock()
    self.stopped = threading.Event()
    self.error = None
    self.worker = None
    self.sequence = 0
    self.ready = False
    self.stage_enabled = os.getenv('OPENPILOT_PREFIX', '').startswith('qnnbench_') and os.getenv('QNN_STAGE_TRACE') == '1'
    self.live_stage_enabled = profile.get('diagnostic_stage_trace') is True and client_role == 'shadow'
    self.stage_enabled |= self.live_stage_enabled
    self.stages = {}
    self.flush_events = deque(maxlen=256)
    self.receive_events = deque(maxlen=256)
    if self.stage_enabled:
      actual_flush, actual_receive = self.client._flush, self.client._receive_until
      def traced_flush():
        before = self.client._queued_bytes
        result = actual_flush()
        self.flush_events.append({'at_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                                  'queued_before': before, 'queued_after': self.client._queued_bytes})
        return result
      def traced_receive(deadline):
        result = actual_receive(deadline)
        if result is not None:
          header, _ = result
          self.receive_events.append({'at_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                                      'kind': int(header.message_type), 'request_id': header.request_id,
                                      'fragment_index': header.fragment_index, 'fragment_count': header.fragment_count})
        return result
      self.client._flush, self.client._receive_until = traced_flush, traced_receive

  def hello(self, timeout=5):
    try:
      self.client.control_timeout = min(float(timeout), 10.)
      compact = self.result_schema == 'control_heads_f32'
      encoding = wire.OutputEncoding.CONTROL_HEADS_FLOAT32_LE if compact else wire.OutputEncoding.FLOAT32_LE
      session = self.client.start_session(wire.InputLayout.CURRENT_PACKED_6, encoding)
      if session.abi_identifier != (COMPACT_ABI if compact else ABI) or session.tensor_bytes != 393216 or session.output_elements != self.result_bytes // 4:
        raise QnnError('OPIF Cinque ABI mismatch')
      if session.maximum_in_flight != 2:
        raise QnnError('Expected OPIF D2 admission contract')
      self.pipeline = Pipeline(self.client, maximum_age=self.frame_timeout)
      self.ready = True
      self.worker = threading.Thread(target=self._run, name='opif-tcp-io', daemon=True)
      self.worker.start()
      self.health = {'ready': True, 'model_sha256': CINQUE_SHA, 'wire_protocol': 'opif_tcp',
              'backend': 'OPIF_UNVERIFIED', 'execution_mode': 'unverified',
              'transport_authenticated': False, 'runtime_identity_verified': False,
              'control_qualified': False, 'maximum_in_flight': 2, 'model_name': session.model_name,
              'opif_session_id': session.session_id, 'state_epoch': 1, 'opif_state_epoch': 1,
              'result_schema': self.result_schema}
      return self.health
    except Exception as error:
      self.close()
      raise classify(error) from error

  def submit(self, frame_id, eof, pixels, scalars, reset_temporal=False):
    if self.error is not None:
      raise self.error
    if not self.ready or self.stopped.is_set():
      raise TransportUnavailable('OPIF session is not running')
    if len(pixels) != 393216 or len(scalars) != 48 or frame_id < 0 or eof <= 0:
      raise QnnError('OPIF camera/live input contract mismatch')
    values = struct.unpack('<12f', scalars)
    if not all(math.isfinite(x) for x in values) or any(x not in (0., 1.) for x in values[:10]):
      raise QnnError('OPIF desire/traffic must be finite one-hot values')
    if sum(values[:8]) > 1 or sum(values[8:10]) != 1 or min(values[10:]) < 0:
      raise QnnError('Invalid OPIF desire/traffic/action values')
    desire = next((i for i, value in enumerate(values[:8]) if i and value == 1.), 0)
    traffic = 0 if values[8] else 1
    now = time.monotonic()
    boot = time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time, "CLOCK_BOOTTIME") else now
    age = boot - int(eof) / 1e9
    if not 0 <= age < self.frame_timeout:
      raise HistoryResetRequired("OPIF camera source age exceeded deadline before transmission")
    captured = now - age
    with self.lock:
      if len(self.sent) >= self.queue_capacity:
        raise HistoryResetRequired('OPIF in-flight queue full')
      self.sequence += 1
      seq = self.sequence
      self.sent[seq] = (int(frame_id), int(eof), captured)
      if self.stage_enabled:
        self.stages[seq] = {'t_link_submit_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME)}
    frame = Frame(bytes(pixels), captured, desire, traffic, tuple(values[10:]), int(eof), (seq, int(frame_id), int(eof)), bool(reset_temporal))
    try:
      self.pending.put_nowait(frame)
    except queue.Full as e:
      error = HistoryResetRequired('OPIF send queue full')
      self._fail(error)
      raise error from e
    return seq

  def _run(self):
    background_thread()  # Do not inherit modeld core7/SCHED_FIFO for network work.
    try:
      while not self.stopped.is_set():
        now = time.monotonic()
        with self.lock:
          oldest = next(iter(self.sent.values()), None)
        self.client.send_deadline = oldest[2] + self.frame_timeout if oldest else now + self.frame_timeout
        if self.pipeline.can_submit:
          try:
            frame = self.pending.get_nowait()
          except queue.Empty:
            pass
          else:
            if frame.context[0] != self.pipeline.next_id:
              raise QnnError('OPIF transport sequence diverged')
            stage = self.stages.get(frame.context[0]) if self.stage_enabled else None
            if stage is not None:stage['t_wire_queue_ns'] = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            self.pipeline.submit(frame)
            if stage is not None:stage['t_wire_queue_done_ns'] = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        for frame, result in self.pipeline.poll(wait=.005):
          seq, fid, eof = frame.context
          raw = result.raw_output
          finite = wire.native_codec.finite_f32(raw) if wire.native_codec.AVAILABLE else all(math.isfinite(v[0]) for v in struct.iter_unpack('<f', raw))
          if len(raw) != self.result_bytes or not finite:
            raise FatalModelFault('Invalid OPIF output tensor')
          stats = {'inference_ms': result.inference_microseconds / 1000,
              'queue_ms': result.queue_microseconds / 1000, 'wire_protocol': 'opif_tcp',
              'runtime_identity_verified': False, 'result_schema': self.result_schema,
              'opif_session_id': self.pipeline.session.session_id, 'state_epoch': 1,
              'opif_state_epoch': 1, 'request_id': seq, 'opif_request_id': seq,
              'frame_id': fid, 'eof_ns': eof, 'soft_reset': bool(frame.reset_temporal),
              'terminal': 'expired' if time.monotonic() - frame.captured >= self.frame_timeout else 'executed'}
          if self.stage_enabled:
            stats.update(self.stages.pop(seq, {}))
            stats['t_wire_result_ns'] = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
          self.completed.put_nowait((seq, fid, eof, raw, stats))
    except Exception as error:
      self._fail(error)

  def _fail(self, error):
    error = classify(error)
    if self.stage_enabled:
      try:
        if self.live_stage_enabled:
          folder = Path('/data/qnn-host/opif-failure-traces'); folder.mkdir(exist_ok=True)
          path = folder / f'worker-{os.getpid()}-{time.clock_gettime_ns(time.CLOCK_BOOTTIME)}.json'
        else:
          path = Path(os.environ['CTM_EXTERNAL_CONFIG']).parent / 'opif-stage-failure.json'
        with self.lock:
          saved_stages = {seq: dict(row) for seq, row in self.stages.items()}
        path.write_text(json.dumps({'error': str(error), 'at_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                                    'stages': saved_stages, 'flush_events': list(self.flush_events),
                                    'receive_events': list(self.receive_events),
                                    'queued_bytes': self.client._queued_bytes},allow_nan=False)+'\n')
      except (OSError, KeyError, TypeError, ValueError, RuntimeError):pass
    self.error = error
    self.stopped.set()
    try:
      self.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
      pass

  def result(self, timeout=.2):
    deadline = time.monotonic() + timeout
    while True:
      if self.error is not None:
        raise self.error
      if self.stopped.is_set():
        raise TransportUnavailable('OPIF session stopped')
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        return None
      try:
        value = self.completed.get(timeout=min(.02, remaining))
      except queue.Empty:
        continue
      with self.lock:
        if not self.sent or value[0] != next(iter(self.sent)):
          raise QnnError('OPIF completion order mismatch')
        expected = self.sent.pop(value[0])
      if expected[:2] != value[1:3]:
        raise QnnError('OPIF result identity mismatch')
      age = time.monotonic() - expected[2]
      if age >= self.frame_timeout:
        value = (*value[:4], dict(value[4], terminal='expired'))
      return value

  def close(self, *, wait=True):
    self.ready = False
    self.stopped.set()
    try:
      self.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
      pass
    self.sock.close()
    if wait and self.worker is not None and self.worker is not threading.current_thread():
      self.worker.join(timeout=.3)
