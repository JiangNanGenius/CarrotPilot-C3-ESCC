#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class SnapshotTimedOut(TimeoutError):
  pass


def _shape_of(image) -> list[int]:
  shape = getattr(image, "shape", None)
  if shape is None:
    return []
  return [int(x) for x in shape]


def _run_with_timeout(timeout_s: int):
  from openpilot.system.camerad.snapshot import snapshot

  old_handler = signal.getsignal(signal.SIGALRM)

  def _raise_timeout(_signum, _frame):
    raise SnapshotTimedOut(f"camera snapshot timed out after {timeout_s}s")

  if timeout_s > 0:
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
  try:
    return snapshot()
  finally:
    if timeout_s > 0:
      signal.setitimer(signal.ITIMER_REAL, 0)
      signal.signal(signal.SIGALRM, old_handler)


def run_probe(output_dir: Path, timeout_s: int) -> dict[str, Any]:
  from openpilot.system.camerad.snapshot import jpeg_write

  output_dir.mkdir(parents=True, exist_ok=True)
  started_at = time.time()
  report: dict[str, Any] = {
    "title": "Genius Pilot C3 Camera Snapshot Probe",
    "ok": False,
    "silent": True,
    "usesUpstreamSnapshot": "openpilot.system.camerad.snapshot.snapshot",
    "outputDir": str(output_dir),
    "startedAt": started_at,
    "durationSec": 0.0,
    "images": {},
    "error": "",
  }
  try:
    rear, front = _run_with_timeout(timeout_s)
    if rear is not None:
      rear_path = output_dir / "back.jpg"
      jpeg_write(str(rear_path), rear)
      report["images"]["back"] = {"path": str(rear_path), "shape": _shape_of(rear)}
    if front is not None:
      front_path = output_dir / "front.jpg"
      jpeg_write(str(front_path), front)
      report["images"]["front"] = {"path": str(front_path), "shape": _shape_of(front)}
    report["ok"] = bool(report["images"])
    if not report["ok"]:
      report["error"] = "upstream snapshot returned no images; device may be onroad, already taking a snapshot, or camera startup failed"
  except Exception as exc:
    report["error"] = str(exc)
  finally:
    report["durationSec"] = round(time.time() - started_at, 3)

  return report


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    "Genius Pilot C3 Camera Snapshot Probe",
    "openpilot.system.camerad.snapshot",
    "snapshot()",
    "jpeg_write",
    "back.jpg",
    "front.jpg",
    "silent",
    "--require-image",
  )
  if not all(token in text for token in required):
    print("FAIL C3 camera snapshot probe self-test: missing token")
    return 1
  if _shape_of(type("FakeImage", (), {"shape": (1, 2, 3)})()) != [1, 2, 3]:
    print("FAIL C3 camera snapshot probe self-test: shape helper failed")
    return 1
  print("PASS C3 camera snapshot probe self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Capture C3 camera snapshots through the upstream camerad snapshot path.")
  parser.add_argument("--output-dir", type=Path, default=Path("/tmp/genius_camera_snapshot"), help="directory for back/front JPEGs and report")
  parser.add_argument("--timeout", type=int, default=25, help="overall snapshot timeout seconds")
  parser.add_argument("--require-image", action="store_true", help="exit non-zero if no camera image is captured")
  parser.add_argument("--pretty", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report = run_probe(args.output_dir, max(1, args.timeout))
  report_path = args.output_dir / "camera_snapshot_probe.json"
  report_path.write_text(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True), encoding="utf-8")
  print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
  return 0 if report["ok"] or not args.require_image else 1


if __name__ == "__main__":
  raise SystemExit(main())
