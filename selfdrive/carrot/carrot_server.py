#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from aiohttp import web

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openpilot.selfdrive.carrot.fishop_hardware import normalize_fishop_payloads


LOCAL_WEB_PORT = 7000
STATUS_BROADCAST_PORT = 7705
STATUS_BROADCAST_INTERVAL_S = 1.0
STATUS_BROADCAST_TARGETS = ("255.255.255.255", "127.0.0.1")
MESSAGING_STATUS_SERVICES = (
  "carState",
  "selfdriveState",
  "controlsState",
  "longitudinalPlanSP",
  "carStateSP",
)
MESSAGING_STATUS_INTERVAL_S = 0.2
NAVIGATION_UDP_PORT = 7706
NAVI_HTTP_PORT = 7713
NAVI_HTTP_MAX_BODY_SIZE = 16 * 1024 * 1024
NAVI_EVENT_TYPES = ("complexCrossroad", "rgdata", "vrtx", "ssinf", "sinf", "route")
NAVI_IMAGE_BASE64_MAX_CHARS = 6 * 1024 * 1024
NAVIGATION_ROUTE_MAX_AGE_S = 30.0
DEFAULT_HOST = "0.0.0.0"
DEFAULT_FISHOP_JSONL = Path("/data/fishop_hardware.jsonl")
MAX_FISHOP_LINES = 240
KPH_TO_MS = 1000.0 / 3600.0
MPH_TO_KPH = 1.609344
PHONE_SPEED_LIMIT_MAX_KPH = 180.0
PHONE_SPEED_LIMIT_MAX_AGE_S = 10.0
PHONE_SPEED_LIMIT_SOURCE_MAX_CHARS = 48

PHONE_SPEED_LIMIT_MS_FIELDS = (
  "speedLimitMS",
  "speed_limit_ms",
  "speedLimitMps",
  "speed_limit_mps",
)

PHONE_SPEED_LIMIT_KPH_FIELDS = (
  "speedLimitKph",
  "speed_limit_kph",
  "speedLimit",
  "speed_limit",
  "limit",
  "speed",
  "nRoadLimitSpeed",
  "nSdiSpeedLimit",
  "nSdiPlusSpeedLimit",
)

PARAM_API_MAX_NAMES = 80
PARAM_API_MAX_VALUE_TEXT = 80

PARAM_API_DEFS: dict[str, dict[str, Any]] = {
  "ExperimentalMode": {"type": "bool", "default": False, "writable": True},
  "ExperimentalModeConfirmed": {"type": "bool", "default": False, "writable": True},
  "IsMetric": {"type": "bool", "default": True, "writable": True},
  "CarrotLearningActive": {"type": "bool", "default": False, "writable": True},
  "CarrotPhoneSpeedLimitEnabled": {"type": "bool", "default": True, "writable": True},
  "CarrotMapOverlayEnabled": {"type": "bool", "default": False, "writable": True},
  "SpeedLimitPolicy": {"type": "int", "default": 5, "writable": True, "min": 0, "max": 5},
  "SpeedLimitOffsetType": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 2},
  "SpeedLimitValueOffset": {"type": "int", "default": 0, "writable": True, "min": -30, "max": 30},
  # Local API intentionally cannot enable active speed-control assist; that remains a UI/road-test gate.
  "SpeedLimitMode": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 2},
  "OffroadMode": {"type": "bool", "default": False, "writable": False},
  "IsOnroad": {"type": "bool", "default": False, "writable": False},
  "OpenpilotEnabledToggle": {"type": "bool", "default": True, "writable": False},
  "SshEnabled": {"type": "bool", "default": False, "writable": False},
  "CarrotActiveSpeedControlEnabled": {"type": "bool", "default": False, "writable": False},
  "CarrotAutoTurnControlEnabled": {"type": "bool", "default": False, "writable": False},
  "CarrotTrafficStopEnabled": {"type": "bool", "default": False, "writable": False},
  "FishopAutoOvertakeEnabled": {"type": "bool", "default": False, "writable": False},
}

VIRTUAL_PARAM_DEFAULTS = {
  "DeviceType": "unknown",
}

NAVIGATION_NUMERIC_FIELDS = (
  "carrotIndex",
  "nRoadLimitSpeed",
  "nSdiType",
  "nSdiSpeedLimit",
  "nSdiDist",
  "nSdiPlusType",
  "nSdiPlusSpeedLimit",
  "nTBTDist",
  "nTBTTurnType",
  "nTBTDistNext",
  "nTBTTurnTypeNext",
  "nGoPosDist",
  "nGoPosTime",
  "vpPosPointLat",
  "vpPosPointLon",
  "latitude",
  "longitude",
)

NAVIGATION_TEXT_FIELDS = (
  "szTBTMainText",
  "szTBTMainTextNext",
  "roadName",
  "currentRoadName",
)

NAVIGATION_COMMAND_FIELDS = (
  "carrotCmd",
  "carrotArg",
)

HIGH_RISK_NAV_COMMANDS = (
  "LANECHANGE",
  "LANE_CHANGE",
  "OVERTAKE",
  "AUTO_OVERTAKE",
)

ACTION_PARAMS = {
  "apply": "CarrotLearningApply",
  "ignore": "CarrotLearningIgnore",
  "clear": "CarrotLearningClear",
}

PARAM_LIMITS = {
  "CruiseMaxVals0": (50, 300),
  "CruiseMaxVals1": (50, 300),
  "CruiseMaxVals2": (40, 250),
  "CruiseMaxVals3": (30, 220),
  "CruiseMaxVals4": (20, 200),
  "CruiseMaxVals5": (20, 180),
  "CruiseMaxVals6": (20, 160),
  "TFollowGap1": (70, 300),
  "TFollowGap2": (80, 350),
  "TFollowGap3": (90, 400),
  "TFollowGap4": (100, 450),
  "JLeadFactor3": (-200, 300),
  "PathOffset": (-150, 150),
  "SteerActuatorDelay": (0, 200),
  "SteerRatioRate": (50, 150),
  "DynamicTFollow": (0, 100),
  "TFollowDecelBoost": (0, 100),
  "StopDistanceCarrot": (300, 1200),
}


def _json_response(payload: dict[str, Any], status: int = 200) -> web.Response:
  return web.json_response(payload, status=status, headers={"Cache-Control": "no-store"})


def _decode_json(raw: Any) -> Any:
  if not raw:
    return None
  try:
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray, memoryview)) else str(raw)
    return json.loads(text)
  except Exception:
    return None


def _as_float(value: Any, default: float = 0.0) -> float:
  if value is None:
    return default
  if isinstance(value, bytes):
    value = value.decode("utf-8", errors="ignore")
  try:
    return float(value)
  except (TypeError, ValueError):
    return default


def _decode_param_text(raw: Any) -> str:
  if raw is None:
    return ""
  if isinstance(raw, bytes):
    return raw.decode("utf-8", errors="ignore")
  return str(raw)


def _as_bool(value: Any) -> bool:
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return value != 0
  if isinstance(value, bytes):
    value = value.decode("utf-8", errors="ignore")
  return str(value).strip().lower() in ("1", "true", "on", "yes", "y")


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
  try:
    return getattr(obj, name)
  except Exception:
    return default


