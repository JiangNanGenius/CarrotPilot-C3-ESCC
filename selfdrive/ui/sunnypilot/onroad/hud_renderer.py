"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl

from cereal import car
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.mici.onroad.torque_bar import TorqueBar
from openpilot.selfdrive.ui.sunnypilot.onroad.developer_ui import DeveloperUiRenderer, DeveloperUiState, get_bottom_dev_ui_offset
from openpilot.selfdrive.ui.sunnypilot.onroad.road_name import RoadNameRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.rocket_fuel import RocketFuel
from openpilot.selfdrive.ui.sunnypilot.onroad.speed_limit import SpeedLimitRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.smart_cruise_control import SmartCruiseControlRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.turn_signal import TurnSignalController
from openpilot.selfdrive.ui.sunnypilot.onroad.circular_alerts import CircularAlertsRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.hud_layout import CRUISE_PANEL_HEIGHT, CRUISE_PANEL_WIDTH, LEFT_MARGIN, TOP_MARGIN
from openpilot.selfdrive.ui.sunnypilot.onroad.speed_renderer import SpeedRenderer
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.selfdrive.ui.onroad.hud_renderer import HudRenderer, UI_CONFIG, COLORS, CRUISE_DISABLED_CHAR
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached

SLA_ACTIVE_COLOR = rl.Color(0x91, 0x9b, 0x95, 0xff)


