"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import datetime
import os
from pathlib import Path

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.layouts.settings.developer import DeveloperLayout
from openpilot.common.hardware import PC
from openpilot.common.hardware.hw import Paths
from openpilot.sunnypilot.hardware.profile import HardwareProfile, get_hardware_profile
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.widgets.list_view import button_item

from openpilot.system.ui.sunnypilot.widgets.html_render import HtmlModalSP
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp
from openpilot.selfdrive.ui.widgets.qnn_wifi import QnnWifiUiState, ENABLED_PARAM, CONTROL_PARAM
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.qnn_wifi import QnnStatusDialog

PREBUILT_PATH = os.path.join(Paths.comma_home(), "prebuilt") if PC else "/data/openpilot/prebuilt"


class DeveloperLayoutSP(DeveloperLayout):
  def __init__(self):
    super().__init__()
    self.error_log_path = os.path.join(Paths.crash_log_root(), "error.log")
    self._is_release_branch: bool = self._is_release or ui_state.params.get_bool("IsReleaseSpBranch")
    self._is_development_branch: bool = ui_state.params.get_bool("IsTestedBranch") or ui_state.params.get_bool("IsDevelopmentBranch")
    self._initialize_items()

    for item in self.items:
      self._scroller.add_widget(item)

  def _initialize_items(self):
    self.show_advanced_controls = toggle_item_sp(lambda: tr("Show Advanced Controls"),
                                                 lambda: tr("Toggle visibility of advanced sunnypilot controls.<br>This only changes the visibility of the toggles; " +
                                                            "it does not change the actual enabled/disabled state."), param="ShowAdvancedControls")

    self.enable_github_runner_toggle = toggle_item_sp(lambda: tr("GitHub Runner Service"), lambda: tr("Enables or disables the GitHub runner service."),
                                                      param="EnableGithubRunner")

    self.enable_copyparty_toggle = toggle_item_sp(lambda: tr("copyparty Service"),
                                                  lambda: tr("copyparty is a very capable file server, you can use it to download your routes, view your logs " +
                                                             "and even make some edits on some files from your browser. " +
                                                             "Requires you to connect to your comma locally via its IP address."), param="EnableCopyparty")

    self.prebuilt_toggle = toggle_item_sp(lambda: tr("Quickboot Mode"), "", param="QuickBootToggle", callback=self._on_prebuilt_toggled)

    self.error_log_btn = button_item(lambda: tr("Error Log"), lambda: tr("VIEW"), lambda: tr("View the error log for sunnypilot crashes."), callback=self._on_error_log_clicked)

    self.items: list = [self.show_advanced_controls, self.enable_github_runner_toggle, self.enable_copyparty_toggle, self.prebuilt_toggle, self.error_log_btn,]

    if get_hardware_profile() == HardwareProfile.C3XL:
      self._qnn_state = QnnWifiUiState(ui_state.params, ui_state.is_offroad)
      self.qnn_wifi_toggle = toggle_item_sp(
        "Android NPU Wi-Fi",
        "Run the paired Snapdragon phone alongside the local model. This switch alone never selects remote control output.",
        initial_state=self._qnn_state.flag(ENABLED_PARAM),
        callback=lambda enabled: self._qnn_state.request(ENABLED_PARAM, enabled),
        enabled=lambda: ui_state.is_offroad() and not self._qnn_state.pending and
                        (self._qnn_state.configured or self._qnn_state.flag(ENABLED_PARAM)),
      )
      self.qnn_control_toggle = toggle_item_sp(
        "QNN control preference (saved)",
        "Saved across restarts and drives. Effective only after phone/model/device verification passes.",
        initial_state=self._qnn_state.flag(CONTROL_PARAM), callback=self._on_qnn_control,
        enabled=lambda: ui_state.is_offroad() and not self._qnn_state.pending and
                        (self._qnn_state.control_preference_editable or self._qnn_state.flag(CONTROL_PARAM)),
      )
      self.qnn_status_button = button_item("Snapdragon NPU status / pairing", "VIEW",
                                           "Pair a phone and inspect the live local/phone source state.",
                                           callback=self._on_qnn_status)
      self.items[0:0] = [self.qnn_wifi_toggle, self.qnn_control_toggle, self.qnn_status_button]

  def _on_qnn_control(self, enabled: bool):
    self.qnn_control_toggle.action_item.set_state(self._qnn_state.flag(CONTROL_PARAM))
    self._qnn_state.request(CONTROL_PARAM, enabled)

  def _on_qnn_status(self):
    gui_app.push_widget(QnnStatusDialog(self._qnn_state))

  @staticmethod
  def _on_prebuilt_toggled(state):
    if state:
      Path(PREBUILT_PATH).touch(exist_ok=True)
    else:
      os.remove(PREBUILT_PATH)
    ui_state.params.put_bool("QuickBootToggle", state)

  def _on_delete_confirm(self, result):
    if result == DialogResult.CONFIRM:
      if os.path.exists(self.error_log_path):
        os.remove(self.error_log_path)

  def _on_error_log_closed(self, result, log_exists):
    if result == DialogResult.CONFIRM and log_exists:
      dialog2 = ConfirmDialog(tr("Would you like to delete this log?"), tr("Yes"), tr("No"), rich=False, callback=self._on_delete_confirm)
      gui_app.push_widget(dialog2)

  def _on_error_log_clicked(self):
    text = ""
    if os.path.exists(self.error_log_path):
      text = f"<b>{datetime.datetime.fromtimestamp(os.path.getmtime(self.error_log_path)).strftime('%d-%b-%Y %H:%M:%S').upper()}</b><br><br>"
      try:
        with open(self.error_log_path) as file:
          text += file.read()
      except Exception:
        pass
    dialog = HtmlModalSP(text=text, callback=lambda result: self._on_error_log_closed(result, os.path.exists(self.error_log_path)))
    gui_app.push_widget(dialog)

  def _update_state(self):
    if hasattr(self, "_qnn_state"):
      self._qnn_state.update()
      self.qnn_wifi_toggle.action_item.set_state(self._qnn_state.flag(ENABLED_PARAM))
      self.qnn_control_toggle.action_item.set_state(self._qnn_state.flag(CONTROL_PARAM))
      self.qnn_status_button.set_description(self._qnn_state.summary())

    disable_updates = ui_state.params.get_bool("DisableUpdates")
    show_advanced = ui_state.params.get_bool("ShowAdvancedControls")

    if (prebuilt_file := os.path.exists(PREBUILT_PATH)) != ui_state.params.get_bool("QuickBootToggle"):
      ui_state.params.put_bool("QuickBootToggle", prebuilt_file)
      self.prebuilt_toggle.action_item.set_state(prebuilt_file)

    self.prebuilt_toggle.set_visible(show_advanced and not (self._is_release_branch or self._is_development_branch))
    self.prebuilt_toggle.action_item.set_enabled(disable_updates)

    if disable_updates:
      self.prebuilt_toggle.set_description(tr("When toggled on, this creates a prebuilt file to allow accelerated boot times. When toggled off, it " +
                                              "removes the prebuilt file so compilation of locally edited cpp files can be made."))
    else:
      self.prebuilt_toggle.set_description(tr("Quickboot mode requires updates to be disabled.<br>Enable 'Disable Updates' in the Software panel first."))

    self.enable_copyparty_toggle.set_visible(show_advanced)
    self.enable_github_runner_toggle.set_visible(show_advanced and not self._is_release_branch)
    self.error_log_btn.set_visible(not self._is_release_branch)
