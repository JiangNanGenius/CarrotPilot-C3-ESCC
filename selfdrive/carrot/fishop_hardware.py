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
NAVIGATION_CONTEXT_MAX_AGE_S = 5.0
NAVIGATION_ACCURACY_THRESHOLD_M = 15.0
FISHOP_PROTOCOL = {
  "opListenPort": 4211,
  "laneRemotePort": 4212,
  "laneListenPort": 4213,
  "navigationListenPort": 7706,
  "navigationRemotePort": 7705,
}
DYNAMIC_BLIND_REFERENCE_DEFAULTS = {
  "DynamicBlindRange": 0,
  "DynamicBlindDistance": 0,
  "LidarBsdDelayTimeSec": 1.0,
  "LidarFrontVDistTimeSec": 1.0,
  "LidarFrontVRelDistTimeSec": 3.0,
  "LidarBehindVDistTimeSec": 1.0,
  "LidarBehindVRelDistTimeSec": 3.0,
  "LaneLineDelayTimeSec": 1.0,
}
DYNAMIC_BLIND_TARGETS = {
  "lf": ("left", "front", "LidarFrontVRelDistTimeSec", "LidarFrontVDistTimeSec"),
  "lb": ("left", "rear", "LidarBehindVRelDistTimeSec", "LidarBehindVDistTimeSec"),
  "rf": ("right", "front", "LidarFrontVRelDistTimeSec", "LidarFrontVDistTimeSec"),
  "rb": ("right", "rear", "LidarBehindVRelDistTimeSec", "LidarBehindVDistTimeSec"),
}

LEFT_SIDE_BIT = 0x1
RIGHT_SIDE_BIT = 0x2

LANE_QUALITY_KEYS = (
  "prob", "l_lane_prob", "l_line_prob", "r_line_prob", "r_lane_prob",
  "l_edge_prob", "r_edge_prob", "l_lane_width", "r_lane_width",
  "l_edge_dist", "r_edge_dist", "lane_width", "atc_state", "blinker",
)
LANE_KEYS = ("left_lane", "right_lane", "lineValid", "max_curve", "lat_a", *LANE_QUALITY_KEYS)
BLINDSPOT_KEYS = (
  "lidar_lblind", "lidar_rblind", "left_blind", "right_blind",
  "l_blindspot", "r_blindspot", "detect_side", "lidar_id",
  "lidar_car_lblind", "lidar_car_rblind", "lidar_l", "lidar_r", "camera_l", "camera_r",
  "lf_drel", "lb_drel", "rf_drel", "rb_drel",
  "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel",
  "lf_vrel", "lb_vrel", "rf_vrel", "rb_vrel", "dist_time", "device",
  "v_ego_mps", "vEgo", "v_ego", "vego",
)
TARGET_KEYS = (
  "lf_drel", "lb_drel", "rf_drel", "rb_drel",
  "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel",
  "lf_vrel", "lb_vrel", "rf_vrel", "rb_vrel",
)
OVERTAKE_KEYS = ("overtake", "overtake_request", "request", "direction", "reason", "index", "cmd", "arg")
OVERTAKE_TRIGGER_KEYS = ("overtake", "overtake_request", "request", "index", "cmd", "arg")
NAVIGATION_CONTEXT_KEYS = (
  "provider", "mapProvider", "navProvider", "navigationProvider", "map_provider",
  "country", "countryCode", "country_code", "region", "navRegion", "navigationRegion", "locale",
  "accuracyM", "gpsAccuracyM", "horizontalAccuracyM", "navAccuracyM", "precisionM", "locationAccuracyM",
  "lat", "latitude", "lon", "lng", "longitude",
)
OVERTAKE_DIRECTIONS = {
  "l": "left",
  "left": "left",
  "左": "left",
  "左侧": "left",
  "r": "right",
  "right": "right",
  "右": "right",
  "右侧": "right",
}


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


