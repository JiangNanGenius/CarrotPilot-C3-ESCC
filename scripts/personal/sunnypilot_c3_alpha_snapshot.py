#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openpilot.selfdrive.carrot.fishop_hardware import normalize_fishop_payloads  # noqa: E402


PARAM_ROOTS = (
  Path("/data/params/d"),
  Path("/data/params"),
  Path("/persist/comma/params/d"),
)

SAFE_PARAM_KEYS = (
  "OffroadMode",
  "SunnylinkEnabled",
  "EnableSunnylinkUploader",
  "OnroadUploads",
  "CarrotMapOverlayEnabled",
  "CarrotPhoneSpeedLimitEnabled",
  "CarrotPhoneSpeedLimit",
  "CarrotPhoneSpeedLimitSource",
  "CarrotPhoneSpeedLimitUpdatedAt",
  "CarrotNavigationEvent",
  "CarrotLearningActive",
  "CarrotLearningApply",
  "CarrotLearningAutoApply",
  "CarrotLearningClear",
  "CarrotLearningIgnore",
  "CarrotLearningPopupReady",
  "CarrotLearningPopupSource",
  "CarrotTunerApplyLat",
  "CarrotTunerApplyLong",
  "CarrotTunerFactoryReset",
  "SpeedLimitPolicy",
  "SpeedLimitMode",
  "SpeedLimitOffsetType",
  "SpeedLimitValueOffset",
  "ModelRunnerTypeCache",
  "ModelManager_ActiveBundle",
  "FishopAutoOvertakeEnabled",
  "FishopLaneCurveEnabled",
  "FishopLidarBlindspotEnabled",
  "FishopLidarLaneDataEnabled",
)

BINARY_PARAM_KEYS = (
  "CarParams",
  "CarParamsCache",
  "CarParamsSP",
)

CLOUD_PROCESS_PATTERNS = {
  "athenad": r"(^|[ /])(manage_athenad|athenad)(\.py)?($|[ \t])",
  "uploader": r"(^|[ /])uploader($|[ \t])",
  "sunnylinkd": r"(^|[ /])(manage_sunnylinkd|sunnylinkd)(\.py)?($|[ \t])",
  "sunnylink_registration_manager": r"(^|[ /])sunnylink_registration_manager(\.py)?($|[ \t])",
  "statsd_sp": r"(^|[ /])statsd_sp(\.py)?($|[ \t])",
  "backup_manager": r"(^|[ /])backup_manager(\.py)?($|[ \t])",
}

LOCAL_PROCESS_PATTERNS = {
  "manager": r"(^|[ /])manager(\.py)?($|[ \t])",
  "updated": r"(^|[ /])updated(\.py)?($|[ \t])",
  "models_manager": r"(^|[ /])models_manager(\.py)?($|[ \t])",
  "carrot_server": r"(^|[ /])carrot_server(\.py)?($|[ \t])",
  "modeld": r"(^|[ /])modeld($|[ \t])",
  "modeld_tinygrad": r"(^|[ /])modeld_tinygrad($|[ \t])",
  "mapd": r"(^|[ /])mapd($|[ \t])",
  "sshd": r"(^|[ /])sshd($|[ \t])",
}

DEFAULT_FISHOP_JSONL = Path("/data/fishop_hardware.jsonl")
MESSAGING_SERVICES = (
  "modelV2",
  "drivingModelData",
  "cameraOdometry",
  "modelManagerSP",
  "managerState",
  "longitudinalPlanSP",
  "carStateSP",
  "pandaStates",
)


