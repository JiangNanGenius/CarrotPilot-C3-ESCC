#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TITLE = "Genius Pilot Super Advanced Contract"

CRITICAL_PARAMS = {
  "CarrotPhoneSpeedLimitEnabled": '"1"',
  "CarrotMapOverlayEnabled": '"0"',
  "CarrotActiveSpeedControlEnabled": '"0"',
  "CarrotAutoTurnControlEnabled": '"0"',
  "CarrotTrafficStopEnabled": '"0"',
  "CarrotLearningActive": '"0"',
  "CarrotLearningAutoApply": '"0"',
  "FishopLaneCurveEnabled": '"0"',
  "FishopLidarBlindspotEnabled": '"0"',
  "FishopLidarLaneDataEnabled": '"0"',
  "FishopAutoOvertakeEnabled": '"0"',
  "NeuralNetworkLateralControl": '"1"',
  "CurveSpeedControlMode": '"1"',
}

SUPER_ADVANCED_KEYS = (
  "CarrotPhoneSpeedLimitEnabled",
  "CarrotMapOverlayEnabled",
  "CurveSpeedControlMode",
  "AutoCurveSpeedLowerLimit",
  "CarrotActiveSpeedControlEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotTrafficStopEnabled",
  "TrafficLightDetectMode",
  "TrafficStopDistanceAdjust",
  "CarrotCruiseAtcDecel",
  "TurnSpeedControlMode",
  "CarrotLearningActive",
  "CarrotLearningAutoApply",
  "CarrotTunerApplyLat",
  "CarrotTunerApplyLong",
  "UseLaneLineCurveSpeed",
  "FishopLaneCurveEnabled",
  "FishopLidarBlindspotEnabled",
  "FishopLidarLaneDataEnabled",
  "FishopAutoOvertakeEnabled",
)

API_WRITABLE_KEYS = (
  "CarrotActiveSpeedControlEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotTrafficStopEnabled",
  "FishopAutoOvertakeEnabled",
  "CurveSpeedControlMode",
  "NeuralNetworkLateralControl",
  "GeniusCarrotWorldOverlay",
  "GeniusFishopVisualOverlay",
)


def read(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
  return {"name": name, "ok": bool(ok), "detail": detail}


def build_report() -> dict[str, Any]:
  params = read("common/params_keys.h")
  carrot_settings = read("selfdrive/ui/sunnypilot/layouts/settings/carrot.py")
  settings = read("selfdrive/ui/sunnypilot/layouts/settings/settings.py")
  carrot_server = read("selfdrive/carrot/carrot_server.py")
  guide = read("docs/personal/CARROT_SETTINGS_GUIDE.md")
  conflicts = read("docs/personal/SETTINGS_CONFLICTS.md")
  matrix = read("docs/personal/SETTINGS_MATRIX.md")

  checks = []
  missing_defaults = [
    key for key, default in CRITICAL_PARAMS.items()
    if f'{{"{key}",' not in params or default not in params[params.find(f'{{"{key}",'):params.find(f'{{"{key}",') + 140]
  ]
  checks.append(check("critical params exist with personal defaults", not missing_defaults, ", ".join(missing_defaults)))

  missing_ui = [key for key in SUPER_ADVANCED_KEYS if key not in carrot_settings]
  checks.append(check("Super Advanced exposes Carrot/Fishop controls", not missing_ui, ", ".join(missing_ui)))

  checks.append(check(
    "Super Advanced is wired as its own settings panel",
    "CarrotLayout" in settings and "OP.PanelType.CARROT" in settings and 'tr_noop("Super Advanced")' in settings,
  ))
  checks.append(check(
    "missing params fail soft instead of causing unknown-key waits",
    "UnknownKeyName" in carrot_settings
    and "This setting is waiting for the updated Genius Pilot parameter table" in carrot_settings
    and 'button_text=lambda: tr("WAIT")' in carrot_settings,
  ))
  checks.append(check(
    "advanced controls are visible and user-toggleable while offroad",
    "PRECONTROL_FEATURE_PARAMS" in carrot_settings
    and "lambda: ui_state.is_offroad()" in carrot_settings
    and "LOCKED_CONTROL_PARAMS" not in carrot_settings
    and "toggle.action_item.set_enabled(False)" not in carrot_settings,
  ))

  missing_api = [key for key in API_WRITABLE_KEYS if f'"{key}":' not in carrot_server]
  checks.append(check("local Carrot Web/API exposes expected writable controls", not missing_api, ", ".join(missing_api)))
  checks.append(check(
    "protected/local-only params are not writable through API",
    '"OffroadMode": {"type": "bool", "default": False, "writable": False}' in carrot_server
    and '"SpeedFromPCM": {"type": "int", "default": 1, "writable": False' in carrot_server
    and "Cannot change params while onroad" in carrot_server,
  ))

  missing_matrix = [key for key in SUPER_ADVANCED_KEYS if key not in matrix]
  checks.append(check("settings matrix tracks Super Advanced controls", not missing_matrix, ", ".join(missing_matrix)))
  checks.append(check(
    "guide documents confusing directionality",
    "Higher values make curve detection more sensitive" in guide
    and "Lower values start slowing from farther away" in guide
    and "Negative values stop earlier/farther before the line" in guide
    and "Fishop display overlay and Carrot World overlay are evidence layers" in guide,
  ))
  checks.append(check(
    "conflict notes keep owners separate",
    "These controls are staged gates, not one shared switch" in conflicts
    and "DEC is a separate Sunny longitudinal option" in conflicts
    and "`FishopAutoOvertakeEnabled` defaults off and remains user-toggleable while offroad" in conflicts,
  ))

  return {"title": TITLE, "ok": all(item["ok"] for item in checks), "checks": checks}


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    TITLE,
    "SUPER_ADVANCED_KEYS",
    "CRITICAL_PARAMS",
    "API_WRITABLE_KEYS",
    "UnknownKeyName",
    "Super Advanced",
    "FishopAutoOvertakeEnabled",
    "CarrotTrafficStopEnabled",
    "NeuralNetworkLateralControl",
  )
  if not all(token in text for token in required):
    print(f"FAIL {TITLE} self-test: missing token")
    return 1
  report = build_report()
  if not report["ok"]:
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1
  print(f"PASS {TITLE} self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description=TITLE)
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report = build_report()
  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    print(f"{'PASS' if report['ok'] else 'FAIL'} {TITLE}")
    for item in report["checks"]:
      print(f"{'PASS' if item['ok'] else 'FAIL'} {item['name']}")
      if not item["ok"] and item.get("detail"):
        print(item["detail"])
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
