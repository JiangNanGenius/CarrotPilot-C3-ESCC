#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[2]


class Report:
  def __init__(self) -> None:
    self.passed: List[str] = []
    self.warned: List[str] = []
    self.failed: List[str] = []

  def pass_(self, label: str) -> None:
    self.passed.append(label)

  def warn(self, label: str, detail: str = "") -> None:
    self.warned.append(label if not detail else f"{label}: {detail}")

  def fail(self, label: str, detail: str = "") -> None:
    self.failed.append(label if not detail else f"{label}: {detail}")

  def require(self, label: str, condition: bool, detail: str = "") -> None:
    if condition:
      self.pass_(label)
    else:
      self.fail(label, detail)


def path(path: str) -> Path:
  return ROOT / path


def read_text(relpath: str) -> str:
  return path(relpath).read_text(encoding="utf-8", errors="replace")


def exists(relpath: str) -> bool:
  return path(relpath).exists()


def contains(relpath: str, needle: str) -> bool:
  return needle in read_text(relpath)


def regex(relpath: str, pattern: str) -> bool:
  return re.search(pattern, read_text(relpath), re.S) is not None


def check_absent_files(report: Report) -> None:
  forbidden_paths = [
    "selfdrive/carrot/amap_navi.py",
    "selfdrive/carrot/lane.py",
    "selfdrive/carrot/lidar_speed_test.py",
    "selfdrive/carrot/auto_overtake.py",
    "selfdrive/carrot/web_interface.py",
    "selfdrive/carrot/xiaoge_web.py",
    "selfdrive/carrot/xiaoge_sentryd.py",
    "selfdrive/controls/lib/dec",
    "amap_navi.py",
    "web_interface.py",
    "xiaoge_web.py",
    "xiaoge_sentryd.py",
  ]
  for relpath in forbidden_paths:
    report.require(
      f"forbidden default-branch module absent: {relpath}",
      not exists(relpath),
      "keep this feature in an experimental branch until it has its own switch and road-test plan",
    )


def check_absent_patterns(report: Report) -> None:
  forbidden_patterns: List[Tuple[str, str, str]] = [
    ("selfdrive/controls/lib/desire_helper.py", "OVERTAKE", "automatic overtake command not wired into desire helper"),
    ("selfdrive/controls/lib/desire_helper.py", "amapNavi", "fishop AmapNavi blind data not wired into desire helper"),
    ("selfdrive/controls/lib/desire_helper.py", "blinker_ctrl", "APP external blinker control not wired into desire helper"),
    ("selfdrive/controls/lib/desire_lib/blinker_manager.py", "OVERTAKE", "automatic overtake command not wired into blinker manager"),
    ("selfdrive/carrot/carrot_man.py", "AmapNaviServ", "fishop AmapNavi service not imported by CarrotMan"),
    ("selfdrive/carrot/carrot_man.py", "amap_navi", "fishop AmapNavi module not referenced by CarrotMan"),
    ("selfdrive/carrot/carrot_man.py", "web_interface", "legacy web_interface not referenced by CarrotMan"),
    ("selfdrive/carrot/carrot_man.py", "WebInterface", "legacy WebInterface not referenced by CarrotMan"),
    ("selfdrive/carrot/carrot_serv.py", "OVERTAKE", "automatic overtake command not parsed by carrot_serv"),
    ("common/params_keys.h", "StockBlinkerCtrl", "external blinker stock-control param not present by default"),
    ("common/params_keys.h", "ExtBlinkerCtrlTest", "external blinker test param not present by default"),
    ("common/params_keys.h", "LidarBsdDelayTime", "lidar blind-spot tuning params not present by default"),
    ("cereal/custom.capnp", "struct AmapNavi", "fishop AmapNavi schema not present by default"),
    ("cereal/services.py", '"amapNavi"', "fishop AmapNavi service not registered by default"),
    ("selfdrive/controls/lib/longcontrol.py", "DynamicExperimentalController", "fishop DEC not wired into longcontrol by default"),
    ("selfdrive/controls/lib/longitudinal_planner.py", "selfdrive.controls.lib.dec", "fishop DEC not wired into longitudinal planner by default"),
    ("system/manager/process_config.py", "amap_navi", "fishop AmapNavi service not managed by default"),
    ("system/manager/process_config.py", "AmapNaviServ", "fishop AmapNavi class not managed by default"),
    ("system/manager/process_config.py", "selfdrive.carrot.lane", "fishop lane camera stream not managed by default"),
    ("system/manager/process_config.py", "auto_overtake", "fishop auto_overtake process not managed by default"),
    ("system/manager/process_config.py", "web_interface", "legacy web_interface service not managed by default"),
    ("system/manager/process_config.py", "WebInterface", "legacy WebInterface service not managed by default"),
    ("system/manager/process_config.py", "xiaoge_web", "standalone xiaoge web service not managed by default"),
    ("system/manager/process_config.py", "xiaoge_sentryd", "standalone xiaoge sentry service not managed by default"),
  ]
  for relpath, needle, label in forbidden_patterns:
    if not exists(relpath):
      report.fail(label, f"missing expected file {relpath}; cannot prove boundary")
      continue
    report.require(
      label,
      not contains(relpath, needle),
      f"found {needle!r} in {relpath}; move behind a separate gate or experimental branch",
    )