def _round_float(value: float | None, digits: int = 3) -> float | None:
  return None if value is None else round(value, digits)


def _line_type(value: Any) -> int:
  # fishop treats values below 1 as no useful lane-line evidence.
  return max(0, _as_int(value, 0))


def _limited_text(value: Any, limit: int = 80) -> str:
  if value is None:
    return ""
  text = str(value).replace("\x00", "").strip()
  return text[:limit]


def _overtake_direction(*values: Any) -> str:
  for value in values:
    text = _limited_text(value).lower()
    if not text:
      continue
    if text in OVERTAKE_DIRECTIONS:
      return OVERTAKE_DIRECTIONS[text]
    for token, direction in OVERTAKE_DIRECTIONS.items():
      if token in text:
        return direction
  return ""


def _first_text(payload: dict[str, Any], *keys: str) -> str:
  for key in keys:
    text = _limited_text(payload.get(key))
    if text:
      return text
  return ""


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
  for key in keys:
    if key in payload:
      value = _as_float(payload.get(key))
      if value is not None:
        return value
  return None


def _text_has_any(text: str, needles: tuple[str, ...]) -> bool:
  lower = text.lower()
  return any(needle.lower() in lower for needle in needles)


def _side_object_risk(drel_mm: float | None, vrel_mps: float | None, v_ego_mps: float | None,
                      time_horizon_s: float, min_drel_scale: float) -> dict[str, Any] | None:
  if drel_mm is None or vrel_mps is None or v_ego_mps is None:
    return None

  drel_m = abs(drel_mm) / 1000.0
  v_other_mps = v_ego_mps + vrel_mps
  if drel_mm > 0:
    closing_speed_mps = max(v_ego_mps - v_other_mps, 0.0)
  else:
    closing_speed_mps = max(v_other_mps - v_ego_mps, 0.0)

  if min_drel_scale >= 0:
    danger_distance_m = max(v_ego_mps * min_drel_scale, 0.0)
  else:
    danger_distance_m = abs(min_drel_scale)
  future_distance_m = drel_m - closing_speed_mps * time_horizon_s
  return {
    "risk": future_distance_m < danger_distance_m or drel_m < danger_distance_m,
    "drelM": _round_float(drel_m),
    "vrelMps": _round_float(vrel_mps),
    "vEgoMps": _round_float(v_ego_mps),
    "closingSpeedMps": _round_float(closing_speed_mps),
    "dangerDistanceM": _round_float(danger_distance_m),
    "futureDistanceM": _round_float(future_distance_m),
    "timeHorizonSec": _round_float(time_horizon_s),
    "minDistanceScale": _round_float(min_drel_scale),
  }