def run(cmd: Sequence[str]) -> tuple[int, str]:
  try:
    proc = subprocess.run(list(cmd), cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.strip()
  except OSError as exc:
    return 127, f"{cmd[0]} unavailable: {exc}"


def git_value(args: Sequence[str]) -> str:
  code, output = run(["git", *args])
  return output if code == 0 and output else "unknown"


def read_param_file(key: str) -> Path | None:
  for root in PARAM_ROOTS:
    path = root / key
    if path.is_file():
      return path
  return None


def sanitize_bytes(data: bytes, max_text_len: int = 240) -> str:
  if not data:
    return ""
  if len(data) > 2048:
    return f"<large value: {len(data)} bytes, sha256:{hashlib.sha256(data).hexdigest()[:16]}>"
  try:
    text = data.decode("utf-8", errors="strict")
  except UnicodeDecodeError:
    return f"<binary value: {len(data)} bytes, sha256:{hashlib.sha256(data).hexdigest()[:16]}>"
  text = text.replace("\x00", "").strip()
  return text[:max_text_len] + ("...<truncated>" if len(text) > max_text_len else "")


def read_safe_params() -> dict[str, str]:
  values: dict[str, str] = {}
  for key in SAFE_PARAM_KEYS:
    path = read_param_file(key)
    values[key] = "<missing>" if path is None else sanitize_bytes(path.read_bytes())
  return values


def read_json_param(key: str) -> Any:
  path = read_param_file(key)
  if path is None:
    return None
  try:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))
  except Exception:
    return None


def param_truthy(value: str | None) -> bool:
  return str(value or "").strip().lower() in ("1", "true", "on", "yes")


def read_binary_param_summaries() -> dict[str, str]:
  values: dict[str, str] = {}
  for key in BINARY_PARAM_KEYS:
    path = read_param_file(key)
    if path is None:
      values[key] = "<missing>"
      continue
    data = path.read_bytes()
    values[key] = f"{len(data)} bytes, sha256:{hashlib.sha256(data).hexdigest()[:16]}"
  return values


def parse_model_bundle(raw: str) -> dict[str, Any]:
  if not raw or raw.startswith("<missing"):
    return {"present": False}
  try:
    bundle = json.loads(raw)
  except json.JSONDecodeError as exc:
    return {"present": True, "parseError": str(exc)}
  return {
    "present": True,
    "ref": bundle.get("ref", ""),
    "internalName": bundle.get("internalName", ""),
    "displayName": bundle.get("displayName", ""),
    "runner": bundle.get("runner", ""),
    "minimumSelectorVersion": bundle.get("minimumSelectorVersion", ""),
    "modelCount": len(bundle.get("models", [])) if isinstance(bundle.get("models"), list) else 0,
  }


def summarize_auto_tuner(safe_params: dict[str, str]) -> dict[str, Any]:
  payload = read_json_param("CarrotLearningRecommend")
  history = read_json_param("CarrotLearningHistory")
  recommendations = payload.get("recommendations", {}) if isinstance(payload, dict) else {}
  if not isinstance(recommendations, dict):
    recommendations = {}

  return {
    "active": param_truthy(safe_params.get("CarrotLearningActive")),
    "autoApply": param_truthy(safe_params.get("CarrotLearningAutoApply")),
    "popupReady": param_truthy(safe_params.get("CarrotLearningPopupReady")),
    "applyLat": safe_params.get("CarrotTunerApplyLat", "<missing>"),
    "applyLong": safe_params.get("CarrotTunerApplyLong", "<missing>"),
    "pending": bool(recommendations),
    "recommendationCount": len(recommendations),
    "recommendationKeys": sorted(str(key) for key in recommendations.keys())[:20],
    "source": str(payload.get("source", "")) if isinstance(payload, dict) else "",
    "createdAt": payload.get("created_at", 0) if isinstance(payload, dict) else 0,
    "historyCount": len(history) if isinstance(history, list) else 0,
    "learningDataPresent": read_param_file("CarrotLearningData") is not None,
  }


def process_snapshot() -> dict[str, Any]:
  code, output = run(["ps", "-A"])
  if code != 0:
    return {"available": False, "error": output, "cloud": {}, "local": {}, "matched": []}

  lines = [line.strip() for line in output.splitlines()]
  cloud = {name: any(re.search(pattern, line) for line in lines) for name, pattern in CLOUD_PROCESS_PATTERNS.items()}
  local = {name: any(re.search(pattern, line) for line in lines) for name, pattern in LOCAL_PROCESS_PATTERNS.items()}
  patterns = list(CLOUD_PROCESS_PATTERNS.values()) + list(LOCAL_PROCESS_PATTERNS.values())
  matched = [line[:220] for line in lines if any(re.search(pattern, line) for pattern in patterns)]
  return {
    "available": True,
    "cloud": cloud,
    "cloudForbiddenSeen": any(cloud.values()),
    "local": local,
    "matched": matched,
  }


