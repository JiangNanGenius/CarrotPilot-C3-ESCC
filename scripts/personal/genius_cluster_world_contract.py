#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DOC = ROOT / "docs/personal/CARROT_CLUSTER_WORLD_SCHEMA.md"
VISUAL_POLICY = ROOT / "docs/personal/VISUALIZATION_POLICY.md"


@dataclass(frozen=True)
class CheckResult:
  name: str
  ok: bool
  detail: str = ""


def finite_float(value: Any, default: float = 0.0) -> float:
  try:
    parsed = float(value)
  except (TypeError, ValueError):
    return default
  if parsed != parsed or parsed in (float("inf"), float("-inf")):
    return default
  return parsed


def first_number(values: Any, default: float | None = None) -> float | None:
  if isinstance(values, (list, tuple)) and values:
    return finite_float(values[0], default if default is not None else 0.0)
  if isinstance(values, (int, float)):
    return finite_float(values)
  return default


def bool_value(value: Any) -> bool:
  if isinstance(value, str):
    return value.strip().lower() in ("1", "true", "yes", "on")
  return bool(value)


def source_available(snapshot: dict[str, Any], name: str) -> bool:
  return bool(snapshot["sourceAvailability"].get(name, False))


def normalize_model_path(model_v2: dict[str, Any]) -> list[dict[str, float]]:
  position = model_v2.get("position", {}) if isinstance(model_v2.get("position"), dict) else {}
  xs = position.get("x", [])
  ys = position.get("y", [])
  zs = position.get("z", [])
  path: list[dict[str, float]] = []
  for index in range(min(len(xs), len(ys), len(zs), 33)):
    path.append({
      "forwardM": finite_float(xs[index]),
      "lateralM": finite_float(ys[index]),
      "zM": finite_float(zs[index]),
    })
  return path


def normalize_lane_lines(model_v2: dict[str, Any]) -> list[dict[str, Any]]:
  lane_lines = model_v2.get("laneLines", [])
  probs = model_v2.get("laneLineProbs", [])
  normalized: list[dict[str, Any]] = []
  for index, lane in enumerate(lane_lines[:4] if isinstance(lane_lines, list) else []):
    if not isinstance(lane, dict):
      continue
    normalized.append({
      "index": index,
      "prob": finite_float(probs[index] if index < len(probs) else 0.0),
      "points": normalize_model_path({"position": lane}),
    })
  return normalized


def normalize_road_edges(model_v2: dict[str, Any]) -> list[dict[str, Any]]:
  road_edges = model_v2.get("roadEdges", [])
  stds = model_v2.get("roadEdgeStds", [])
  normalized: list[dict[str, Any]] = []
  for index, edge in enumerate(road_edges[:2] if isinstance(road_edges, list) else []):
    if not isinstance(edge, dict):
      continue
    normalized.append({
      "index": index,
      "std": finite_float(stds[index] if index < len(stds) else 1.0),
      "points": normalize_model_path({"position": edge}),
    })
  return normalized


def object_from_radar_lead(label: str, lead: dict[str, Any]) -> dict[str, Any] | None:
  if not bool_value(lead.get("status")):
    return None
  d_rel = finite_float(lead.get("dRel"))
  if d_rel <= 0.2:
    return None
  return {
    "label": label,
    "source": "radarState",
    "longitudinalM": d_rel,
    "lateralM": -finite_float(lead.get("yRel")),
    "relativeSpeedMps": finite_float(lead.get("vRel")),
    "absoluteSpeedKph": max(0.0, finite_float(lead.get("vLead", 0.0)) * 3.6),
    "primary": label == "TARGET",
  }


def objects_from_radar_state(radar_state: dict[str, Any]) -> list[dict[str, Any]]:
  objects: list[dict[str, Any]] = []
  for label, key in (("TARGET", "leadOne"), ("TARGET2", "leadTwo")):
    lead = radar_state.get(key, {})
    if isinstance(lead, dict):
      obj = object_from_radar_lead(label, lead)
      if obj is not None:
        objects.append(obj)
  return objects