def _safe_nested(obj: Any, *names: str, default: Any = None) -> Any:
  current = obj
  for name in names:
    current = _safe_attr(current, name, None)
    if current is None:
      return default
  return current


def _ms_to_kph(value: Any) -> float:
  return _as_float(value) / KPH_TO_MS


def _safe_source_text(value: Any) -> str:
  text = str(value or "phone").strip()
  if not text:
    text = "phone"
  safe = "".join(ch for ch in text if ch.isalnum() or ch in (" ", "-", "_", ".", "/", ":")).strip()
  return (safe or "phone")[:PHONE_SPEED_LIMIT_SOURCE_MAX_CHARS]


def _put_float(params: Any, key: str, value: float) -> None:
  params.put(key, float(value))


def _clamp_param(key: str, value: Any) -> int:
  low, high = PARAM_LIMITS[key]
  return int(max(low, min(high, int(value))))


def _params_state() -> tuple[Any | None, str]:
  try:
    from openpilot.common.params import Params
    return Params(), ""
  except Exception as exc:
    return None, str(exc)[:240]


def _params_get(params: Any, key: str, default: Any = None) -> Any:
  try:
    return params.get(key, return_default=True)
  except TypeError:
    value = params.get(key)
    return default if value is None else value
  except Exception:
    return default


def _param_meta(name: str) -> dict[str, Any] | None:
  return PARAM_API_DEFS.get(name)


def _normalize_param_value(value: Any, meta: dict[str, Any]) -> Any:
  value_type = meta.get("type")
  if value_type == "bool":
    return _as_bool(value)
  if value_type == "int":
    normalized = int(round(_as_float(value, float(meta.get("default", 0)))))
    if "min" in meta:
      normalized = max(int(meta["min"]), normalized)
    if "max" in meta:
      normalized = min(int(meta["max"]), normalized)
    return normalized
  if value_type == "float":
    normalized_float = _as_float(value, float(meta.get("default", 0.0)))
    if "min" in meta:
      normalized_float = max(float(meta["min"]), normalized_float)
    if "max" in meta:
      normalized_float = min(float(meta["max"]), normalized_float)
    return normalized_float
  text = _decode_param_text(value).strip()
  return text[:PARAM_API_MAX_VALUE_TEXT]


def _json_safe_value(value: Any) -> Any:
  if isinstance(value, bytes):
    return value.decode("utf-8", errors="replace")
  if isinstance(value, (str, int, float, bool)) or value is None:
    return value
  if isinstance(value, (dict, list)):
    return value
  return str(value)


def _write_param_value(params: Any, name: str, value: Any, meta: dict[str, Any]) -> None:
  if meta.get("type") == "bool":
    params.put_bool(name, bool(value))
  else:
    params.put(name, value)


def _requested_param_names(raw_names: str) -> list[str]:
  names: list[str] = []
  for raw in raw_names.split(","):
    name = raw.strip()
    if name and name not in names:
      names.append(name)
    if len(names) >= PARAM_API_MAX_NAMES:
      break
  return names


def params_bulk_state(names: Iterable[str]) -> dict[str, Any]:
  values: dict[str, Any] = {}
  writable: dict[str, bool] = {}
  params, error = _params_state()

  for name in names:
    if name in VIRTUAL_PARAM_DEFAULTS:
      values[name] = VIRTUAL_PARAM_DEFAULTS[name]
      writable[name] = False
      continue

    meta = _param_meta(name)
    if meta is None:
      values[name] = 0
      writable[name] = False
      continue

    value = meta.get("default")
    if params is not None:
      value = _params_get(params, name, meta.get("default"))
    values[name] = _json_safe_value(_normalize_param_value(value, meta))
    writable[name] = bool(meta.get("writable", False))

  return {
    "hasParams": params is not None,
    "values": values,
    "writable": writable,
    "error": error if params is None else "",
  }


def set_param_from_api(name: str, value: Any) -> dict[str, Any]:
  if not name:
    raise ValueError("missing name")
  meta = _param_meta(name)
  if meta is None:
    raise ValueError(f"param is not exposed through local API: {name}")
  if not meta.get("writable", False):
    raise ValueError(f"param is read-only through local API: {name}")

  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")

  normalized = _normalize_param_value(value, meta)
  current = _normalize_param_value(_params_get(params, name, meta.get("default")), meta)
  changed = normalized != current

  if params.get_bool("IsOnroad") and changed:
    raise RuntimeError("Cannot change params while onroad")

  if changed:
    _write_param_value(params, name, normalized, meta)

  return {
    "name": name,
    "value": _json_safe_value(normalized),
    "changed": changed,
    "hasParams": True,
  }


def _safe_navigation_text(value: Any) -> str:
  text = _decode_param_text(value).replace("\x00", "").strip()
  return text[:120]


def _navigation_payload_event(payload: dict[str, Any], source: str) -> dict[str, Any]:
  numeric: dict[str, float | int] = {}
  text: dict[str, str] = {}
  for key in NAVIGATION_NUMERIC_FIELDS:
    if key not in payload:
      continue
    value = _as_float(payload.get(key), 0.0)
    numeric[key] = int(value) if float(value).is_integer() else round(value, 7)
  for key in NAVIGATION_TEXT_FIELDS:
    if key in payload:
      text[key] = _safe_navigation_text(payload.get(key))

  command = _safe_navigation_text(payload.get(NAVIGATION_COMMAND_FIELDS[0], ""))
  command_arg = _safe_navigation_text(payload.get(NAVIGATION_COMMAND_FIELDS[1], ""))
  command_upper = command.upper()
  ignored_command = bool(command or command_arg)
  high_risk_command = command_upper in HIGH_RISK_NAV_COMMANDS

  speed_kph, speed_field = _extract_phone_speed_kph(payload)
  return {
    "updatedAt": time.time(),
    "source": _safe_source_text(source),
    "numeric": numeric,
    "text": text,
    "speedLimitKph": round(speed_kph, 3) if speed_kph is not None else 0.0,
    "speedLimitSourceField": speed_field,
    "commandIgnored": ignored_command,
    "highRiskCommandSeen": high_risk_command,
    "ignoredCommand": command,
    "ignoredCommandArg": command_arg,
  }


def navigation_event_state() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    return {"hasParams": False, "event": {}, "error": error}
  raw = _params_get(params, "CarrotNavigationEvent", {})
  if isinstance(raw, dict):
    event = raw
  else:
    decoded = _decode_json(raw)
    event = decoded if isinstance(decoded, dict) else {}
  return {"hasParams": True, "event": event}


def record_navigation_event(payload: dict[str, Any], source: str = "api") -> dict[str, Any]:
  if not isinstance(payload, dict):
    raise ValueError("invalid navigation payload")
  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")

  event = _navigation_payload_event(payload, source)
  params.put("CarrotNavigationEvent", event)
  phone_result: dict[str, Any] = {"accepted": False}
  try:
    phone_payload = dict(payload)
    phone_payload["source"] = source
    phone_result = set_phone_speed_limit(phone_payload)
  except Exception as exc:
    phone_result = {"accepted": False, "error": str(exc)}
  return {"recorded": True, "event": event, "phoneSpeed": phone_result}