def safe_attr(obj: object, name: str, default: object = None) -> object:
  try:
    return getattr(obj, name, default)
  except Exception:
    return default


def enum_text(value: object) -> str:
  try:
    return str(value).split(".")[-1]
  except Exception:
    return str(value)


def summarize_car_params() -> dict[str, Any]:
  path = read_param_file("CarParams")
  if path is None:
    return {"available": False}
  try:
    from cereal import car
    cp = car.CarParams.from_bytes(path.read_bytes())
  except Exception as exc:
    return {"available": True, "decodeError": str(exc)[:200]}

  return {
    "available": True,
    "carName": str(safe_attr(cp, "carName", "")),
    "carFingerprint": str(safe_attr(cp, "carFingerprint", "")),
    "fingerprintSource": enum_text(safe_attr(cp, "fingerprintSource")),
    "networkLocation": enum_text(safe_attr(cp, "networkLocation")),
    "openpilotLongitudinalControl": bool(safe_attr(cp, "openpilotLongitudinalControl", False)),
    "pcmCruise": bool(safe_attr(cp, "pcmCruise", False)),
    "dashcamOnly": bool(safe_attr(cp, "dashcamOnly", False)),
    "flags": int(safe_attr(cp, "flags", 0) or 0),
    "spFlags": int(safe_attr(cp, "spFlags", 0) or 0),
    "carFwCount": len(safe_attr(cp, "carFw", []) or []),
  }


def _payloads_from_lines(lines: Iterable[str]) -> Iterable[dict[str, Any]]:
  for line in lines:
    line = line.strip()
    if not line:
      continue
    payload = json.loads(line)
    if isinstance(payload, dict):
      yield payload
    elif isinstance(payload, list):
      for item in payload:
        if isinstance(item, dict):
          yield item


def fishop_snapshot(jsonl_path: Path | None) -> dict[str, Any]:
  path = jsonl_path or DEFAULT_FISHOP_JSONL
  result: dict[str, Any] = {
    "inputPath": str(path),
    "inputAvailable": path.is_file(),
    "parseError": "",
    "snapshot": normalize_fishop_payloads([]),
  }
  if not path.is_file():
    return result

  try:
    payloads = list(_payloads_from_lines(path.read_text(encoding="utf-8", errors="replace").splitlines()))
    result["payloadCount"] = len(payloads)
    result["snapshot"] = normalize_fishop_payloads(payloads)
  except Exception as exc:
    result["parseError"] = str(exc)[:200]
  return result


