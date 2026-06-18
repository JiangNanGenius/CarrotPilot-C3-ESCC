#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openpilot.selfdrive.carrot.fishop_hardware import FishopHardwareState  # noqa: E402


SAMPLE_PAYLOADS: list[dict[str, Any]] = [
  {"resp": "lane", "left_lane": 2, "right_lane": 1, "lineValid": True, "max_curve": 0.018, "lat_a": 0.21},
  {"device": "lidar", "resp": "blindspot", "detect_side": 3, "lidar_id": 0, "dist_time": 123456,
   "lidar_lblind": True, "lidar_car_lblind": True, "rf_drel": 4200, "rb_drel": -1800, "rf_xrel": 850, "rf_vrel": -1.2},
  {"device": "camera", "resp": "cam_blind", "detect_side": 1, "left_blind": True},
  {"device": "overtake", "index": 7, "cmd": "OVERTAKE", "arg": "left",
   "request": True, "direction": "left", "reason": "hardware sample only"},
]


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Normalize fishop hardware JSON payloads into a read-only evidence snapshot.")
  parser.add_argument("jsonl", nargs="?", help="JSON Lines file. Use '-' or omit to read stdin.")
  parser.add_argument("--sample", action="store_true", help="Use built-in sample payloads.")
  parser.add_argument("--now", type=float, default=1000.0, help="Synthetic timestamp for deterministic output.")
  parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
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


def main() -> int:
  args = parse_args()
  state = FishopHardwareState()
  for payload in load_payloads(args):
    state.update_from_payload(payload, args.now)

  output = state.to_dict(args.now)
  print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
