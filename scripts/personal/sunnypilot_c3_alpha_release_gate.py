#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]


class StepResult(dict):
  def __init__(self, name: str, ok: bool, command: Sequence[str], output: str = "", timeout_s: int | None = None):
    super().__init__(
      name=name,
      ok=bool(ok),
      command=list(command),
      output=output[-2400:],
      timeoutS=timeout_s,
    )


def command_env() -> dict[str, str]:
  env = os.environ.copy()
  env.setdefault("GIT_TERMINAL_PROMPT", "0")
  env.setdefault("GIT_OPTIONAL_LOCKS", "0")
  return env


def run_step(name: str, cmd: Sequence[str], timeout_s: int) -> StepResult:
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
    return StepResult(name, proc.returncode == 0, cmd, proc.stdout.strip(), timeout_s)
  except subprocess.TimeoutExpired as exc:
    output = ((exc.stdout or "") + (exc.stderr or "")).strip()
    return StepResult(name, False, cmd, f"timed out after {timeout_s}s\n{output}".strip(), timeout_s)
  except OSError as exc:
    return StepResult(name, False, cmd, str(exc), timeout_s)


def py() -> str:
  return sys.executable


def build_steps(args: argparse.Namespace) -> list[tuple[str, list[str], int]]:
  scripts = [
    "scripts/personal/build_c3_qt_compat_installer.py",
    "scripts/personal/sunnypilot_c3_installer_audit.py",
    "scripts/personal/sunnypilot_c3_alpha_release_gate.py",
    "scripts/personal/sunnypilot_c3_compat_audit.py",
    "scripts/personal/sunnypilot_c3_alpha_evidence_check.py",
    "scripts/personal/sunnypilot_c3_alpha_snapshot.py",
    "scripts/personal/sunnypilot_c3_alpha_static_check.py",
    "scripts/personal/sunnypilot_c3_alpha_update_audit.py",
    "scripts/personal/sunnypilot_c3_device_collect.py",
    "scripts/personal/sunnypilot_c3_settings_conflict_audit.py",
    "scripts/personal/patch_tici_updater_wifi_manager.py",
    "scripts/personal/genius_visualization_contract.py",
    "scripts/personal/genius_settings_matrix.py",
    "scripts/personal/genius_curve_speed_contract.py",
  ]
  steps: list[tuple[str, list[str], int]] = [
    ("python compile personal gates", [py(), "-m", "py_compile", *scripts], 60),
    ("packed TICI updater Wi-Fi fallback", [py(), "scripts/personal/patch_tici_updater_wifi_manager.py", "--check"], 30),
    ("Genius visualization contract", [py(), "scripts/personal/genius_visualization_contract.py", "--self-test"], 30),
    ("installer audit self-test", [py(), "scripts/personal/sunnypilot_c3_installer_audit.py", "--self-test"], 30),
    (
      "C3/TICI compatibility audit",
      [
        py(),
        "scripts/personal/sunnypilot_c3_compat_audit.py",
        "--strict",
        "--skip-reference-refs",
        "--skip-git-metadata",
      ],
      120,
    ),
    ("alpha evidence checker self-test", [py(), "scripts/personal/sunnypilot_c3_alpha_evidence_check.py", "--self-test"], 30),
    ("alpha update audit self-test", [py(), "scripts/personal/sunnypilot_c3_alpha_update_audit.py", "--self-test"], 30),
    ("settings conflict audit", [py(), "scripts/personal/sunnypilot_c3_settings_conflict_audit.py", "--strict"], 60),
    ("Genius settings matrix", [py(), "scripts/personal/genius_settings_matrix.py", "--check"], 30),
    ("Genius curve-speed contract", [py(), "scripts/personal/genius_curve_speed_contract.py", "--self-test"], 30),
    ("C3 device collect self-test", [py(), "scripts/personal/sunnypilot_c3_device_collect.py", "--self-test"], 30),
  ]

  if not args.skip_online_installer:
    steps.append(("published /x installer audit", [py(), "scripts/personal/sunnypilot_c3_installer_audit.py"], 60))

  if args.snapshot:
    snapshot_cmd = [py(), "scripts/personal/sunnypilot_c3_alpha_evidence_check.py", str(args.snapshot)]
    for phase in args.phase:
      snapshot_cmd.extend(["--phase", phase])
    steps.append(("device snapshot evidence check", snapshot_cmd, 30))

  if args.fetch_references:
    steps.append((
      "upstream reference fetch/update audit",
      [py(), "scripts/personal/sunnypilot_c3_alpha_update_audit.py", "--fetch", "--strict", "--scan-risk-tokens"],
      900,
    ))

  if args.full:
    steps.append(("full alpha static check", [py(), "scripts/personal/sunnypilot_c3_alpha_static_check.py"], 360))

  return steps


def print_report(report: dict[str, object], as_json: bool) -> None:
  if as_json:
    print(json.dumps(report, indent=2, sort_keys=True))
    return
  print(f"{'PASS' if report['ok'] else 'FAIL'} {report['title']}")
  for step in report["steps"]:
    status = "PASS" if step["ok"] else "FAIL"
    print(f"{status} {step['name']}")
    if not step["ok"] and step.get("output"):
      print(step["output"])


def self_test() -> int:
  good = StepResult("synthetic pass", True, [py(), "-c", "pass"])
  bad = StepResult("synthetic fail", False, [py(), "-c", "raise SystemExit(1)"], "failed")
  report = {
    "title": "CarrotPilot-C3-ESCC Alpha Release Gate",
    "ok": good["ok"] and not bad["ok"],
    "steps": [good, bad],
  }
  if not report["ok"]:
    print_report(report, True)
    return 1
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Run the repeatable CarrotPilot-C3-ESCC alpha update and release gate.")
  parser.add_argument("--full", action="store_true", help="also run the full alpha static check")
  parser.add_argument("--skip-online-installer", action="store_true", help="skip the live GitHub Pages /x installer audit")
  parser.add_argument("--snapshot", type=Path, help="optional device snapshot JSON to validate")
  parser.add_argument("--fetch-references", action="store_true", help="fetch and compare configured upstream reference branches")
  parser.add_argument("--phase", action="append", default=["static"], help="snapshot evidence phase to validate")
  parser.add_argument("--json", action="store_true", help="print JSON report")
  parser.add_argument("--self-test", action="store_true", help="run the release gate's offline self-test")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  steps = [run_step(name, cmd, timeout_s) for name, cmd, timeout_s in build_steps(args)]
  report = {
    "title": "CarrotPilot-C3-ESCC Alpha Release Gate",
    "ok": all(step["ok"] for step in steps),
    "full": args.full,
    "snapshot": str(args.snapshot) if args.snapshot else "",
    "steps": steps,
  }
  print_report(report, args.json)
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
