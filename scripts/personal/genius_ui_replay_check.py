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
DEFAULT_UI_VARIANT = "tizi"
REQUIRED_FILES = (
  "tools/replay/README.md",
  "tools/replay/main.cc",
  "tools/replay/replay.cc",
  "tools/replay/replay.h",
  "selfdrive/ui/tests/diff/replay.py",
  "selfdrive/ui/tests/diff/replay_script.py",
  "selfdrive/ui/tests/diff/diff.py",
  "selfdrive/ui/tests/diff/diff_template.html",
  "selfdrive/ui/onroad/model_renderer.py",
  "selfdrive/ui/onroad/carrot_world_overlay.py",
  "selfdrive/ui/onroad/fishop_overlay.py",
  "selfdrive/ui/translations/app_zh-CHS.po",
  "selfdrive/ui/translations/app_zh-CHT.po",
)


def py() -> str:
  return sys.executable


def command_env() -> dict[str, str]:
  env = os.environ.copy()
  env.setdefault("GIT_TERMINAL_PROMPT", "0")
  env.setdefault("GIT_OPTIONAL_LOCKS", "0")
  env.setdefault("CI", "1")
  return env


def run(cmd: Sequence[str], timeout_s: int, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
  env = command_env()
  if extra_env:
    env.update(extra_env)
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


def ui_replay_command(variant: str) -> list[str]:
  cmd = [py(), "selfdrive/ui/tests/diff/replay.py"]
  if variant == "tizi":
    cmd.append("--big")
  return cmd


def tools_replay_demo_command(no_vipc: bool) -> list[str]:
  cmd = ["tools/replay/replay", "--demo", "--no-loop"]
  if no_vipc:
    cmd.append("--no-vipc")
  return cmd


def readiness_report() -> dict[str, Any]:
  files = {path: (ROOT / path).exists() for path in REQUIRED_FILES}
  built_artifacts = {
    "tools/replay/replay": (ROOT / "tools/replay/replay").exists(),
  }
  replay_readme = (ROOT / "tools/replay/README.md").read_text(encoding="utf-8", errors="replace")
  replay_script = (ROOT / "selfdrive/ui/tests/diff/replay_script.py").read_text(encoding="utf-8", errors="replace")
  model_renderer = (ROOT / "selfdrive/ui/onroad/model_renderer.py").read_text(encoding="utf-8", errors="replace")
  carrot_world_overlay = (ROOT / "selfdrive/ui/onroad/carrot_world_overlay.py").read_text(encoding="utf-8", errors="replace")
  fishop_overlay = (ROOT / "selfdrive/ui/onroad/fishop_overlay.py").read_text(encoding="utf-8", errors="replace")
  zh_chs = (ROOT / "selfdrive/ui/translations/app_zh-CHS.po").read_text(encoding="utf-8", errors="replace")
  token_checks = {
    "tools_replay_demo_command": "tools/replay/replay --demo" in replay_readme or "--demo" in replay_readme,
    "ui_diff_replay_big_layout": "build_tizi_script" in replay_script and "--big" in (ROOT / "selfdrive/ui/tests/diff/replay.py").read_text(encoding="utf-8", errors="replace"),
    "settings_replay_script": "Settings - Network" in replay_script and "Settings - Software" in replay_script and "Settings - Developer" in replay_script,
    "visual_modes_rendered": "genius_visual_mode" in model_renderer and "genius_lane_line_style" in model_renderer and "genius_lead_radar_visual_mode" in model_renderer,
    "carrot_world_overlay": "CarrotWorldOverlay" in carrot_world_overlay and "never writes params" in carrot_world_overlay,
    "fishop_overlay": "FishopVisualOverlay" in fishop_overlay and "normalize_fishop_payloads" in fishop_overlay,
    "chinese_sidebar_text": "msgid \"PHONE\"" in zh_chs and "msgid \"GPS\"" in zh_chs and "msgid \"NO FIX\"" in zh_chs,
  }
  return {
    "files": files,
    "builtArtifacts": built_artifacts,
    "tokens": token_checks,
    "ok": all(files.values()) and all(token_checks.values()),
  }


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    "Genius Pilot UI Replay Check",
    "tools/replay/replay",
    "--demo",
    "selfdrive/ui/tests/diff/replay.py",
    "replay_script.py",
    "GeniusVisualMode",
    "GeniusFishopVisualOverlay",
    "app_zh-CHS.po",
    "--run-ui-replay",
    "--run-tools-replay-demo",
  )
  if not all(token in text for token in required):
    print("FAIL Genius UI replay check self-test: missing token")
    return 1
  if "--demo" not in tools_replay_demo_command(no_vipc=True):
    print("FAIL Genius UI replay check self-test: demo command missing")
    return 1
  if "--big" not in ui_replay_command("tizi"):
    print("FAIL Genius UI replay check self-test: tizi replay command missing --big")
    return 1
  print("PASS Genius UI replay check self-test")
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
  for key in ("uiReplay", "toolsReplayDemo"):
    if key in report:
      run_report = report[key]
      print(f"{'PASS' if run_report['ok'] else 'FAIL'} {key}")
      if not run_report["ok"] and run_report.get("output"):
        print(run_report["output"])


def main() -> int:
  parser = argparse.ArgumentParser(description="Check or run Genius Pilot no-car UI replay diagnostics.")
  parser.add_argument("--variant", choices=("tizi", "mici"), default=DEFAULT_UI_VARIANT, help="UI layout variant for diff replay")
  parser.add_argument("--run-ui-replay", action="store_true", help="run selfdrive/ui/tests/diff/replay.py and record a UI replay video")
  parser.add_argument("--run-tools-replay-demo", action="store_true", help="run tools/replay/replay --demo briefly; requires built replay binary")
  parser.add_argument("--tools-replay-timeout", type=int, default=20, help="seconds for tools/replay demo smoke run")
  parser.add_argument("--ui-replay-timeout", type=int, default=240, help="seconds for UI diff replay")
  parser.add_argument("--no-vipc", action="store_true", default=True, help="pass --no-vipc to tools/replay demo smoke run")
  parser.add_argument("--record-output", default="genius_tizi_ui_replay.mp4", help="UI replay output filename under selfdrive/ui/tests/diff/report")
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  readiness = readiness_report()
  report: dict[str, Any] = {
    "title": "Genius Pilot UI Replay Check",
    "ok": readiness["ok"],
    "readiness": readiness,
    "uiReplayCommand": ui_replay_command(args.variant),
    "toolsReplayDemoCommand": tools_replay_demo_command(args.no_vipc),
  }
  if args.run_ui_replay:
    report["uiReplay"] = run(
      report["uiReplayCommand"],
      max(1, args.ui_replay_timeout),
      {"RECORD_OUTPUT": args.record_output},
    )
    report["ok"] = bool(report["ok"] and report["uiReplay"]["ok"])
  else:
    report["uiReplaySkipped"] = "pass --run-ui-replay to generate the deterministic UI replay video"

  if args.run_tools_replay_demo:
    report["toolsReplayDemo"] = run(report["toolsReplayDemoCommand"], max(1, args.tools_replay_timeout))
    report["ok"] = bool(report["ok"] and report["toolsReplayDemo"]["ok"])
  else:
    report["toolsReplayDemoSkipped"] = "pass --run-tools-replay-demo after tools/replay/replay is built"

  print_report(report, args.json)
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
