#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROCS = ("controlsd", "plannerd", "radard", "locationd", "paramsd")
REQUIRED_FILES = (
  "selfdrive/test/process_replay/README.md",
  "selfdrive/test/process_replay/process_replay.py",
  "selfdrive/test/process_replay/test_processes.py",
  "selfdrive/test/process_replay/model_replay.py",
  "tools/replay/README.md",
  "tools/replay/main.cc",
  "tools/replay/replay.cc",
  "tools/replay/replay.h",
)


def py() -> str:
  return sys.executable


def split_csv(value: str) -> list[str]:
  return [part.strip() for part in value.split(",") if part.strip()]


def command_env() -> dict[str, str]:
  env = os.environ.copy()
  env.setdefault("GIT_TERMINAL_PROMPT", "0")
  env.setdefault("GIT_OPTIONAL_LOCKS", "0")
  return env


def run(cmd: Sequence[str], timeout_s: int) -> dict[str, Any]:
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=ROOT,
      env=command_env(),
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      check=False,
      timeout=timeout_s,
    )
    return {
      "command": list(cmd),
      "ok": proc.returncode == 0,
      "returnCode": proc.returncode,
      "output": proc.stdout.strip()[-3000:],
      "timeoutS": timeout_s,
    }
  except subprocess.TimeoutExpired as exc:
    output = ((exc.stdout or "") + (exc.stderr or "")).strip()
    return {
      "command": list(cmd),
      "ok": False,
      "returnCode": 124,
      "output": f"timed out after {timeout_s}s\n{output}".strip()[-3000:],
      "timeoutS": timeout_s,
    }
  except OSError as exc:
    return {"command": list(cmd), "ok": False, "returnCode": 127, "output": str(exc), "timeoutS": timeout_s}


def process_replay_command(procs: Sequence[str], cars: Sequence[str], update_refs: bool) -> list[str]:
  cmd = [py(), "selfdrive/test/process_replay/test_processes.py", "--whitelist-procs", ",".join(procs)]
  if cars:
    cmd.extend(["--whitelist-cars", ",".join(cars)])
  if update_refs:
    cmd.append("--update-refs")
  return cmd


def readiness_report() -> dict[str, Any]:
  file_checks = {path: (ROOT / path).exists() for path in REQUIRED_FILES}
  binary_checks = {
    "tools/replay/replay": (ROOT / "tools/replay/replay").exists(),
  }
  process_readme = (ROOT / "selfdrive/test/process_replay/README.md").read_text(encoding="utf-8", errors="replace")
  replay_readme = (ROOT / "tools/replay/README.md").read_text(encoding="utf-8", errors="replace")
  model_replay = (ROOT / "selfdrive/test/process_replay/model_replay.py").read_text(encoding="utf-8", errors="replace")
  token_checks = {
    "process_replay_api": "replay_process_with_name" in process_readme and "custom_params" in process_readme,
    "visionipc_model_note": "FrameReader" in process_readme and "modeld" in process_readme,
    "tools_replay_demo": "tools/replay/replay --demo" in replay_readme or "--demo" in replay_readme,
    "model_replay_outputs": "modelV2" in model_replay and "cameraOdometry" in model_replay,
  }
  return {
    "files": file_checks,
    "builtArtifacts": binary_checks,
    "tokens": token_checks,
    "ok": all(file_checks.values()) and all(token_checks.values()),
  }


def self_test() -> int:
  cmd = process_replay_command(DEFAULT_PROCS, ["HYUNDAI"], False)
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    "process_replay_command",
    "selfdrive/test/process_replay/test_processes.py",
    "tools/replay/replay",
    "tools/replay/main.cc",
    "model_replay.py",
    "FrameReader",
    "controlsd",
    "plannerd",
    "radard",
    "locationd",
    "paramsd",
  )
  if not all(token in text for token in required):
    print("FAIL Genius offline replay check self-test: missing token")
    return 1
  if "--update-refs" in cmd:
    print("FAIL Genius offline replay check self-test: update-refs should be opt-in")
    return 1
  if ",".join(DEFAULT_PROCS) not in cmd:
    print("FAIL Genius offline replay check self-test: default process list missing")
    return 1
  print("PASS Genius offline replay check self-test")
  return 0


def print_report(report: dict[str, Any], as_json: bool) -> None:
  if as_json:
    print(json.dumps(report, indent=2, sort_keys=True))
    return
  print(f"{'PASS' if report['ok'] else 'FAIL'} {report['title']}")
  for check, ok in report["readiness"]["files"].items():
    print(f"{'PASS' if ok else 'FAIL'} file {check}")
  for check, ok in report["readiness"]["builtArtifacts"].items():
    print(f"{'PASS' if ok else 'INFO'} built artifact {check}")
  for check, ok in report["readiness"]["tokens"].items():
    print(f"{'PASS' if ok else 'FAIL'} {check}")
  if report.get("processReplay"):
    run_report = report["processReplay"]
    print(f"{'PASS' if run_report['ok'] else 'FAIL'} process replay")
    if not run_report["ok"] and run_report.get("output"):
      print(run_report["output"])


def main() -> int:
  parser = argparse.ArgumentParser(description="Check or run Genius Pilot offline replay gates.")
  parser.add_argument("--procs", default=",".join(DEFAULT_PROCS), help="comma-separated process_replay proc names")
  parser.add_argument("--cars", default="", help="optional comma-separated process_replay car whitelist")
  parser.add_argument("--run-process-replay", action="store_true", help="run process_replay instead of readiness-only checks")
  parser.add_argument("--update-refs", action="store_true", help="pass --update-refs to process_replay; never enabled by default")
  parser.add_argument("--timeout", type=int, default=900, help="process replay timeout seconds")
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  procs = split_csv(args.procs) or list(DEFAULT_PROCS)
  cars = split_csv(args.cars)
  readiness = readiness_report()
  report: dict[str, Any] = {
    "title": "Genius Pilot Offline Replay Check",
    "ok": readiness["ok"],
    "readiness": readiness,
    "defaultProcesses": list(DEFAULT_PROCS),
    "requestedProcesses": procs,
    "requestedCars": cars,
    "processReplayCommand": process_replay_command(procs, cars, args.update_refs),
  }
  if args.run_process_replay:
    replay = run(report["processReplayCommand"], max(1, args.timeout))
    report["processReplay"] = replay
    report["ok"] = bool(report["ok"] and replay["ok"])
  else:
    report["skipped"] = "process_replay not run; pass --run-process-replay when route artifacts/network budget are available"

  print_report(report, args.json)
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
