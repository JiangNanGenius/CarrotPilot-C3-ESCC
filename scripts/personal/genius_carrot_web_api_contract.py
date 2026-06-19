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

WRITABLE_CASES: dict[str, Any] = {
  "CarrotActiveSpeedControlEnabled": True,
  "CarrotAutoTurnControlEnabled": True,
  "CarrotTrafficStopEnabled": True,
  "FishopAutoOvertakeEnabled": True,
  "CurveSpeedControlMode": 3,
  "TurnSpeedControlMode": 3,
  "SpeedLimitMode": 3,
  "NeuralNetworkLateralControl": False,
  "GeniusVisualMode": 1,
  "GeniusLaneLineStyle": 2,
  "GeniusLeadRadarVisualMode": 2,
  "GeniusLaneChangeVisuals": False,
  "GeniusCarrotWorldOverlay": True,
  "GeniusFishopVisualOverlay": True,
}

READ_ONLY_PARAMS = ("OffroadMode", "SpeedFromPCM", "SshEnabled")
CLOUD_PARAMS = ("SunnylinkEnabled", "EnableSunnylinkUploader", "OnroadUploads", "EnableConnect")


class FakeParams:
  shared_store: dict[str, bytes] = {}
  defaults: dict[str, Any] = {}

  @classmethod
  def reset(cls) -> None:
    cls.shared_store = {}

  def __init__(self):
    self.store = self.shared_store

  def get(self, key: str, *args, **kwargs):
    if key in self.store:
      return self.store[key]
    if kwargs.get("return_default") and key in self.defaults:
      return self._encode(self.defaults[key])
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

  def put_int(self, key: str, value: Any) -> None:
    self.put(key, str(int(value)))

  def put_float(self, key: str, value: Any) -> None:
    self.put(key, f"{float(value):.6f}")

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


def with_fake_params():
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


def normalized_store_value(value: Any) -> bytes:
  if isinstance(value, bool):
    return b"1" if value else b"0"
  return str(value).encode("utf-8")


