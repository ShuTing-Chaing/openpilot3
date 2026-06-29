import pyray as rl
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.system.ui.widgets.label import Label


class SetupWidget(Widget):
  def __init__(self):
    super().__init__()
    self._open_settings_callback = None
    self._open_settings_btn = Button(lambda: tr("Open"), lambda: self._open_settings_callback() if self._open_settings_callback else None,
                                     button_style=ButtonStyle.PRIMARY)
    self._firehose_label = Label(lambda: tr("🔥 Firehose Mode 🔥"), font_weight=FontWeight.MEDIUM, font_size=64)

  def set_open_settings_callback(self, callback):
    self._open_settings_callback = callback

  def _render(self, rect: rl.Rectangle):
    if not ui_state.prime_state.is_paired():
      self._render_registration(rect)
    else:
      self._render_firehose_prompt(rect)

  def _render_registration(self, rect: rl.Rectangle):
    """Render MR.ONE brand card with safety notice."""

    BG_COLOR = rl.Color(30, 35, 50, 255)     # dark navy
    ACCENT = rl.Color(70, 91, 234, 255)       # brand blue
    SEPARATOR = rl.Color(60, 65, 85, 255)     # subtle line

    # Full card background
    rl.draw_rectangle_rounded(rl.Rectangle(rect.x, rect.y, rect.width, rect.height), 0.035, 20, BG_COLOR)

    x_center = rect.x + rect.width / 2
    y_center = rect.y + rect.height / 2

    # MR.ONE title
    bold_font = gui_app.font(FontWeight.BOLD)
    title = "MR.ONE"
    title_size = 85
    title_measure = rl.measure_text_ex(bold_font, title, title_size, 0)
    rl.draw_text_ex(bold_font, title, rl.Vector2(x_center - title_measure.x / 2, y_center - 130), title_size, 0, ACCENT)

    # === Separator ===
    sep_y = y_center + 5
    sep_w = 280
    rl.draw_rectangle(int(x_center - sep_w / 2), int(sep_y), sep_w, 2, SEPARATOR)

    # === Bottom section: safety notice ===
    warn = tr("这不是自动驾驶，请注意行车安全")
    warn_size = 68
    warn_measure = rl.measure_text_ex(bold_font, warn, warn_size, 0)
    rl.draw_text_ex(bold_font, warn, rl.Vector2(x_center - warn_measure.x / 2, y_center + 35), warn_size, 0, rl.Color(201, 34, 49, 255))

    # === Footer: version & url ===
    footer_text = "V0.11.1  |  www.mr-one.cn"
    footer_size = 30
    footer_measure = rl.measure_text_ex(bold_font, footer_text, footer_size, 0)
    rl.draw_text_ex(bold_font, footer_text, rl.Vector2(x_center - footer_measure.x / 2, rect.y + rect.height - 50), footer_size, 0, rl.Color(110, 115, 135, 255))

  def _render_firehose_prompt(self, rect: rl.Rectangle):
    """Render firehose prompt widget."""

    rl.draw_rectangle_rounded(rl.Rectangle(rect.x, rect.y, rect.width, 500), 0.04, 20, rl.Color(51, 51, 51, 255))

    # Content margins (56, 40, 56, 40)
    x = rect.x + 56
    y = rect.y + 40
    w = rect.width - 112
    spacing = 42

    # Title with fire emojis
    self._firehose_label.render(rl.Rectangle(rect.x, y, rect.width, 64))
    y += 64 + spacing

    # Description
    desc_font = gui_app.font(FontWeight.NORMAL)
    desc_text = tr("Maximize your training data uploads to improve openpilot's driving models.")
    wrapped_desc = wrap_text(desc_font, desc_text, 40, int(w))

    for line in wrapped_desc:
      rl.draw_text_ex(desc_font, line, rl.Vector2(x, y), 40, 0, rl.WHITE)
      y += 40 * FONT_SCALE

    y += spacing

    # Open button
    button_height = 48 + 64  # font size + padding
    button_rect = rl.Rectangle(x, y, w, button_height)
    self._open_settings_btn.render(button_rect)
