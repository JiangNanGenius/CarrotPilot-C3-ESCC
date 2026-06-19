#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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


def safe_python_command() -> list[str]:
  # Python 3.11+ safe-path mode keeps cwd/script directories from outranking
  # PYTHONPATH. This matters on macOS, where replay uses local native-extension
  # shadows ahead of the checked-in C3/Linux extension files.
  return [py(), "-P"] if sys.version_info >= (3, 11) else [py()]


def split_csv(value: str) -> list[str]:
  return [part.strip() for part in value.split(",") if part.strip()]


def command_env() -> dict[str, str]:
  env = os.environ.copy()
  env.setdefault("GIT_TERMINAL_PROMPT", "0")
  env.setdefault("GIT_OPTIONAL_LOCKS", "0")
  env.setdefault("CI", "1")
  existing_pythonpath = env.get("PYTHONPATH", "")
  env["PYTHONPATH"] = str(ROOT) if not existing_pythonpath else f"{existing_pythonpath}{os.pathsep}{ROOT}"
  return env


def output_text(*parts: object) -> str:
  chunks: list[str] = []
  for part in parts:
    if part is None:
      continue
    if isinstance(part, bytes):
      chunks.append(part.decode("utf-8", errors="replace"))
    else:
      chunks.append(str(part))
  return "".join(chunks)


def run(cmd: Sequence[str], timeout_s: int) -> dict[str, Any]:
  env = command_env()
  temp_params: tempfile.TemporaryDirectory[str] | None = None
  if not env.get("PARAMS_ROOT"):
    temp_params = tempfile.TemporaryDirectory(prefix="genius_process_replay_params_")
    env["PARAMS_ROOT"] = temp_params.name
  else:
    Path(env["PARAMS_ROOT"]).mkdir(parents=True, exist_ok=True)
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=ROOT,
      env=env,
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
      "output": proc.stdout.strip()[-8000:],
      "timeoutS": timeout_s,
    }
  except subprocess.TimeoutExpired as exc:
    output = output_text(exc.stdout, exc.stderr).strip()
    return {
      "command": list(cmd),
      "ok": False,
      "returnCode": 124,
      "output": f"timed out after {timeout_s}s\n{output}".strip()[-3000:],
      "timeoutS": timeout_s,
    }
  except OSError as exc:
    return {"command": list(cmd), "ok": False, "returnCode": 127, "output": str(exc), "timeoutS": timeout_s}
  finally:
    if temp_params is not None:
      temp_params.cleanup()


def process_replay_command(procs: Sequence[str], cars: Sequence[str], update_refs: bool, jobs: int | None = None) -> list[str]:
  cmd = [*safe_python_command(), "selfdrive/test/process_replay/test_processes.py", "--whitelist-procs", *procs]
  if cars:
    cmd.extend(["--whitelist-cars", *cars])
  if jobs is not None and jobs > 0:
    cmd.extend(["--jobs", str(jobs)])
  if update_refs:
    cmd.append("--update-refs")
  return cmd


def classify_process_replay_result(result: dict[str, Any]) -> dict[str, Any]:
  output = result.get("output", "")
  native_blocked = any(token in output for token in ("slice is not valid mach-o", "ImportError: dlopen", "acados_ocp_solver_pyx.so", "ekf_sym_pyx.so"))
  completed = "TEST SUCCEEDED" in output or "TEST FAILED" in output
  crashed = any(token in output for token in ("Traceback (most recent call last)", "\ncrash\n", "Segmentation fault", "ZeroDivisionError"))
  timed_out = result.get("returnCode") == 124
  reference_diffs = "TEST FAILED" in output and not crashed and not timed_out
  result["completed"] = completed
  result["crashFree"] = bool(completed and not crashed and not timed_out and not native_blocked)
  result["referenceDiffs"] = bool(reference_diffs)
  result["nativeExtensionBlocked"] = bool(native_blocked)
  return result


def import_smoke_command() -> list[str]:
  return [
    *safe_python_command(),
    "-c",
    "from openpilot.selfdrive.test.process_replay.process_replay import CONFIGS; "
    "print('process_replay_import_ok', len(CONFIGS))",
  ]


