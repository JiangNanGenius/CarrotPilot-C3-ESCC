#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def check_sources() -> list[str]:
  errors: list[str] = []
  guide = read("docs/personal/CARROT_SETTINGS_GUIDE.md")
  carrot_ui = read("selfdrive/ui/sunnypilot/layouts/settings/carrot.py")
  cruise_ui = read("selfdrive/ui/sunnypilot/layouts/settings/cruise.py")
  matrix = read("docs/personal/SETTINGS_MATRIX.md")

  required_guide_tokens = (
    "AutoCurveSpeedFactor",
    "Higher values make curve detection more sensitive",
    "lower-limit speed",
    "AutoNaviSpeedDecelRate",
    "Lower values start slowing from farther away",
    "CruiseMaxVals0",
    "CruiseMaxVals6",
    "0.01 m/s^2",
    "0 km/h",
    "140 km/h",
    "PathOffset",
    "negative shifts left",
    "positive shifts right",
    "SteerActuatorDelay",
    "0 uses live/default delay",
    "VEgoStopping",
    "0.01 m/s",
    "Recommendation target meanings",
    "Stronger requested acceleration",
    "Longer following time gap",
    "No pending recommendation means no tuning value changes",
    "数值越高",
    "数值越低",
    "负值",
  )
  if not all(token in guide for token in required_guide_tokens):
    errors.append("Carrot settings guide missing required direction/unit tokens")

  required_ui_tokens = (
    "Main Carrot curve-speed scaling value. Higher values make curve detection more sensitive",
    "If the lower-limit speed is already reached",
    "Navigation-event deceleration scale. Lower values start slowing from farther away",
    "Maximum requested cruise acceleration near 80 km/h, in 0.01 m/s^2 units",
    "Lane/path lateral offset used by Carrot tuning. Zero is neutral; negative shifts left, positive shifts right.",
    "Additional steering actuator delay target used by Auto-Tuner. Zero uses live/default delay",
    "Stopping detection threshold in 0.01 m/s units",
    "If no recommendation is pending, no value changes",
    "higher Cruise Accel is stronger",
    "Speed-limit data still needs Speed Limit Assist",
    "Deceleration target used only by Auto Turn Control",
  )
  if not all(token in carrot_ui for token in required_ui_tokens):
    errors.append("Super Advanced Carrot UI missing clarified tuning descriptions")

  if "Navigation-event deceleration scale. Lower values start slowing from farther away" not in cruise_ui:
    errors.append("Cruise page must use the same navigation decel direction as Super Advanced")

  forbidden = (
    "Higher usually keeps more speed through curves",
    "Fusion keeps Sunny curve quality",
    "Off/Sunny/Carrot/Fusion selector",
  )
  for token in forbidden:
    if token in guide + carrot_ui + cruise_ui + matrix:
      errors.append(f"stale misleading token still present: {token}")

  required_matrix_tokens = (
    "Higher makes Carrot curve detection more sensitive",
    "Lower values slow from farther away",
    "0.01 m/s^2 @ 80 km/h",
    "0.01 m/s",
    "negative shifts left, positive shifts right",
    "0 uses live/default delay",
    "Off/Sunny/Carrot/Balanced selector",
  )
  if not all(token in matrix for token in required_matrix_tokens):
    errors.append("settings matrix missing clarified Carrot tuning semantics")

  return errors


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate Genius Pilot Carrot settings guide and tuning semantics.")
  parser.add_argument("--self-test", action="store_true", help="run source checks used by the release gate")
  parser.parse_args()

  errors = check_sources()
  if errors:
    for error in errors:
      print(f"FAIL {error}")
    return 1

  print("PASS Genius Carrot settings guide contract")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
