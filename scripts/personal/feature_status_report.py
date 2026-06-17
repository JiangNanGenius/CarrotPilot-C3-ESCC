#!/usr/bin/env python3
import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class FeatureStatus:
  name: str
  state: str
  detail: str
  required: bool = False
  ok: bool = True


def path(relpath: str) -> Path:
  return ROOT / relpath


def exists(relpath: str) -> bool:
  return path(relpath).exists()


def read_text(relpath: str) -> str:
  return path(relpath).read_text(encoding="utf-8", errors="replace")


def contains(relpath: str, needle: str) -> bool:
  return exists(relpath) and needle in read_text(relpath)


def regex(relpath: str, pattern: str) -> bool:
  return exists(relpath) and re.search(pattern, read_text(relpath), re.S) is not None


def present(name: str, detail: str, condition: bool, required: bool = True) -> FeatureStatus:
  return FeatureStatus(name, "READY_STATIC" if condition else "MISSING", detail, required=required, ok=condition or not required)


def gated(name: str, detail: str, condition: bool, required: bool = True) -> FeatureStatus:
  return FeatureStatus(name, "GATED" if condition else "MISSING_GATE", detail, required=required, ok=condition or not required)


def pending(name: str, detail: str) -> FeatureStatus:
  return FeatureStatus(name, "PENDING", detail, required=False, ok=True)


def isolated(name: str, detail: str, absent: bool) -> FeatureStatus:
  return FeatureStatus(name, "ISOLATED" if absent else "UNGUARDED_PRESENT", detail, required=True, ok=absent)


def check_web_console() -> FeatureStatus:
  required = [
    regex("selfdrive/carrot/carrot_server.py", r'parser\.add_argument\("--port".*?default=7000'),
    contains("selfdrive/carrot/server/features/__init__.py", "dashcam.register(app)"),
    contains("selfdrive/carrot/server/features/__init__.py", "screenrecord.register(app)"),
    contains("selfdrive/carrot/server/features/__init__.py", "tools.register(app)"),
    contains("selfdrive/carrot/server/features/__init__.py", "terminal.register(app)"),
    contains("selfdrive/carrot/server/features/__init__.py", "vision_diag.register(app)"),
    exists("selfdrive/carrot/web/index.html"),
  ]
  return present("7000 Web console", "port 7000 plus dashcam/screenrecord/tools/terminal/vision diagnostics", all(required))


def check_experimental_toggle() -> FeatureStatus:
  condition = (
    contains("selfdrive/carrot/web/js/pages/setting_device_config.js", "ExperimentalMode")
    and contains("selfdrive/carrot/server/features/system.py", "ExperimentalModeConfirmed")
  )
  return present("Experimental mode Web toggle", "device Web settings expose the existing ExperimentalMode parameter", condition)


def check_auto_tuner() -> FeatureStatus:
  condition = (
    exists("selfdrive/carrot/carrot_learning.py")
    and exists("selfdrive/carrot/server/features/carrot_learning.py")
    and contains("selfdrive/carrot_settings.json", "CarrotLearningActive")
    and contains("selfdrive/carrot_settings.json", "CarrotLearningAutoApply")
  )
  return present("Auto-Tuner manual flow", "learner, Web API, and default-off settings are present", condition)


def check_cplink() -> FeatureStatus:
  condition = (
    contains("cereal/custom.capnp", "struct CarrotMan")
    and contains("cereal/services.py", '"carrotMan"')
    and contains("selfdrive/carrot/carrot_man.py", "carrot_man_port = 7706")
    and contains("selfdrive/carrot/carrot_serv.py", '"nRoadLimitSpeed"')
    and contains("selfdrive/controls/lib/desire_helper.py", 'carrotCmd == "LANECHANGE"')
  )
  return present("CP搭子 / Navipilot core protocol", "CarrotMan, UDP 7705/7706, nav fields, and LANECHANGE hook", condition)


def check_cluster_hud() -> FeatureStatus:
  condition = (
    exists("selfdrive/carrot/cluster")
    and regex("system/manager/process_config.py", r'PythonProcess\("carrot_cluster",\s*"selfdrive\.carrot\.cluster_autorun",\s*enable_cluster_hud\)')
    and regex("system/manager/process_config.py", r"def enable_cluster_hud\(.*?ClusterHud")
  )
  return gated("cluster HUD / USB display", "code is present and manager startup is gated by ClusterHud", condition)


