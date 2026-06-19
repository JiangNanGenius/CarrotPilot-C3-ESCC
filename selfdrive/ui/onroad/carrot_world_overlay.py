from __future__ import annotations

import numpy as np
import pyray as rl
from cereal import log

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.shader_polygon import draw_polygon
from openpilot.system.ui.widgets import Widget

CLIP_MARGIN = 500
LANE_TOP_SAFE_Y = 340.0
LANE_MAX_DISTANCE = 42.0
RADAR_MAX_DISTANCE = 95.0

EventName = log.OnroadEvent.EventName

COLOR_DIM_LANE = rl.Color(255, 255, 255, 38)
COLOR_ASSIST = rl.Color(0, 204, 0, 118)
COLOR_WARN = rl.Color(255, 203, 40, 150)
COLOR_BLOCK = rl.Color(255, 64, 52, 165)
COLOR_MODEL = rl.Color(0, 120, 255, 230)
COLOR_RADAR = rl.Color(255, 175, 3, 230)
COLOR_CLOSING = rl.Color(255, 64, 52, 235)
COLOR_OPENING = rl.Color(0, 203, 0, 230)
COLOR_TEXT = rl.Color(255, 255, 255, 240)
COLOR_BG = rl.Color(0, 0, 0, 145)


class CarrotWorldOverlay(Widget):
  """Display-only Carrot-style world evidence overlay.

  This keeps the denser Carrot lane/radar awareness separate from the base
  Sunny/Carrot/Fusion HUD preset. It reads UI state only and never writes params
  or publishes control/CAN messages.
  """

  def __init__(self):
    super().__init__()
    self._car_space_transform = np.zeros((3, 3), dtype=np.float32)
    self._clip_region: rl.Rectangle | None = None

  def set_transform(self, transform: np.ndarray) -> None:
    self._car_space_transform = transform.astype(np.float32)

  def _render(self, rect: rl.Rectangle) -> None:
    if not ui_state.genius_carrot_world_overlay:
      return

    sm = ui_state.sm
    if (sm.recv_frame["modelV2"] < ui_state.started_frame or
        sm.recv_frame["carState"] < ui_state.started_frame or
        not sm.valid["modelV2"] or not sm.valid["carState"]):
      return

    self._clip_region = rl.Rectangle(
      rect.x - CLIP_MARGIN,
      rect.y - CLIP_MARGIN,
      rect.width + 2 * CLIP_MARGIN,
      rect.height + 2 * CLIP_MARGIN,
    )

    self._draw_lane_world(rect)
    self._draw_lead_world(rect)

  def _draw_lane_world(self, rect: rl.Rectangle) -> None:
    sm = ui_state.sm
    model = sm["modelV2"]
    car_state = sm["carState"]
    position = self._model_position(model)
    if position.shape[0] == 0:
      return

    pre_left, pre_right = self._lane_change_intent()
    left_blind = bool(car_state.leftBlindspot)
    right_blind = bool(car_state.rightBlindspot)

    lane_specs = (
      ("L", -3.35, -1.75, left_blind, pre_left),
      ("R", 1.75, 3.35, right_blind, pre_right),
    )
    for side, outer_y, inner_y, blind, intent in lane_specs:
      polygon = self._build_side_lane_polygon(position, outer_y, inner_y, rect)
      if polygon.shape[0] >= 6:
        if blind:
          color = COLOR_BLOCK
        elif intent:
          color = COLOR_ASSIST
        else:
          color = COLOR_DIM_LANE
        draw_polygon(rect, polygon, color)
        self._draw_lane_edge_lines(polygon, COLOR_WARN if blind else color)

      if blind or intent:
        label = f"{side} BSM" if blind else f"{side} READY"
        self._draw_side_label(rect, side, label, COLOR_BLOCK if blind else COLOR_ASSIST)

  def _draw_lead_world(self, rect: rl.Rectangle) -> None:
    sm = ui_state.sm
    if not sm.valid["radarState"] or not sm.valid["modelV2"]:
      return

    radar_state = sm["radarState"]
    model = sm["modelV2"]
    position = self._model_position(model)
    if position.shape[0] == 0:
      return

    leads = (radar_state.leadOne, radar_state.leadTwo)
    for idx, lead in enumerate(leads):
      if not lead.status:
        continue

      d_rel = float(lead.dRel)
      if d_rel <= 2.5 or d_rel > RADAR_MAX_DISTANCE:
        continue

      screen = self._lead_screen_point(position, lead)
      if screen is None:
        continue

      speed = self._lead_speed(lead)
      color = self._lead_color(lead, speed)
      tag = f"{d_rel:.0f}m {speed:.0f}"
      if idx == 1:
        tag = f"2 {tag}"

      self._draw_radar_vector(position, lead, screen, color)
      self._draw_tag(screen[0], screen[1], tag, color)

  @staticmethod
  def _model_position(model) -> np.ndarray:
    if len(model.position.x) == 0:
      return np.empty((0, 3), dtype=np.float32)
    return np.array([model.position.x, model.position.y, model.position.z], dtype=np.float32).T

  def _lane_change_intent(self) -> tuple[bool, bool]:
    events = ui_state.sm["onroadEvents"]
    left = any(e.name == EventName.preLaneChangeLeft for e in events)
    right = any(e.name == EventName.preLaneChangeRight for e in events)
    return left, right

  def _build_side_lane_polygon(self, position: np.ndarray, outer_y: float, inner_y: float, rect: rl.Rectangle) -> np.ndarray:
    max_idx = self._path_index(position[:, 0], LANE_MAX_DISTANCE)
    left_points: list[tuple[float, float]] = []
    right_points: list[tuple[float, float]] = []
    top_y = rect.y + LANE_TOP_SAFE_Y

    for i in range(0, max_idx + 1):
      x = float(position[i, 0])
      if x < 0.0:
        continue

      base_y = float(position[i, 1])
      z = float(position[i, 2])
      outer = self._map_to_screen(x, base_y + outer_y, z + 0.62)
      inner = self._map_to_screen(x, base_y + inner_y, z + 0.98)
      if outer is None or inner is None:
        continue
      if outer[1] < top_y or inner[1] < top_y:
        continue

      left_points.append(outer)
      right_points.insert(0, inner)

    if len(left_points) < 3 or len(right_points) < 3:
      return np.empty((0, 2), dtype=np.float32)
    return np.array(left_points + right_points, dtype=np.float32)

  def _draw_lane_edge_lines(self, polygon: np.ndarray, color: rl.Color) -> None:
    half = polygon.shape[0] // 2
    if half < 2:
      return
    outer = polygon[:half]
    inner = polygon[half:][::-1]
    line_color = rl.Color(color.r, color.g, color.b, min(235, color.a + 55))
    self._draw_polyline(outer, 2.0, line_color, stride=2)
    self._draw_polyline(inner, 2.0, line_color, stride=2)

  def _draw_side_label(self, rect: rl.Rectangle, side: str, text: str, color: rl.Color) -> None:
    font_size = 25
    text_w = rl.measure_text(text, font_size)
    pad_x = 16
    box_w = text_w + pad_x * 2
    box_h = 42
    x = rect.x + 52 if side == "L" else rect.x + rect.width - 52 - box_w
    y = rect.y + rect.height * 0.56
    self._draw_rect_label(x, y, box_w, box_h, text, font_size, color)

  def _lead_screen_point(self, position: np.ndarray, lead) -> tuple[float, float] | None:
    d_rel = float(lead.dRel)
    idx = self._path_index(position[:, 0], d_rel)
    z = float(position[idx, 2]) if idx < position.shape[0] else 0.0
    return self._map_to_screen(d_rel, -float(lead.yRel), z + 0.65)

  def _draw_radar_vector(self, position: np.ndarray, lead, start: tuple[float, float], color: rl.Color) -> None:
    v_long = float(lead.vLeadK)
    if abs(v_long) < 0.01:
      v_long = float(lead.vRel) + float(ui_state.sm["carState"].vEgo)
    v_lat = float(lead.vLat)
    if abs(v_long) < 2.0 and abs(v_lat) < 0.5:
      return

    d_future = max(2.0, float(lead.dRel) + v_long * 1.2)
    idx = self._path_index(position[:, 0], min(d_future, RADAR_MAX_DISTANCE))
    z = float(position[idx, 2]) if idx < position.shape[0] else 0.0
    end = self._map_to_screen(d_future, -(float(lead.yRel) + v_lat * 1.2), z + 0.65)
    if end is None:
      return

    rl.draw_line_ex(rl.Vector2(float(start[0]), float(start[1])), rl.Vector2(float(end[0]), float(end[1])), 3.0, color)
    rl.draw_circle_v(rl.Vector2(float(end[0]), float(end[1])), 8.0, color)

  def _draw_tag(self, x: float, y: float, text: str, color: rl.Color) -> None:
    font_size = 25
    text_w = rl.measure_text(text, font_size)
    box_w = max(72, text_w + 18)
    box_h = 38
    box_x = x - box_w / 2
    box_y = y - box_h - 12
    self._draw_rect_label(box_x, box_y, box_w, box_h, text, font_size, color)

  @staticmethod
  def _lead_speed(lead) -> float:
    v_long = float(lead.vLeadK)
    if abs(v_long) < 0.01:
      v_long = float(lead.vRel) + float(ui_state.sm["carState"].vEgo)
    v_lat = float(lead.vLat)
    v_abs = float(np.sqrt(v_long * v_long + v_lat * v_lat))
    signed = v_abs if v_long >= 0.0 else -v_abs
    return signed * (3.6 if ui_state.is_metric else 2.2369363)

  @staticmethod
  def _lead_color(lead, speed: float) -> rl.Color:
    if not bool(lead.radar):
      return COLOR_MODEL
    if float(lead.vRel) < -2.0:
      return COLOR_CLOSING
    if speed > 3.0:
      return COLOR_OPENING
    return COLOR_RADAR

  def _map_to_screen(self, in_x: float, in_y: float, in_z: float) -> tuple[float, float] | None:
    input_pt = np.array([in_x, in_y, in_z], dtype=np.float32)
    pt = self._car_space_transform @ input_pt
    if abs(float(pt[2])) < 1e-6:
      return None

    x = float(pt[0] / pt[2])
    y = float(pt[1] / pt[2])
    clip = self._clip_region
    if clip is None:
      return None
    if not (clip.x <= x <= clip.x + clip.width and clip.y <= y <= clip.y + clip.height):
      return None
    return x, y

  @staticmethod
  def _path_index(pos_x_array: np.ndarray, path_distance: float) -> int:
    if len(pos_x_array) == 0:
      return 0
    indices = np.where(pos_x_array <= path_distance)[0]
    return int(indices[-1]) if indices.size > 0 else 0

  @staticmethod
  def _draw_polyline(points: np.ndarray, thickness: float, color: rl.Color, stride: int = 1) -> None:
    for i in range(0, points.shape[0] - 1, stride):
      p0 = rl.Vector2(float(points[i, 0]), float(points[i, 1]))
      p1 = rl.Vector2(float(points[i + 1, 0]), float(points[i + 1, 1]))
      rl.draw_line_ex(p0, p1, thickness, color)

  @staticmethod
  def _draw_rect_label(x: float, y: float, w: float, h: float, text: str, font_size: int, color: rl.Color) -> None:
    rect = rl.Rectangle(float(x), float(y), float(w), float(h))
    rl.draw_rectangle_rounded(rect, 0.24, 8, COLOR_BG)
    rl.draw_rectangle_rounded_lines_ex(rect, 0.24, 8, 3, color)
    text_w = rl.measure_text(text, font_size)
    rl.draw_text(text, int(x + (w - text_w) / 2), int(y + (h - font_size) / 2), font_size, COLOR_TEXT)
