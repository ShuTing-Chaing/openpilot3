"""C3XL developer opt-in and per-onroad fallback latch for external CTM."""

import subprocess

from openpilot.common.params import Params
from openpilot.sunnypilot.hardware.profile import HardwareProfile, get_hardware_profile


PARAM = "C3XLExternalCTMControl"
AUTO_PARAM = "C3XLExternalCTMAuto"
FAILED_PARAM = "C3XLExternalCTMFailedThisOnroad"


def on_target_branch() -> bool:
  # This fork ships QNN Wi-Fi as a C3XL feature.  Hardware identity, not the
  # operator's branch label, is the stable capability boundary.
  return get_hardware_profile() == HardwareProfile.C3XL


def enabled(params: Params | None = None) -> bool:
  params = params or Params()
  return on_target_branch() and params.get_bool(PARAM) and not params.get_bool(FAILED_PARAM)


def activate(params: Params | None = None) -> bool:
  params = params or Params()
  if not on_target_branch() or params.get_bool(FAILED_PARAM):
    return False
  if params.get(AUTO_PARAM, return_default=True) is True:
    params.put_bool(PARAM, True, block=True)
  return enabled(params)


def mark_failed(params: Params | None = None) -> None:
  params = params or Params()
  params.put_bool(FAILED_PARAM, True, block=True)
  params.put_bool(PARAM, False, block=True)


if __name__ == "__main__":
  import sys
  if sys.argv[1:] == ["--fail"]:
    mark_failed()
  else:
    raise SystemExit(0 if activate() else 1)
