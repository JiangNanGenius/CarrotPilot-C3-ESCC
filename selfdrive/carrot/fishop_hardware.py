from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
import time
from typing import Any, Iterable


CONTROL_OUTPUT_ENABLED = False
LANE_MAX_AGE_S = 1.0
BLINDSPOT_MAX_AGE_S = 2.0
LIDAR_DISTANCE_MAX_AGE_S = 1.0
OVERTAKE_MAX_AGE_S = 1.0

LEFT_SIDE_BIT = 0x1
RIGHT_SIDE_BIT = 0x2

LANE_KEYS = ("left_lane", "right_lane", "lineValid", "max_curve", "lat_a")
BLINDSPOT_KEYS = (
  "lidar_lblind", "lidar_rblind", "left_blind", "right_blind",
  "l_blindspot", "r_blindspot", "detect_side", "lidar_id",
  "lf_drel", "lb_drel", "rf_drel", "rb_drel",
  "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel",
)
OVERTAKE_KEYS = ("overtake", "overtake_request", "request", "direction", "reason")


def _now() -> float:
  return time.monotonic()


def _age(last_update_s: float, now_s: float) -> float | None:
  if last_update_s <= 0.:
    return None
  return max(0., now_s - last_update_s)


def _fresh(last_update_s: float, now_s: float, max_age_s: float) -> bool:
  age = _age(last_update_s, now_s)
  return age is not None and age <= max_age_s


def _as_bool(value: Any, default: bool = False) -> bool:
  if value is None:
    return default
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return value != 0
  if isinstance(value, str):
    text = value.strip().lower()
    if text in ("1", "true", "yes", "on"):
      return True
    if text in ("0", "false", "no", "off", ""):
      return False
  return default


def _as_int(value: Any, default: int = 0) -> int:
  try:
    return int(value)
  except (TypeError, ValueError):
    return default


def _as_float(value: Any) -> float | None:
  try:
    val = float(value)
  except (TypeError, ValueError):
    return None
  return val if isfinite(val) else None


def _line_type(value: Any) -> int:
  # fishop treats values below 1 as no useful lane-line evidence.
  return max(0, _as_int(value, 0))


def _limited_text(value: Any, limit: int = 80) -> str:
  if value is None:
    return ""
  text = str(value).replace("\x00", "").strip()
  return text[:limit]


@dataclass
class LaneEvidence:
  last_update_s: float = 0.
  left_line: int = 0
  right_line: int = 0
  line_valid: bool = False
  max_curve: float | None = None
  lat_a: float | None = None

  def update(self, payload: dict[str, Any], now_s: float) -> None:
    if "left_lane" in payload:
      self.left_line = _line_type(payload.get("left_lane"))
    if "right_lane" in payload:
      self.right_line = _line_type(payload.get("right_lane"))
    if "lineValid" in payload:
      self.line_valid = _as_bool(payload.get("lineValid"))
    else:
      self.line_valid = self.left_line > 0 or self.right_line > 0
    if "max_curve" in payload:
      self.max_curve = _as_float(payload.get("max_curve"))
    if "lat_a" in payload:
      self.lat_a = _as_float(payload.get("lat_a"))
    self.last_update_s = now_s

  def to_dict(self, now_s: float) -> dict[str, Any]:
    fresh = _fresh(self.last_update_s, now_s, LANE_MAX_AGE_S)
    return {
      "fresh": fresh,
      "ageSec": _age(self.last_update_s, now_s),
      "lastUpdateMonotonicSec": self.last_update_s if self.last_update_s > 0. else None,
      "lineValid": self.line_valid and fresh,
      "leftLine": self.left_line,
      "rightLine": self.right_line,
      "maxCurve": self.max_curve,
      "latA": self.lat_a,
    }