def objects_from_model(model_v2: dict[str, Any]) -> list[dict[str, Any]]:
  leads = model_v2.get("leadsV3", [])
  model_speed = first_number((model_v2.get("velocity", {}) or {}).get("x"), 0.0)
  objects: list[dict[str, Any]] = []
  for index, lead in enumerate(leads[:2] if isinstance(leads, list) else []):
    if not isinstance(lead, dict):
      continue
    prob = finite_float(lead.get("prob"))
    if prob < 0.35:
      continue
    x_m = first_number(lead.get("x"))
    y_m = first_number(lead.get("y"))
    if x_m is None or y_m is None:
      continue
    v_mps = first_number(lead.get("v"))
    objects.append({
      "label": f"M{index + 1}",
      "source": "modelV2.leadsV3",
      "longitudinalM": x_m,
      "lateralM": y_m,
      "probability": prob,
      "relativeSpeedMps": None if v_mps is None or model_speed is None else v_mps - model_speed,
      "absoluteSpeedKph": None if v_mps is None else max(0.0, v_mps * 3.6),
      "primary": index == 0,
    })
  return objects


def objects_from_car_state(car_state: dict[str, Any]) -> list[dict[str, Any]]:
  corners = (
    ("LF", "leftLongDist", "leftLatDist", -1.0, 1.0),
    ("RF", "rightLongDist", "rightLatDist", 1.0, 1.0),
    ("LR", "leftRearLongDist", "leftRearLatDist", -1.0, -1.0),
    ("RR", "rightRearLongDist", "rightRearLatDist", 1.0, -1.0),
  )
  objects: list[dict[str, Any]] = []
  for label, long_key, lat_key, side, forward_sign in corners:
    dist = finite_float(car_state.get(long_key))
    if not 0.2 < dist < 180.0:
      continue
    objects.append({
      "label": label,
      "source": "carState",
      "longitudinalM": forward_sign * dist,
      "lateralM": side * abs(finite_float(car_state.get(lat_key))),
    })
  return objects


def objects_from_fishop(fishop: dict[str, Any]) -> list[dict[str, Any]]:
  blindspot = fishop.get("blindspot", {}) if isinstance(fishop.get("blindspot"), dict) else {}
  objects: list[dict[str, Any]] = []
  for label, key, lateral in (
    ("FISHOP_L", "leftLidarCarBlind", -3.4),
    ("FISHOP_R", "rightLidarCarBlind", 3.4),
  ):
    if bool_value(blindspot.get(key)):
      objects.append({
        "label": label,
        "source": "Fishop",
        "longitudinalM": 8.0,
        "lateralM": lateral,
        "probability": 0.8,
      })
  return objects


def radar_points_from_live_tracks(live_tracks: dict[str, Any], ego_speed_kph: float) -> list[dict[str, Any]]:
  points: list[dict[str, Any]] = []
  tracks = live_tracks.get("points", [])
  for index, track in enumerate(tracks if isinstance(tracks, list) else []):
    if not isinstance(track, dict):
      continue
    d_rel = finite_float(track.get("dRel"))
    if not 0.2 < d_rel < 180.0:
      continue
    v_rel = finite_float(track.get("vRel"))
    track_id = track.get("trackId", index)
    points.append({
      "label": f"T{track_id}",
      "source": "liveTracks",
      "longitudinalM": d_rel,
      "lateralM": -finite_float(track.get("yRel")),
      "relativeSpeedMps": v_rel,
      "absoluteSpeedKph": max(0.0, ego_speed_kph + v_rel * 3.6),
      "lateralSpeedMps": -finite_float(track.get("yvRel")),
      "relativeAccelMps2": finite_float(track.get("aRel")),
      "valid": 1 if bool_value(track.get("measured", True)) else 0,
    })
  return points


def lane_change_intent(onroad_events: list[str]) -> str:
  if "preLaneChangeLeft" in onroad_events:
    return "left"
  if "preLaneChangeRight" in onroad_events:
    return "right"
  if "laneChange" in onroad_events:
    return "active"
  return "none"


