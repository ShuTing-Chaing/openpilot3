"""Native discovery, explicit phone-fingerprint pairing and live QNN status."""
import html
import pyray as rl

from openpilot.selfdrive.ui.widgets.qnn_wifi import PAIRING_STEPS
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.sunnypilot.widgets.input_dialog import InputDialogSP
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.button import Button
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.html_render import HtmlRenderer
from openpilot.system.ui.widgets.list_view import button_item
from openpilot.system.ui.widgets.label import UnifiedLabel
from openpilot.system.ui.widgets.scroller_tici import Scroller


class QnnStatusDialog(Widget):
  def __init__(self, state):
    super().__init__()
    self.state, self.flow = state, state.pairing
    self._message = UnifiedLabel(lambda: self.flow.message, font_size=40)
    def allowed():
      return state.is_offroad() and not self.flow.busy and not state.pending
    discover = button_item("Discover QNN phones", "SCAN", callback=self.flow.begin_discovery, enabled=allowed)
    manual = button_item("Manual phone IPv4 / port", "ENTER", callback=self._manual, enabled=allowed)
    opif = button_item("OPIF TCP: either phone App", "CONFIGURE", "No authentication; shadow mode only. Default port5555.", self._opif, enabled=allowed)
    capture = button_item(lambda: f"New pairing capture: {self.flow.capture[0]} x {self.flow.capture[1]}", "CHANGE",
                          "Changes the next pairing profile only; it grants no camera/model qualification.", self._cycle_capture, enabled=allowed)
    mode = button_item(lambda: f"Backend choice: {self.flow.execution_mode}", "CHANGE",
                       "npu_only: strict NPU; npu_cpu: NPU + CPU; gpu_cpu: GPU + CPU; cpu: ORT CPU reference. " +
                       "Selection does not modify the phone or existing profile.", self.flow.cycle_execution_mode, enabled=allowed)
    apply_mode = button_item("Apply mode to this saved profile", "APPLY", "Clears enable/control. Select the SAME mode in the phone app.",
                             self.flow.begin_mode_update, enabled=lambda: allowed() and state.paired)
    forget = button_item("Forget phone locally", "FORGET", "Removes local credentials and disables QNN. Phone-side revocation is separate.",
                         self._forget, enabled=allowed)
    self._candidates = [button_item(lambda i=i: self._candidate_title(i), "SELECT", "Untrusted discovery candidate; verify the phone fingerprint.",
                                    lambda i=i: self._select(i), enabled=allowed) for i in range(12)]
    for item in self._candidates:
      item.set_visible(False)
    self._last_text = self._status_text()
    self._content = HtmlRenderer(text=self._last_text)
    self._scroller = Scroller([discover, manual, opif, capture, mode, apply_mode, forget, *self._candidates, self._content], spacing=10)
    self._close = Button("Close", gui_app.pop_widget)

  def _candidate_title(self, index):
    if index >= len(self.flow.devices):
      return ""
    item = self.flow.devices[index]
    return f"{item['name']} — {item['host']}:{item['port']}"

  def _input(self, title, callback, *, minimum=0, secret=False):
    if not self.flow._allowed():
      return
    dialog = InputDialogSP(title, min_text_size=minimum, password_mode=secret)
    def result(outcome, text):
      dialog.keyboard.clear()
      if outcome == DialogResult.CONFIRM and self.state.is_offroad():
        callback(text)
    dialog.callback = result
    dialog.show()

  def _opif(self):
    self._input("OPIF phone IPv4 or IPv4:5555", self.flow.begin_opif, minimum=7)

  def _manual(self):
    def selected(endpoint):
      if self.flow.select_endpoint(endpoint):
        self._fingerprint_input()
    self._input("Phone IPv4 or IPv4:port", selected, minimum=7)

  def _select(self, index):
    if index >= len(self.flow.devices):
      return
    device = self.flow.devices[index]
    if self.flow.select_endpoint(f"{device['host']}:{device['port']}", device['fingerprint']):
      if self.flow.selection.get('fingerprint'):
        self._compare()
      else:
        self._fingerprint_input()

  def _fingerprint_input(self):
    def entered(pin):
      if self.flow.set_fingerprint(pin):
        self._compare()
    self._input("Complete SHA256 shown on PHONE", entered, minimum=64)

  def _compare(self):
    if not self.state.is_offroad() or self.flow.selection is None:
      return
    selected = dict(self.flow.selection)
    fingerprint = selected['fingerprint']
    chunks = '<br>'.join(fingerprint[i:i + 16] for i in range(0, 64, 16))
    message = (f"<h1>Compare with the PHONE screen</h1><p>{html.escape(selected['host'])}:{selected['port']}</p>" +
               f"<p>{chunks}</p><p>Check all 64 digits. Discovery alone is not trusted. Continue only when the phone shows this exact fingerprint.</p>")
    def confirmed(outcome):
      if outcome == DialogResult.CONFIRM and self.flow.selection == selected and self.flow.confirm_fingerprint():
        self._input("Phone's temporary six-digit pairing code", self.flow.begin_pair, minimum=6, secret=True)
    gui_app.push_widget(ConfirmDialog(message, "Matches phone", rich=True, callback=confirmed))

  def _cycle_capture(self):
    if self.flow._allowed():
      self.flow.capture = (1344, 760) if self.flow.capture == (1928, 1208) else (1928, 1208)

  def _forget(self):
    if not self.flow._allowed():
      return
    def confirmed(outcome):
      if outcome == DialogResult.CONFIRM:
        self.flow.begin_forget()
    gui_app.push_widget(ConfirmDialog("Remove local pairing and turn off QNN? The phone still retains its client authorization; " +
                                     "use the phone app to revoke it there.", "Forget locally", callback=confirmed))

  def _status_text(self):
    rows = [("Pairing action", self.flow.message), *self.state.rows()]
    fingerprint = self.state.public.get("fingerprint_sha256") or "Not paired"
    rows.append(("Saved TLS SHA256 fingerprint", fingerprint))
    rows.extend(PAIRING_STEPS)
    return "<h1>Android NPU Wi-Fi</h1>" + "".join(
      f"<p><b>{html.escape(title)}</b><br>{html.escape(value)}</p>" for title, value in rows)

  def _update_state(self):
    super()._update_state()
    self.flow.poll()
    for index, item in enumerate(self._candidates):
      item.set_visible(index < len(self.flow.devices))
    text = self._status_text()
    if text != self._last_text:
      self._content.parse_html_content(text)
      self._last_text = text

  def _render(self, rect):
    self._message.render(rl.Rectangle(rect.x + 40, rect.y + 20, rect.width - 80, 100))
    body = rl.Rectangle(rect.x + 40, rect.y + 140, rect.width - 80, rect.height - 310)
    self._content.set_rect(rl.Rectangle(0, 0, body.width, self._content.get_total_height(int(body.width))))
    self._scroller.render(body)
    self._close.render(rl.Rectangle(rect.x + rect.width - 400, rect.y + rect.height - 150, 350, 120))

  def show_event(self):
    super().show_event()
    self._scroller.show_event()

  def hide_event(self):
    self._scroller.hide_event()
    super().hide_event()
