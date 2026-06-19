#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PHASES = {
  "static",
  "parked",
  "model",
  "seltos-escc",
  "navipilot",
  "fishop",
  "release-review",
}


@dataclass
class CheckResult:
  name: str
  ok: bool
  detail: str = ""
  missing: bool = False


class EvidenceReport:
  def __init__(self) -> None:
    self.results: list[CheckResult] = []

  def require(self, name: str, condition: bool, detail: str = "", missing: bool = False) -> None:
    self.results.append(CheckResult(name=name, ok=bool(condition), detail=detail, missing=missing and not condition))

  def missing(self, name: str, detail: str) -> None:
    self.results.append(CheckResult(name=name, ok=False, detail=detail, missing=True))

  @property
  def failed(self) -> list[CheckResult]:
    return [result for result in self.results if not result.ok]

  def print(self) -> None:
    for result in self.results:
      status = "PASS" if result.ok else ("MISS" if result.missing else "FAIL")
      suffix = f": {result.detail}" if result.detail and not result.ok else ""
      print(f"{status} {result.name}{suffix}")


def load_json(path: Path) -> dict[str, Any]:
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except Exception as exc:
    raise SystemExit(f"cannot read snapshot JSON {path}: {exc}") from exc
  if not isinstance(data, dict):
    raise SystemExit(f"snapshot JSON must be an object: {path}")
  return data


def get(data: dict[str, Any], *path: str, default: Any = None) -> Any:
  value: Any = data
  for key in path:
    if not isinstance(value, dict) or key not in value:
      return default
    value = value[key]
  return value


def truthy(value: Any) -> bool:
  if isinstance(value, bool):
    return value
  if value is None:
    return False
  return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def phase_set(phases: Iterable[str]) -> set[str]:
  requested = set(phases)
  if not requested:
    requested = {"static"}
  if "release-review" in requested:
    requested.update({"static", "parked", "model", "seltos-escc", "navipilot", "fishop"})
  if any(phase in requested for phase in ("parked", "model", "seltos-escc", "navipilot", "fishop")):
    requested.add("static")
  return requested


def check_static(snapshot: dict[str, Any], report: EvidenceReport) -> None:
  report.require(
    "snapshot title",
    get(snapshot, "metadata", "title") == "CarrotPilot-C3-ESCC SunnyPilot Alpha Snapshot",
    "wrong or missing alpha snapshot metadata",
  )
  report.require("cloud processes absent", get(snapshot, "cloudGuard", "cloudForbiddenProcessesSeen") is False,
                 "disabled cloud/upload process was seen")
  process_available = get(snapshot, "process", "available") is True
  report.require("process snapshot available", process_available, "process list is missing", missing=not process_available)
  if process_available:
    report.require("process snapshot has no cloud process", get(snapshot, "process", "cloudForbiddenSeen") is False,
                   "cloudForbiddenSeen must be false")

  cloud_params = get(snapshot, "cloudGuard", "cloudParams", default={}) or {}
  enabled_cloud_params = [key for key, value in cloud_params.items() if truthy(value)]
  report.require("cloud params disabled", not enabled_cloud_params, "enabled cloud params: " + ", ".join(enabled_cloud_params))

  speed = get(snapshot, "speedLimitEvidence", default={}) or {}
  report.require("speed policy phone priority", speed.get("policyName") == "phone_priority",
                 f"policyName={speed.get('policyName')!r}")
  report.require("speed offset neutral", speed.get("offsetTypeName") == "off" and int(speed.get("offsetValue", 0) or 0) == 0,
                 f"offsetTypeName={speed.get('offsetTypeName')!r}, offsetValue={speed.get('offsetValue')!r}")

  feature_gates = get(snapshot, "carrotFeatureGates", default={}) or {}
  report.require("Carrot gates remain read-only", feature_gates.get("readOnly") is True
                 and feature_gates.get("controlOutput") is False
                 and feature_gates.get("controlOutputAllowed") is False,
                 "high-risk Carrot gates must not allow control output")
  for key, feature in (feature_gates.get("features") or {}).items():
    if isinstance(feature, dict):
      report.require(
        f"feature gate blocked: {key}",
        feature.get("readOnly") is True and feature.get("readyForControl") is False and feature.get("controlOutput") is False,
        "feature must stay evidence-only until real-car gates pass",
      )

  stages = get(snapshot, "fishopOvertakeStages", default={}) or {}
  report.require("fishop stages read-only", stages.get("readOnly") is True and stages.get("controlOutput") is False,
                 "fishop staged plan must be read-only")
  report.require("fishop implemented stages cannot output lateral control",
                 stages.get("allImplementedStagesNoControlOutput") is True,
                 "implemented fishop stages may not publish desire or lateral commands")


def check_parked(snapshot: dict[str, Any], report: EvidenceReport) -> None:
  local = get(snapshot, "process", "local", default={}) or {}
  for proc in ("manager", "updated", "models_manager", "carrot_server", "mapd", "sshd"):
    report.require(f"parked local process: {proc}", local.get(proc) is True,
                   f"{proc} not seen in process snapshot", missing=local.get(proc) is not True)

  carrot_web = get(snapshot, "carrotWeb", default={}) or {}
  report.require("Carrot Web available", carrot_web.get("available") is True,
                 "local 7000 Carrot Web did not respond", missing=carrot_web.get("available") is not True)
  report.require("Carrot Web read-only", carrot_web.get("controlOutput") is False,
                 "Carrot Web evidence must report controlOutput=false")


