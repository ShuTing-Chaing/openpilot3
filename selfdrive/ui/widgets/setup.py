import pyray as rl
from openpilot.common.time_helpers import system_time_valid
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.widgets.pairing_dialog import PairingDialog
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.confirm_dialog import alert_dialog
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.system.ui.widgets.label import Label


class SetupWidget(Widget):
  def __init__(self):
    super().__init__()
    self._open_settings_callback = None
    self._pair_kitty_texture = gui_app.texture("../../dragonpilot/selfdrive/assets/hellokitty.png", 400, 400)
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
    """Render Hello Kitty image as pairing prompt."""

    rl.draw_rectangle_rounded(rl.Rectangle(rect.x, rect.y, rect.width, rect.height), 0.03, 20, rl.Color(51, 51, 51, 255))

    # Center the Hello Kitty texture in the card
    img_w = self._pair_kitty_texture.width
    img_h = self._pair_kitty_texture.height
    img_x = rect.x + (rect.width - img_w) / 2
    img_y = rect.y + (rect.height - img_h) / 2
    rl.draw_texture_ex(self._pair_kitty_texture, rl.Vector2(img_x, img_y), 0.0, 1.1, rl.WHITE)

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

  @staticmethod
  def _show_pairing():
    if not system_time_valid():
      dlg = alert_dialog(tr("Please connect to Wi-Fi to complete initial pairing"))
      gui_app.push_widget(dlg)
      return

    gui_app.push_widget(PairingDialog())
