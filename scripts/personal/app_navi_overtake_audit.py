#!/usr/bin/env python3
import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]

FISHOP_REF_CANDIDATES = [
  "fishop/cp",
  "tracking/fishop-cp",
]
NAVIPILOT_REF_CANDIDATES = [
  "tracking/jixie-navipilot",
  "jixie-navipilot/CPdazi",
]

FISHOP_SOURCE_FILES = [
  "cereal/custom.capnp",
  "cereal/services.py",
  "system/manager/process_config.py",
  "selfdrive/carrot/amap_navi.py",
  "selfdrive/carrot/carrot_man.py",
  "selfdrive/carrot/carrot_serv.py",
  "selfdrive/carrot/config.py",
  "selfdrive/carrot/lane.py",
  "selfdrive/carrot/lidar_speed_test.py",
  "selfdrive/controls/lib/desire_helper.py",
  "selfdrive/controls/lib/dec/dec.py",
  "selfdrive/controls/lib/dec/longitudinal_planner.py",
  "selfdrive/controls/lib/longcontrol.py",
]

NAVIPILOT_SOURCE_FILES = [
  "app/src/main/java/com/example/navipilot/AutoOvertakeManager.kt",
  "app/src/main/java/com/example/navipilot/CarrotManNetworkClient.kt",
  "app/src/main/java/com/example/navipilot/CarrotManDataModels.kt",
  "app/src/main/java/com/example/navipilot/AmapBroadcastHandlers.kt",
]

GIT_TIMEOUT_S = 12.0


@dataclass
class Check:
  name: str
  ok: bool
  detail: str


def run_git(args: Sequence[str], timeout: float = GIT_TIMEOUT_S) -> Tuple[int, str]:
  env = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
  }
  cmd = [
    "git",
    "-c", "core.fsmonitor=false",
    "-c", "gc.auto=0",
    "-c", "maintenance.auto=false",
    *args,
  ]
  try:
    proc = subprocess.run(
      cmd,
      cwd=str(ROOT),
      env=env,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      timeout=timeout,
    )
  except subprocess.TimeoutExpired:
    return 124, f"git {' '.join(args)} timed out after {timeout:.0f}s"
  except OSError as exc:
    return 127, f"git unavailable: {exc}"
  return proc.returncode, proc.stdout.strip()

def ref_exists(ref: str) -> bool:
  code, _ = run_git(["rev-parse", "--verify", "--quiet", ref])
  return code == 0


def resolve_ref(candidates: Sequence[str], explicit: Optional[str], label: str) -> str:
  refs = [explicit] if explicit else candidates
  for ref in refs:
    if ref and ref_exists(ref):
      return ref
  raise RuntimeError(f"{label} source ref not found; fetch the tracking remote first")


def git_blob_exists(ref: str, path: str) -> bool:
  code, _ = run_git(["cat-file", "-e", f"{ref}:{path}"])
  return code == 0


def git_show(ref: str, path: str) -> str:
  code, output = run_git(["show", f"{ref}:{path}"])
  if code != 0:
    raise RuntimeError(f"cannot read {ref}:{path}: {output}")
  return output


def worktree_text(path: str) -> str:
  p = ROOT / path
  if not p.exists() or not p.is_file():
    return ""
  return p.read_text(encoding="utf-8", errors="replace")


def path_exists(path: str) -> bool:
  return (ROOT / path).exists()


def contains(text: str, needle: str) -> bool:
  return needle in text


def all_contains(text: str, needles: Sequence[str]) -> Tuple[bool, List[str]]:
  missing = [needle for needle in needles if needle not in text]
  return not missing, missing


def file_check(ref: str, files: Sequence[str]) -> Check:
  missing = [path for path in files if not git_blob_exists(ref, path)]
  return Check(
    "source files",
    not missing,
    "all expected files present" if not missing else "missing: " + ", ".join(missing),
  )


