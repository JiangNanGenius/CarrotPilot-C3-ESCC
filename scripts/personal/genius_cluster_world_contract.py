#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openpilot.selfdrive.carrot.cluster_world import built_in_cluster_world_sample, normalize_cluster_world_sample


SCHEMA_DOC = ROOT / "docs/personal/CARROT_CLUSTER_WORLD_SCHEMA.md"
VISUAL_POLICY = ROOT / "docs/personal/VISUALIZATION_POLICY.md"
CLUSTER_WORLD_MODULE = ROOT / "selfdrive/carrot/cluster_world.py"
CARROT_SERVER = ROOT / "selfdrive/carrot/carrot_server.py"


@dataclass(frozen=True)
class CheckResult:
  name: str
  ok: bool
  detail: str = ""


def source_available(snapshot: dict[str, Any], name: str) -> bool:
  return bool(snapshot["sourceAvailability"].get(name, False))


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
    "debug-only local Web page",
    "/cluster_world",
    "/api/cluster_world",
    "the base road view is mutually exclusive, but evidence overlays are additive",
    "Carrot's lane and lane-change presentation is preferred",
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


def check_runtime_sources() -> list[CheckResult]:
  module = CLUSTER_WORLD_MODULE.read_text(encoding="utf-8")
  server = CARROT_SERVER.read_text(encoding="utf-8")
  required_module = (
    "SOURCE_COLORS = {",
    "def source_color",
    "def normalize_cluster_world_sample",
    "def built_in_cluster_world_sample",
    "def objects_from_radar_state",
    "def radar_points_from_live_tracks",
    '"sourceColor": source_color',
    '"raw": True',
    '"controlOutput": False',
    '"displayOnly": True',
  )
  required_server = (
    "from openpilot.selfdrive.carrot.cluster_world import default_cluster_world_snapshot, normalize_cluster_world_sample",
    "CLUSTER_WORLD_SERVICES = (",
    "def default_cluster_world_state",
    "def cluster_world_state",
    "async def cluster_world_loop",
    "async def api_cluster_world",
    "async def cluster_world_page",
    'app.router.add_get("/api/cluster_world", api_cluster_world)',
    'app.router.add_get("/cluster_world", cluster_world_page)',
    '"/api/cluster_world"',
    '"/cluster_world"',
    'fetch("/api/cluster_world"',
  )
  forbidden_server = (
    "PubMaster",
    "sendcan",
    "CarControl",
    "controlOutputAllowed",
  )
  try:
    loop_start = server.index("async def cluster_world_loop")
    loop_end = server.index("async def start_cluster_world", loop_start)
    loop_text = server[loop_start:loop_end]
  except ValueError:
    loop_text = server
  return [
    CheckResult(
      "cluster/world normalizer lives in runtime module",
      all(token in module for token in required_module),
      "selfdrive/carrot/cluster_world.py must hold the shared runtime normalizer",
    ),
    CheckResult(
      "Carrot Web exposes read-only cluster world API",
      all(token in server for token in required_server),
      "carrot_server.py must expose /api/cluster_world and use the shared normalizer",
    ),
    CheckResult(
      "cluster world server path remains display-only",
      not any(token in loop_text for token in forbidden_server) and '".put("' not in loop_text and "params.put" not in loop_text,
      "cluster_world_loop must not publish controls, send CAN, or write params",
    ),
  ]


def check_replay() -> list[CheckResult]:
  snapshot = normalize_cluster_world_sample(built_in_cluster_world_sample())
  sources = snapshot["sourceAvailability"]
  object_sources = {item["source"] for item in snapshot["objects"]}
  labels = {item["label"] for item in snapshot["objects"]}
  fallback_text = " ".join(snapshot["fallbacks"])
  all_objects = snapshot["objects"] + snapshot["radarPoints"]
  return [
    CheckResult("cluster snapshot is display-only", snapshot["displayOnly"] and not snapshot["controlOutput"], "controlOutput must stay false"),
    CheckResult("cluster snapshot has base lane-change evidence", snapshot["base"]["laneChangeIntent"] == "left", "preLaneChangeLeft should normalize to left intent"),
    CheckResult("cluster snapshot keeps source availability", all(source_available(snapshot, key) for key in ("carState", "modelV2", "radarState", "liveTracks", "Fishop", "onroadEvents")), json.dumps(sources, sort_keys=True)),
    CheckResult("cluster snapshot preserves lane and road-edge evidence", len(snapshot["lanes"]["laneLines"]) >= 4 and len(snapshot["lanes"]["roadEdges"]) >= 2 and snapshot["lanes"]["laneChangeAvailableLeft"] is True, "lane lines, road edges, and lane-change availability must be present"),
    CheckResult("cluster snapshot preserves multi-source objects", {"radarState", "modelV2.leadsV3", "carState", "Fishop"}.issubset(object_sources), f"sources={sorted(object_sources)}"),
    CheckResult("cluster snapshot preserves corner labels", {"LF", "RF"}.issubset(labels), f"labels={sorted(labels)}"),
    CheckResult("cluster snapshot preserves liveTracks radar points", len(snapshot["radarPoints"]) >= 2 and all(point["source"] == "liveTracks" for point in snapshot["radarPoints"]), "liveTracks points should normalize to radarPoints"),
    CheckResult("cluster snapshot colors every object source", all(item.get("sourceColor") for item in all_objects), "objects and radar points need deterministic source colors"),
    CheckResult("cluster snapshot marks raw liveTracks points", all(point.get("raw") is True and point.get("merged") is False for point in snapshot["radarPoints"]), "liveTracks points must stay raw display evidence"),
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
  parser = argparse.ArgumentParser(description="Validate the Carrot cluster/world runtime schema and replay fixture.")
  parser.add_argument("--self-test", action="store_true", help="run the offline schema and replay checks")
  parser.parse_args()

  results = check_documentation() + check_runtime_sources() + check_replay()
  print_results(results)
  return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
  raise SystemExit(main())
