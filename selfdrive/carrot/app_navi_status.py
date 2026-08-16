#!/usr/bin/env python3
"""Read-only AmapNavi compatibility publisher.

This intentionally does not receive app commands, control external blinkers, or
feed lane-change logic. It only mirrors existing carState lane/blind data into
the fishop-compatible amapNavi message for later app/navigation experiments.
"""

OEM_BLIND_BIT = 2
PUBLISH_HZ = 20


def _safe_int(value, default: int = -1) -> int:
  try:
    return int(value)
  except (TypeError, ValueError):
    return default


def _stock_blind_mask(value) -> int:
  return OEM_BLIND_BIT if bool(value) else 0


def build_payload(car_state) -> dict[str, object]:
  left_line = _safe_int(getattr(car_state, "leftLaneLine", -1))
  right_line = _safe_int(getattr(car_state, "rightLaneLine", -1))
  return {
    "leftBlind": _stock_blind_mask(getattr(car_state, "leftBlindspot", False)),
    "rightBlind": _stock_blind_mask(getattr(car_state, "rightBlindspot", False)),
    "lineValid": left_line >= 0 or right_line >= 0,
    "leftLine": left_line,
    "rightLine": right_line,
  }


def fill_message(msg, car_state) -> None:
  payload = build_payload(car_state)
  msg.amapNavi.leftBlind = payload["leftBlind"]
  msg.amapNavi.rightBlind = payload["rightBlind"]
  msg.amapNavi.lineValid = payload["lineValid"]
  msg.amapNavi.leftLine = payload["leftLine"]
  msg.amapNavi.rightLine = payload["rightLine"]


def main() -> None:
  import cereal.messaging as messaging
  from openpilot.common.realtime import Ratekeeper

  sm = messaging.SubMaster(["carState"])
  pm = messaging.PubMaster(["amapNavi"])
  rk = Ratekeeper(PUBLISH_HZ, print_delay_threshold=None)

  while True:
    sm.update(0)
    msg = messaging.new_message("amapNavi")
    msg.valid = bool(sm.alive["carState"])
    fill_message(msg, sm["carState"])
    pm.send("amapNavi", msg)
    rk.keep_time()


if __name__ == "__main__":
  main()
