import json
import time
from typing import Any, List, Optional

from .params import HAS_PARAMS, Params


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


def _get_params():
  if not HAS_PARAMS or Params is None:
    raise RuntimeError("Params unavailable")
  return Params()


def _read_payload(params) -> Optional[dict[str, Any]]:
  payload = _decode_json(params.get("CarrotLearningRecommend"))
  return payload if isinstance(payload, dict) else None


def _normalize_recommendations(payload: Optional[dict[str, Any]]) -> List[dict[str, Any]]:
  if not payload:
    return []

  raw_recs = payload.get("recommendations")
  if isinstance(raw_recs, dict):
    source_items = raw_recs.items()
  else:
    source_items = []

  normalized: list[dict[str, Any]] = []
  for key, info in source_items:
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


def _clear_pending(params) -> None:
  params.remove("CarrotLearningRecommend")
  params.remove("CarrotLearningPopupSource")
  params.put_bool("CarrotLearningPopupReady", False)
  params.put_bool("CarrotLearningApply", False)
  params.put_bool("CarrotLearningIgnore", False)


def _append_history(params, payload: dict[str, Any], applied: dict[str, int], mode: str) -> None:
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
  if not HAS_PARAMS:
    return {
      "has_params": False,
      "active": False,
      "pending": False,
      "recommendations": [],
      "source": "",
      "created_at": 0,
      "message": "Params unavailable",
    }

  params = _get_params()
  payload = _read_payload(params)
  recs = _normalize_recommendations(payload)
  return {
    "has_params": True,
    "active": params.get_int("CarrotLearningActive") == 1,
    "pending": bool(recs),
    "popup_ready": params.get_bool("CarrotLearningPopupReady"),
    "auto_apply": params.get_bool("CarrotLearningAutoApply"),
    "apply_lat": params.get_int("CarrotTunerApplyLat") != 0,
    "apply_long": params.get_int("CarrotTunerApplyLong") != 0,
    "source": str(payload.get("source", "")) if isinstance(payload, dict) else "",
    "created_at": payload.get("created_at", 0) if isinstance(payload, dict) else 0,
    "recommendations": recs,
  }


def apply_learning_recommendations() -> dict[str, Any]:
  params = _get_params()
  if params.get_bool("IsOnroad"):
    raise RuntimeError("Cannot apply Auto-Tuner recommendations while onroad")

  payload = _read_payload(params)
  recs = _normalize_recommendations(payload)
  if not payload or not recs:
    _clear_pending(params)
    return {"applied": {}, "applied_count": 0}

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
  return {"applied": applied, "applied_count": len(applied)}


def ignore_learning_recommendations() -> dict[str, Any]:
  params = _get_params()
  _clear_pending(params)
  return {"ignored": True}


def clear_learning_data() -> dict[str, Any]:
  params = _get_params()
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
