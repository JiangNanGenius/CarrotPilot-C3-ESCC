"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl

from cereal import car, log
from opendbc.sunnypilot.car.hyundai.values import HyundaiFlagsSP
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
CruiseTargetSource = log.LongitudinalPlan.CruiseTargetSource


def cruise_source_label(plan_alive: bool, target_source) -> str:
  if not plan_alive:
    return "不可用"
  # pycapnp readers expose enum fields as _DynamicEnum objects. They compare
  # equal to the generated integer constants, but have a different hash, so a
  # direct dictionary lookup silently falls through to the default label.
  target_source = getattr(target_source, "raw", target_source)
  return {
    CruiseTargetSource.instrumentSet: "仪表定速",
    CruiseTargetSource.wheelSet: "实际车速",
    CruiseTargetSource.vehicleLimit: "车辆限速",
    CruiseTargetSource.mapLimit: "地图限速",
    CruiseTargetSource.navigationLimit: "导航限速",
    CruiseTargetSource.visionCurve: "视觉弯道",
    CruiseTargetSource.mapCurve: "地图弯道",
    CruiseTargetSource.trafficLight: "红灯停车",
    CruiseTargetSource.safetyDecel: "安全减速",
  }.get(target_source, "仪表定速")


def radar_packet_status(packet_valid: bool, has_errors: bool) -> str:
  """Map one fresh radar packet to a truthful driver-facing health state."""
  if not packet_valid:
    return "invalid"
  return "fault" if has_errors else "healthy"


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
    self.radar_status: str = "initializing"
    self.radar_seen: bool = False
    self._radar_wait_frames: int = 0
    self.escc_enabled: bool = False
    self.lead_detected: bool = False
    self.lead_from_radar: bool = False
    self.cruise_target_speed: float = 0.0
    self.cruise_target_source = CruiseTargetSource.instrumentSet
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
      self.escc_enabled = bool(
        ui_state.CP is not None and ui_state.CP.brand == "hyundai" and
        ui_state.CP_SP.flags & HyundaiFlagsSP.ENHANCED_SCC
      )
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

    # Hardware health comes from explicit radar errors. Message-envelope
    # validity can be false during producer timestamp convergence and must not
    # paint healthy ESCC hardware red.
    if ui_state.sm.updated['radarState']:
      radar_state = ui_state.sm['radarState']
      lead_one = radar_state.leadOne
      self.radar_seen = True
      self._radar_wait_frames = 0
      self.radar_status = radar_packet_status(
        ui_state.sm.valid['radarState'], any(radar_state.radarErrors.to_dict().values()),
      )
      self.radar_available = self.radar_status == "healthy"
      self.lead_detected = self.radar_available and lead_one.status
      self.lead_from_radar = self.radar_available and lead_one.radar
    elif not ui_state.sm.alive['radarState']:
      self._radar_wait_frames += 1
      if self.radar_seen or self._radar_wait_frames > 3 * gui_app.target_fps:
        self.radar_status = "stale"
      self.radar_available = False
      self.lead_detected = False
      self.lead_from_radar = False

    # Visual traffic-light stopping and the final planner target are published
    # by longitudinal_planner. Keep the green state briefly so it is readable.
    if ui_state.sm.updated['longitudinalPlan']:
      if ui_state.sm.valid['longitudinalPlan']:
        self.longitudinal_plan_alive = True
        long_plan = ui_state.sm['longitudinalPlan']
        self.cruise_target_speed = long_plan.cruiseTargetSpeed
        self.cruise_target_source = long_plan.cruiseTargetSource
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
        # An alive producer can continuously publish invalid envelopes. Never
        # retain an old target or green-light release through that condition.
        self.longitudinal_plan_alive = False
        self.cruise_target_speed = 0.0
        self.traffic_light_state = "off"
        self.traffic_stop_distance = 0.0
        self._traffic_light_hold_frames = 0
    elif not ui_state.sm.alive['longitudinalPlan']:
      self.longitudinal_plan_alive = False
      self.cruise_target_speed = 0.0
      self.traffic_light_state = "off"
      self.traffic_stop_distance = 0.0
      self._traffic_light_hold_frames = 0

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

    title = "当前目标"
    rl.draw_text_ex(
      self._font_semi_bold,
      title,
      rl.Vector2(x + 22, y + 17),
      36,
      0,
      max_color,
    )

    self._draw_gear_shifter(rl.Rectangle(x + panel_width - 70, y + 13, 50, 48))

    # Zero is a real and safety-critical target at a red light. Reserve the
    # dash exclusively for a missing/stale longitudinal plan.
    target_text = "–" if not self.longitudinal_plan_alive else str(round(max(0.0, self.cruise_target_speed)))
    target_size = 108 if len(target_text) >= 3 else 124
    target_width = measure_text_cached(self._font_bold, target_text, target_size).x
    rl.draw_text_ex(
      self._font_bold,
      target_text,
      rl.Vector2(x + (panel_width - target_width) / 2, y + 48),
      target_size,
      0,
      set_speed_color if self.longitudinal_plan_alive else COLORS.DARK_GREY,
    )

    unit = tr("km/h") if ui_state.is_metric else tr("mph")
    unit_width = measure_text_cached(self._font_medium, unit, 25).x
    rl.draw_text_ex(self._font_medium, unit, rl.Vector2(x + (panel_width - unit_width) / 2, y + 169), 25, 0, COLORS.GREY)

    divider_y = y + 208
    rl.draw_line_ex(rl.Vector2(x + 22, divider_y), rl.Vector2(x + panel_width - 22, divider_y), 2, rl.Color(255, 255, 255, 38))

    max_speed_text = CRUISE_DISABLED_CHAR if not self.is_cruise_set else str(round(self.set_speed))
    source_text = cruise_source_label(self.longitudinal_plan_alive, self.cruise_target_source)
    metric_width = (panel_width - 58) / 2
    self._draw_cruise_metric(x + 20, y + 222, metric_width, "最高定速", max_speed_text, COLORS.WHITE)
    self._draw_cruise_metric(x + 38 + metric_width, y + 222, metric_width, "定速依据", source_text,
                             COLORS.ENGAGED if self.longitudinal_plan_alive else COLORS.DARK_GREY, text_value=True)

    rl.draw_line_ex(rl.Vector2(x + 22, y + 326), rl.Vector2(x + panel_width - 22, y + 326), 2, rl.Color(255, 255, 255, 38))
    self._draw_integrated_speed_limit(x + 20, y + 342, 168, 150)
    self._draw_integrated_traffic(x + 208, y + 342, 172, 150)

  def _draw_cruise_metric(self, x: float, y: float, width: float, label: str, value: str, color: rl.Color,
                          text_value: bool = False) -> None:
    label_width = measure_text_cached(self._font_semi_bold, label, 29).x
    rl.draw_text_ex(self._font_semi_bold, label, rl.Vector2(x + (width - label_width) / 2, y), 29, 0, COLORS.GREY)
    value_size = (32 if len(value) >= 4 else 37) if text_value else (54 if len(value) >= 3 else 62)
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
      detail = f"距停点 {self.traffic_stop_distance:.0f}m" if self.traffic_stop_distance > 0 else "停车控制中"
      label, color = "红灯停车", rl.RED
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

  def _draw_radar_status(self, rect: rl.Rectangle) -> None:
    """Draw radar status indicator (top-right corner)."""
    w = 218
    h = 70
    x = rect.x + rect.width - UI_CONFIG.border_size - UI_CONFIG.button_size - w - 18
    y = rect.y + 42

    bg_color = rl.Color(0, 0, 0, 180)
    rl.draw_rectangle_rounded(rl.Rectangle(x, y, w, h), 0.22, 8, bg_color)

    if self.radar_status == "healthy":
      radar_color = COLORS.ENGAGED
    elif self.radar_status in ("initializing", "invalid"):
      radar_color = rl.Color(255, 190, 32, 255)
    else:
      radar_color = rl.RED
    rl.draw_circle(int(x + 25), int(y + h // 2), 10, radar_color)

    text = "ESCC" if self.escc_enabled else "RADAR"
    text_color = radar_color
    rl.draw_text_ex(self._font_semi_bold, text, rl.Vector2(x + 48, y + 8), 25, 0, text_color)

    if self.radar_status == "healthy":
      # Keep status text inside the shipped atlas. The middle-dot glyph is not
      # part of the CJK fallback set and rendered as a replacement character.
      detail = "正常 / 雷达前车" if self.lead_detected and self.lead_from_radar else \
               "正常 / 视觉前车" if self.lead_detected else "硬件正常"
    elif self.radar_status == "initializing":
      detail = "正在初始化"
    elif self.radar_status == "invalid":
      detail = "数据校验中"
    elif self.radar_status == "stale":
      detail = "数据中断"
    else:
      detail = "雷达故障"
    rl.draw_text_ex(self._font_medium, detail, rl.Vector2(x + 48, y + 39), 20, 0, radar_color)
