#!/usr/bin/env python3
import time
import json
import jwt
from pathlib import Path

from datetime import datetime, timedelta, UTC
from openpilot.common.api import api_get
from openpilot.common.params import Params
from openpilot.common.spinner import Spinner
from openpilot.selfdrive.selfdrived.alertmanager import set_offroad_alert
from openpilot.system.hardware import HARDWARE, PC
from openpilot.system.hardware.hw import Paths
from openpilot.common.swaglog import cloudlog


UNREGISTERED_DONGLE_ID = "UnregisteredDevice"

def is_registered_device() -> bool:
  dongle = Params().get("DongleId", encoding='utf-8')
  return dongle not in (None, UNREGISTERED_DONGLE_ID)


def register(show_spinner=False) -> str | None:
  """
  All devices built since March 2024 come with all
  info stored in /persist/. This is kept around
  only for devices built before then.

  With a backend update to take serial number instead
  of dongle ID to some endpoints, this can be removed
  entirely.
  """
  params = Params()


  #return UNREGISTERED_DONGLE_ID  # for c3lite, clone
  dongle_id: str | None = params.get("DongleId", encoding='utf8')
  if dongle_id is None and Path(Paths.persist_root()+"/comma/dongle_id").is_file():
    # not all devices will have this; added early in comma 3X production (2/28/24)
    with open(Paths.persist_root()+"/comma/dongle_id") as f:
      dongle_id = f.read().strip()

  pubkey = Path(Paths.persist_root()+"/comma/id_rsa.pub")
  if not pubkey.is_file():
    dongle_id = UNREGISTERED_DONGLE_ID
    cloudlog.warning(f"missing public key: {pubkey}")
  elif dongle_id is None:
    if show_spinner:
      spinner = Spinner()
      spinner.update("registering device")

    # Create registration token, in the future, this key will make JWTs directly
    with open(Paths.persist_root()+"/comma/id_rsa.pub") as f1, open(Paths.persist_root()+"/comma/id_rsa") as f2:
      public_key = f1.read()
      private_key = f2.read()

    # Block until we get the imei
    serial = HARDWARE.get_serial()
    start_time = time.monotonic()
    imei1, imei2 = "12345678", "123456789"
    dongle_id = UNREGISTERED_DONGLE_ID
    if show_spinner:
      spinner.close()

  if dongle_id:
    params.put("DongleId", dongle_id)
    set_offroad_alert("Offroad_UnofficialHardware", (dongle_id == UNREGISTERED_DONGLE_ID) and not PC)
  return dongle_id


if __name__ == "__main__":
  print(register())
