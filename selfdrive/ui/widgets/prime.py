import pyray as rl

from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import gui_label


class PrimeWidget(Widget):
  """Widget for displaying MR.ONE promotional content"""

  PRIME_BG_COLOR = rl.Color(51, 51, 51, 255)
  BRAND_COLOR = rl.Color(70, 91, 234, 255)

  def _render(self, rect):
    self._render_promotion(rect)

  def _render_promotion(self, rect: rl.Rectangle):
    """Renders the MR.ONE brand promotion."""

    rl.draw_rectangle_rounded(rect, 0.025, 10, self.PRIME_BG_COLOR)

    # Layout
    x, y = rect.x + 80, rect.y + 90
    w = rect.width - 160

    # Title
    gui_label(rl.Rectangle(x, y, w, 90), tr("MR.ONE"), 85, font_weight=FontWeight.BOLD, color=self.BRAND_COLOR)

    # Subtitle
    sub_y = y + 110
    font = gui_app.font(FontWeight.NORMAL)
    rl.draw_text_ex(font, tr("更智能的驾驶体验"), rl.Vector2(x, sub_y), 56, 0, rl.WHITE)

    # Features section
    features_y = sub_y + 80
    gui_label(rl.Rectangle(x, features_y, w, 50), tr("特色功能:"), 41, font_weight=FontWeight.BOLD)

    # Feature list
    features = [tr("专属调校"), tr("持续OTA更新"), tr("实时远程监控"), tr("精湛本地化体验")]
    for i, feature in enumerate(features):
      item_y = features_y + 80 + i * 65
      gui_label(rl.Rectangle(x, item_y, 100, 60), "✦", 50, color=self.BRAND_COLOR)
      gui_label(rl.Rectangle(x + 60, item_y, w - 60, 60), feature, 50)

    # Contact
    contact_y = features_y + 80 + len(features) * 65 + 30
    rl.draw_text_ex(font, tr("联系我们获取更多信息"), rl.Vector2(x, contact_y), 41, 0, rl.Color(200, 200, 200, 200))
