#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
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
  "CarrotNaviDebug",
  "CarrotNaviEvent",
  "CarrotNaviImage",
  "CarrotNavigationEvent",
  "CarrotActiveSpeedControlEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotTrafficStopEnabled",
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
  "IsMetric",
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

HIGH_RISK_FEATURE_GATES = (
  ("trafficStop", "Traffic Light Stop", "CarrotTrafficStopEnabled", (
    "parked_navigation_replay",
    "red_light_input_consistency",
    "Seltos 2023 ESCC road test",
    "driver confirmation gate",
  )),
  ("autoTurn", "Auto Turn Slowdown", "CarrotAutoTurnControlEnabled", (
    "fresh turn-by-turn input",
    "curve and turn-type consistency",
    "Seltos 2023 ESCC road test",
    "planner handoff review",
  )),
  ("activeSpeed", "Carrot Active Speed Control", "CarrotActiveSpeedControlEnabled", (
    "phone/car/map speed source comparison",
    "Speed Limit Assist road test",
    "braking comfort review",
    "Seltos 2023 ESCC road test",
  )),
  ("autoTunerAutoApply", "Auto-Tuner Auto Apply", "CarrotLearningAutoApply", (
    "offroad-only apply proof",
    "manual recommendation review history",
    "parameter rollback point",
    "Seltos 2023 stability review",
  )),
  ("fishopAutoOvertake", "fishop Auto Overtake", "FishopAutoOvertakeEnabled", (
    "fresh lane input",
    "fresh lidar and camera blindspot input",
    "existing safe lane-change chain review",
    "driver confirmation gate",
    "Seltos 2023 ESCC road test",
  )),
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
CARROT_WEB_HOST = "127.0.0.1"
CARROT_WEB_PORT = 7000
CARROT_STATUS_BROADCAST_PATH = "/api/status_broadcast"
CARROT_HEALTH_PATH = "/api/health"
NAVIPILOT_LIVE_CHECK_SCRIPT = ROOT / "scripts/personal/navipilot_live_check.py"
ALPHA_INSTALL_URL = "https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x"
STABLE_ROLLBACK_INSTALL_URL = "https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/i"
HYUNDAI_SP_ENHANCED_SCC_FLAG = 1
HYUNDAI_SP_ESCC_SAFETY_PARAM = 1
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


def param_int(value: str | None, default: int = 0) -> int:
  try:
    return int(float(str(value or "").strip()))
  except (TypeError, ValueError):
    return default


def param_float(value: str | None, default: float = 0.0) -> float:
  try:
    return float(str(value or "").strip())
  except (TypeError, ValueError):
    return default


def offset_type_name(value: int) -> str:
  return {
    0: "off",
    1: "fixed",
    2: "percentage",
  }.get(value, "unknown")


def speed_limit_policy_name(value: int) -> str:
  return {
    0: "car_state_only",
    1: "map_data_only",
    2: "car_state_priority",
    3: "map_data_priority",
    4: "combined",
    5: "phone_priority",
  }.get(value, "unknown")


def speed_limit_mode_name(value: int) -> str:
  return {
    0: "off",
    1: "information",
    2: "warning",
    3: "assist",
  }.get(value, "unknown")


def summarize_speed_limit(safe_params: dict[str, str], messaging: dict[str, Any]) -> dict[str, Any]:
  policy = param_int(safe_params.get("SpeedLimitPolicy"), 5)
  mode = param_int(safe_params.get("SpeedLimitMode"), 1)
  offset_type = param_int(safe_params.get("SpeedLimitOffsetType"), 0)
  offset_value = param_int(safe_params.get("SpeedLimitValueOffset"), 0)
  is_metric_raw = safe_params.get("IsMetric", "1")
  is_metric = True if str(is_metric_raw).startswith("<missing") else param_truthy(is_metric_raw)
  offset_unit = ""
  if offset_type == 1:
    offset_unit = "kph" if is_metric else "mph"
  elif offset_type == 2:
    offset_unit = "percent"

  phone_speed_ms = param_float(safe_params.get("CarrotPhoneSpeedLimit"), 0.0)
  phone_updated_at = param_float(safe_params.get("CarrotPhoneSpeedLimitUpdatedAt"), 0.0)
  phone_age = max(0.0, time.time() - phone_updated_at) if phone_updated_at > 0.0 else 0.0
  phone_enabled = param_truthy(safe_params.get("CarrotPhoneSpeedLimitEnabled"))
  phone_fresh = phone_enabled and phone_speed_ms > 0.0 and phone_updated_at > 0.0 and phone_age <= 10.0
  last = messaging.get("last", {}) if isinstance(messaging, dict) else {}
  longitudinal = last.get("longitudinalPlanSP", {}) if isinstance(last, dict) else {}
  car_state_sp = last.get("carStateSP", {}) if isinstance(last, dict) else {}

  return {
    "policy": policy,
    "policyName": speed_limit_policy_name(policy),
    "mode": mode,
    "modeName": speed_limit_mode_name(mode),
    "offsetType": offset_type,
    "offsetTypeName": offset_type_name(offset_type),
    "offsetValue": offset_value,
    "offsetUnit": offset_unit,
    "phone": {
      "enabled": phone_enabled,
      "fresh": phone_fresh,
      "speedLimit": phone_speed_ms,
      "speedLimitKph": round(phone_speed_ms * 3.6, 3) if phone_speed_ms > 0.0 else 0.0,
      "source": safe_params.get("CarrotPhoneSpeedLimitSource", ""),
      "updatedAt": phone_updated_at,
      "ageSec": round(phone_age, 3),
      "maxAgeSec": 10.0,
    },
    "resolver": {
      "speedLimit": longitudinal.get("speedLimit", 0.0),
      "speedLimitFinal": longitudinal.get("speedLimitFinal", 0.0),
      "speedLimitOffset": longitudinal.get("speedLimitOffset", 0.0),
      "speedLimitValid": longitudinal.get("speedLimitValid", False),
      "source": longitudinal.get("source", ""),
      "sourceLabel": longitudinal.get("sourceLabel", ""),
    },
    "carState": {
      "speedLimit": car_state_sp.get("speedLimit", 0.0),
    },
  }


def summarize_navigation_event() -> dict[str, Any]:
  event = read_json_param("CarrotNavigationEvent")
  if not isinstance(event, dict):
    return {
      "available": False,
      "event": {},
      "hazards": {},
      "modelSpeed": {},
      "controlPreview": {},
      "controlOutput": False,
      "readOnly": True,
    }
  hazards = event.get("hazards", {}) if isinstance(event.get("hazards"), dict) else {}
  model_speed = event.get("modelSpeed", {}) if isinstance(event.get("modelSpeed"), dict) else {}
  control_preview = event.get("controlPreview", {}) if isinstance(event.get("controlPreview"), dict) else {}
  traffic = event.get("trafficLight", {}) if isinstance(event.get("trafficLight"), dict) else {}
  numeric = event.get("numeric", {}) if isinstance(event.get("numeric"), dict) else {}
  return {
    "available": bool(event.get("updatedAt")),
    "source": event.get("source", ""),
    "updatedAt": event.get("updatedAt", 0.0),
    "speedLimitKph": event.get("speedLimitKph", 0.0),
    "speedLimitSourceField": event.get("speedLimitSourceField", ""),
    "commandIgnored": bool(event.get("commandIgnored", False)),
    "highRiskCommandSeen": bool(event.get("highRiskCommandSeen", False)),
    "ignoredCommand": event.get("ignoredCommand", ""),
    "tbtDistanceM": numeric.get("nTBTDist", 0),
    "tbtTurnType": numeric.get("nTBTTurnType", 0),
    "hazards": hazards,
    "modelSpeed": model_speed,
    "trafficLight": traffic,
    "controlPreview": control_preview,
    "controlOutput": bool(event.get("controlOutput", False)),
    "readOnly": bool(event.get("readOnly", True)),
  }


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
  preview: list[dict[str, Any]] = []
  for key in sorted(str(key) for key in recommendations.keys())[:20]:
    info = recommendations.get(key, {})
    if not isinstance(info, dict):
      continue
    captured_current = param_int(str(info.get("current", 0)), 0)
    recommended = param_int(str(info.get("recommended", captured_current)), captured_current)
    current_path = read_param_file(key)
    current_raw = sanitize_bytes(current_path.read_bytes()) if current_path else str(captured_current)
    current_value = param_int(current_raw, captured_current)
    preview.append({
      "key": key,
      "category": str(info.get("category", "")),
      "capturedCurrentValue": captured_current,
      "currentValue": current_value,
      "recommendedValue": recommended,
      "appliedValue": current_value,
      "liveDelta": recommended - current_value,
      "applied": current_value == recommended,
      "state": "applied" if current_value == recommended else ("changed" if current_value != captured_current else "pending"),
    })

  return {
    "active": param_truthy(safe_params.get("CarrotLearningActive")),
    "autoApply": param_truthy(safe_params.get("CarrotLearningAutoApply")),
    "popupReady": param_truthy(safe_params.get("CarrotLearningPopupReady")),
    "applyLat": safe_params.get("CarrotTunerApplyLat", "<missing>"),
    "applyLong": safe_params.get("CarrotTunerApplyLong", "<missing>"),
    "pending": bool(recommendations),
    "recommendationCount": len(recommendations),
    "recommendationKeys": sorted(str(key) for key in recommendations.keys())[:20],
    "recommendationsPreview": preview,
    "appliedRecommendationCount": sum(1 for rec in preview if rec.get("applied")),
    "pendingRecommendationCount": sum(1 for rec in preview if rec.get("state") == "pending"),
    "changedRecommendationCount": sum(1 for rec in preview if rec.get("state") == "changed"),
    "source": str(payload.get("source", "")) if isinstance(payload, dict) else "",
    "createdAt": payload.get("created_at", 0) if isinstance(payload, dict) else 0,
    "historyCount": len(history) if isinstance(history, list) else 0,
    "learningDataPresent": read_param_file("CarrotLearningData") is not None,
  }


def feature_gate_blocking_reasons(enabled_param: bool, candidate: bool) -> list[str]:
  if not enabled_param:
    return ["param_disabled", "control_output_disabled"]
  reasons = ["real_car_gate_missing", "control_output_disabled"]
  if not candidate:
    reasons.insert(0, "candidate_evidence_missing")
  return reasons


def feature_gate_state(enabled_param: bool, candidate: bool) -> str:
  if not enabled_param:
    return "disabled_default"
  if not candidate:
    return "blocked_waiting_evidence"
  return "blocked_real_car_gate"


def summarize_carrot_feature_gates(safe_params: dict[str, str], navigation: dict[str, Any],
                                   auto_tuner: dict[str, Any], fishop: dict[str, Any]) -> dict[str, Any]:
  control_preview = navigation.get("controlPreview", {}) if isinstance(navigation.get("controlPreview"), dict) else {}
  fishop_state = fishop.get("snapshot", {}) if isinstance(fishop.get("snapshot"), dict) else {}
  overtake = fishop_state.get("overtake", {}) if isinstance(fishop_state.get("overtake"), dict) else {}
  overtake_preview = overtake.get("suggestionPreview", {}) if isinstance(overtake.get("suggestionPreview"), dict) else {}
  traffic = navigation.get("trafficLight", {}) if isinstance(navigation.get("trafficLight"), dict) else {}

  candidates = {
    "trafficStop": bool(control_preview.get("trafficStop", {}).get("candidate", False)),
    "autoTurn": bool(control_preview.get("autoTurn", {}).get("candidate", False)),
    "activeSpeed": bool(control_preview.get("activeSpeed", {}).get("candidate", False)),
    "autoTunerAutoApply": bool(auto_tuner.get("pending", False) or int(auto_tuner.get("pendingRecommendationCount", 0) or 0) > 0),
    "fishopAutoOvertake": bool(overtake.get("requested", False) or overtake.get("commandSeen", False)
                                or overtake_preview.get("readyForSuggestion", False)),
  }
  evidence = {
    "trafficStop": {
      "source": navigation.get("source", ""),
      "updatedAt": navigation.get("updatedAt", 0.0),
      "redLightInput": bool(traffic.get("red", False)),
      "greenLightInput": bool(traffic.get("green", False)),
      "preview": control_preview.get("trafficStop", {}),
    },
    "autoTurn": {
      "source": navigation.get("source", ""),
      "updatedAt": navigation.get("updatedAt", 0.0),
      "preview": control_preview.get("autoTurn", {}),
    },
    "activeSpeed": {
      "source": navigation.get("source", ""),
      "updatedAt": navigation.get("updatedAt", 0.0),
      "speedLimitKph": navigation.get("speedLimitKph", 0.0),
      "preview": control_preview.get("activeSpeed", {}),
    },
    "autoTunerAutoApply": {
      "active": bool(auto_tuner.get("active", False)),
      "pending": bool(auto_tuner.get("pending", False)),
      "pendingRecommendationCount": int(auto_tuner.get("pendingRecommendationCount", 0) or 0),
      "autoApplyStateReported": bool(auto_tuner.get("autoApply", False)),
      "source": auto_tuner.get("source", ""),
      "createdAt": auto_tuner.get("createdAt", 0.0),
    },
    "fishopAutoOvertake": {
      "inputAvailable": bool(fishop.get("inputAvailable", False)),
      "sensorOnline": bool(fishop_state.get("sensorOnline", False)),
      "direction": overtake.get("direction", ""),
      "commandSeen": bool(overtake.get("commandSeen", False)),
      "requested": bool(overtake.get("requested", False)),
      "suggestionPreview": overtake_preview,
    },
  }

  features: dict[str, Any] = {}
  for key, label, param, required_evidence in HIGH_RISK_FEATURE_GATES:
    enabled_param = param_truthy(safe_params.get(param))
    candidate = candidates.get(key, False)
    features[key] = {
      "label": label,
      "param": param,
      "enabledParam": enabled_param,
      "candidate": candidate,
      "state": feature_gate_state(enabled_param, candidate),
      "readyForControl": False,
      "readOnly": True,
      "controlOutput": False,
      "blockingReasons": feature_gate_blocking_reasons(enabled_param, candidate),
      "requiredEvidence": list(required_evidence),
      "evidence": evidence.get(key, {}),
    }

  return {
    "stage": "pre_control_evidence",
    "readOnly": True,
    "controlOutput": False,
    "controlOutputAllowed": False,
    "allBlocked": all(not feature["readyForControl"] for feature in features.values()),
    "enabledFeatures": [key for key, feature in features.items() if feature["enabledParam"]],
    "candidateFeatures": [key for key, feature in features.items() if feature["candidate"]],
    "features": features,
    "requiredBeforeControl": (
      "cloud processes absent",
      "Seltos 2023 SCC and ESCC evidence captured",
      "stock model baseline road test",
      "feature-specific parked replay",
      "feature-specific road test",
      "rollback installer available",
    ),
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


def _local_carrot_json(path: str, timeout: float) -> tuple[bool, dict[str, Any], str]:
  conn: http.client.HTTPConnection | None = None
  try:
    conn = http.client.HTTPConnection(CARROT_WEB_HOST, CARROT_WEB_PORT, timeout=timeout)
    conn.request("GET", path, headers={"Accept": "application/json"})
    response = conn.getresponse()
    raw = response.read(96 * 1024)
    if response.status >= 400:
      return False, {}, f"http {response.status}"
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
      return False, {}, "non-object response"
    return True, data, ""
  except (OSError, TimeoutError, json.JSONDecodeError, http.client.HTTPException) as exc:
    return False, {}, str(exc)[:240]
  finally:
    if conn is not None:
      conn.close()


def _string_list(value: object, limit: int = 20) -> list[str]:
  if not isinstance(value, list):
    return []
  return [str(item)[:120] for item in value[:limit]]


def summarize_carrot_web_status(timeout: float = 1.0) -> dict[str, Any]:
  base_url = f"http://{CARROT_WEB_HOST}:{CARROT_WEB_PORT}"
  result: dict[str, Any] = {
    "available": False,
    "host": CARROT_WEB_HOST,
    "port": CARROT_WEB_PORT,
    "statusBroadcastUrl": f"{base_url}{CARROT_STATUS_BROADCAST_PATH}",
    "healthUrl": f"{base_url}{CARROT_HEALTH_PATH}",
    "readOnly": True,
    "controlOutput": False,
    "statusBroadcast": {
      "available": False,
      "error": "",
      "port": 0,
      "targets": [],
      "activeTargets": [],
      "lastTargets": [],
      "carrotManPeer": {},
      "payload": {
        "carrotManPeerActive": False,
        "carrotManPeerHost": "",
        "carrotManPeerAgeSec": None,
        "xState": 0,
        "trafficState": 0,
        "controlOutput": False,
      },
    },
    "health": {
      "available": False,
      "error": "",
      "statusBroadcastActiveTargets": [],
      "carrotManPeer": {},
    },
  }

  status_ok, status_data, status_error = _local_carrot_json(CARROT_STATUS_BROADCAST_PATH, timeout)
  result["statusBroadcast"]["available"] = status_ok
  result["statusBroadcast"]["error"] = status_error
  if status_ok:
    payload = status_data.get("payload", {})
    if not isinstance(payload, dict):
      payload = {}
    peer = status_data.get("carrotManPeer", {})
    if not isinstance(peer, dict):
      peer = {}
    payload_summary = {
      "carrotManPeerActive": bool(payload.get("carrotManPeerActive", False)),
      "carrotManPeerHost": str(payload.get("carrotManPeerHost", ""))[:120],
      "carrotManPeerAgeSec": payload.get("carrotManPeerAgeSec"),
      "xState": int(payload.get("xState", 0) or 0),
      "trafficState": int(payload.get("trafficState", 0) or 0),
      "controlOutput": bool(payload.get("controlOutput", False)),
    }
    result["available"] = True
    result["controlOutput"] = payload_summary["controlOutput"]
    result["readOnly"] = (
      payload_summary["controlOutput"] is False
      and payload_summary["xState"] == 0
      and payload_summary["trafficState"] == 0
    )
    result["statusBroadcast"].update({
      "port": int(status_data.get("port", 0) or 0),
      "targets": _string_list(status_data.get("targets")),
      "activeTargets": _string_list(status_data.get("activeTargets")),
      "lastTargets": _string_list(status_data.get("lastTargets")),
      "carrotManPeer": {
        "active": bool(peer.get("active", False)),
        "host": str(peer.get("host", ""))[:120],
        "port": int(peer.get("port", 0) or 0),
        "source": str(peer.get("source", ""))[:80],
        "ageSec": peer.get("ageSec"),
      },
      "payload": payload_summary,
    })

  health_ok, health_data, health_error = _local_carrot_json(CARROT_HEALTH_PATH, timeout)
  result["health"]["available"] = health_ok
  result["health"]["error"] = health_error
  if health_ok:
    peer = health_data.get("carrotManPeer", {})
    if not isinstance(peer, dict):
      peer = {}
    result["available"] = True
    result["health"].update({
      "statusBroadcastActiveTargets": _string_list(health_data.get("statusBroadcastActiveTargets")),
      "carrotManPeer": {
        "active": bool(peer.get("active", False)),
        "host": str(peer.get("host", ""))[:120],
        "port": int(peer.get("port", 0) or 0),
        "source": str(peer.get("source", ""))[:80],
        "ageSec": peer.get("ageSec"),
      },
    })

  return result


def summarize_navipilot_live_check(requested: bool, host: str, listen_seconds: float,
                                   send_navigation_probe: bool, write_same_value: bool) -> dict[str, Any]:
  result: dict[str, Any] = {
    "requested": requested,
    "available": False,
    "overallOk": False,
    "returnCode": None,
    "script": str(NAVIPILOT_LIVE_CHECK_SCRIPT),
    "host": host,
    "listenSeconds": max(float(listen_seconds), 0.0),
    "sendNavigationProbe": send_navigation_probe,
    "writeSameValue": write_same_value,
    "error": "",
    "report": {},
  }
  if not requested:
    result["overallOk"] = True
    return result
  if not NAVIPILOT_LIVE_CHECK_SCRIPT.is_file():
    result["error"] = "navipilot live check script is missing"
    return result

  cmd = [
    sys.executable,
    str(NAVIPILOT_LIVE_CHECK_SCRIPT),
    "--host",
    host,
    "--listen-seconds",
    f"{max(float(listen_seconds), 0.0):.3f}",
    "--json",
  ]
  if send_navigation_probe:
    cmd.append("--send-navigation-probe")
  if write_same_value:
    cmd.append("--write-same-value")

  try:
    proc = subprocess.run(
      cmd,
      cwd=str(ROOT),
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      timeout=max(15.0, float(listen_seconds) + 10.0),
      check=False,
    )
  except Exception as exc:
    result["error"] = str(exc)[:400]
    return result

  result["returnCode"] = proc.returncode
  if proc.stderr.strip():
    result["stderr"] = proc.stderr.strip()[-800:]
  try:
    report = json.loads(proc.stdout)
  except Exception as exc:
    result["error"] = f"cannot parse navipilot live check JSON: {exc}"
    result["stdoutTail"] = proc.stdout[-800:]
    return result
  if not isinstance(report, dict):
    result["error"] = "navipilot live check did not return a JSON object"
    return result

  result["available"] = True
  result["report"] = report
  result["overallOk"] = proc.returncode == 0 and report.get("overallOk") is True
  safety = report.get("safetyBoundary", {}) if isinstance(report.get("safetyBoundary"), dict) else {}
  result["controlOutput"] = safety.get("controlOutput")
  result["cloudServices"] = safety.get("cloudServices")
  result["localOnly"] = safety.get("localOnly")
  return result


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


def summarize_car_params_sp() -> dict[str, Any]:
  path = read_param_file("CarParamsSP") or read_param_file("CarParamsSPPersistent") or read_param_file("CarParamsSPCache")
  if path is None:
    return {"available": False}
  try:
    from cereal import custom, messaging
    cp_sp = messaging.log_from_bytes(path.read_bytes(), custom.CarParamsSP)
  except Exception as exc:
    return {"available": True, "decodeError": str(exc)[:200]}

  flags = int(safe_attr(cp_sp, "flags", 0) or 0)
  safety_param = int(safe_attr(cp_sp, "safetyParam", 0) or 0)
  return {
    "available": True,
    "sourceParam": path.name,
    "flags": flags,
    "safetyParam": safety_param,
    "enhancedSccDetected": bool(flags & HYUNDAI_SP_ENHANCED_SCC_FLAG),
    "esccSafetyParamSet": bool(safety_param & HYUNDAI_SP_ESCC_SAFETY_PARAM),
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


def gate_check(pass_condition: bool, missing_condition: bool, fail_reason: str, missing_reason: str = "") -> dict[str, Any]:
  if missing_condition:
    return {"status": "missing", "ok": False, "reason": missing_reason or fail_reason}
  if pass_condition:
    return {"status": "pass", "ok": True, "reason": ""}
  return {"status": "fail", "ok": False, "reason": fail_reason}


def summarize_fishop_release_gate(safe_params: dict[str, str], process: dict[str, Any], car_params: dict[str, Any],
                                  car_params_sp: dict[str, Any], messaging: dict[str, Any],
                                  fishop: dict[str, Any]) -> dict[str, Any]:
  fishop_state = fishop.get("snapshot", {}) if isinstance(fishop, dict) else {}
  lane = fishop_state.get("lane", {}) if isinstance(fishop_state, dict) else {}
  blindspot = fishop_state.get("blindspot", {}) if isinstance(fishop_state, dict) else {}
  overtake = fishop_state.get("overtake", {}) if isinstance(fishop_state, dict) else {}
  preview = overtake.get("suggestionPreview", {}) if isinstance(overtake, dict) else {}
  messaging_last = messaging.get("last", {}) if isinstance(messaging, dict) else {}
  panda_states = messaging_last.get("pandaStates", []) if isinstance(messaging_last, dict) else []
  cloud_param_values = {
    "SunnylinkEnabled": safe_params.get("SunnylinkEnabled"),
    "EnableSunnylinkUploader": safe_params.get("EnableSunnylinkUploader"),
    "OnroadUploads": safe_params.get("OnroadUploads"),
  }
  cloud_params_disabled = not any(param_truthy(str(value)) for value in cloud_param_values.values() if value != "<missing>")
  car_fingerprint = str(car_params.get("carFingerprint", "")) if isinstance(car_params, dict) else ""

  checks = {
    "cloudProcessesAbsent": gate_check(
      process.get("available", False) and not process.get("cloudForbiddenSeen", False),
      not process.get("available", False),
      "disabled cloud/upload process is visible",
      "process list unavailable",
    ),
    "cloudParamsDisabled": gate_check(
      cloud_params_disabled,
      False,
      "Sunnylink/upload params are enabled",
    ),
    "seltosSccFingerprint": gate_check(
      "KIA_SELTOS" in car_fingerprint and not bool(car_params.get("dashcamOnly", True)),
      not car_params.get("available", False) or bool(car_params.get("decodeError")),
      "CarParams is not a usable Seltos SCC profile",
      "CarParams is unavailable or undecodable",
    ),
    "esccDetected": gate_check(
      bool(car_params_sp.get("enhancedSccDetected")) and bool(car_params_sp.get("esccSafetyParamSet")),
      not car_params_sp.get("available", False) or bool(car_params_sp.get("decodeError")),
      "CarParamsSP does not prove ENHANCED_SCC and ESCC safetyParam",
      "CarParamsSP is unavailable or undecodable",
    ),
    "pandaEvidencePresent": gate_check(
      isinstance(panda_states, list) and len(panda_states) > 0,
      not messaging.get("enabled", False),
      "live pandaStates were not observed",
      "messaging sampling was not requested",
    ),
    "fishopParsed": gate_check(
      not fishop.get("parseError") and bool(fishop.get("inputAvailable")),
      not bool(fishop.get("inputAvailable")),
      "fishop JSONL parse error",
      "fishop JSONL input is missing",
    ),
    "fishopSensorFresh": gate_check(
      bool(fishop_state.get("sensorOnline")) and bool(lane.get("fresh")) and bool(blindspot.get("fresh")),
      not bool(fishop_state),
      "fishop lane/blindspot evidence is stale or offline",
      "fishop snapshot is unavailable",
    ),
    "fishopOvertakeDisplayOnly": gate_check(
      bool(preview.get("readOnly")) and preview.get("controlOutput") is False and preview.get("emitsLateralCommand") is False
      and preview.get("stage") == "display_only"
      and preview.get("navigationGate", {}).get("controlEligible") is False
      and preview.get("overtakeHint", {}).get("controlOutput") is False
      and preview.get("overtakeHint", {}).get("emitsLateralCommand") is False,
      not isinstance(preview, dict) or not preview,
      "fishop overtake preview is not display-only/read-only",
      "fishop overtake preview is missing",
    ),
  }
  blocking = [name for name, check in checks.items() if not check["ok"]]
  return {
    "stage": "pre_control_evidence",
    "readyForNextStageReview": not blocking,
    "blockingChecks": blocking,
    "checks": checks,
    "cloudParams": cloud_param_values,
    "carFingerprint": car_fingerprint,
    "pandaStatesSeen": len(panda_states) if isinstance(panda_states, list) else 0,
    "fishopSuggestionDecision": preview.get("decision", ""),
    "requiredBeforeControl": (
      "cloudProcessesAbsent",
      "cloudParamsDisabled",
      "seltosSccFingerprint",
      "esccDetected",
      "pandaEvidencePresent",
      "fishopParsed",
      "fishopSensorFresh",
      "fishopOvertakeDisplayOnly",
    ),
  }


def _stage_status(implemented: bool, evidence_ok: bool, locked: bool = False) -> str:
  if locked:
    return "locked"
  if not implemented:
    return "not_implemented"
  return "pass" if evidence_ok else "waiting_evidence"


def _stage_record(stage_id: int, name: str, implemented: bool, evidence_ok: bool, current_allowed: bool,
                  required_log: str, missing: Iterable[str], rollback: dict[str, Any], locked: bool = False) -> dict[str, Any]:
  return {
    "stageId": stage_id,
    "name": name,
    "status": _stage_status(implemented, evidence_ok, locked),
    "implemented": implemented,
    "currentAllowed": current_allowed,
    "evidenceOk": evidence_ok,
    "readOnly": True,
    "controlOutput": False,
    "mayPublishDesire": False,
    "maySendLateralCommand": False,
    "requiredLog": required_log,
    "rollback": rollback,
    "missingBeforeNextStage": list(missing),
  }


def summarize_fishop_overtake_stages(fishop: dict[str, Any], release_gate: dict[str, Any]) -> dict[str, Any]:
  fishop_state = fishop.get("snapshot", {}) if isinstance(fishop, dict) else {}
  lane = fishop_state.get("lane", {}) if isinstance(fishop_state, dict) else {}
  blindspot = fishop_state.get("blindspot", {}) if isinstance(fishop_state, dict) else {}
  overtake = fishop_state.get("overtake", {}) if isinstance(fishop_state, dict) else {}
  preview = overtake.get("suggestionPreview", {}) if isinstance(overtake, dict) else {}
  hint = preview.get("overtakeHint", {}) if isinstance(preview.get("overtakeHint"), dict) else {}
  navigation_gate = preview.get("navigationGate", {}) if isinstance(preview.get("navigationGate"), dict) else {}
  release_checks = release_gate.get("checks", {}) if isinstance(release_gate, dict) else {}
  rollback = {
    "required": True,
    "alphaInstaller": ALPHA_INSTALL_URL,
    "stableRollbackInstaller": STABLE_ROLLBACK_INSTALL_URL,
    "branch": git_value(["branch", "--show-current"]),
    "commit": git_value(["rev-parse", "--short=12", "HEAD"]),
    "tagRequiredBeforePromotion": True,
  }

  data_evidence = bool(fishop.get("inputAvailable")) and not bool(fishop.get("parseError")) and bool(fishop_state)
  sensor_evidence = bool(fishop_state.get("sensorOnline")) and bool(lane.get("fresh")) and bool(blindspot.get("fresh"))
  display_evidence = bool(release_checks.get("fishopOvertakeDisplayOnly", {}).get("ok"))
  hint_supported = (
    isinstance(hint, dict)
    and hint.get("readOnly") is True
    and hint.get("controlOutput") is False
    and hint.get("emitsLateralCommand") is False
    and hint.get("stage") == "hint_only"
  )
  suggestion_review_supported = (
    bool(preview.get("readyForSuggestion"))
    and navigation_gate.get("suggestionEligible") is True
    and navigation_gate.get("controlEligible") is False
    and preview.get("emitsLateralCommand") is False
  )

  stages = [
    _stage_record(
      1,
      "data_only_capture",
      True,
      data_evidence,
      True,
      "fishop JSONL/input capture with timestamps, lane, blindspot, navigation, and overtake fields",
      () if data_evidence else ("fishop input file or parsed payload evidence",),
      rollback,
    ),
    _stage_record(
      2,
      "display_only_web_snapshot",
      True,
      sensor_evidence and display_evidence,
      True,
      "Carrot Web/API/snapshot display-only evidence; no planner, desire, steering, or CAN output",
      () if sensor_evidence and display_evidence else ("fresh lane/blindspot evidence", "display-only release gate"),
      rollback,
    ),
    _stage_record(
      3,
      "hint_only_no_desire",
      True,
      hint_supported,
      True,
      "overtakeHint log with direction, reasons, navigationGate, and explicit no-desire/no-lateral-output fields",
      () if hint_supported else ("overtakeHint evidence with controlOutput=false and emitsLateralCommand=false",),
      rollback,
    ),
    _stage_record(
      4,
      "suggestion_review_existing_safety_chain",
      False,
      suggestion_review_supported,
      False,
      "future suggestion review log consumed only by existing safe lane-change chain",
      (
        "existing safe lane-change chain integration",
        "turn signal and driver confirmation gate",
        "original and external blindspot agreement gate",
        "speed, road type, and Seltos 2023 SCC/ESCC gate",
        "parked replay plus road-test evidence",
      ),
      rollback,
      locked=True,
    ),
    _stage_record(
      5,
      "controlled_execution_experiment",
      False,
      False,
      False,
      "future controlled execution evidence log with separate tag, rollback installer, and driver override review",
      (
        "all previous stages passed on device",
        "separate experimental tag",
        "rollback installer verified",
        "driver override and disengagement review",
        "cloud/upload processes absent in every evidence bundle",
      ),
      rollback,
      locked=True,
    ),
  ]
  return {
    "readOnly": True,
    "controlOutput": False,
    "currentMaxStage": max(stage["stageId"] for stage in stages if stage["implemented"] and stage["currentAllowed"]),
    "nextLockedStage": next((stage["stageId"] for stage in stages if stage["status"] == "locked"), None),
    "rollbackRequiredForEveryStage": True,
    "cloudEvidenceRequiredEveryStage": True,
    "allImplementedStagesNoControlOutput": all(
      stage["controlOutput"] is False and stage["mayPublishDesire"] is False and stage["maySendLateralCommand"] is False
      for stage in stages
    ),
    "stages": stages,
  }


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
          "speedLimitOffset": float(safe_attr(resolver, "speedLimitOffset", 0.) or 0.),
          "speedLimitValid": bool(safe_attr(resolver, "speedLimitValid", False)),
          "distToSpeedLimit": float(safe_attr(resolver, "distToSpeedLimit", 0.) or 0.),
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


def build_snapshot(sample_seconds: int, fishop_jsonl: Path | None,
                   navipilot_live_check_requested: bool = False,
                   navipilot_host: str = CARROT_WEB_HOST,
                   navipilot_listen_seconds: float = 3.0,
                   navipilot_send_navigation_probe: bool = False,
                   navipilot_write_same_value: bool = False) -> dict[str, Any]:
  safe_params = read_safe_params()
  process = process_snapshot()
  messaging = sample_messaging(sample_seconds)
  car_params = summarize_car_params()
  car_params_sp = summarize_car_params_sp()
  fishop = fishop_snapshot(fishop_jsonl)
  carrot_web = summarize_carrot_web_status()
  navipilot_live_check = summarize_navipilot_live_check(
    navipilot_live_check_requested,
    navipilot_host,
    navipilot_listen_seconds,
    navipilot_send_navigation_probe,
    navipilot_write_same_value,
  )
  navigation = summarize_navigation_event()
  auto_tuner = summarize_auto_tuner(safe_params)
  carrot_feature_gates = summarize_carrot_feature_gates(safe_params, navigation, auto_tuner, fishop)
  fishop_release_gate = summarize_fishop_release_gate(safe_params, process, car_params, car_params_sp, messaging, fishop)
  fishop_overtake_stages = summarize_fishop_overtake_stages(fishop, fishop_release_gate)
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
    "carParams": car_params,
    "carParamsSP": car_params_sp,
    "model": {
      "runnerCache": safe_params.get("ModelRunnerTypeCache"),
      "activeBundle": parse_model_bundle(safe_params.get("ModelManager_ActiveBundle", "")),
    },
    "speedLimitEvidence": summarize_speed_limit(safe_params, messaging),
    "navigationEvidence": navigation,
    "carrotWeb": carrot_web,
    "navipilotLiveCheck": navipilot_live_check,
    "carrotFeatureGates": carrot_feature_gates,
    "autoTuner": auto_tuner,
    "process": process,
    "cloudGuard": {
      "cloudParams": cloud_params,
      "cloudForbiddenProcessesSeen": process.get("cloudForbiddenSeen", False),
    },
    "messaging": messaging,
    "fishopHardware": fishop,
    "fishopReleaseGate": fishop_release_gate,
    "fishopOvertakeStages": fishop_overtake_stages,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Collect a privacy-safe SunnyPilot C3 alpha validation snapshot.")
  parser.add_argument("--sample-seconds", type=int, default=0, help="sample live messaging for model and speed evidence")
  parser.add_argument("--fishop-jsonl", type=Path, help="optional fishop hardware JSON Lines capture")
  parser.add_argument("--output", type=Path, help="write JSON report to this path")
  parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
  parser.add_argument("--navipilot-live-check", action="store_true", help="run the local Navipilot / CPdazi endpoint live check")
  parser.add_argument("--navipilot-host", default=CARROT_WEB_HOST, help="host used for the Navipilot live check")
  parser.add_argument("--navipilot-listen-seconds", type=float, default=3.0, help="seconds to listen for UDP 7705 during the live check")
  parser.add_argument("--navipilot-send-navigation-probe", action="store_true", help="send one safe evidence-only navigation probe while parked")
  parser.add_argument("--navipilot-write-same-value", action="store_true", help="test /api/param_set by writing a safe param back to its current value")
  parser.add_argument("--require-no-cloud-processes", action="store_true", help="fail if disabled cloud/upload processes are running")
  parser.add_argument("--require-fishop-release-gate", action="store_true", help="fail if fishop next-stage evidence gate is not satisfied")
  parser.add_argument("--require-navipilot-live-check", action="store_true", help="fail if the Navipilot live check is not clean")
  args = parser.parse_args()

  snapshot = build_snapshot(
    max(args.sample_seconds, 0),
    args.fishop_jsonl,
    navipilot_live_check_requested=args.navipilot_live_check or args.require_navipilot_live_check,
    navipilot_host=args.navipilot_host,
    navipilot_listen_seconds=args.navipilot_listen_seconds,
    navipilot_send_navigation_probe=args.navipilot_send_navigation_probe,
    navipilot_write_same_value=args.navipilot_write_same_value,
  )
  text = json.dumps(snapshot, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True)
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
  else:
    print(text)

  if args.require_no_cloud_processes and snapshot["cloudGuard"]["cloudForbiddenProcessesSeen"]:
    return 2
  if args.require_fishop_release_gate and not snapshot["fishopReleaseGate"]["readyForNextStageReview"]:
    return 3
  if args.require_navipilot_live_check and not snapshot["navipilotLiveCheck"]["overallOk"]:
    return 4
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