def normalize_cluster_world_sample(sample: dict[str, Any]) -> dict[str, Any]:
  car_state = sample.get("carState", {}) if isinstance(sample.get("carState"), dict) else {}
  model_v2 = sample.get("modelV2", {}) if isinstance(sample.get("modelV2"), dict) else {}
  radar_state = sample.get("radarState", {}) if isinstance(sample.get("radarState"), dict) else {}
  live_tracks = sample.get("liveTracks", {}) if isinstance(sample.get("liveTracks"), dict) else {}
  fishop = sample.get("fishop", {}) if isinstance(sample.get("fishop"), dict) else {}
  onroad_events = sample.get("onroadEvents", [])
  if not isinstance(onroad_events, list):
    onroad_events = []

  meta = model_v2.get("meta", {}) if isinstance(model_v2.get("meta"), dict) else {}
  left_width = meta.get("laneWidthLeft")
  right_width = meta.get("laneWidthRight")
  lane_widths = [finite_float(value) for value in (left_width, right_width) if value is not None]
  lane_width_m = sum(lane_widths) / len(lane_widths) if lane_widths else 3.6
  speed_kph = finite_float(car_state.get("vEgo")) * 3.6

  snapshot = {
    "displayOnly": True,
    "controlOutput": False,
    "base": {
      "speedKph": speed_kph,
      "cruiseKph": finite_float((car_state.get("cruiseState", {}) or {}).get("speed"), 0.0) * 3.6,
      "leftBlinker": bool_value(car_state.get("leftBlinker")),
      "rightBlinker": bool_value(car_state.get("rightBlinker")),
      "leftBlindspot": bool_value(car_state.get("leftBlindspot")),
      "rightBlindspot": bool_value(car_state.get("rightBlindspot")),
      "laneChangeIntent": lane_change_intent([str(event) for event in onroad_events]),
    },
    "lanes": {
      "laneWidthM": lane_width_m,
      "modelPath": normalize_model_path(model_v2),
      "laneLines": normalize_lane_lines(model_v2),
      "roadEdges": normalize_road_edges(model_v2),
      "leftLaneLine": car_state.get("leftLaneLine", "unknown"),
      "rightLaneLine": car_state.get("rightLaneLine", "unknown"),
      "activeLaneLine": car_state.get("activeLaneLine"),
      "leftLaneWidthM": left_width,
      "rightLaneWidthM": right_width,
      "leftRoadEdgeDistanceM": meta.get("distanceToRoadEdgeLeft"),
      "rightRoadEdgeDistanceM": meta.get("distanceToRoadEdgeRight"),
      "laneChangeAvailableLeft": meta.get("laneChangeAvailableLeft"),
      "laneChangeAvailableRight": meta.get("laneChangeAvailableRight"),
    },
    "objects": [],
    "radarPoints": [],
    "plans": {
      "longitudinal": sample.get("longitudinalPlan", {}) if isinstance(sample.get("longitudinalPlan"), dict) else {},
      "lateral": sample.get("lateralPlan", {}) if isinstance(sample.get("lateralPlan"), dict) else {},
    },
    "fishop": fishop,
    "sourceAvailability": {
      "carState": bool(car_state),
      "modelV2": bool(model_v2),
      "radarState": bool(radar_state),
      "liveTracks": bool(live_tracks.get("points")),
      "Fishop": bool(fishop),
      "onroadEvents": bool(onroad_events),
      "longitudinalPlan": isinstance(sample.get("longitudinalPlan"), dict),
      "lateralPlan": isinstance(sample.get("lateralPlan"), dict),
    },
    "fallbacks": [],
  }

  snapshot["objects"] = (
    objects_from_radar_state(radar_state)
    + objects_from_model(model_v2)
    + objects_from_car_state(car_state)
    + objects_from_fishop(fishop)
  )
  snapshot["radarPoints"] = radar_points_from_live_tracks(live_tracks, speed_kph)

  if snapshot["lanes"]["activeLaneLine"] is None:
    snapshot["fallbacks"].append("activeLaneLine unavailable")
  if snapshot["lanes"]["leftLaneLine"] == "unknown":
    snapshot["fallbacks"].append("leftLaneLine unavailable")
  if snapshot["lanes"]["rightLaneLine"] == "unknown":
    snapshot["fallbacks"].append("rightLaneLine unavailable")
  if not snapshot["radarPoints"]:
    snapshot["fallbacks"].append("liveTracks.points unavailable")
  return snapshot