def check_model(snapshot: dict[str, Any], report: EvidenceReport) -> None:
  messaging = get(snapshot, "messaging", default={}) or {}
  valid = messaging.get("valid") if isinstance(messaging.get("valid"), dict) else {}
  updates = messaging.get("updates") if isinstance(messaging.get("updates"), dict) else {}
  report.require("messaging sampled", messaging.get("enabled") is True and messaging.get("ok") is True,
                 "run snapshot with --sample-seconds on the C3", missing=messaging.get("enabled") is not True)
  for service in ("modelV2", "drivingModelData", "cameraOdometry", "modelManagerSP"):
    seen = valid.get(service) is True or int(updates.get(service, 0) or 0) > 0
    report.require(f"model service observed: {service}", seen,
                   f"{service} not observed in messaging sample", missing=not seen)

  local = get(snapshot, "process", "local", default={}) or {}
  report.require("modeld process observed", local.get("modeld") is True or local.get("modeld_tinygrad") is True,
                 "neither stock modeld nor modeld_tinygrad was visible", missing=True)


def check_seltos_escc(snapshot: dict[str, Any], report: EvidenceReport) -> None:
  car_params = get(snapshot, "carParams", default={}) or {}
  cp_available = car_params.get("available") is True and not car_params.get("decodeError")
  report.require("CarParams decoded", cp_available, "CarParams missing or undecodable", missing=not cp_available)
  fingerprint = str(car_params.get("carFingerprint", ""))
  report.require("Seltos SCC fingerprint", "KIA_SELTOS" in fingerprint and car_params.get("dashcamOnly") is False,
                 f"carFingerprint={fingerprint!r}, dashcamOnly={car_params.get('dashcamOnly')!r}")
  report.require("openpilot longitudinal available", car_params.get("openpilotLongitudinalControl") is True,
                 "Seltos ESCC test path should prove longitudinal control availability")

  car_params_sp = get(snapshot, "carParamsSP", default={}) or {}
  sp_available = car_params_sp.get("available") is True and not car_params_sp.get("decodeError")
  report.require("CarParamsSP decoded", sp_available, "CarParamsSP missing or undecodable", missing=not sp_available)
  report.require("ESCC enhanced SCC detected", car_params_sp.get("enhancedSccDetected") is True,
                 f"flags={car_params_sp.get('flags')!r}")
  report.require("ESCC safety param set", car_params_sp.get("esccSafetyParamSet") is True,
                 f"safetyParam={car_params_sp.get('safetyParam')!r}")


def check_navipilot(snapshot: dict[str, Any], report: EvidenceReport) -> None:
  live = get(snapshot, "navipilotLiveCheck", default={}) or {}
  report.require("Navipilot live check requested", live.get("requested") is True,
                 "run snapshot with --navipilot-live-check", missing=live.get("requested") is not True)
  report.require("Navipilot live check overall OK", live.get("overallOk") is True,
                 f"overallOk={live.get('overallOk')!r}")
  report.require("Navipilot live check local only", live.get("localOnly") is True,
                 "localOnly must be true")
  report.require("Navipilot live check no cloud", live.get("cloudServices") is False,
                 "cloudServices must be false")
  report.require("Navipilot live check no control output", live.get("controlOutput") is False,
                 "controlOutput must be false")


def check_fishop(snapshot: dict[str, Any], report: EvidenceReport, require_release: bool) -> None:
  gate = get(snapshot, "fishopReleaseGate", default={}) or {}
  checks = gate.get("checks") if isinstance(gate.get("checks"), dict) else {}
  for name in ("fishopParsed", "fishopSensorFresh", "fishopOvertakeDisplayOnly"):
    check = checks.get(name) if isinstance(checks.get(name), dict) else {}
    report.require(f"fishop gate: {name}", check.get("ok") is True,
                   check.get("reason") or "fishop check did not pass", missing=check.get("status") == "missing")
  if require_release:
    report.require("fishop release gate ready", gate.get("readyForNextStageReview") is True,
                   "fishopReleaseGate must be ready before promotion")


def check_snapshot(snapshot: dict[str, Any], phases: Iterable[str]) -> EvidenceReport:
  requested = phase_set(phases)
  report = EvidenceReport()
  if "static" in requested:
    check_static(snapshot, report)
  if "parked" in requested:
    check_parked(snapshot, report)
  if "model" in requested:
    check_model(snapshot, report)
  if "seltos-escc" in requested:
    check_seltos_escc(snapshot, report)
  if "navipilot" in requested:
    check_navipilot(snapshot, report)
  if "fishop" in requested:
    check_fishop(snapshot, report, require_release="release-review" in requested)
  return report


