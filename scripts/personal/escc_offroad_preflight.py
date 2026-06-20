#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
GIT_TIMEOUT_S = 12.0
FORBIDDEN_LEGACY_PARAMS = (
  "Always" + "Offline",
  "device_go" + "_off_road",
)


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

  def require_contains(self, label: str, path: str, needle: str) -> None:
    text = read_text(path)
    self.require(label, needle in text, f"missing {needle!r} in {path}")

  def require_not_contains(self, label: str, path: str, needle: str) -> None:
    text = read_text(path)
    self.require(label, needle not in text, f"unexpected {needle!r} in {path}")

  def require_regex(self, label: str, path: str, pattern: str) -> None:
    text = read_text(path)
    self.require(label, re.search(pattern, text, re.S) is not None, f"missing pattern {pattern!r} in {path}")


def read_text(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8")


def run_git(args: List[str]) -> Tuple[int, str]:
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
      timeout=GIT_TIMEOUT_S,
    )
  except subprocess.TimeoutExpired:
    return 124, f"git {' '.join(args)} timed out after {GIT_TIMEOUT_S:.0f}s"
  except OSError as exc:
    return 127, f"git unavailable: {exc}"
  return proc.returncode, proc.stdout.strip()


def git_ref_exists(ref: str) -> bool:
  code, _ = run_git(["rev-parse", "--verify", "--quiet", ref])
  return code == 0


def git_is_ancestor(ancestor: str, descendant: str) -> bool:
  code, _ = run_git(["merge-base", "--is-ancestor", ancestor, descendant])
  return code == 0


def parse_params_keys() -> Dict[str, Tuple[str, str, Optional[str]]]:
  text = read_text("common/params_keys.h")
  params: Dict[str, Tuple[str, str, Optional[str]]] = {}
  pattern = re.compile(r'\{"(?P<name>[^"]+)", \{(?P<body>[^}]*)\}\}')
  for match in pattern.finditer(text):
    body_parts = [part.strip() for part in match.group("body").split(",")]
    flags = body_parts[0] if body_parts else ""
    typ = body_parts[1] if len(body_parts) > 1 else ""
    default = None
    if len(body_parts) > 2:
      default = body_parts[2].strip().strip('"')
    params[match.group("name")] = (flags, typ, default)
  return params


def expect_param(report: Report, params: Dict[str, Tuple[str, str, Optional[str]]], name: str,
                 typ: str, default: Optional[str] = None, required_flag: str = "PERSISTENT") -> None:
  item = params.get(name)
  report.require(f"param key exists: {name}", item is not None)
  if item is None:
    return

  flags, actual_type, actual_default = item
  report.require(f"param key flag: {name}", required_flag in flags, f"got {flags!r}")
  report.require(f"param key type: {name}", actual_type == typ, f"got {actual_type!r}")
  if default is not None:
    report.require(f"param key default: {name}", actual_default == default, f"got {actual_default!r}")


def settings_by_name() -> Dict[str, Dict[str, Any]]:
  data = json.loads(read_text("selfdrive/carrot_settings.json"))
  return {item["name"]: item for item in data.get("params", []) if item.get("name")}


def expect_setting(report: Report, settings: Dict[str, Dict[str, Any]], name: str, default: Any) -> None:
  item = settings.get(name)
  report.require(f"settings entry exists: {name}", item is not None)
  if item is None:
    return
  report.require(f"settings default: {name}", item.get("default") == default, f"got {item.get('default')!r}")


def dbc_message_block(text: str, message_name: str) -> str:
  match = re.search(rf"^BO_ \d+ {re.escape(message_name)}:.*?(?=^BO_ |\Z)", text, re.M | re.S)
  return "" if match is None else match.group(0)


def capnp_field_count(path: str, field: str) -> int:
  return sum(1 for line in read_text(path).splitlines() if field in line)


