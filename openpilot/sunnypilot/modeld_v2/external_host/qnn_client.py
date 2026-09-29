"""Pinned TLS / persistent TCP+NODELAY client for Android QNN protocol v2."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import queue
import socket
import ssl
import struct
import threading
import time
import uuid
import hmac

from .wire import HostError

CINQUE_SHA = '404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4'
MAGIC = b'NQW2'
MAX_HEADER = 16384
MAX_PAYLOAD = 1024 * 1024


class QnnError(HostError):
  pass


def _hex_digest(value):
  if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
    raise QnnError('Expected a lowercase SHA256 fingerprint')
  return value


def open_pinned(host, port, fingerprint, timeout=3.0):
  """No trust-on-first-use: fingerprint must be confirmed from the phone UI."""
  fingerprint = _hex_digest(fingerprint)
  ipaddress.ip_address(host)
  if not 1 <= int(port) <= 65535:
    raise QnnError('Invalid QNN port')
  raw = socket.create_connection((host, int(port)), timeout=timeout)
  try:
    raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # Trust is the out-of-band SHA256 pin below.
    secure = context.wrap_socket(raw, server_hostname=None)
    actual = hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest()
    if not hmac.compare_digest(actual, fingerprint):
      secure.close()
      raise QnnError('Phone certificate fingerprint mismatch')
    secure.settimeout(0.05)
    return secure
  except BaseException:
    raw.close()
    raise


def _read_exact(sock, count, deadline):
  result = bytearray()
  while len(result) < count:
    if time.monotonic() >= deadline:
      raise QnnError('QNN receive deadline exceeded')
    try:
      value = sock.recv(count - len(result))
    except (TimeoutError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
      continue
    if not value:
      raise QnnError('QNN connection closed during packet')
    result.extend(value)
  return bytes(result)


def recv_packet(sock, timeout):
  deadline = time.monotonic() + timeout
  header = _read_exact(sock, 12, deadline)
  if header[:4] != MAGIC:
    raise QnnError('QNN protocol magic mismatch')
  n, size = struct.unpack('>II', header[4:])
  if not 1 <= n <= MAX_HEADER or size > MAX_PAYLOAD:
    raise QnnError('QNN packet size out of bounds')
  try:
    info = json.loads(_read_exact(sock, n, deadline))
  except (UnicodeDecodeError, ValueError) as e:
    raise QnnError('Invalid QNN header JSON') from e
  if not isinstance(info, dict):
    raise QnnError('QNN header must be an object')
  payload = _read_exact(sock, size, deadline)
  return info, payload


def send_packet(sock, header, payload=b'', timeout=0.2):
  encoded = json.dumps(header, separators=(',', ':'), allow_nan=False).encode()
  if not 1 <= len(encoded) <= MAX_HEADER or len(payload) > MAX_PAYLOAD:
    raise QnnError('QNN packet size out of bounds')
  data = memoryview(MAGIC + struct.pack('>II', len(encoded), len(payload)) + encoded + payload)
  deadline = time.monotonic() + timeout
  while data:
    if time.monotonic() >= deadline:
      raise QnnError('QNN send deadline exceeded')
    try:
      count = sock.send(data)
    except (TimeoutError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
      continue
    if count <= 0:
      raise QnnError('QNN connection closed while sending')
    data = data[count:]


def _expect(sock, expected, timeout):
  reply, payload = recv_packet(sock, timeout)
  if reply.get('type') == 'ERROR':
    raise QnnError(str(reply.get('error', 'QNN error')))
  if reply.get('type') != expected:
    raise QnnError('Unexpected QNN reply type')
  return reply, payload


def pair(host, port, fingerprint, code, label):
  with open_pinned(host, port, fingerprint) as sock:
    send_packet(sock, {'type': 'PAIR', 'protocol': 2, 'code': str(code), 'label': str(label)[:64]}, timeout=3)
    reply, payload = _expect(sock, 'PAIRED', 3)
    if payload or not isinstance(reply.get('client_id'), str) or str(uuid.UUID(reply['client_id'])) != reply['client_id'] or len(reply.get('token', '')) != 64:
      raise QnnError('Invalid pairing response')
    return {key: reply[key] for key in ('client_id', 'token', 'device_id')}


EXECUTION_MODES = {
  'npu_only': ('QNN_HTP', False),
  'npu_cpu': ('QNN_HTP_CPU', True),
  'gpu_cpu': ('QNN_GPU_CPU', True),
  'cpu': ('ORT_CPU', False),
}


def validate_execution_mode(health, profile):
  mode = profile.get('execution_mode', 'npu_only')
  if mode not in EXECUTION_MODES:
    raise QnnError('Unknown configured execution mode')
  backend, cpu_fallback = EXECUTION_MODES[mode]
  # Legacy strict-only servers are compatible only with the strict baseline.
  actual_mode = health.get('execution_mode', 'npu_only')
  if (actual_mode != mode or health.get('backend') != backend or
      health.get('cpu_fallback') is not cpu_fallback or health.get('gpu_fallback') is not False):
    raise QnnError('Phone execution policy differs from the explicitly configured mode')
  return mode


class QnnLink:
  """Single TLS I/O owner; bounded requests are compatible with AsyncSession."""

  def __init__(self, profile, client_role):
    if client_role not in ('modeld', 'shadow', 'diagnostic'):
      raise QnnError('Invalid QNN role')
    if profile.get('transport') != 'qnn_wifi':
      raise QnnError('QNN profile must use qnn_wifi')
    self.execution_mode = profile.get('execution_mode', 'npu_only')
    if self.execution_mode not in EXECUTION_MODES:
      raise QnnError('Unknown configured execution mode')
    self.model_sha256 = _hex_digest(profile.get('model_sha256'))
    self.runtime_model_sha256 = profile.get('runtime_model_sha256')
    if self.runtime_model_sha256 is not None:
      _hex_digest(self.runtime_model_sha256)
    self.device_id = profile.get('device_id')
    self.runtime_artifact_sha256 = profile.get('runtime_artifact_sha256')
    if self.runtime_artifact_sha256 is not None:
      _hex_digest(self.runtime_artifact_sha256)
    self.role = client_role
    self.credentials = json.loads(Path(profile['pairing_file']).read_text())
    if not isinstance(self.credentials.get('client_id'), str) or len(self.credentials.get('token', '')) != 64:
      raise QnnError('Invalid QNN pairing credentials')
    self.sock = open_pinned(profile['host'], profile.get('port', 5600), profile['fingerprint_sha256'])
    self.sent = OrderedDict()
    self.pending = queue.Queue(maxsize=3)
    self.completed = queue.Queue(maxsize=3)
    self.lock = threading.Lock()
    self.stopped = threading.Event()
    self.error = None
    self.sequence = 0
    self.session_id = None
    self.worker = None
    self.frame_timeout = float(profile.get('result_timeout_seconds', 0.2))
    if not 0.05 <= self.frame_timeout <= 0.2:
      self.sock.close()
      raise QnnError('QNN result deadline must be between 50 and 200ms')

  def hello(self, timeout=5):
    try:
      send_packet(
        self.sock,
        {
          'type': 'HELLO',
          'protocol': 2,
          'client_id': self.credentials['client_id'],
          'token': self.credentials['token'],
          'model_sha256': self.model_sha256,
          'role': self.role,
        },
        timeout=timeout,
      )
      ready, _ = _expect(self.sock, 'READY', timeout)
      validate_execution_mode(ready, {'execution_mode': self.execution_mode})
      if ready.get('model_sha256') != self.model_sha256 or ready.get('ready') is not True:
        raise QnnError('QNN model identity/readiness mismatch')
      if self.runtime_model_sha256 and ready.get('runtime_model_sha256') != self.runtime_model_sha256:
        raise QnnError('QNN runtime artifact identity mismatch')
      if self.device_id and ready.get('device_id') != self.device_id:
        raise QnnError('QNN phone identity mismatch')
      if self.runtime_artifact_sha256 and ready.get('runtime_artifact_sha256') != self.runtime_artifact_sha256:
        raise QnnError('QNN runtime bundle identity mismatch')
      self.negotiated = {key: ready.get(key) for key in ('model_sha256', 'runtime_model_sha256', 'runtime_artifact_sha256',
                                                                      'execution_mode', 'backend', 'cpu_fallback', 'gpu_fallback')}
      send_packet(self.sock, {'type': 'START'}, timeout=timeout)
      started, _ = _expect(self.sock, 'STARTED', timeout)
      if any(started.get(key) != value for key, value in self.negotiated.items()):
        raise QnnError('QNN START identity differs from HELLO')
      self.session_id = started.get('session_id')
      if not isinstance(self.session_id, str) or not self.session_id:
        raise QnnError('Missing QNN session identity')
      self.worker = threading.Thread(target=self._run, name='qnn-tls-io', daemon=True)
      self.worker.start()
      return ready
    except BaseException:
      self.close()
      raise

  def submit(self, frame_id, eof, pixels, scalars):
    if self.stopped.is_set() or self.session_id is None:
      raise QnnError('QNN session is not running')
    if len(pixels) != 393216 or len(scalars) != 48 or not all(math.isfinite(x) for x in struct.unpack('<12f', scalars)):
      raise QnnError('QNN frame payload contract mismatch')
    if int(frame_id) < 0 or int(eof) <= 0:
      raise QnnError('Invalid QNN camera identity')
    with self.lock:
      if len(self.sent) >= 3:
        raise QnnError('QNN in-flight queue full')
      self.sequence += 1
      seq = self.sequence
      self.sent[seq] = (int(frame_id), int(eof), time.monotonic())
    header = {'type': 'FRAME', 'session_id': self.session_id, 'seq': seq, 'frame_id': int(frame_id), 'eof_ns': int(eof)}
    try:
      self.pending.put_nowait((header, bytes(scalars) + bytes(pixels)))
    except queue.Full as e:
      self._fail(QnnError('QNN send queue full'))
      raise QnnError('QNN send queue full') from e
    return seq

  def _run(self):
    try:
      while not self.stopped.is_set():
        try:
          header, payload = self.pending.get(timeout=0.05)
        except queue.Empty:
          continue
        seq = header['seq']
        send_packet(self.sock, header, payload, timeout=self.frame_timeout)
        reply, raw = _expect(self.sock, 'RESULT', max(1.0, self.frame_timeout) if seq <= 10 else self.frame_timeout)
        if any(reply.get(k) != header[k] for k in ('session_id', 'seq', 'frame_id', 'eof_ns')):
          raise QnnError('QNN result identity mismatch')
        if any(reply.get(key) != value for key, value in self.negotiated.items()):
          raise QnnError('QNN result model identity mismatch')
        if len(raw) != 73808 or not all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', raw)):
          raise QnnError('QNN result tensor invalid')
        self.completed.put_nowait((seq, header['frame_id'], header['eof_ns'], raw, reply.get('stats', {})))
    except Exception as error:
      self._fail(error)

  def _fail(self, error):
    self.error = error
    self.stopped.set()
    try:
      self.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
      pass

  def result(self, timeout=0.2):
    deadline = time.monotonic() + timeout
    while True:
      if self.error is not None:
        raise QnnError(str(self.error)) from self.error
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        raise QnnError('QNN result deadline exceeded')
      try:
        value = self.completed.get(timeout=min(0.05, remaining))
      except queue.Empty:
        continue
      with self.lock:
        if not self.sent or value[0] != next(iter(self.sent)):
          raise QnnError('QNN completion sequence mismatch')
        del self.sent[value[0]]
      return value

  def close(self, *, wait=True):
    self.stopped.set()
    try:
      self.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
      pass
    self.sock.close()
    if wait and self.worker is not None and self.worker is not threading.current_thread():
      self.worker.join(timeout=0.3)


def connect_qnn(profile, client_role='modeld'):
  if profile.get('wire_protocol', 'nqw2_tls') == 'opif_tcp':
    if Path('/AGNOS').exists() or profile.get('io_process') is True:
      from .opif_process import ProcessOpifLink
      return ProcessOpifLink(profile, client_role)
    from .opif_client import OpifLink
    return OpifLink(profile, client_role)
  if profile.get('wire_protocol', 'nqw2_tls') != 'nqw2_tls':
    raise QnnError('Unknown explicitly selected phone wire protocol')
  return QnnLink(profile, client_role)