@dataclass
class LaneEvidence:
  last_update_s: float = 0.
  left_line: int = 0
  right_line: int = 0
  line_valid: bool = False
  max_curve: float | None = None
  lat_a: float | None = None
  model_prob_available: bool = False
  lane_probs: dict[str, float | None] = field(default_factory=dict)
  edge_probs: dict[str, float | None] = field(default_factory=dict)
  lane_widths_m: dict[str, float | None] = field(default_factory=dict)
  road_edge_distances_m: dict[str, float | None] = field(default_factory=dict)
  atc_state: int | None = None
  blinker: int | None = None

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
    if "prob" in payload:
      self.model_prob_available = _as_bool(payload.get("prob"))
    for payload_key, output_key in (
      ("l_lane_prob", "leftOuter"),
      ("l_line_prob", "leftInner"),
      ("r_line_prob", "rightInner"),
      ("r_lane_prob", "rightOuter"),
    ):
      if payload_key in payload:
        self.lane_probs[output_key] = _as_float(payload.get(payload_key))
    for payload_key, output_key in (("l_edge_prob", "left"), ("r_edge_prob", "right")):
      if payload_key in payload:
        self.edge_probs[output_key] = _as_float(payload.get(payload_key))
    for payload_key, output_key in (
      ("l_lane_width", "left"),
      ("r_lane_width", "right"),
      ("lane_width", "center"),
    ):
      if payload_key in payload:
        self.lane_widths_m[output_key] = _as_float(payload.get(payload_key))
    for payload_key, output_key in (("l_edge_dist", "left"), ("r_edge_dist", "right")):
      if payload_key in payload:
        self.road_edge_distances_m[output_key] = _as_float(payload.get(payload_key))
    if "atc_state" in payload:
      self.atc_state = _as_int(payload.get("atc_state"), 0)
    if "blinker" in payload:
      self.blinker = _as_int(payload.get("blinker"), 0)
    self.last_update_s = now_s

  def quality(self, fresh: bool) -> dict[str, Any]:
    curve_available = fresh and (self.max_curve is not None or self.lat_a is not None)
    model_available = fresh and (
      self.model_prob_available
      or bool(self.lane_probs)
      or bool(self.edge_probs)
      or bool(self.lane_widths_m)
      or bool(self.road_edge_distances_m)
    )
    return {
      "readOnly": True,
      "controlOutput": False,
      "lineSource": "fishop UDP 4213 lane payload",
      "lineEvidenceAvailable": fresh and self.line_valid,
      "curveAvailable": curve_available,
      "curveSource": "fishop status JSON; reference uses shared lat_a/max_curve or modelV2.orientationRate.z fallback",
      "maxCurve": _round_float(self.max_curve),
      "latA": _round_float(self.lat_a),
      "modelEvidenceAvailable": model_available,
      "modelSource": "fishop status JSON from modelV2 laneLineProbs, roadEdgeStds, and LaneLineMeta widths/distances",
      "laneProbabilities": dict(sorted(self.lane_probs.items())),
      "roadEdgeProbabilities": dict(sorted(self.edge_probs.items())),
      "laneWidthsM": dict(sorted(self.lane_widths_m.items())),
      "roadEdgeDistancesM": dict(sorted(self.road_edge_distances_m.items())),
      "atcState": self.atc_state if fresh else None,
      "blinker": self.blinker if fresh else None,
      "notUsedFor": ("steering target", "path output", "automatic lane-change"),
    }

  def to_dict(self, now_s: float) -> dict[str, Any]:
    fresh = _fresh(self.last_update_s, now_s, LANE_MAX_AGE_S)
    return {
      "fresh": fresh,
      "ageSec": _age(self.last_update_s, now_s),
      "lastUpdateMonotonicSec": self.last_update_s if self.last_update_s > 0. else None,
      "lineValid": self.line_valid and fresh,
      "leftLine": self.left_line,
      "rightLine": self.right_line,
      "leftLaneBlind": self.left_line >= 1 and fresh,
      "rightLaneBlind": self.right_line >= 1 and fresh,
      "lineTypeRule": "fishop reference treats lane line values >= 1 as solid-line lane-change blockers",
      "maxCurve": self.max_curve,
      "latA": self.lat_a,
      "laneQuality": self.quality(fresh),
    }