def readiness_report(import_timeout_s: int) -> dict[str, Any]:
  file_checks = {path: (ROOT / path).exists() for path in REQUIRED_FILES}
  binary_checks = {
    "tools/replay/replay": (ROOT / "tools/replay/replay").exists(),
  }
  runtime_checks = {
    "python_3_12_plus": sys.version_info >= (3, 12),
    "python_safe_path": sys.version_info >= (3, 11),
  }
  process_readme = (ROOT / "selfdrive/test/process_replay/README.md").read_text(encoding="utf-8", errors="replace")
  replay_readme = (ROOT / "tools/replay/README.md").read_text(encoding="utf-8", errors="replace")
  model_replay = (ROOT / "selfdrive/test/process_replay/model_replay.py").read_text(encoding="utf-8", errors="replace")
  import_smoke = run(import_smoke_command(), max(1, import_timeout_s))
  runtime_checks["process_replay_import"] = import_smoke["ok"]
  token_checks = {
    "process_replay_api": "replay_process_with_name" in process_readme and "custom_params" in process_readme,
    "visionipc_model_note": "FrameReader" in process_readme and "modeld" in process_readme,
    "tools_replay_demo": "tools/replay/replay --demo" in replay_readme or "--demo" in replay_readme,
    "model_replay_outputs": "modelV2" in model_replay and "cameraOdometry" in model_replay,
  }
  return {
    "files": file_checks,
    "builtArtifacts": binary_checks,
    "runtime": runtime_checks,
    "importSmoke": import_smoke,
    "tokens": token_checks,
    "ok": all(file_checks.values()) and all(token_checks.values()) and all(runtime_checks.values()),
  }


def self_test() -> int:
  cmd = process_replay_command(DEFAULT_PROCS, ["HYUNDAI"], False, jobs=1)
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    "process_replay_command",
    "import_smoke_command",
    "classify_process_replay_result",
    "crashFree",
    "referenceDiffs",
    "nativeExtensionBlocked",
    "safe_python_command",
    "-P",
    "selfdrive/test/process_replay/test_processes.py",
    "tools/replay/replay",
    "tools/replay/main.cc",
    "model_replay.py",
    "FrameReader",
    "PYTHONPATH",
    "PARAMS_ROOT",
    "python_3_12_plus",
    "process_replay_import",
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
  if ",".join(DEFAULT_PROCS) in cmd:
    print("FAIL Genius offline replay check self-test: upstream expects repeated proc args, not CSV")
    return 1
  if not all(proc in cmd for proc in DEFAULT_PROCS):
    print("FAIL Genius offline replay check self-test: default process list missing")
    return 1
  if "HYUNDAI" not in cmd or "--jobs" not in cmd:
    print("FAIL Genius offline replay check self-test: car/jobs args missing")
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
  for check, ok in report["readiness"]["runtime"].items():
    print(f"{'PASS' if ok else 'FAIL'} runtime {check}")
  for check, ok in report["readiness"]["tokens"].items():
    print(f"{'PASS' if ok else 'FAIL'} {check}")
  import_smoke = report["readiness"].get("importSmoke")
  if import_smoke and not import_smoke["ok"] and import_smoke.get("output"):
    print(import_smoke["output"])
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
  parser.add_argument("--jobs", type=int, default=1, help="process replay worker count; default keeps no-car smoke runs deterministic")
  parser.add_argument("--timeout", type=int, default=900, help="process replay timeout seconds")
  parser.add_argument("--import-timeout", type=int, default=45, help="process replay import smoke timeout seconds")
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  procs = split_csv(args.procs) or list(DEFAULT_PROCS)
  cars = split_csv(args.cars)
  readiness = readiness_report(args.import_timeout)
  report: dict[str, Any] = {
    "title": "Genius Pilot Offline Replay Check",
    "ok": readiness["ok"],
    "readiness": readiness,
    "defaultProcesses": list(DEFAULT_PROCS),
    "requestedProcesses": procs,
    "requestedCars": cars,
    "processReplayCommand": process_replay_command(procs, cars, args.update_refs, args.jobs),
  }
  if args.run_process_replay:
    replay = run(report["processReplayCommand"], max(1, args.timeout))
    report["processReplay"] = classify_process_replay_result(replay)
    report["ok"] = bool(report["ok"] and replay["ok"])
  else:
    report["skipped"] = "process_replay not run; pass --run-process-replay when route artifacts/network budget are available"

  print_report(report, args.json)
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
