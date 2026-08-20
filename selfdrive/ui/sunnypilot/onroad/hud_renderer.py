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

    # Radar health is independent of whether a lead is currently present.
    if ui_state.sm.alive['radarState'] and ui_state.sm.valid['radarState']:
      radar_state = ui_state.sm['radarState']
      lead_one = ui_state.sm['radarState'].leadOne
      self.radar_available = len(radar_state.radarErrors) == 0
      self.lead_detected = lead_one.status
      self.lead_from_radar = lead_one.radar
    else:
      self.radar_available = False
      self.lead_detected = False
      self.lead_from_radar = False

    # Visual traffic-light stopping and the final planner target are published
    # by longitudinal_planner. Keep the green state briefly so it is readable.
    if ui_state.sm.alive['longitudinalPlan'] and ui_state.sm.valid['longitudinalPlan']:
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
    else:
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

    panel_width = 330
    panel_height = 224
    x = rect.x + 30
    y = rect.y + 30

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

    title = "巡航设定"
    rl.draw_text_ex(
      self._font_semi_bold,
      title,
      rl.Vector2(x + 24, y + 15),
      30,
      0,
      max_color,
    )

    self._draw_gear_shifter(rl.Rectangle(x + panel_width - 82, y + 14, 58, 50))

    set_speed_text = CRUISE_DISABLED_CHAR if not self.is_cruise_set else str(round(self.set_speed))
    rl.draw_text_ex(
      self._font_bold,
      set_speed_text,
      rl.Vector2(x + 22, y + 54),
      92,
      0,
      set_speed_color,
    )

    unit = tr("km/h") if ui_state.is_metric else tr("mph")
    rl.draw_text_ex(self._font_medium, unit, rl.Vector2(x + 174, y + 103), 25, 0, COLORS.GREY)

    divider_y = y + 156
    rl.draw_line_ex(rl.Vector2(x + 22, divider_y), rl.Vector2(x + panel_width - 22, divider_y), 2, rl.Color(255, 255, 255, 38))

    stock_text = "–" if self.speed_cluster <= 0 else str(round(self.speed_cluster))
    target_text = "–" if self.cruise_target_speed <= 0 else str(round(self.cruise_target_speed))
    self._draw_cruise_metric(x + 24, y + 169, "原车", stock_text, COLORS.WHITE)
    self._draw_cruise_metric(x + 176, y + 169, "目标", target_text,
                             COLORS.ENGAGED if self.cruise_target_speed > 0 else COLORS.DARK_GREY)

  def _draw_cruise_metric(self, x: float, y: float, label: str, value: str, color: rl.Color) -> None:
    rl.draw_text_ex(self._font_medium, label, rl.Vector2(x, y + 7), 24, 0, COLORS.GREY)
    rl.draw_text_ex(self._font_bold, value, rl.Vector2(x + 66, y), 38, 0, color)

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
    self.speed_limit_renderer.render(rect)
    self.smart_cruise_control_renderer.render(rect)
    self.turn_signal_controller.render(rect)
    self.circular_alerts_renderer.render(rect)
    self.rocket_fuel.render(rect, ui_state.sm)

    # 雷达工作状态指示器（右上角）
    self._draw_radar_status(rect)

    # 红绿灯状态提示（右下角）
    self._draw_traffic_light_status(rect)

  def _draw_gear_shifter(self, rect: rl.Rectangle) -> None:
    """Draw the gear badge inside the cruise panel."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height

    # 背景
    bg_color = rl.Color(0, 0, 0, 180)
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.26, 8, bg_color)

    # 档位文字
    text_color = rl.WHITE if self.gear_shifter in ("D", "S", "M") else rl.YELLOW
    text_width = measure_text_cached(self._font_bold, self.gear_shifter, 34).x
    rl.draw_text_ex(
      self._font_bold,
      self.gear_shifter,
      rl.Vector2(x + (w - text_width) / 2, y + 7),
      34,
      0,
      text_color,
    )

  def _draw_traffic_light_status(self, rect: rl.Rectangle) -> None:
    """Draw traffic light status indicator (bottom-right corner)."""
    if self.traffic_light_state == "off":
      return

    w = 250
    h = 116
    x = rect.x + rect.width - w - 30
    y = rect.y + rect.height - h - 200
    center_x = x + 54
    center_y = y + h / 2

    bg_color = rl.Color(0, 0, 0, 200)
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.18, 12, bg_color)

    # 红绿灯颜色
    if self.traffic_light_state == "red":
      color = rl.RED
    elif self.traffic_light_state == "green":
      color = rl.GREEN
    else:
      color = rl.GRAY

    rl.draw_circle(int(center_x), int(center_y), 31, color)
    rl.draw_circle_lines(int(center_x), int(center_y), 34, rl.Color(255, 255, 255, 90))

    # 文字
    text = "停" if self.traffic_light_state == "red" else "行"
    text_width = measure_text_cached(self._font_bold, text, 30).x
    rl.draw_text_ex(
      self._font_bold,
      text,
      rl.Vector2(center_x - text_width / 2, center_y - 15),
      30,
      0,
      rl.WHITE,
    )

    status_text = "红灯停车" if self.traffic_light_state == "red" else "绿灯放行"
    rl.draw_text_ex(self._font_bold, status_text, rl.Vector2(x + 100, y + 25), 32, 0, rl.WHITE)
    if self.traffic_light_state == "red" and 0 < self.traffic_stop_distance < 300:
      distance_text = f"距停车点 {self.traffic_stop_distance:.0f} m"
    else:
      distance_text = "停车规划已更新"
    rl.draw_text_ex(self._font_medium, distance_text, rl.Vector2(x + 100, y + 68), 22, 0, COLORS.GREY)

  def _draw_radar_status(self, rect: rl.Rectangle) -> None:
    """Draw radar status indicator (top-right corner)."""
    w = 186
    h = 58
    x = rect.x + rect.width - UI_CONFIG.border_size - UI_CONFIG.button_size - w - 18
    y = rect.y + 42

    # 背景
    bg_color = rl.Color(0, 0, 0, 180)
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.22, 8, bg_color)

    # 雷达图标（简单表示）
    radar_color = rl.GREEN if self.radar_available else rl.RED
    rl.draw_circle(int(x + 24), int(y + h // 2), 9, radar_color)

    # 文字
    text = "雷达正常" if self.radar_available else "雷达异常"
    text_color = rl.WHITE if self.radar_available else rl.RED
    rl.draw_text_ex(self._font_semi_bold, text, rl.Vector2(x + 44, y + 8), 23, 0, text_color)

    # Lead source is useful without redefining radar health.
    if self.lead_detected:
      lead_text = "雷达目标" if self.lead_from_radar else "视觉目标"
      rl.draw_text_ex(self._font_medium, lead_text, rl.Vector2(x + 44, y + 33), 17, 0, COLORS.ENGAGED)