def _status_payload_navigation_fields(event: dict[str, Any]) -> dict[str, Any]:
  numeric = event.get("numeric") if isinstance(event, dict) else {}
  text = event.get("text") if isinstance(event, dict) else {}
  numeric = numeric if isinstance(numeric, dict) else {}
  text = text if isinstance(text, dict) else {}
  updated_at = _as_float(event.get("updatedAt"), 0.0) if isinstance(event, dict) else 0.0
  route_age_sec = max(0.0, time.time() - updated_at) if updated_at > 0.0 else 0.0
  route_has_guidance = bool(
    _as_float(numeric.get("nTBTDist"), 0.0) > 0.0
    or _as_float(numeric.get("nSdiDist"), 0.0) > 0.0
    or _safe_navigation_text(text.get("szTBTMainTextNext") or text.get("szTBTMainText") or "")
  )
  return {
    "route_active": route_has_guidance and updated_at > 0.0 and route_age_sec <= NAVIGATION_ROUTE_MAX_AGE_S,
    "route_age_sec": round(route_age_sec, 3),
    "tbt_dist": int(_as_float(numeric.get("nTBTDist"), 0.0)),
    "sdi_dist": int(_as_float(numeric.get("nSdiDist"), 0.0)),
    "sdi_speed": int(_as_float(numeric.get("nSdiSpeedLimit"), 0.0)),
    "road_limit_speed": int(_as_float(numeric.get("nRoadLimitSpeed"), 0.0)),
    "tbt_turn_type": int(_as_float(numeric.get("nTBTTurnType"), 0.0)),
    "tbt_next_turn_type": int(_as_float(numeric.get("nTBTTurnTypeNext"), 0.0)),
    "tbt_main_text": _safe_navigation_text(text.get("szTBTMainTextNext") or text.get("szTBTMainText") or ""),
  }


def default_messaging_status() -> dict[str, Any]:
  return {
    "available": False,
    "lastUpdateAt": 0.0,
    "lastError": "",
    "carStateAlive": False,
    "selfdriveStateAlive": False,
    "controlsStateAlive": False,
    "longitudinalPlanSPAlive": False,
    "carStateSPAlive": False,
    "vEgoKph": 0.0,
    "vCruiseKph": 0.0,
    "carCruiseSpeedKph": 0.0,
    "logCarrot": "",
    "active": False,
    "enabled": False,
    "isOnroad": False,
    "standstill": False,
    "canValid": False,
    "speedLimitKph": 0.0,
    "speedLimitSource": "",
  }


def _sm_alive(sm: Any, service: str) -> bool:
  try:
    return bool(sm.alive.get(service, False))
  except Exception:
    try:
      return bool(sm.alive[service])
    except Exception:
      return False


def _sm_message(sm: Any, service: str) -> Any:
  try:
    return sm[service]
  except Exception:
    return None


def _positive_float(*values: Any) -> float:
  for value in values:
    normalized = _as_float(value, 0.0)
    if normalized > 0.0:
      return normalized
  return 0.0


def _messaging_speed_limit_state(longitudinal_plan_sp: Any, car_state_sp: Any) -> tuple[float, str]:
  resolver = _safe_nested(longitudinal_plan_sp, "speedLimit", "resolver")
  source = ""
  speed_limit_ms = 0.0
  if resolver is not None:
    source = str(_safe_attr(resolver, "sourceLabel", "") or _safe_attr(resolver, "source", "") or "")
    if bool(_safe_attr(resolver, "speedLimitValid", False)):
      speed_limit_ms = _positive_float(
        _safe_attr(resolver, "speedLimitFinal", 0.0),
        _safe_attr(resolver, "speedLimit", 0.0),
      )
    if speed_limit_ms <= 0.0:
      speed_limit_ms = _positive_float(_safe_attr(resolver, "speedLimitFinalLast", 0.0), _safe_attr(resolver, "speedLimitLast", 0.0))

  if speed_limit_ms <= 0.0 and car_state_sp is not None:
    speed_limit_ms = _positive_float(_safe_attr(car_state_sp, "speedLimit", 0.0))
    if speed_limit_ms > 0.0 and not source:
      source = "car"

  return (round(_ms_to_kph(speed_limit_ms), 3) if speed_limit_ms > 0.0 else 0.0, source[:48])


def update_messaging_status_from_sm(sm: Any) -> dict[str, Any]:
  car_state = _sm_message(sm, "carState")
  selfdrive_state = _sm_message(sm, "selfdriveState")
  controls_state = _sm_message(sm, "controlsState")
  longitudinal_plan_sp = _sm_message(sm, "longitudinalPlanSP")
  car_state_sp = _sm_message(sm, "carStateSP")

  v_ego_ms = _positive_float(_safe_attr(car_state, "vEgoCluster", 0.0), _safe_attr(car_state, "vEgo", 0.0))
  cruise_state = _safe_attr(car_state, "cruiseState")
  log_carrot = _decode_param_text(_safe_attr(car_state, "logCarrot", ""))
  v_cruise_kph = _positive_float(
    _safe_attr(car_state, "vCruiseCluster", 0.0),
    _safe_attr(car_state, "vCruise", 0.0),
    _safe_nested(controls_state, "deprecated", "vCruiseCluster", default=0.0),
    _safe_nested(controls_state, "deprecated", "vCruise", default=0.0),
    _ms_to_kph(_safe_attr(cruise_state, "speedCluster", 0.0)),
    _ms_to_kph(_safe_attr(cruise_state, "speed", 0.0)),
  )
  car_cruise_speed_kph = _positive_float(
    _ms_to_kph(_safe_attr(cruise_state, "speedCluster", 0.0)),
    _ms_to_kph(_safe_attr(cruise_state, "speed", 0.0)),
    v_cruise_kph,
  )
  speed_limit_kph, speed_limit_source = _messaging_speed_limit_state(longitudinal_plan_sp, car_state_sp)

  active = bool(_safe_attr(selfdrive_state, "active", False))
  enabled = bool(_safe_attr(selfdrive_state, "enabled", False))
  return {
    **default_messaging_status(),
    "available": True,
    "lastUpdateAt": time.time(),
    "carStateAlive": _sm_alive(sm, "carState"),
    "selfdriveStateAlive": _sm_alive(sm, "selfdriveState"),
    "controlsStateAlive": _sm_alive(sm, "controlsState"),
    "longitudinalPlanSPAlive": _sm_alive(sm, "longitudinalPlanSP"),
    "carStateSPAlive": _sm_alive(sm, "carStateSP"),
    "vEgoKph": round(_ms_to_kph(v_ego_ms), 3) if v_ego_ms > 0.0 else 0.0,
    "vCruiseKph": round(v_cruise_kph, 3) if v_cruise_kph > 0.0 else 0.0,
    "carCruiseSpeedKph": round(car_cruise_speed_kph, 3) if car_cruise_speed_kph > 0.0 else 0.0,
    "logCarrot": log_carrot[:240],
    "active": active,
    "enabled": enabled,
    "isOnroad": active or enabled,
    "standstill": bool(_safe_attr(car_state, "standstill", False)),
    "canValid": bool(_safe_attr(car_state, "canValid", False)),
    "speedLimitKph": speed_limit_kph,
    "speedLimitSource": speed_limit_source,
  }