@dataclass
class BlindspotEvidence:
  last_update_s: float = 0.
  left_lidar_blind: bool = False
  right_lidar_blind: bool = False
  left_camera_blind: bool = False
  right_camera_blind: bool = False
  detect_side: int = 0
  lidar_id: int | None = None
  targets: dict[str, float | None] = field(default_factory=dict)

  def update(self, payload: dict[str, Any], now_s: float) -> None:
    detect_side = _as_int(payload.get("detect_side"), self.detect_side)
    self.detect_side = detect_side
    if "lidar_id" in payload:
      self.lidar_id = _as_int(payload.get("lidar_id"), 0)

    if "lidar_lblind" in payload:
      self.left_lidar_blind = _as_bool(payload.get("lidar_lblind"))
    if "lidar_rblind" in payload:
      self.right_lidar_blind = _as_bool(payload.get("lidar_rblind"))

    if "left_blind" in payload or "l_blindspot" in payload:
      self.left_camera_blind = _as_bool(payload.get("left_blind", payload.get("l_blindspot")))
    if "right_blind" in payload or "r_blindspot" in payload:
      self.right_camera_blind = _as_bool(payload.get("right_blind", payload.get("r_blindspot")))

    for key in ("lf_drel", "lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel"):
      if key in payload:
        self.targets[key] = _as_float(payload.get(key))

    if payload:
      self.last_update_s = now_s

  def to_dict(self, now_s: float) -> dict[str, Any]:
    fresh = _fresh(self.last_update_s, now_s, BLINDSPOT_MAX_AGE_S)
    return {
      "fresh": fresh,
      "ageSec": _age(self.last_update_s, now_s),
      "lastUpdateMonotonicSec": self.last_update_s if self.last_update_s > 0. else None,
      "detectSide": self.detect_side,
      "lidarId": self.lidar_id,
      "leftLidarBlind": self.left_lidar_blind if fresh else False,
      "rightLidarBlind": self.right_lidar_blind if fresh else False,
      "leftCameraBlind": self.left_camera_blind if fresh else False,
      "rightCameraBlind": self.right_camera_blind if fresh else False,
      "targetsFresh": _fresh(self.last_update_s, now_s, LIDAR_DISTANCE_MAX_AGE_S),
      "targets": dict(sorted(self.targets.items())),
    }


@dataclass
class OvertakeEvidence:
  last_update_s: float = 0.
  command_seen: bool = False
  requested: bool = False
  direction: str = ""
  reason: str = ""

  def update(self, payload: dict[str, Any], now_s: float) -> None:
    self.command_seen = True
    self.requested = _as_bool(payload.get("overtake", payload.get("overtake_request", payload.get("request"))))
    self.direction = _limited_text(payload.get("direction"))
    self.reason = _limited_text(payload.get("reason"))
    self.last_update_s = now_s

  def to_dict(self, now_s: float) -> dict[str, Any]:
    fresh = _fresh(self.last_update_s, now_s, OVERTAKE_MAX_AGE_S)
    return {
      "fresh": fresh,
      "ageSec": _age(self.last_update_s, now_s),
      "lastUpdateMonotonicSec": self.last_update_s if self.last_update_s > 0. else None,
      "commandSeen": self.command_seen and fresh,
      "requested": self.requested and fresh,
      "direction": self.direction if fresh else "",
      "reason": self.reason if fresh else "",
      "readOnly": True,
    }


@dataclass
class FishopHardwareState:
  lane: LaneEvidence = field(default_factory=LaneEvidence)
  blindspot: BlindspotEvidence = field(default_factory=BlindspotEvidence)
  overtake: OvertakeEvidence = field(default_factory=OvertakeEvidence)

  def update_from_payload(self, payload: dict[str, Any], now_s: float | None = None) -> None:
    now_s = _now() if now_s is None else now_s
    source = _limited_text(payload.get("resp", payload.get("type", payload.get("device_type")))).lower()

    if source == "lane" or any(key in payload for key in LANE_KEYS):
      self.lane.update(payload, now_s)

    if source in ("blindspot", "cam_blind") or any(key in payload for key in BLINDSPOT_KEYS):
      self.blindspot.update(payload, now_s)

    if source == "overtake" or any(key in payload for key in OVERTAKE_KEYS):
      self.overtake.update(payload, now_s)

  def to_dict(self, now_s: float | None = None) -> dict[str, Any]:
    now_s = _now() if now_s is None else now_s
    lane = self.lane.to_dict(now_s)
    blindspot = self.blindspot.to_dict(now_s)
    overtake = self.overtake.to_dict(now_s)
    last_updates = [
      value for value in (
        self.lane.last_update_s,
        self.blindspot.last_update_s,
        self.overtake.last_update_s,
      ) if value > 0.
    ]
    return {
      "readOnly": True,
      "controlOutputEnabled": CONTROL_OUTPUT_ENABLED,
      "sensorOnline": bool(lane["fresh"] or blindspot["fresh"] or overtake["fresh"]),
      "lastUpdateMonotonicSec": max(last_updates) if last_updates else None,
      "lane": lane,
      "blindspot": blindspot,
      "overtake": overtake,
    }


def normalize_fishop_payloads(payloads: Iterable[dict[str, Any]], now_s: float | None = None) -> dict[str, Any]:
  state = FishopHardwareState()
  base_now = _now() if now_s is None else now_s
  for payload in payloads:
    state.update_from_payload(payload, base_now)
  return state.to_dict(base_now)
