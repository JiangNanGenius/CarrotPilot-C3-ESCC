#!/usr/bin/env python3
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_LEGACY_PARAMS = (
  "Always" + "Offline",
  "device_go" + "_off_road",
)
WHITESPACE_CANDIDATES = [
  "README.md",
  ".github/workflows/personal-smoke.yml",
  "docs/personal",
  "scripts/personal",
  "selfdrive/carrot",
  "selfdrive/carrot_settings.json",
  "selfdrive/car/hyundai",
  "opendbc_repo/opendbc/dbc/hyundai_kia_generic.dbc",
  "panda/board/safety/safety_hyundai.h",
]


class CheckFailure(Exception):
  pass


class FakeParams:
  DEFAULTS = {
    "AlwaysOffroad": False,
    "EnableEscc": 0,
    "EnableConnect": 0,
    "SoftwareMenu": 1,
    "CarrotLearningActive": 0,
    "CarrotLearningAutoApply": False,
    "CarrotTunerApplyLat": 1,
    "CarrotTunerApplyLong": 1,
    "CarrotLearningApply": False,
    "CarrotLearningIgnore": False,
    "CarrotLearningClear": False,
    "CarrotLearningPopupReady": False,
    "IsOnroad": False,
    "CruiseMaxVals0": 160,
    "CruiseMaxVals1": 200,
    "CruiseMaxVals2": 160,
    "CruiseMaxVals3": 130,
    "CruiseMaxVals4": 110,
    "CruiseMaxVals5": 95,
    "CruiseMaxVals6": 80,
    "TFollowGap1": 110,
    "TFollowGap2": 120,
    "TFollowGap3": 140,
    "TFollowGap4": 160,
    "JLeadFactor3": 0,
    "PathOffset": 0,
    "SteerActuatorDelay": 0,
    "SteerRatioRate": 100,
    "DynamicTFollow": 0,
    "TFollowDecelBoost": 10,
    "StopDistanceCarrot": 550,
  }

  def __init__(self, store: Optional[Dict[str, Any]] = None):
    self.store = store if store is not None else {}

  def get(self, key: str) -> Any:
    return self.store.get(key)

  def get_int(self, key: str) -> int:
    return int(self.store.get(key, self.DEFAULTS.get(key, 0)))

  def get_bool(self, key: str) -> bool:
    return bool(self.store.get(key, self.DEFAULTS.get(key, False)))

  def put(self, key: str, value: Any) -> None:
    self.store[key] = value

  def put_int(self, key: str, value: Any) -> None:
    self.store[key] = int(value)

  def put_bool(self, key: str, value: Any) -> None:
    self.store[key] = bool(value)

  def remove(self, key: str) -> None:
    self.store.pop(key, None)


def rel(path: Path) -> str:
  return str(path.relative_to(ROOT))