def sample_messaging(seconds: int) -> dict[str, Any]:
  result: dict[str, Any] = {
    "enabled": seconds > 0,
    "seconds": seconds,
    "ok": False,
    "error": "",
    "updates": {service: 0 for service in MESSAGING_SERVICES},
    "valid": {service: False for service in MESSAGING_SERVICES},
    "last": {},
  }
  if seconds <= 0:
    return result

  try:
    import cereal.messaging as messaging
  except Exception as exc:
    result["error"] = f"cannot import cereal.messaging: {exc}"
    return result

  try:
    sm = messaging.SubMaster(list(MESSAGING_SERVICES))
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
      sm.update(100)
      for service in MESSAGING_SERVICES:
        if sm.updated.get(service, False):
          result["updates"][service] += 1
          result["valid"][service] = bool(sm.valid.get(service, False))

      if sm.updated.get("modelManagerSP", False):
        mm = sm["modelManagerSP"]
        active = safe_attr(mm, "activeBundle")
        result["last"]["modelManagerSP"] = {
          "activeBundleName": str(safe_attr(active, "displayName", safe_attr(active, "internalName", ""))),
          "runner": enum_text(safe_attr(active, "runner", "")),
          "availableBundles": len(safe_attr(mm, "availableBundles", []) or []),
        }

      if sm.updated.get("longitudinalPlanSP", False):
        resolver = safe_attr(safe_attr(sm["longitudinalPlanSP"], "speedLimit"), "resolver")
        result["last"]["longitudinalPlanSP"] = {
          "speedLimit": float(safe_attr(resolver, "speedLimit", 0.) or 0.),
          "speedLimitFinal": float(safe_attr(resolver, "speedLimitFinal", 0.) or 0.),
          "source": enum_text(safe_attr(resolver, "source", "")),
          "sourceLabel": str(safe_attr(resolver, "sourceLabel", "")),
        }

      if sm.updated.get("carStateSP", False):
        result["last"]["carStateSP"] = {
          "speedLimit": float(safe_attr(sm["carStateSP"], "speedLimit", 0.) or 0.),
        }

      if sm.updated.get("pandaStates", False):
        states = sm["pandaStates"]
        result["last"]["pandaStates"] = [
          {
            "safetyModel": enum_text(safe_attr(state, "safetyModel", "")),
            "controlsAllowed": bool(safe_attr(state, "controlsAllowed", False)),
            "powerSaveEnabled": bool(safe_attr(state, "powerSaveEnabled", False)),
            "harnessStatus": enum_text(safe_attr(state, "harnessStatus", "")),
          }
          for state in states
        ]

    result["ok"] = True
  except Exception as exc:
    result["error"] = str(exc)[:240]
  return result


def build_snapshot(sample_seconds: int, fishop_jsonl: Path | None) -> dict[str, Any]:
  safe_params = read_safe_params()
  process = process_snapshot()
  cloud_params = {
    "SunnylinkEnabled": safe_params.get("SunnylinkEnabled"),
    "EnableSunnylinkUploader": safe_params.get("EnableSunnylinkUploader"),
    "OnroadUploads": safe_params.get("OnroadUploads"),
  }

  return {
    "metadata": {
      "title": "CarrotPilot-C3-ESCC SunnyPilot Alpha Snapshot",
      "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
      "repo": str(ROOT),
      "branch": git_value(["branch", "--show-current"]),
      "commit": git_value(["rev-parse", "--short=12", "HEAD"]),
      "statusShort": git_value(["status", "--short"]),
      "platform": platform.platform(),
      "python": sys.version.split()[0],
    },
    "params": safe_params,
    "binaryParamSummaries": read_binary_param_summaries(),
    "carParams": summarize_car_params(),
    "model": {
      "runnerCache": safe_params.get("ModelRunnerTypeCache"),
      "activeBundle": parse_model_bundle(safe_params.get("ModelManager_ActiveBundle", "")),
    },
    "autoTuner": summarize_auto_tuner(safe_params),
    "process": process,
    "cloudGuard": {
      "cloudParams": cloud_params,
      "cloudForbiddenProcessesSeen": process.get("cloudForbiddenSeen", False),
    },
    "messaging": sample_messaging(sample_seconds),
    "fishopHardware": fishop_snapshot(fishop_jsonl),
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Collect a privacy-safe SunnyPilot C3 alpha validation snapshot.")
  parser.add_argument("--sample-seconds", type=int, default=0, help="sample live messaging for model and speed evidence")
  parser.add_argument("--fishop-jsonl", type=Path, help="optional fishop hardware JSON Lines capture")
  parser.add_argument("--output", type=Path, help="write JSON report to this path")
  parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
  parser.add_argument("--require-no-cloud-processes", action="store_true", help="fail if disabled cloud/upload processes are running")
  args = parser.parse_args()

  snapshot = build_snapshot(max(args.sample_seconds, 0), args.fishop_jsonl)
  text = json.dumps(snapshot, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True)
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
  else:
    print(text)

  if args.require_no_cloud_processes and snapshot["cloudGuard"]["cloudForbiddenProcessesSeen"]:
    return 2
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
