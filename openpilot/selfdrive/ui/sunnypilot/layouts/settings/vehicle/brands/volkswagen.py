"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.vehicle.brands.base import BrandSettings
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import multiple_button_item_sp, toggle_item_sp


DESCRIPTIONS = {
  'avoid_eps_lockout': tr_noop(
    'Scale steering torque down at low speeds to avoid EPS lockout.'
  ),
  'network_location': tr_noop(
    'Choose whether the J533 harness is connected at the vehicle gateway or front camera. Changing this restarts the car interface.'
  ),
}


class VolkswagenSettings(BrandSettings):
  def __init__(self):
    super().__init__()

    self.avoid_eps_lockout = toggle_item_sp(
      lambda: tr("Avoid EPS Lockout"),
      description=lambda: tr(DESCRIPTIONS["avoid_eps_lockout"]),
      initial_state=ui_state.params.get_bool("VagAvoidEPSLockout"),
      callback=self._on_enable_avoid_eps_lockout,
      enabled=lambda: not ui_state.engaged,
    )

    self.network_location = multiple_button_item_sp(
      lambda: tr("Volkswagen Connection"),
      lambda: tr(DESCRIPTIONS["network_location"]),
      [lambda: tr("Gateway"), lambda: tr("Camera")],
      callback=self._on_network_location_changed,
      inline=False,
    )

    self.items = [
      self.network_location,
      self.avoid_eps_lockout,
    ]

  def _on_enable_avoid_eps_lockout(self, state: bool):
    ui_state.params.put_bool("VagAvoidEPSLockout", state, block=True)
    ui_state.params.put_bool("OnroadCycleRequested", True)

  def _on_network_location_changed(self, index: int):
    if index not in (0, 1):
      return
    ui_state.params.put("VagNetworkLocation", index, block=True)
    ui_state.params.put_bool("OnroadCycleRequested", True)

  def update_settings(self):
    value = ui_state.params.get("VagNetworkLocation")
    try:
      index = 0 if value is None else int(value)
    except (TypeError, ValueError):
      index = 0
    self.network_location.action_item.set_selected_button(index if index in (0, 1) else 0)
    self.network_location.action_item.set_enabled(ui_state.is_offroad())