def check_share_data() -> FeatureStatus:
  condition = (
    exists("selfdrive/carrot/xiaoge_data.py")
    and regex("system/manager/process_config.py", r'PythonProcess\("xiaoge_data",\s*"selfdrive\.carrot\.xiaoge_data",\s*enable_xiaoge_data\)')
    and regex("system/manager/process_config.py", r"def enable_xiaoge_data\(.*?ShareData")
  )
  return gated("Xiaoge data broadcaster", "xiaoge_data exists and is gated by ShareData", condition)


def check_driving_report() -> FeatureStatus:
  candidates = [
    "selfdrive/carrot/server/features/driving_report.py",
    "selfdrive/carrot/server/features/drive_report.py",
    "selfdrive/carrot/web/js/pages/report.js",
  ]
  if any(exists(candidate) for candidate in candidates):
    return FeatureStatus("Driving report", "READY_STATIC", "a dedicated driving report module exists", required=False, ok=True)
  return pending("Driving report", "no dedicated driving report module yet; dashcam route browser is present but is not the same feature")


def check_model_selector() -> FeatureStatus:
  patterns = [
    ("selfdrive/carrot/web/js/pages/setting_device_config.js", "ModelSelector"),
    ("system/manager/process_config.py", "ModelSelector"),
    ("selfdrive/modeld/modeld.py", "ModelSelector"),
  ]
  if any(contains(relpath, needle) for relpath, needle in patterns):
    return FeatureStatus("Model selector", "READY_STATIC", "model selector references are present", required=False, ok=True)
  return pending("Model selector", "not integrated; keep as a separate high-risk modeld/UI batch")


def check_isolated_high_risk() -> List[FeatureStatus]:
  overtake_absent = (
    not contains("selfdrive/controls/lib/desire_helper.py", "OVERTAKE")
    and not contains("selfdrive/controls/lib/desire_lib/blinker_manager.py", "OVERTAKE")
    and not contains("selfdrive/carrot/carrot_serv.py", "OVERTAKE")
  )
  amap_absent = (
    not exists("selfdrive/carrot/amap_navi.py")
    and not contains("system/manager/process_config.py", "amap_navi")
    and not contains("selfdrive/carrot/carrot_man.py", "amap_navi")
  )
  sentry_absent = (
    not exists("selfdrive/carrot/xiaoge_web.py")
    and not exists("selfdrive/carrot/xiaoge_sentryd.py")
    and not contains("system/manager/process_config.py", "xiaoge_sentryd")
  )
  return [
    isolated("Automatic OVERTAKE command", "not integrated until it has its own safety gate and road-test plan", overtake_absent),
    isolated("fishop AmapNavi device service", "kept out of the main line because CP搭子 overlaps it", amap_absent),
    isolated("standalone Xiaoge web/sentry services", "kept out of the main line because they need separate security review", sentry_absent),
  ]


def build_statuses() -> List[FeatureStatus]:
  return [
    check_web_console(),
    check_experimental_toggle(),
    check_auto_tuner(),
    check_cplink(),
    check_cluster_hud(),
    check_share_data(),
    check_driving_report(),
    check_model_selector(),
    *check_isolated_high_risk(),
  ]


def print_report(statuses: List[FeatureStatus]) -> None:
  print("Personal feature status report")
  print("repo:", ROOT)
  for status in statuses:
    marker = "PASS" if status.ok else "FAIL"
    print(f"[{marker}] {status.name}: {status.state} - {status.detail}")
  missing = [status.name for status in statuses if status.required and not status.ok]
  if missing:
    print("FAILED: required feature status changed unexpectedly: " + ", ".join(missing))
  else:
    print("OK: feature status report completed")


def main() -> int:
  parser = argparse.ArgumentParser(description="Report current personal feature integration status.")
  parser.add_argument("--strict", action="store_true", help="fail when required static/gated/isolated status is not satisfied")
  args = parser.parse_args()

  statuses = build_statuses()
  print_report(statuses)
  if args.strict and any(status.required and not status.ok for status in statuses):
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