def build_status_payload(runtime_status: dict[str, Any] | None = None, navi_http_status: dict[str, Any] | None = None) -> dict[str, Any]:
  params, _error = _params_state()
  event_state = navigation_event_state()
  event = event_state.get("event", {}) if isinstance(event_state, dict) else {}
  nav_fields = _status_payload_navigation_fields(event if isinstance(event, dict) else {})
  runtime_status = {**default_messaging_status(), **(runtime_status or {})}
  navi_http_status = {**default_navi_http_state(), **(navi_http_status or {})}
  navi_http_available = bool(navi_http_status.get("available", False))

  is_onroad = bool(params.get_bool("IsOnroad")) if params is not None else bool(runtime_status.get("isOnroad", False))
  active = bool(runtime_status.get("active", False))
  speed_limit_state = phone_speed_state()

  return {
    "Carrot2": "CarrotPilot-C3-ESCC-alpha",
    "IsOnroad": is_onroad,
    "CarrotRouteActive": bool(is_onroad and nav_fields["route_active"]),
    "ip": DEFAULT_HOST,
    "port": NAVIGATION_UDP_PORT,
    "navi_debug": 0,
    "navi_http_port": NAVI_HTTP_PORT if navi_http_available else 0,
    "naviHttpAvailable": navi_http_available,
    "naviHttpLastError": str(navi_http_status.get("lastError", "")),
    "carrotManCompatible": True,
    "carrotManControlStateAvailable": False,
    "active": active,
    "log_carrot": str(runtime_status.get("logCarrot", "")),
    "v_ego_kph": round(_as_float(runtime_status.get("vEgoKph")), 1),
    "v_cruise_kph": round(_as_float(runtime_status.get("vCruiseKph")), 1),
    "carcruiseSpeed": round(_as_float(runtime_status.get("carCruiseSpeedKph")), 1),
    "tbt_dist": nav_fields["tbt_dist"],
    "sdi_dist": nav_fields["sdi_dist"],
    "xState": 0,
    "trafficState": 0,
    "sdi_speed": nav_fields["sdi_speed"],
    "road_limit_speed": nav_fields["road_limit_speed"],
    "tbt_turn_type": nav_fields["tbt_turn_type"],
    "tbt_next_turn_type": nav_fields["tbt_next_turn_type"],
    "tbt_main_text": nav_fields["tbt_main_text"],
    "carrotRouteAgeSec": nav_fields["route_age_sec"],
    "carrotRouteMaxAgeSec": NAVIGATION_ROUTE_MAX_AGE_S,
    "phoneSpeedLimitKph": speed_limit_state.get("speedLimitKph", 0.0),
    "phoneSpeedLimitSource": speed_limit_state.get("source", ""),
    "phoneSpeedLimitFresh": bool(speed_limit_state.get("fresh", False)),
    "speedLimitKph": _as_float(runtime_status.get("speedLimitKph"), 0.0),
    "speedLimitSource": str(runtime_status.get("speedLimitSource", "")),
    "messagingAvailable": bool(runtime_status.get("available", False)),
    "messagingLastUpdateAt": _as_float(runtime_status.get("lastUpdateAt"), 0.0),
    "messagingLastError": str(runtime_status.get("lastError", "")),
    "canValid": bool(runtime_status.get("canValid", False)),
    "standstill": bool(runtime_status.get("standstill", False)),
    "enabled": bool(runtime_status.get("enabled", False)),
    "navigationUpdatedAt": event.get("updatedAt", 0.0) if isinstance(event, dict) else 0.0,
    "timestamp": time.time(),
    "controlOutput": False,
    "paramsAvailable": params is not None,
  }


def _read_payload(params: Any) -> dict[str, Any] | None:
  payload = _decode_json(params.get("CarrotLearningRecommend"))
  return payload if isinstance(payload, dict) else None