class HudRendererSP(HudRenderer):
  def __init__(self):
    super().__init__()
    self.developer_ui = DeveloperUiRenderer()
    self.road_name_renderer = RoadNameRenderer()
    self.rocket_fuel = RocketFuel()
    self.speed_limit_renderer = SpeedLimitRenderer()
    self.smart_cruise_control_renderer = SmartCruiseControlRenderer()
    self.turn_signal_controller = TurnSignalController()
    self.circular_alerts_renderer = CircularAlertsRenderer()
    self.speed_renderer = SpeedRenderer()
    self._torque_bar = TorqueBar(scale=3.0, always=True)

    self.pcm_cruise_speed: bool = True
    self.show_icbm_status: bool = False
    self.icbm_active_counter: int = 0
    self.speed_cluster: float = 0.0
    self.speed_conv: float = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    self.radar_available: bool = False
    self.lead_detected: bool = False
    self.lead_from_radar: bool = False
    self.cruise_target_speed: float = 0.0
    self.traffic_stop_distance: float = 0.0
    self.traffic_light_state: str = "off"
    self._traffic_light_hold_frames: int = 0
    self.longitudinal_plan_alive: bool = False
    self.gear_shifter: str = "unknown"  # 当前档位

  def _update_state(self) -> None:
    if ui_state.sm.recv_frame["carState"] < ui_state.started_frame:
      return

    if ui_state.CP_SP is not None:
      self.pcm_cruise_speed = ui_state.CP_SP.pcmCruiseSpeed
    self.speed_conv = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    self.speed_cluster = ui_state.sm['carState'].cruiseState.speedCluster * self.speed_conv

    # 当前档位
    gear = ui_state.sm['carState'].gearShifter
    if gear == car.CarState.GearShifter.park:
      self.gear_shifter = "P"
    elif gear == car.CarState.GearShifter.reverse:
      self.gear_shifter = "R"
    elif gear == car.CarState.GearShifter.neutral:
      self.gear_shifter = "N"
    elif gear == car.CarState.GearShifter.drive:
      self.gear_shifter = "D"
    elif gear == car.CarState.GearShifter.sport:
      self.gear_shifter = "S"
    elif gear == car.CarState.GearShifter.manumatic:
      self.gear_shifter = "M"
    elif gear == car.CarState.GearShifter.low:
      self.gear_shifter = "L"
    elif gear == car.CarState.GearShifter.eco:
      self.gear_shifter = "E"
    else:
      self.gear_shifter = "?"

    # Accept the first fresh message immediately; alive takes a few samples to
    # settle at startup. A genuinely stale stream still clears the indicator.
    if ui_state.sm.updated['radarState'] and ui_state.sm.valid['radarState']:
      radar_state = ui_state.sm['radarState']
      lead_one = ui_state.sm['radarState'].leadOne
      self.radar_available = not any(radar_state.radarErrors.to_dict().values())
      self.lead_detected = lead_one.status
      self.lead_from_radar = lead_one.radar
    elif not ui_state.sm.alive['radarState']:
      self.radar_available = False
      self.lead_detected = False
      self.lead_from_radar = False

    # Visual traffic-light stopping and the final planner target are published
    # by longitudinal_planner. Keep the green state briefly so it is readable.
    if ui_state.sm.updated['longitudinalPlan'] and ui_state.sm.valid['longitudinalPlan']:
      self.longitudinal_plan_alive = True
      long_plan = ui_state.sm['longitudinalPlan']
      self.cruise_target_speed = long_plan.cruiseTargetSpeed
      if not ui_state.is_metric:
        self.cruise_target_speed *= CV.KPH_TO_MPH
      self.traffic_stop_distance = max(0.0, long_plan.trafficStopDistance)

      traffic_state = int(long_plan.trafficState)
      if traffic_state == 1:
        self.traffic_light_state = "red"
        self._traffic_light_hold_frames = max(1, int(0.5 * gui_app.target_fps))
      elif traffic_state == 2:
        self.traffic_light_state = "green"
        self._traffic_light_hold_frames = max(1, int(2.0 * gui_app.target_fps))
      elif self._traffic_light_hold_frames > 0:
        self._traffic_light_hold_frames -= 1
      else:
        self.traffic_light_state = "off"
        self.traffic_stop_distance = 0.0
    elif not ui_state.sm.alive['longitudinalPlan']:
      self.longitudinal_plan_alive = False
      self.cruise_target_speed = 0.0
      if self._traffic_light_hold_frames > 0:
        self._traffic_light_hold_frames -= 1
      else:
        self.traffic_light_state = "off"
        self.traffic_stop_distance = 0.0

    super()._update_state()
    self.road_name_renderer.update()
    self.speed_limit_renderer.update()
    self.smart_cruise_control_renderer.update()
    self.turn_signal_controller.update()
    self.circular_alerts_renderer.update()
    self.speed_renderer.update()

  def _get_icbm_status(self):
    if not self.pcm_cruise_speed and ui_state.sm['carControl'].enabled:
      if round(self.set_speed) != round(self.speed_cluster):
        self.icbm_active_counter = 3 * gui_app.target_fps  # 3 seconds usually
      elif self.icbm_active_counter > 0:
        self.icbm_active_counter -= 1
    else:
      self.icbm_active_counter = 0

    self.show_icbm_status = self.icbm_active_counter > 0

  def _draw_set_speed(self, rect: rl.Rectangle) -> None:
    long_plan_sp = ui_state.sm['longitudinalPlanSP']
    long_override = ui_state.sm['carControl'].cruiseControl.override
    self._get_icbm_status()

    panel_width = CRUISE_PANEL_WIDTH
    panel_height = CRUISE_PANEL_HEIGHT
    x = rect.x + LEFT_MARGIN
    y = rect.y + TOP_MARGIN

    panel_rect = rl.Rectangle(x, y, panel_width, panel_height)
    rl.draw_rectangle_rounded(panel_rect, 0.16, 12, rl.Color(0, 0, 0, 190))

    max_color = COLORS.GREY
    set_speed_color = COLORS.DARK_GREY
    if self.is_cruise_set:
      set_speed_color = COLORS.WHITE
      if long_plan_sp.speedLimit.assist.active:
        set_speed_color = SLA_ACTIVE_COLOR if long_override else rl.Color(0, 0xff, 0, 0xff)
        max_color = SLA_ACTIVE_COLOR if long_override else rl.Color(0x80, 0xd8, 0xa6, 0xff)
      else:
        if ui_state.status == UIStatus.ENGAGED:
          max_color = COLORS.ENGAGED
        elif ui_state.status == UIStatus.DISENGAGED:
          max_color = COLORS.DISENGAGED
        elif ui_state.status == UIStatus.OVERRIDE:
          max_color = COLORS.OVERRIDE

    title = "巡航"
    rl.draw_text_ex(
      self._font_semi_bold,
      title,
      rl.Vector2(x + 22, y + 17),
      36,
      0,
      max_color,
    )

    self._draw_gear_shifter(rl.Rectangle(x + panel_width - 70, y + 13, 50, 48))

    set_speed_text = CRUISE_DISABLED_CHAR if not self.is_cruise_set else str(round(self.set_speed))
    set_speed_size = 108 if len(set_speed_text) >= 3 else 124
    set_speed_width = measure_text_cached(self._font_bold, set_speed_text, set_speed_size).x
    rl.draw_text_ex(
      self._font_bold,
      set_speed_text,
      rl.Vector2(x + (panel_width - set_speed_width) / 2, y + 48),
      set_speed_size,
      0,
      set_speed_color,
    )

    unit = tr("km/h") if ui_state.is_metric else tr("mph")
    unit_width = measure_text_cached(self._font_medium, unit, 25).x
    rl.draw_text_ex(self._font_medium, unit, rl.Vector2(x + (panel_width - unit_width) / 2, y + 169), 25, 0, COLORS.GREY)

    divider_y = y + 208
    rl.draw_line_ex(rl.Vector2(x + 22, divider_y), rl.Vector2(x + panel_width - 22, divider_y), 2, rl.Color(255, 255, 255, 38))

    stock_text = "–" if self.speed_cluster <= 0 else str(round(self.speed_cluster))
    target_text = "–" if self.cruise_target_speed <= 0 else str(round(self.cruise_target_speed))
    metric_width = (panel_width - 58) / 2
    self._draw_cruise_metric(x + 20, y + 222, metric_width, "仪表设定", stock_text, COLORS.WHITE)
    self._draw_cruise_metric(x + 38 + metric_width, y + 222, metric_width, "规划目标", target_text,
                             COLORS.ENGAGED if self.cruise_target_speed > 0 else COLORS.DARK_GREY)

    rl.draw_line_ex(rl.Vector2(x + 22, y + 326), rl.Vector2(x + panel_width - 22, y + 326), 2, rl.Color(255, 255, 255, 38))
    self._draw_integrated_speed_limit(x + 20, y + 342, 168, 150)
    self._draw_integrated_traffic(x + 208, y + 342, 172, 150)

  def _draw_cruise_metric(self, x: float, y: float, width: float, label: str, value: str, color: rl.Color) -> None:
    label_width = measure_text_cached(self._font_semi_bold, label, 29).x
    rl.draw_text_ex(self._font_semi_bold, label, rl.Vector2(x + (width - label_width) / 2, y), 29, 0, COLORS.GREY)
    value_size = 54 if len(value) >= 3 else 62
    value_width = measure_text_cached(self._font_bold, value, value_size).x
    rl.draw_text_ex(self._font_bold, value, rl.Vector2(x + (width - value_width) / 2, y + 35), value_size, 0, color)

  def _draw_integrated_speed_limit(self, x: float, y: float, width: float, height: float) -> None:
    speed_limit = self.speed_limit_renderer
    has_limit = speed_limit.speed_limit_valid or speed_limit.speed_limit_last_valid
    limit = str(round(speed_limit.speed_limit_final_last)) if has_limit else "--"
    overspeed = has_limit and round(speed_limit.speed) > round(speed_limit.speed_limit_final_last)
    color = rl.RED if overspeed else COLORS.WHITE
    rl.draw_text_ex(self._font_semi_bold, "限速", rl.Vector2(x, y), 29, 0, COLORS.GREY)
    circle_x, circle_y = int(x + width / 2), int(y + 84)
    rl.draw_circle(circle_x, circle_y, 57, COLORS.WHITE)
    rl.draw_ring(rl.Vector2(circle_x, circle_y), 46, 57, 0, 360, 40, rl.RED if has_limit else COLORS.GREY)
    size = 55 if len(limit) >= 3 else 64
    text_width = measure_text_cached(self._font_bold, limit, size).x
    rl.draw_text_ex(self._font_bold, limit, rl.Vector2(circle_x - text_width / 2, circle_y - size / 2), size, 0,
                    rl.RED if overspeed else rl.BLACK)
    if speed_limit.speed_limit_offset:
      offset = f"偏移 {speed_limit.speed_limit_offset:+.0f}"
      rl.draw_text_ex(self._font_medium, offset, rl.Vector2(x + 4, y + height - 23), 22, 0, color)

  def _draw_integrated_traffic(self, x: float, y: float, width: float, height: float) -> None:
    if not self.longitudinal_plan_alive:
      label, detail, color = "纵向离线", "不可用", rl.RED
    elif self.traffic_light_state == "red":
      label, detail, color = "红灯停车", f"距停点 {self.traffic_stop_distance:.0f}m", rl.RED
    elif self.traffic_light_state == "green":
      label, detail, color = "绿灯通行", "路径已放行", rl.GREEN
    else:
      label, detail, color = "信号灯", "正在监测", COLORS.GREY
    rl.draw_text_ex(self._font_semi_bold, label, rl.Vector2(x, y), 29, 0, color)
    rl.draw_circle(int(x + width / 2), int(y + 83), 43, rl.Color(8, 8, 8, 245))
    rl.draw_circle(int(x + width / 2), int(y + 83), 34, color)
    detail_width = measure_text_cached(self._font_medium, detail, 23).x
    rl.draw_text_ex(self._font_medium, detail, rl.Vector2(x + (width - detail_width) / 2, y + height - 25), 23, 0, COLORS.WHITE)

  def _draw_current_speed(self, rect: rl.Rectangle) -> None:
    self.speed_renderer.render(rect)

  def _render(self, rect: rl.Rectangle) -> None:
    # Render the base HUD explicitly so the overridden cruise panel is drawn
    # exactly once and the top-right experiment button keeps its own space.
    rl.draw_rectangle_gradient_v(
      int(rect.x), int(rect.y), int(rect.width), UI_CONFIG.header_height,
      COLORS.HEADER_GRADIENT_START, COLORS.HEADER_GRADIENT_END,
    )
    if self.is_cruise_available:
      self._draw_set_speed(rect)
    self._draw_current_speed(rect)
    button_x = rect.x + rect.width - UI_CONFIG.border_size - UI_CONFIG.button_size
    button_y = rect.y + UI_CONFIG.border_size
    self._exp_button.render(rl.Rectangle(button_x, button_y, UI_CONFIG.button_size, UI_CONFIG.button_size))

    if ui_state.torque_bar:
      torque_rect = rect
      if ui_state.developer_ui in (DeveloperUiState.BOTTOM, DeveloperUiState.BOTH):
        torque_rect = rl.Rectangle(rect.x, rect.y, rect.width, rect.height - get_bottom_dev_ui_offset())
      self._torque_bar.render(torque_rect)

    self.developer_ui.render(rect)
    self.road_name_renderer.render(rect)
    # Speed-limit, traffic-light and curve-control states share the left
    # cruise rail; standalone floating cards are deliberately suppressed.
    self.turn_signal_controller.render(rect)
    self.circular_alerts_renderer.render(rect)
    self.rocket_fuel.render(rect, ui_state.sm)

    # Radar status (top-right)
    self._draw_radar_status(rect)

    self._draw_curve_control_status(rect)

  def _draw_curve_control_status(self, rect: rl.Rectangle) -> None:
    scc = self.smart_cruise_control_renderer
    labels = []
    if scc.vision_enabled:
      labels.append("弯道视觉" if (scc.vision_active or scc.vision_approaching) else "视觉待命")
    if scc.map_enabled:
      labels.append("弯道地图" if scc.map_active else "地图待命")
    if not labels:
      return
    x = rect.x + LEFT_MARGIN
    y = rect.y + TOP_MARGIN + CRUISE_PANEL_HEIGHT + 12
    text = "  ·  ".join(labels)
    color = COLORS.OVERRIDE if scc.long_override else (COLORS.ENGAGED if (scc.vision_active or scc.map_active) else COLORS.GREY)
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, CRUISE_PANEL_WIDTH, 54), 0.22, 8, rl.Color(0, 0, 0, 190))
    tw = measure_text_cached(self._font_semi_bold, text, 25).x
    rl.draw_text_ex(self._font_semi_bold, text, rl.Vector2(x + (CRUISE_PANEL_WIDTH - tw) / 2, y + 12), 25, 0, color)

  def _draw_gear_shifter(self, rect: rl.Rectangle) -> None:
    """Draw the gear badge inside the cruise panel."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height

    bg_color = rl.Color(0, 0, 0, 180)
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.26, 8, bg_color)

    text_color = rl.WHITE if self.gear_shifter in ("D", "S", "M") else rl.YELLOW
    text_width = measure_text_cached(self._font_bold, self.gear_shifter, 29).x
    rl.draw_text_ex(
      self._font_bold,
      self.gear_shifter,
      rl.Vector2(x + (w - text_width) / 2, y + 6),
      29,
      0,
      text_color,
    )

  def _draw_traffic_light_status(self, rect: rl.Rectangle) -> None:
    """Draw the active traffic-control decision near the driver's sightline."""
    if self.traffic_light_state == "off":
      return

    w = TRAFFIC_CARD_WIDTH
    h = TRAFFIC_CARD_HEIGHT
    x = rect.x + (rect.width - w) / 2
    y = rect.y + rect.height - h - TRAFFIC_CARD_BOTTOM_MARGIN
    center_x = x + 82
    center_y = y + h / 2

    bg_color = rl.Color(0, 0, 0, 200)
    card_rect = rl.Rectangle(x, y, w, h)
    rl.draw_rectangle_rounded(card_rect, 0.14, 12, bg_color)

    if self.traffic_light_state == "red":
      color = rl.RED
    elif self.traffic_light_state == "green":
      color = rl.GREEN
    else:
      color = rl.GRAY

    rl.draw_rectangle_rounded_lines_ex(card_rect, 0.14, 12, 3, rl.color_alpha(color, 0.72))
    rl.draw_circle(int(center_x), int(center_y), 47, rl.Color(10, 10, 10, 255))
    rl.draw_circle(int(center_x), int(center_y), 40, color)
    rl.draw_circle_lines(int(center_x), int(center_y), 48, rl.Color(255, 255, 255, 105))

    symbol = "!" if self.traffic_light_state == "red" else "GO"
    symbol_size = 42 if self.traffic_light_state == "red" else 27
    text_width = measure_text_cached(self._font_bold, symbol, symbol_size).x
    rl.draw_text_ex(
      self._font_bold,
      symbol,
      rl.Vector2(center_x - text_width / 2, center_y - symbol_size / 2),
      symbol_size,
      0,
      rl.WHITE,
    )

    status_text = "STOP" if self.traffic_light_state == "red" else "GO"
    rl.draw_text_ex(self._font_bold, status_text, rl.Vector2(x + 154, y + 22), 54, 0, rl.WHITE)
    if self.traffic_light_state == "red" and 0 < self.traffic_stop_distance < 300:
      distance_text = f"STOP LINE  {self.traffic_stop_distance:.0f} m"
    else:
      distance_text = "PATH CLEAR"
    rl.draw_text_ex(self._font_semi_bold, distance_text, rl.Vector2(x + 156, y + 91), 32, 0, rl.Color(238, 238, 238, 255))

  def _draw_radar_status(self, rect: rl.Rectangle) -> None:
    """Draw radar status indicator (top-right corner)."""
    w = 186
    h = 58
    x = rect.x + rect.width - UI_CONFIG.border_size - UI_CONFIG.button_size - w - 18
    y = rect.y + 42

    bg_color = rl.Color(0, 0, 0, 180)
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.22, 8, bg_color)

    radar_color = rl.GREEN if self.radar_available else rl.RED
    rl.draw_circle(int(x + 24), int(y + h // 2), 9, radar_color)

    text = "RADAR"
    text_color = rl.WHITE if self.radar_available else rl.RED
    rl.draw_text_ex(self._font_semi_bold, text, rl.Vector2(x + 44, y + 8), 23, 0, text_color)

    # Lead source is useful without redefining radar health.
    if self.lead_detected:
      lead_text = "LEAD: RADAR" if self.lead_from_radar else "LEAD: VISION"
      rl.draw_text_ex(self._font_medium, lead_text, rl.Vector2(x + 44, y + 31), 19, 0, COLORS.ENGAGED)
