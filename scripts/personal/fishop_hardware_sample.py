#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openpilot.selfdrive.carrot.fishop_hardware import FishopHardwareState  # noqa: E402


SAMPLE_PAYLOADS: list[dict[str, Any]] = [
  {"resp": "lane", "left_lane": 2, "right_lane": 1, "lineValid": True, "max_curve": 0.018, "lat_a": 0.21,
   "prob": True, "l_lane_prob": 0.7, "l_line_prob": 0.9, "r_line_prob": 0.8, "r_lane_prob": 0.6,
   "l_edge_prob": 0.5, "r_edge_prob": 0.4, "l_lane_width": 3.2, "r_lane_width": 3.3,
   "l_edge_dist": 1.8, "r_edge_dist": 2.1, "lane_width": 3.25, "atc_state": 0, "blinker": 0},
  {"device": "lidar", "resp": "blindspot", "detect_side": 3, "lidar_id": 0, "dist_time": 123456,
   "lidar_lblind": True, "lidar_car_lblind": True, "rf_drel": 4200, "rb_drel": -1800,
   "rf_xrel": 850, "rf_vrel": -1.2, "v_ego_mps": 15.0},
  {"device": "camera", "resp": "cam_blind", "detect_side": 1, "left_blind": True},
  {"device": "navi", "provider": "Mapbox", "country": "AU", "accuracyM": 3.0,
   "lat": -33.8688, "lon": 151.2093},
  {"device": "overtake", "index": 7, "cmd": "OVERTAKE", "arg": "left",
   "request": True, "direction": "left", "reason": "hardware sample only"},
]


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Normalize fishop hardware JSON payloads into a read-only evidence snapshot.")
  parser.add_argument("jsonl", nargs="?", help="JSON Lines file. Use '-' or omit to read stdin.")
  parser.add_argument("--sample", action="store_true", help="Use built-in sample payloads.")
  parser.add_argument("--now", type=float, default=1000.0, help="Synthetic timestamp for deterministic output.")
  parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
  parser.add_argument("--self-test", action="store_true", help="Run the built-in Fishop replay contract.")
  return parser.parse_args()


def _payloads_from_lines(lines: Iterable[str]) -> Iterable[dict[str, Any]]:
  for line in lines:
    line = line.strip()
    if not line:
      continue
    payload = json.loads(line)
    if isinstance(payload, dict):
      yield payload
    elif isinstance(payload, list):
      for item in payload:
        if isinstance(item, dict):
          yield item


def load_payloads(args: argparse.Namespace) -> list[dict[str, Any]]:
  if args.sample:
    return list(SAMPLE_PAYLOADS)
  if args.jsonl and args.jsonl != "-":
    return list(_payloads_from_lines(Path(args.jsonl).read_text(encoding="utf-8", errors="replace").splitlines()))
  return list(_payloads_from_lines(sys.stdin))


def check(condition: bool, message: str) -> None:
  if not condition:
    raise AssertionError(message)


def assert_sample_snapshot(snapshot: dict[str, Any]) -> None:
  lane = snapshot.get("lane", {})
  blindspot = snapshot.get("blindspot", {})
  navigation = snapshot.get("navigation", {})
  overtake = snapshot.get("overtake", {})
  dynamic_blind = blindspot.get("dynamicBlind", {}) if isinstance(blindspot, dict) else {}
  preview = overtake.get("suggestionPreview", {}) if isinstance(overtake, dict) else {}
  gate = preview.get("navigationGate", {}) if isinstance(preview, dict) else {}

  check(snapshot.get("readOnly") is True and snapshot.get("controlOutputEnabled") is False, "Fishop snapshot must remain read-only/no-control")
  check(snapshot.get("sensorOnline") is True, "sample should report fresh Fishop evidence")
  check(lane.get("lineValid") is True, "lane-line evidence should be valid")
  check(lane.get("leftLine") == 2 and lane.get("rightLine") == 1, "left/right lane line values were not preserved")
  check(lane.get("maxCurve") == 0.018 and lane.get("latA") == 0.21, "lane curve values were not preserved")
  check(lane.get("laneQuality", {}).get("curveAvailable") is True, "lane curve quality was not exposed")
  check(lane.get("laneQuality", {}).get("controlOutput") is False, "lane quality must not publish control")

  check(blindspot.get("leftLidarBlind") is True and blindspot.get("leftLidarCarBlind") is True, "left lidar blindspot was not preserved")
  check(blindspot.get("leftCameraBlind") is True, "left camera blindspot was not preserved")
  check(blindspot.get("rightLidarOnline") is True, "right lidar online evidence was not preserved")
  check(blindspot.get("targetsFresh") is True, "lidar target freshness was not preserved")
  check("rf" in dynamic_blind.get("activeRiskPreview", []), "dynamic right-front risk preview missing")
  check(dynamic_blind.get("controlOutput") is False, "dynamic blind preview must not publish control")

  check(navigation.get("fresh") is True and navigation.get("provider") == "Mapbox", "navigation context was not preserved")
  check(gate.get("suggestionEligible") is False, "Mapbox/AU sample should not pass domestic navigation gate")
  check(gate.get("downgradeOutsideDomesticMap") is True, "navigation gate must downgrade outside domestic map coverage")
  check(gate.get("controlOutput") is False, "navigation gate must not publish control")

  check(overtake.get("commandSeen") is True and overtake.get("requested") is True, "overtake request was not preserved")
  check(overtake.get("direction") == "left", "overtake direction was not normalized")
  check(overtake.get("directionality", {}).get("alphaAction") == "record_only", "overtake action must remain record-only")
  check(preview.get("stage") == "display_only", "overtake preview must stay display-only")
  check(preview.get("readyForSuggestion") is False, "blocked sample should not be ready for suggestion")
  check(preview.get("controlOutput") is False and preview.get("emitsLateralCommand") is False, "overtake preview must not emit control")
  check("left blindspot evidence blocks the suggestion" in preview.get("reasons", []), "blindspot blocking reason missing")


def self_test() -> None:
  state = FishopHardwareState()
  for payload in SAMPLE_PAYLOADS:
    state.update_from_payload(payload, 1000.0)
  assert_sample_snapshot(state.to_dict(1000.0))

  from openpilot.selfdrive.carrot import carrot_server

  with tempfile.TemporaryDirectory() as tmpdir:
    jsonl = Path(tmpdir) / "fishop_hardware.jsonl"
    jsonl.write_text("\n".join(json.dumps(payload, separators=(",", ":")) for payload in SAMPLE_PAYLOADS) + "\n",
                    encoding="utf-8")
    previous_path = carrot_server.DEFAULT_FISHOP_JSONL
    carrot_server.DEFAULT_FISHOP_JSONL = jsonl
    try:
      api_state = carrot_server.fishop_state()
    finally:
      carrot_server.DEFAULT_FISHOP_JSONL = previous_path

  check(api_state.get("inputAvailable") is True, "Carrot Web/API fishop state did not see sample input")
  check(api_state.get("payloadCount") == len(SAMPLE_PAYLOADS), "Carrot Web/API fishop state lost sample payloads")
  check(api_state.get("parseError") == "", "Carrot Web/API fishop state reported a parse error")
  assert_sample_snapshot(api_state.get("snapshot", {}))


def main() -> int:
  args = parse_args()
  if args.self_test:
    self_test()
    print("OK: Fishop hardware sample replay self-test passed")
    return 0

  state = FishopHardwareState()
  for payload in load_payloads(args):
    state.update_from_payload(payload, args.now)

  output = state.to_dict(args.now)
  print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