def good_snapshot() -> dict[str, Any]:
  feature = {
    "readOnly": True,
    "readyForControl": False,
    "controlOutput": False,
    "enabledParam": False,
    "candidate": False,
  }
  return {
    "metadata": {"title": "CarrotPilot-C3-ESCC SunnyPilot Alpha Snapshot"},
    "cloudGuard": {
      "cloudForbiddenProcessesSeen": False,
      "cloudParams": {"SunnylinkEnabled": "0", "EnableSunnylinkUploader": "0", "OnroadUploads": "0"},
    },
    "process": {
      "available": True,
      "cloudForbiddenSeen": False,
      "local": {
        "manager": True,
        "updated": True,
        "models_manager": True,
        "carrot_server": True,
        "mapd": True,
        "sshd": True,
        "modeld": True,
        "modeld_tinygrad": False,
      },
    },
    "speedLimitEvidence": {"policyName": "phone_priority", "offsetTypeName": "off", "offsetValue": 0},
    "carrotFeatureGates": {
      "readOnly": True,
      "controlOutput": False,
      "controlOutputAllowed": False,
      "features": {"trafficStop": copy.deepcopy(feature), "fishopAutoOvertake": copy.deepcopy(feature)},
    },
    "fishopOvertakeStages": {
      "readOnly": True,
      "controlOutput": False,
      "allImplementedStagesNoControlOutput": True,
    },
    "carrotWeb": {"available": True, "controlOutput": False},
    "messaging": {
      "enabled": True,
      "ok": True,
      "valid": {"modelV2": True, "drivingModelData": True, "cameraOdometry": True, "modelManagerSP": True},
      "updates": {"modelV2": 4, "drivingModelData": 4, "cameraOdometry": 4, "modelManagerSP": 1},
    },
    "carParams": {
      "available": True,
      "carFingerprint": "KIA_SELTOS_2023",
      "dashcamOnly": False,
      "openpilotLongitudinalControl": True,
    },
    "carParamsSP": {
      "available": True,
      "flags": 1,
      "safetyParam": 1,
      "enhancedSccDetected": True,
      "esccSafetyParamSet": True,
    },
    "navipilotLiveCheck": {
      "requested": True,
      "overallOk": True,
      "localOnly": True,
      "cloudServices": False,
      "controlOutput": False,
    },
    "fishopReleaseGate": {
      "readyForNextStageReview": True,
      "checks": {
        "fishopParsed": {"ok": True, "status": "pass"},
        "fishopSensorFresh": {"ok": True, "status": "pass"},
        "fishopOvertakeDisplayOnly": {"ok": True, "status": "pass"},
      },
    },
  }


def run_self_test() -> int:
  good = good_snapshot()
  report = check_snapshot(good, ["release-review"])
  if report.failed:
    report.print()
    print("self-test good snapshot unexpectedly failed")
    return 1

  cases: list[tuple[str, tuple[str, ...], Any, list[str]]] = [
    ("cloud process", ("cloudGuard", "cloudForbiddenProcessesSeen"), True, ["static"]),
    ("control output", ("carrotFeatureGates", "features", "trafficStop", "controlOutput"), True, ["static"]),
    ("missing ESCC", ("carParamsSP", "enhancedSccDetected"), False, ["seltos-escc"]),
    ("navipilot cloud", ("navipilotLiveCheck", "cloudServices"), True, ["navipilot"]),
    ("fishop stale", ("fishopReleaseGate", "checks", "fishopSensorFresh", "ok"), False, ["fishop"]),
  ]
  for label, path, value, phases in cases:
    bad = copy.deepcopy(good)
    target = bad
    for key in path[:-1]:
      target = target[key]
    target[path[-1]] = value
    bad_report = check_snapshot(bad, phases)
    if not bad_report.failed:
      print(f"self-test case did not fail: {label}")
      return 1
  bad_model = copy.deepcopy(good)
  bad_model["messaging"]["valid"]["modelV2"] = False
  bad_model["messaging"]["updates"]["modelV2"] = 0
  bad_report = check_snapshot(bad_model, ["model"])
  if not bad_report.failed:
    print("self-test case did not fail: missing model")
    return 1
  print("OK: alpha evidence checker self-test passed")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate a SunnyPilot C3 alpha snapshot against parked and road-test evidence gates.")
  parser.add_argument("snapshot", nargs="?", type=Path, help="JSON from sunnypilot_c3_alpha_snapshot.py")
  parser.add_argument("--phase", choices=sorted(PHASES), action="append", default=[],
                      help="evidence phase to validate; may be repeated. default: static")
  parser.add_argument("--self-test", action="store_true", help="run synthetic self-tests")
  args = parser.parse_args()

  if args.self_test:
    return run_self_test()
  if args.snapshot is None:
    parser.error("snapshot JSON path is required unless --self-test is used")

  snapshot = load_json(args.snapshot)
  report = check_snapshot(snapshot, args.phase)
  print("SunnyPilot C3 alpha evidence check")
  print("snapshot:", args.snapshot)
  print("phases:", ", ".join(sorted(phase_set(args.phase))))
  report.print()
  if report.failed:
    print(f"FAILED: {len(report.failed)} check(s)")
    return 2
  print("OK: alpha evidence gates passed")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
