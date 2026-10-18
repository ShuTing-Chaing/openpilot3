"""The unit's fitted narrow->wide rotation, kept across boots in /data."""
import json
import os
from pathlib import Path

import numpy as np

from .geometry import POP_ROTATION, rotvec_from_wide_from_device_euler

ROTATION_PATH = Path('/data/reproject_rotation.json')


def read_rotation() -> dict:
  """{'rotvec', ...} as the fitter/reprojector saved it, or {} when not fitted."""
  try:
    d = json.loads(ROTATION_PATH.read_text(encoding='utf-8'))
    if len(d['rotvec']) == 3 and np.isfinite(d['rotvec']).all():
      return d
  except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
    pass
  return {}


def load_rotation():
  """The fitted value, else the stock calibration seed, else the fleet median."""
  d = read_rotation()
  if d:
    return tuple(float(v) for v in d['rotvec'])
  try:
    from openpilot.cereal import log
    from openpilot.common.params import Params
    with log.Event.from_bytes(Params().get('CalibrationParams')) as msg:
      e = list(msg.extrinsicsCalibration.wideFromDeviceEuler)
    if len(e) == 3 and np.isfinite(e).all():
      return rotvec_from_wide_from_device_euler(e)
  except Exception:
    pass
  return POP_ROTATION


def save_rotation(rotvec, **extra) -> None:
  data = {'rotvec': [float(v) for v in rotvec], **extra}
  tmp = ROTATION_PATH.with_name(f'.{ROTATION_PATH.name}.tmp')
  tmp.write_text(json.dumps(data), encoding='utf-8')
  os.replace(tmp, ROTATION_PATH)
