#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
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
  return _json_response({
    "ok": True,
    "service": "carrot_server",
    "mode": "local",
    "port": LOCAL_WEB_PORT,
    "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "cloudServices": False,
    "controlOutput": False,
    "endpoints": [
      "/api/health",
      "/api/params_bulk",
      "/api/param_set",
      "/api/carrot_learning",
      "/api/fishop_hardware",
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
        <li><a href="/api/carrot_learning"><code>/api/carrot_learning</code></a></li>
        <li><a href="/api/fishop_hardware"><code>/api/fishop_hardware</code></a></li>
        <li><a href="/api/phone_speed_limit"><code>/api/phone_speed_limit</code></a></li>
      </ul>
    </section>
  </main>
</body>
</html>
"""
  return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})


def make_app() -> web.Application:
  app = web.Application()
  app.router.add_get("/", index)
  app.router.add_get("/api/health", api_health)
  app.router.add_get("/api/params_bulk", api_params_bulk)
  app.router.add_post("/api/param_set", api_param_set)
  app.router.add_get("/api/carrot_learning", api_carrot_learning)
  app.router.add_post("/api/carrot_learning", api_carrot_learning_action)
  app.router.add_get("/api/fishop_hardware", api_fishop_hardware)
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
