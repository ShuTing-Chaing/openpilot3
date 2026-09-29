"""Bounded descriptive Params publishing off the model frame's real-time core."""
import queue
import threading
from .priority import background_thread

class RuntimeStatusPublisher:
  def __init__(self, params):
    self.params = params
    self.pending = queue.Queue(maxsize=1)
    self.stopped = threading.Event()
    self.last_offered = None
    self.worker = threading.Thread(target=self._run, name='qnn-source-status', daemon=True)
    self.worker.start()

  def offer(self, phase, active):
    value = (str(phase), bool(active))
    if self.stopped.is_set() or value == self.last_offered:
      return
    self.last_offered = value
    try:
      self.pending.put_nowait(value)
    except queue.Full:
      try:self.pending.get_nowait()
      except queue.Empty:pass
      try:self.pending.put_nowait(value)
      except queue.Full:pass

  def _run(self):
    background_thread()
    while not self.stopped.is_set():
      try:phase, active = self.pending.get(timeout=.1)
      except queue.Empty:continue
      try:
        # phase is the authoritative single-field router state. Active remains
        # a compatibility/UI hint; consumers must not treat their interleave as failure.
        self.params.put('C3XLQnnRuntimePhase', phase, block=True)
        self.params.put_bool('ChestnutActive', active, block=True)
      except Exception:
        self.last_offered = None  # Retry metadata on the next frame; never stop inference.

  def close(self):
    self.stopped.set()
