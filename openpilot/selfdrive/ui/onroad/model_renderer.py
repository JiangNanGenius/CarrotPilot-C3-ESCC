import colorsys
import numpy as np
import pyray as rl
from openpilot.cereal import messaging
from opendbc.car.structs import car
from dataclasses import dataclass, field
from typing import Any
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.selfdrive.locationd.calibrationd import HEIGHT_INIT
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.selfdrive.ui.mici.onroad import blend_colors
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.shader_polygon import draw_polygon, Gradient
from openpilot.system.ui.widgets import Widget

from openpilot.selfdrive.ui.sunnypilot.onroad.model_renderer import ChevronMetrics, ModelRendererSP

CLIP_MARGIN = 500
MIN_DRAW_DISTANCE = 10.0
MAX_DRAW_DISTANCE = 100.0

THROTTLE_COLORS = [
  rl.Color(13, 248, 122, 102),   # HSLF(148/360, 0.94, 0.51, 0.4)
  rl.Color(114, 255, 92, 89),    # HSLF(112/360, 1.0, 0.68, 0.35)
  rl.Color(114, 255, 92, 0),     # HSLF(112/360, 1.0, 0.68, 0.0)
]

NO_THROTTLE_COLORS = [
  rl.Color(242, 242, 242, 102), # HSLF(148/360, 0.0, 0.95, 0.4)
  rl.Color(242, 242, 242, 89),  # HSLF(112/360, 0.0, 0.95, 0.35)
  rl.Color(242, 242, 242, 0),   # HSLF(112/360, 0.0, 0.95, 0.0)
]

CARROT_PATH_ACTIVE_COLORS = [
  rl.Color(0, 202, 255, 112),
  rl.Color(31, 255, 134, 92),
  rl.Color(31, 255, 134, 0),
]

CARROT_PATH_LIMITED_COLORS = [
  rl.Color(255, 122, 0, 118),
  rl.Color(255, 62, 52, 96),
  rl.Color(255, 62, 52, 0),
]

LANE_LINE_COLORS = {
  UIStatus.DISENGAGED: rl.Color(200, 200, 200, 255),
  UIStatus.OVERRIDE: rl.Color(255, 255, 255, 255),
  UIStatus.ENGAGED: rl.Color(0, 255, 64, 255),
  UIStatus.LAT_ONLY: rl.Color(0, 255, 64, 255),
  UIStatus.LONG_ONLY: rl.Color(0, 255, 64, 255),
}


@dataclass
class ModelPoints:
  raw_points: np.ndarray = field(default_factory=lambda: np.empty((0, 3), dtype=np.float32))
  projected_points: np.ndarray = field(default_factory=lambda: np.empty((0, 2), dtype=np.float32))


@dataclass
class LeadVehicle:
  glow: list[tuple[float, float]] = field(default_factory=list)
  chevron: list[tuple[float, float]] = field(default_factory=list)
  fill_alpha: int = 0
  rect: list[tuple[float, float]] = field(default_factory=list)
  color: Any | None = None
  tag: str = ""


@dataclass
class RadarInfoItem:
  x: float = 0.0
  y: float = 0.0
  w: float = 0.0
  h: float = 0.0
  text: str = ""
  color: Any | None = None
  is_star: bool = False


