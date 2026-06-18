#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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

  params = read("common/params_keys.h")
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
  for key in (
    "FishopAutoOvertakeEnabled",
    "FishopLaneCurveEnabled",
    "FishopLidarBlindspotEnabled",
    "FishopLidarLaneDataEnabled",
  ):
    failures += not require(f"{key} default off", f'{{"{key}", {{PERSISTENT | BACKUP, BOOL, "0"}}}}' in params,
                            f"{key} must exist and default to 0")

  settings = read("selfdrive/ui/sunnypilot/layouts/settings/settings.py")
  device_settings = read("selfdrive/ui/sunnypilot/layouts/settings/device.py")
  mici_settings = read("selfdrive/ui/sunnypilot/mici/layouts/settings.py")
  main_onboarding = read("selfdrive/ui/layouts/onboarding.py")
  mici_onboarding = read("selfdrive/ui/mici/layouts/onboarding.py")
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

  custom_capnp = read("cereal/custom.capnp")
  resolver = read("sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_resolver.py")
  common = read("sunnypilot/selfdrive/controls/lib/speed_limit/common.py")
  planner = read("sunnypilot/selfdrive/controls/lib/longitudinal_planner.py")
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
