"""Read-only, cached onroad QNN source display; never grants model control."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import queue
import threading
import time

STATUS_PATH = Path('/dev/shm/qnn-host-status.json')
ICON = 'icons/network.png'
POLICY_LABELS = {'npu_only': 'NPU', 'npu_cpu': 'NPU+CPU', 'gpu_cpu': 'GPU+CPU', 'cpu': 'PHONE CPU'}
LOCAL_PHASES = {'shadow': 'SHADOW', 'qualifying': 'WARM', 'handover_wait': 'SYNC WAIT', 'local_bridge': 'BRIDGE', 'recovering': 'RECOVER', 'reconnecting': 'RECONNECT', 'latched_local': 'FALLBACK'}


def _boottime():
  return time.clock_gettime(getattr(time, 'CLOCK_BOOTTIME', time.CLOCK_MONOTONIC))


def read_runtime_status(path):
  """Worker-only bounded read. No profile, Params, pairing or network access."""
  try:
    if not path.is_file():
      return None
    with path.open() as stream:
      text = stream.read(65537)
    if len(text) > 65536:
      return None
    result = json.loads(text)
    return result if isinstance(result, dict) else None
  except (OSError, ValueError):
    return None


@dataclass(frozen=True)
class BadgeState:
  visible: bool = False
  active: bool = False
  title: str = 'QNN ?'
  detail: str = 'STATUS LOST'
  tone: str = 'muted'


def describe_runtime(raw, now, *, seen=False):
  unknown = BadgeState(visible=seen)
  if not isinstance(raw, dict) or raw.get('schema') != 'qnn-host-status-v1':
    return unknown
  stamp = raw.get('updated_boottime')
  if type(stamp) not in (int, float) or not math.isfinite(stamp) or not math.isfinite(now) or now < stamp:
    return unknown
  if now - stamp >= 3:
    return BadgeState(visible=seen, detail='STATUS OLD')
  source, phase = raw.get('source'), raw.get('phase')
  local_runs = raw.get('local_runs')
  if source == 'qnn' and phase == 'remote_active':
    label = POLICY_LABELS.get(raw.get('execution_mode', 'npu_only'))
    if label is None:
      return unknown
    if type(local_runs) is not int or not 0 < local_runs < 10**12:
      return BadgeState(visible=seen, detail='HOT UNKNOWN')
    # Policy label describes configured execution, not actual per-provider utilization.
    return BadgeState(True, True, label, 'LOCAL HOT', 'active')
  if source != 'local' or phase not in LOCAL_PHASES:
    return unknown
  detail = LOCAL_PHASES[phase]
  if phase == 'qualifying':
    good, needed = raw.get('good_frames'), raw.get('qualification_frames')
    if type(good) is int and type(needed) is int and 0 <= good <= needed <= 10000:
      detail = f'WARM {good}/{needed}'
  return BadgeState(True, False, 'LOCAL', detail, 'warning' if phase == 'latched_local' else 'muted')


class RuntimeBadgeCache:
  """At most one background read per second; per-frame state is memory-only."""
  def __init__(self, *, path=STATUS_PATH, clock=_boottime, reader=read_runtime_status):
    self.path, self.clock, self.reader = path, clock, reader
    self._raw = None
    self._seen = False
    self._worker = None
    self._next_read = -float('inf')
    self._results = queue.Queue(maxsize=1)

  @property
  def pending(self):
    return self._worker is not None and self._worker.is_alive()

  def _consume(self):
    try:
      self._raw = self._results.get_nowait()
      if isinstance(self._raw, dict) and self._raw.get('schema') == 'qnn-host-status-v1':
        self._seen = True
    except queue.Empty:
      pass

  def update(self):
    self._consume()
    now = self.clock()
    if self.pending or now < self._next_read:
      return
    self._next_read = now + 1.

    def read():
      try:
        raw = self.reader(self.path)
      except Exception:
        raw = None
      try:
        self._results.put_nowait(raw)
      except queue.Full:
        pass

    self._worker = threading.Thread(target=read, name='qnn-hud-status', daemon=True)
    self._worker.start()

  def state(self):
    self._consume()
    return describe_runtime(self._raw, self.clock(), seen=self._seen)


class QnnRuntimeBadge:
  """Shared renderer for Mici and the standard SP HUD extension points."""
  def __init__(self, *, compact=False):
    import pyray as rl
    from openpilot.system.ui.lib.application import FontWeight, gui_app

    self.rl = rl
    self.compact = compact
    self.cache = RuntimeBadgeCache()
    self.icon_size = 38 if compact else 56
    self.icon = gui_app.texture(ICON, self.icon_size, self.icon_size)
    self.font = gui_app.font(FontWeight.BOLD)
    self.detail_font = gui_app.font(FontWeight.MEDIUM)

  def update(self):
    self.cache.update()

  def claims_source(self):
    state = self.cache.state()
    return state.visible and (state.active or state.title == 'LOCAL')

  def render(self, rect):
    state = self.cache.state()
    if not state.visible:
      return
    rl = self.rl
    width, height, margin, offset = (202, 62, 14, 14) if self.compact else (280, 84, 30, 246)
    if rect.width < width + 2 * margin or rect.height < offset + height:
      return
    box = rl.Rectangle(rect.x + rect.width - width - margin, rect.y + offset, width, height)
    colors = {'active': rl.Color(105, 238, 155, 255), 'warning': rl.Color(255, 188, 87, 255), 'muted': rl.Color(172, 179, 188, 230)}
    color = colors[state.tone]
    rl.draw_rectangle_rounded(box, .24, 8, rl.Color(15, 18, 24, 210))
    rl.draw_rectangle_rounded_lines_ex(box, .24, 8, 2, color)
    alpha = 255 if state.active else 80
    rl.draw_texture_ex(self.icon, rl.Vector2(box.x + 9, box.y + (height-self.icon_size)/2), 0., 1., rl.Color(255, 255, 255, alpha))
    x = box.x + self.icon_size + 18
    rl.draw_text_ex(self.font, state.title, rl.Vector2(x, box.y + 6), 23 if self.compact else 31, 0, color)
    rl.draw_text_ex(self.detail_font, state.detail, rl.Vector2(x, box.y + (35 if self.compact else 48)), 16 if self.compact else 21, 0, color)
