#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


class FakeParams:
  def __init__(self, mode: int):
    self.mode = mode

  def get_int(self, key: str) -> int:
    if key != "CurveSpeedControlMode":
      raise KeyError(key)
    return self.mode


def import_policy():
  path = ROOT / "sunnypilot/selfdrive/controls/lib/smart_cruise_control/curve_speed_policy.py"
  source = path.read_text(encoding="utf-8").replace("from openpilot.common.params import Params", "class Params:\n  pass")
  module = types.ModuleType("curve_speed_policy_contract")
  exec(compile(source, str(path), "exec"), module.__dict__)
  return module


def check_sources() -> list[str]:
  errors: list[str] = []
  policy = read("sunnypilot/selfdrive/controls/lib/smart_cruise_control/curve_speed_policy.py")
  vision = read("sunnypilot/selfdrive/controls/lib/smart_cruise_control/vision_controller.py")
  map_controller = read("sunnypilot/selfdrive/controls/lib/smart_cruise_control/map_controller.py")
  planner = read("sunnypilot/selfdrive/controls/lib/longitudinal_planner.py")
  ui = read("selfdrive/ui/sunnypilot/layouts/settings/carrot.py")
  matrix = read("docs/personal/SETTINGS_MATRIX.md")

  required_policy = (
    "CurveSpeedControlMode",
    "sunny_vision_curve_enabled",
    "sunny_map_speed_enabled",
    "carrot_curve_inputs_enabled",
    "return False",
  )
  if not all(token in policy for token in required_policy):
    errors.append("curve-speed policy helper missing required mode functions")

  if "sunny_vision_curve_enabled" not in vision or 'get_bool("SmartCruiseControlVision")' in vision:
    errors.append("SCC-V must be owned by CurveSpeedControlMode, not legacy SmartCruiseControlVision")

  if "sunny_map_speed_enabled" not in map_controller or 'get_bool("SmartCruiseControlMap")' in map_controller:
    errors.append("SCC-M must be owned by Genius policy, not legacy SmartCruiseControlMap")

  if "LongitudinalPlanSource.sccVision" not in planner or "LongitudinalPlanSource.sccMap" not in planner:
    errors.append("longitudinal planner must still publish SCC-V/SCC-M evidence")

  if "Fusion keeps Sunny curve quality and Carrot navigation/phone inputs together" not in ui:
    errors.append("Super Advanced UI must describe Fusion semantics")

  if "Off/Sunny/Carrot/Fusion selector" not in matrix:
    errors.append("settings matrix must classify CurveSpeedControlMode")

  return errors


def check_policy_runtime() -> list[str]:
  errors: list[str] = []
  module = import_policy()
  expected = {
    0: (False, False, False),
    1: (True, False, False),
    2: (False, True, False),
    3: (True, True, False),
  }
  for mode, (vision_expected, carrot_expected, map_expected) in expected.items():
    params = FakeParams(mode)
    vision = bool(module.sunny_vision_curve_enabled(params))
    carrot = bool(module.carrot_curve_inputs_enabled(params))
    map_enabled = bool(module.sunny_map_speed_enabled(params))
    if (vision, carrot, map_enabled) != (vision_expected, carrot_expected, map_expected):
      errors.append(
        f"mode {mode}: got vision={vision} carrot={carrot} map={map_enabled}, "
        f"expected vision={vision_expected} carrot={carrot_expected} map={map_expected}"
      )
  return errors


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate Genius Pilot curve-speed ownership and Fusion semantics.")
  parser.add_argument("--self-test", action="store_true", help="run source and lightweight runtime checks")
  parser.parse_args()

  errors = check_sources() + check_policy_runtime()
  if errors:
    for error in errors:
      print(f"FAIL {error}")
    return 1

  print("PASS Genius curve-speed contract")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