@dataclass
class BlindspotEvidence:
  last_update_s: float = 0.
  left_lidar_blind: bool = False
  right_lidar_blind: bool = False
  left_lidar_car_blind: bool = False
  right_lidar_car_blind: bool = False
  left_camera_blind: bool = False
  right_camera_blind: bool = False
  lidar_detect_side: int = 0
  camera_detect_side: int = 0
  lidar_id: int | None = None
  dist_time_ms: int | None = None
  v_ego_mps: float | None = None
  targets: dict[str, float | None] = field(default_factory=dict)

  def update(self, payload: dict[str, Any], now_s: float) -> None:
    source = _limited_text(payload.get("resp", payload.get("type", payload.get("device")))).lower()
    device = _limited_text(payload.get("device")).lower()
    detect_side = _as_int(payload.get("detect_side"), 0)
    lidar_payload = source == "blindspot" or device == "lidar" or any(key in payload for key in ("lidar_lblind", "lidar_rblind", "lidar_id", "dist_time"))
    camera_payload = source == "cam_blind" or device == "camera" or any(key in payload for key in ("left_blind", "right_blind", "l_blindspot", "r_blindspot"))
    if detect_side:
      if lidar_payload:
        self.lidar_detect_side = detect_side
      if camera_payload:
        self.camera_detect_side = detect_side
    if "lidar_id" in payload:
      self.lidar_id = _as_int(payload.get("lidar_id"), 0)
    if "dist_time" in payload:
      self.dist_time_ms = _as_int(payload.get("dist_time"), 0)
    for speed_key in ("v_ego_mps", "vEgo", "v_ego", "vego"):
      if speed_key in payload:
        self.v_ego_mps = _as_float(payload.get(speed_key))
        break

    if "lidar_lblind" in payload:
      self.left_lidar_blind = _as_bool(payload.get("lidar_lblind"))
    if "lidar_rblind" in payload:
      self.right_lidar_blind = _as_bool(payload.get("lidar_rblind"))
    if "lidar_car_lblind" in payload:
      self.left_lidar_car_blind = _as_bool(payload.get("lidar_car_lblind"))
    if "lidar_car_rblind" in payload:
      self.right_lidar_car_blind = _as_bool(payload.get("lidar_car_rblind"))

    if "left_blind" in payload or "l_blindspot" in payload:
      self.left_camera_blind = _as_bool(payload.get("left_blind", payload.get("l_blindspot")))
    if "right_blind" in payload or "r_blindspot" in payload:
      self.right_camera_blind = _as_bool(payload.get("right_blind", payload.get("r_blindspot")))

    for key in TARGET_KEYS:
      if key in payload:
        self.targets[key] = _as_float(payload.get(key))

    if payload:
      self.last_update_s = now_s

  def dynamic_blind(self, targets_fresh: bool) -> dict[str, Any]:
    preview: dict[str, dict[str, Any]] = {}
    if targets_fresh:
      for prefix, (side, position, horizon_key, distance_key) in DYNAMIC_BLIND_TARGETS.items():
        risk = _side_object_risk(
          self.targets.get(f"{prefix}_drel"),
          self.targets.get(f"{prefix}_vrel"),
          self.v_ego_mps,
          DYNAMIC_BLIND_REFERENCE_DEFAULTS[horizon_key],
          DYNAMIC_BLIND_REFERENCE_DEFAULTS[distance_key],
        )
        if risk is not None:
          risk["side"] = side
          risk["position"] = position
          preview[prefix] = risk

    active = sorted(key for key, value in preview.items() if value.get("risk"))
    return {
      "readOnly": True,
      "controlOutput": False,
      "available": bool(preview),
      "targetsFresh": targets_fresh,
      "vEgoMps": _round_float(self.v_ego_mps),
      "activeRiskPreview": active,
      "riskPreview": preview,
      "reference": "fishop is_side_object_risky preview from amap_navi.py; alpha records evidence only",
      "referenceDefaults": dict(DYNAMIC_BLIND_REFERENCE_DEFAULTS),
      "notUsedFor": ("lane-change decision", "steering target", "path output"),
    }

  def to_dict(self, now_s: float) -> dict[str, Any]:
    fresh = _fresh(self.last_update_s, now_s, BLINDSPOT_MAX_AGE_S)
    targets_fresh = _fresh(self.last_update_s, now_s, LIDAR_DISTANCE_MAX_AGE_S)
    return {
      "fresh": fresh,
      "ageSec": _age(self.last_update_s, now_s),
      "lastUpdateMonotonicSec": self.last_update_s if self.last_update_s > 0. else None,
      "detectSide": self.lidar_detect_side | self.camera_detect_side,
      "lidarDetectSide": self.lidar_detect_side,
      "cameraDetectSide": self.camera_detect_side,
      "lidarId": self.lidar_id,
      "distTimeMs": self.dist_time_ms,
      "leftLidarOnline": bool((self.lidar_detect_side & LEFT_SIDE_BIT) and fresh),
      "rightLidarOnline": bool((self.lidar_detect_side & RIGHT_SIDE_BIT) and fresh),
      "leftCameraOnline": bool((self.camera_detect_side & LEFT_SIDE_BIT) and fresh),
      "rightCameraOnline": bool((self.camera_detect_side & RIGHT_SIDE_BIT) and fresh),
      "leftLidarBlind": self.left_lidar_blind if fresh else False,
      "rightLidarBlind": self.right_lidar_blind if fresh else False,
      "leftLidarCarBlind": self.left_lidar_car_blind if fresh else False,
      "rightLidarCarBlind": self.right_lidar_car_blind if fresh else False,
      "leftCameraBlind": self.left_camera_blind if fresh else False,
      "rightCameraBlind": self.right_camera_blind if fresh else False,
      "targetsFresh": targets_fresh,
      "targets": dict(sorted(self.targets.items())),
      "dynamicBlind": self.dynamic_blind(targets_fresh),
      "targetUnits": {
        "drel": "millimeter longitudinal distance; front positive, rear negative in fishop reference",
        "xrel": "millimeter lateral distance",
        "vrel": "meter_per_second relative speed",
        "distTimeMs": "sensor timestamp in milliseconds",
      },
    }