def built_in_sample() -> dict[str, Any]:
  points_x = [float(i * 3) for i in range(12)]
  path_y = [0.03 * i for i in range(12)]
  zeros = [0.0 for _ in range(12)]
  return {
    "carState": {
      "vEgo": 18.5,
      "leftBlinker": True,
      "rightBlinker": False,
      "leftBlindspot": False,
      "rightBlindspot": True,
      "cruiseState": {"speed": 22.2},
      "leftLongDist": 9.5,
      "leftLatDist": 1.7,
      "rightLongDist": 12.0,
      "rightLatDist": 1.9,
      "leftLaneLine": 1,
      "rightLaneLine": 2,
    },
    "modelV2": {
      "position": {"x": points_x, "y": path_y, "z": zeros},
      "velocity": {"x": [18.0]},
      "laneLines": [
        {"x": points_x, "y": [-5.4 for _ in points_x], "z": zeros},
        {"x": points_x, "y": [-1.8 for _ in points_x], "z": zeros},
        {"x": points_x, "y": [1.8 for _ in points_x], "z": zeros},
        {"x": points_x, "y": [5.4 for _ in points_x], "z": zeros},
      ],
      "laneLineProbs": [0.35, 0.89, 0.91, 0.42],
      "roadEdges": [
        {"x": points_x, "y": [-6.4 for _ in points_x], "z": zeros},
        {"x": points_x, "y": [6.4 for _ in points_x], "z": zeros},
      ],
      "roadEdgeStds": [0.22, 0.35],
      "leadsV3": [
        {"prob": 0.82, "x": [32.0], "y": [-0.4], "v": [15.5], "a": [-0.4], "xStd": [1.5], "yStd": [0.4]},
        {"prob": 0.55, "x": [44.0], "y": [3.1], "v": [17.2], "a": [0.1]},
      ],
      "meta": {
        "laneWidthLeft": 3.55,
        "laneWidthRight": 3.62,
        "distanceToRoadEdgeLeft": 5.8,
        "distanceToRoadEdgeRight": 6.1,
        "laneChangeAvailableLeft": True,
        "laneChangeAvailableRight": False,
      },
    },
    "radarState": {
      "leadOne": {"status": True, "dRel": 28.0, "yRel": 0.2, "vRel": -1.2, "vLead": 17.3, "aLeadK": -0.1},
      "leadTwo": {"status": True, "dRel": 42.0, "yRel": -3.2, "vRel": 0.5, "vLead": 19.0, "aLeadK": 0.0},
    },
    "liveTracks": {
      "points": [
        {"trackId": 101, "dRel": 28.4, "yRel": 0.15, "vRel": -1.0, "vLead": 17.5, "yvRel": 0.02, "aRel": -0.1, "measured": True},
        {"trackId": 202, "dRel": 45.0, "yRel": -3.0, "vRel": 0.4, "vLead": 18.7, "yvRel": -0.05, "aRel": 0.0, "measured": True},
      ],
    },
    "onroadEvents": ["preLaneChangeLeft"],
    "longitudinalPlan": {"speeds": [18.0, 17.7], "accels": [-0.2, -0.4], "shouldStop": False},
    "lateralPlan": {"useLaneLines": True, "curvatures": [0.001, 0.0012]},
    "fishop": {
      "lane": {"fresh": True, "leftLine": 88, "rightLine": 92},
      "blindspot": {"leftLidarCarBlind": True, "rightLidarCarBlind": False},
      "overtake": {"suggestionPreview": {"direction": "LEFT", "readyForSuggestion": False}},
    },
  }


