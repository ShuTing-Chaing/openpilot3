"""Bounded, single-owner UDP state machine for live modeld and offline replay."""
from dataclasses import dataclass
from collections import OrderedDict
import struct
import time

from . import wire
from ..faults import HistoryResetRequired, TransportUnavailable

MAX_FRAME_AGE = .200
REPAIR_INTERVAL = .050


@dataclass(frozen=True)
class Frame:
  tensor: bytes
  captured: float                 # source EOF converted to local monotonic clock
  desire: int = 0
  traffic: int = 0
  action_t: tuple[float, float] = (0., 0.)
  timestamp_ns: int = 0
  context: object = None
  reset_temporal: bool = False


@dataclass
class Pending:
  frame: Frame
  request: wire.EncodedMessage
  fully_sent: bool
  repair_at: float
  accepted: bool = False
  assembly: wire.MessageAssembly | None = None
  result: wire.InferenceResult | None = None


class Pipeline:
  def __init__(self, client, maximum_age=MAX_FRAME_AGE, completion_timeout=1.0):
    self.client = client
    self.session = client._require_session()
    self.maximum_age = maximum_age
    if not maximum_age <= completion_timeout <= 2.0:
      raise ValueError('OPIF completion watchdog must be bounded at 2 seconds')
    self.completion_timeout = completion_timeout
    self.tombstones = OrderedDict()
    self.pending = {}
    self.controls = {}
    self.next_id = self.next_publish = 1
    self.keepalive_at = time.monotonic() + 1
    self.repairs = 0

  @property
  def depth(self):
    return min(2, self.client.current_in_flight_limit)

  @property
  def submitted_count(self):
    return sum(item.fully_sent and item.result is None for item in self.pending.values())

  @property
  def can_submit(self):
    # TCP is already ordered/reliable: a partial third frame only adds byte
    # queueing beyond D2. Preserve partial-message prefetch for datagram links.
    return (self.depth > 0
            and len(self.pending) < self.depth + (0 if getattr(self.client, 'reliable_ordered', False) else 1)
            and all(item.fully_sent if getattr(self.client, 'reliable_ordered', False) else item.accepted
                    for item in self.pending.values()))

  def submit(self, frame):
    if not self.can_submit:
      raise RuntimeError("OPIF admission window is full")
    if time.monotonic() - frame.captured > self.maximum_age:
      raise HistoryResetRequired("input exceeded OPIF source-age budget before transmission")
    if len(frame.tensor) != self.session.tensor_bytes:
      raise ValueError("incorrect current6 tensor size")
    prefix = wire.INFERENCE_PREFIX_STRUCT.pack(
      int(self.session.layout), 0, frame.desire, frame.traffic, int(self.next_id == 1 or frame.reset_temporal),
      *frame.action_t, frame.timestamp_ns, len(frame.tensor), len(frame.tensor))
    request = wire.encode_message(wire.MessageType.INFERENCE_REQUEST, self.session.session_id,
                                  self.next_id, prefix + frame.tensor, self.session.maximum_datagram_bytes)
    full = self.submitted_count < self.depth
    # An incomplete next message consumes a reassembly slot, not an inference
    # credit. Withhold its final fragment until a previous result releases one.
    if hasattr(self.client, 'set_frame_deadline'):
      self.client.set_frame_deadline(self.next_id, frame.captured + self.maximum_age)
    self.client._send_encoded(request, None if full else range(request.fragment_count - 1))
    self.pending[self.next_id] = Pending(frame, request, full, time.monotonic() + REPAIR_INTERVAL)
    self.next_id += 1

  def poll(self, wait=.001):
    now = time.monotonic()
    for rid, item in self.pending.items():
      if now - item.frame.captured > self.completion_timeout and item.result is None:
        raise TransportUnavailable(f"OPIF request {rid} has no terminal response within completion watchdog")
      if not item.fully_sent and self.submitted_count < self.depth:
        self.client._send_encoded(item.request, [item.request.fragment_count-1])
        item.fully_sent = True
        item.repair_at = time.monotonic() + REPAIR_INTERVAL
      if item.fully_sent and item.result is None and now >= item.repair_at:
        if not item.accepted:
          self.client._send_retransmit_query(self.session, item.request)
        elif item.assembly is None:
          self.client._send_result_query(self.session, rid)
        else:
          self.client._send_result_nack(self.session, rid, item.assembly)
        self.repairs += 1
        item.repair_at = now + REPAIR_INTERVAL
    if now >= self.keepalive_at:
      self.client._send_keepalive(self.session)
      self.keepalive_at = now + 1

    deadline = time.monotonic() + wait
    for _ in range(256):
      item = self.pending.get(self.next_publish)
      if item is not None and item.result is not None and hasattr(self.client, '_receive_ready'):
        # Preserve the message budget and process already-ready errors/ACKs,
        # without waiting for future traffic after an ordered result is ready.
        message = self.client._receive_ready()
      else:
        message = self.client._receive_until(deadline)
      if message is None:
        break
      self._receive(*message)
    ready = []
    while (item := self.pending.get(self.next_publish)) is not None and item.result is not None:
      # The owner validates even an expired output and records its executed
      # terminal. It is never permitted to use that output for publication.
      ready.append((item.frame, item.result))
      self.tombstones[self.next_publish] = item.assembly.message_crc32c
      if len(self.tombstones) > 256:
        self.tombstones.popitem(last=False)
      del self.pending[self.next_publish]
      if hasattr(self.client, 'release_frame_deadline'):
        self.client.release_frame_deadline(self.next_publish)
      self.next_publish += 1
    return ready

  def _receive(self, header, payload):
    if header.session_id != self.session.session_id:
      return
    kind, rid = header.message_type, header.request_id
    if kind == wire.MessageType.PIPELINE_STATUS:
      self.client._consume_pipeline_status(header, payload, self.controls, self.session)
      return
    if kind == wire.MessageType.PONG:
      self.client._complete_control(self.controls, header, payload)
      return
    item = self.pending.get(rid)
    if item is None or item.result is not None:
      result_crc = self.tombstones.get(rid) if item is None else item.assembly.message_crc32c
      if kind == wire.MessageType.INFERENCE_RESULT and result_crc is not None and header.message_crc32c != result_crc:
        raise wire.ProtocolError('OPIF duplicate terminal has different contents')
      if rid >= self.next_id and kind in (wire.MessageType.INFERENCE_RESULT, wire.MessageType.MESSAGE_ACCEPTED, wire.MessageType.ERROR):
        raise wire.ProtocolError('OPIF response references a request that was never submitted')
      return
    if kind == wire.MessageType.INFERENCE_RESULT:
      item.accepted = True
      if item.assembly is None:
        item.assembly = wire.MessageAssembly.from_header(header)
      try:
        changed = item.assembly.add(header, payload)
        body = item.assembly.complete_body()
      except wire.MessageCRCError:
        item.assembly.reset_all()
        self.client._send_result_nack(self.session, rid, item.assembly)
        self.repairs += 1
        item.repair_at = time.monotonic() + REPAIR_INTERVAL
        return
      if changed:
        item.repair_at = time.monotonic() + REPAIR_INTERVAL
      if body is not None:
        item.result = wire._parse_inference_result(body, self.session)
        self.client._send_result_accepted(self.session, rid)
      return
    body = self.client._complete_control(self.controls, header, payload)
    if body is None:
      return
    if kind == wire.MessageType.ERROR:
      code, expected, detail = wire._parse_error(body)
      # A partial next request can complete just as the server shrinks its
      # window. Code 9 has NOT consumed the ID; retry identical bytes later.
      if code == 9 and expected == rid and not item.accepted:
        item.repair_at = time.monotonic() + REPAIR_INTERVAL
        return
      if code == 8:
        raise HistoryResetRequired(f'OPIF request sequence gap: expected={expected}, request={rid}')
      if code == 12:
        raise TransportUnavailable(f'OPIF terminal no longer available for request {rid}')
      raise wire.ProtocolError(f"OPIF request {rid}: code={code} expected={expected}: {detail}")
    if kind == wire.MessageType.MESSAGE_ACCEPTED:
      if body != bytes([wire.MessageType.INFERENCE_REQUEST]):
        raise wire.ProtocolError("invalid OPIF acceptance target")
      item.accepted = True
      # An accepted request may legitimately take >50 ms. Allow 150 ms before
      # asking for a completely absent result, but promptly repair partial ones.
      if item.assembly is None:
        item.repair_at = time.monotonic() + .150
    elif kind == wire.MessageType.MISSING_FRAGMENTS:
      if len(body) < 4:
        raise wire.ProtocolError("short missing-fragment bitmap")
      target, reserved, count = struct.unpack_from("<BBH", body)
      if (target != wire.MessageType.INFERENCE_REQUEST or reserved or
          count != item.request.fragment_count or len(body) != 4 + (count+7)//8):
        raise wire.ProtocolError("invalid missing-fragment metadata")
      if item.fully_sent:
        self.client._send_encoded(item.request, wire._indices_from_bitmap(body[4:], count))
        self.repairs += 1
        item.repair_at = time.monotonic() + REPAIR_INTERVAL