@dataclass
class OvertakeEvidence:
  last_update_s: float = 0.
  command_seen: bool = False
  requested: bool = False
  direction: str = ""
  reason: str = ""
  source_device: str = ""
  cmd_index: int | None = None
  remote_cmd: str = ""
  remote_arg: str = ""

  def update(self, payload: dict[str, Any], now_s: float) -> None:
    self.command_seen = True
    self.requested = _as_bool(payload.get("overtake", payload.get("overtake_request", payload.get("request"))))
    self.direction = _limited_text(payload.get("direction"))
    self.reason = _limited_text(payload.get("reason"))
    self.source_device = _limited_text(payload.get("device", payload.get("resp", payload.get("type"))))
    if "index" in payload:
      self.cmd_index = _as_int(payload.get("index"), 0)
    if "cmd" in payload:
      self.remote_cmd = _limited_text(payload.get("cmd"))
    if "arg" in payload:
      self.remote_arg = _limited_text(payload.get("arg"))
    self.last_update_s = now_s

  def to_dict(self, now_s: float) -> dict[str, Any]:
    fresh = _fresh(self.last_update_s, now_s, OVERTAKE_MAX_AGE_S)
    direction = _overtake_direction(self.direction, self.remote_arg)
    return {
      "fresh": fresh,
      "ageSec": _age(self.last_update_s, now_s),
      "lastUpdateMonotonicSec": self.last_update_s if self.last_update_s > 0. else None,
      "commandSeen": self.command_seen and fresh,
      "requested": self.requested and fresh,
      "direction": direction if fresh else "",
      "rawDirection": self.direction if fresh else "",
      "reason": self.reason if fresh else "",
      "sourceDevice": self.source_device if fresh else "",
      "cmdIndex": self.cmd_index if fresh else None,
      "remoteCmd": self.remote_cmd if fresh else "",
      "remoteArg": self.remote_arg if fresh else "",
      "readOnly": True,
      "directionality": {
        "inbound": "external fishop APP/hardware command evidence reaches C3 as device=overtake/navi JSON or index/cmd/arg fields",
        "outbound": "fishop reference sends OP status back to overtake/navi clients on the client port and UDP 7705",
        "alphaAction": "record_only",
        "suggestionStage": "display_only",
        "usesExistingLaneChangeChain": False,
        "controlOutput": False,
      },
    }


