#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8")


def require(name: str, condition: bool, detail: str) -> bool:
  if condition:
    print(f"PASS {name}")
    return True
  print(f"FAIL {name}: {detail}")
  return False


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
  failures += not require("Carrot phone limit enabled", '{"CarrotPhoneSpeedLimitEnabled", {PERSISTENT | BACKUP, BOOL, "1"}}' in params,
                          "CarrotPhoneSpeedLimitEnabled must exist and default to 1")
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
  fishop_sample = read("scripts/personal/fishop_hardware_sample.py")
  alpha_snapshot = read("scripts/personal/sunnypilot_c3_alpha_snapshot.py")
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
