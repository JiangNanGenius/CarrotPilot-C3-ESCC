#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import ipaddress
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
CARROT_MAN_PEER_MAX_AGE_S = 30.0
MESSAGING_STATUS_SERVICES = (
  "carState",
  "selfdriveState",
  "controlsState",
  "longitudinalPlanSP",
  "carStateSP",
)
MESSAGING_STATUS_INTERVAL_S = 0.2
NAVIGATION_UDP_PORT = 7706
NAVI_TCP_PORT = 7712
NAVI_TCP_MAX_LINE_BYTES = 1024 * 1024
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
SPEED_LIMIT_POLICY_NAMES = {
  0: "car_state_only",
  1: "map_data_only",
  2: "car_state_priority",
  3: "map_data_priority",
  4: "combined",
  5: "phone_priority",
}
SPEED_LIMIT_OFFSET_TYPE_NAMES = {
  0: "off",
  1: "fixed",
  2: "percentage",
}
SPEED_LIMIT_MODE_NAMES = {
  0: "off",
  1: "information",
  2: "warning",
  3: "assist",
}

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
  "NeuralNetworkLateralControl": {"type": "bool", "default": True, "writable": True},
  "CarrotLearningActive": {"type": "bool", "default": False, "writable": True},
  "CarrotLearningAutoApply": {"type": "bool", "default": False, "writable": True},
  "CarrotTunerApplyLat": {"type": "bool", "default": True, "writable": True},
  "CarrotTunerApplyLong": {"type": "bool", "default": True, "writable": True},
  "CarrotPhoneSpeedLimitEnabled": {"type": "bool", "default": True, "writable": True},
  "CarrotMapOverlayEnabled": {"type": "bool", "default": False, "writable": True},
  "GeniusVisualMode": {"type": "int", "default": 2, "writable": True, "min": 0, "max": 2},
  "GeniusLaneLineStyle": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 2},
  "GeniusLeadRadarVisualMode": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 2},
  "GeniusLaneChangeVisuals": {"type": "bool", "default": True, "writable": True},
  "GeniusFishopVisualOverlay": {"type": "bool", "default": False, "writable": True},
  "SpeedLimitPolicy": {"type": "int", "default": 5, "writable": True, "min": 0, "max": 5},
  "SpeedLimitOffsetType": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 2},
  "SpeedLimitValueOffset": {"type": "int", "default": 0, "writable": True, "min": -30, "max": 30},
  "SpeedLimitMode": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 3},
  "CurveSpeedControlMode": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 3},
  "AutoCurveSpeedLowerLimit": {"type": "int", "default": 30, "writable": True, "min": 10, "max": 120},
  "AutoCurveSpeedFactor": {"type": "int", "default": 120, "writable": True, "min": 50, "max": 250},
  "AutoCurveSpeedAggressiveness": {"type": "int", "default": 100, "writable": True, "min": 50, "max": 200},
  "AutoNaviSpeedDecelRate": {"type": "int", "default": 120, "writable": True, "min": 50, "max": 300},
  "CarrotRainWet": {"type": "bool", "default": False, "writable": True},
  "OffroadMode": {"type": "bool", "default": False, "writable": False},
  "IsOnroad": {"type": "bool", "default": False, "writable": False},
  "OpenpilotEnabledToggle": {"type": "bool", "default": True, "writable": False},
  "SshEnabled": {"type": "bool", "default": False, "writable": False},
  "SpeedFromPCM": {"type": "int", "default": 1, "writable": False, "min": 0, "max": 1},
  "CarrotActiveSpeedControlEnabled": {"type": "bool", "default": False, "writable": True},
  "CarrotAutoTurnControlEnabled": {"type": "bool", "default": False, "writable": True},
  "CarrotTrafficStopEnabled": {"type": "bool", "default": False, "writable": True},
  "TrafficLightDetectMode": {"type": "int", "default": 2, "writable": True, "min": 0, "max": 3},
  "TrafficStopDistanceAdjust": {"type": "int", "default": -150, "writable": True, "min": -500, "max": 500},
  "DynamicExperimentalControl": {"type": "bool", "default": False, "writable": True},
  "MyDrivingMode": {"type": "int", "default": 3, "writable": True, "min": 0, "max": 5},
  "MyDrivingModeAuto": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 1},
  "CruiseEcoControl": {"type": "int", "default": 2, "writable": True, "min": 0, "max": 3},
  "CarrotCruiseDecel": {"type": "int", "default": -1, "writable": True, "min": -1, "max": 200},
  "CarrotCruiseAtcDecel": {"type": "int", "default": -1, "writable": True, "min": -1, "max": 200},
  "StopDistanceCarrot": {"type": "int", "default": 550, "writable": True, "min": 300, "max": 1200},
  "DynamicTFollow": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 100},
  "TFollowDecelBoost": {"type": "int", "default": 10, "writable": True, "min": 0, "max": 100},
  "TFollowSpeedFactor": {"type": "int", "default": 0, "writable": True, "min": -100, "max": 100},
  "DynamicTFollowLC": {"type": "int", "default": 100, "writable": True, "min": 50, "max": 200},
  "EnableSpeedTF": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 1},
  "TFollowGap1": {"type": "int", "default": 110, "writable": True, "min": 70, "max": 300},
  "TFollowGap2": {"type": "int", "default": 120, "writable": True, "min": 80, "max": 350},
  "TFollowGap3": {"type": "int", "default": 140, "writable": True, "min": 90, "max": 400},
  "TFollowGap4": {"type": "int", "default": 160, "writable": True, "min": 100, "max": 450},
  "CruiseMaxVals0": {"type": "int", "default": 160, "writable": True, "min": 20, "max": 260},
  "CruiseMaxVals1": {"type": "int", "default": 200, "writable": True, "min": 20, "max": 260},
  "CruiseMaxVals2": {"type": "int", "default": 160, "writable": True, "min": 20, "max": 240},
  "CruiseMaxVals3": {"type": "int", "default": 130, "writable": True, "min": 20, "max": 220},
  "CruiseMaxVals4": {"type": "int", "default": 110, "writable": True, "min": 20, "max": 200},
  "CruiseMaxVals5": {"type": "int", "default": 95, "writable": True, "min": 20, "max": 180},
  "CruiseMaxVals6": {"type": "int", "default": 80, "writable": True, "min": 20, "max": 160},
  "LongTuningKpV": {"type": "int", "default": 100, "writable": True, "min": 0, "max": 300},
  "LongTuningKiV": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 300},
  "LongTuningKf": {"type": "int", "default": 100, "writable": True, "min": 0, "max": 300},
  "LongActuatorDelay": {"type": "int", "default": 20, "writable": True, "min": 0, "max": 200},
  "VEgoStopping": {"type": "int", "default": 50, "writable": True, "min": 0, "max": 150},
  "RadarReactionFactor": {"type": "int", "default": 100, "writable": True, "min": 0, "max": 300},
  "JLeadFactor3": {"type": "int", "default": 0, "writable": True, "min": -200, "max": 300},
  "AChangeCostStarting": {"type": "int", "default": 10, "writable": True, "min": 0, "max": 100},
  "TurnSpeedControlMode": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 3},
  "AutoTurnControl": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 1},
  "AutoTurnControlSpeedTurn": {"type": "int", "default": 20, "writable": True, "min": 5, "max": 80},
  "AutoTurnControlTurnEnd": {"type": "int", "default": 6, "writable": True, "min": 1, "max": 30},
  "AutoTurnMapChange": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 1},
  "PathOffset": {"type": "int", "default": 0, "writable": True, "min": -150, "max": 150},
  "SteerActuatorDelay": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 200},
  "SteerRatioRate": {"type": "int", "default": 100, "writable": True, "min": 50, "max": 150},
  "UseLaneLineSpeed": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 1},
  "UseLaneLineCurveSpeed": {"type": "int", "default": 0, "writable": True, "min": 0, "max": 1},
  "FishopLaneCurveEnabled": {"type": "bool", "default": False, "writable": True},
  "FishopLidarBlindspotEnabled": {"type": "bool", "default": False, "writable": True},
  "FishopLidarLaneDataEnabled": {"type": "bool", "default": False, "writable": True},
  "FishopAutoOvertakeEnabled": {"type": "bool", "default": False, "writable": True},
}

HIGH_RISK_FEATURE_GATES: tuple[dict[str, Any], ...] = (
  {
    "key": "trafficStop",
    "label": "Traffic Light Stop",
    "param": "CarrotTrafficStopEnabled",
    "requiredEvidence": (
      "parked_navigation_replay",
      "red_light_input_consistency",
      "Seltos 2023 ESCC road test",
      "driver confirmation gate",
    ),
  },
  {
    "key": "autoTurn",
    "label": "Auto Turn Slowdown",
    "param": "CarrotAutoTurnControlEnabled",
    "requiredEvidence": (
      "fresh turn-by-turn input",
      "curve and turn-type consistency",
      "Seltos 2023 ESCC road test",
      "planner handoff review",
    ),
  },
  {
    "key": "activeSpeed",
    "label": "Carrot Active Speed Control",
    "param": "CarrotActiveSpeedControlEnabled",
    "requiredEvidence": (
      "phone/car/map speed source comparison",
      "Speed Limit Assist road test",
      "braking comfort review",
      "Seltos 2023 ESCC road test",
    ),
  },
  {
    "key": "autoTunerAutoApply",
    "label": "Auto-Tuner Auto Apply",
    "param": "CarrotLearningAutoApply",
    "requiredEvidence": (
      "offroad-only apply proof",
      "manual recommendation review history",
      "parameter rollback point",
      "Seltos 2023 stability review",
    ),
  },
  {
    "key": "fishopAutoOvertake",
    "label": "fishop Auto Overtake",
    "param": "FishopAutoOvertakeEnabled",
    "requiredEvidence": (
      "fresh lane input",
      "fresh lidar and camera blindspot input",
      "existing safe lane-change chain review",
      "driver confirmation gate",
      "Seltos 2023 ESCC road test",
    ),
  },
)

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
  "nSdiPlusDist",
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

NAVIGATION_BOOLEAN_FIELDS = (
  "trafficRedLightOn",
  "trafficGreenLightOn",
  "redLightOn",
  "greenLightOn",
  "leftLightOn",
  "speedBump",
  "speedBumpValid",
  "schoolZone",
  "childrenProtectionZone",
)