@dataclass
class NavigationContextEvidence:
  last_update_s: float = 0.
  provider: str = ""
  country: str = ""
  region: str = ""
  locale: str = ""
  accuracy_m: float | None = None
  precision_m: float | None = None
  latitude: float | None = None
  longitude: float | None = None

  def update(self, payload: dict[str, Any], now_s: float) -> None:
    provider = _first_text(payload, "provider", "mapProvider", "navProvider", "navigationProvider", "map_provider")
    source = _limited_text(payload.get("source", payload.get("resp", payload.get("type", payload.get("device")))))
    if not provider and _text_has_any(source, ("amap", "gaode", "autonavi", "高德", "导航")):
      provider = source
    if provider:
      self.provider = provider

    country = _first_text(payload, "country", "countryCode", "country_code")
    if country:
      self.country = country
    region = _first_text(payload, "region", "navRegion", "navigationRegion")
    if region:
      self.region = region
    locale = _first_text(payload, "locale")
    if locale:
      self.locale = locale

    accuracy = _first_float(payload, "accuracyM", "gpsAccuracyM", "horizontalAccuracyM", "navAccuracyM", "locationAccuracyM")
    if accuracy is not None:
      self.accuracy_m = accuracy
    precision = _first_float(payload, "precisionM")
    if precision is not None:
      self.precision_m = precision

    lat = _first_float(payload, "lat", "latitude")
    lon = _first_float(payload, "lon", "lng", "longitude")
    if lat is not None:
      self.latitude = lat
    if lon is not None:
      self.longitude = lon
    self.last_update_s = now_s

  def policy(self, fresh: bool) -> dict[str, Any]:
    provider_text = " ".join(text for text in (self.provider, self.region, self.locale) if text)
    country_text = " ".join(text for text in (self.country, self.region, self.locale) if text)
    provider_supported = fresh and _text_has_any(provider_text, ("amap", "gaode", "autonavi", "高德"))
    region_supported = fresh and (
      _text_has_any(country_text, ("cn", "chn", "china", "中国", "mainland"))
      or self.country.upper() in ("CN", "CHN")
    )
    accuracy = self.accuracy_m if self.accuracy_m is not None else self.precision_m
    accuracy_usable = fresh and accuracy is not None and accuracy <= NAVIGATION_ACCURACY_THRESHOLD_M
    suggestion_eligible = provider_supported and region_supported and accuracy_usable
    reasons: list[str] = []
    if not fresh:
      reasons.append("navigation context is stale or missing")
    if fresh and not provider_supported:
      reasons.append("navigation provider is not a trusted domestic Amap/Gaode source")
    if fresh and not region_supported:
      reasons.append("navigation region is not mainland China; downgrade outside domestic map coverage")
    if fresh and not accuracy_usable:
      reasons.append("navigation accuracy is missing or worse than threshold")
    return {
      "readOnly": True,
      "controlOutput": False,
      "fresh": fresh,
      "providerTrustedForSuggestion": provider_supported,
      "regionSupportedForSuggestion": region_supported,
      "accuracyUsableForSuggestion": accuracy_usable,
      "accuracyM": _round_float(accuracy),
      "accuracyThresholdM": NAVIGATION_ACCURACY_THRESHOLD_M,
      "suggestionEligible": suggestion_eligible,
      "controlEligible": False,
      "decision": "eligible_for_suggestion_review" if suggestion_eligible else "hint_only",
      "reasons": reasons,
      "downgradeOutsideDomesticMap": True,
      "notUsedFor": ("lane-change execution", "steering target", "path output"),
    }

  def to_dict(self, now_s: float) -> dict[str, Any]:
    fresh = _fresh(self.last_update_s, now_s, NAVIGATION_CONTEXT_MAX_AGE_S)
    return {
      "fresh": fresh,
      "ageSec": _age(self.last_update_s, now_s),
      "lastUpdateMonotonicSec": self.last_update_s if self.last_update_s > 0. else None,
      "provider": self.provider if fresh else "",
      "country": self.country if fresh else "",
      "region": self.region if fresh else "",
      "locale": self.locale if fresh else "",
      "accuracyM": _round_float(self.accuracy_m if fresh else None),
      "precisionM": _round_float(self.precision_m if fresh else None),
      "positionAvailable": fresh and self.latitude is not None and self.longitude is not None,
      "latitude": _round_float(self.latitude, 6) if fresh else None,
      "longitude": _round_float(self.longitude, 6) if fresh else None,
      "readOnly": True,
      "controlOutput": False,
      "policy": self.policy(fresh),
    }


