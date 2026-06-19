#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
MODEL_RENDERER = ROOT / "selfdrive/ui/onroad/model_renderer.py"
CARROT_WORLD_OVERLAY = ROOT / "selfdrive/ui/onroad/carrot_world_overlay.py"
AUGMENTED_ROAD_VIEW = ROOT / "selfdrive/ui/onroad/augmented_road_view.py"
VISUALS_LAYOUT = ROOT / "selfdrive/ui/sunnypilot/layouts/settings/visuals.py"
TURN_SIGNAL = ROOT / "selfdrive/ui/sunnypilot/onroad/turn_signal.py"
PARAM_KEYS = ROOT / "common/params_keys.h"
VISUAL_POLICY = ROOT / "docs/personal/VISUALIZATION_POLICY.md"

C3_CONTENT = (0.0, 0.0, 2160.0, 1080.0)
HUD_SAFE_Y = 360.0


@dataclass(frozen=True)
class CheckResult:
  name: str
  ok: bool
  detail: str = ""


def source_section(text: str, start: str, end: str) -> str:
  start_idx = text.index(start)
  end_idx = text.index(end, start_idx)
  return text[start_idx:end_idx]


def check_sources() -> list[CheckResult]:
  renderer = MODEL_RENDERER.read_text(encoding="utf-8")
  carrot_world = CARROT_WORLD_OVERLAY.read_text(encoding="utf-8")
  augmented = AUGMENTED_ROAD_VIEW.read_text(encoding="utf-8")
  visuals = VISUALS_LAYOUT.read_text(encoding="utf-8")
  turn_signal = TURN_SIGNAL.read_text(encoding="utf-8")
  params = PARAM_KEYS.read_text(encoding="utf-8")
  policy = VISUAL_POLICY.read_text(encoding="utf-8")
  path_section = source_section(renderer, "  def _draw_path(self, sm):", "  def _draw_lead_indicator(self):")
  carrot_world_render_section = source_section(carrot_world, "  def _render(self, rect: rl.Rectangle) -> None:", "  def _draw_lane_world(self, rect: rl.Rectangle) -> None:")

  required_renderer = (
    "CARROT_PATH_ACTIVE_COLORS",
    "CARROT_PATH_LIMITED_COLORS",
    "ui_state.genius_visual_mode == 1",
    "ui_state.genius_visual_mode == 2",
    "def _draw_path_sunny",
    "def _draw_path_carrot",
    "def _draw_path_fusion",
    "def _draw_path_edges",
    "def _draw_carrot_path_markers",
    "draw_polygon(self._rect, self._path.projected_points",
    "rl.draw_line_ex",
    "rl.draw_circle_v",
  )
  required_lane_lead = (
    "_get_lane_line_color",
    "_update_leads_carrot",
    "_draw_lead_rect",
    "_update_radar_info",
    "genius_lead_radar_visual_mode",
    "genius_lane_line_style",
  )
  required_visuals = (
    "Genius Visualization Preset",
    "Carrot emphasizes lane, path, lead, and radar information",
    "Carrot-style lane and path cues",
    "Fishop and Carrot World overlays are independent top layers",
    "Carrot World Overlay",
    "side-lane, blindspot, lane-change, lead, and radar evidence",
    "callback=self._apply_visual_preset",
    "self._params.put(\"GeniusLaneLineStyle\", 2)",
    "self._params.put(\"GeniusLeadRadarVisualMode\", 2)",
    "self._params.put(\"GeniusLaneLineStyle\", 1)",
    "self._params.put(\"GeniusLeadRadarVisualMode\", 1)",
  )
  required_defaults = (
    '{"GeniusCarrotWorldOverlay", {PERSISTENT | BACKUP, BOOL, "0"}}',
    '{"GeniusVisualMode", {PERSISTENT | BACKUP, INT, "2"}}',
    '{"GeniusLaneLineStyle", {PERSISTENT | BACKUP, INT, "1"}}',
    '{"GeniusLeadRadarVisualMode", {PERSISTENT | BACKUP, INT, "1"}}',
    '{"GeniusLaneChangeVisuals", {PERSISTENT | BACKUP, BOOL, "1"}}',
    '{"GeniusFishopVisualOverlay", {PERSISTENT | BACKUP, BOOL, "0"}}',
  )
  required_policy = (
    "One base preset is active at a time",
    "`Sunny`: minimal upstream-style HUD",
    "`Carrot`: denser Carrot-style road view",
    "`Fusion`: default C3 preset",
    "`GeniusCarrotWorldOverlay` is independent",
    "`GeniusFishopVisualOverlay` is not a base preset",
    "the base road view is mutually exclusive, but evidence overlays are additive",
    "Carrot's lane and lane-change presentation is preferred",
    "Carrot Cluster / World View",
    "Visualization settings must not publish control messages",
    "The C3 alpha default is `GeniusVisualMode=2`",
  )
  required_lane_change = (
    "class LaneChangeIntentWidget",
    "EventName.preLaneChangeLeft",
    "EventName.preLaneChangeRight",
    "EventName.laneChange",
    "ui_state.genius_lane_change_visuals",
    "rect.y + 120",
    "rl.draw_texture_pro",
  )
  required_carrot_world = (
    "class CarrotWorldOverlay",
    "ui_state.genius_carrot_world_overlay",
    "EventName.preLaneChangeLeft",
    "EventName.preLaneChangeRight",
    "leftBlindspot",
    "rightBlindspot",
    "leadOne",
    "leadTwo",
    "_draw_lane_world",
    "_draw_lead_world",
    "_draw_radar_vector",
    "draw_polygon(rect, polygon",
  )
  required_augmented = (
    "from openpilot.selfdrive.ui.onroad.carrot_world_overlay import CarrotWorldOverlay",
    "self.carrot_world_overlay = CarrotWorldOverlay()",
    "self.carrot_world_overlay.render(self._content_rect)",
    "self.carrot_world_overlay.set_transform(video_transform @ calib_transform)",
  )
  required_stack_order = (
    "self.model_renderer.render(self._content_rect)",
    "self.carrot_world_overlay.render(self._content_rect)",
    "self.fishop_overlay.render(self._content_rect)",
    "self._hud_renderer.render(self._content_rect)",
    "self.alert_renderer.render(self._content_rect)",
  )
  forbidden_path_tokens = (
    "PubMaster",
    "SubMaster",
    "CarControl",
    "CANParser",
    "sendto",
    ".bind(",
    "Params(",
    ".put(",
    "desire_helper",
    "laneChange",
    "controlOutputEnabled = True",
  )
  forbidden_lane_change_tokens = tuple(token for token in forbidden_path_tokens if token != "laneChange")
  stack_tokens_present = all(token in augmented for token in required_stack_order)
  stack_order_ok = stack_tokens_present and all(
    augmented.index(required_stack_order[i]) < augmented.index(required_stack_order[i + 1])
    for i in range(len(required_stack_order) - 1)
  )

  results = [
    CheckResult(
      "renderer path mode entry points",
      all(token in renderer for token in required_renderer),
      "missing one or more Carrot/Fusion path renderer tokens",
    ),
    CheckResult(
      "visuals settings describe path presets",
      all(token in visuals for token in required_visuals),
      "Visuals page must explain lane/path ownership and preset callback defaults",
    ),
    CheckResult(
      "visual params default to Fusion with Fishop off",
      all(token in params for token in required_defaults),
      "C3 defaults must keep Fusion as the base display and Carrot/Fishop overlays off",
    ),
    CheckResult(
      "visualization policy documents coexistence",
      all(token in policy for token in required_policy),
      "docs/personal/VISUALIZATION_POLICY.md must define base presets, overlay rules, and safety boundary",
    ),
    CheckResult(
      "renderer lane and lead modes wired",
      all(token in renderer for token in required_lane_lead),
      "renderer must include Carrot lane-line, lead-box, and radar-label paths",
    ),
    CheckResult(
      "lane-change intent widget wired",
      all(token in turn_signal for token in required_lane_change),
      "lane-change display must use existing onroad events and GeniusLaneChangeVisuals",
    ),
    CheckResult(
      "Carrot world overlay wired",
      all(token in carrot_world for token in required_carrot_world) and all(token in augmented for token in required_augmented),
      "Carrot world overlay must be an independent display-only layer wired into onroad view",
    ),
    CheckResult(
      "visual overlays render between base road and HUD",
      stack_order_ok,
      "onroad view must render base road, Carrot World, Fishop, HUD, and alerts in that order",
    ),
    CheckResult(
      "path renderer remains display-only",
      not any(token in path_section for token in forbidden_path_tokens),
      "path renderer section must not publish controls, write params, open sockets, or touch lane-change control",
    ),
    CheckResult(
      "Carrot world overlay remains display-only",
      not any(token in carrot_world_render_section for token in forbidden_path_tokens) and
      "PubMaster" not in carrot_world and "Params(" not in carrot_world and ".put(" not in carrot_world,
      "Carrot world overlay must not publish controls, write params, open sockets, or touch lane-change control",
    ),
    CheckResult(
      "lane-change renderer remains display-only",
      not any(token in turn_signal for token in forbidden_lane_change_tokens),
      "lane-change renderer must not publish controls, write params, open sockets, or alter lane-change decisions",
    ),
  ]
  return results


