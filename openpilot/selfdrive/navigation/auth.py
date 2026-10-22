from __future__ import annotations

import os
from pathlib import Path

from openpilot.common.params import Params

NAV_API_HOST = os.environ.get("NAV_API_HOST", "https://nav.mr-one.cn").rstrip("/")
NAV_TOKEN_PATH = Path(os.environ.get("NAV_TOKEN_PATH", "/data/nav_token"))
NAV_DEVICE_ID = os.environ.get("NAV_DEVICE_ID", "")


def _as_text(value) -> str:
  if isinstance(value, bytes):
    return value.decode("utf-8", "replace").strip()
  return str(value or "").strip()


def nav_auth(params: Params | None = None) -> tuple[str, dict[str, str]]:
  params = params if params is not None else Params()
  device_id = _as_text(NAV_DEVICE_ID or params.get("DongleId"))
  try:
    token = NAV_TOKEN_PATH.read_text(encoding="utf-8").strip()
  except OSError:
    token = ""
  if not device_id or not token:
    raise RuntimeError("navigation credentials are not installed")
  return device_id, {"X-Device-ID": device_id, "X-Nav-Token": token}
