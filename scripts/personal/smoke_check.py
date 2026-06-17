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


class CheckFailure(Exception):
  pass


class FakeParams:
  DEFAULTS = {
    "AlwaysOffline": True,
    "EnableEscc": 0,
    "EnableConnect": 0,
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


def read_text(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8")


def expect_contains(path: str, needle: str, label: str) -> None:
  text = read_text(path)
  if needle not in text:
    raise CheckFailure("%s missing in %s" % (label, path))


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
    "AlwaysOffline": 1,
    "EnableEscc": 0,
    "CarrotLearningActive": 0,
    "CarrotLearningAutoApply": 0,
    "CarrotLearningApply": 0,
    "CarrotLearningIgnore": 0,
    "CarrotLearningClear": 0,
  }
  for name, default in expected.items():
    if name not in by_name:
      raise CheckFailure("missing setting entry: " + name)
    if by_name[name].get("default") != default:
      raise CheckFailure("%s default expected %r, got %r" % (name, default, by_name[name].get("default")))


def check_params_defaults() -> None:
  params_keys = "common/params_keys.h"
  patterns = {
    "AlwaysOffline default on": r'\{"AlwaysOffline", \{PERSISTENT, BOOL, "1"\}\}',
    "EnableEscc default off": r'\{"EnableEscc", \{PERSISTENT, INT, "0"\}\}',
    "EnableConnect default off": r'\{"EnableConnect", \{PERSISTENT, INT, "0"\}\}',
    "CarrotLearningActive default off": r'\{"CarrotLearningActive", \{PERSISTENT, INT, "0"\}\}',
    "CarrotLearningAutoApply default off": r'\{"CarrotLearningAutoApply", \{PERSISTENT, BOOL, "0"\}\}',
    "CarrotLearningApply action": r'\{"CarrotLearningApply", \{PERSISTENT, BOOL, "0"\}\}',
    "CarrotLearningIgnore action": r'\{"CarrotLearningIgnore", \{PERSISTENT, BOOL, "0"\}\}',
    "CarrotTunerApplyLat default on": r'\{"CarrotTunerApplyLat", \{PERSISTENT, INT, "1"\}\}',
    "CarrotTunerApplyLong default on": r'\{"CarrotTunerApplyLong", \{PERSISTENT, INT, "1"\}\}',
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


def check_offline_static() -> None:
  expect_contains("system/manager/manager.py", "AlwaysOffline", "manager AlwaysOffline")
  expect_contains("system/manager/manager.py", "UNREGISTERED_DONGLE_ID", "offline dongle fallback")
  expect_contains("system/athena/registration.py", 'UNREGISTERED_DONGLE_ID = "UnregisteredDevice"', "unregistered dongle id")
  expect_contains("system/manager/manager.py", "DisableUpdates", "offline disables updates")
  expect_contains("system/athena/registration.py", "AlwaysOffline", "registration AlwaysOffline")
  expect_contains("system/manager/process_config.py", "enable_connect", "connect process gate")
  expect_contains("system/manager/process_config.py", "AlwaysOffline", "process config AlwaysOffline")
  expect_contains("selfdrive/car/car_specific.py", "AlwaysOffline", "car_specific shutdown guard")


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
  files = [
    "scripts/personal/smoke_check.py",
    "scripts/personal/escc_offline_preflight.py",
    "scripts/personal/cplink_preflight.py",
    "scripts/personal/update_audit.py",
    "scripts/personal/release_gate.py",
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


def main() -> int:
  checks: List[Tuple[str, Callable[[], Any]]] = [
    ("git diff whitespace", lambda: run(["git", "diff", "--check"], "git diff --check")),
    ("settings JSON", lambda: run([sys.executable, "-m", "json.tool", "selfdrive/carrot_settings.json"], "settings JSON")),
    ("python syntax", check_py_compile),
    ("javascript syntax", check_js_syntax),
    ("settings defaults", check_settings_defaults),
    ("params defaults", check_params_defaults),
    ("Seltos 2023 static checks", check_seltos_static),
    ("ESCC static checks", check_escc_static),
    ("Always Offline static checks", check_offline_static),
    ("ESCC / Always Offline preflight", lambda: run([sys.executable, "scripts/personal/escc_offline_preflight.py", "--no-manual"], "ESCC / Always Offline preflight")),
    ("CPlink / Navipilot preflight", lambda: run([sys.executable, "scripts/personal/cplink_preflight.py", "--no-manual"], "CPlink / Navipilot preflight")),
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