def check_required_web_features(report: Report) -> None:
  required_files = [
    "selfdrive/carrot/server/features/dashcam/routes.py",
    "selfdrive/carrot/server/features/screenrecord/routes.py",
    "selfdrive/carrot/server/features/tools/routes.py",
    "selfdrive/carrot/server/features/carrot_learning.py",
  ]
  for relpath in required_files:
    report.require(f"7000 Web feature file present: {relpath}", exists(relpath), "expected current C3 web feature")

  report.require(
    "carrot_server default port is 7000",
    regex("selfdrive/carrot/carrot_server.py", r'parser\.add_argument\("--port".*?default=7000'),
    "the personal docs and cweb_push assume port 7000",
  )
  report.require(
    "manager starts carrot_server as always-run local console",
    regex("system/manager/process_config.py", r'PythonProcess\("carrot_server",\s*"selfdrive\.carrot\.carrot_server",\s*always_run\)'),
    "carrot_server should stay available for local device diagnostics",
  )
  report.require(
    "cweb_push remains device-only",
    regex("system/manager/process_config.py", r'PythonProcess\("cweb_push",\s*"selfdrive\.carrot\.cweb_push",\s*always_run,\s*enabled=not PC\)'),
    "avoid running cweb_push in PC-only smoke environments",
  )


def check_gated_existing_features(report: Report) -> None:
  process_config = "system/manager/process_config.py"
  report.require(
    "cluster HUD process is gated",
    regex(process_config, r'PythonProcess\("carrot_cluster",\s*"selfdrive\.carrot\.cluster_autorun",\s*enable_cluster_hud\)'),
    "cluster HUD must not run unconditionally",
  )
  report.require(
    "cluster HUD gate reads ClusterHud",
    regex(process_config, r"def enable_cluster_hud\(.*?ClusterHud"),
    "ClusterHud param should remain the only default manager gate",
  )
  report.require(
    "xiaoge data broadcaster is gated",
    regex(process_config, r'PythonProcess\("xiaoge_data",\s*"selfdrive\.carrot\.xiaoge_data",\s*enable_xiaoge_data\)'),
    "ShareData feature must not run unconditionally",
  )
  report.require(
    "xiaoge data gate reads ShareData",
    regex(process_config, r"def enable_xiaoge_data\(.*?ShareData"),
    "ShareData param should remain the only default manager gate",
  )

  if exists("selfdrive/carrot/cluster"):
    report.warn("cluster HUD code present", "current manager gate is required; real device validation is still separate")
  if exists("selfdrive/carrot/xiaoge_data.py"):
    report.warn("ShareData broadcaster present", "keep default off unless the user explicitly enables sharing")


def manual_items() -> List[str]:
  return [
    "Treat 7000 Web, cluster HUD, and ShareData as existing gated features, not proof of real device validation.",
    "Keep OVERTAKE, AmapNavi device service, external blinker control, lidar blind paths, DEC/longcontrol rewrites, and standalone sentry/web services out of the main branch until each has its own switch and test plan.",
    "If a future upstream update adds any blocked feature intentionally, update this check in the same commit that adds the safety gate and documentation.",
  ]


def print_report(report: Report, show_manual: bool) -> None:
  print("Personal feature boundary check")
  print("repo:", ROOT)
  for label in report.passed:
    print("[PASS]", label)
  for label in report.warned:
    print("[WARN]", label)
  for label in report.failed:
    print("[FAIL]", label)
  if show_manual:
    print("Manual checks still required:")
    for item in manual_items():
      print("[TODO]", item)
  if report.failed:
    print("FAILED: %d check(s)" % len(report.failed))
  else:
    print("OK: feature boundary check passed")


def main() -> int:
  parser = argparse.ArgumentParser(description="Static feature-boundary guard for the personal main branch.")
  parser.add_argument("--no-manual", action="store_true", help="Do not print manual follow-up items.")
  args = parser.parse_args()

  report = Report()
  check_absent_files(report)
  check_absent_patterns(report)
  check_required_web_features(report)
  check_gated_existing_features(report)
  print_report(report, show_manual=not args.no_manual)
  return 1 if report.failed else 0


if __name__ == "__main__":
  raise SystemExit(main())
