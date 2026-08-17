#!/usr/bin/env python3
from pathlib import Path

from openpilot.common.api import get_key_pair
from openpilot.common.params import Params
from openpilot.system.hardware import HARDWARE
from openpilot.system.hardware.hw import Paths


UNREGISTERED_DONGLE_ID = "UnregisteredDevice"

def is_registered_device() -> bool:
  dongle = Params().get("DongleId")
  return dongle not in (None, UNREGISTERED_DONGLE_ID)


def register(show_spinner=False) -> str | None:
  """
  Offline device registration. Generates a stable local DongleId and never
  contacts any remote backend. Always returns a non-empty identifier so that
  callers (e.g. the manager) never fail on registration.
  """
  params = Params()
  dongle_id: str | None = params.get("DongleId")
  if dongle_id is None and Path(Paths.persist_root()+"/comma/dongle_id").is_file():
    # not all devices will have this; added early in comma 3X production (2/28/24)
    with open(Paths.persist_root()+"/comma/dongle_id") as f:
      dongle_id = f.read().strip()

  # Read the local key pair (pure local filesystem access, non-network). The
  # result is optional and does not affect local DongleId derivation.
  _ = get_key_pair()

  if dongle_id is None:
    serial = HARDWARE.get_serial()
    dongle_id = f"local-{serial}"  # stable, never "UnregisteredDevice"

  if dongle_id:
    params.put("DongleId", dongle_id)
  return dongle_id


if __name__ == "__main__":
  print(register())
