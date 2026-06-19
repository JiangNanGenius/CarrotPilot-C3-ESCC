#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


class FakeParams:
  shared_store: dict[str, bytes] = {}

  @classmethod
  def reset(cls) -> None:
    cls.shared_store = {
      "CarrotPhoneSpeedLimitEnabled": b"1",
      "CarrotTrafficStopEnabled": b"1",
      "CarrotAutoTurnControlEnabled": b"1",
      "CarrotActiveSpeedControlEnabled": b"1",
      "FishopAutoOvertakeEnabled": b"1",
      "SpeedLimitPolicy": b"5",
      "SpeedLimitMode": b"1",
      "SpeedLimitOffsetType": b"0",
      "SpeedLimitValueOffset": b"0",
      "IsMetric": b"1",
      "IsOnroad": b"0",
    }

  def __init__(self) -> None:
    self.store = self.shared_store

  def get(self, key: str, *args, **kwargs):
    if key in self.store:
      return self.store[key]
    if kwargs.get("return_default"):
      return None
    return None

  def get_bool(self, key: str) -> bool:
    raw = self.get(key)
    if raw is None:
      return False
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="ignore")
    return str(raw).strip().lower() in ("1", "true", "on", "yes", "y")

  def get_int(self, key: str) -> int:
    raw = self.get(key)
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="ignore")
    try:
      return int(raw or 0)
    except (TypeError, ValueError):
      return 0

  def put(self, key: str, value: Any) -> None:
    self.store[key] = self._encode(value)

  def put_bool(self, key: str, value: Any) -> None:
    self.put(key, "1" if bool(value) else "0")

  def remove(self, key: str) -> None:
    self.store.pop(key, None)

  @staticmethod
  def _encode(value: Any) -> bytes:
    if isinstance(value, bytes):
      return value
    if isinstance(value, (dict, list)):
      return json.dumps(value, separators=(",", ":")).encode("utf-8")
    return str(value).encode("utf-8")


def import_file(module_name: str, rel: str):
  spec = importlib.util.spec_from_file_location(module_name, str(ROOT / rel))
  if spec is None or spec.loader is None:
    raise RuntimeError(f"unable to import {rel}")
  module = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = module
  spec.loader.exec_module(module)
  return module


def install_fake_params():
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  return previous_params


def restore_params(previous_params) -> None:
  if previous_params is None:
    sys.modules.pop("openpilot.common.params", None)
  else:
    sys.modules["openpilot.common.params"] = previous_params


def check(condition: bool, message: str) -> None:
  if not condition:
    raise AssertionError(message)


def decode_param_json(key: str) -> dict[str, Any]:
  raw = FakeParams.shared_store.get(key, b"{}")
  decoded = json.loads(raw.decode("utf-8", errors="replace"))
  check(isinstance(decoded, dict), f"{key} did not store a JSON object")
  return decoded


def flat_nav_payload() -> dict[str, Any]:
  return {
    "carrotIndex": 7,
    "carrotCmd": "OVERTAKE",
    "carrotArg": "left",
    "nRoadLimitSpeed": 80,
    "speedLimitKph": 70,
    "nSdiType": 7,
    "nSdiSpeedLimit": 60,
    "nSdiDist": 240,
    "nSdiPlusType": 3,
    "nSdiPlusSpeedLimit": 50,
    "nSdiPlusDist": 600,
    "nTBTDist": 500,
    "nTBTTurnType": 12,
    "nTBTDistNext": 900,
    "nTBTTurnTypeNext": 13,
    "nSpeedBumpDist": 80,
    "modelSpeedKph": 45,
    "trafficRedLightOn": True,
    "trafficGreenLightOn": False,
    "leftLightOn": True,
    "szTBTMainText": "Carrot replay",
    "szTBTMainTextNext": "left turn ahead",
    "latitude": 1.234567,
    "longitude": 2.345678,
  }


def assert_navigation_event(event: dict[str, Any], *, source: str, speed_limit_kph: float) -> None:
  check(event.get("source") == source, f"unexpected source: {event.get('source')}")
  check(event.get("readOnly") is True and event.get("controlOutput") is False, "navigation event must remain read-only/no-control")
  check(event.get("speedLimitKph") == speed_limit_kph, "phone/APN speed limit was not parsed")

  numeric = event.get("numeric", {})
  hazards = event.get("hazards", {})
  traffic = event.get("trafficLight", {})
  model_speed = event.get("modelSpeed", {})
  preview = event.get("controlPreview", {})

  check(numeric.get("nTBTTurnType") == 12 and numeric.get("nTBTTurnTypeNext") == 13, "turn fields were not parsed")
  check(hazards.get("sdi", {}).get("type") == 7, "SDI type was not parsed")
  check(hazards.get("sdi", {}).get("speedLimitKph") == 60.0, "SDI speed limit was not parsed")
  check(hazards.get("sdi", {}).get("distanceM") == 240.0, "SDI distance was not parsed")
  check(hazards.get("sdi", {}).get("plusDistanceM") == 600.0, "SDI plus distance was not parsed")
  check(hazards.get("speedBump", {}).get("available") is True, "speed-bump evidence was not marked available")
  check(hazards.get("speedBump", {}).get("distanceM") == 80.0, "speed-bump distance was not parsed")
  check(model_speed.get("available") is True and model_speed.get("speedKph") == 45.0, "model speed was not parsed")
  check(model_speed.get("controlOutput") is False, "model speed must be read-only evidence")
  check(traffic.get("red") is True and traffic.get("leftGreen") is True, "traffic light fields were not parsed")
  check(preview.get("trafficStop", {}).get("candidate") is True, "traffic-stop preview candidate missing")
  check(preview.get("autoTurn", {}).get("candidate") is True, "auto-turn preview candidate missing")
  check(preview.get("activeSpeed", {}).get("candidate") is True, "active-speed preview candidate missing")
  check(preview.get("controlOutput") is False, "preview must not publish control output")