def _overtake_hint(basic_ready: bool, navigation_policy: dict[str, Any], direction: str, reasons: list[str]) -> dict[str, Any]:
  available = basic_ready and not navigation_policy.get("suggestionEligible", False)
  if available:
    message = "overtake request is clear for hint-only display; navigation gate blocks lane-change suggestion"
  elif basic_ready:
    message = "overtake request is clear for suggestion review; control output remains disabled"
  else:
    message = "overtake hint blocked by sensor or request evidence"
  return {
    "readOnly": True,
    "controlOutput": False,
    "emitsLateralCommand": False,
    "stage": "hint_only",
    "available": available,
    "direction": direction if available or basic_ready else "",
    "message": message,
    "blockingReasons": list(reasons),
    "navigationRequiredBeforeSuggestion": True,
    "downgradeOutsideDomesticMap": bool(navigation_policy.get("downgradeOutsideDomesticMap", True)),
  }


def _overtake_suggestion_preview(lane: dict[str, Any], blindspot: dict[str, Any],
                                 overtake: dict[str, Any], navigation: dict[str, Any]) -> dict[str, Any]:
  direction = overtake.get("direction", "")
  reasons: list[str] = []

  if not overtake.get("fresh"):
    reasons.append("overtake command is stale")
  if not overtake.get("requested"):
    reasons.append("no active overtake request")
  if direction not in ("left", "right"):
    reasons.append("direction is missing or unsupported")
  if not lane.get("fresh"):
    reasons.append("lane evidence is stale")
  if not blindspot.get("fresh"):
    reasons.append("blindspot evidence is stale")

  if direction == "left":
    if lane.get("leftLaneBlind"):
      reasons.append("left lane line blocks the suggestion")
    if blindspot.get("leftLidarBlind") or blindspot.get("leftLidarCarBlind") or blindspot.get("leftCameraBlind"):
      reasons.append("left blindspot evidence blocks the suggestion")
  elif direction == "right":
    if lane.get("rightLaneBlind"):
      reasons.append("right lane line blocks the suggestion")
    if blindspot.get("rightLidarBlind") or blindspot.get("rightLidarCarBlind") or blindspot.get("rightCameraBlind"):
      reasons.append("right blindspot evidence blocks the suggestion")

  active_dynamic = blindspot.get("dynamicBlind", {}).get("activeRiskPreview", [])
  if direction == "left" and any(str(item).startswith("l") for item in active_dynamic):
    reasons.append("left dynamic blind preview blocks the suggestion")
  if direction == "right" and any(str(item).startswith("r") for item in active_dynamic):
    reasons.append("right dynamic blind preview blocks the suggestion")

  basic_ready = not reasons
  navigation_policy = navigation.get("policy", {}) if isinstance(navigation.get("policy"), dict) else {}
  for reason in navigation_policy.get("reasons", []):
    reasons.append(str(reason))

  ready = not reasons
  return {
    "readOnly": True,
    "controlOutput": False,
    "stage": "display_only",
    "decision": "ready_for_suggestion" if ready else "blocked",
    "readyForSuggestion": ready,
    "direction": direction,
    "reasons": reasons,
    "navigationGate": navigation_policy,
    "overtakeHint": _overtake_hint(basic_ready, navigation_policy, direction, reasons),
    "evidence": {
      "overtakeFresh": bool(overtake.get("fresh")),
      "requestActive": bool(overtake.get("requested")),
      "laneFresh": bool(lane.get("fresh")),
      "blindspotFresh": bool(blindspot.get("fresh")),
      "navigationFresh": bool(navigation.get("fresh")),
      "targetLaneLineClear": direction == "left" and not lane.get("leftLaneBlind") or direction == "right" and not lane.get("rightLaneBlind"),
      "blindspotClear": direction == "left" and not (blindspot.get("leftLidarBlind") or blindspot.get("leftLidarCarBlind") or blindspot.get("leftCameraBlind"))
                         or direction == "right" and not (blindspot.get("rightLidarBlind") or blindspot.get("rightLidarCarBlind") or blindspot.get("rightCameraBlind")),
      "dynamicBlindClear": (direction == "left" and not any(str(item).startswith("l") for item in active_dynamic))
                           or (direction == "right" and not any(str(item).startswith("r") for item in active_dynamic)),
    },
    "nextRequiredGate": "existing safety chain must still approve before any lateral command",
    "emitsLateralCommand": False,
  }


