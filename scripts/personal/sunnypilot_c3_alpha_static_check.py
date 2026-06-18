#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8")


def read_tree(rel: str, suffixes: tuple[str, ...]) -> str:
  root = ROOT / rel
  chunks: list[str] = []
  for path in root.rglob("*"):
    if not path.is_file() or path.suffix not in suffixes:
      continue
    if path.stat().st_size > 1_000_000:
      continue
    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
  return "\n".join(chunks)


def require(name: str, condition: bool, detail: str) -> bool:
  if condition:
    print(f"PASS {name}")
    return True
  print(f"FAIL {name}: {detail}")
  return False


AUTO_TUNER_DEFAULTS = {
  "CarrotActiveSpeedControlEnabled": 0,
  "CarrotAutoTurnControlEnabled": 0,
  "CarrotLearningActive": 0,
  "CarrotLearningAutoApply": 0,
  "CarrotLearningApply": 0,
  "CarrotLearningIgnore": 0,
  "CarrotLearningClear": 0,
  "CarrotLearningPopupReady": 0,
  "CarrotPhoneSpeedLimit": 0,
  "CarrotPhoneSpeedLimitEnabled": 1,
  "CarrotPhoneSpeedLimitUpdatedAt": 0,
  "CarrotMapOverlayEnabled": 0,
  "CarrotNavigationEvent": "{}",
  "CarrotTrafficStopEnabled": 0,
  "CarrotTunerApplyLat": 1,
  "CarrotTunerApplyLong": 1,
  "CarrotTunerFactoryReset": 0,
  "ExperimentalMode": 0,
  "ExperimentalModeConfirmed": 0,
  "FishopAutoOvertakeEnabled": 0,
  "IsMetric": 1,
  "IsOnroad": 0,
  "OffroadMode": 0,
  "OpenpilotEnabledToggle": 1,
  "SpeedLimitMode": 1,
  "SpeedLimitOffsetType": 0,
  "SpeedLimitPolicy": 5,
  "SpeedLimitValueOffset": 0,
  "SshEnabled": 0,
  "CruiseMaxVals0": 160,
  "CruiseMaxVals1": 200,
  "CruiseMaxVals2": 160,
  "CruiseMaxVals3": 130,
  "CruiseMaxVals4": 110,
  "CruiseMaxVals5": 95,
  "CruiseMaxVals6": 80,
  "DynamicTFollow": 0,
  "JLeadFactor3": 0,
  "PathOffset": 0,
  "SteerActuatorDelay": 0,
  "SteerRatioRate": 100,
  "StopDistanceCarrot": 550,
  "TFollowDecelBoost": 10,
  "TFollowGap1": 110,
  "TFollowGap2": 120,
  "TFollowGap3": 140,
  "TFollowGap4": 160,
}


class FakeParams:
  shared_store: dict[str, bytes] = {}

  @classmethod
  def reset(cls) -> None:
    cls.shared_store = {key: str(value).encode("utf-8") for key, value in AUTO_TUNER_DEFAULTS.items()}

  def __init__(self):
    if not self.shared_store:
      self.reset()
    self.store = self.shared_store

  def get(self, key, *args, **_kwargs):
    return self.store.get(key)

  def get_int(self, key):
    raw = self.get(key)
    try:
      return int((raw or b"0").decode("utf-8"))
    except Exception:
      return 0

  def get_bool(self, key):
    raw = self.get(key)
    if raw is None:
      return False
    try:
      return raw.decode("utf-8").strip().lower() in ("1", "true", "on", "yes")
    except Exception:
      return False

  def put(self, key, value):
    if isinstance(value, bytes):
      self.store[key] = value
    elif isinstance(value, (dict, list)):
      self.store[key] = json.dumps(value, separators=(",", ":")).encode("utf-8")
    else:
      self.store[key] = str(value).encode("utf-8")

  def put_int(self, key, value):
    self.put(key, str(int(value)))

  def put_bool(self, key, value):
    self.put(key, "1" if value else "0")

  def put_float(self, key, value):
    self.put(key, f"{float(value):.6f}")

  def remove(self, key):
    self.store.pop(key, None)


def import_file(module_name: str, rel: str):
  spec = importlib.util.spec_from_file_location(module_name, str(ROOT / rel))
  if spec is None or spec.loader is None:
    raise RuntimeError(f"unable to import {rel}")
  module = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = module
  spec.loader.exec_module(module)
  return module