def check_documentation() -> list[CheckResult]:
  doc = SCHEMA_DOC.read_text(encoding="utf-8")
  policy = VISUAL_POLICY.read_text(encoding="utf-8")
  required_doc = (
    "GeniusClusterWorldSnapshot",
    "ClusterUiState",
    "DetectedVehicle",
    "RadarPoint",
    "LaneMarking",
    "ModelPathPoint",
    "modelV2",
    "radarState.leadOne/leadTwo",
    "liveTracks.points",
    "carState.leftLongDist/rightLongDist/leftRearLongDist/rightRearLongDist",
    "Fishop",
    "activeLaneLine unavailable",
    "controlOutput",
    "Replay Requirements",
  )
  required_policy = (
    "Carrot Cluster / World View",
    "standalone page",
    "debug-only visual mode",
  )
  return [
    CheckResult(
      "cluster/world schema doc covers source fields and fallbacks",
      all(token in doc for token in required_doc),
      "docs/personal/CARROT_CLUSTER_WORLD_SCHEMA.md must name source models, fields, fallbacks, display-only boundary, and replay requirements",
    ),
    CheckResult(
      "visual policy keeps full cluster surface separate",
      all(token in policy for token in required_policy),
      "visualization policy must keep full Carrot cluster/world view outside the default main HUD",
    ),
  ]


def check_replay() -> list[CheckResult]:
  snapshot = normalize_cluster_world_sample(built_in_sample())
  sources = snapshot["sourceAvailability"]
  object_sources = {item["source"] for item in snapshot["objects"]}
  labels = {item["label"] for item in snapshot["objects"]}
  fallback_text = " ".join(snapshot["fallbacks"])
  return [
    CheckResult("cluster snapshot is display-only", snapshot["displayOnly"] and not snapshot["controlOutput"], "controlOutput must stay false"),
    CheckResult("cluster snapshot has base lane-change evidence", snapshot["base"]["laneChangeIntent"] == "left", "preLaneChangeLeft should normalize to left intent"),
    CheckResult("cluster snapshot keeps source availability", all(source_available(snapshot, key) for key in ("carState", "modelV2", "radarState", "liveTracks", "Fishop", "onroadEvents")), json.dumps(sources, sort_keys=True)),
    CheckResult("cluster snapshot preserves lane and road-edge evidence", len(snapshot["lanes"]["laneLines"]) >= 4 and len(snapshot["lanes"]["roadEdges"]) >= 2 and snapshot["lanes"]["laneChangeAvailableLeft"] is True, "lane lines, road edges, and lane-change availability must be present"),
    CheckResult("cluster snapshot preserves multi-source objects", {"radarState", "modelV2.leadsV3", "carState", "Fishop"}.issubset(object_sources), f"sources={sorted(object_sources)}"),
    CheckResult("cluster snapshot preserves corner labels", {"LF", "RF"}.issubset(labels), f"labels={sorted(labels)}"),
    CheckResult("cluster snapshot preserves liveTracks radar points", len(snapshot["radarPoints"]) >= 2 and all(point["source"] == "liveTracks" for point in snapshot["radarPoints"]), "liveTracks points should normalize to radarPoints"),
    CheckResult("cluster snapshot records missing ajouatom-only fields", "activeLaneLine unavailable" in fallback_text, fallback_text),
    CheckResult("cluster snapshot has no output-channel keys", all(key not in snapshot for key in ("sendcan", "CarControl", "PubMaster", "controlCommand")), "schema must not expose output channels"),
  ]


def print_results(results: list[CheckResult]) -> None:
  for result in results:
    if result.ok:
      print(f"PASS {result.name}")
    else:
      print(f"FAIL {result.name}: {result.detail}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate the Carrot cluster/world schema and replay fixture.")
  parser.add_argument("--self-test", action="store_true", help="run the offline schema and replay checks")
  args = parser.parse_args()

  results = check_documentation() + check_replay()
  print_results(results)
  return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
  raise SystemExit(main())
