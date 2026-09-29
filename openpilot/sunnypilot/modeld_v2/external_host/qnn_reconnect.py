"""Rate-limited network recovery; ownership returns to the camera frame thread."""
import threading

from .faults import TransportUnavailable, HistoryResetRequired
from .priority import background_thread


class RecoveryWorker:
  def __init__(self, connect):
    self.connect = connect
    self.stop = threading.Event()
    self.lock = threading.Lock()
    self.ready = self.error = None
    self.attempts = 0
    self.thread = threading.Thread(target=self._run, name='qnn-reconnect', daemon=True)
    self.thread.start()

  @staticmethod
  def release(value):
    session, _health = value
    try:
      session.close(wait=False)
    finally:
      session.link.close(wait=False)

  def _run(self):
    background_thread()
    attempt = 0
    while not self.stop.is_set():
      self.attempts = attempt + 1
      if self.stop.wait(0 if attempt == 0 else 1 if attempt == 1 else 2):
        return
      try:
        value = self.connect()
      except (TransportUnavailable, HistoryResetRequired):
        attempt += 1
        continue
      except Exception as error:
        # Identity/schema errors are never retried or reclassified by text.
        with self.lock:
          self.error = error
        return
      with self.lock:
        if not self.stop.is_set():
          self.ready = value
          return
      self.release(value)
      return

  def take(self):
    with self.lock:
      value, self.ready = self.ready, None
      return value, self.error

  def close(self):
    self.stop.set()
    with self.lock:
      value, self.ready = self.ready, None
    if value is not None:
      self.release(value)