def assert_status_payload(server, *, expected_speed_limit_kph: float) -> None:
  status = server.build_status_payload({"speedLimitKph": expected_speed_limit_kph, "speedLimitSource": "phone"})
  check(status.get("tbt_dist") == 500, "status payload lost TBT distance")
  check(status.get("sdi_dist") == 240 and status.get("sdi_type") == 7, "status payload lost SDI evidence")
  check(status.get("speedBumpAvailable") is True and status.get("speedBumpDist") == 80.0, "status payload lost speed-bump evidence")
  check(status.get("modelSpeedAvailable") is True and status.get("modelSpeedKph") == 45.0, "status payload lost model speed evidence")
  check(status.get("trafficLight", {}).get("red") is True, "status payload lost traffic-light evidence")
  check(status.get("carrotControlPreview", {}).get("controlOutput") is False, "status payload preview must remain no-control")
  check(status.get("phoneSpeedLimitFresh") is True, "phone speed state should be fresh after replay")
  check(status.get("phoneSpeedLimitKph") == expected_speed_limit_kph, "phone speed state has wrong speed")
  check(status.get("controlOutput") is False, "status payload must remain no-control")


def run_contract() -> list[str]:
  FakeParams.reset()
  previous_params = install_fake_params()
  try:
    server = import_file("genius_navipilot_replay_contract_server", "selfdrive/carrot/carrot_server.py")
    checked: list[str] = []

    result = server.record_navigation_event(flat_nav_payload(), "udp-7706")
    event = result.get("event", {})
    check(result.get("recorded") is True and isinstance(event, dict), "flat UDP-style navigation event was not recorded")
    check(result.get("phoneSpeed", {}).get("accepted") is True, "flat navigation replay did not update phone speed")
    assert_navigation_event(event, source="udp-7706", speed_limit_kph=70.0)
    check(event.get("commandIgnored") is True and event.get("highRiskCommandSeen") is True, "overtake command was not kept as ignored evidence")
    raw_speed = float(FakeParams.shared_store.get("CarrotPhoneSpeedLimit", b"0").decode("utf-8"))
    check(abs(raw_speed - 19.444444) < 0.001, "phone speed was not stored in m/s")
    persisted = decode_param_json("CarrotNavigationEvent")
    check(persisted.get("ignoredCommand") == "OVERTAKE", "ignored command evidence was not persisted")
    checked.append("flat UDP/APN navigation replay")

    assert_status_payload(server, expected_speed_limit_kph=70.0)
    checked.append("status payload navigation evidence")

    app = {"navi_http_state": {}}
    rgdata_payload = flat_nav_payload()
    rgdata_payload["speedLimitKph"] = 65
    result = server.record_navi_http_event(app, {"rgdata": rgdata_payload}, "replay")
    check(result.get("recorded") is True and result.get("type") == "rgdata", "rgdata compatibility event was not recorded")
    check(result.get("paramsWritten") is True, "rgdata compatibility event did not write CarrotNavi params")
    nav_result = result.get("navigation", {})
    event = nav_result.get("event", {})
    check(nav_result.get("recorded") is True and isinstance(event, dict), "rgdata compatibility navigation event missing")
    assert_navigation_event(event, source="http-7713-rgdata", speed_limit_kph=65.0)
    navi_debug = decode_param_json("CarrotNaviDebug")
    check(navi_debug.get("controlOutput") is False, "CarrotNaviDebug must stay no-control")
    check(app["navi_http_state"].get("receivedTypes", {}).get("rgdata") == 1, "rgdata receive counter missing")
    checked.append("rgdata HTTP/TCP compatibility replay")

    sinf_app = {"navi_http_state": {}}
    sinf_result = server.record_navi_http_event(sinf_app, {"sinf": {"distance": 150, "redLightOn": True}}, "")
    sinf_event = sinf_result.get("navigation", {}).get("event", {})
    check(sinf_event.get("trafficLight", {}).get("red") is True, "sinf red-light event was not parsed")
    check(sinf_event.get("controlPreview", {}).get("trafficStop", {}).get("candidate") is True, "sinf traffic-stop candidate missing")
    ssinf_result = server.record_navi_http_event(sinf_app, {"ssinf": {"distance": 90, "straight": "GREEN_LIGHT_ON", "left": "GREEN_LIGHT_ON"}}, "")
    ssinf_event = ssinf_result.get("navigation", {}).get("event", {})
    check(ssinf_event.get("trafficLight", {}).get("green") is True, "ssinf green-light event was not parsed")
    check(ssinf_event.get("trafficLight", {}).get("leftGreen") is True, "ssinf left-green event was not parsed")
    checked.append("sinf/ssinf traffic-light replay")

    return checked
  finally:
    restore_params(previous_params)


def main() -> int:
  parser = argparse.ArgumentParser(description="Replay Navipilot/APN/N samples through the Genius Pilot local navigation parser.")
  parser.add_argument("--self-test", action="store_true", help="run the offline fake-Params replay contract")
  _args = parser.parse_args()

  checked = run_contract()
  for item in checked:
    print(f"PASS {item}")
  print("PASS Genius Navipilot/APN/N replay contract")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
