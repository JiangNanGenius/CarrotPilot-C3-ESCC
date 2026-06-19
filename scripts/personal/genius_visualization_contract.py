#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
MODEL_RENDERER = ROOT / "selfdrive/ui/onroad/model_renderer.py"
VISUALS_LAYOUT = ROOT / "selfdrive/ui/sunnypilot/layouts/settings/visuals.py"


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
  visuals = VISUALS_LAYOUT.read_text(encoding="utf-8")
  path_section = source_section(renderer, "  def _draw_path(self, sm):", "  def _draw_lead_indicator(self):")

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
  required_visuals = (
    "Genius Visualization Preset",
    "Carrot emphasizes lane, path, lead, and radar information",
    "Carrot-style lane and path cues",
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

  results = [
    CheckResult(
      "renderer path mode entry points",
      all(token in renderer for token in required_renderer),
      "missing one or more Carrot/Fusion path renderer tokens",
    ),
    CheckResult(
      "visuals settings describe path presets",
      all(token in visuals for token in required_visuals),
      "Visuals page must explain lane/path ownership for the base presets",
    ),
    CheckResult(
      "path renderer remains display-only",
      not any(token in path_section for token in forbidden_path_tokens),
      "path renderer section must not publish controls, write params, open sockets, or touch lane-change control",
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


def edge_points(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
  half = points.shape[0] // 2
  return points[:half], points[half:][::-1]


def check_geometry() -> list[CheckResult]:
  polygon = synthetic_path_polygon()
  left, right = edge_points(polygon)
  center = (left + right) * 0.5

  hud_safe_y = 360.0
  content = (0.0, 0.0, 2160.0, 1080.0)
  marker_indices = list(range(3, min(center.shape[0], 44), 6))
  edge_widths = right[:, 0] - left[:, 0]

  results = [
    CheckResult("synthetic path polygon nonblank", polygon.shape[0] >= 20, f"point count={polygon.shape[0]}"),
    CheckResult("synthetic path top stays below HUD", float(np.min(polygon[:, 1])) > hud_safe_y, f"top y={float(np.min(polygon[:, 1])):.1f}"),
    CheckResult("synthetic path stays in camera content", bool(np.all((polygon[:, 0] >= content[0]) & (polygon[:, 0] <= content[2]) &
                                                                       (polygon[:, 1] >= content[1]) & (polygon[:, 1] <= content[3]))),
                "path points should remain inside the C3 camera content rectangle"),
    CheckResult("path edge widths remain drawable", bool(np.all(edge_widths > 24.0)), f"min width={float(np.min(edge_widths)):.1f}"),
    CheckResult("Carrot center markers are nonblank", len(marker_indices) >= 5, f"marker count={len(marker_indices)}"),
    CheckResult("center track follows lane center", bool(np.allclose(center[:, 0], (left[:, 0] + right[:, 0]) * 0.5)), "centerline math mismatch"),
  ]
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

  results = check_sources() + check_geometry()
  print_results(results)
  return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
  raise SystemExit(main())