def check_git_context(report: Report) -> None:
  code, branch = run_git(["branch", "--show-current"])
  report.require("git current branch is readable", code == 0 and bool(branch), branch)
  if branch:
    report.pass_(f"git current branch: {branch}")

  if git_ref_exists("origin/c3-wip"):
    if git_is_ancestor("origin/c3-wip", "HEAD"):
      report.pass_("HEAD contains latest fetched origin/c3-wip")
    else:
      report.warn("HEAD does not contain latest fetched origin/c3-wip", "review upstream before release tagging")
  else:
    report.warn("origin/c3-wip not found", "fetch upstream before release tagging")

  if git_ref_exists("personal/c3-escc"):
    if git_is_ancestor("personal/c3-escc", "HEAD"):
      report.pass_("current branch contains personal/c3-escc protection line")
    else:
      report.warn("current branch does not contain personal/c3-escc protection line", "review protection branch ancestry before release tagging")
  else:
    report.warn("personal/c3-escc not found", "cannot confirm protection branch ancestry")


def check_params_and_settings(report: Report) -> None:
  params = parse_params_keys()
  for name, typ, default in [
    ("AlwaysOffroad", "BOOL", "0"),
    ("EnableConnect", "INT", "0"),
    ("SoftwareMenu", "INT", "1"),
    ("EnableEscc", "INT", "0"),
    ("HyundaiCameraSCC", "INT", "0"),
    ("CanfdHDA2", "INT", "0"),
    ("EnableRadarTracks", "INT", "0"),
    ("RadarLatFactor", "INT", "0"),
    ("EnableCornerRadar", "INT", "0"),
    ("AutoGasCancelSpeed", "INT", "30"),
    ("CarrotLearningActive", "INT", "0"),
    ("CarrotLearningAutoApply", "BOOL", "0"),
  ]:
    expect_param(report, params, name, typ, default)

  expect_param(report, params, "EnableRadarTracksResult", "INT", required_flag="CLEAR_ON_MANAGER_START")

  settings = settings_by_name()
  for name, default in [
    ("AlwaysOffroad", 0),
    ("EnableConnect", 0),
    ("SoftwareMenu", 1),
    ("EnableEscc", 0),
    ("HyundaiCameraSCC", 0),
    ("CanfdHDA2", 0),
    ("EnableRadarTracks", 0),
    ("RadarLatFactor", 0),
    ("EnableCornerRadar", 0),
    ("CarrotLearningActive", 0),
    ("CarrotLearningAutoApply", 0),
  ]:
    expect_setting(report, settings, name, default)


def check_capnp_and_dbc(report: Report) -> None:
  for path in ["cereal/car.capnp", "opendbc_repo/opendbc/car/car.capnp"]:
    report.require(f"capnp spFlags exists once: {path}", capnp_field_count(path, "spFlags @79 :UInt32") == 1)

  dbc = read_text("opendbc_repo/opendbc/dbc/hyundai_kia_generic.dbc")
  escc = dbc_message_block(dbc, "ESCC")
  report.require("DBC ESCC message id 683 exists", escc.startswith("BO_ 683 ESCC:"), "missing BO_ 683 ESCC")
  for signal in [
    "FCA_CmdAct",
    "AEB_CmdAct",
    "CF_VSM_Warn_SCC12",
    "CF_VSM_DecCmdAct_SCC12",
    "CR_VSM_DecCmd_SCC12",
    "ObjValid",
    "ACC_ObjStatus",
    "ACC_ObjLatPos",
    "ACC_ObjRelSpd",
    "ACC_ObjDist",
  ]:
    report.require(f"DBC ESCC signal: {signal}", f"SG_ {signal} " in escc)