class ModelRenderer(Widget, ChevronMetrics, ModelRendererSP):
  def __init__(self):
    Widget.__init__(self)
    ChevronMetrics.__init__(self)
    ModelRendererSP.__init__(self)
    self._longitudinal_control = False
    self._experimental_mode = False
    self._blend_filter = FirstOrderFilter(1.0, 0.25, 1 / gui_app.target_fps)
    self._prev_allow_throttle = True
    self._torque_filter = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)
    self._lane_line_probs = np.zeros(4, dtype=np.float32)
    self._road_edge_stds = np.zeros(2, dtype=np.float32)
    self._lead_vehicles = [LeadVehicle(), LeadVehicle()]
    self._lead_pt_filt: list[tuple[float, float] | None] = [None, None]
    self._radar_info_items: list[RadarInfoItem] = []
    self._path_offset_z = HEIGHT_INIT[0]
    self._counter = -1
    self._camera_offset = ui_state.params.get("CameraOffset", return_default=True) if ui_state.active_bundle else 0.0
    # Initialize ModelPoints objects
    self._path = ModelPoints()
    self._lane_lines = [ModelPoints() for _ in range(4)]
    self._road_edges = [ModelPoints() for _ in range(2)]
    self._acceleration_x = np.empty((0,), dtype=np.float32)

    # Transform matrix (3x3 for car space to screen space)
    self._car_space_transform = np.zeros((3, 3), dtype=np.float32)
    self._transform_dirty = True
    self._clip_region = None

    self._exp_gradient = Gradient(
      start=(0.0, 1.0),  # Bottom of path
      end=(0.0, 0.0),  # Top of path
      colors=[],
      stops=[],
    )

    # Get longitudinal control setting from car parameters
    if car_params := Params().get("CarParams"):
      cp = messaging.log_from_bytes(car_params, car.CarParams)
      self._longitudinal_control = cp.openpilotLongitudinalControl

  def set_transform(self, transform: np.ndarray):
    self._car_space_transform = transform.astype(np.float32)
    self._transform_dirty = True

  def _render(self, rect: rl.Rectangle):
    sm = ui_state.sm
    self._torque_filter.update(-ui_state.sm['carOutput'].actuatorsOutput.torque)

    # Check if data is up-to-date
    if (sm.recv_frame["extrinsicsCalibration"] < ui_state.started_frame or
        sm.recv_frame["modelV2"] < ui_state.started_frame):
      return

    # Set up clipping region
    self._clip_region = rl.Rectangle(
      rect.x - CLIP_MARGIN, rect.y - CLIP_MARGIN, rect.width + 2 * CLIP_MARGIN, rect.height + 2 * CLIP_MARGIN
    )

    # Update state
    self._experimental_mode = sm['selfdriveState'].experimentalMode

    extrinsics_calibration = sm['extrinsicsCalibration']
    self._path_offset_z = extrinsics_calibration.height[0] if extrinsics_calibration.height else HEIGHT_INIT[0]

    if self._counter % 60 == 0:
      self._camera_offset = ui_state.params.get("CameraOffset", return_default=True) if ui_state.active_bundle else 0.0
    self._counter += 1

    if sm.updated['carParams']:
      self._longitudinal_control = sm['carParams'].openpilotLongitudinalControl

    model = sm['modelV2']
    radar_state = sm['radarState'] if sm.valid['radarState'] else None
    lead_one = radar_state.leadOne if radar_state else None
    render_lead_indicator = self._longitudinal_control and radar_state is not None

    # Update model data when needed
    model_updated = sm.updated['modelV2']
    if model_updated or sm.updated['radarState'] or self._transform_dirty:
      if model_updated:
        self._update_raw_points(model)

      path_x_array = self._path.raw_points[:, 0]
      if path_x_array.size == 0:
        return

      self._update_model(lead_one, path_x_array)
      if render_lead_indicator:
        if ui_state.genius_lead_radar_visual_mode > 0:
          self._update_leads_carrot(radar_state, path_x_array)
        else:
          self._update_leads(radar_state, path_x_array)
        if ui_state.genius_lead_radar_visual_mode >= 2:
          self._update_radar_info(radar_state, path_x_array)
        else:
          self._radar_info_items = []
      self._transform_dirty = False

    # Draw elements
    self._draw_lane_lines()
    self._draw_path(sm)

    if render_lead_indicator and radar_state:
      self._draw_lead_indicator()
      if ui_state.genius_lead_radar_visual_mode == 0:
        self.chevron_metrics.draw_lead_status(sm, radar_state, self._rect, self._lead_vehicles)
      elif ui_state.genius_lead_radar_visual_mode >= 2:
        self._draw_radar_info()

  def _update_raw_points(self, model):
    """Update raw 3D points from model data"""
    self._path.raw_points = np.array([model.position.x, np.array(model.position.y) + self._camera_offset, model.position.z], dtype=np.float32).T

    for i, lane_line in enumerate(model.laneLines):
      self._lane_lines[i].raw_points = np.array([lane_line.x, np.array(lane_line.y) + self._camera_offset, lane_line.z], dtype=np.float32).T

    for i, road_edge in enumerate(model.roadEdges):
      self._road_edges[i].raw_points = np.array([road_edge.x, np.array(road_edge.y) + self._camera_offset, road_edge.z], dtype=np.float32).T

    self._lane_line_probs = np.array(model.laneLineProbs, dtype=np.float32)
    self._road_edge_stds = np.array(model.roadEdgeStds, dtype=np.float32)
    self._acceleration_x = np.array(model.acceleration.x, dtype=np.float32)

  def _update_leads(self, radar_state, path_x_array):
    """Update positions of lead vehicles"""
    self._lead_vehicles = [LeadVehicle(), LeadVehicle()]
    leads = [radar_state.leadOne, radar_state.leadTwo]

    for i, lead_data in enumerate(leads):
      if lead_data and lead_data.present:
        d_rel, y_rel, v_rel = lead_data.dRel, lead_data.yRel, lead_data.vRel
        idx = self._get_path_length_idx(path_x_array, d_rel)

        # Get z-coordinate from path at the lead vehicle position
        z = self._path.raw_points[idx, 2] if idx < len(self._path.raw_points) else 0.0
        point = self._map_to_screen(d_rel, -y_rel + self._camera_offset, z + self._path_offset_z)
        if point:
          self._lead_vehicles[i] = self._update_lead_vehicle(d_rel, v_rel, point, self._rect)

  def _update_leads_carrot(self, radar_state, path_x_array):
    """Draw leads as Carrot-style outline boxes, without changing planner behavior."""
    self._lead_vehicles = [LeadVehicle(), LeadVehicle()]
    leads = [radar_state.leadOne, radar_state.leadTwo]

    for i, lead_data in enumerate(leads):
      if not lead_data or not lead_data.status:
        self._lead_pt_filt[i] = None
        continue

      d_rel = float(lead_data.dRel)
      y_rel = float(lead_data.yRel)
      idx = self._get_path_length_idx(path_x_array, d_rel)
      z = float(self._path.raw_points[idx, 2]) if idx < len(self._path.raw_points) else 0.0

      pt_left = self._map_to_screen(d_rel, -y_rel - 1.2 + self._camera_offset, z + self._path_offset_z)
      pt_right = self._map_to_screen(d_rel, -y_rel + 1.2 + self._camera_offset, z + self._path_offset_z)
      if not pt_left or not pt_right:
        self._lead_pt_filt[i] = None
        continue

      center = ((pt_left[0] + pt_right[0]) * 0.5, (pt_left[1] + pt_right[1]) * 0.5)
      filtered = self._filter_lead_point(i, center)
      path_width = float(np.clip(abs(pt_right[0] - pt_left[0]), 52.0, 360.0))

      half_w = path_width * 0.5
      rect_h = path_width * 0.8
      left = float(np.clip(filtered[0] - half_w, self._rect.x, self._rect.x + self._rect.width))
      right = float(np.clip(filtered[0] + half_w, self._rect.x, self._rect.x + self._rect.width))
      bottom = float(np.clip(filtered[1], self._rect.y, self._rect.y + self._rect.height))
      top = float(np.clip(filtered[1] - rect_h, self._rect.y, self._rect.y + self._rect.height))

      if not bool(getattr(lead_data, "radar", False)):
        color = rl.Color(0, 120, 255, 255)
      elif int(getattr(lead_data, "radarTrackId", -1)) in (0, 1):
        color = rl.Color(201, 34, 49, 255)
      else:
        color = rl.Color(255, 115, 0, 255)

      tag = self._lead_speed_tag(lead_data)
      self._lead_vehicles[i] = LeadVehicle(
        rect=[(left, top), (right, top), (right, bottom), (left, bottom)],
        color=color,
        tag=tag,
      )

  def _filter_lead_point(self, slot: int, point: tuple[float, float], alpha: float = 0.2) -> tuple[float, float]:
    prev = self._lead_pt_filt[slot]
    if prev is None:
      filtered = (float(point[0]), float(point[1]))
      self._lead_pt_filt[slot] = filtered
      return filtered

    x = prev[0] + (float(point[0]) - prev[0]) * alpha
    y = prev[1] + (float(point[1]) - prev[1]) * alpha
    self._lead_pt_filt[slot] = (x, y)
    return x, y

  def _lead_speed_tag(self, lead_data) -> str:
    v_abs = float(getattr(lead_data, "vLeadK", 0.0))
    if abs(v_abs) < 0.01:
      v_abs = float(getattr(lead_data, "vRel", 0.0)) + float(ui_state.sm["carState"].vEgo)
    speed = v_abs * (3.6 if ui_state.is_metric else 2.2369363)
    return f"{speed:.0f}"

  def _update_model(self, lead, path_x_array):
    """Update model visualization data based on model message"""
    max_distance = np.clip(path_x_array[-1], MIN_DRAW_DISTANCE, MAX_DRAW_DISTANCE)
    max_idx = self._get_path_length_idx(self._lane_lines[0].raw_points[:, 0], max_distance)

    # Update lane lines using raw points
    for i, lane_line in enumerate(self._lane_lines):
      line_width_factor = 0.025
      if ui_state.genius_lane_line_style >= 2 and i in (1, 2):
        line_width_factor = 0.045
      lane_line.projected_points = self._map_line_to_polygon(
        lane_line.raw_points, line_width_factor * self._lane_line_probs[i], 0.0, max_idx, max_distance
      )

    # Update road edges using raw points
    for road_edge in self._road_edges:
      road_edge.projected_points = self._map_line_to_polygon(road_edge.raw_points, 0.025, 0.0, max_idx, max_distance)

    # Update path using raw points
    if lead and lead.present:
      lead_d = lead.dRel * 2.0
      max_distance = np.clip(lead_d - min(lead_d * 0.35, 10.0), 0.0, max_distance)

    max_idx = self._get_path_length_idx(path_x_array, max_distance)
    self._path.projected_points = self._map_line_to_polygon(
      self._path.raw_points, 0.9, self._path_offset_z, max_idx, max_distance, allow_invert=False
    )

    self._update_experimental_gradient()

  def _update_experimental_gradient(self):
    """Pre-calculate experimental mode gradient colors"""
    if not self._experimental_mode:
      return

    max_len = min(len(self._path.projected_points) // 2, len(self._acceleration_x))

    segment_colors = []
    gradient_stops = []

    i = 0
    while i < max_len:
      # Some points (screen space) are out of frame (rect space)
      track_y = self._path.projected_points[i][1]
      if track_y < self._rect.y or track_y > (self._rect.y + self._rect.height):
        i += 1
        continue

      # Calculate color based on acceleration (0 is bottom, 1 is top)
      lin_grad_point = 1 - (track_y - self._rect.y) / self._rect.height

      # speed up: 120, slow down: 0
      path_hue = np.clip(60 + self._acceleration_x[i] * 35, 0, 120)

      saturation = min(abs(self._acceleration_x[i] * 1.5), 1)
      lightness = np.interp(saturation, [0.0, 1.0], [0.95, 0.62])
      alpha = np.interp(lin_grad_point, [0.75 / 2.0, 0.75], [0.4, 0.0])

      # Use HSL to RGB conversion
      color = self._hsla_to_color(path_hue / 360.0, saturation, lightness, alpha)

      gradient_stops.append(lin_grad_point)
      segment_colors.append(color)

      # Skip a point, unless next is last
      i += 1 + (1 if (i + 2) < max_len else 0)

    # Store the gradient in the path object
    self._exp_gradient = Gradient(
      start=(0.0, 1.0),  # Bottom of path
      end=(0.0, 0.0),  # Top of path
      colors=segment_colors,
      stops=gradient_stops,
    )

  def _update_lead_vehicle(self, d_rel, v_rel, point, rect):
    speed_buff, lead_buff = 10.0, 40.0

    # Calculate fill alpha
    fill_alpha = 0
    if d_rel < lead_buff:
      fill_alpha = 255 * (1.0 - (d_rel / lead_buff))
      if v_rel < 0:
        fill_alpha += 255 * (-1 * (v_rel / speed_buff))
      fill_alpha = min(fill_alpha, 255)

    # Calculate size and position
    sz = np.clip((25 * 30) / (d_rel / 3 + 30), 15.0, 30.0) * 2.35
    x = np.clip(point[0], 0.0, rect.width - sz / 2)
    y = min(point[1], rect.height - sz * 0.6)

    g_xo = sz / 5
    g_yo = sz / 10

    glow = [(x + (sz * 1.35) + g_xo, y + sz + g_yo), (x, y - g_yo), (x - (sz * 1.35) - g_xo, y + sz + g_yo)]
    chevron = [(x + (sz * 1.25), y + sz), (x, y), (x - (sz * 1.25), y + sz)]

    return LeadVehicle(glow=glow, chevron=chevron, fill_alpha=int(fill_alpha))

  def _get_lane_line_color(self, prob: float, adjacent: bool, left: bool) -> rl.Color:
    alpha = np.clip(prob, 0.0, 0.7)

    if ui_state.genius_lane_line_style <= 0:
      return rl.Color(255, 255, 255, int(alpha * 255))

    if adjacent:
      base = LANE_LINE_COLORS.get(ui_state.status, LANE_LINE_COLORS[UIStatus.DISENGAGED])
      color = rl.Color(base.r, base.g, base.b, int(alpha * 255))

      if ui_state.genius_lane_line_style >= 2:
        torque = float(self._torque_filter.x)
        if abs(torque) > 0.6 and (left == (torque > 0)):
          color = blend_colors(
            color,
            rl.Color(255, 115, 0, int(alpha * 255)),
            float(np.interp(abs(torque), [0.6, 0.85], [0.0, 1.0])),
          )
    else:
      color = rl.Color(255, 255, 255, int(alpha * 255))

    if ui_state.status == UIStatus.DISENGAGED and not ui_state.sm["carControl"].latActive:
      return rl.Color(0, 0, 0, int(alpha * 255))

    return color

  def _draw_lane_lines(self):
    """Draw lane lines and road edges"""
    for i, lane_line in enumerate(self._lane_lines):
      if lane_line.projected_points.size == 0:
        continue

      color = self._get_lane_line_color(float(self._lane_line_probs[i]), i in (1, 2), i in (0, 1))
      draw_polygon(self._rect, lane_line.projected_points, color)

    for i, road_edge in enumerate(self._road_edges):
      if road_edge.projected_points.size == 0:
        continue

      alpha = np.clip(1.0 - self._road_edge_stds[i], 0.0, 1.0)
      if ui_state.genius_lane_line_style > 0:
        color = self._get_lane_line_color(float(alpha), float(self._lane_line_probs[i + 1]) < 0.25, i == 0)
      else:
        color = rl.Color(255, 0, 0, int(alpha * 255))
      draw_polygon(self._rect, road_edge.projected_points, color)

  def _draw_path(self, sm):
    """Draw path with dynamic coloring based on mode and throttle state."""
    if not self._path.projected_points.size:
      return

    allow_throttle = sm['longitudinalPlan'].allowThrottle or not self._longitudinal_control
    self._blend_filter.update(int(allow_throttle))

    if ui_state.rainbow_path:
      self.rainbow_path.draw_rainbow_path(self._rect, self._path)
      return

    if ui_state.genius_visual_mode == 1:
      self._draw_path_carrot()
      return

    if ui_state.genius_visual_mode == 2:
      self._draw_path_fusion()
      return

    self._draw_path_sunny()

  def _draw_path_sunny(self):
    if self._experimental_mode:
      # Draw with acceleration coloring
      if len(self._exp_gradient.colors) > 1:
        draw_polygon(self._rect, self._path.projected_points, gradient=self._exp_gradient)
      else:
        draw_polygon(self._rect, self._path.projected_points, rl.Color(255, 255, 255, 30))
    else:
      # Blend throttle/no throttle colors based on transition
      blend_factor = round(self._blend_filter.x * 100) / 100
      blended_colors = self._blend_colors(NO_THROTTLE_COLORS, THROTTLE_COLORS, blend_factor)
      gradient = Gradient(
        start=(0.0, 1.0),  # Bottom of path
        end=(0.0, 0.0),  # Top of path
        colors=blended_colors,
        stops=[0.0, 0.5, 1.0],
      )
      draw_polygon(self._rect, self._path.projected_points, gradient=gradient)

  def _draw_path_carrot(self):
    """Draw a denser Carrot-style route ribbon without changing the planner path."""
    blend_factor = round(self._blend_filter.x * 100) / 100
    blended_colors = self._blend_colors(CARROT_PATH_LIMITED_COLORS, CARROT_PATH_ACTIVE_COLORS, blend_factor)
    gradient = Gradient(
      start=(0.0, 1.0),
      end=(0.0, 0.0),
      colors=blended_colors,
      stops=[0.0, 0.56, 1.0],
    )
    draw_polygon(self._rect, self._path.projected_points, gradient=gradient)
    self._draw_path_edges(rl.Color(0, 245, 255, 160), rl.Color(255, 255, 255, 92), 4.0)
    self._draw_carrot_path_markers(rl.Color(255, 255, 255, 150))

  def _draw_path_fusion(self):
    """Keep the Sunny path body and add a light Carrot track cue."""
    self._draw_path_sunny()
    self._draw_path_edges(rl.Color(0, 245, 255, 118), rl.Color(255, 255, 255, 72), 2.8)

  def _path_edge_points(self) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    points = self._path.projected_points
    if points.shape[0] < 4:
      return None, None
    half = points.shape[0] // 2
    left = points[:half]
    right = points[half:][::-1]
    if left.shape[0] < 2 or right.shape[0] < 2:
      return None, None
    return left, right

  def _draw_path_edges(self, edge_color: rl.Color, center_color: rl.Color, thickness: float):
    edge_points = self._path_edge_points()
    if edge_points[0] is None or edge_points[1] is None:
      return

    left, right = edge_points
    self._draw_polyline(left, thickness, edge_color)
    self._draw_polyline(right, thickness, edge_color)
    center = (left + right) * 0.5
    self._draw_polyline(center, max(1.8, thickness * 0.45), center_color, stride=2)

  def _draw_carrot_path_markers(self, color: rl.Color):
    edge_points = self._path_edge_points()
    if edge_points[0] is None or edge_points[1] is None:
      return

    left, right = edge_points
    center = (left + right) * 0.5
    phase = max(0, self._counter // 3) % 6
    max_markers = min(center.shape[0], 44)
    for i in range(3 + phase, max_markers, 6):
      radius = float(np.clip(9.0 - i * 0.11, 3.0, 9.0))
      rl.draw_circle_v(rl.Vector2(float(center[i, 0]), float(center[i, 1])), radius, color)

  @staticmethod
  def _draw_polyline(points: np.ndarray, thickness: float, color: rl.Color, stride: int = 1):
    for i in range(0, points.shape[0] - 1, stride):
      p0 = (float(points[i, 0]), float(points[i, 1]))
      p1 = (float(points[i + 1, 0]), float(points[i + 1, 1]))
      rl.draw_line_ex(p0, p1, thickness, color)

  def _draw_lead_indicator(self):
    # Draw lead vehicles if available
    for lead in self._lead_vehicles:
      if lead.rect and lead.color is not None:
        self._draw_lead_rect(lead)
        continue

      if not lead.glow or not lead.chevron:
        continue

      rl.draw_triangle_fan(lead.glow, len(lead.glow), rl.Color(218, 202, 37, 255))
      rl.draw_triangle_fan(lead.chevron, len(lead.chevron), rl.Color(201, 34, 49, lead.fill_alpha))

  def _draw_lead_rect(self, lead: LeadVehicle):
    pts = lead.rect
    color = lead.color
    thickness = 4.0
    rl.draw_line_ex(pts[0], pts[1], thickness, color)
    rl.draw_line_ex(pts[1], pts[2], thickness, color)
    rl.draw_line_ex(pts[2], pts[3], thickness, color)
    rl.draw_line_ex(pts[3], pts[0], thickness, color)

    if lead.tag and ui_state.genius_lead_radar_visual_mode >= 2:
      text_size = 28
      text_w = rl.measure_text(lead.tag, text_size)
      box_w = text_w + 18
      box_h = text_size + 8
      x = int((pts[0][0] + pts[1][0]) * 0.5 - box_w * 0.5)
      y = int(pts[0][1] - box_h - 6)
      rl.draw_rectangle_rounded(rl.Rectangle(x, y, box_w, box_h), 0.24, 8, rl.Color(color.r, color.g, color.b, 220))
      rl.draw_text(lead.tag, int(x + (box_w - text_w) / 2), int(y + 3), text_size, rl.WHITE)

  def _get_radar_info_color(self, lead_data, speed: float) -> rl.Color:
    if not bool(getattr(lead_data, "radar", False)):
      return rl.Color(0, 120, 255, 220)
    if abs(float(getattr(lead_data, "modelProb", 0.0)) - 0.01) < 0.001:
      return rl.Color(0, 203, 0, 220)
    if speed > 0.0:
      return rl.Color(255, 175, 3, 220)
    return rl.Color(255, 0, 0, 220)

  def _update_radar_info(self, radar_state, path_x_array):
    self._radar_info_items = []
    leads = [radar_state.leadOne, radar_state.leadTwo]

    for lead_data in leads:
      if not lead_data or not lead_data.status:
        continue

      d_rel = float(getattr(lead_data, "dRel", 0.0))
      if d_rel <= 2.5:
        continue

      idx = self._get_path_length_idx(path_x_array, d_rel)
      z = float(self._path.raw_points[idx, 2]) - 0.61 if idx < len(self._path.raw_points) else 0.0
      point = self._map_to_screen(d_rel, -float(getattr(lead_data, "yRel", 0.0)) + self._camera_offset, z + self._path_offset_z)
      if not point:
        continue

      v_long = float(getattr(lead_data, "vLeadK", 0.0))
      if abs(v_long) < 0.01:
        v_long = float(getattr(lead_data, "vRel", 0.0)) + float(ui_state.sm["carState"].vEgo)
      v_lat = float(getattr(lead_data, "vLat", 0.0))
      v_abs = float(np.sqrt(v_long * v_long + v_lat * v_lat))
      v_sum = v_abs if v_long >= 0.0 else -v_abs

      if v_abs <= 3.0:
        self._radar_info_items.append(
          RadarInfoItem(x=float(point[0]), y=float(point[1]), text="*", color=rl.Color(255, 255, 255, 230), is_star=True)
        )
        continue

      speed_value = v_sum * (3.6 if ui_state.is_metric else 2.2369363)
      text = f"{speed_value:.0f}"
      font_size = 24
      pad_x = 6
      pad_y = 2
      text_w = rl.measure_text(text, font_size)
      box_w = float(text_w + pad_x * 2)
      box_h = float(font_size + pad_y * 2)
      box_x = float(np.clip(point[0] - box_w * 0.5, self._rect.x, self._rect.x + self._rect.width - box_w))
      box_y = float(np.clip(point[1] - box_h * 0.5, self._rect.y, self._rect.y + self._rect.height - box_h))
      self._radar_info_items.append(
        RadarInfoItem(x=box_x, y=box_y, w=box_w, h=box_h, text=text, color=self._get_radar_info_color(lead_data, v_sum))
      )

  def _draw_radar_info(self):
    for item in self._radar_info_items:
      if item.color is None:
        continue

      font_size = 24
      if item.is_star:
        rl.draw_text(item.text, int(item.x), int(item.y), font_size, item.color)
        continue

      rl.draw_rectangle_rounded(rl.Rectangle(item.x, item.y, item.w, item.h), 0.28, 8, item.color)
      text_w = rl.measure_text(item.text, font_size)
      rl.draw_text(item.text, int(item.x + (item.w - text_w) / 2), int(item.y + (item.h - font_size) / 2), font_size, rl.WHITE)

  @staticmethod
  def _get_path_length_idx(pos_x_array: np.ndarray, path_distance: float) -> int:
    """Get the index corresponding to the given path distance"""
    if len(pos_x_array) == 0:
      return 0
    indices = np.where(pos_x_array <= path_distance)[0]
    return indices[-1] if indices.size > 0 else 0

  def _map_to_screen(self, in_x, in_y, in_z):
    """Project a point in car space to screen space"""
    input_pt = np.array([in_x, in_y, in_z])
    pt = self._car_space_transform @ input_pt

    if abs(pt[2]) < 1e-6:
      return None

    x, y = pt[0] / pt[2], pt[1] / pt[2]

    clip = self._clip_region
    if not (clip.x <= x <= clip.x + clip.width and clip.y <= y <= clip.y + clip.height):
      return None

    return (x, y)

  def _map_line_to_polygon(self, line: np.ndarray, y_off: float, z_off: float, max_idx: int, max_distance: float, allow_invert: bool = True) -> np.ndarray:
    """Convert 3D line to 2D polygon for rendering."""
    if line.shape[0] == 0:
      return np.empty((0, 2), dtype=np.float32)

    # Slice points and filter non-negative x-coordinates
    points = line[:max_idx + 1]

    # Interpolate around max_idx so path end is smooth (max_distance is always >= p0.x)
    if 0 < max_idx < line.shape[0] - 1:
      p0 = line[max_idx]
      p1 = line[max_idx + 1]
      x0, x1 = p0[0], p1[0]
      interp_y = np.interp(max_distance, [x0, x1], [p0[1], p1[1]])
      interp_z = np.interp(max_distance, [x0, x1], [p0[2], p1[2]])
      interp_point = np.array([max_distance, interp_y, interp_z], dtype=points.dtype)
      points = np.concatenate((points, interp_point[None, :]), axis=0)

    points = points[points[:, 0] >= 0]
    if points.shape[0] == 0:
      return np.empty((0, 2), dtype=np.float32)

    N = points.shape[0]
    # Generate left and right 3D points in one array using broadcasting
    offsets = np.array([[0, -y_off, z_off], [0, y_off, z_off]], dtype=np.float32)
    points_3d = points[None, :, :] + offsets[:, None, :]  # Shape: 2xNx3
    points_3d = points_3d.reshape(2 * N, 3)  # Shape: (2*N)x3

    # Transform all points to projected space in one operation
    proj = self._car_space_transform @ points_3d.T  # Shape: 3x(2*N)
    proj = proj.reshape(3, 2, N)
    left_proj = proj[:, 0, :]
    right_proj = proj[:, 1, :]

    # Filter points where z is sufficiently large
    valid_proj = (np.abs(left_proj[2]) >= 1e-6) & (np.abs(right_proj[2]) >= 1e-6)
    if not np.any(valid_proj):
      return np.empty((0, 2), dtype=np.float32)

    # Compute screen coordinates
    left_screen = left_proj[:2, valid_proj] / left_proj[2, valid_proj][None, :]
    right_screen = right_proj[:2, valid_proj] / right_proj[2, valid_proj][None, :]

    # Define clip region bounds
    clip = self._clip_region
    x_min, x_max = clip.x, clip.x + clip.width
    y_min, y_max = clip.y, clip.y + clip.height

    # Filter points within clip region
    left_in_clip = (
      (left_screen[0] >= x_min) & (left_screen[0] <= x_max) &
      (left_screen[1] >= y_min) & (left_screen[1] <= y_max)
    )
    right_in_clip = (
      (right_screen[0] >= x_min) & (right_screen[0] <= x_max) &
      (right_screen[1] >= y_min) & (right_screen[1] <= y_max)
    )
    both_in_clip = left_in_clip & right_in_clip

    if not np.any(both_in_clip):
      return np.empty((0, 2), dtype=np.float32)

    # Select valid and clipped points
    left_screen = left_screen[:, both_in_clip]
    right_screen = right_screen[:, both_in_clip]

    # Handle Y-coordinate inversion on hills
    if not allow_invert and left_screen.shape[1] > 1:
      y = left_screen[1, :]  # y-coordinates
      keep = y == np.minimum.accumulate(y)
      if not np.any(keep):
        return np.empty((0, 2), dtype=np.float32)
      left_screen = left_screen[:, keep]
      right_screen = right_screen[:, keep]

    return np.vstack((left_screen.T, right_screen[:, ::-1].T)).astype(np.float32)

  @staticmethod
  def _hsla_to_color(h, s, l, a):
    rgb = colorsys.hls_to_rgb(h, l, s)
    return rl.Color(
      int(rgb[0] * 255),
      int(rgb[1] * 255),
      int(rgb[2] * 255),
      int(a * 255)
    )

  @staticmethod
  def _blend_colors(begin_colors, end_colors, t):
    if t >= 1.0:
      return end_colors
    if t <= 0.0:
      return begin_colors

    inv_t = 1.0 - t
    return [rl.Color(
      int(inv_t * start.r + t * end.r),
      int(inv_t * start.g + t * end.g),
      int(inv_t * start.b + t * end.b),
      int(inv_t * start.a + t * end.a)
    ) for start, end in zip(begin_colors, end_colors, strict=True)]