def run(cmd: List[str], label: str, optional: bool = False) -> Tuple[bool, str]:
  if optional and shutil.which(cmd[0]) is None:
    return True, "SKIP: missing " + cmd[0]

  proc = subprocess.run(
    cmd,
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  if proc.returncode != 0:
    raise CheckFailure(label + " failed:\n" + proc.stdout[-4000:])
  return True, proc.stdout.strip()


def changed_candidate_paths(cached: bool = False) -> List[Path]:
  cmd = ["git", "diff", "--name-only"]
  if cached:
    cmd.append("--cached")
  cmd.extend(["--", *WHITESPACE_CANDIDATES])
  try:
    proc = subprocess.run(
      cmd,
      cwd=str(ROOT),
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      timeout=20,
    )
  except subprocess.TimeoutExpired:
    return []
  if proc.returncode != 0:
    return []
  return [ROOT / line for line in proc.stdout.splitlines() if line.strip()]


def check_worktree_whitespace() -> str:
  paths = set(changed_candidate_paths()) | set(changed_candidate_paths(cached=True))
  if not paths:
    return "no personal-path changes"

  failures = []
  for path in sorted(paths):
    if not path.exists() or not path.is_file():
      continue
    try:
      with path.open("rb") as f:
        data = f.read()
    except OSError as exc:
      raise CheckFailure("failed reading %s: %s" % (rel(path), exc)) from exc
    if b"\0" in data:
      continue
    text = data.decode("utf-8", errors="ignore")
    for line_no, line in enumerate(text.splitlines(), start=1):
      trailing = len(line) - len(line.rstrip(" \t"))
      if trailing == 0:
        continue
      if path.suffix.lower() == ".md" and trailing == 2 and line.endswith("  "):
        continue
      else:
        failures.append("%s:%d: trailing whitespace" % (rel(path), line_no))

  if failures:
    raise CheckFailure("worktree whitespace failed:\n" + "\n".join(failures[:80]))
  return "%d file(s)" % len(paths)


def read_text(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8")


def expect_contains(path: str, needle: str, label: str) -> None:
  text = read_text(path)
  if needle not in text:
    raise CheckFailure("%s missing in %s" % (label, path))


def expect_not_contains(path: str, needle: str, label: str) -> None:
  text = read_text(path)
  if needle in text:
    raise CheckFailure("%s unexpectedly found in %s" % (label, path))


def expect_regex(path: str, pattern: str, label: str) -> None:
  text = read_text(path)
  if not re.search(pattern, text, re.S):
    raise CheckFailure("%s missing in %s" % (label, path))


def settings_by_name() -> Dict[str, Dict[str, Any]]:
  with (ROOT / "selfdrive/carrot_settings.json").open("r", encoding="utf-8") as f:
    data = json.load(f)
  by_name: Dict[str, Dict[str, Any]] = {}
  for item in data.get("params", []):
    name = item.get("name")
    if name:
      by_name[name] = item
  return by_name


def check_settings_defaults() -> None:
  by_name = settings_by_name()
  expected = {
    "AlwaysOffroad": 0,
    "EnableConnect": 0,
    "SoftwareMenu": 1,
    "EnableEscc": 0,
    "CarrotLearningActive": 0,
    "CarrotLearningAutoApply": 0,
    "CarrotLearningApply": 0,
    "CarrotLearningIgnore": 0,
    "CarrotLearningClear": 0,
    "EnableAmapNaviStatus": 0,
    "AutoNaviSpeedLimitOffset": 0,
    "AutoNaviSpeedSafetyFactor": 100,
  }
  for name, default in expected.items():
    if name not in by_name:
      raise CheckFailure("missing setting entry: " + name)
    if by_name[name].get("default") != default:
      raise CheckFailure("%s default expected %r, got %r" % (name, default, by_name[name].get("default")))


def check_params_defaults() -> None:
  params_keys = "common/params_keys.h"
  patterns = {
    "AlwaysOffroad default off": r'\{"AlwaysOffroad", \{PERSISTENT, BOOL, "0"\}\}',
    "EnableEscc default off": r'\{"EnableEscc", \{PERSISTENT, INT, "0"\}\}',
    "EnableConnect default off": r'\{"EnableConnect", \{PERSISTENT, INT, "0"\}\}',
    "SoftwareMenu default on": r'\{"SoftwareMenu", \{PERSISTENT, INT, "1"\}\}',
    "CarrotLearningActive default off": r'\{"CarrotLearningActive", \{PERSISTENT, INT, "0"\}\}',
    "CarrotLearningAutoApply default off": r'\{"CarrotLearningAutoApply", \{PERSISTENT, BOOL, "0"\}\}',
    "CarrotLearningApply action": r'\{"CarrotLearningApply", \{PERSISTENT, BOOL, "0"\}\}',
    "CarrotLearningIgnore action": r'\{"CarrotLearningIgnore", \{PERSISTENT, BOOL, "0"\}\}',
    "CarrotTunerApplyLat default on": r'\{"CarrotTunerApplyLat", \{PERSISTENT, INT, "1"\}\}',
    "CarrotTunerApplyLong default on": r'\{"CarrotTunerApplyLong", \{PERSISTENT, INT, "1"\}\}',
    "EnableAmapNaviStatus default off": r'\{"EnableAmapNaviStatus", \{PERSISTENT, INT, "0"\}\}',
    "AutoNaviSpeedLimitOffset default zero": r'\{"AutoNaviSpeedLimitOffset", \{PERSISTENT, INT, "0"\}\}',
    "AutoNaviSpeedSafetyFactor default neutral": r'\{"AutoNaviSpeedSafetyFactor", \{PERSISTENT, INT, "100"\}\}',
    "PowerCycleBootOk default off": r'\{"PowerCycleBootOk", \{PERSISTENT, BOOL, "0"\}\}',
  }
  for label, pattern in patterns.items():
    expect_regex(params_keys, pattern, label)


def check_seltos_static() -> None:
  path = "opendbc_repo/opendbc/car/hyundai/values.py"
  expect_contains(path, "KIA_SELTOS_2023 = HyundaiPlatformConfig", "Seltos 2023 platform")
  expect_contains(path, 'HyundaiCarDocs("Kia Seltos 2023"', "Seltos 2023 display name")
  expect_contains(path, "CarHarness.hyundai_a", "Seltos 2023 harness")
  expect_regex(path, r"KIA_SELTOS_2023 = HyundaiPlatformConfig\(.*?CarSpecs\(mass=1337, wheelbase=2.63, steerRatio=14.56\).*?flags=HyundaiFlags.CHECKSUM_CRC8", "Seltos 2023 specs/CRC8")
  expect_contains(path, "CAR.KIA_SELTOS, CAR.KIA_SELTOS_2023", "Seltos 2023 ABS non-essential ECU")


def check_escc_static() -> None:
  expect_contains("opendbc_repo/opendbc/dbc/hyundai_kia_generic.dbc", "BO_ 683 ESCC", "ESCC DBC message")
  expect_contains("opendbc_repo/opendbc/car/car.capnp", "spFlags @79 :UInt32", "opendbc CarParams spFlags")
  expect_contains("opendbc_repo/opendbc/car/hyundai/values.py", "ESCC = 1024", "HyundaiSafetyFlags ESCC")
  expect_contains("opendbc_repo/opendbc/car/hyundai/values.py", "SP_ENHANCED_SCC = 1", "HyundaiFlagsSP ESCC")
  expect_contains("opendbc_repo/opendbc/car/hyundai/interface.py", 'params.get_int("EnableEscc") == 1', "EnableEscc gate")
  expect_contains("opendbc_repo/opendbc/car/hyundai/radar_interface.py", "ESCC_TID", "ESCC radar track id")
  expect_contains("opendbc_repo/opendbc/safety/safety/safety_hyundai_common.h", "HYUNDAI_PARAM_ESCC = 1024", "panda ESCC safety param")


def check_offroad_static() -> None:
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
      expect_not_contains(path, legacy_name, "forbidden legacy param")

  expect_contains("system/hardware/hardwared.py", 'params.get_bool("AlwaysOffroad")', "hardwared AlwaysOffroad")
  expect_contains("system/hardware/hardwared.py", "should_start = not always_offroad", "hardwared offroad gate")
  expect_contains("selfdrive/pandad/panda_safety.cc", 'params_.getBool("AlwaysOffroad")', "pandad AlwaysOffroad")
  expect_contains("selfdrive/pandad/panda_safety.cc", "SafetyModel::NO_OUTPUT", "pandad no-output safety")
  expect_contains("system/manager/manager.py", "UNREGISTERED_DONGLE_ID", "unregistered dongle fallback")
  expect_contains("system/athena/registration.py", 'UNREGISTERED_DONGLE_ID = "UnregisteredDevice"', "unregistered dongle id")
  expect_contains("system/manager/manager.py", "connect_enabled", "connect process gate")
  expect_contains("system/athena/registration.py", "EnableConnect", "registration EnableConnect")
  expect_contains("system/manager/process_config.py", "enable_connect", "connect process gate")
  expect_contains("system/manager/process_config.py", "return not started and params.get_bool(\"SoftwareMenu\")", "updated stays available offroad")
  expect_contains("system/manager/process_config.py", "return params.get_int(\"EnableConnect\") > 0", "connect process uses EnableConnect")
  expect_regex("selfdrive/ui/qt/offroad/settings.cc", r'CValueControl\("AlwaysOffroad".*?, 0, 1, 1\)', "native AlwaysOffroad setting")
  expect_regex("selfdrive/ui/qt/offroad/settings.cc", r'CValueControl\("EnableConnect".*?, 0, 1, 1\)', "native EnableConnect setting is binary")
  expect_not_contains("system/manager/manager.py", "DisableUpdates", "manager does not disable updates for offroad")
  expect_not_contains("selfdrive/car/car_specific.py", "AlwaysOffroad", "car_specific not tied to AlwaysOffroad")


def check_speed_camera_offsets() -> None:
  expect_contains("selfdrive/carrot/carrot_serv.py", 'params.get_int("AutoNaviSpeedLimitOffset")', "speed camera fixed offset param")
  expect_contains("selfdrive/carrot/carrot_serv.py", "def _camera_speed_limit", "speed camera target helper")
  expect_contains("selfdrive/carrot/carrot_serv.py", "speed_limit_kph * self.autoNaviSpeedSafetyFactor + offset_kph", "speed camera percent plus fixed offset")
  expect_not_contains("selfdrive/carrot/carrot_serv.py", "offset = 5 if self.is_metric", "no hardcoded speed-camera +5 offset")
  expect_not_contains("selfdrive/carrot/carrot_serv.py", "offset_kph *= CV.MPH_TO_KPH", "speed camera fixed offset stays km/h")
  expect_regex("selfdrive/ui/qt/offroad/settings.cc", r'CValueControl\("AutoNaviSpeedLimitOffset".*?, -20, 30, 1\)', "native speed camera fixed offset setting")
  expect_regex("selfdrive/ui/qt/offroad/settings.cc", r'CValueControl\("AutoNaviSpeedSafetyFactor".*?, 80, 120, 1\)', "native speed camera percent setting")
  expect_not_contains("selfdrive/ui/translations/main_zh-CHS.ts", "SpeedCamSafetyFactor(105%)", "no stale speed-camera translation")


def install_fake_openpilot_params() -> None:
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams

  sys.modules["openpilot"] = types.ModuleType("openpilot")
  sys.modules["openpilot.common"] = types.ModuleType("openpilot.common")
  sys.modules["openpilot.common.params"] = params_mod


def import_file(module_name: str, path: str):
  spec = importlib.util.spec_from_file_location(module_name, str(ROOT / path))
  if spec is None or spec.loader is None:
    raise CheckFailure("unable to import " + path)
  module = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = module
  spec.loader.exec_module(module)
  return module


def check_carrot_learning_mock() -> None:
  install_fake_openpilot_params()
  learning = import_file("carrot_learning_under_test", "selfdrive/carrot/carrot_learning.py")
  learner = learning.CarrotLearner()

  learner.update(80, True, True, False, lead_drel=30, lead_v_kph=70, gas_val=0.3)
  if learner.params.get("CarrotLearningData") is not None:
    raise CheckFailure("inactive learner wrote CarrotLearningData")

  learner.params.put_int("CarrotLearningActive", 1)
  for _ in range(160):
    learner.update(80, True, True, False, lead_drel=40, lead_v_kph=75, gas_val=0.4)
  learner.update(0, False, False, True)

  raw = learner.params.get("CarrotLearningRecommend")
  if not raw:
    raise CheckFailure("active learner did not create recommendation")
  payload = json.loads(raw.decode("utf-8"))
  if "CruiseMaxVals4" not in payload.get("recommendations", {}):
    raise CheckFailure("learner recommendation missing CruiseMaxVals4")
  if learner.params.get_int("CruiseMaxVals4") != 110:
    raise CheckFailure("learner changed control param before manual apply")

  learner.params.put_bool("CarrotLearningApply", True)
  learner.update(0, False, False, False)
  if learner.params.get_int("CruiseMaxVals4") <= 110:
    raise CheckFailure("learner apply action did not apply recommendation")
  if learner.params.get_bool("CarrotLearningApply"):
    raise CheckFailure("CarrotLearningApply did not reset")


def check_learning_service_mock() -> None:
  service_params = types.ModuleType("openpilot.selfdrive.carrot.server.services.params")
  service_params.HAS_PARAMS = True
  service_params.Params = FakeParams

  package_names = [
    "openpilot.selfdrive",
    "openpilot.selfdrive.carrot",
    "openpilot.selfdrive.carrot.server",
    "openpilot.selfdrive.carrot.server.services",
  ]
  for name in package_names:
    if name not in sys.modules:
      mod = types.ModuleType(name)
      mod.__path__ = []
      sys.modules[name] = mod
  sys.modules["openpilot.selfdrive.carrot.server.services.params"] = service_params

  svc = import_file(
    "openpilot.selfdrive.carrot.server.services.carrot_learning",
    "selfdrive/carrot/server/services/carrot_learning.py",
  )

  store = {
    "CarrotLearningRecommend": json.dumps({
      "source": "smoke",
      "created_at": 1,
      "recommendations": {
        "CruiseMaxVals4": {
          "category": "long",
          "current": 110,
          "recommended": 121,
          "reason": "smoke",
          "evidence": {},
        }
      },
    }).encode("utf-8"),
    "CarrotLearningPopupReady": True,
  }

  class StoreParams(FakeParams):
    def __init__(self):
      super().__init__(store)

  svc.HAS_PARAMS = True
  svc.Params = StoreParams
  state = svc.get_learning_state()
  if not state.get("pending") or len(state.get("recommendations", [])) != 1:
    raise CheckFailure("learning service did not expose pending recommendation")
  result = svc.apply_learning_recommendations()
  if result.get("applied_count") != 1 or store.get("CruiseMaxVals4") != 121:
    raise CheckFailure("learning service did not apply recommendation")

  store.clear()
  store.update({
    "IsOnroad": True,
    "CarrotLearningRecommend": json.dumps({
      "recommendations": {
        "CruiseMaxVals4": {"category": "long", "current": 110, "recommended": 121}
      }
    }).encode("utf-8"),
  })
  try:
    svc.apply_learning_recommendations()
  except RuntimeError:
    return
  raise CheckFailure("learning service allowed onroad apply")


def check_py_compile() -> None:
  pycache = Path("/tmp/carrotpilot-c3-escc-pycache")
  pycache.mkdir(parents=True, exist_ok=True)
  os.environ.setdefault("PYTHONPYCACHEPREFIX", str(pycache))

  files = [
    "scripts/personal/smoke_check.py",
    "scripts/personal/escc_offroad_preflight.py",
    "scripts/personal/cplink_preflight.py",
    "scripts/personal/feature_boundary_check.py",
    "scripts/personal/feature_status_report.py",
    "scripts/personal/update_audit.py",
    "scripts/personal/upstream_update_plan.py",
    "scripts/personal/base_version_check.py",
    "scripts/personal/build_binary_installer.py",
    "scripts/personal/release_gate.py",
    "scripts/personal/settings_cn_audit.py",
    "scripts/personal/device_snapshot.py",
    "scripts/personal/install_target_check.py",
    "scripts/personal/params_migration.py",
    "scripts/personal/c3_commissioning.py",
    "scripts/personal/seltos_profile_check.py",
    "scripts/personal/road_test_evidence_check.py",
    "scripts/personal/evidence_readiness_report.py",
    "scripts/personal/navipilot_live_check.py",
    "scripts/personal/record_power_cycle_boot.py",
    "scripts/personal/model_selector_audit.py",
    "scripts/personal/app_navi_overtake_audit.py",
    "scripts/personal/amap_navi_status_check.py",
    "scripts/personal/c3_static_check.py",
    "scripts/personal/collect_real_car_evidence.py",
    "opendbc_repo/opendbc/car/hyundai/values.py",
    "opendbc_repo/opendbc/car/hyundai/interface.py",
    "opendbc_repo/opendbc/car/hyundai/radar_interface.py",
    "opendbc_repo/opendbc/car/hyundai/carstate.py",
    "opendbc_repo/opendbc/car/hyundai/hyundaican.py",
    "opendbc_repo/opendbc/car/hyundai/carcontroller.py",
    "system/manager/manager.py",
    "system/manager/process_config.py",
    "system/athena/registration.py",
    "selfdrive/car/car_specific.py",
    "selfdrive/carrot/carrot_functions.py",
    "selfdrive/carrot/carrot_learning.py",
    "selfdrive/carrot/app_navi_status.py",
    "selfdrive/carrot/server/services/carrot_learning.py",
    "selfdrive/carrot/server/features/carrot_learning.py",
    "selfdrive/carrot/server/features/params.py",
    "selfdrive/carrot/server/features/__init__.py",
  ]
  run([sys.executable, "-m", "py_compile"] + files, "python syntax")


def check_js_syntax() -> str:
  files = [
    "selfdrive/carrot/web/js/pages/setting.js",
    "selfdrive/carrot/web/js/shared/api.js",
  ]
  if shutil.which("node") is None:
    return "SKIP: missing node"
  for f in files:
    run(["node", "--check", f], "js syntax " + f)
  return "checked"


def check_install_script() -> None:
  expect_contains("scripts/personal/install_c3_escc.sh", "CARROTPILOT_FIRST_BOOT_NOTE", "installer first-boot note env")
  expect_contains("scripts/personal/install_c3_escc.sh", "write_first_boot_note", "installer first-boot note writer")
  expect_contains("scripts/personal/install_c3_escc.sh", "c3_commissioning.py --archive", "installer first-boot commissioning command")
  expect_contains("scripts/personal/install_c3_escc.sh", "PowerCycleBootOk", "installer power-cycle confirmation reset")
  expect_contains("scripts/personal/install_c3_escc.sh", 'write_param "AutoNaviSpeedLimitOffset" "0"', "installer neutral speed-camera fixed offset")
  expect_contains("scripts/personal/install_c3_escc.sh", 'write_param "AutoNaviSpeedSafetyFactor" "100"', "installer neutral speed-camera percentage")
  expect_contains("scripts/personal/install_c3_escc.sh", "install-c3-escc-test", "installer test channel")
  expect_contains("scripts/personal/install_c3_escc.sh", "alpha-supercombo", "installer alpha supercombo channel")
  expect_contains("scripts/personal/install_c3_escc.sh", "--list-channels", "installer channel listing")
  run([sys.executable, "scripts/personal/record_power_cycle_boot.py", "--self-test"], "power-cycle boot recorder self-test")
  run([sys.executable, "scripts/personal/build_binary_installer.py", "--self-test"], "C3 binary installer builder self-test")
  run(["sh", "-n", "scripts/personal/install_c3_escc.sh"], "C3 installer shell syntax")
  run(["scripts/personal/install_c3_escc.sh", "--list-channels"], "C3 installer channel list")
  run([
    "scripts/personal/install_c3_escc.sh",
    "--dry-run",
    "--force",
    "--channel",
    "test",
    "--install-dir",
    "/data/openpilot-smoke",
    "--tmp-dir",
    "/data/tmppilot-smoke",
    "--backup-root",
    "/data/carrotpilot-backups-smoke",
    "--no-params",
    "--no-continue",
  ], "C3 installer dry-run")


def check_c3_static_dry_run() -> None:
  run([
    sys.executable,
    "scripts/personal/c3_static_check.py",
    "--output",
    "/tmp/carrotpilot-c3-escc-static-check-smoke.md",
    "--snapshot-output",
    "/tmp/carrotpilot-c3-escc-snapshot-smoke.md",
    "--allow-branch",
    "--skip-preflight",
  ], "C3 static check dry-run")
  report = Path("/tmp/carrotpilot-c3-escc-static-check-smoke.md")
  snapshot = Path("/tmp/carrotpilot-c3-escc-snapshot-smoke.md")
  if not report.exists() or "# CarrotPilot-C3-ESCC Static Check" not in report.read_text(encoding="utf-8"):
    raise CheckFailure("C3 static dry-run did not create a valid report")
  if not snapshot.exists() or "# CarrotPilot-C3-ESCC Device Snapshot" not in snapshot.read_text(encoding="utf-8"):
    raise CheckFailure("C3 static dry-run did not create a valid snapshot")
  snapshot_text = snapshot.read_text(encoding="utf-8")
  for key in [
    "CarParamsDecoded",
    "EnableAmapNaviStatus",
    "process_snapshot_available",
    "connect_forbidden_processes_seen",
    "updated_process_seen",
    "connect_process_seen",
    "uploader_process_seen",
    "cplink_updates_seen",
    "cplink_speed_limit_seen",
    "last_navInstructionCarrot",
    "amapNavi_updates",
    "amap_navi_updates_seen",
    "last_amapNavi",
    "DrivingModelName",
    "PendingModelName",
    "model_selector_status_available",
    "model_selector_engine",
    "model_selector_pending_active",
    "model_selector_describe",
    "PowerCycleBootOk",
    "PowerCycleBootCommit",
    "PowerCycleBootRecordedAt",
  ]:
    if key not in snapshot_text:
      raise CheckFailure("C3 static dry-run snapshot missing " + key)


def check_real_car_evidence_dry_run() -> None:
  output_dir = Path("/tmp/carrotpilot-c3-escc-evidence-smoke")
  run([
    sys.executable,
    "scripts/personal/collect_real_car_evidence.py",
    "--output-dir",
    str(output_dir),
    "--allow-branch",
    "--skip-preflight",
    "--force",
  ], "real-car evidence bundle dry-run")

  expected_files = [
    "README.md",
    "manifest.json",
    "static-check.md",
    "static-check-output.txt",
    "device-snapshot.md",
    "road-test-log-draft.md",
  ]
  for name in expected_files:
    if not (output_dir / name).exists():
      raise CheckFailure("real-car evidence bundle missing " + name)

  if "# CarrotPilot-C3-ESCC Evidence Bundle" not in (output_dir / "README.md").read_text(encoding="utf-8"):
    raise CheckFailure("real-car evidence README has wrong title")
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  if manifest.get("static_check_exit_code") != 0:
    raise CheckFailure("real-car evidence manifest recorded a failed static check")


def check_c3_commissioning_dry_run() -> None:
  output_dir = Path("/tmp/carrotpilot-c3-escc-commissioning-smoke")
  run([
    sys.executable,
    "scripts/personal/c3_commissioning.py",
    "--output-dir",
    str(output_dir),
    "--allow-branch",
    "--skip-preflight",
    "--force",
  ], "C3 commissioning dry-run")

  expected_files = [
    "README.md",
    "manifest.json",
    "migration-import-output.txt",
    "evidence-collection-output.txt",
    "evidence-readiness.txt",
  ]
  for name in expected_files:
    if not (output_dir / name).exists():
      raise CheckFailure("C3 commissioning output missing " + name)
  for name in ["manifest.json", "static-check.md", "device-snapshot.md", "road-test-log-draft.md"]:
    if not (output_dir / "evidence" / name).exists():
      raise CheckFailure("C3 commissioning evidence folder missing " + name)

  if "# CarrotPilot-C3-ESCC C3 Commissioning" not in (output_dir / "README.md").read_text(encoding="utf-8"):
    raise CheckFailure("C3 commissioning README has wrong title")
  if "SKIPPED: no --migration-input" not in (output_dir / "migration-import-output.txt").read_text(encoding="utf-8"):
    raise CheckFailure("C3 commissioning missing migration skip output")
  if "CarrotPilot-C3-ESCC evidence readiness report" not in (output_dir / "evidence-readiness.txt").read_text(encoding="utf-8"):
    raise CheckFailure("C3 commissioning missing readiness output")
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  if manifest.get("migration_mode") != "skipped":
    raise CheckFailure("C3 commissioning manifest did not record skipped migration")
  if manifest.get("evidence_exit_code") != 0 or manifest.get("readiness_exit_code") != 0:
    raise CheckFailure("C3 commissioning manifest recorded failed evidence/readiness step")


def main() -> int:
  checks: List[Tuple[str, Callable[[], Any]]] = [
    ("worktree whitespace", check_worktree_whitespace),
    ("settings JSON", lambda: run([sys.executable, "-m", "json.tool", "selfdrive/carrot_settings.json"], "settings JSON")),
    ("python syntax", check_py_compile),
    ("javascript syntax", check_js_syntax),
    ("settings defaults", check_settings_defaults),
    ("params defaults", check_params_defaults),
    ("Seltos profile parity", lambda: run([sys.executable, "scripts/personal/seltos_profile_check.py"], "Seltos profile parity")),
    ("Road-test evidence checker self-test", lambda: run([sys.executable, "scripts/personal/road_test_evidence_check.py", "--self-test"], "Road-test evidence checker self-test")),
    ("Evidence readiness report self-test", lambda: run([sys.executable, "scripts/personal/evidence_readiness_report.py", "--self-test"], "Evidence readiness report self-test")),
    ("Navipilot live check self-test", lambda: run([sys.executable, "scripts/personal/navipilot_live_check.py", "--self-test"], "Navipilot live check self-test")),
    ("Model selector audit", lambda: run([sys.executable, "scripts/personal/model_selector_audit.py"], "Model selector audit")),
    ("Upstream update plan self-test", lambda: run([sys.executable, "scripts/personal/upstream_update_plan.py", "--self-test"], "Upstream update plan self-test")),
    ("Base version documentation", lambda: run([sys.executable, "scripts/personal/base_version_check.py"], "Base version documentation")),
    ("App navigation / overtake audit", lambda: run([sys.executable, "scripts/personal/app_navi_overtake_audit.py"], "App navigation / overtake audit")),
    ("AmapNavi status compatibility", lambda: run([sys.executable, "scripts/personal/amap_navi_status_check.py"], "AmapNavi status compatibility")),
    ("Seltos 2023 static checks", check_seltos_static),
    ("ESCC static checks", check_escc_static),
    ("AlwaysOffroad static checks", check_offroad_static),
    ("Speed camera offset static checks", check_speed_camera_offsets),
    ("ESCC / AlwaysOffroad preflight", lambda: run([sys.executable, "scripts/personal/escc_offroad_preflight.py", "--no-manual"], "ESCC / AlwaysOffroad preflight")),
    ("CPlink / Navipilot preflight", lambda: run([sys.executable, "scripts/personal/cplink_preflight.py", "--no-manual"], "CPlink / Navipilot preflight")),
    ("Feature boundary guard", lambda: run([sys.executable, "scripts/personal/feature_boundary_check.py", "--no-manual"], "Feature boundary guard")),
    ("Feature status report", lambda: run([sys.executable, "scripts/personal/feature_status_report.py", "--strict"], "Feature status report")),
    ("Chinese settings audit", lambda: run([sys.executable, "scripts/personal/settings_cn_audit.py"], "Chinese settings audit")),
    ("Localization audit", lambda: run([sys.executable, "scripts/personal/localization_audit.py"], "Localization audit")),
    ("Install target manifest", lambda: run([sys.executable, "scripts/personal/install_target_check.py"], "Install target manifest")),
    ("Release integrity checker self-test", lambda: run([sys.executable, "scripts/personal/release_integrity_check.py", "--self-test"], "Release integrity checker self-test")),
    ("C3 installer script", check_install_script),
    ("Params migration self-test", lambda: run([sys.executable, "scripts/personal/params_migration.py", "self-test"], "Params migration self-test")),
    ("C3 static check dry-run", check_c3_static_dry_run),
    ("Real-car evidence bundle dry-run", check_real_car_evidence_dry_run),
    ("C3 commissioning dry-run", check_c3_commissioning_dry_run),
    ("Auto-Tuner learner mock", check_carrot_learning_mock),
    ("Auto-Tuner service mock", check_learning_service_mock),
  ]

  print("Personal smoke check")
  print("repo:", ROOT)
  failures = 0
  for name, fn in checks:
    try:
      result = fn()
      suffix = ""
      if isinstance(result, str) and result:
        suffix = " (" + result + ")"
      print("[PASS] " + name + suffix)
    except Exception as exc:
      failures += 1
      print("[FAIL] " + name)
      print(str(exc))

  if failures:
    print("FAILED: %d check(s)" % failures)
    return 1
  print("OK: all checks passed")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
