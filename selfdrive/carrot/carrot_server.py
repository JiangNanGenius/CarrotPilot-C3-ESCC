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


def _clamp_param(key: str, value: Any) -> int:
  low, high = PARAM_LIMITS[key]
  return int(max(low, min(high, int(value))))


def _params_state() -> tuple[Any | None, str]:
  try:
    from openpilot.common.params import Params
    return Params(), ""
  except Exception as exc:
    return None, str(exc)[:240]


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
      "/api/carrot_learning",
      "/api/fishop_hardware",
    ],
  })


async def api_carrot_learning(_request: web.Request) -> web.Response:
  return _json_response({"ok": True, **get_learning_state()})


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
        <li><a href="/api/carrot_learning"><code>/api/carrot_learning</code></a></li>
        <li><a href="/api/fishop_hardware"><code>/api/fishop_hardware</code></a></li>
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
  app.router.add_get("/api/carrot_learning", api_carrot_learning)
  app.router.add_post("/api/carrot_learning", api_carrot_learning_action)
  app.router.add_get("/api/fishop_hardware", api_fishop_hardware)
  return app


def main() -> None:
  parser = argparse.ArgumentParser(description="CarrotPilot C3 local web service")
  parser.add_argument("--host", default=DEFAULT_HOST)
  parser.add_argument("--port", type=int, default=LOCAL_WEB_PORT)
  args = parser.parse_args()
  web.run_app(make_app(), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
  main()