def check_seltos_profile(report: Report) -> None:
  values = read_text("opendbc_repo/opendbc/car/hyundai/values.py")
  report.require_contains("Seltos 2023 platform exists", "opendbc_repo/opendbc/car/hyundai/values.py", "KIA_SELTOS_2023 = HyundaiPlatformConfig")
  report.require_contains("Seltos 2023 display name exists", "opendbc_repo/opendbc/car/hyundai/values.py", 'HyundaiCarDocs("Kia Seltos 2023"')
  report.require_regex(
    "Seltos 2023 reuses Seltos 2021 physical profile",
    "opendbc_repo/opendbc/car/hyundai/values.py",
    r"KIA_SELTOS_2023 = HyundaiPlatformConfig\(.*?CarHarness\.hyundai_a.*?CarSpecs\(mass=1337, wheelbase=2\.63, steerRatio=14\.56\).*?HyundaiFlags\.CHECKSUM_CRC8",
  )
  seltos_block_match = re.search(r"KIA_SELTOS_2023 = HyundaiPlatformConfig\(.*?\n  \)", values, re.S)
  seltos_block = "" if seltos_block_match is None else seltos_block_match.group(0)
  report.require("Seltos 2023 stays non-CANFD", "HyundaiCanFDPlatformConfig" not in seltos_block and "CANFD" not in seltos_block)
  report.require("Seltos 2023 stays non-HDA2", "HDA2" not in seltos_block)
  report.require_contains("Seltos 2023 ABS non-essential ECU parity", "opendbc_repo/opendbc/car/hyundai/values.py", "CAR.KIA_SELTOS, CAR.KIA_SELTOS_2023")


def check_escc_wiring(report: Report) -> None:
  report.require_regex("ESCC gated by explicit parameter", "opendbc_repo/opendbc/car/hyundai/interface.py", r'params\.get_int\("EnableEscc"\) == 1')
  report.require_regex("ESCC requires 0x2AB on bus 0", "opendbc_repo/opendbc/car/hyundai/interface.py", r"0x2AB in fingerprint\[0\]")
  report.require_contains("ESCC sets spFlags", "opendbc_repo/opendbc/car/hyundai/interface.py", "ret.spFlags |= HyundaiFlagsSP.SP_ENHANCED_SCC.value")
  report.require_contains("ESCC sets panda safety flag", "opendbc_repo/opendbc/car/hyundai/interface.py", "HyundaiSafetyFlags.ESCC.value")
  report.require_contains("ESCC enables longitudinal path", "opendbc_repo/opendbc/car/hyundai/interface.py", "enable_escc")

  report.require_contains("ESCC radar parser watches ESCC", "opendbc_repo/opendbc/car/hyundai/radar_interface.py", '("ESCC", 50)')
  report.require_contains("ESCC radar trigger is 0x2AB", "opendbc_repo/opendbc/car/hyundai/radar_interface.py", "self.trigger_msg_tracks = 0x2AB")
  for signal in ["ACC_ObjStatus", "ACC_ObjDist", "ACC_ObjLatPos", "ACC_ObjRelSpd"]:
    report.require_contains(f"ESCC radar reads {signal}", "opendbc_repo/opendbc/car/hyundai/radar_interface.py", signal)

  report.require_contains("carstate caches ESCC parser", "opendbc_repo/opendbc/car/hyundai/carstate.py", 'add_and_cache(self.cp, "ESCC", "escc")')
  for field in ["escc_aeb_warning", "escc_aeb_dec_cmd_act", "escc_cmd_act", "escc_aeb_dec_cmd"]:
    report.require_contains(f"carstate preserves {field}", "opendbc_repo/opendbc/car/hyundai/carstate.py", field)

  report.require_contains("hyundaican preserves ESCC AEB status", "opendbc_repo/opendbc/car/hyundai/hyundaican.py", 'scc12_values["AEB_Status"] = 2 if escc else 1')
  report.require_contains("hyundaican skips FCA11 while ESCC", "opendbc_repo/opendbc/car/hyundai/hyundaican.py", "not escc")
  report.require_contains("carcontroller skips tester-present disable while ESCC", "opendbc_repo/opendbc/car/hyundai/carcontroller.py", "or escc")
  report.require_contains("carcontroller skips radar option spam while ESCC", "opendbc_repo/opendbc/car/hyundai/carcontroller.py", "not camera_scc and not escc")

  report.require_contains("panda safety has ESCC param", "opendbc_repo/opendbc/safety/safety/safety_hyundai_common.h", "HYUNDAI_PARAM_ESCC = 1024")
  report.require_contains("panda safety parses ESCC param", "opendbc_repo/opendbc/safety/safety/safety_hyundai_common.h", "hyundai_escc = GET_FLAG(param, HYUNDAI_PARAM_ESCC)")