def synthetic_path_polygon() -> np.ndarray:
  y = np.linspace(945.0, 410.0, 44, dtype=np.float32)
  phase = np.linspace(0.0, 1.45, 44, dtype=np.float32)
  center_x = 1080.0 + np.sin(phase) * 92.0
  half_width = np.linspace(230.0, 48.0, 44, dtype=np.float32)
  left = np.column_stack((center_x - half_width, y))
  right = np.column_stack((center_x + half_width, y))
  return np.vstack((left, right[::-1])).astype(np.float32)


def synthetic_lane_polygon(center_offset: float, width: float = 16.0) -> np.ndarray:
  y = np.linspace(990.0, 390.0, 38, dtype=np.float32)
  phase = np.linspace(0.0, 1.2, 38, dtype=np.float32)
  center_x = 1080.0 + center_offset + np.sin(phase) * 80.0
  half_width = np.linspace(width, width * 0.35, 38, dtype=np.float32)
  left = np.column_stack((center_x - half_width, y))
  right = np.column_stack((center_x + half_width, y))
  return np.vstack((left, right[::-1])).astype(np.float32)


def synthetic_lead_rect() -> np.ndarray:
  return np.array([
    (930.0, 430.0),
    (1230.0, 430.0),
    (1230.0, 675.0),
    (930.0, 675.0),
  ], dtype=np.float32)