def _normalize_recommendations(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
  if not payload:
    return []
  raw_recs = payload.get("recommendations", {})
  if not isinstance(raw_recs, dict):
    return []

  normalized: list[dict[str, Any]] = []
  for key, info in raw_recs.items():
    if key not in PARAM_LIMITS or not isinstance(info, dict):
      continue
    try:
      current = int(info.get("current", 0))
      recommended = _clamp_param(key, info.get("recommended", current))
    except Exception:
      continue
    normalized.append({
      "key": key,
      "category": str(info.get("category", "long")),
      "current": current,
      "recommended": recommended,
      "delta": recommended - current,
      "reason": str(info.get("reason", "")),
      "evidence": info.get("evidence", {}),
    })
  return normalized


def _clear_pending(params: Any) -> None:
  params.remove("CarrotLearningRecommend")
  params.remove("CarrotLearningPopupSource")
  params.put_bool("CarrotLearningPopupReady", False)
  params.put_bool("CarrotLearningApply", False)
  params.put_bool("CarrotLearningIgnore", False)


def _append_history(params: Any, payload: dict[str, Any], applied: dict[str, int], mode: str) -> None:
  history = _decode_json(params.get("CarrotLearningHistory"))
  if not isinstance(history, list):
    history = []
  history.append({
    "applied_at": time.time(),
    "mode": mode,
    "source": payload.get("source", ""),
    "applied": applied,
  })
  params.put("CarrotLearningHistory", json.dumps(history[-50:], separators=(",", ":")).encode("utf-8"))


def get_learning_state() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    return {
      "hasParams": False,
      "active": False,
      "pending": False,
      "popupReady": False,
      "autoApply": False,
      "applyLat": False,
      "applyLong": False,
      "source": "",
      "createdAt": 0,
      "recommendations": [],
      "error": error,
    }

  payload = _read_payload(params)
  recs = _normalize_recommendations(payload)
  return {
    "hasParams": True,
    "active": params.get_bool("CarrotLearningActive"),
    "pending": bool(recs),
    "popupReady": params.get_bool("CarrotLearningPopupReady"),
    "autoApply": params.get_bool("CarrotLearningAutoApply"),
    "applyLat": params.get_int("CarrotTunerApplyLat") != 0,
    "applyLong": params.get_int("CarrotTunerApplyLong") != 0,
    "source": str(payload.get("source", "")) if isinstance(payload, dict) else "",
    "createdAt": payload.get("created_at", 0) if isinstance(payload, dict) else 0,
    "recommendations": recs,
  }


def apply_learning_recommendations() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")
  if params.get_bool("IsOnroad"):
    raise RuntimeError("Cannot apply Auto-Tuner recommendations while onroad")

  payload = _read_payload(params)
  recs = _normalize_recommendations(payload)
  if not payload or not recs:
    _clear_pending(params)
    return {"applied": {}, "appliedCount": 0}

  applied: dict[str, int] = {}
  for rec in recs:
    key = rec["key"]
    category = rec.get("category", "long")
    if category == "lat" and params.get_int("CarrotTunerApplyLat") == 0:
      continue
    if category == "long" and params.get_int("CarrotTunerApplyLong") == 0:
      continue
    value = _clamp_param(key, rec["recommended"])
    params.put_int(key, value)
    applied[key] = value

  if applied:
    _append_history(params, payload, applied, "manual")
  _clear_pending(params)
  return {"applied": applied, "appliedCount": len(applied)}


def ignore_learning_recommendations() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")
  _clear_pending(params)
  return {"ignored": True}


def clear_learning_data() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")
  params.remove("CarrotLearningData")
  params.remove("CarrotLearningRecommend")
  params.remove("CarrotLearningPopupSource")
  params.put_bool("CarrotLearningPopupReady", False)
  params.put_bool("CarrotLearningApply", False)
  params.put_bool("CarrotLearningIgnore", False)
  params.put_bool("CarrotLearningClear", False)
  return {"cleared": True}


def handle_learning_action(action: str) -> dict[str, Any]:
  if action == "apply":
    return apply_learning_recommendations()
  if action == "ignore":
    return ignore_learning_recommendations()
  if action == "clear":
    return clear_learning_data()
  raise ValueError(f"unknown Auto-Tuner action: {action}")


def _candidate_phone_payloads(body: dict[str, Any]) -> Iterable[dict[str, Any]]:
  yield body
  for key in ("payload", "navigation", "nav", "data"):
    nested = body.get(key)
    if isinstance(nested, dict):
      yield nested


def _extract_phone_speed_kph(body: dict[str, Any]) -> tuple[float | None, str]:
  for payload in _candidate_phone_payloads(body):
    for key in PHONE_SPEED_LIMIT_MS_FIELDS:
      if key in payload:
        speed_ms = _as_float(payload.get(key), -1.0)
        if speed_ms <= 0.0:
          continue
        return speed_ms / KPH_TO_MS, key

    unit = str(payload.get("unit", "kph")).strip().lower()
    for key in PHONE_SPEED_LIMIT_KPH_FIELDS:
      if key not in payload:
        continue
      speed = _as_float(payload.get(key), -1.0)
      if speed <= 0.0:
        continue
      if unit in ("m/s", "ms", "mps", "meter_per_second", "meters_per_second"):
        return speed / KPH_TO_MS, key
      if unit in ("mph", "mi/h"):
        return speed * MPH_TO_KPH, key
      return speed, key

  return None, ""


def phone_speed_state() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    return {
      "hasParams": False,
      "enabled": False,
      "fresh": False,
      "speedLimitMS": 0.0,
      "speedLimitKph": 0.0,
      "source": "",
      "updatedAt": 0.0,
      "ageSec": 0.0,
      "maxAgeSec": PHONE_SPEED_LIMIT_MAX_AGE_S,
      "error": error,
    }

  now = time.time()
  speed_ms = _as_float(params.get("CarrotPhoneSpeedLimit"))
  updated_at = _as_float(params.get("CarrotPhoneSpeedLimitUpdatedAt"))
  age_sec = now - updated_at if updated_at > 0 else 0.0
  enabled = params.get_bool("CarrotPhoneSpeedLimitEnabled")
  source = _decode_param_text(params.get("CarrotPhoneSpeedLimitSource"))
  fresh = enabled and speed_ms > 0.0 and updated_at > 0.0 and 0.0 <= age_sec <= PHONE_SPEED_LIMIT_MAX_AGE_S

  return {
    "hasParams": True,
    "enabled": enabled,
    "fresh": fresh,
    "speedLimitMS": round(speed_ms, 6),
    "speedLimitKph": round(speed_ms / KPH_TO_MS, 3) if speed_ms > 0.0 else 0.0,
    "source": source or "phone",
    "updatedAt": updated_at,
    "ageSec": round(age_sec, 3),
    "maxAgeSec": PHONE_SPEED_LIMIT_MAX_AGE_S,
  }


def clear_phone_speed_limit() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")
  _put_float(params, "CarrotPhoneSpeedLimit", 0.0)
  _put_float(params, "CarrotPhoneSpeedLimitUpdatedAt", 0.0)
  params.remove("CarrotPhoneSpeedLimitSource")
  return {"cleared": True}


def set_phone_speed_limit(body: dict[str, Any]) -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")

  if not isinstance(body, dict):
    raise ValueError("invalid JSON body")
  if str(body.get("action", "")).strip().lower() == "clear":
    return clear_phone_speed_limit()

  speed_kph, source_field = _extract_phone_speed_kph(body)
  if speed_kph is None:
    raise ValueError("missing speed limit")
  if speed_kph <= 0.0 or speed_kph > PHONE_SPEED_LIMIT_MAX_KPH:
    raise ValueError(f"speed limit must be between 0 and {PHONE_SPEED_LIMIT_MAX_KPH:g} km/h")

  source = _safe_source_text(body.get("source") or body.get("provider") or source_field or "phone")
  _put_float(params, "CarrotPhoneSpeedLimit", speed_kph * KPH_TO_MS)
  _put_float(params, "CarrotPhoneSpeedLimitUpdatedAt", time.time())
  params.put("CarrotPhoneSpeedLimitSource", source.encode("utf-8"))
  return {
    "accepted": True,
    "sourceField": source_field,
    "speedLimitKph": round(speed_kph, 3),
    "speedLimitMS": round(speed_kph * KPH_TO_MS, 6),
    "source": source,
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


def default_navi_http_state() -> dict[str, Any]:
  return {
    "available": False,
    "port": NAVI_HTTP_PORT,
    "lastError": "",
    "lastEvent": {},
    "lastReceivedAt": 0.0,
    "receivedTypes": {},
  }


def _detect_navi_event_type(payload: Any) -> str:
  if not isinstance(payload, dict):
    return "unknown"
  for key in NAVI_EVENT_TYPES:
    if payload.get(key) is not None:
      return key
  return "unknown"


def _navi_event_timestamp_ms(payload: dict[str, Any]) -> int:
  try:
    return int(_as_float(payload.get("timestamp_ms") or payload.get("timestamp"), 0.0))
  except Exception:
    return 0


def _navi_route_count(value: Any) -> int:
  if isinstance(value, list):
    return len(value)
  if isinstance(value, dict):
    for key in ("points", "coordinates", "route", "vrtx"):
      nested = value.get(key)
      if isinstance(nested, list):
        return len(nested)
  return 0


def _navi_http_summary(payload: dict[str, Any], event_type: str) -> dict[str, Any]:
  summary: dict[str, Any] = {"type": event_type}
  event_payload = payload.get(event_type) if event_type in payload else payload
  if event_type == "rgdata" and isinstance(event_payload, dict):
    summary.update({
      "lat": event_payload.get("vpPosPointLat") or event_payload.get("latitude"),
      "lon": event_payload.get("vpPosPointLon") or event_payload.get("longitude"),
      "roadLimitSpeed": event_payload.get("nRoadLimitSpeed"),
      "tbtDist": event_payload.get("nTBTDist"),
      "sdiType": event_payload.get("nSdiType"),
      "sdiSpeedLimit": event_payload.get("nSdiSpeedLimit"),
      "sdiDist": event_payload.get("nSdiDist"),
    })
  elif event_type in ("vrtx", "route"):
    summary["routePointCount"] = _navi_route_count(event_payload)
  elif event_type in ("sinf", "ssinf") and isinstance(event_payload, dict):
    summary.update({
      "distance": event_payload.get("distance"),
      "redLightOn": event_payload.get("redLightOn") or event_payload.get("straight") == "RED_LIGHT_ON",
      "greenLightOn": event_payload.get("greenLightOn") or event_payload.get("straight") == "GREEN_LIGHT_ON",
      "leftLightOn": event_payload.get("leftLightOn") or event_payload.get("left") == "GREEN_LIGHT_ON",
    })
  elif event_type == "complexCrossroad" and isinstance(event_payload, dict):
    image_base64 = event_payload.get("imageBase64")
    image_hash = ""
    if isinstance(image_base64, str) and image_base64:
      digest = hashlib.sha256()
      for index in range(0, len(image_base64), 65536):
        digest.update(image_base64[index:index + 65536].encode("ascii", "ignore"))
      image_hash = digest.hexdigest()[:16]
    summary.update({
      "show": bool(event_payload.get("show", False)),
      "imageUrl": str(event_payload.get("imageUrl", ""))[:200],
      "imageMime": str(event_payload.get("imageMime", ""))[:64],
      "imageWidth": int(_as_float(event_payload.get("imageWidth"), 0.0)),
      "imageHeight": int(_as_float(event_payload.get("imageHeight"), 0.0)),
      "hasImageBase64": isinstance(image_base64, str) and bool(image_base64),
      "imageBase64Size": len(image_base64) if isinstance(image_base64, str) else 0,
      "imageHash": image_hash,
    })
  else:
    summary["keys"] = list(payload.keys())[:10]
  return summary


def _navigation_payload_from_navi_http(payload: dict[str, Any], event_type: str) -> dict[str, Any]:
  if event_type == "rgdata" and isinstance(payload.get("rgdata"), dict):
    return dict(payload["rgdata"])
  if event_type == "sinf" and isinstance(payload.get("sinf"), dict):
    sinf = payload["sinf"]
    return {
      "nTBTDist": sinf.get("distance", 0),
      "trafficRedLightOn": bool(sinf.get("redLightOn", False)),
      "trafficGreenLightOn": bool(sinf.get("greenLightOn", False)),
      "source": "http-7713-sinf",
    }
  if event_type == "ssinf" and isinstance(payload.get("ssinf"), dict):
    ssinf = payload["ssinf"]
    return {
      "nTBTDist": ssinf.get("distance", 0),
      "trafficStraight": ssinf.get("straight", ""),
      "trafficLeft": ssinf.get("left", ""),
      "source": "http-7713-ssinf",
    }
  return dict(payload)


def _write_navi_http_params(payload: dict[str, Any], event: dict[str, Any], image: dict[str, Any] | None) -> bool:
  params, _error = _params_state()
  if params is None:
    return False
  params.put("CarrotNaviEvent", event)
  params.put("CarrotNaviDebug", {
    "receivedAt": event["receivedAt"],
    "eventTimeMs": event["eventTimeMs"],
    "summary": event["summary"],
    "controlOutput": False,
  })
  if image is not None:
    params.put("CarrotNaviImage", image)
  return True


def record_navi_http_event(app: web.Application, payload: dict[str, Any], tmap_version: str = "") -> dict[str, Any]:
  if not isinstance(payload, dict):
    raise ValueError("navigation HTTP payload must be a JSON object")
  event_type = _detect_navi_event_type(payload)
  received_at = time.time()
  summary = _navi_http_summary(payload, event_type)
  event = {
    "receivedAt": received_at,
    "eventTimeMs": _navi_event_timestamp_ms(payload),
    "type": event_type,
    "tmapVersion": _safe_navigation_text(tmap_version),
    "summary": summary,
    "controlOutput": False,
  }

  image: dict[str, Any] | None = None
  if event_type == "complexCrossroad" and isinstance(payload.get("complexCrossroad"), dict):
    crossroad = payload["complexCrossroad"]
    image_base64 = crossroad.get("imageBase64")
    image_too_large = isinstance(image_base64, str) and len(image_base64) > NAVI_IMAGE_BASE64_MAX_CHARS
    if image_too_large:
      image_base64 = ""
    image = {
      "receivedAt": received_at,
      "show": bool(crossroad.get("show", False)),
      "imageBase64": image_base64 if isinstance(image_base64, str) else "",
      "imageMime": str(crossroad.get("imageMime", "")),
      "imageEncoding": str(crossroad.get("imageEncoding", "")),
      "imageWidth": int(_as_float(crossroad.get("imageWidth"), 0.0)),
      "imageHeight": int(_as_float(crossroad.get("imageHeight"), 0.0)),
      "imageHash": str(summary.get("imageHash", "")),
      "imageUrl": str(crossroad.get("imageUrl", "")),
      "imageTooLarge": image_too_large,
    }

  params_written = _write_navi_http_params(payload, event, image)
  nav_result: dict[str, Any] = {"recorded": False}
  try:
    nav_payload = _navigation_payload_from_navi_http(payload, event_type)
    nav_result = record_navigation_event(nav_payload, f"http-7713-{event_type}")
  except Exception as exc:
    nav_result = {"recorded": False, "error": str(exc)}

  state = app["navi_http_state"]
  received_types = state.setdefault("receivedTypes", {})
  received_types[event_type] = int(received_types.get(event_type, 0)) + 1
  state["lastEvent"] = event
  state["lastReceivedAt"] = received_at
  state["lastError"] = ""
  return {
    "recorded": True,
    "type": event_type,
    "tmapVersion": _safe_navigation_text(tmap_version),
    "paramsWritten": params_written,
    "navigation": nav_result,
    "summary": summary,
    "controlOutput": False,
  }


def fishop_state() -> dict[str, Any]:
  result: dict[str, Any] = {
    "inputPath": str(DEFAULT_FISHOP_JSONL),
    "inputAvailable": DEFAULT_FISHOP_JSONL.is_file(),
    "payloadCount": 0,
    "parseError": "",
    "snapshot": normalize_fishop_payloads([]),
  }
  if not DEFAULT_FISHOP_JSONL.is_file():
    return result

  try:
    lines = DEFAULT_FISHOP_JSONL.read_text(encoding="utf-8", errors="replace").splitlines()[-MAX_FISHOP_LINES:]
    payloads = list(_payloads_from_lines(lines))
    result["payloadCount"] = len(payloads)
    result["snapshot"] = normalize_fishop_payloads(payloads)
  except Exception as exc:
    result["parseError"] = str(exc)[:200]
  return result


async def api_health(_request: web.Request) -> web.Response:
  udp_error = str(_request.app.get("navigation_udp_error", ""))
  udp_protocol = _request.app.get("navigation_udp_protocol")
  udp_last_error = str(getattr(udp_protocol, "last_error", ""))
  udp_last_datagram_at = float(getattr(udp_protocol, "last_datagram_at", 0.0))
  udp_last_recorded_at = float(getattr(udp_protocol, "last_recorded_at", 0.0))
  status_state = _request.app["status_broadcast_state"]
  status_last_sent_at = float(status_state.get("lastSentAt", 0.0))
  status_last_error = str(status_state.get("lastError", ""))
  messaging_state = _request.app["messaging_status_state"]
  navi_http_state = _request.app["navi_http_state"]
  return _json_response({
    "ok": True,
    "service": "carrot_server",
    "mode": "local",
    "port": LOCAL_WEB_PORT,
    "statusBroadcastPort": STATUS_BROADCAST_PORT,
    "statusBroadcastTargets": list(STATUS_BROADCAST_TARGETS),
    "statusBroadcastLastSentAt": status_last_sent_at,
    "statusBroadcastError": status_last_error,
    "messagingAvailable": bool(messaging_state.get("available", False)),
    "messagingLastUpdateAt": float(messaging_state.get("lastUpdateAt", 0.0)),
    "messagingLastError": str(messaging_state.get("lastError", "")),
    "navigationUdpPort": NAVIGATION_UDP_PORT,
    "navigationUdpError": udp_error,
    "navigationUdpLastError": udp_last_error,
    "navigationUdpLastDatagramAt": udp_last_datagram_at,
    "navigationUdpLastRecordedAt": udp_last_recorded_at,
    "naviHttpPort": NAVI_HTTP_PORT,
    "naviHttpAvailable": bool(navi_http_state.get("available", False)),
    "naviHttpLastError": str(navi_http_state.get("lastError", "")),
    "naviHttpLastReceivedAt": float(navi_http_state.get("lastReceivedAt", 0.0)),
    "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "cloudServices": False,
    "controlOutput": False,
    "endpoints": [
      "/api/health",
      "/api/params_bulk",
      "/api/param_set",
      "/api/status_broadcast",
      "/api/carrot_learning",
      "/api/fishop_hardware",
      "/api/navigation_event",
      "/api/navi",
      "/api/phone_speed_limit",
    ],
  })


async def api_carrot_learning(_request: web.Request) -> web.Response:
  return _json_response({"ok": True, **get_learning_state()})


async def api_params_bulk(request: web.Request) -> web.Response:
  names = _requested_param_names(request.query.get("names", ""))
  if not names:
    return _json_response({"ok": False, "error": "missing names"}, status=400)
  state = params_bulk_state(names)
  return _json_response({"ok": state["hasParams"], **state}, status=200 if state["hasParams"] else 400)


async def api_param_set(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return _json_response({"ok": False, "error": "invalid json"}, status=400)

  name = str(body.get("name", "")).strip()
  try:
    result = set_param_from_api(name, body.get("value"))
    return _json_response({"ok": True, **result})
  except Exception as exc:
    params, error = _params_state()
    return _json_response({
      "ok": False,
      "name": name,
      "hasParams": params is not None,
      "error": str(exc) if params is not None else f"Params unavailable: {error}",
    }, status=400)


async def api_status_broadcast(_request: web.Request) -> web.Response:
  status_state = _request.app["status_broadcast_state"]
  messaging_state = _request.app["messaging_status_state"]
  navi_http_state = _request.app["navi_http_state"]
  return _json_response({
    "ok": True,
    "port": STATUS_BROADCAST_PORT,
    "targets": list(STATUS_BROADCAST_TARGETS),
    "lastSentAt": float(status_state.get("lastSentAt", 0.0)),
    "lastError": str(status_state.get("lastError", "")),
    "messagingStatus": messaging_state,
    "naviHttpStatus": navi_http_state,
    "payload": status_state.get("lastPayload") or build_status_payload(messaging_state, navi_http_state),
  })


async def api_carrot_learning_action(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  action = str(body.get("action", "")).strip()
  if action not in ACTION_PARAMS:
    return _json_response({"ok": False, "error": "missing or invalid action"}, status=400)
  try:
    result = handle_learning_action(action)
    return _json_response({"ok": True, **result, **get_learning_state()})
  except Exception as exc:
    return _json_response({"ok": False, "error": str(exc)}, status=400)


async def api_fishop_hardware(_request: web.Request) -> web.Response:
  return _json_response({"ok": True, **fishop_state()})


async def api_navigation_event(_request: web.Request) -> web.Response:
  state = navigation_event_state()
  return _json_response({"ok": state["hasParams"], **state}, status=200 if state["hasParams"] else 400)


async def api_navigation_event_action(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  try:
    result = record_navigation_event(body, "api")
    return _json_response({"ok": True, **result})
  except Exception as exc:
    state = navigation_event_state()
    return _json_response({"ok": False, "error": str(exc), **state}, status=400)


async def api_navi_http_health(request: web.Request) -> web.Response:
  state = request.app["navi_http_state"]
  return _json_response({
    "ok": True,
    "service": "carrot_navi_http",
    "port": NAVI_HTTP_PORT,
    "available": bool(state.get("available", False)),
    "lastError": str(state.get("lastError", "")),
    "lastEvent": state.get("lastEvent", {}),
    "receivedTypes": state.get("receivedTypes", {}),
    "controlOutput": False,
  })


async def api_navi_http_post(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    try:
      text = (await request.text()).strip()
      body = json.loads(text) if text else {}
    except Exception as exc:
      return _json_response({"ok": False, "error": f"invalid json: {exc}", "controlOutput": False}, status=400)
  try:
    result = record_navi_http_event(request.app, body, request.match_info.get("tmap_version", ""))
    return _json_response({"ok": True, **result})
  except Exception as exc:
    request.app["navi_http_state"]["lastError"] = str(exc)[:200]
    return _json_response({"ok": False, "error": str(exc), "controlOutput": False}, status=400)


async def api_phone_speed_limit(_request: web.Request) -> web.Response:
  return _json_response({"ok": True, **phone_speed_state()})


async def api_phone_speed_limit_action(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  try:
    result = set_phone_speed_limit(body)
    return _json_response({"ok": True, **result, **phone_speed_state()})
  except Exception as exc:
    return _json_response({"ok": False, "error": str(exc), **phone_speed_state()}, status=400)


async def index(_request: web.Request) -> web.Response:
  html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CarrotPilot C3 Local Web</title>
  <style>
    :root { color-scheme: dark; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #101418; color: #eef4f8; }
    main { max-width: 760px; margin: 0 auto; padding: 32px 20px; }
    h1 { font-size: 28px; margin: 0 0 8px; font-weight: 680; }
    p { color: #b8c5cc; line-height: 1.5; }
    section { border: 1px solid #2f3b43; border-radius: 8px; padding: 18px; margin-top: 16px; background: #151b20; }
    a { color: #7dd3fc; text-decoration: none; }
    code { background: #222b31; padding: 2px 6px; border-radius: 5px; }
    ul { padding-left: 20px; }
  </style>
</head>
<body>
  <main>
    <h1>CarrotPilot C3 Local Web</h1>
    <p>Local-only alpha service for maintenance evidence, Auto-Tuner recommendations, and fishop hardware snapshots.</p>
    <section>
      <h2>APIs</h2>
      <ul>
        <li><a href="/api/health"><code>/api/health</code></a></li>
        <li><a href="/api/params_bulk?names=ExperimentalMode"><code>/api/params_bulk</code></a></li>
        <li><a href="/api/status_broadcast"><code>/api/status_broadcast</code></a></li>
        <li><a href="/api/carrot_learning"><code>/api/carrot_learning</code></a></li>
        <li><a href="/api/fishop_hardware"><code>/api/fishop_hardware</code></a></li>
        <li><a href="/api/navigation_event"><code>/api/navigation_event</code></a></li>
        <li><a href="/api/phone_speed_limit"><code>/api/phone_speed_limit</code></a></li>
      </ul>
    </section>
  </main>
</body>
</html>
"""
  return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})


class NavigationUdpProtocol(asyncio.DatagramProtocol):
  def __init__(self) -> None:
    self.last_error = ""
    self.last_datagram_at = 0.0
    self.last_recorded_at = 0.0

  def datagram_received(self, data: bytes, _addr: tuple[str, int]) -> None:
    self.last_datagram_at = time.time()
    try:
      payload = json.loads(data.decode("utf-8", errors="replace"))
      if not isinstance(payload, dict):
        raise ValueError("navigation UDP payload must be a JSON object")
      record_navigation_event(payload, "udp-7706")
      self.last_recorded_at = time.time()
      self.last_error = ""
    except Exception as exc:
      self.last_error = str(exc)[:200]


async def start_navigation_udp(app: web.Application) -> None:
  loop = asyncio.get_running_loop()
  protocol = NavigationUdpProtocol()
  try:
    transport, _ = await loop.create_datagram_endpoint(
      lambda: protocol,
      local_addr=(DEFAULT_HOST, NAVIGATION_UDP_PORT),
    )
    app["navigation_udp_transport"] = transport
    app["navigation_udp_protocol"] = protocol
    app["navigation_udp_error"] = ""
  except Exception as exc:
    app["navigation_udp_error"] = str(exc)[:200]


async def stop_navigation_udp(app: web.Application) -> None:
  transport = app.get("navigation_udp_transport")
  if transport is not None:
    transport.close()


async def messaging_status_loop(app: web.Application) -> None:
  messaging_state = app["messaging_status_state"]
  try:
    from cereal import messaging
    sm = messaging.SubMaster(list(MESSAGING_STATUS_SERVICES))
  except Exception as exc:
    messaging_state.update(default_messaging_status())
    messaging_state["lastError"] = str(exc)[:200]
    return

  while True:
    try:
      sm.update(0)
      messaging_state.update(update_messaging_status_from_sm(sm))
      messaging_state["lastError"] = ""
    except Exception as exc:
      messaging_state.update(default_messaging_status())
      messaging_state["lastError"] = str(exc)[:200]
    await asyncio.sleep(MESSAGING_STATUS_INTERVAL_S)


async def start_messaging_status(app: web.Application) -> None:
  app["background_tasks"]["messaging_status"] = asyncio.create_task(messaging_status_loop(app))


async def stop_messaging_status(app: web.Application) -> None:
  task = app["background_tasks"].get("messaging_status")
  if task is not None:
    task.cancel()
    try:
      await task
    except asyncio.CancelledError:
      pass
    app["background_tasks"]["messaging_status"] = None


async def status_broadcast_loop(app: web.Application) -> None:
  transport = app.get("status_broadcast_transport")
  if transport is None:
    return
  status_state = app["status_broadcast_state"]
  messaging_state = app["messaging_status_state"]
  navi_http_state = app["navi_http_state"]

  while True:
    try:
      payload = build_status_payload(dict(messaging_state), dict(navi_http_state))
      data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
      for target in STATUS_BROADCAST_TARGETS:
        transport.sendto(data, (target, STATUS_BROADCAST_PORT))
      status_state["lastPayload"] = payload
      status_state["lastSentAt"] = time.time()
      status_state["lastError"] = ""
    except Exception as exc:
      status_state["lastError"] = str(exc)[:200]
    await asyncio.sleep(STATUS_BROADCAST_INTERVAL_S)


async def start_status_broadcast(app: web.Application) -> None:
  loop = asyncio.get_running_loop()
  try:
    transport, _ = await loop.create_datagram_endpoint(
      asyncio.DatagramProtocol,
      local_addr=(DEFAULT_HOST, 0),
      allow_broadcast=True,
    )
    app["status_broadcast_transport"] = transport
    app["status_broadcast_task"] = asyncio.create_task(status_broadcast_loop(app))
    app["status_broadcast_state"]["lastError"] = ""
  except Exception as exc:
    app["status_broadcast_state"]["lastError"] = str(exc)[:200]


async def stop_status_broadcast(app: web.Application) -> None:
  task = app.get("status_broadcast_task")
  if task is not None:
    task.cancel()
    try:
      await task
    except asyncio.CancelledError:
      pass
  transport = app.get("status_broadcast_transport")
  if transport is not None:
    transport.close()


def add_navi_http_routes(app: web.Application) -> None:
  app.router.add_get("/health", api_navi_http_health)
  app.router.add_get("/api/navi/health", api_navi_http_health)
  app.router.add_post("/api/navi", api_navi_http_post)
  app.router.add_post("/api/navi/{tmap_version}", api_navi_http_post)


async def start_navi_http(app: web.Application) -> None:
  navi_app = web.Application(client_max_size=NAVI_HTTP_MAX_BODY_SIZE)
  navi_app["navi_http_state"] = app["navi_http_state"]
  add_navi_http_routes(navi_app)
  runner = web.AppRunner(navi_app, access_log=None)
  try:
    await runner.setup()
    site = web.TCPSite(runner, DEFAULT_HOST, NAVI_HTTP_PORT)
    await site.start()
    app["background_tasks"]["navi_http_runner"] = runner
    app["navi_http_state"]["available"] = True
    app["navi_http_state"]["lastError"] = ""
  except Exception as exc:
    app["navi_http_state"]["available"] = False
    app["navi_http_state"]["lastError"] = str(exc)[:200]
    await runner.cleanup()


async def stop_navi_http(app: web.Application) -> None:
  runner = app["background_tasks"].get("navi_http_runner")
  if runner is not None:
    await runner.cleanup()
    app["background_tasks"]["navi_http_runner"] = None
  app["navi_http_state"]["available"] = False


def make_app() -> web.Application:
  app = web.Application(client_max_size=NAVI_HTTP_MAX_BODY_SIZE)
  app["status_broadcast_state"] = {"lastPayload": {}, "lastSentAt": 0.0, "lastError": ""}
  app["messaging_status_state"] = default_messaging_status()
  app["navi_http_state"] = default_navi_http_state()
  app["background_tasks"] = {"messaging_status": None, "navi_http_runner": None}
  app.on_startup.append(start_messaging_status)
  app.on_startup.append(start_navi_http)
  app.on_startup.append(start_status_broadcast)
  app.on_startup.append(start_navigation_udp)
  app.on_cleanup.append(stop_status_broadcast)
  app.on_cleanup.append(stop_navi_http)
  app.on_cleanup.append(stop_messaging_status)
  app.on_cleanup.append(stop_navigation_udp)
  app.router.add_get("/", index)
  app.router.add_get("/api/health", api_health)
  app.router.add_get("/api/params_bulk", api_params_bulk)
  app.router.add_post("/api/param_set", api_param_set)
  app.router.add_get("/api/status_broadcast", api_status_broadcast)
  app.router.add_get("/api/carrot_learning", api_carrot_learning)
  app.router.add_post("/api/carrot_learning", api_carrot_learning_action)
  app.router.add_get("/api/fishop_hardware", api_fishop_hardware)
  app.router.add_get("/api/navigation_event", api_navigation_event)
  app.router.add_post("/api/navigation_event", api_navigation_event_action)
  add_navi_http_routes(app)
  app.router.add_get("/api/phone_speed_limit", api_phone_speed_limit)
  app.router.add_post("/api/phone_speed_limit", api_phone_speed_limit_action)
  return app


def main() -> None:
  parser = argparse.ArgumentParser(description="CarrotPilot C3 local web service")
  parser.add_argument("--host", default=DEFAULT_HOST)
  parser.add_argument("--port", type=int, default=LOCAL_WEB_PORT)
  args = parser.parse_args()
  web.run_app(make_app(), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
  main()