NAVIGATION_TEXT_FIELDS = (
  "szTBTMainText",
  "szTBTMainTextNext",
  "roadName",
  "currentRoadName",
  "trafficStraight",
  "trafficLeft",
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

NAVIGATION_SPEED_BUMP_DISTANCE_FIELDS = (
  "nSpeedBumpDist",
  "nSpeedBumpDistance",
  "speedBumpDist",
  "speedBumpDistance",
  "bumpDist",
  "bumpDistance",
)

NAVIGATION_MODEL_SPEED_KPH_FIELDS = (
  "modelSpeedKph",
  "modelSpeedLimitKph",
  "modelSpeed",
  "modelSpeedLimit",
  "modelTargetSpeed",
)

NAVIGATION_MODEL_SPEED_MS_FIELDS = (
  "modelSpeedMS",
  "modelSpeedMps",
  "modelSpeedLimitMS",
  "modelSpeedLimitMps",
)

ACTION_PARAMS = {
  "apply": "CarrotLearningApply",
  "ignore": "CarrotLearningIgnore",
  "clear": "CarrotLearningClear",
}

PARAM_LIMITS = {
  "CurveSpeedControlMode": (0, 3),
  "AutoCurveSpeedLowerLimit": (10, 120),
  "AutoCurveSpeedFactor": (50, 250),
  "AutoCurveSpeedAggressiveness": (50, 200),
  "AutoNaviSpeedDecelRate": (50, 300),
  "MyDrivingMode": (0, 5),
  "MyDrivingModeAuto": (0, 1),
  "CruiseEcoControl": (0, 3),
  "CarrotCruiseDecel": (-1, 200),
  "CarrotCruiseAtcDecel": (-1, 200),
  "CruiseMaxVals0": (20, 260),
  "CruiseMaxVals1": (20, 260),
  "CruiseMaxVals2": (20, 240),
  "CruiseMaxVals3": (20, 220),
  "CruiseMaxVals4": (20, 200),
  "CruiseMaxVals5": (20, 180),
  "CruiseMaxVals6": (20, 160),
  "TFollowGap1": (70, 300),
  "TFollowGap2": (80, 350),
  "TFollowGap3": (90, 400),
  "TFollowGap4": (100, 450),
  "JLeadFactor3": (-200, 300),
  "AChangeCostStarting": (0, 100),
  "PathOffset": (-150, 150),
  "SteerActuatorDelay": (0, 200),
  "SteerRatioRate": (50, 150),
  "TurnSpeedControlMode": (0, 3),
  "AutoTurnControl": (0, 1),
  "AutoTurnControlSpeedTurn": (5, 80),
  "AutoTurnControlTurnEnd": (1, 30),
  "AutoTurnMapChange": (0, 1),
  "UseLaneLineSpeed": (0, 1),
  "UseLaneLineCurveSpeed": (0, 1),
  "DynamicTFollow": (0, 100),
  "TFollowDecelBoost": (0, 100),
  "TFollowSpeedFactor": (-100, 100),
  "DynamicTFollowLC": (50, 200),
  "EnableSpeedTF": (0, 1),
  "StopDistanceCarrot": (300, 1200),
  "LongTuningKpV": (0, 300),
  "LongTuningKiV": (0, 300),
  "LongTuningKf": (0, 300),
  "LongActuatorDelay": (0, 200),
  "VEgoStopping": (0, 150),
  "RadarReactionFactor": (0, 300),
  "TrafficLightDetectMode": (0, 3),
  "TrafficStopDistanceAdjust": (-500, 500),
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


def _param_int(params: Any | None, key: str, default: int = 0) -> int:
  if params is None:
    return default
  try:
    return int(params.get_int(key))
  except Exception:
    return int(_as_float(_params_get(params, key, default), float(default)))


def _param_bool(params: Any | None, key: str, default: bool = False) -> bool:
  if params is None:
    return default
  try:
    return bool(params.get_bool(key))
  except Exception:
    raw = _params_get(params, key, "1" if default else "0")
    return _as_bool(raw)


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


def _requested_param_names_from_body(body: Any) -> list[str]:
  if not isinstance(body, dict):
    return []
  raw_names = body.get("names")
  if isinstance(raw_names, str):
    return _requested_param_names(raw_names)
  if isinstance(raw_names, list):
    names: list[str] = []
    for raw in raw_names:
      name = str(raw).strip()
      if name and name not in names:
        names.append(name)
      if len(names) >= PARAM_API_MAX_NAMES:
        break
    return names
  raw_name = body.get("name")
  return _requested_param_names(str(raw_name or ""))


def _default_value_for_param(name: str) -> Any:
  if name in VIRTUAL_PARAM_DEFAULTS:
    return VIRTUAL_PARAM_DEFAULTS[name]
  meta = _param_meta(name)
  if meta is None:
    return 0
  return _json_safe_value(meta.get("default"))


def params_bulk_state(names: Iterable[str]) -> dict[str, Any]:
  values: dict[str, Any] = {}
  writable: dict[str, bool] = {}
  defaults: dict[str, Any] = {}
  types: dict[str, str] = {}
  unknown: list[str] = []
  params, error = _params_state()

  for name in names:
    defaults[name] = _default_value_for_param(name)
    if name in VIRTUAL_PARAM_DEFAULTS:
      values[name] = VIRTUAL_PARAM_DEFAULTS[name]
      writable[name] = False
      types[name] = "virtual"
      continue

    meta = _param_meta(name)
    if meta is None:
      values[name] = 0
      writable[name] = False
      defaults[name] = 0
      types[name] = "unknown"
      unknown.append(name)
      continue

    value = meta.get("default")
    if params is not None:
      value = _params_get(params, name, meta.get("default"))
    values[name] = _json_safe_value(_normalize_param_value(value, meta))
    writable[name] = bool(meta.get("writable", False))
    types[name] = str(meta.get("type", "string"))

  return {
    "hasParams": params is not None,
    "has_params": params is not None,
    "values": values,
    "writable": writable,
    "readOnly": {name: not bool(writable.get(name, False)) for name in values},
    "defaults": defaults,
    "types": types,
    "unknown": unknown,
    "source": "local_safe_whitelist",
    "error": error if params is None else "",
  }


def get_param_values(names: Iterable[str], _defaults: dict[str, Any] | None = None) -> dict[str, Any]:
  return params_bulk_state(names)["values"]


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
    "has_params": True,
    "writable": True,
  }


def set_param_value(name: str, value: Any) -> dict[str, Any]:
  return set_param_from_api(name, value)


def _safe_navigation_text(value: Any) -> str:
  text = _decode_param_text(value).replace("\x00", "").strip()
  return text[:120]


def _navigation_payload_candidates(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
  yield payload
  for key in ("payload", "navigation", "nav", "data", "rgdata", "sinf", "ssinf"):
    nested = payload.get(key)
    if isinstance(nested, dict):
      yield nested


def _navigation_value(candidates: Iterable[dict[str, Any]], key: str) -> Any:
  for candidate in candidates:
    if key in candidate:
      return candidate.get(key)
  return None


def _navigation_numeric_value(candidates: Iterable[dict[str, Any]], keys: Iterable[str], default: float = 0.0) -> tuple[float, str]:
  for key in keys:
    value = _navigation_value(candidates, key)
    if value is None:
      continue
    return _as_float(value, default), key
  return default, ""


def _navigation_bool_value(candidates: Iterable[dict[str, Any]], keys: Iterable[str]) -> bool:
  for key in keys:
    value = _navigation_value(candidates, key)
    if value is not None:
      return _as_bool(value)
  return False


def _navigation_model_speed(candidates: list[dict[str, Any]]) -> dict[str, Any]:
  speed_ms, source_field = _navigation_numeric_value(candidates, NAVIGATION_MODEL_SPEED_MS_FIELDS, -1.0)
  speed_kph = speed_ms / KPH_TO_MS if speed_ms > 0.0 else 0.0
  if speed_kph <= 0.0:
    speed_kph, source_field = _navigation_numeric_value(candidates, NAVIGATION_MODEL_SPEED_KPH_FIELDS, -1.0)
  valid = speed_kph > 0.0 and speed_kph <= PHONE_SPEED_LIMIT_MAX_KPH
  return {
    "available": valid,
    "speedKph": round(speed_kph, 3) if valid else 0.0,
    "sourceField": source_field if valid else "",
    "readOnly": True,
    "controlOutput": False,
  }


def _navigation_hazard_evidence(candidates: list[dict[str, Any]], numeric: dict[str, float | int]) -> dict[str, Any]:
  speed_bump_distance, speed_bump_field = _navigation_numeric_value(candidates, NAVIGATION_SPEED_BUMP_DISTANCE_FIELDS, 0.0)
  explicit_speed_bump = _navigation_bool_value(candidates, ("speedBump", "speedBumpValid"))
  sdi_dist = _as_float(numeric.get("nSdiDist"), 0.0)
  sdi_speed = _as_float(numeric.get("nSdiSpeedLimit"), 0.0)
  sdi_type = int(_as_float(numeric.get("nSdiType"), 0.0))
  plus_dist = _as_float(numeric.get("nSdiPlusDist"), 0.0)
  plus_speed = _as_float(numeric.get("nSdiPlusSpeedLimit"), 0.0)
  plus_type = int(_as_float(numeric.get("nSdiPlusType"), 0.0))
  return {
    "sdi": {
      "available": sdi_dist > 0.0 or sdi_speed > 0.0 or sdi_type > 0,
      "type": sdi_type,
      "speedLimitKph": round(sdi_speed, 3) if sdi_speed > 0.0 else 0.0,
      "distanceM": round(sdi_dist, 3) if sdi_dist > 0.0 else 0.0,
      "plusType": plus_type,
      "plusSpeedLimitKph": round(plus_speed, 3) if plus_speed > 0.0 else 0.0,
      "plusDistanceM": round(plus_dist, 3) if plus_dist > 0.0 else 0.0,
    },
    "speedBump": {
      "available": explicit_speed_bump or speed_bump_distance > 0.0,
      "distanceM": round(speed_bump_distance, 3) if speed_bump_distance > 0.0 else 0.0,
      "sourceField": speed_bump_field,
    },
    "schoolZone": {
      "available": _navigation_bool_value(candidates, ("schoolZone", "childrenProtectionZone")),
    },
    "readOnly": True,
    "controlOutput": False,
  }


def _traffic_light_state(candidates: list[dict[str, Any]], text: dict[str, str]) -> dict[str, Any]:
  straight = (text.get("trafficStraight") or "").upper()
  left = (text.get("trafficLeft") or "").upper()
  red = (
    _navigation_bool_value(candidates, ("trafficRedLightOn", "redLightOn"))
    or straight == "RED_LIGHT_ON"
  )
  green = (
    _navigation_bool_value(candidates, ("trafficGreenLightOn", "greenLightOn"))
    or straight == "GREEN_LIGHT_ON"
  )
  left_green = _navigation_bool_value(candidates, ("leftLightOn",)) or left == "GREEN_LIGHT_ON"
  return {
    "red": red,
    "green": green,
    "leftGreen": left_green,
    "straight": straight,
    "left": left,
  }


def _navigation_control_preview(params: Any | None, event: dict[str, Any], traffic: dict[str, Any]) -> dict[str, Any]:
  numeric = event.get("numeric", {}) if isinstance(event.get("numeric"), dict) else {}
  hazards = event.get("hazards", {}) if isinstance(event.get("hazards"), dict) else {}
  model_speed = event.get("modelSpeed", {}) if isinstance(event.get("modelSpeed"), dict) else {}
  sdi = hazards.get("sdi", {}) if isinstance(hazards.get("sdi"), dict) else {}
  speed_bump = hazards.get("speedBump", {}) if isinstance(hazards.get("speedBump"), dict) else {}
  tbt_dist = _as_float(numeric.get("nTBTDist"), 0.0)
  turn_type = int(_as_float(numeric.get("nTBTTurnType"), 0.0))
  next_turn_type = int(_as_float(numeric.get("nTBTTurnTypeNext"), 0.0))
  speed_limit_kph = _as_float(event.get("speedLimitKph"), 0.0)

  traffic_stop_enabled = _param_bool(params, "CarrotTrafficStopEnabled", False)
  auto_turn_enabled = _param_bool(params, "CarrotAutoTurnControlEnabled", False)
  active_speed_enabled = _param_bool(params, "CarrotActiveSpeedControlEnabled", False)
  overtake_enabled = _param_bool(params, "FishopAutoOvertakeEnabled", False)

  traffic_candidate = bool(traffic.get("red")) and tbt_dist > 0.0
  turn_candidate = tbt_dist > 0.0 and (turn_type > 0 or next_turn_type > 0)
  active_speed_candidate = speed_limit_kph > 0.0 or _as_float(sdi.get("speedLimitKph"), 0.0) > 0.0 or bool(model_speed.get("available"))
  speed_bump_candidate = bool(speed_bump.get("available"))

  return {
    "trafficStop": {
      "enabledParam": traffic_stop_enabled,
      "candidate": traffic_candidate,
      "redLightInput": bool(traffic.get("red")),
      "greenLightInput": bool(traffic.get("green")),
      "distanceM": round(tbt_dist, 3) if tbt_dist > 0.0 else 0.0,
      "state": "off" if not traffic_stop_enabled else ("active_input" if traffic_candidate else "enabled_waiting_input"),
      "controlOutput": False,
    },
    "autoTurn": {
      "enabledParam": auto_turn_enabled,
      "candidate": turn_candidate,
      "turnType": turn_type,
      "nextTurnType": next_turn_type,
      "distanceM": round(tbt_dist, 3) if tbt_dist > 0.0 else 0.0,
      "state": "off" if not auto_turn_enabled else ("active_input" if turn_candidate else "enabled_waiting_input"),
      "controlOutput": False,
    },
    "activeSpeed": {
      "enabledParam": active_speed_enabled,
      "candidate": active_speed_candidate or speed_bump_candidate,
      "phoneOrSdiSpeedLimitKph": round(speed_limit_kph or _as_float(sdi.get("speedLimitKph"), 0.0), 3),
      "modelSpeedKph": model_speed.get("speedKph", 0.0),
      "speedBumpInput": speed_bump_candidate,
      "state": "off" if not active_speed_enabled else ("active_input" if active_speed_candidate or speed_bump_candidate else "enabled_waiting_input"),
      "controlOutput": False,
    },
    "overtake": {
      "enabledParam": overtake_enabled,
      "commandIgnored": bool(event.get("commandIgnored", False)),
      "highRiskCommandSeen": bool(event.get("highRiskCommandSeen", False)),
      "state": "local_command" if event.get("highRiskCommandSeen") else "no_command",
      "controlOutput": False,
    },
    "readOnly": True,
    "controlOutput": False,
  }


def _feature_gate_blocking_reasons(enabled_param: bool, candidate: bool) -> list[str]:
  if not enabled_param:
    return ["param_off"]
  reasons = ["control_output_not_published"]
  if not candidate:
    reasons.insert(0, "input_waiting")
  return reasons


def _feature_gate_state(enabled_param: bool, candidate: bool) -> str:
  if not enabled_param:
    return "off"
  if not candidate:
    return "enabled_waiting_input"
  return "active_input"


def _navigation_preview_feature(nav_event: dict[str, Any], key: str) -> tuple[bool, dict[str, Any]]:
  preview = nav_event.get("controlPreview", {}) if isinstance(nav_event.get("controlPreview"), dict) else {}
  feature = preview.get(key, {}) if isinstance(preview.get(key), dict) else {}
  return bool(feature.get("candidate", False)), feature


def _feature_gate_evidence(feature_key: str, nav_event: dict[str, Any], learning: dict[str, Any],
                           fishop: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
  if feature_key == "trafficStop":
    candidate, preview = _navigation_preview_feature(nav_event, "trafficStop")
    traffic = nav_event.get("trafficLight", {}) if isinstance(nav_event.get("trafficLight"), dict) else {}
    return candidate, {
      "source": nav_event.get("source", ""),
      "updatedAt": nav_event.get("updatedAt", 0.0),
      "redLightInput": bool(traffic.get("red", False)),
      "greenLightInput": bool(traffic.get("green", False)),
      "preview": preview,
    }

  if feature_key == "autoTurn":
    candidate, preview = _navigation_preview_feature(nav_event, "autoTurn")
    return candidate, {
      "source": nav_event.get("source", ""),
      "updatedAt": nav_event.get("updatedAt", 0.0),
      "preview": preview,
    }

  if feature_key == "activeSpeed":
    candidate, preview = _navigation_preview_feature(nav_event, "activeSpeed")
    return candidate, {
      "source": nav_event.get("source", ""),
      "updatedAt": nav_event.get("updatedAt", 0.0),
      "speedLimitKph": nav_event.get("speedLimitKph", 0.0),
      "preview": preview,
    }

  if feature_key == "autoTunerAutoApply":
    summary = learning.get("recommendationSummary", {}) if isinstance(learning.get("recommendationSummary"), dict) else {}
    pending_count = int(_as_float(summary.get("pending"), 0.0))
    candidate = bool(learning.get("pending", False) or pending_count > 0)
    return candidate, {
      "active": bool(learning.get("active", False)),
      "pending": bool(learning.get("pending", False)),
      "pendingRecommendationCount": pending_count,
      "autoApplyStateReported": bool(learning.get("autoApply", False)),
      "source": learning.get("source", ""),
      "createdAt": learning.get("createdAt", 0.0),
    }

  if feature_key == "fishopAutoOvertake":
    snapshot = fishop.get("snapshot", {}) if isinstance(fishop.get("snapshot"), dict) else {}
    overtake = snapshot.get("overtake", {}) if isinstance(snapshot.get("overtake"), dict) else {}
    preview = overtake.get("suggestionPreview", {}) if isinstance(overtake.get("suggestionPreview"), dict) else {}
    candidate = bool(overtake.get("requested", False) or overtake.get("commandSeen", False) or preview.get("readyForSuggestion", False))
    return candidate, {
      "inputAvailable": bool(fishop.get("inputAvailable", False)),
      "sensorOnline": bool(snapshot.get("sensorOnline", False)),
      "direction": overtake.get("direction", ""),
      "commandSeen": bool(overtake.get("commandSeen", False)),
      "requested": bool(overtake.get("requested", False)),
      "suggestionPreview": preview,
    }

  return False, {}


def carrot_feature_gate_state() -> dict[str, Any]:
  params, error = _params_state()
  nav_state = navigation_event_state()
  nav_event = nav_state.get("event", {}) if isinstance(nav_state, dict) and isinstance(nav_state.get("event"), dict) else {}
  learning = get_learning_state()
  fishop = fishop_state()
  features: dict[str, Any] = {}

  for spec in HIGH_RISK_FEATURE_GATES:
    key = str(spec["key"])
    param = str(spec["param"])
    enabled_param = _param_bool(params, param, False)
    candidate, evidence = _feature_gate_evidence(key, nav_event, learning, fishop)
    features[key] = {
      "label": str(spec["label"]),
      "param": param,
      "enabledParam": enabled_param,
      "candidate": candidate,
      "state": _feature_gate_state(enabled_param, candidate),
      "readyForControl": False,
      "readOnly": True,
      "controlOutput": False,
      "blockingReasons": _feature_gate_blocking_reasons(enabled_param, candidate),
      "requiredEvidence": list(spec["requiredEvidence"]),
      "evidence": evidence,
    }

  enabled_features = [key for key, feature in features.items() if feature["enabledParam"]]
  candidate_features = [key for key, feature in features.items() if feature["candidate"]]
  return {
    "hasParams": params is not None,
    "error": error,
    "stage": "diagnostic_preview",
    "readOnly": True,
    "controlOutput": False,
    "controlOutputAllowed": False,
    "allBlocked": False,
    "enabledFeatures": enabled_features,
    "candidateFeatures": candidate_features,
    "features": features,
    "notes": (
      "Settings are user-accessible from Super Advanced.",
      "This endpoint reports local inputs and whether this bridge publishes a direct control output.",
    ),
  }


def _navigation_payload_event(payload: dict[str, Any], source: str, params: Any | None = None) -> dict[str, Any]:
  candidates = list(_navigation_payload_candidates(payload))
  numeric: dict[str, float | int] = {}
  booleans: dict[str, bool] = {}
  text: dict[str, str] = {}
  for key in NAVIGATION_NUMERIC_FIELDS:
    value = _navigation_value(candidates, key)
    if value is None:
      continue
    value = _as_float(value, 0.0)
    numeric[key] = int(value) if float(value).is_integer() else round(value, 7)
  for key in NAVIGATION_BOOLEAN_FIELDS:
    value = _navigation_value(candidates, key)
    if value is not None:
      booleans[key] = _as_bool(value)
  for key in NAVIGATION_TEXT_FIELDS:
    value = _navigation_value(candidates, key)
    if value is not None:
      text[key] = _safe_navigation_text(value)

  command = _safe_navigation_text(_navigation_value(candidates, NAVIGATION_COMMAND_FIELDS[0]) or "")
  command_arg = _safe_navigation_text(_navigation_value(candidates, NAVIGATION_COMMAND_FIELDS[1]) or "")
  command_upper = command.upper()
  ignored_command = bool(command or command_arg)
  high_risk_command = command_upper in HIGH_RISK_NAV_COMMANDS

  speed_kph, speed_field = _extract_phone_speed_kph(payload)
  hazards = _navigation_hazard_evidence(candidates, numeric)
  model_speed = _navigation_model_speed(candidates)
  traffic = _traffic_light_state(candidates, text)
  event = {
    "updatedAt": time.time(),
    "source": _safe_source_text(source),
    "numeric": numeric,
    "booleans": booleans,
    "text": text,
    "hazards": hazards,
    "modelSpeed": model_speed,
    "trafficLight": traffic,
    "speedLimitKph": round(speed_kph, 3) if speed_kph is not None else 0.0,
    "speedLimitSourceField": speed_field,
    "commandIgnored": ignored_command,
    "highRiskCommandSeen": high_risk_command,
    "ignoredCommand": command,
    "ignoredCommandArg": command_arg,
    "readOnly": True,
    "controlOutput": False,
  }
  event["controlPreview"] = _navigation_control_preview(params, event, traffic)
  return event


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

  event = _navigation_payload_event(payload, source, params)
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


def _status_payload_navigation_evidence(event: dict[str, Any]) -> dict[str, Any]:
  hazards = event.get("hazards") if isinstance(event, dict) else {}
  model_speed = event.get("modelSpeed") if isinstance(event, dict) else {}
  control_preview = event.get("controlPreview") if isinstance(event, dict) else {}
  traffic = event.get("trafficLight") if isinstance(event, dict) else {}
  hazards = hazards if isinstance(hazards, dict) else {}
  model_speed = model_speed if isinstance(model_speed, dict) else {}
  control_preview = control_preview if isinstance(control_preview, dict) else {}
  traffic = traffic if isinstance(traffic, dict) else {}
  speed_bump = hazards.get("speedBump") if isinstance(hazards.get("speedBump"), dict) else {}
  sdi = hazards.get("sdi") if isinstance(hazards.get("sdi"), dict) else {}
  return {
    "hazards": hazards,
    "modelSpeed": model_speed,
    "controlPreview": control_preview,
    "trafficLight": traffic,
    "speedBumpDistanceM": _as_float(speed_bump.get("distanceM"), 0.0),
    "speedBumpAvailable": bool(speed_bump.get("available", False)),
    "modelSpeedKph": _as_float(model_speed.get("speedKph"), 0.0),
    "modelSpeedAvailable": bool(model_speed.get("available", False)),
    "sdiType": int(_as_float(sdi.get("type"), 0.0)),
    "sdiPlusDistanceM": _as_float(sdi.get("plusDistanceM"), 0.0),
    "controlOutput": False,
    "readOnly": True,
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


def build_status_payload(runtime_status: dict[str, Any] | None = None,
                         navi_http_status: dict[str, Any] | None = None,
                         navi_tcp_status: dict[str, Any] | None = None,
                         carrot_man_peer_status: dict[str, Any] | None = None) -> dict[str, Any]:
  params, _error = _params_state()
  event_state = navigation_event_state()
  event = event_state.get("event", {}) if isinstance(event_state, dict) else {}
  nav_fields = _status_payload_navigation_fields(event if isinstance(event, dict) else {})
  nav_evidence = _status_payload_navigation_evidence(event if isinstance(event, dict) else {})
  runtime_status = {**default_messaging_status(), **(runtime_status or {})}
  navi_http_status = {**default_navi_http_state(), **(navi_http_status or {})}
  navi_tcp_status = {**default_navi_tcp_state(), **(navi_tcp_status or {})}
  carrot_man_peer_status = _carrot_man_peer_state(carrot_man_peer_status)
  navi_http_available = bool(navi_http_status.get("available", False))
  navi_tcp_available = bool(navi_tcp_status.get("available", False))

  is_onroad = bool(params.get_bool("IsOnroad")) if params is not None else bool(runtime_status.get("isOnroad", False))
  active = bool(runtime_status.get("active", False))
  speed_limit_state = phone_speed_state()
  speed_limit_evidence = speed_limit_evidence_state(runtime_status)

  return {
    "Carrot2": "GeniusPilot-alpha",
    "IsOnroad": is_onroad,
    "CarrotRouteActive": bool(is_onroad and nav_fields["route_active"]),
    "ip": DEFAULT_HOST,
    "port": NAVIGATION_UDP_PORT,
    "navi_debug": 0,
    "navi_http_port": NAVI_HTTP_PORT if navi_http_available else 0,
    "naviHttpAvailable": navi_http_available,
    "naviHttpLastError": str(navi_http_status.get("lastError", "")),
    "navi_tcp_port": NAVI_TCP_PORT if navi_tcp_available else 0,
    "naviTcpAvailable": navi_tcp_available,
    "naviTcpLastError": str(navi_tcp_status.get("lastError", "")),
    "carrotManCompatible": True,
    "carrotManControlStateAvailable": False,
    "carrotManPeer": carrot_man_peer_status,
    "carrotManPeerActive": bool(carrot_man_peer_status.get("active", False)),
    "carrotManPeerHost": str(carrot_man_peer_status.get("host", "")),
    "carrotManPeerAgeSec": carrot_man_peer_status.get("ageSec", 0.0),
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
    "sdi_type": nav_evidence["sdiType"],
    "sdi_plus_dist": nav_evidence["sdiPlusDistanceM"],
    "speedBumpDist": nav_evidence["speedBumpDistanceM"],
    "speedBumpAvailable": nav_evidence["speedBumpAvailable"],
    "modelSpeedKph": nav_evidence["modelSpeedKph"],
    "modelSpeedAvailable": nav_evidence["modelSpeedAvailable"],
    "trafficLight": nav_evidence["trafficLight"],
    "carrotControlPreview": nav_evidence["controlPreview"],
    "navigationHazards": nav_evidence["hazards"],
    "navigationModelSpeed": nav_evidence["modelSpeed"],
    "phoneSpeedLimitKph": speed_limit_state.get("speedLimitKph", 0.0),
    "phoneSpeedLimitSource": speed_limit_state.get("source", ""),
    "phoneSpeedLimitFresh": bool(speed_limit_state.get("fresh", False)),
    "phoneSpeedLimitEnabled": bool(speed_limit_state.get("enabled", False)),
    "phoneSpeedLimitAgeSec": speed_limit_state.get("ageSec", 0.0),
    "phoneSpeedLimitMaxAgeSec": speed_limit_state.get("maxAgeSec", PHONE_SPEED_LIMIT_MAX_AGE_S),
    "speedLimitKph": _as_float(runtime_status.get("speedLimitKph"), 0.0),
    "speedLimitSource": str(runtime_status.get("speedLimitSource", "")),
    "speedLimitPolicy": speed_limit_evidence["policy"],
    "speedLimitPolicyName": speed_limit_evidence["policyName"],
    "speedLimitMode": speed_limit_evidence["mode"],
    "speedLimitModeName": speed_limit_evidence["modeName"],
    "speedLimitOffsetType": speed_limit_evidence["offsetType"],
    "speedLimitOffsetTypeName": speed_limit_evidence["offsetTypeName"],
    "speedLimitOffsetValue": speed_limit_evidence["offsetValue"],
    "speedLimitOffsetUnit": speed_limit_evidence["offsetUnit"],
    "speedLimitEvidence": speed_limit_evidence,
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


def _normalize_recommendations(payload: dict[str, Any] | None, params: Any | None = None) -> list[dict[str, Any]]:
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
      captured_current = int(info.get("current", 0))
      recommended = _clamp_param(key, info.get("recommended", captured_current))
      current_value = params.get_int(key) if params is not None else captured_current
    except Exception:
      continue
    applied = current_value == recommended
    changed_since_recommendation = current_value != captured_current
    state = "applied" if applied else ("changed" if changed_since_recommendation else "pending")
    normalized.append({
      "key": key,
      "category": str(info.get("category", "long")),
      "current": captured_current,
      "capturedCurrentValue": captured_current,
      "currentValue": current_value,
      "recommended": recommended,
      "recommendedValue": recommended,
      "appliedValue": current_value,
      "delta": recommended - captured_current,
      "liveDelta": recommended - current_value,
      "applied": applied,
      "changedSinceRecommendation": changed_since_recommendation,
      "state": state,
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
      "recommendationSummary": {"total": 0, "pending": 0, "applied": 0, "changed": 0, "lat": 0, "long": 0},
      "recommendations": [],
      "error": error,
    }

  payload = _read_payload(params)
  recs = _normalize_recommendations(payload, params)
  recommendation_summary = {
    "total": len(recs),
    "pending": sum(1 for rec in recs if rec.get("state") == "pending"),
    "applied": sum(1 for rec in recs if rec.get("applied")),
    "changed": sum(1 for rec in recs if rec.get("state") == "changed"),
    "lat": sum(1 for rec in recs if rec.get("category") == "lat"),
    "long": sum(1 for rec in recs if rec.get("category") == "long"),
  }
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
    "recommendationSummary": recommendation_summary,
    "recommendations": recs,
  }


def apply_learning_recommendations() -> dict[str, Any]:
  params, error = _params_state()
  if params is None:
    raise RuntimeError(f"Params unavailable: {error}")
  if params.get_bool("IsOnroad"):
    raise RuntimeError("Cannot apply Auto-Tuner recommendations while onroad")

  payload = _read_payload(params)
  recs = _normalize_recommendations(payload, params)
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


def speed_limit_evidence_state(runtime_status: dict[str, Any] | None = None) -> dict[str, Any]:
  params, error = _params_state()
  runtime_status = runtime_status or {}
  phone_state = phone_speed_state()
  policy = _param_int(params, "SpeedLimitPolicy", 5)
  mode = _param_int(params, "SpeedLimitMode", 1)
  offset_type = _param_int(params, "SpeedLimitOffsetType", 0)
  offset_value = _param_int(params, "SpeedLimitValueOffset", 0)
  is_metric = bool(params.get_bool("IsMetric")) if params is not None else True
  offset_unit = ""
  if offset_type == 1:
    offset_unit = "kph" if is_metric else "mph"
  elif offset_type == 2:
    offset_unit = "percent"

  return {
    "hasParams": params is not None,
    "error": error if params is None else "",
    "policy": policy,
    "policyName": SPEED_LIMIT_POLICY_NAMES.get(policy, "unknown"),
    "mode": mode,
    "modeName": SPEED_LIMIT_MODE_NAMES.get(mode, "unknown"),
    "offsetType": offset_type,
    "offsetTypeName": SPEED_LIMIT_OFFSET_TYPE_NAMES.get(offset_type, "unknown"),
    "offsetValue": offset_value,
    "offsetUnit": offset_unit,
    "isMetric": is_metric,
    "resolvedSpeedLimitKph": round(_as_float(runtime_status.get("speedLimitKph"), 0.0), 3),
    "resolvedSource": str(runtime_status.get("speedLimitSource", "")),
    "phone": phone_state,
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


def default_navi_tcp_state() -> dict[str, Any]:
  return {
    "available": False,
    "port": NAVI_TCP_PORT,
    "lastError": "",
    "lastEvent": {},
    "lastReceivedAt": 0.0,
    "receivedTypes": {},
    "activeConnections": 0,
    "lastPeer": "",
  }


def default_carrot_man_peer_state() -> dict[str, Any]:
  return {
    "active": False,
    "host": "",
    "port": 0,
    "source": "",
    "lastSeenAt": 0.0,
    "ageSec": 0.0,
    "maxAgeSec": CARROT_MAN_PEER_MAX_AGE_S,
    "lastError": "",
  }


def _peer_host_allowed(host: str) -> bool:
  try:
    ip = ipaddress.ip_address(host)
  except ValueError:
    return False
  return not ip.is_multicast and not ip.is_unspecified and (
    ip.is_private or ip.is_loopback or ip.is_link_local
  )


def _record_carrot_man_peer(app: web.Application, peer: Any, source: str) -> None:
  if not isinstance(peer, tuple) or len(peer) < 2:
    return
  host = str(peer[0])
  if not _peer_host_allowed(host):
    return
  try:
    port = int(peer[1])
  except Exception:
    port = 0
  state = app.get("carrot_man_peer_state")
  if not isinstance(state, dict):
    return
  state.update({
    "active": True,
    "host": host,
    "port": port,
    "source": source[:48],
    "lastSeenAt": time.time(),
    "ageSec": 0.0,
    "maxAgeSec": CARROT_MAN_PEER_MAX_AGE_S,
    "lastError": "",
  })


def _carrot_man_peer_state(state: dict[str, Any] | None) -> dict[str, Any]:
  result = {**default_carrot_man_peer_state(), **(state or {})}
  last_seen_at = _as_float(result.get("lastSeenAt"), 0.0)
  age_sec = max(0.0, time.time() - last_seen_at) if last_seen_at > 0.0 else 0.0
  result["ageSec"] = round(age_sec, 3)
  result["active"] = bool(result.get("host")) and last_seen_at > 0.0 and age_sec <= CARROT_MAN_PEER_MAX_AGE_S
  if not result["active"] and result.get("host"):
    result["lastError"] = "peer expired"
  return result


def _status_broadcast_targets(peer_state: dict[str, Any] | None) -> list[tuple[str, int]]:
  targets: list[tuple[str, int]] = [(target, STATUS_BROADCAST_PORT) for target in STATUS_BROADCAST_TARGETS]
  peer = _carrot_man_peer_state(peer_state)
  if peer["active"]:
    target = (str(peer["host"]), STATUS_BROADCAST_PORT)
    if target not in targets:
      targets.append(target)
  return targets


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


def _record_navi_compat_event(app: web.Application, payload: dict[str, Any], *,
                              tmap_version: str = "", state_key: str = "navi_http_state",
                              source_prefix: str = "http-7713") -> dict[str, Any]:
  if not isinstance(payload, dict):
    raise ValueError("navigation compatibility payload must be a JSON object")
  event_type = _detect_navi_event_type(payload)
  received_at = time.time()
  summary = _navi_http_summary(payload, event_type)
  event = {
    "receivedAt": received_at,
    "eventTimeMs": _navi_event_timestamp_ms(payload),
    "type": event_type,
    "source": source_prefix,
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
    nav_result = record_navigation_event(nav_payload, f"{source_prefix}-{event_type}")
  except Exception as exc:
    nav_result = {"recorded": False, "error": str(exc)}

  state = app[state_key]
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


def record_navi_http_event(app: web.Application, payload: dict[str, Any], tmap_version: str = "") -> dict[str, Any]:
  return _record_navi_compat_event(app, payload, tmap_version=tmap_version, state_key="navi_http_state", source_prefix="http-7713")


def record_navi_tcp_event(app: web.Application, payload: dict[str, Any]) -> dict[str, Any]:
  return _record_navi_compat_event(app, payload, state_key="navi_tcp_state", source_prefix="tcp-7712")


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
  navi_tcp_state = _request.app["navi_tcp_state"]
  carrot_man_peer_state = _carrot_man_peer_state(_request.app.get("carrot_man_peer_state"))
  nav_state = navigation_event_state()
  nav_event = nav_state.get("event", {}) if isinstance(nav_state, dict) else {}
  feature_gates = carrot_feature_gate_state()
  return _json_response({
    "ok": True,
    "service": "carrot_server",
    "mode": "local",
    "port": LOCAL_WEB_PORT,
    "statusBroadcastPort": STATUS_BROADCAST_PORT,
    "statusBroadcastTargets": list(STATUS_BROADCAST_TARGETS),
    "statusBroadcastActiveTargets": [f"{host}:{port}" for host, port in _status_broadcast_targets(carrot_man_peer_state)],
    "statusBroadcastLastSentAt": status_last_sent_at,
    "statusBroadcastError": status_last_error,
    "carrotManPeer": carrot_man_peer_state,
    "messagingAvailable": bool(messaging_state.get("available", False)),
    "messagingLastUpdateAt": float(messaging_state.get("lastUpdateAt", 0.0)),
    "messagingLastError": str(messaging_state.get("lastError", "")),
    "speedLimitEvidence": speed_limit_evidence_state(messaging_state),
    "navigationEvidence": _status_payload_navigation_evidence(nav_event if isinstance(nav_event, dict) else {}),
    "carrotFeatureGates": feature_gates,
    "navigationUdpPort": NAVIGATION_UDP_PORT,
    "navigationUdpError": udp_error,
    "navigationUdpLastError": udp_last_error,
    "navigationUdpLastDatagramAt": udp_last_datagram_at,
    "navigationUdpLastRecordedAt": udp_last_recorded_at,
    "naviHttpPort": NAVI_HTTP_PORT,
    "naviHttpAvailable": bool(navi_http_state.get("available", False)),
    "naviHttpLastError": str(navi_http_state.get("lastError", "")),
    "naviHttpLastReceivedAt": float(navi_http_state.get("lastReceivedAt", 0.0)),
    "naviTcpPort": NAVI_TCP_PORT,
    "naviTcpAvailable": bool(navi_tcp_state.get("available", False)),
    "naviTcpLastError": str(navi_tcp_state.get("lastError", "")),
    "naviTcpLastReceivedAt": float(navi_tcp_state.get("lastReceivedAt", 0.0)),
    "naviTcpActiveConnections": int(navi_tcp_state.get("activeConnections", 0)),
    "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "cloudServices": False,
    "controlOutput": False,
    "endpoints": [
      "/api/health",
      "/api/params_bulk",
      "/api/param_set",
      "/api/status_broadcast",
      "/api/carrot_learning",
      "/api/carrot_feature_gates",
      "/api/fishop_hardware",
      "/api/navigation_event",
      "/api/navi",
      "/api/navi/tcp_health",
      "/api/phone_speed_limit",
    ],
  })


async def api_carrot_feature_gates(_request: web.Request) -> web.Response:
  return _json_response({"ok": True, **carrot_feature_gate_state()})


async def api_carrot_learning(_request: web.Request) -> web.Response:
  return _json_response({"ok": True, **get_learning_state()})


async def api_params_bulk(request: web.Request) -> web.Response:
  names = _requested_param_names(request.query.get("names", ""))
  if not names and request.method == "POST":
    try:
      body = await request.json()
    except Exception:
      body = {}
    names = _requested_param_names_from_body(body)
  if not names:
    return _json_response({"ok": False, "error": "missing names"}, status=400)
  state = params_bulk_state(names)
  return _json_response({"ok": state["hasParams"], **state}, status=200 if state["hasParams"] else 400)


async def api_param_set(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return _json_response({"ok": False, "error": "invalid json"}, status=400)

  name = str(body.get("name") or body.get("param") or body.get("key") or "").strip()
  try:
    result = set_param_from_api(name, body.get("value"))
    return _json_response({"ok": True, **result})
  except Exception as exc:
    params, error = _params_state()
    return _json_response({
      "ok": False,
      "name": name,
      "hasParams": params is not None,
      "has_params": params is not None,
      "error": str(exc) if params is not None else f"Params unavailable: {error}",
    }, status=400)


async def api_status_broadcast(_request: web.Request) -> web.Response:
  status_state = _request.app["status_broadcast_state"]
  messaging_state = _request.app["messaging_status_state"]
  navi_http_state = _request.app["navi_http_state"]
  navi_tcp_state = _request.app["navi_tcp_state"]
  carrot_man_peer_state = _carrot_man_peer_state(_request.app.get("carrot_man_peer_state"))
  return _json_response({
    "ok": True,
    "port": STATUS_BROADCAST_PORT,
    "targets": list(STATUS_BROADCAST_TARGETS),
    "activeTargets": [f"{host}:{port}" for host, port in _status_broadcast_targets(carrot_man_peer_state)],
    "lastTargets": status_state.get("lastTargets", []),
    "carrotManPeer": carrot_man_peer_state,
    "lastSentAt": float(status_state.get("lastSentAt", 0.0)),
    "lastError": str(status_state.get("lastError", "")),
    "messagingStatus": messaging_state,
    "naviHttpStatus": navi_http_state,
    "naviTcpStatus": navi_tcp_state,
    "payload": status_state.get("lastPayload") or build_status_payload(messaging_state, navi_http_state, navi_tcp_state, carrot_man_peer_state),
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


async def api_navi_tcp_health(request: web.Request) -> web.Response:
  state = request.app["navi_tcp_state"]
  return _json_response({
    "ok": True,
    "service": "carrot_navi_tcp",
    "port": NAVI_TCP_PORT,
    "available": bool(state.get("available", False)),
    "lastError": str(state.get("lastError", "")),
    "lastEvent": state.get("lastEvent", {}),
    "lastPeer": str(state.get("lastPeer", "")),
    "activeConnections": int(state.get("activeConnections", 0)),
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
    _record_carrot_man_peer(request.app, request.transport.get_extra_info("peername") if request.transport else None, "http-7713")
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
    h2 { font-size: 18px; margin: 0 0 12px; font-weight: 650; }
    h3 { font-size: 15px; margin: 0 0 8px; color: #d7e5eb; }
    p { color: #b8c5cc; line-height: 1.5; }
    section { border: 1px solid #2f3b43; border-radius: 8px; padding: 18px; margin-top: 16px; background: #151b20; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .panel { border: 1px solid #27343c; border-radius: 8px; padding: 12px; background: #10161b; }
    .metric { display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid #26323a; padding: 7px 0; font-size: 14px; }
    .metric:first-of-type { border-top: 0; }
    .label { color: #91a4ad; }
    .value { color: #eef4f8; text-align: right; overflow-wrap: anywhere; }
    .pill { display: inline-flex; align-items: center; min-height: 22px; padding: 0 8px; border-radius: 999px; background: #26323a; color: #cfe3eb; font-size: 13px; }
    .pill.ok { background: #12352c; color: #86efac; }
    .pill.warn { background: #3a2b12; color: #facc15; }
    .pill.off { background: #2a3035; color: #a8b4bb; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    button { min-height: 34px; border: 1px solid #33434d; border-radius: 7px; padding: 0 12px; background: #1c252b; color: #eef4f8; font: inherit; cursor: pointer; }
    button:hover:not(:disabled) { border-color: #4d6878; background: #23313a; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .list { display: grid; gap: 8px; margin-top: 12px; }
    .rec { border: 1px solid #27343c; border-radius: 8px; padding: 10px; background: #10161b; }
    .rec-head { display: flex; justify-content: space-between; gap: 10px; font-size: 14px; color: #eef4f8; }
    .rec-meta { color: #91a4ad; font-size: 13px; line-height: 1.45; margin-top: 6px; overflow-wrap: anywhere; }
    a { color: #7dd3fc; text-decoration: none; }
    code { background: #222b31; padding: 2px 6px; border-radius: 5px; }
    ul { padding-left: 20px; }
  </style>
</head>
<body>
  <main>
    <h1>CarrotPilot C3 Local Web</h1>
    <p>Local-only service for maintenance, Auto-Tuner recommendations, and fishop hardware snapshots.</p>
    <section id="safety-boundaries">
      <h2>Local Status</h2>
      <div class="metric"><span class="label">Cloud services</span><span class="value">disabled; no Sunnylink, connect, upload, pairing, or backup</span></div>
      <div class="metric"><span class="label">Speed limits</span><span class="value">phone first, then car, then map; stale phone data times out</span></div>
      <div class="metric"><span class="label">Speed offset</span><span class="value">default 0; fixed or percentage only when deliberately set</span></div>
      <div class="metric"><span class="label">Auto-Tuner</span><span class="value">learning off by default; apply only while parked</span></div>
      <div class="metric"><span class="label">fishop hardware</span><span class="value">lane, lidar, blindspot, and overtake settings are available in Super Advanced</span></div>
      <div class="metric"><span class="label">Carrot control</span><span class="value">traffic stop, auto turn, active speed, and overtake settings are available in Super Advanced</span></div>
    </section>
    <section id="control-gates-panel">
      <h2>Carrot Feature Status</h2>
      <div class="metric"><span class="label">State</span><span class="value"><span id="control-gates-state" class="pill off">loading</span></span></div>
      <div class="metric"><span class="label">Enabled params</span><span class="value" id="control-gates-enabled">-</span></div>
      <div class="metric"><span class="label">Candidate inputs</span><span class="value" id="control-gates-candidates">-</span></div>
      <div class="metric"><span class="label">Traffic stop</span><span class="value" id="control-gate-traffic-stop">-</span></div>
      <div class="metric"><span class="label">Auto turn</span><span class="value" id="control-gate-auto-turn">-</span></div>
      <div class="metric"><span class="label">Active speed</span><span class="value" id="control-gate-active-speed">-</span></div>
      <div class="metric"><span class="label">Auto-Tuner auto apply</span><span class="value" id="control-gate-auto-tuner">-</span></div>
      <div class="metric"><span class="label">fishop auto overtake</span><span class="value" id="control-gate-fishop-overtake">-</span></div>
      <div class="metric"><span class="label">Output</span><span class="value" id="control-gates-boundary">-</span></div>
      <p id="control-gates-error"></p>
    </section>
    <section id="navigation-panel">
      <h2>Navigation Evidence</h2>
      <div class="metric"><span class="label">State</span><span class="value"><span id="navigation-state" class="pill off">loading</span></span></div>
      <div class="metric"><span class="label">Source</span><span class="value" id="navigation-source">-</span></div>
      <div class="metric"><span class="label">SDI</span><span class="value" id="navigation-sdi">-</span></div>
      <div class="metric"><span class="label">Speed bump</span><span class="value" id="navigation-speed-bump">-</span></div>
      <div class="metric"><span class="label">Model speed</span><span class="value" id="navigation-model-speed">-</span></div>
      <div class="metric"><span class="label">Traffic stop</span><span class="value" id="navigation-traffic-stop">-</span></div>
      <div class="metric"><span class="label">Auto turn</span><span class="value" id="navigation-auto-turn">-</span></div>
      <div class="metric"><span class="label">Active speed</span><span class="value" id="navigation-active-speed">-</span></div>
      <div class="metric"><span class="label">Command status</span><span class="value" id="navigation-command-boundary">-</span></div>
      <p id="navigation-error"></p>
    </section>
    <section id="fishop-panel">
      <h2>fishop Hardware</h2>
      <div class="metric"><span class="label">State</span><span class="value"><span id="fishop-state" class="pill off">loading</span></span></div>
      <div class="metric"><span class="label">Input</span><span class="value" id="fishop-input">-</span></div>
      <div class="metric"><span class="label">Payloads</span><span class="value" id="fishop-payloads">-</span></div>
      <div class="metric"><span class="label">Last update</span><span class="value" id="fishop-last-update">-</span></div>
      <div class="grid">
        <div class="panel">
          <h3>Lane</h3>
          <div class="metric"><span class="label">Valid</span><span class="value" id="fishop-lane-valid">-</span></div>
          <div class="metric"><span class="label">Left / right</span><span class="value" id="fishop-lane-lines">-</span></div>
          <div class="metric"><span class="label">Curve</span><span class="value" id="fishop-lane-curve">-</span></div>
          <div class="metric"><span class="label">Quality</span><span class="value" id="fishop-lane-quality">-</span></div>
          <div class="metric"><span class="label">Age</span><span class="value" id="fishop-lane-age">-</span></div>
        </div>
        <div class="panel">
          <h3>Blindspot</h3>
          <div class="metric"><span class="label">Lidar</span><span class="value" id="fishop-lidar-blind">-</span></div>
          <div class="metric"><span class="label">Camera</span><span class="value" id="fishop-camera-blind">-</span></div>
          <div class="metric"><span class="label">Targets</span><span class="value" id="fishop-targets">-</span></div>
          <div class="metric"><span class="label">Dynamic risk</span><span class="value" id="fishop-dynamic-risk">-</span></div>
          <div class="metric"><span class="label">Age</span><span class="value" id="fishop-blind-age">-</span></div>
        </div>
        <div class="panel">
          <h3>Overtake Input</h3>
          <div class="metric"><span class="label">Command</span><span class="value" id="fishop-overtake-command">-</span></div>
          <div class="metric"><span class="label">Request</span><span class="value" id="fishop-overtake-request">-</span></div>
          <div class="metric"><span class="label">Direction</span><span class="value" id="fishop-overtake-direction">-</span></div>
          <div class="metric"><span class="label">Suggestion</span><span class="value" id="fishop-overtake-suggestion">-</span></div>
          <div class="metric"><span class="label">Navigation gate</span><span class="value" id="fishop-navigation-gate">-</span></div>
          <div class="metric"><span class="label">Hint</span><span class="value" id="fishop-overtake-hint">-</span></div>
          <div class="metric"><span class="label">Input path</span><span class="value" id="fishop-overtake-path">local</span></div>
          <div class="metric"><span class="label">Output</span><span class="value" id="fishop-overtake-boundary">-</span></div>
        </div>
      </div>
      <p id="fishop-error"></p>
    </section>
    <section id="auto-tuner-panel">
      <h2>Auto-Tuner</h2>
      <div class="metric"><span class="label">State</span><span class="value"><span id="auto-tuner-state" class="pill off">loading</span></span></div>
      <div class="metric"><span class="label">Mode</span><span class="value" id="auto-tuner-mode">-</span></div>
      <div class="metric"><span class="label">Apply scope</span><span class="value" id="auto-tuner-scope">-</span></div>
      <div class="metric"><span class="label">Recommendations</span><span class="value" id="auto-tuner-summary">-</span></div>
      <div class="metric"><span class="label">Source</span><span class="value" id="auto-tuner-source">-</span></div>
      <div class="actions">
        <button id="auto-tuner-apply" type="button">Apply</button>
        <button id="auto-tuner-ignore" type="button">Ignore</button>
        <button id="auto-tuner-clear" type="button">Clear</button>
      </div>
      <div id="auto-tuner-recommendations" class="list"></div>
      <p id="auto-tuner-error"></p>
    </section>
    <section>
      <h2>APIs</h2>
      <ul>
        <li><a href="/api/health"><code>/api/health</code></a></li>
        <li><a href="/api/params_bulk?names=ExperimentalMode"><code>/api/params_bulk</code></a></li>
        <li><a href="/api/status_broadcast"><code>/api/status_broadcast</code></a></li>
        <li><a href="/api/carrot_learning"><code>/api/carrot_learning</code></a></li>
        <li><a href="/api/carrot_feature_gates"><code>/api/carrot_feature_gates</code></a></li>
        <li><a href="/api/fishop_hardware"><code>/api/fishop_hardware</code></a></li>
        <li><a href="/api/navigation_event"><code>/api/navigation_event</code></a></li>
        <li><a href="/api/phone_speed_limit"><code>/api/phone_speed_limit</code></a></li>
      </ul>
    </section>
  </main>
  <script>
    const setText = (id, value) => {
      const node = document.getElementById(id);
      if (node) node.textContent = value;
    };
    const yesNo = (value) => value ? "yes" : "no";
    const age = (value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} s` : "-";
    const num = (value, digits = 3) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "-";
    const targetSummary = (targets = {}) => {
      const keys = ["lf_drel", "lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel", "lf_vrel", "lb_vrel", "rf_vrel", "rb_vrel"];
      const parts = keys.filter((key) => targets[key] !== null && targets[key] !== undefined)
        .map((key) => `${key}:${num(targets[key], 1)}`);
      return parts.length ? parts.join(" ") : "-";
    };
    const dynamicRiskSummary = (dynamicBlind = {}) => {
      const preview = dynamicBlind.riskPreview || {};
      const active = Array.isArray(dynamicBlind.activeRiskPreview) ? dynamicBlind.activeRiskPreview : [];
      if (!dynamicBlind.available) {
        return dynamicBlind.vEgoMps === null || dynamicBlind.vEgoMps === undefined ? "waiting vEgo" : "-";
      }
      if (active.length) {
        return `risk ${active.join(", ")} @ ${num(dynamicBlind.vEgoMps, 1)} m/s`;
      }
      return Object.keys(preview).length ? `clear @ ${num(dynamicBlind.vEgoMps, 1)} m/s` : "-";
    };
    const laneQualitySummary = (laneQuality = {}) => {
      const probs = laneQuality.laneProbabilities || {};
      const widths = laneQuality.laneWidthsM || {};
      const inner = [probs.leftInner, probs.rightInner].filter((value) => Number.isFinite(Number(value)));
      const width = Number.isFinite(Number(widths.center)) ? widths.center : (Number.isFinite(Number(widths.left)) ? widths.left : widths.right);
      const parts = [];
      if (inner.length) parts.push(`line ${inner.map((value) => num(value, 1)).join("/")}`);
      if (Number.isFinite(Number(width))) parts.push(`width ${num(width, 1)} m`);
      if (laneQuality.curveAvailable) parts.push("curve");
      return parts.length ? parts.join(" ") : "-";
    };
    const suggestionSummary = (preview = {}) => {
      if (!preview.readOnly) return "-";
      if (preview.readyForSuggestion) return `ready ${preview.direction || ""}`.trim();
      const reasons = Array.isArray(preview.reasons) ? preview.reasons.slice(0, 2) : [];
      return reasons.length ? `waiting: ${reasons.join("; ")}` : "waiting";
    };
    const navigationGateSummary = (gate = {}) => {
      if (!gate.readOnly) return "-";
      const state = gate.suggestionEligible ? "eligible" : "hint only";
      const provider = gate.providerTrustedForSuggestion ? "trusted map" : "map untrusted";
      const region = gate.regionSupportedForSuggestion ? "region ok" : "region waiting";
      const accuracy = gate.accuracyUsableForSuggestion ? `accuracy ${num(gate.accuracyM, 1)} m` : "accuracy waiting";
      return `${state} / ${provider} / ${region} / ${accuracy}`;
    };
    const overtakeHintSummary = (hint = {}) => {
      if (!hint.readOnly) return "-";
      const state = hint.available ? "hint ready" : "no hint";
      return `${state}: ${hint.message || "-"}`;
    };
    const controlStateSummary = (preview = {}) => {
      const state = preview.state || "display_only";
      const candidate = preview.candidate ? "candidate" : "idle";
      const enabled = preview.enabledParam ? "param on" : "default off";
      return `${state} / ${candidate} / ${enabled}`;
    };
    const gateSummary = (feature = {}) => {
      const state = feature.state || "waiting";
      const candidate = feature.candidate ? "candidate" : "idle";
      const enabled = feature.enabledParam ? "param on" : "default off";
      const reasons = Array.isArray(feature.blockingReasons) ? feature.blockingReasons.slice(0, 2) : [];
      const suffix = reasons.length ? ` / ${reasons.join(", ")}` : "";
      return `${state} / ${candidate} / ${enabled}${suffix}`;
    };
    const timeText = (value) => {
      const timestamp = Number(value);
      return Number.isFinite(timestamp) && timestamp > 0 ? new Date(timestamp * 1000).toLocaleString() : "-";
    };
    const valueText = (value) => {
      if (value === null || value === undefined || value === "") return "-";
      const parsed = Number(value);
      return Number.isFinite(parsed) ? String(parsed) : String(value);
    };
    const summaryText = (summary = {}) => {
      const total = Number(summary.total || 0);
      if (!total) return "none";
      return `${summary.pending || 0} pending / ${summary.applied || 0} applied / ${summary.changed || 0} changed`;
    };
    const setPill = (id, text, className) => {
      const node = document.getElementById(id);
      if (!node) return;
      node.textContent = text;
      node.className = `pill ${className}`;
    };
    const renderRecommendations = (recommendations = []) => {
      const list = document.getElementById("auto-tuner-recommendations");
      if (!list) return;
      list.textContent = "";
      if (!recommendations.length) {
        const empty = document.createElement("div");
        empty.className = "rec-meta";
        empty.textContent = "No pending recommendations";
        list.appendChild(empty);
        return;
      }
      for (const rec of recommendations.slice(0, 24)) {
        const row = document.createElement("div");
        row.className = "rec";

        const head = document.createElement("div");
        head.className = "rec-head";
        const name = document.createElement("span");
        name.textContent = `${rec.key || "-"} (${rec.category || "-"})`;
        const state = document.createElement("span");
        state.className = `pill ${rec.applied ? "ok" : rec.changedSinceRecommendation ? "warn" : "off"}`;
        state.textContent = rec.state || (rec.applied ? "applied" : "pending");
        head.appendChild(name);
        head.appendChild(state);
        row.appendChild(head);

        const values = document.createElement("div");
        values.className = "rec-meta";
        values.textContent = `captured/current/recommended: ${valueText(rec.capturedCurrentValue)} / ${valueText(rec.currentValue)} / ${valueText(rec.recommendedValue)}; applied ${valueText(rec.appliedValue)}; live delta ${valueText(rec.liveDelta)}`;
        row.appendChild(values);

        if (rec.reason) {
          const reason = document.createElement("div");
          reason.className = "rec-meta";
          reason.textContent = String(rec.reason);
          row.appendChild(reason);
        }
        list.appendChild(row);
      }
    };
    const renderNavigationEvidence = (data = {}) => {
      const event = data.event || {};
      const hazards = event.hazards || {};
      const sdi = hazards.sdi || {};
      const speedBump = hazards.speedBump || {};
      const modelSpeed = event.modelSpeed || {};
      const preview = event.controlPreview || {};
      const command = preview.overtake || {};
      if (!data.hasParams) {
        setPill("navigation-state", "unavailable", "warn");
      } else if (event.updatedAt) {
        setPill("navigation-state", "recorded", "ok");
      } else {
        setPill("navigation-state", "empty", "off");
      }
      setText("navigation-source", `${event.source || "-"} @ ${timeText(event.updatedAt)}`);
      setText("navigation-sdi", sdi.available ? `type ${sdi.type || 0}, ${num(sdi.speedLimitKph, 0)} kph, ${num(sdi.distanceM, 0)} m` : "-");
      setText("navigation-speed-bump", speedBump.available ? `${num(speedBump.distanceM, 0)} m via ${speedBump.sourceField || "flag"}` : "-");
      setText("navigation-model-speed", modelSpeed.available ? `${num(modelSpeed.speedKph, 0)} kph via ${modelSpeed.sourceField || "-"}` : "-");
      setText("navigation-traffic-stop", controlStateSummary(preview.trafficStop || {}));
      setText("navigation-auto-turn", controlStateSummary(preview.autoTurn || {}));
      setText("navigation-active-speed", controlStateSummary(preview.activeSpeed || {}));
      setText("navigation-command-boundary", command.highRiskCommandSeen ? `local input ${event.ignoredCommand || "command"}` : "local input");
      setText("navigation-error", data.error || "");
    };
    const renderFeatureGates = (data = {}) => {
      const features = data.features || {};
      if (!data.hasParams) {
        setPill("control-gates-state", "unavailable", "warn");
      } else if (data.controlOutputAllowed) {
        setPill("control-gates-state", "output available", "warn");
      } else {
        setPill("control-gates-state", "diagnostics", "ok");
      }
      const enabled = Array.isArray(data.enabledFeatures) ? data.enabledFeatures : [];
      const candidates = Array.isArray(data.candidateFeatures) ? data.candidateFeatures : [];
      setText("control-gates-enabled", enabled.length ? enabled.join(", ") : "none");
      setText("control-gates-candidates", candidates.length ? candidates.join(", ") : "none");
      setText("control-gate-traffic-stop", gateSummary(features.trafficStop || {}));
      setText("control-gate-auto-turn", gateSummary(features.autoTurn || {}));
      setText("control-gate-active-speed", gateSummary(features.activeSpeed || {}));
      setText("control-gate-auto-tuner", gateSummary(features.autoTunerAutoApply || {}));
      setText("control-gate-fishop-overtake", gateSummary(features.fishopAutoOvertake || {}));
      setText("control-gates-boundary", data.controlOutput ? "control output present" : "diagnostic status only");
      setText("control-gates-error", data.error || "");
    };
    const renderAutoTuner = (data = {}) => {
      if (!data.hasParams) {
        setPill("auto-tuner-state", "unavailable", "warn");
      } else if (data.pending) {
        setPill("auto-tuner-state", "pending", "warn");
      } else if (data.active) {
        setPill("auto-tuner-state", "active", "ok");
      } else {
        setPill("auto-tuner-state", "off", "off");
      }
      setText("auto-tuner-mode", `${data.active ? "learning on" : "learning off"} / auto apply ${yesNo(data.autoApply)}`);
      setText("auto-tuner-scope", `lat ${yesNo(data.applyLat)} / long ${yesNo(data.applyLong)}`);
      setText("auto-tuner-summary", summaryText(data.recommendationSummary || {}));
      setText("auto-tuner-source", `${data.source || "-"} @ ${timeText(data.createdAt)}`);
      renderRecommendations(Array.isArray(data.recommendations) ? data.recommendations : []);
      setText("auto-tuner-error", data.error || "");
      const apply = document.getElementById("auto-tuner-apply");
      const ignore = document.getElementById("auto-tuner-ignore");
      const clear = document.getElementById("auto-tuner-clear");
      if (apply) apply.disabled = !data.hasParams || !data.pending;
      if (ignore) ignore.disabled = !data.hasParams || !data.pending;
      if (clear) clear.disabled = !data.hasParams;
    };
    async function refreshAutoTuner() {
      try {
        const response = await fetch("/api/carrot_learning", {cache: "no-store"});
        const data = await response.json();
        renderAutoTuner(data);
      } catch (err) {
        setPill("auto-tuner-state", "error", "warn");
        setText("auto-tuner-error", String(err).slice(0, 160));
      }
    }
    async function refreshNavigationEvidence() {
      try {
        const response = await fetch("/api/navigation_event", {cache: "no-store"});
        const data = await response.json();
        renderNavigationEvidence(data);
      } catch (err) {
        setPill("navigation-state", "error", "warn");
        setText("navigation-error", String(err).slice(0, 160));
      }
    }
    async function refreshFeatureGates() {
      try {
        const response = await fetch("/api/carrot_feature_gates", {cache: "no-store"});
        const data = await response.json();
        renderFeatureGates(data);
      } catch (err) {
        setPill("control-gates-state", "error", "warn");
        setText("control-gates-error", String(err).slice(0, 160));
      }
    }
    async function postAutoTunerAction(action) {
      try {
        const response = await fetch("/api/carrot_learning", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({action}),
        });
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || `Auto-Tuner ${action} failed`);
        renderAutoTuner(data.state || {});
      } catch (err) {
        setPill("auto-tuner-state", "error", "warn");
        setText("auto-tuner-error", String(err).slice(0, 160));
      }
    }
    async function refreshFishopHardware() {
      try {
        const response = await fetch("/api/fishop_hardware", {cache: "no-store"});
        const data = await response.json();
        const snapshot = data.snapshot || {};
        const lane = snapshot.lane || {};
        const blindspot = snapshot.blindspot || {};
        const overtake = snapshot.overtake || {};
        const state = document.getElementById("fishop-state");
        if (state) {
          state.textContent = snapshot.sensorOnline ? "online" : "offline";
          state.className = `pill ${snapshot.sensorOnline ? "ok" : "off"}`;
        }
        setText("fishop-input", data.inputAvailable ? data.inputPath : "no input file");
        setText("fishop-payloads", String(data.payloadCount || 0));
        setText("fishop-last-update", age(snapshot.lastUpdateMonotonicSec));
        setText("fishop-lane-valid", yesNo(lane.lineValid));
        setText("fishop-lane-lines", `${lane.leftLine || 0} / ${lane.rightLine || 0}`);
        setText("fishop-lane-curve", `curve ${num(lane.maxCurve)} / latA ${num(lane.latA)}`);
        setText("fishop-lane-quality", laneQualitySummary(lane.laneQuality || {}));
        setText("fishop-lane-age", age(lane.ageSec));
        setText("fishop-lidar-blind", `L ${yesNo(blindspot.leftLidarBlind)} / R ${yesNo(blindspot.rightLidarBlind)}`);
        setText("fishop-camera-blind", `L ${yesNo(blindspot.leftCameraBlind)} / R ${yesNo(blindspot.rightCameraBlind)}`);
        setText("fishop-targets", targetSummary(blindspot.targets || {}));
        setText("fishop-dynamic-risk", dynamicRiskSummary(blindspot.dynamicBlind || {}));
        setText("fishop-blind-age", age(blindspot.ageSec));
        setText("fishop-overtake-command", yesNo(overtake.commandSeen));
        setText("fishop-overtake-request", yesNo(overtake.requested));
        setText("fishop-overtake-direction", overtake.direction || "-");
        setText("fishop-overtake-suggestion", suggestionSummary(overtake.suggestionPreview || {}));
        setText("fishop-navigation-gate", navigationGateSummary((overtake.suggestionPreview || {}).navigationGate || {}));
        setText("fishop-overtake-hint", overtakeHintSummary((overtake.suggestionPreview || {}).overtakeHint || {}));
        setText("fishop-overtake-path", (overtake.directionality || {}).alphaAction || "local");
        setText("fishop-overtake-boundary", snapshot.controlOutputEnabled ? "control output present" : "diagnostic status only");
        setText("fishop-error", data.parseError || "");
      } catch (err) {
        const state = document.getElementById("fishop-state");
        if (state) {
          state.textContent = "error";
          state.className = "pill warn";
        }
        setText("fishop-error", String(err).slice(0, 160));
      }
    }
    for (const [id, action] of [["auto-tuner-apply", "apply"], ["auto-tuner-ignore", "ignore"], ["auto-tuner-clear", "clear"]]) {
      const node = document.getElementById(id);
      if (node) node.addEventListener("click", () => postAutoTunerAction(action));
    }
    refreshAutoTuner();
    setInterval(refreshAutoTuner, 5000);
    refreshNavigationEvidence();
    setInterval(refreshNavigationEvidence, 1000);
    refreshFeatureGates();
    setInterval(refreshFeatureGates, 2000);
    refreshFishopHardware();
    setInterval(refreshFishopHardware, 1000);
  </script>
</body>
</html>
"""
  return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})


class NavigationUdpProtocol(asyncio.DatagramProtocol):
  def __init__(self, app: web.Application) -> None:
    self.app = app
    self.last_error = ""
    self.last_datagram_at = 0.0
    self.last_recorded_at = 0.0

  def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
    self.last_datagram_at = time.time()
    try:
      payload = json.loads(data.decode("utf-8", errors="replace"))
      if not isinstance(payload, dict):
        raise ValueError("navigation UDP payload must be a JSON object")
      _record_carrot_man_peer(self.app, addr, "udp-7706")
      record_navigation_event(payload, "udp-7706")
      self.last_recorded_at = time.time()
      self.last_error = ""
    except Exception as exc:
      self.last_error = str(exc)[:200]


async def start_navigation_udp(app: web.Application) -> None:
  loop = asyncio.get_running_loop()
  protocol = NavigationUdpProtocol(app)
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
  navi_tcp_state = app["navi_tcp_state"]
  carrot_man_peer_state = app["carrot_man_peer_state"]

  while True:
    try:
      peer_state = _carrot_man_peer_state(carrot_man_peer_state)
      payload = build_status_payload(dict(messaging_state), dict(navi_http_state), dict(navi_tcp_state), peer_state)
      data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
      targets = _status_broadcast_targets(peer_state)
      for target in targets:
        transport.sendto(data, target)
      status_state["lastPayload"] = payload
      status_state["lastSentAt"] = time.time()
      status_state["lastTargets"] = [f"{host}:{port}" for host, port in targets]
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


async def handle_navi_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, app: web.Application) -> None:
  state = app["navi_tcp_state"]
  peer = writer.get_extra_info("peername")
  peer_text = f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) and len(peer) >= 2 else str(peer or "")
  state["activeConnections"] = int(state.get("activeConnections", 0)) + 1
  state["lastPeer"] = peer_text
  _record_carrot_man_peer(app, peer, "tcp-7712")
  try:
    while True:
      line = await reader.readline()
      if not line:
        break
      if len(line) > NAVI_TCP_MAX_LINE_BYTES:
        state["lastError"] = "navigation TCP line too large"
        continue
      text = line.decode("utf-8", errors="replace").strip()
      if not text:
        continue
      try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
          raise ValueError("navigation TCP payload must be a JSON object")
        record_navi_tcp_event(app, payload)
        state["lastError"] = ""
      except Exception as exc:
        state["lastError"] = str(exc)[:200]
  finally:
    state["activeConnections"] = max(0, int(state.get("activeConnections", 0)) - 1)
    try:
      writer.close()
      await writer.wait_closed()
    except Exception:
      pass


async def start_navi_tcp(app: web.Application) -> None:
  try:
    server = await asyncio.start_server(
      lambda reader, writer: handle_navi_tcp_client(reader, writer, app),
      DEFAULT_HOST,
      NAVI_TCP_PORT,
    )
    app["background_tasks"]["navi_tcp_server"] = server
    app["navi_tcp_state"]["available"] = True
    app["navi_tcp_state"]["lastError"] = ""
  except Exception as exc:
    app["navi_tcp_state"]["available"] = False
    app["navi_tcp_state"]["lastError"] = str(exc)[:200]


async def stop_navi_tcp(app: web.Application) -> None:
  server = app["background_tasks"].get("navi_tcp_server")
  if server is not None:
    server.close()
    await server.wait_closed()
    app["background_tasks"]["navi_tcp_server"] = None
  app["navi_tcp_state"]["available"] = False


def add_navi_http_routes(app: web.Application) -> None:
  app.router.add_get("/health", api_navi_http_health)
  app.router.add_get("/api/navi/health", api_navi_http_health)
  app.router.add_get("/api/navi/tcp_health", api_navi_tcp_health)
  app.router.add_post("/api/navi", api_navi_http_post)
  app.router.add_post("/api/navi/{tmap_version}", api_navi_http_post)


async def start_navi_http(app: web.Application) -> None:
  navi_app = web.Application(client_max_size=NAVI_HTTP_MAX_BODY_SIZE)
  navi_app["navi_http_state"] = app["navi_http_state"]
  navi_app["navi_tcp_state"] = app["navi_tcp_state"]
  navi_app["carrot_man_peer_state"] = app["carrot_man_peer_state"]
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
  app["status_broadcast_state"] = {"lastPayload": {}, "lastSentAt": 0.0, "lastTargets": [], "lastError": ""}
  app["messaging_status_state"] = default_messaging_status()
  app["navi_http_state"] = default_navi_http_state()
  app["navi_tcp_state"] = default_navi_tcp_state()
  app["carrot_man_peer_state"] = default_carrot_man_peer_state()
  app["background_tasks"] = {"messaging_status": None, "navi_http_runner": None, "navi_tcp_server": None}
  app.on_startup.append(start_messaging_status)
  app.on_startup.append(start_navi_tcp)
  app.on_startup.append(start_navi_http)
  app.on_startup.append(start_status_broadcast)
  app.on_startup.append(start_navigation_udp)
  app.on_cleanup.append(stop_status_broadcast)
  app.on_cleanup.append(stop_navi_http)
  app.on_cleanup.append(stop_navi_tcp)
  app.on_cleanup.append(stop_messaging_status)
  app.on_cleanup.append(stop_navigation_udp)
  app.router.add_get("/", index)
  app.router.add_get("/api/health", api_health)
  app.router.add_get("/api/params_bulk", api_params_bulk)
  app.router.add_post("/api/params_bulk", api_params_bulk)
  app.router.add_post("/api/param_set", api_param_set)
  app.router.add_get("/api/status_broadcast", api_status_broadcast)
  app.router.add_get("/api/carrot_learning", api_carrot_learning)
  app.router.add_post("/api/carrot_learning", api_carrot_learning_action)
  app.router.add_get("/api/carrot_feature_gates", api_carrot_feature_gates)
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