def check_offroad_wiring(report: Report) -> None:
  for path in [
    "common/params_keys.h",
    "selfdrive/carrot_settings.json",
    "system/hardware/hardwared.py",
    "selfdrive/pandad/panda_safety.cc",
    "selfdrive/pandad/pandad.h",
    "selfdrive/ui/qt/offroad/settings.cc",
    "system/manager/manager.py",
    "system/manager/process_config.py",
    "system/athena/registration.py",
    "selfdrive/car/car_specific.py",
  ]:
    for legacy_name in FORBIDDEN_LEGACY_PARAMS:
      report.require_not_contains("forbidden legacy param absent: " + path, path, legacy_name)

  report.require_contains("hardwared reads AlwaysOffroad", "system/hardware/hardwared.py", 'params.get_bool("AlwaysOffroad")')
  report.require_contains("hardwared keeps device offroad", "system/hardware/hardwared.py", "should_start = not always_offroad")
  report.require_contains("pandad reads AlwaysOffroad", "selfdrive/pandad/panda_safety.cc", 'params_.getBool("AlwaysOffroad")')
  report.require_contains("pandad forces no-output safety", "selfdrive/pandad/panda_safety.cc", "SafetyModel::NO_OUTPUT")
  report.require_contains("manager checks EnableConnect", "system/manager/manager.py", 'params.get_int("EnableConnect")')
  report.require_contains("manager keeps unregistered dongle id", "system/manager/manager.py", "UNREGISTERED_DONGLE_ID")
  report.require_contains("registration returns unregistered id when Connect is disabled", "system/athena/registration.py", "return UNREGISTERED_DONGLE_ID")
  report.require_contains("registration skips when connect disabled", "system/athena/registration.py", 'params.get_int("EnableConnect") != 1')
  report.require_contains("local updater remains available offroad", "system/manager/process_config.py", 'return not started and params.get_bool("SoftwareMenu")')
  report.require_contains("remote connect process is hard-disabled", "system/manager/process_config.py", 'DaemonProcess("manage_athenad", "system.athena.manage_athenad", "AthenadPid", enabled=False)')
  report.require_regex("native setting exposes AlwaysOffroad", "selfdrive/ui/qt/offroad/settings.cc", r'CValueControl\("AlwaysOffroad".*?, 0, 1, 1\)')
  report.require_regex("native setting keeps EnableConnect binary", "selfdrive/ui/qt/offroad/settings.cc", r'CValueControl\("EnableConnect".*?, 0, 1, 1\)')


def manual_items() -> List[str]:
  return [
    "On the C3 clone, confirm boot reaches UI with AlwaysOffroad=0 and EnableConnect=0 after ACC/CAN power loss.",
    "With EnableEscc=0, confirm Seltos 2023 behaves like the known-good Seltos 2021 path.",
    "With EnableEscc=1, confirm CAN bus 0 sees stable 0x2AB before enabling longitudinal control.",
    "Record /data/params for DongleId, AlwaysOffroad, SoftwareMenu, EnableConnect, EnableEscc, HyundaiCameraSCC, CanfdHDA2, and EnableRadarTracks.",
    "With AlwaysOffroad=1 while powered, confirm the UI stays offroad and local Web/update access still works.",
    "Confirm no SCC/AEB/FCW fault appears after ESCC is enabled.",
  ]


def print_report(report: Report, show_manual: bool) -> None:
  print("ESCC / AlwaysOffroad preflight")
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
    print("OK: static preflight passed")


def main() -> int:
  parser = argparse.ArgumentParser(description="Static preflight for the personal C3/Seltos/ESCC build.")
  parser.add_argument("--no-manual", action="store_true", help="Do not print manual on-car checks.")
  args = parser.parse_args()

  report = Report()
  check_git_context(report)
  check_params_and_settings(report)
  check_capnp_and_dbc(report)
  check_seltos_profile(report)
  check_escc_wiring(report)
  check_offroad_wiring(report)

  print_report(report, show_manual=not args.no_manual)
  return 1 if report.failed else 0


if __name__ == "__main__":
  raise SystemExit(main())