@dataclass
class FishopHardwareState:
  lane: LaneEvidence = field(default_factory=LaneEvidence)
  blindspot: BlindspotEvidence = field(default_factory=BlindspotEvidence)
  overtake: OvertakeEvidence = field(default_factory=OvertakeEvidence)
  navigation: NavigationContextEvidence = field(default_factory=NavigationContextEvidence)

  def update_from_payload(self, payload: dict[str, Any], now_s: float | None = None) -> None:
    now_s = _now() if now_s is None else now_s
    source = _limited_text(payload.get("resp", payload.get("type", payload.get("device_type", payload.get("device"))))).lower()

    if source == "lane" or any(key in payload for key in LANE_KEYS):
      self.lane.update(payload, now_s)

    if source in ("blindspot", "cam_blind", "lidar", "camera") or any(key in payload for key in BLINDSPOT_KEYS):
      self.blindspot.update(payload, now_s)

    if source in ("navi", "navigation", "route", "amap") or any(key in payload for key in NAVIGATION_CONTEXT_KEYS):
      self.navigation.update(payload, now_s)

    if source == "overtake" or any(key in payload for key in OVERTAKE_TRIGGER_KEYS):
      self.overtake.update(payload, now_s)

  def to_dict(self, now_s: float | None = None) -> dict[str, Any]:
    now_s = _now() if now_s is None else now_s
    lane = self.lane.to_dict(now_s)
    blindspot = self.blindspot.to_dict(now_s)
    overtake = self.overtake.to_dict(now_s)
    navigation = self.navigation.to_dict(now_s)
    overtake["suggestionPreview"] = _overtake_suggestion_preview(lane, blindspot, overtake, navigation)
    last_updates = [
      value for value in (
        self.lane.last_update_s,
        self.blindspot.last_update_s,
        self.overtake.last_update_s,
        self.navigation.last_update_s,
      ) if value > 0.
    ]
    return {
      "readOnly": True,
      "controlOutputEnabled": CONTROL_OUTPUT_ENABLED,
      "protocol": dict(FISHOP_PROTOCOL),
      "source": "fishop/openpilot:selfdrive/carrot/amap_navi.py",
      "sensorOnline": bool(lane["fresh"] or blindspot["fresh"] or overtake["fresh"]),
      "lastUpdateMonotonicSec": max(last_updates) if last_updates else None,
      "lane": lane,
      "blindspot": blindspot,
      "navigation": navigation,
      "overtake": overtake,
    }


def normalize_fishop_payloads(payloads: Iterable[dict[str, Any]], now_s: float | None = None) -> dict[str, Any]:
  state = FishopHardwareState()
  base_now = _now() if now_s is None else now_s
  for payload in payloads:
    state.update_from_payload(payload, base_now)
  return state.to_dict(base_now)