def check_fishop_source(ref: str) -> List[Check]:
  texts: Dict[str, str] = {path: git_show(ref, path) for path in FISHOP_SOURCE_FILES}
  checks = [file_check(ref, FISHOP_SOURCE_FILES)]

  ok, missing = all_contains(texts["selfdrive/carrot/amap_navi.py"], [
    "class AmapNaviServ",
    "PubMaster(['amapNavi'])",
    "broadcast_port = 4210",
    "listen_port = 4211",
    "navi_port = 7706",
    "navi_remote_port = 7705",
    "blinker_ctrl",
    "lidar_lblind",
    "remote_cmd",
  ])
  checks.append(Check(
    "fishop AmapNavi device service",
    ok,
    "UDP/app service, amapNavi publisher, external blinker, lidar blind, and remote command markers present" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["selfdrive/carrot/carrot_man.py"], [
    "AmapNaviServ",
    "get_data_amap_navi",
    "update_amap_navi",
    "carrotCmdIndex",
    "carrotCmd",
    "lidar_lblind",
  ])
  checks.append(Check(
    "fishop CarrotMan coupling",
    ok,
    "AmapNavi is coupled through carrot_man and CarrotMan command/blind fields" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["cereal/custom.capnp"], [
    "struct AmapNavi",
    "carrotCmdIndex",
    "carrotCmd",
    "extBlinker",
    "leftBlind",
    "rightBlind",
  ])
  checks.append(Check(
    "fishop cereal contract",
    ok,
    "custom schema carries AmapNavi, command, external blinker, and blind fields" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["cereal/services.py"], [
    '"carrotMan"',
    '"amapNavi"',
    '"navInstructionCarrot"',
  ])
  checks.append(Check(
    "fishop service registration",
    ok,
    "carrotMan, amapNavi, and navInstructionCarrot services present" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["selfdrive/controls/lib/desire_helper.py"], [
    'carrotMan.carrotCmd == "LANECHANGE"',
    'carrotMan.carrotCmd == "OVERTAKE"',
    "amapNavi",
    "leftBlind",
    "rightBlind",
    "ContinuousLaneChange",
  ])
  checks.append(Check(
    "fishop lane-change and overtake hook",
    ok,
    "desire_helper accepts APP lane/overtake commands and AmapNavi blind data" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["selfdrive/carrot/config.py"], [
    "StockBlinkerCtrl",
    "ExtBlinkerCtrlTest",
    "LidarBsdDelayTime",
    "ContinuousLaneChange",
  ])
  checks.append(Check(
    "fishop app hardware params",
    ok,
    "external blinker, lidar blind, and continuous lane-change params present" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["system/manager/process_config.py"], [
    'PythonProcess("carrot_man"',
    'PythonProcess("lane"',
    "#PythonProcess(\"amap_navi\"",
  ])
  checks.append(Check(
    "fishop manager wiring",
    ok,
    "carrot_man runs, lane stream is managed, and standalone amap_navi is commented" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["selfdrive/controls/lib/dec/dec.py"], [
    "class DynamicExperimentalController",
    "ExperimentalMode",
    "ModeTransitionManager",
  ])
  checks.append(Check(
    "fishop DEC source",
    ok,
    "DEC dynamic experimental controller markers present" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["selfdrive/controls/lib/longcontrol.py"], [
    "LongControl",
    "stopping",
    "starting",
  ])
  checks.append(Check(
    "fishop longcontrol source",
    ok,
    "longcontrol source is present for later separate diff review" if ok else "missing: " + ", ".join(missing),
  ))
  return checks


def check_navipilot_source(ref: str) -> List[Check]:
  texts: Dict[str, str] = {path: git_show(ref, path) for path in NAVIPILOT_SOURCE_FILES}
  checks = [file_check(ref, NAVIPILOT_SOURCE_FILES)]

  ok, missing = all_contains(texts["app/src/main/java/com/example/navipilot/AutoOvertakeManager.kt"], [
    "class AutoOvertakeManager",
    "overtake_mode",
    "MIN_TURN_DIST",
    "TBT_STOP_OVERTAKE_THRESHOLD",
    "sendLaneChangeCommand",
    'networkManager.sendControlCommand("LANECHANGE", direction)',
  ])
  checks.append(Check(
    "Navipilot APP automatic overtake manager",
    ok,
    "APP-side overtake state machine can send LANECHANGE commands to C3" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["app/src/main/java/com/example/navipilot/CarrotManNetworkClient.kt"], [
    "BROADCAST_PORT = 7705",
    "MAIN_DATA_PORT = 7706",
    "COMMAND_PORT = 7706",
    "build7706Payload",
    "carrotCmd",
  ])
  checks.append(Check(
    "Navipilot APP network command channel",
    ok,
    "APP uses 7705/7706 and carries carrotCmd in the command payload" if ok else "missing: " + ", ".join(missing),
  ))

  ok, missing = all_contains(texts["app/src/main/java/com/example/navipilot/AmapBroadcastHandlers.kt"], [
    "handleTurnInfo",
    "mapAmapIconToCarrotTurn",
    "nTBTTurnType",
    "nRoadLimitSpeed",
  ])
  checks.append(Check(
    "Navipilot AMap broadcast bridge",
    ok,
    "APP maps AMap/TBT data into CarrotMan fields" if ok else "missing: " + ", ".join(missing),
  ))
  return checks


def check_current_branch_boundary() -> List[Check]:
  checks: List[Check] = []

  forbidden_paths = [
    "selfdrive/carrot/amap_navi.py",
    "selfdrive/carrot/lane.py",
    "selfdrive/carrot/lidar_speed_test.py",
    "selfdrive/carrot/auto_overtake.py",
    "selfdrive/controls/lib/dec",
  ]
  present_paths = [path for path in forbidden_paths if path_exists(path)]
  checks.append(Check(
    "current high-risk source paths",
    not present_paths,
    "AmapNavi/lane/lidar/auto-overtake/DEC paths are absent" if not present_paths else "present: " + ", ".join(present_paths),
  ))

  markers = [
    ("common/params_keys.h", "StockBlinkerCtrl", "external blinker stock control param"),
    ("common/params_keys.h", "ExtBlinkerCtrlTest", "external blinker test param"),
    ("common/params_keys.h", "LidarBsdDelayTime", "lidar blind delay param"),
    ("selfdrive/carrot/carrot_man.py", "AmapNaviServ", "fishop AmapNavi import"),
    ("selfdrive/carrot/carrot_man.py", "amap_navi", "fishop AmapNavi module reference"),
    ("selfdrive/carrot/carrot_serv.py", "OVERTAKE", "OVERTAKE command parser"),
    ("selfdrive/controls/lib/desire_helper.py", "OVERTAKE", "OVERTAKE desire hook"),
    ("selfdrive/controls/lib/desire_helper.py", "amapNavi", "AmapNavi desire helper data path"),
    ("selfdrive/controls/lib/desire_lib/blinker_manager.py", "OVERTAKE", "OVERTAKE blinker manager hook"),
    ("selfdrive/controls/lib/longcontrol.py", "DynamicExperimentalController", "DEC longcontrol integration"),
    ("selfdrive/controls/lib/longitudinal_planner.py", "selfdrive.controls.lib.dec", "DEC longitudinal planner integration"),
    ("system/manager/process_config.py", "amap_navi", "amap_navi manager process"),
    ("system/manager/process_config.py", "selfdrive.carrot.lane", "fishop lane camera manager process"),
    ("system/manager/process_config.py", "auto_overtake", "auto_overtake manager process"),
  ]
  present_markers = []
  missing_files = []
  for relpath, needle, label in markers:
    text = worktree_text(relpath)
    if text == "" and not path_exists(relpath):
      missing_files.append(relpath)
    elif needle in text:
      present_markers.append(label)

  checks.append(Check(
    "current high-risk integration markers",
    not present_markers and not missing_files,
    "no fishop command AmapNavi, external blinker, lidar, OVERTAKE, or DEC markers in default C3 line" if not present_markers and not missing_files else (
      ("present: " + ", ".join(present_markers)) + ("; missing files: " + ", ".join(sorted(set(missing_files))) if missing_files else "")
    ),
  ))

  app_navi_status_ok = (
    "struct AmapNavi @0xaedffd8f31e7b55d" in worktree_text("cereal/custom.capnp")
    and "amapNavi @108 :Custom.AmapNavi" in worktree_text("cereal/log.capnp")
    and '"amapNavi": (True, 20., 5)' in worktree_text("cereal/services.py")
    and path_exists("selfdrive/carrot/app_navi_status.py")
    and 'PubMaster(["amapNavi"])' in worktree_text("selfdrive/carrot/app_navi_status.py")
    and 'SubMaster(["carState"])' in worktree_text("selfdrive/carrot/app_navi_status.py")
    and "carrotCmd" not in worktree_text("selfdrive/carrot/app_navi_status.py")
    and "OVERTAKE" not in worktree_text("selfdrive/carrot/app_navi_status.py")
    and "blinker_ctrl" not in worktree_text("selfdrive/carrot/app_navi_status.py")
    and "EnableAmapNaviStatus" in worktree_text("common/params_keys.h")
    and "enable_app_navi_status" in worktree_text("system/manager/process_config.py")
  )
  checks.append(Check(
    "current read-only AmapNavi status bridge",
    app_navi_status_ok,
    "default-off bridge publishes lane/blind status only; fishop command, external blinker, lidar, and OVERTAKE remain isolated",
  ))

  lanechange_ok = (
    'carrotMan.carrotCmd == "LANECHANGE"' in worktree_text("selfdrive/controls/lib/desire_helper.py")
    or 'carrotMan.carrotCmd == "LANECHANGE"' in worktree_text("selfdrive/controls/lib/desire_lib/blinker_manager.py")
  )
  checks.append(Check(
    "current CPdazi lane-change boundary",
    lanechange_ok,
    "LANECHANGE remains the existing CPdazi hook; OVERTAKE remains isolated",
  ))
  return checks


def print_checks(title: str, checks: Sequence[Check]) -> None:
  print(title)
  for check in checks:
    state = "PASS" if check.ok else "FAIL"
    print(f"[{state}] {check.name}: {check.detail}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit app navigation, external blinker, overtake, and DEC source/boundary.")
  parser.add_argument("--fishop-ref", help="git ref for fishop/openpilot source")
  parser.add_argument("--navipilot-ref", help="git ref for jixiexiaoge/navipilot source")
  parser.add_argument("--source-only", action="store_true", help="only check source contracts")
  parser.add_argument("--boundary-only", action="store_true", help="only check current branch boundary")
  args = parser.parse_args()

  failures = 0
  print("App navigation / overtake audit")
  print("repo:", ROOT)

  if not args.boundary_only:
    try:
      fishop_ref = resolve_ref(FISHOP_REF_CANDIDATES, args.fishop_ref, "fishop")
      code, fishop_sha = run_git(["rev-parse", "--short=12", fishop_ref])
      print(f"fishop source ref: {fishop_ref} @ {fishop_sha if code == 0 else 'unknown'}")
      fishop_checks = check_fishop_source(fishop_ref)
      print_checks("## fishop Source Contract", fishop_checks)
      failures += sum(1 for check in fishop_checks if not check.ok)
    except Exception as exc:
      failures += 1
      print("## fishop Source Contract")
      print(f"[FAIL] fishop source contract: {exc}")

    try:
      nav_ref = resolve_ref(NAVIPILOT_REF_CANDIDATES, args.navipilot_ref, "Navipilot")
      code, nav_sha = run_git(["rev-parse", "--short=12", nav_ref])
      print(f"Navipilot source ref: {nav_ref} @ {nav_sha if code == 0 else 'unknown'}")
      nav_checks = check_navipilot_source(nav_ref)
      print_checks("## Navipilot Source Contract", nav_checks)
      failures += sum(1 for check in nav_checks if not check.ok)
    except Exception as exc:
      failures += 1
      print("## Navipilot Source Contract")
      print(f"[FAIL] Navipilot source contract: {exc}")

  if not args.source_only:
    boundary_checks = check_current_branch_boundary()
    print_checks("## Current Branch Boundary", boundary_checks)
    failures += sum(1 for check in boundary_checks if not check.ok)

  if failures:
    print(f"FAILED: {failures} app navigation / overtake audit check(s)")
    return 2
  print("OK: app navigation / overtake audit passed")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