def check_carrot_learning_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    learning = import_file("alpha_carrot_learning_static_check", "selfdrive/carrot/carrot_learning.py")
    learner = learning.CarrotLearner()

    learner.update(80, True, True, False, lead_drel=30, lead_v_kph=70, gas_val=0.3)
    if learner.params.get("CarrotLearningData") is not None:
      return False, "inactive learner wrote CarrotLearningData"

    learner.params.put_bool("CarrotLearningActive", True)
    for _ in range(160):
      learner.update(80, True, True, False, lead_drel=40, lead_v_kph=75, gas_val=0.4)
    learner.update(0, False, False, True)

    raw = learner.params.get("CarrotLearningRecommend")
    if not raw:
      return False, "active learner did not create a recommendation"
    payload = json.loads(raw.decode("utf-8"))
    if "CruiseMaxVals4" not in payload.get("recommendations", {}):
      return False, "learner recommendation missing CruiseMaxVals4"
    if learner.params.get_int("CruiseMaxVals4") != 110:
      return False, "learner changed target params before apply"

    learner.params.put_bool("IsOnroad", True)
    learner.params.put_bool("CarrotLearningApply", True)
    learner.update(0, False, False, False)
    if learner.params.get_int("CruiseMaxVals4") != 110:
      return False, "learner applied recommendations while IsOnroad=1"
    if learner.params.get_bool("CarrotLearningApply"):
      return False, "CarrotLearningApply did not reset after blocked onroad apply"
    if not learner.params.get("CarrotLearningRecommend"):
      return False, "blocked onroad apply cleared the pending recommendation"

    learner.params.put_bool("IsOnroad", False)
    learner.params.put_bool("CarrotLearningApply", True)
    learner.update(0, False, False, False)
    if learner.params.get_int("CruiseMaxVals4") <= 110:
      return False, "offroad manual apply did not apply recommendation"
    if learner.params.get("CarrotLearningRecommend"):
      return False, "manual apply did not clear pending recommendation"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_phone_speed_limit_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_static_check", "selfdrive/carrot/carrot_server.py")
    result = server.set_phone_speed_limit({"speedLimit": 50, "source": "navipilot"})
    if not result.get("accepted"):
      return False, "phone speed endpoint did not accept a normal speed limit"
    raw_speed = FakeParams.shared_store.get("CarrotPhoneSpeedLimit", b"0").decode("utf-8")
    if abs(float(raw_speed) - 13.888889) > 0.001:
      return False, f"phone speed endpoint wrote {raw_speed}, expected m/s for 50 kph"
    raw_source = FakeParams.shared_store.get("CarrotPhoneSpeedLimitSource", b"").decode("utf-8")
    if raw_source != "navipilot":
      return False, "phone speed endpoint did not preserve the local source label"
    state = server.phone_speed_state()
    if not state.get("fresh") or state.get("speedLimitKph") != 50.0:
      return False, "phone speed state did not report fresh 50 kph data"

    server.set_phone_speed_limit({"nRoadLimitSpeed": 0, "nSdiSpeedLimit": 40, "source": "apn"})
    state = server.phone_speed_state()
    if not state.get("fresh") or state.get("speedLimitKph") != 40.0 or state.get("source") != "apn":
      return False, "phone speed endpoint did not skip zero road limit and use SDI fallback"

    server.set_phone_speed_limit({"action": "clear"})
    state = server.phone_speed_state()
    if state.get("fresh") or state.get("speedLimitMS") != 0.0:
      return False, "phone speed clear action did not invalidate the phone source"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_params_api_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_params_static_check", "selfdrive/carrot/carrot_server.py")
    state = server.params_bulk_state(["ExperimentalMode", "OffroadMode", "AlwaysOffroad", "DeviceType"])
    if not state.get("hasParams"):
      return False, "params bulk state did not report fake Params"
    values = state.get("values", {})
    writable = state.get("writable", {})
    if values.get("ExperimentalMode") is not False or writable.get("ExperimentalMode") is not True:
      return False, "ExperimentalMode was not exposed as a writable bool"
    if values.get("OffroadMode") is not False or writable.get("OffroadMode") is not False:
      return False, "OffroadMode must be read-only through local API"
    if values.get("AlwaysOffroad") != 0 or writable.get("AlwaysOffroad") is not False:
      return False, "legacy unknown AlwaysOffroad must only read as an inert default"
    if values.get("DeviceType") != "unknown" or writable.get("DeviceType") is not False:
      return False, "DeviceType must be a read-only virtual value"

    result = server.set_param_from_api("ExperimentalMode", 1)
    if not result.get("changed") or FakeParams.shared_store.get("ExperimentalMode") != b"1":
      return False, "param_set did not write ExperimentalMode"
    unchanged = server.set_param_from_api("ExperimentalMode", True)
    if unchanged.get("changed"):
      return False, "same-value param_set should report unchanged"
    server.set_param_from_api("SpeedLimitMode", 3)
    if FakeParams.shared_store.get("SpeedLimitMode") != b"2":
      return False, "SpeedLimitMode must clamp local API writes to warning, not assist"

    for blocked_name in ("OffroadMode", "CarrotTrafficStopEnabled", "FishopAutoOvertakeEnabled"):
      try:
        server.set_param_from_api(blocked_name, 1)
        return False, f"{blocked_name} should be read-only through local API"
      except ValueError:
        pass

    FakeParams.shared_store["IsOnroad"] = b"1"
    try:
      server.set_param_from_api("ExperimentalMode", 0)
      return False, "onroad param change was not blocked"
    except RuntimeError:
      pass
    unchanged_onroad = server.set_param_from_api("ExperimentalMode", True)
    if unchanged_onroad.get("changed"):
      return False, "same-value onroad write probe should remain unchanged"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_navigation_event_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_navigation_static_check", "selfdrive/carrot/carrot_server.py")
    payload = {
      "carrotIndex": 7,
      "carrotCmd": "OVERTAKE",
      "carrotArg": "left",
      "nRoadLimitSpeed": 0,
      "nSdiSpeedLimit": 60,
      "nSdiDist": 240,
      "nTBTDist": 500,
      "szTBTMainTextNext": "static check",
      "latitude": 1.234567,
      "longitude": 2.345678,
    }
    result = server.record_navigation_event(payload, "udp-7706")
    event = result.get("event", {})
    if not result.get("recorded") or not isinstance(event, dict):
      return False, "navigation event was not recorded"
    if not event.get("commandIgnored") or not event.get("highRiskCommandSeen"):
      return False, "high-risk navigation command was not recorded as ignored evidence"
    if event.get("speedLimitKph") != 60.0 or event.get("speedLimitSourceField") != "nSdiSpeedLimit":
      return False, "navigation event did not use SDI speed fallback"
    raw_speed = FakeParams.shared_store.get("CarrotPhoneSpeedLimit", b"0").decode("utf-8")
    if abs(float(raw_speed) - 16.666667) > 0.001:
      return False, "navigation event did not update phone speed limit in m/s"
    raw_event = json.loads(FakeParams.shared_store.get("CarrotNavigationEvent", b"{}").decode("utf-8"))
    if raw_event.get("ignoredCommand") != "OVERTAKE":
      return False, "CarrotNavigationEvent did not persist ignored command evidence"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_status_broadcast_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_status_static_check", "selfdrive/carrot/carrot_server.py")

    class Obj:
      def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    class FakeSm:
      alive = {
        "carState": True,
        "selfdriveState": True,
        "controlsState": True,
        "longitudinalPlanSP": True,
        "carStateSP": True,
      }

      def __init__(self):
        self.messages = {
          "carState": Obj(vEgoCluster=10.0, vEgo=9.0, vCruiseCluster=88.0, vCruise=87.0,
                          cruiseState=Obj(speedCluster=25.0, speed=24.0), standstill=False, canValid=True),
          "selfdriveState": Obj(active=True, enabled=True),
          "controlsState": Obj(deprecated=Obj(vCruiseCluster=0.0, vCruise=0.0)),
          "longitudinalPlanSP": Obj(speedLimit=Obj(resolver=Obj(speedLimitValid=True, speedLimitFinal=20.0,
                                                                 speedLimit=18.0, sourceLabel="phone"))),
          "carStateSP": Obj(speedLimit=19.0),
        }

      def __getitem__(self, service):
        return self.messages[service]

    runtime = server.update_messaging_status_from_sm(FakeSm())
    if runtime.get("vEgoKph") != 36.0 or runtime.get("vCruiseKph") != 88.0:
      return False, "messaging status helper did not derive car speed or cruise speed"
    if runtime.get("carCruiseSpeedKph") != 90.0 or runtime.get("speedLimitKph") != 72.0:
      return False, "messaging status helper did not derive cluster cruise or speed-limit state"
    if runtime.get("active") is not True or runtime.get("enabled") is not True or runtime.get("canValid") is not True:
      return False, "messaging status helper did not derive selfdrive/CAN state"

    server.record_navigation_event({
      "nRoadLimitSpeed": 0,
      "nSdiSpeedLimit": 60,
      "nSdiDist": 240,
      "nTBTDist": 500,
      "nTBTTurnType": 12,
      "szTBTMainTextNext": "status check",
    }, "udp-7706")
    payload = server.build_status_payload({
      "available": True,
      "lastUpdateAt": 1234.0,
      "vEgoKph": 48.6,
      "vCruiseKph": 82.0,
      "carCruiseSpeedKph": 80.0,
      "active": True,
      "enabled": True,
      "standstill": False,
      "canValid": True,
      "speedLimitKph": 60.0,
      "speedLimitSource": "phone",
    })
    for key in ("Carrot2", "IsOnroad", "active", "v_ego_kph", "v_cruise_kph", "carcruiseSpeed", "tbt_dist", "sdi_dist", "xState", "trafficState"):
      if key not in payload:
        return False, f"status payload missing {key}"
    if payload.get("active") is not True or payload.get("v_ego_kph") != 48.6 or payload.get("v_cruise_kph") != 82.0:
      return False, "status payload did not expose runtime messaging state"
    if payload.get("carcruiseSpeed") != 80.0 or payload.get("speedLimitKph") != 60.0 or payload.get("speedLimitSource") != "phone":
      return False, "status payload did not expose cruise/speed-limit messaging state"
    if payload.get("messagingAvailable") is not True or payload.get("messagingLastUpdateAt") != 1234.0:
      return False, "status payload did not expose messaging evidence"
    if payload.get("tbt_dist") != 500 or payload.get("sdi_dist") != 240:
      return False, "status payload did not expose latest navigation distances"
    if payload.get("sdi_speed") != 60 or payload.get("phoneSpeedLimitKph") != 60.0:
      return False, "status payload did not expose latest SDI/phone speed"
    if payload.get("xState") != 0 or payload.get("trafficState") != 0:
      return False, "xState and trafficState must stay inert until Carrot control migration"
    if payload.get("controlOutput") is not False:
      return False, "status payload must explicitly remain read-only"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def main() -> int:
  failures = 0

  process_config = read("system/manager/process_config.py")
  for proc_name in (
    "manage_athenad",
    '"uploader"',
    "manage_sunnylinkd",
    "sunnylink_registration_manager",
    "statsd_sp",
    "backup_manager",
    "sunnylink_uploader",
  ):
    failures += not require(
      f"cloud process disabled: {proc_name}",
      proc_name not in process_config,
      "process_config.py still references a disabled cloud/upload process",
    )
  failures += not require("models_manager only offroad", 'PythonProcess("models_manager", "sunnypilot.models.manager", only_offroad)' in process_config,
                          "models_manager must remain an offroad-only process")
  failures += not require("stock modeld guarded by stock runner", 'PythonProcess("modeld", "selfdrive.modeld.modeld", and_(only_onroad, is_stock_model))' in process_config,
                          "stock modeld must only run when the active runner is stock")
  failures += not require("tinygrad modeld guarded by tinygrad runner", 'NativeProcess("modeld_tinygrad", "sunnypilot/modeld_v2", ["./modeld"], and_(only_onroad, is_tinygrad_model))' in process_config,
                          "modeld_tinygrad must only run onroad when the active runner is tinygrad")
  failures += not require("local statsd retained", 'PythonProcess("statsd", "system.statsd", always_run)' in process_config,
                          "local system.statsd should stay available for local-only stats evidence")
  failures += not require("local carrot web retained", 'PythonProcess("carrot_server", "selfdrive.carrot.carrot_server", always_run)' in process_config,
                          "local Carrot Web server must be registered as an always-run local process")

  params = read("common/params_keys.h")
  failures += not require("OffroadMode param exists", '{"OffroadMode", {CLEAR_ON_MANAGER_START, BOOL}}' in params,
                          "OffroadMode must be the only Always Offroad param")
  failures += not require("no AlwaysOffline alias", "AlwaysOffline" not in params and "AlwaysOffroad" not in params,
                          "do not add confusing AlwaysOffline/AlwaysOffroad aliases in alpha")
  failures += not require("Sunnylink default off", '{"SunnylinkEnabled", {PERSISTENT, BOOL, "0"}}' in params,
                          "SunnylinkEnabled must default to 0")
  failures += not require("OnroadUploads default off", '{"OnroadUploads", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "OnroadUploads must default to 0 even though uploader is removed")
  failures += not require("CarrotMapOverlay default off", '{"CarrotMapOverlayEnabled", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "CarrotMapOverlayEnabled must default to 0")
  failures += not require("Carrot learning active default off", '{"CarrotLearningActive", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "CarrotLearningActive must default to 0")
  failures += not require("Carrot learning auto-apply default off", '{"CarrotLearningAutoApply", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "CarrotLearningAutoApply must default to 0")
  for key in (
    "CarrotLearningData",
    "CarrotLearningRecommend",
    "CarrotLearningPopupReady",
    "CarrotLearningHistory",
    "CarrotLearningPopupSource",
    "CarrotLearningApply",
    "CarrotLearningIgnore",
    "CarrotLearningClear",
    "CarrotTunerApplyLat",
    "CarrotTunerApplyLong",
    "CarrotTunerFactoryReset",
    "CarrotDSPRecommend",
  ):
    failures += not require(f"Auto-Tuner param exists: {key}", f'{{"{key}", ' in params,
                            f"{key} must be registered for Auto-Tuner migration")
  for key in (
    "CruiseMaxVals0",
    "CruiseMaxVals1",
    "CruiseMaxVals2",
    "CruiseMaxVals3",
    "CruiseMaxVals4",
    "CruiseMaxVals5",
    "CruiseMaxVals6",
    "TFollowGap1",
    "TFollowGap2",
    "TFollowGap3",
    "TFollowGap4",
    "JLeadFactor3",
    "PathOffset",
    "SteerActuatorDelay",
    "SteerRatioRate",
    "DynamicTFollow",
    "TFollowDecelBoost",
    "StopDistanceCarrot",
  ):
    failures += not require(f"Auto-Tuner target param exists: {key}", f'{{"{key}", ' in params,
                            f"{key} must be registered before Carrot control migration")
  failures += not require("Carrot phone limit enabled", '{"CarrotPhoneSpeedLimitEnabled", {PERSISTENT | BACKUP, BOOL, "1"}}' in params,
                          "CarrotPhoneSpeedLimitEnabled must exist and default to 1")
  failures += not require("Carrot navigation event param exists", '{"CarrotNavigationEvent", {CLEAR_ON_MANAGER_START, JSON}}' in params,
                          "CarrotNavigationEvent must record the latest local navigation input and clear on manager start")
  failures += not require("SpeedLimitPolicy phone priority default", '{"SpeedLimitPolicy", {PERSISTENT | BACKUP, INT, "5"}}' in params,
                          "SpeedLimitPolicy must default to phone_priority")
  failures += not require("SpeedLimitOffsetType default off", '{"SpeedLimitOffsetType", {PERSISTENT | BACKUP, INT, "0"}}' in params,
                          "SpeedLimitOffsetType must default to off")
  failures += not require("SpeedLimitValueOffset default zero", '{"SpeedLimitValueOffset", {PERSISTENT | BACKUP, INT, "0"}}' in params,
                          "SpeedLimitValueOffset must default to 0")
  for key in (
    "FishopAutoOvertakeEnabled",
    "FishopLaneCurveEnabled",
    "FishopLidarBlindspotEnabled",
    "FishopLidarLaneDataEnabled",
  ):
    failures += not require(f"{key} default off", f'{{"{key}", {{PERSISTENT | BACKUP, BOOL, "0"}}}}' in params,
                            f"{key} must exist and default to 0")

  fishop_hardware = read("selfdrive/carrot/fishop_hardware.py")
  carrot_learning = read("selfdrive/carrot/carrot_learning.py")
  carrot_server = read("selfdrive/carrot/carrot_server.py")
  fishop_sample = read("scripts/personal/fishop_hardware_sample.py")
  alpha_snapshot = read("scripts/personal/sunnypilot_c3_alpha_snapshot.py")
  failures += not require("Auto-Tuner learner module exists", "class CarrotLearner" in carrot_learning
                          and "def apply_recommendations" in carrot_learning,
                          "CarrotLearner core module must exist in alpha")
  failures += not require("Auto-Tuner learner default uses bool gate", 'get_bool("CarrotLearningActive")' in carrot_learning,
                          "CarrotLearner must use the alpha bool default gate")
  failures += not require("Auto-Tuner apply blocked onroad", 'get_bool("IsOnroad")' in carrot_learning
                          and "if self.is_onroad()" in carrot_learning,
                          "CarrotLearner must not apply recommendations while onroad")
  ok, detail = check_carrot_learning_runtime()
  failures += not require("Auto-Tuner runtime guard", ok, detail or "runtime guard check failed")
  failures += not require("Carrot Web local server exists", "LOCAL_WEB_PORT = 7000" in carrot_server
                          and "def make_app" in carrot_server and "web.run_app" in carrot_server,
                          "carrot_server must provide the local port-7000 aiohttp service")
  for route in ("/api/health", "/api/params_bulk", "/api/param_set", "/api/status_broadcast", "/api/carrot_learning", "/api/fishop_hardware", "/api/navigation_event", "/api/phone_speed_limit"):
    failures += not require(f"Carrot Web route exists: {route}", route in carrot_server,
                            f"carrot_server missing {route}")
  failures += not require("Carrot Web params API whitelist", "PARAM_API_DEFS" in carrot_server
                          and '"ExperimentalMode": {"type": "bool", "default": False, "writable": True}' in carrot_server
                          and '"OffroadMode": {"type": "bool", "default": False, "writable": False}' in carrot_server
                          and '"FishopAutoOvertakeEnabled": {"type": "bool", "default": False, "writable": False}' in carrot_server,
                          "Carrot Web params API must expose only an explicit whitelist and keep high-risk params read-only")
  failures += not require("Carrot Web params API blocks onroad changes", 'params.get_bool("IsOnroad") and changed' in carrot_server
                          and "Cannot change params while onroad" in carrot_server,
                          "param_set must reject changed values while onroad")
  failures += not require("Carrot Web params API clamps active speed mode", '"SpeedLimitMode": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 2}' in carrot_server,
                          "local param_set must not enable SpeedLimitMode assist through the phone API")
  ok, detail = check_params_api_runtime()
  failures += not require("Carrot Web params API runtime", ok, detail or "params API runtime check failed")
  failures += not require("Carrot Web status broadcast exists", "STATUS_BROADCAST_PORT = 7705" in carrot_server
                          and "STATUS_BROADCAST_TARGETS" in carrot_server
                          and "def build_status_payload" in carrot_server
                          and "status_broadcast_loop" in carrot_server,
                          "Carrot Web must provide a local UDP 7705 status broadcaster for Navipilot")
  failures += not require("Carrot Web status broadcast reads messaging",
                          "MESSAGING_STATUS_SERVICES" in carrot_server
                          and '"carState"' in carrot_server and '"selfdriveState"' in carrot_server
                          and '"longitudinalPlanSP"' in carrot_server and '"carStateSP"' in carrot_server
                          and "from cereal import messaging" in carrot_server
                          and "messaging.SubMaster(list(MESSAGING_STATUS_SERVICES))" in carrot_server
                          and "update_messaging_status_from_sm" in carrot_server,
                          "UDP 7705 status broadcast must read carState/selfdriveState/speed-limit state through a local SubMaster cache")
  for key in ("Carrot2", "IsOnroad", "active", "v_ego_kph", "v_cruise_kph", "carcruiseSpeed", "tbt_dist", "sdi_dist", "xState", "trafficState"):
    failures += not require(f"7705 status key exists: {key}", f'"{key}"' in carrot_server,
                            f"UDP 7705 status broadcast must include {key}")
  failures += not require("Carrot Web status broadcast local-only", "255.255.255.255" in carrot_server
                          and "127.0.0.1" in carrot_server and "allow_broadcast=True" in carrot_server
                          and "controlOutput" in carrot_server,
                          "UDP 7705 broadcast must stay local/LAN and explicitly read-only")
  ok, detail = check_status_broadcast_runtime()
  failures += not require("Carrot Web status broadcast runtime", ok, detail or "status broadcast runtime check failed")
  failures += not require("Carrot Web navigation UDP input", "NAVIGATION_UDP_PORT = 7706" in carrot_server
                          and "class NavigationUdpProtocol" in carrot_server
                          and "record_navigation_event(payload, \"udp-7706\")" in carrot_server,
                          "Carrot Web must listen for local Navipilot/APN UDP 7706 navigation JSON")
  failures += not require("Carrot Web navigation input remains evidence-only", "CarrotNavigationEvent" in carrot_server
                          and "commandIgnored" in carrot_server and "highRiskCommandSeen" in carrot_server
                          and "HIGH_RISK_NAV_COMMANDS" in carrot_server,
                          "navigation input must record commands as ignored evidence, not execute them")
  for forbidden in ("PubMaster", "CarControl", "sendcan", "desire_helper", "LateralPlan"):
    failures += not require(f"Carrot Web navigation omits control output {forbidden}", forbidden not in carrot_server,
                            "navigation UDP/API input must not publish controls or touch lane-change/planner outputs")
  ok, detail = check_navigation_event_runtime()
  failures += not require("Carrot Web navigation runtime", ok, detail or "navigation runtime check failed")
  failures += not require("Carrot Web phone speed API writes resolver params",
                          "def set_phone_speed_limit" in carrot_server
                          and "CarrotPhoneSpeedLimitUpdatedAt" in carrot_server
                          and "CarrotPhoneSpeedLimitSource" in carrot_server
                          and "KPH_TO_MS" in carrot_server
                          and "params.put(key, float(value))" in carrot_server,
                          "Carrot Web must expose a local phone speed API that writes resolver params in m/s")
  failures += not require("Carrot Web phone speed API reports freshness",
                          "PHONE_SPEED_LIMIT_MAX_AGE_S = 10.0" in carrot_server
                          and '"fresh": fresh' in carrot_server,
                          "Carrot Web phone speed state must report the same freshness window as the resolver")
  ok, detail = check_phone_speed_limit_runtime()
  failures += not require("Carrot Web phone speed runtime", ok, detail or "phone speed runtime check failed")
  failures += not require("Carrot Web blocks onroad Auto-Tuner apply", 'params.get_bool("IsOnroad")' in carrot_server
                          and "Cannot apply Auto-Tuner recommendations while onroad" in carrot_server,
                          "Carrot Web must refuse Auto-Tuner apply while onroad")
  for forbidden in ("requests.", "urllib.", "websocket", "ClientSession", "common.api", "SunnylinkApi", "DongleId"):
    failures += not require(f"Carrot Web omits cloud client token {forbidden}", forbidden not in carrot_server,
                            "local Carrot Web must not include outbound cloud/client code")
  for forbidden in ("subprocess", "tmux", "terminal", "shell=True", "os.system"):
    failures += not require(f"Carrot Web alpha omits high-risk tool {forbidden}", forbidden not in carrot_server,
                            "alpha Carrot Web should not expose terminal/tools before explicit migration gates")
  failures += not require("fishop hardware read-only module exists", "class FishopHardwareState" in fishop_hardware
                          and "CONTROL_OUTPUT_ENABLED = False" in fishop_hardware,
                          "fishop hardware parser must exist and remain read-only")
  for forbidden in ("socket", "PubMaster", "SubMaster", "CarControl", "CANParser", "sendto", ".bind(", "desire_helper", "blinker_ctrl"):
    failures += not require(f"fishop hardware parser omits {forbidden}", forbidden not in fishop_hardware,
                            "fishop hardware parser must not open network sockets, publish controls, or touch lane-change control")
  failures += not require("fishop hardware sample tool exists", "FishopHardwareState" in fishop_sample and "SAMPLE_PAYLOADS" in fishop_sample,
                          "fishop hardware sample tool must normalize captured JSON payloads")
  failures += not require("alpha snapshot tool exists", "CarrotPilot-C3-ESCC SunnyPilot Alpha Snapshot" in alpha_snapshot
                          and "MESSAGING_SERVICES" in alpha_snapshot and "fishopHardware" in alpha_snapshot,
                          "alpha snapshot must collect model, process, params, and fishop evidence")
  failures += not require("alpha snapshot records Auto-Tuner summary", '"CarrotLearningActive"' in alpha_snapshot
                          and '"autoTuner"' in alpha_snapshot and "summarize_auto_tuner" in alpha_snapshot,
                          "alpha snapshot must summarize Auto-Tuner state")
  failures += not require("alpha snapshot records navigation event", '"CarrotNavigationEvent"' in alpha_snapshot,
                          "alpha snapshot must include the latest sanitized navigation event")
  failures += not require("alpha snapshot records carrot_server process", '"carrot_server"' in alpha_snapshot,
                          "alpha snapshot must report local Carrot Web process state")
  for service_name in ("modelV2", "drivingModelData", "cameraOdometry", "modelManagerSP", "longitudinalPlanSP", "carStateSP", "pandaStates"):
    failures += not require(f"alpha snapshot samples {service_name}", f'"{service_name}"' in alpha_snapshot,
                            f"alpha snapshot must sample {service_name}")
  failures += not require("alpha snapshot records panda output state", "safetyModel" in alpha_snapshot
                          and "controlsAllowed" in alpha_snapshot and "powerSaveEnabled" in alpha_snapshot
                          and "harnessStatus" in alpha_snapshot,
                          "alpha snapshot must report panda safety/output state")
  for disabled_process in ("manage_athenad", "uploader", "manage_sunnylinkd", "sunnylink_registration_manager", "statsd_sp", "backup_manager"):
    failures += not require(f"alpha snapshot checks cloud process {disabled_process}", disabled_process in alpha_snapshot,
                            f"alpha snapshot must report disabled cloud process {disabled_process}")

  settings = read("selfdrive/ui/sunnypilot/layouts/settings/settings.py")
  device_settings = read("selfdrive/ui/sunnypilot/layouts/settings/device.py")
  settings_ui_device = read("sunnypilot/sunnylink/settings_ui_src/pages/device.yaml")
  settings_ui_json = read("sunnypilot/sunnylink/settings_ui.json")
  mici_settings = read("selfdrive/ui/sunnypilot/mici/layouts/settings.py")
  main_onboarding = read("selfdrive/ui/layouts/onboarding.py")
  mici_onboarding = read("selfdrive/ui/mici/layouts/onboarding.py")
  hardwared = read("system/hardware/hardwared.py")
  panda_safety = read("selfdrive/pandad/panda_safety.cc")
  pandad = read("selfdrive/pandad/pandad.cc")
  system_statsd = read("system/statsd.py")
  failures += not require("Sunnylink panel removed", "SunnylinkLayout" not in settings and "SUNNYLINK" not in settings,
                          "Sunnylink panel is still wired into settings")
  failures += not require("MICI Sunnylink panel removed", "SunnylinkLayoutMici" not in mici_settings and "sunnylink_btn" not in mici_settings,
                          "MICI Sunnylink panel is still wired into settings")
  failures += not require("Onroad Uploads setting removed", "Onroad Uploads" not in device_settings,
                          "Device settings still expose Onroad Uploads")
  failures += not require("OnroadUploads removed from settings-ui", "OnroadUploads" not in settings_ui_device + settings_ui_json,
                          "settings-ui source or compiled JSON still exposes OnroadUploads")
  failures += not require("Sunnylink removed from settings-ui", all(key not in settings_ui_device + settings_ui_json for key in ("SunnylinkEnabled", "EnableSunnylinkUploader")),
                          "settings-ui must not expose Sunnylink cloud toggles")
  failures += not require("TICI onboarding skips Sunnylink", "SunnylinkOnboarding" not in main_onboarding,
                          "Main onboarding still imports Sunnylink onboarding")
  failures += not require("MICI onboarding skips Sunnylink", "SunnylinkConsentPage" not in mici_onboarding,
                          "MICI onboarding still imports Sunnylink consent")
  failures += not require("OffroadMode blocks onroad", 'offroad_mode = params.get_bool("OffroadMode")' in hardwared
                          and 'startup_conditions["not_always_offroad"] = not offroad_mode' in hardwared
                          and 'onroad_conditions["not_always_offroad"] = not offroad_mode' in hardwared,
                          "hardwared must use OffroadMode to keep the device offroad")
  failures += not require("OffroadMode forces panda no-output", 'params_.getBool("OffroadMode")' in panda_safety
                          and "always_offroad = panda_safety.getOffroadMode()" in pandad
                          and "&& !always_offroad" in pandad
                          and "SafetyModel::NO_OUTPUT" in pandad,
                          "pandad must drive panda to NO_OUTPUT while OffroadMode keeps ignition_local false")
  failures += not require("system statsd local-only", "sock.bind(STATS_SOCKET)" in system_statsd
                          and "atomic_write(stats_path)" in system_statsd
                          and all(token not in system_statsd for token in ("requests.", "urllib.", "websocket", "create_connection", "UPLOAD_SESS", "common.api")),
                          "system.statsd must remain local-only and must not upload over the network")
  overlay_sources = "\n".join((
    read_tree("selfdrive/carrot", (".py", ".html", ".js", ".json", ".yaml")),
    read_tree("selfdrive/ui", (".py", ".cc", ".h", ".html", ".js", ".json", ".yaml")),
  ))
  for token in ("mapbox.com", "api.mapbox", "mapboxgl", "MapboxGL", "dapi.kakao", "kakao.maps", "<iframe"):
    failures += not require(f"map overlay omits external loader {token}", token not in overlay_sources,
                            "CarrotMapOverlayEnabled defaults off, so UI/Carrot Web must not load external map SDKs or iframe overlays by default")

  values = read("opendbc_repo/opendbc/car/hyundai/values.py")
  car_fingerprints = read("opendbc_repo/opendbc/car/fingerprints.py")
  hyundai_fingerprints = read("opendbc_repo/opendbc/car/hyundai/fingerprints.py")
  fingerprints_ext = read("opendbc_repo/opendbc/sunnypilot/car/hyundai/fingerprints_ext.py")
  failures += not require("KIA_SELTOS_2023 exists", "KIA_SELTOS_2023 = HyundaiPlatformConfig" in values,
                          "KIA_SELTOS_2023 must be a normal SCC HyundaiPlatformConfig")
  failures += not require("KIA_SELTOS_2023 reuses Seltos specs", "KIA_SELTOS.specs" in values,
                          "KIA_SELTOS_2023 should reuse KIA_SELTOS specs")
  failures += not require("KIA_SELTOS_2023 manual mapping exists", '"KIA SELTOS 2023": HYUNDAI.KIA_SELTOS_2023' in car_fingerprints,
                          "KIA SELTOS 2023 manual mapping missing")
  failures += not require("KIA_SELTOS_2023 FW entry exists", "CAR.KIA_SELTOS_2023" in hyundai_fingerprints,
                          "KIA_SELTOS_2023 FW fingerprint entry missing")
  failures += not require("Seltos Non-SCC personal entry removed",
                          "KIA_SELTOS_2023_NON_SCC" not in values + car_fingerprints + hyundai_fingerprints + fingerprints_ext,
                          "KIA_SELTOS_2023_NON_SCC should not be selectable or auto-matched in this build")

  interface = read("opendbc_repo/opendbc/car/hyundai/interface.py")
  failures += not require("ESCC auto-detect preserved", "if ESCC_MSG in fingerprint[0]" in interface and "ENHANCED_SCC" in interface,
                          "0x2AB ESCC auto-detection missing")
  escc_surfaces = params + settings + device_settings + mici_settings + values + car_fingerprints + hyundai_fingerprints + fingerprints_ext
  failures += not require("no manual ESCC toggle", all(key not in escc_surfaces for key in ("EnableEscc", "EnableESCC", "ESCCEnabled")),
                          "ESCC must be detected from the 0x2AB hardware message, not exposed as a normal user toggle")

  models_helpers = read("sunnypilot/models/helpers.py")
  models_manager = read("sunnypilot/models/manager.py")
  failures += not require("model runner defaults stock", "runner_type = custom.ModelManagerSP.Runner.stock" in models_helpers,
                          "model runner must default to stock without a valid active bundle")
  failures += not require("invalid active bundle resets stock", 'params.remove("ModelManager_ActiveBundle")' in models_helpers
                          and "ModelRunnerTypeCache" in models_helpers and "Runner.stock" in models_helpers,
                          "invalid active bundle must clear active bundle and reset runner cache to stock")
  failures += not require("model manager validates active bundle", "validate_active_bundle(self.params, self.available_models)" in models_manager,
                          "models_manager must validate active bundle before publishing state")
  failures += not require("model download request cleared", 'self.params.remove("ModelManager_DownloadIndex")' in models_manager,
                          "models_manager must clear download request after handling it")

  try:
    from openpilot.selfdrive.carrot.fishop_hardware import FishopHardwareState
    fishop_state = FishopHardwareState()
    fishop_state.update_from_payload({"resp": "lane", "left_lane": 2, "right_lane": 1, "lineValid": True}, 1000.0)
    fishop_state.update_from_payload({"resp": "blindspot", "detect_side": 3, "lidar_lblind": True, "rf_drel": 4200}, 1000.0)
    fishop_state.update_from_payload({"resp": "overtake", "request": True, "direction": "left"}, 1000.0)
    fishop_snapshot = fishop_state.to_dict(1000.5)
    failures += not require("fishop parser preserves lane evidence", fishop_snapshot["lane"]["leftLine"] == 2
                            and fishop_snapshot["lane"]["rightLine"] == 1 and fishop_snapshot["lane"]["fresh"],
                            "fishop parser must expose lane evidence without using it for control")
    failures += not require("fishop parser preserves blindspot evidence", fishop_snapshot["blindspot"]["leftLidarBlind"]
                            and fishop_snapshot["blindspot"]["fresh"],
                            "fishop parser must expose blindspot evidence while fresh")
    failures += not require("fishop parser records overtake read-only", fishop_snapshot["overtake"]["commandSeen"]
                            and fishop_snapshot["overtake"]["readOnly"] and not fishop_snapshot["controlOutputEnabled"],
                            "fishop overtake input must be evidence-only and never enable control output")
    failures += not require("fishop parser reports sensor freshness", fishop_snapshot["sensorOnline"]
                            and fishop_snapshot["lastUpdateMonotonicSec"] == 1000.0
                            and fishop_snapshot["lane"]["lastUpdateMonotonicSec"] == 1000.0,
                            "fishop parser must expose sensorOnline and last-update evidence")
    stale_snapshot = fishop_state.to_dict(1003.0)
    failures += not require("fishop stale lane invalid", not stale_snapshot["lane"]["fresh"]
                            and not stale_snapshot["lane"]["lineValid"],
                            "stale fishop lane input must not stay valid")
    failures += not require("fishop stale blindspot clears active bits", not stale_snapshot["blindspot"]["fresh"]
                            and not stale_snapshot["blindspot"]["leftLidarBlind"],
                            "stale fishop blindspot input must not stay active")
  except Exception as exc:
    failures += not require("fishop parser import/sample", False, f"fishop parser import/sample failed: {exc}")

  custom_capnp = read("cereal/custom.capnp")
  resolver = read("sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_resolver.py")
  common = read("sunnypilot/selfdrive/controls/lib/speed_limit/common.py")
  planner = read("sunnypilot/selfdrive/controls/lib/longitudinal_planner.py")
  failures += not require("percentage speed offset exists", "percentage = 2" in common and "self.offset_value * 0.01 * self.speed_limit" in resolver,
                          "speed limit resolver must support percentage offsets")
  failures += not require("phone speed source schema", "phone @3;" in custom_capnp and "sourceLabel @9 :Text;" in custom_capnp,
                          "custom.capnp must expose phone source and sourceLabel")
  failures += not require("phone_priority policy exists", "phone_priority = 5" in common,
                          "speed limit policy enum must include phone_priority")
  failures += not require("phone resolver timeout", "PHONE_SPEED_LIMIT_MAX_AGE_S" in resolver and "CarrotPhoneSpeedLimitUpdatedAt" in resolver,
                          "resolver must reject stale phone speed data")
  failures += not require("phone source priority", "Policy.phone_priority: [SpeedLimitSource.phone, SpeedLimitSource.car, SpeedLimitSource.map]" in resolver,
                          "phone_priority must resolve phone, car, then map")
  failures += not require("source label published", "resolver.sourceLabel = self.resolver.source_label" in planner,
                          "longitudinal planner must publish resolver sourceLabel")

  return 1 if failures else 0


if __name__ == "__main__":
  raise SystemExit(main())
