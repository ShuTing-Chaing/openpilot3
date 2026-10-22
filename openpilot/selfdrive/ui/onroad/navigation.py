import numpy as np
import pyray as rl

from msgq.visionipc import VisionIpcClient
from openpilot.cereal.visionipc import VisionStreamType
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, TextAlignmentVertical
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import UnifiedLabel, gui_label

PANEL_WIDTH = 261
CONNECTION_RETRY_INTERVAL = 1.0
STALE_SECONDS = 3
PHONE_MAP_STREAM_NAME = 'phone_navi'
FALLBACK_MAP_WIDTH = 384
FALLBACK_MAP_HEIGHT = 512


def format_distance(meters: float) -> str:
  """m / ft under 1000 m / 300 m, km / mi beyond."""
  if ui_state.is_metric:
    return f'{round(meters / 10) * 10} m' if meters < 1000 else f'{meters / 1000:.1f} km'
  return f'{round(meters * CV.METER_TO_FOOT / 50) * 50} ft' if meters < 300 else f'{meters * CV.METER_TO_MILE:.1f} mi'


class NavigationPanel(Widget):
  """Turn instructions around RGB map frames supplied by the phone navigation app."""

  def __init__(self):
    super().__init__()
    self._client = VisionIpcClient(PHONE_MAP_STREAM_NAME, VisionStreamType.VISION_STREAM_MAP, True)
    self._last_connect = 0.0
    self._frame_time = 0.0
    self._texture = None
    self._map_width = FALLBACK_MAP_WIDTH
    self._map_height = FALLBACK_MAP_HEIGHT
    self._eta_label = UnifiedLabel('', 34, FontWeight.BOLD, rl.WHITE, scroll=True)
    self._accent = rl.Color(155, 230, 185, 255)
    self._muted = rl.Color(162, 175, 185, 255)

  def _update_state(self):
    if not self._client.is_connected():
      if rl.get_time() - self._last_connect < CONNECTION_RETRY_INTERVAL:
        return
      self._last_connect = rl.get_time()
      if not self._client.connect(False) or not self._client.num_buffers:
        return
      self._unload_texture()
      self._map_width = int(self._client.width or FALLBACK_MAP_WIDTH)
      self._map_height = int(self._client.height or FALLBACK_MAP_HEIGHT)
      self._texture = rl.load_texture_from_image(
        rl.Image(None, self._map_width, self._map_height, 1, rl.PixelFormat.PIXELFORMAT_UNCOMPRESSED_R8G8B8)
      )
    frame = self._client.recv(timeout_ms=0)
    if frame is not None and self._texture is not None:
      count = self._map_width * self._map_height * 3
      if len(frame.data) >= count:
        rgb = np.frombuffer(frame.data, dtype=np.uint8, count=count).reshape((self._map_height, self._map_width, 3))
        rl.update_texture(self._texture, rl.ffi.cast("void *", rl.ffi.from_buffer(rgb)))
        self._frame_time = rl.get_time() if self._client.timestamp_sof else 0.0

  @property
  def routing(self):
    return ui_state.sm.valid['navInstruction'] and ui_state.sm.alive['navInstruction']

  @property
  def map_ready(self):
    return self._texture is not None and 0 <= rl.get_time() - self._frame_time < STALE_SECONDS

  def _draw_status(self, rect):
    """What the phone map is waiting on, in place of the map."""
    statuses = (
      ('Phone stream', self._client.is_connected()),
      ('Route', self.routing),
      ('Map frames', self.map_ready),
    )
    for i, (name, ok) in enumerate(statuses):
      gui_label(rl.Rectangle(rect.x + 10, rect.y + 12 + i * 28, rect.width - 20, 26), f'{name}: {"yes" if ok else "no"}', 22,
                self._accent if ok else self._muted, FontWeight.MEDIUM, alignment_vertical=TextAlignmentVertical.TOP)

  def _render(self, rect):
    x, y = rect.x, rect.y
    rl.draw_rectangle_rec(rect, rl.Color(7, 13, 18, 255))
    instruction = ui_state.sm['navInstruction']
    if self.routing:
      direction = instruction.maneuverModifier
      flip = -1 if 'left' in direction else 1
      # The maneuver arrow on a 1.4x grid, centered in the header's icon box, with round joins for the thick stroke.
      if direction in ('straight', ''):
        shape = [(0, 14), (0, -12), (-6, -5), (0, -12), (6, -5)]
      else:
        shape = [(-flip*9, 14), (-flip*9, -4), (-flip*2, -9), (flip*9, -9), (flip*3, -15), (flip*9, -9), (flip*3, -3)]
      points = [rl.Vector2(x + 31 + 1.4*px, y + 30 + 1.4*py) for px, py in shape]
      for a, b in zip(points[:-1], points[1:], strict=True):
        rl.draw_line_ex(a, b, 7, self._accent)
      for point in points:
        rl.draw_circle_v(point, 3.5, self._accent)
      gui_label(rl.Rectangle(x+64, y+11, rect.width-72, 40), format_distance(max(0, instruction.maneuverDistance)), 34, rl.WHITE, FontWeight.BOLD,
                alignment_vertical=TextAlignmentVertical.TOP)
    else:
      gui_label(rl.Rectangle(x+12, y+18, rect.width-24, 30), 'Waiting for route', 26, rl.WHITE, FontWeight.BOLD,
                alignment_vertical=TextAlignmentVertical.TOP)
    map_rect = rl.Rectangle(x+8, y+61, rect.width-16, rect.height-111)
    rl.draw_rectangle_rec(map_rect, rl.BLACK)
    if self.map_ready:
      scale = min(map_rect.width / self._map_width, map_rect.height / self._map_height)
      width = self._map_width * scale
      height = self._map_height * scale
      source = rl.Rectangle(0, 0, self._map_width, self._map_height)
      target = rl.Rectangle(map_rect.x + (map_rect.width - width) / 2, map_rect.y + (map_rect.height - height) / 2, width, height)
      rl.draw_texture_pro(self._texture, source, target, rl.Vector2(0, 0), 0, rl.WHITE)
    else:
      self._draw_status(map_rect)
    if self.routing:
      seconds = max(0, instruction.timeRemaining)
      remaining = max(0, instruction.distanceRemaining)
      self._eta_label.set_text(f'{max(1, round(seconds / 60))} min / {format_distance(remaining)}')
      self._eta_label.render(rl.Rectangle(x+9, y+rect.height-45, rect.width-18, 40))

  def _unload_texture(self):
    if self._texture:
      rl.unload_texture(self._texture)
      self._texture = None

  def close(self):
    self._unload_texture()