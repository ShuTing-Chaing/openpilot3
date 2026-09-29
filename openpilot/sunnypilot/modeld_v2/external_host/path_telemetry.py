"""Display-only SP path bridge. Never joins or blocks modeld on network/UI work."""
from __future__ import annotations
import math
import queue
import socket
import struct
import threading
import time

HEADER = struct.Struct('<4sBBH5Q2I3f2H')
FLOATS = struct.Struct('<150f')

def boottime_ns():
  return time.clock_gettime_ns(getattr(time, 'CLOCK_BOOTTIME', time.CLOCK_MONOTONIC))


def encode_path(record, now_ns):
  age_ms = (now_ns - record['eof_ns']) / 1e6
  if not 0 <= age_ms < 200:
    return None
  source, flags = record['source'], record['flags']
  if source not in (1, 2) or flags & ~31 or record['session_id'] <= 0 or record['state_epoch'] <= 0:
    return None
  if (source == 1 and record['request_id'] != 0) or (source == 2 and record['request_id'] <= 0):
    return None
  if not .2 <= record['height'] <= 4 or not 0 <= record['blend'] <= 1:
    return None
  points, projection, accel = record['position'], record['projections'], record['acceleration']
  if len(points) != 33 or any(len(p) != 3 for p in points) or len(projection) != 18 or len(accel) != 33:
    return None
  values = [*projection, *(v for p in points for v in p), *accel]
  if not all(math.isfinite(v) for v in values):
    return None
  remaining = int(200 - age_ms)
  if remaining < 1:
    return None
  return HEADER.pack(b'SPR1', 1, source, flags, record['publish_seq'], record['session_id'],
                     record['state_epoch'], record['request_id'], record['eof_ns'],
                     record['frame_id'], record['frame_id_extra'], age_ms, record['height'], record['blend'], remaining, 33) + FLOATS.pack(*values)


class PathPublisher:
  """A latest-only mailbox; publisher does not wait for any acknowledgement."""
  def __init__(self, host, *, port=5556):
    self.endpoint = (host, port)
    self.pending = queue.Queue(maxsize=1)
    self.stopped = threading.Event()
    self.worker = threading.Thread(target=self._run, name='sp-path-preview', daemon=True)
    self.worker.start()

  def offer(self, record):
    if self.stopped.is_set():
      return False
    try:
      self.pending.put_nowait(record)
    except queue.Full:
      try:
        self.pending.get_nowait()
      except queue.Empty:
        pass
      try:
        self.pending.put_nowait(record)
      except queue.Full:
        return False
    return True

  def _run(self):
    from .priority import background_thread
    background_thread()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
      while not self.stopped.is_set():
        try:
          record = self.pending.get(timeout=.1)
        except queue.Empty:
          continue
        try:
          packet = encode_path(record, boottime_ns())
          if packet is not None:
            sock.sendto(packet, self.endpoint)
        except (OSError, ValueError, KeyError, TypeError, OverflowError, struct.error):
          # Display failure must never affect model/control output.
          continue
    finally:
      sock.close()

  def close(self):
    self.stopped.set()