def run_contract() -> list[str]:
  FakeParams.reset()
  previous_params = with_fake_params()
  try:
    server = import_file("genius_carrot_web_api_contract_server", "selfdrive/carrot/carrot_server.py")
    cluster_world = import_file("genius_carrot_web_api_contract_cluster_world", "selfdrive/carrot/cluster_world.py")
    FakeParams.defaults = {key: meta.get("default") for key, meta in server.PARAM_API_DEFS.items()}

    checked: list[str] = []
    names = list(WRITABLE_CASES) + list(READ_ONLY_PARAMS) + ["AlwaysOffroad", "DeviceType"]
    state = server.params_bulk_state(names)
    check(state.get("hasParams") is True and state.get("has_params") is True, "fake Params was not used")
    check("AlwaysOffroad" in state.get("unknown", []), "legacy AlwaysOffroad must remain an inert unknown")
    check(state["values"].get("DeviceType") == "unknown", "DeviceType virtual default changed")
    checked.append("bulk metadata")

    for cloud_param in CLOUD_PARAMS:
      check(cloud_param not in server.PARAM_API_DEFS, f"{cloud_param} must not be exposed through local API")
      try:
        server.set_param_from_api(cloud_param, True)
        raise AssertionError(f"{cloud_param} should not be writable")
      except ValueError:
        pass
    checked.append("cloud params absent")

    empty_cluster = server.cluster_world_state()
    check(empty_cluster.get("schema") == "GeniusClusterWorldSnapshot", "cluster world API state schema changed")
    check(empty_cluster.get("controlOutput") is False and empty_cluster.get("readOnly") is True, "cluster world API must remain read-only")
    live_snapshot = server.normalize_cluster_world_sample({
      "carState": {"vEgo": 10.0, "cruiseState": {"speed": 12.5}},
      "modelV2": {"position": {"x": [0.0, 5.0], "y": [0.0, 0.1], "z": [0.0, 0.0]}},
      "onroadEvents": ["preLaneChangeRight"],
    })
    live_cluster = server.cluster_world_state({
      "available": True,
      "lastSample": {"carState": {"vEgo": 10.0}},
      "lastUpdateAt": server.time.time(),
      "snapshot": live_snapshot,
    })
    check(live_cluster.get("fresh") is True and live_cluster.get("hasLiveSample") is True, "cluster world live state did not become fresh")
    check(live_cluster.get("snapshot", {}).get("base", {}).get("laneChangeIntent") == "right", "cluster world snapshot did not preserve lane-change evidence")
    check(live_cluster.get("snapshot", {}).get("controlOutput") is False, "cluster world snapshot must not expose control output")
    sample_cluster = cluster_world.normalize_cluster_world_sample(cluster_world.built_in_cluster_world_sample())
    combined_items = sample_cluster.get("objects", []) + sample_cluster.get("radarPoints", [])
    check(combined_items and all(item.get("sourceColor") for item in combined_items), "cluster world items must expose source colors for the debug page")
    check(all(point.get("raw") is True and point.get("merged") is False for point in sample_cluster.get("radarPoints", [])), "cluster world radar points must remain raw display evidence")
    checked.append("cluster world read-only API")

    for name in READ_ONLY_PARAMS:
      state = server.params_bulk_state([name])
      check(state["writable"].get(name) is False, f"{name} should be read-only")
      try:
        server.set_param_from_api(name, 1)
        raise AssertionError(f"{name} should reject writes")
      except ValueError:
        pass
    checked.append("read-only params blocked")

    for name, value in WRITABLE_CASES.items():
      state = server.params_bulk_state([name])
      check(state["writable"].get(name) is True, f"{name} should be writable while offroad")
      result = server.set_param_from_api(name, value)
      check(result.get("changed") is True, f"{name} write did not report changed")
      after = server.params_bulk_state([name])
      check(after["values"].get(name) == result.get("value"), f"{name} readback mismatch")
      check(FakeParams.shared_store.get(name) == normalized_store_value(result["value"]), f"{name} store mismatch")
    checked.append("offroad writes/readbacks")

    clamp = server.set_param_from_api("SpeedLimitValueOffset", 999)
    check(clamp["value"] == 30 and FakeParams.shared_store.get("SpeedLimitValueOffset") == b"30", "SpeedLimitValueOffset high clamp failed")
    clamp = server.set_param_from_api("SpeedLimitValueOffset", -999)
    check(clamp["value"] == -30 and FakeParams.shared_store.get("SpeedLimitValueOffset") == b"-30", "SpeedLimitValueOffset low clamp failed")
    clamp = server.set_param_from_api("CurveSpeedControlMode", 99)
    check(clamp["value"] == 3 and FakeParams.shared_store.get("CurveSpeedControlMode") == b"3", "CurveSpeedControlMode high clamp failed")
    clamp = server.set_param_from_api("CurveSpeedControlMode", -8)
    check(clamp["value"] == 0 and FakeParams.shared_store.get("CurveSpeedControlMode") == b"0", "CurveSpeedControlMode low clamp failed")
    checked.append("bounds clamps")

    server.set_param_from_api("CarrotActiveSpeedControlEnabled", True)
    FakeParams.shared_store["IsOnroad"] = b"1"
    try:
      server.set_param_from_api("CarrotActiveSpeedControlEnabled", False)
      raise AssertionError("onroad changed write was not blocked")
    except RuntimeError:
      pass
    unchanged = server.set_param_from_api("CarrotActiveSpeedControlEnabled", True)
    check(unchanged.get("changed") is False, "same-value onroad probe should not be treated as a changed write")
    checked.append("onroad write block")

    return checked
  finally:
    restore_params(previous_params)


def main() -> int:
  parser = argparse.ArgumentParser(description="Check Genius Pilot local Carrot Web/API parameter contract.")
  parser.add_argument("--self-test", action="store_true", help="run the local fake-Params API contract")
  args = parser.parse_args()

  checked = run_contract()
  for item in checked:
    print(f"PASS {item}")
  print(f"PASS Genius Carrot Web API contract: {len(WRITABLE_CASES)} writable params")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