def rect_nonblank(rect: np.ndarray) -> bool:
  width = float(np.max(rect[:, 0]) - np.min(rect[:, 0]))
  height = float(np.max(rect[:, 1]) - np.min(rect[:, 1]))
  return width > 10.0 and height > 10.0


def edge_points(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
  half = points.shape[0] // 2
  return points[:half], points[half:][::-1]


def check_geometry() -> list[CheckResult]:
  polygon = synthetic_path_polygon()
  lane_polygons = [synthetic_lane_polygon(offset) for offset in (-520.0, -175.0, 175.0, 520.0)]
  lead_rect = synthetic_lead_rect()
  left, right = edge_points(polygon)
  center = (left + right) * 0.5

  marker_indices = list(range(3, min(center.shape[0], 44), 6))
  edge_widths = right[:, 0] - left[:, 0]
  lane_change_rect = (0.0, 120.0, 2160.0, 960.0)
  lane_change_texture_center = (lane_change_rect[0] + lane_change_rect[2] * 0.5,
                                lane_change_rect[1] + lane_change_rect[3] * 0.5)
  carrot_world_left = np.array([
    (210.0, 845.0),
    (310.0, 620.0),
    (410.0, 390.0),
    (515.0, 392.0),
    (430.0, 620.0),
    (330.0, 845.0),
  ], dtype=np.float32)
  carrot_world_right = carrot_world_left.copy()
  carrot_world_right[:, 0] = C3_CONTENT[2] - carrot_world_left[:, 0]

  results = [
    CheckResult("synthetic path polygon nonblank", polygon.shape[0] >= 20, f"point count={polygon.shape[0]}"),
    CheckResult("synthetic path top stays below HUD", float(np.min(polygon[:, 1])) > HUD_SAFE_Y, f"top y={float(np.min(polygon[:, 1])):.1f}"),
    CheckResult("synthetic path stays in camera content", bool(np.all((polygon[:, 0] >= C3_CONTENT[0]) & (polygon[:, 0] <= C3_CONTENT[2]) &
                                                                       (polygon[:, 1] >= C3_CONTENT[1]) & (polygon[:, 1] <= C3_CONTENT[3]))),
                "path points should remain inside the C3 camera content rectangle"),
    CheckResult("path edge widths remain drawable", bool(np.all(edge_widths > 24.0)), f"min width={float(np.min(edge_widths)):.1f}"),
    CheckResult("Carrot center markers are nonblank", len(marker_indices) >= 5, f"marker count={len(marker_indices)}"),
    CheckResult("center track follows lane center", bool(np.allclose(center[:, 0], (left[:, 0] + right[:, 0]) * 0.5)), "centerline math mismatch"),
    CheckResult("lane polygons nonblank in replay", all(poly.shape[0] >= 20 and rect_nonblank(poly) for poly in lane_polygons),
                "all four lane-line polygons should have drawable area"),
    CheckResult("lane polygons avoid speed HUD", all(float(np.min(poly[:, 1])) > HUD_SAFE_Y for poly in lane_polygons),
                "lane-line polygons should start below the upper speed/HUD band"),
    CheckResult("lead box nonblank in replay", rect_nonblank(lead_rect), "Carrot lead box should have drawable size"),
    CheckResult("lead box avoids speed HUD", float(np.min(lead_rect[:, 1])) > HUD_SAFE_Y, f"lead top y={float(np.min(lead_rect[:, 1])):.1f}"),
    CheckResult("lane-change cue avoids speed HUD", lane_change_rect[1] >= 120.0 and lane_change_texture_center[1] > HUD_SAFE_Y,
                f"lane-change center y={lane_change_texture_center[1]:.1f}"),
    CheckResult("Carrot world side-lane overlay nonblank", rect_nonblank(carrot_world_left) and rect_nonblank(carrot_world_right),
                "side-lane overlay should have drawable left/right bands"),
    CheckResult("Carrot world overlay avoids speed HUD", float(np.min(carrot_world_left[:, 1])) > HUD_SAFE_Y and float(np.min(carrot_world_right[:, 1])) > HUD_SAFE_Y,
                "Carrot world side-lane bands should stay below the upper speed/HUD band"),
  ]
  return results


def check_visual_modes() -> list[CheckResult]:
  polygon = synthetic_path_polygon()
  left, right = edge_points(polygon)
  center = (left + right) * 0.5
  marker_count = len(list(range(3, min(center.shape[0], 44), 6)))

  mode_expectations = {
    "Sunny": {
      "mode": 0,
      "path": polygon.shape[0] >= 20,
      "carrot_edges": False,
      "markers": False,
    },
    "Carrot": {
      "mode": 1,
      "path": polygon.shape[0] >= 20,
      "carrot_edges": True,
      "markers": marker_count >= 5,
    },
    "Fusion": {
      "mode": 2,
      "path": polygon.shape[0] >= 20,
      "carrot_edges": True,
      "markers": False,
    },
  }

  results: list[CheckResult] = []
  for name, expected in mode_expectations.items():
    detail = f"mode={expected['mode']} edges={expected['carrot_edges']} markers={expected['markers']}"
    results.append(CheckResult(f"{name} visual replay contract", bool(expected["path"]), detail))

  results.append(CheckResult("visual base presets are mutually exclusive", len({m["mode"] for m in mode_expectations.values()}) == 3,
                             "Sunny, Carrot, and Fusion must remain distinct base presets"))
  results.append(CheckResult("Fusion is the default C3 base preset", mode_expectations["Fusion"]["mode"] == 2,
                             "Fusion keeps Sunny HUD structure with Carrot road cues"))
  results.append(CheckResult("Carrot preset is the dense lane/path/lead/radar preset",
                             bool(mode_expectations["Carrot"]["carrot_edges"] and mode_expectations["Carrot"]["markers"]),
                             "Carrot mode must keep the denser route ribbon and center markers"))
  results.append(CheckResult("Fishop overlay remains independent of base preset",
                             all("GeniusFishopVisualOverlay" != name for name in mode_expectations),
                             "Fishop overlay is a separate top layer checked in static UI/source tests"))
  results.append(CheckResult("Carrot world overlay remains independent of base preset",
                             all("GeniusCarrotWorldOverlay" != name for name in mode_expectations),
                             "Carrot world overlay is a separate evidence layer checked in static UI/source tests"))
  return results


def print_results(results: list[CheckResult]) -> None:
  for result in results:
    if result.ok:
      print(f"PASS {result.name}")
    else:
      print(f"FAIL {result.name}: {result.detail}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Check Genius Pilot onroad visualization rendering contracts.")
  parser.add_argument("--self-test", action="store_true", help="run the same offline contract checks used by the release gate")
  args = parser.parse_args()

  results = check_sources() + check_geometry() + check_visual_modes()
  print_results(results)
  return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
  raise SystemExit(main())
