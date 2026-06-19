"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from enum import IntEnum

import pyray as rl
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.cruise_sub_layouts.speed_limit_settings import SpeedLimitSettingsLayout
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.lib.styles import style
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp, option_item_sp, simple_button_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import gui_label
from openpilot.system.ui.widgets.scroller_tici import Scroller


class PanelType(IntEnum):
  CRUISE = 0
  SLA = 1


ICBM_DESC = tr_noop("When enabled, Genius Pilot will attempt to manage the built-in cruise control buttons " +
                    "by emulating button presses for limited longitudinal control.")
ICMB_UNAVAILABLE = tr_noop("Intelligent Cruise Button Management is currently unavailable on this platform.")
ICMB_UNAVAILABLE_LONG_AVAILABLE = tr_noop("Disable the Genius Pilot Longitudinal Control (alpha) toggle to allow Intelligent Cruise Button Management.")
ICMB_UNAVAILABLE_LONG_UNAVAILABLE = tr_noop("Genius Pilot Longitudinal Control is the default longitudinal control for this platform.")
CARROT_CRUISE_POLICY = tr_noop("This personal build keeps cruise-speed behavior aligned with CarrotPilot. ICBM, SCC-V, and SCC-M stay hidden. Sunny DEC is available in Cruise and Super Advanced settings.")
DEC_DESCRIPTION = tr_noop("Sunny dynamic experimental control. It can switch between classic longitudinal and E2E-style behavior when available.")

ACC_ENABLED_DESCRIPTION = tr_noop("Enable custom Short & Long press increments for cruise speed increase/decrease.")
ACC_NOLONG_DESCRIPTION = tr_noop("This feature can only be used with Genius Pilot longitudinal control enabled.")
ACC_PCMCRUISE_DISABLED_DESCRIPTION = tr_noop("This feature is not supported on this platform due to vehicle limitations.")
ONROAD_ONLY_DESCRIPTION = tr_noop("Start the vehicle to check vehicle compatibility.")


class CruiseSectionHeader(Widget):
  def __init__(self, title, description=None):
    super().__init__()
    self._title = title
    self._description = description
    self._rect = rl.Rectangle(0, 0, 0, 112 if description else 72)

  @staticmethod
  def _resolve(value) -> str:
    return value() if callable(value) else str(value)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def _render(self, _) -> None:
    content_x = self._rect.x + style.ITEM_PADDING
    content_w = self._rect.width - style.ITEM_PADDING * 2
    title_rect = rl.Rectangle(content_x, self._rect.y + 8, content_w, 44)
    gui_label(title_rect, self._resolve(self._title), font_size=34, color=rl.Color(150, 205, 255, 255),
              font_weight=FontWeight.SEMI_BOLD, alignment=rl.GuiTextAlignment.TEXT_ALIGN_LEFT)

    if self._description:
      desc_rect = rl.Rectangle(content_x, self._rect.y + 54, content_w, 36)
      gui_label(desc_rect, self._resolve(self._description), font_size=26, color=style.ITEM_TEXT_VALUE_COLOR,
                alignment=rl.GuiTextAlignment.TEXT_ALIGN_LEFT)


class CruiseLayout(Widget):
  def __init__(self):
    super().__init__()
    self._current_panel = PanelType.CRUISE
    self._speed_limit_layout = SpeedLimitSettingsLayout(lambda: self._set_current_panel(PanelType.CRUISE))

    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _initialize_items(self):

    self.icbm_toggle = toggle_item_sp(
      title=tr("Intelligent Cruise Button Management (ICBM) (Alpha)"),
      description="",
      param="IntelligentCruiseButtonManagement")

    self.scc_v_toggle = toggle_item_sp(
      title=tr("Smart Cruise Control - Vision"),
      description=tr("Use vision path predictions to estimate the appropriate speed to drive through turns ahead."),
      param="SmartCruiseControlVision")

    self.scc_m_toggle = toggle_item_sp(
      title=tr("Smart Cruise Control - Map"),
      description=tr("Use map data to estimate the appropriate speed to drive through turns ahead."),
      param="SmartCruiseControlMap")

    self.custom_acc_toggle = toggle_item_sp(
      title=tr("Custom ACC Speed Increments"),
      description="",
      param="CustomAccIncrementsEnabled",
      callback=self._on_custom_acc_toggle)

    self.custom_acc_short_increment = option_item_sp(
      title=tr("Short Press Increment"),
      param="CustomAccShortPressIncrement",
      min_value=1, max_value=10, value_change_step=1,
      inline=True)

    self.custom_acc_long_increment = option_item_sp(
      title=tr("Long Press Increment"),
      param="CustomAccLongPressIncrement",
      value_map={1: 1, 2: 5, 3: 10},
      min_value=1, max_value=3, value_change_step=1,
      inline=True)

    self.sla_settings_button = simple_button_item_sp(
      button_text=lambda: tr("Speed Limit"),
      button_width=800,
      callback=lambda: self._set_current_panel(PanelType.SLA)
    )

    self.phone_speed_source = toggle_item_sp(
      title=lambda: tr("Phone Speed Limit Source"),
      description=lambda: tr("Use fresh APN/N, Navipilot, or Carrot phone speed-limit data before vehicle and map sources. Stale data times out automatically."),
      param="CarrotPhoneSpeedLimitEnabled")

    self.carrot_active_speed = toggle_item_sp(
      title=lambda: tr("Carrot Active Speed Control"),
      description=lambda: tr("Allow Carrot speed-limit, navigation, SDI, speed-bump, traffic-light, and model-speed evidence to adjust cruise targets when the related assist mode is enabled."),
      param="CarrotActiveSpeedControlEnabled")

    self.curve_speed_mode = option_item_sp(
      title=lambda: tr("Curve Speed Control Mode"),
      param="CurveSpeedControlMode",
      min_value=0, max_value=3, value_change_step=1,
      label_callback=self._curve_mode_label,
      description=lambda: tr("Select the curve-speed strategy: Off, Sunny, Carrot, or Fusion. Fusion keeps Sunny model-curvature quality and Carrot navigation/phone/lane inputs together."))

    self.auto_turn_control = toggle_item_sp(
      title=lambda: tr("Carrot Auto Turn Slowdown"),
      description=lambda: tr("Use Carrot navigation and curve information to slow for turns and junctions."),
      param="CarrotAutoTurnControlEnabled")

    self.turn_speed_mode = option_item_sp(
      title=lambda: tr("Turn Speed Control Mode"),
      param="TurnSpeedControlMode",
      min_value=0, max_value=3, value_change_step=1,
      label_callback=self._turn_mode_label,
      description=lambda: tr("Select the turn-speed strategy: Off, Carrot, Sunny, or Fusion."))

    self.navigation_decel_rate = option_item_sp(
      title=lambda: tr("Navigation Decel Rate"),
      param="AutoNaviSpeedDecelRate",
      min_value=50, max_value=300, value_change_step=5,
      label_callback=lambda v: f"{v}%",
      description=lambda: tr("Deceleration strength for navigation speed events such as turns, speed cameras, speed bumps, and model-speed limits."))

    self.traffic_stop = toggle_item_sp(
      title=lambda: tr("Carrot Traffic Light Stop"),
      description=lambda: tr("Use Carrot traffic-light input for red-light stop behavior."),
      param="CarrotTrafficStopEnabled")

    self.traffic_light_mode = option_item_sp(
      title=lambda: tr("Traffic Light Detect Mode"),
      param="TrafficLightDetectMode",
      min_value=0, max_value=3, value_change_step=1,
      label_callback=self._traffic_mode_label,
      description=lambda: tr("Select the traffic-light detection mode used by Carrot red-light stop."))

    self.dec_toggle = toggle_item_sp(
      title=lambda: tr("Sunny DEC Dynamic Experimental Control"),
      description=lambda: tr(DEC_DESCRIPTION),
      param="DynamicExperimentalControl")

    self.cruise_decel = option_item_sp(
      title=lambda: tr("Cruise Decel"),
      param="CarrotCruiseDecel",
      min_value=-1, max_value=200, value_change_step=5,
      label_callback=self._auto_percent_label,
      description=lambda: tr("Carrot cruise deceleration target. Auto uses the current Carrot default."))

    self.atc_decel = option_item_sp(
      title=lambda: tr("ATC Decel"),
      param="CarrotCruiseAtcDecel",
      min_value=-1, max_value=200, value_change_step=5,
      label_callback=self._auto_percent_label,
      description=lambda: tr("Deceleration target used by Auto Turn Control. Auto uses the current Carrot default."))

    self.stop_distance = option_item_sp(
      title=lambda: tr("Stop Distance"),
      param="StopDistanceCarrot",
      min_value=300, max_value=1200, value_change_step=10,
      label_callback=lambda v: f"{v / 100:.2f} m",
      description=lambda: tr("Carrot stop-distance target used by the tuning workflow. Keep your known-good value until braking logs are reviewed."))

    self.dynamic_following = option_item_sp(
      title=lambda: tr("Dynamic Following"),
      param="DynamicTFollow",
      min_value=0, max_value=100, value_change_step=5,
      label_callback=lambda v: f"{v}%",
      description=lambda: tr("Dynamic following strength. This is a tuning target and should be changed slowly after log review."))

    self.decel_follow_boost = option_item_sp(
      title=lambda: tr("Deceleration Follow Boost"),
      param="TFollowDecelBoost",
      min_value=0, max_value=100, value_change_step=5,
      label_callback=lambda v: f"{v}%",
      description=lambda: tr("Extra follow-distance behavior during deceleration. Higher values can feel more conservative."))

    self.follow_gap_1 = option_item_sp(
      title=lambda: tr("Follow Gap 1"),
      param="TFollowGap1",
      min_value=70, max_value=300, value_change_step=5,
      label_callback=lambda v: f"{v / 100:.2f} s",
      description=lambda: tr("Time gap preset 1 used by Carrot tuning."))

    self.follow_gap_2 = option_item_sp(
      title=lambda: tr("Follow Gap 2"),
      param="TFollowGap2",
      min_value=80, max_value=350, value_change_step=5,
      label_callback=lambda v: f"{v / 100:.2f} s",
      description=lambda: tr("Time gap preset 2 used by Carrot tuning."))

    self.follow_gap_3 = option_item_sp(
      title=lambda: tr("Follow Gap 3"),
      param="TFollowGap3",
      min_value=90, max_value=400, value_change_step=5,
      label_callback=lambda v: f"{v / 100:.2f} s",
      description=lambda: tr("Time gap preset 3 used by Carrot tuning."))

    self.follow_gap_4 = option_item_sp(
      title=lambda: tr("Follow Gap 4"),
      param="TFollowGap4",
      min_value=100, max_value=450, value_change_step=5,
      label_callback=lambda v: f"{v / 100:.2f} s",
      description=lambda: tr("Time gap preset 4 used by Carrot tuning."))

    items = [
      CruiseSectionHeader(lambda: tr("Speed Limit And Model-Speed"), lambda: tr("Phone speed, vehicle speed, map speed, and model-speed evidence stay visible here; detailed source policy is inside Speed Limit.")),
      self.sla_settings_button,
      self.phone_speed_source,
      self.carrot_active_speed,
      CruiseSectionHeader(lambda: tr("Curve And Turn Slowdown"), lambda: tr("Sunny curve quality, Carrot navigation turns, lane-line curve input, and model-speed events are selected by explicit modes.")),
      self.curve_speed_mode,
      self.auto_turn_control,
      self.turn_speed_mode,
      self.navigation_decel_rate,
      CruiseSectionHeader(lambda: tr("Traffic Light Stop"), lambda: tr("Red-light behavior remains a separate Carrot gate and should be tested independently.")),
      self.traffic_stop,
      self.traffic_light_mode,
      CruiseSectionHeader(lambda: tr("Longitudinal Behavior"), lambda: tr("DEC is separate from Carrot speed logic; the Carrot decel and following values remain user-tuneable while parked.")),
      self.dec_toggle,
      self.cruise_decel,
      self.atc_decel,
      self.stop_distance,
      self.dynamic_following,
      self.decel_follow_boost,
      self.follow_gap_1,
      self.follow_gap_2,
      self.follow_gap_3,
      self.follow_gap_4,
      CruiseSectionHeader(lambda: tr("Cruise Button Behavior"), lambda: tr("Button behavior stays limited to local cruise-speed increment settings. ICBM/SCC-V/SCC-M remain hidden because they overlap Carrot cruise logic.")),
      self.custom_acc_toggle,
      self.custom_acc_short_increment,
      self.custom_acc_long_increment,
    ]
    return items

  def _render(self, rect):
    if self._current_panel == PanelType.SLA:
      self._speed_limit_layout.render(rect)
    else:
      self._scroller.render(rect)

  def show_event(self):
    self._set_current_panel(PanelType.CRUISE)
    self._scroller.show_event()
    for item in (
      self.phone_speed_source,
      self.carrot_active_speed,
      self.curve_speed_mode,
      self.auto_turn_control,
      self.turn_speed_mode,
      self.navigation_decel_rate,
      self.traffic_stop,
      self.traffic_light_mode,
      self.dec_toggle,
      self.cruise_decel,
      self.atc_decel,
      self.stop_distance,
      self.dynamic_following,
      self.decel_follow_boost,
      self.follow_gap_1,
      self.follow_gap_2,
      self.follow_gap_3,
      self.follow_gap_4,
      self.custom_acc_toggle,
    ):
      item.show_description(True)

  def _set_current_panel(self, panel: PanelType):
    self._current_panel = panel
    if panel == PanelType.SLA:
      self._speed_limit_layout.show_event()

  def _update_state(self):
    super()._update_state()

    if ui_state.CP is not None and ui_state.CP_SP is not None:
      has_long = ui_state.has_longitudinal_control
      has_icbm = False

      for param in ("IntelligentCruiseButtonManagement", "SmartCruiseControlVision", "SmartCruiseControlMap"):
        ui_state.params.remove(param)
      self.icbm_toggle.action_item.set_enabled(False)
      self.scc_v_toggle.action_item.set_enabled(False)
      self.scc_m_toggle.action_item.set_enabled(False)

      if has_long:
        self.custom_acc_toggle.action_item.set_enabled((has_long and not ui_state.CP.pcmCruise) and ui_state.is_offroad())
      else:
        ui_state.params.remove("CustomAccIncrementsEnabled")
        self.custom_acc_toggle.action_item.set_enabled(False)

    else:
      has_icbm = has_long = False
      self.icbm_toggle.action_item.set_enabled(False)
      self.icbm_toggle.set_description(tr(CARROT_CRUISE_POLICY))

    self.dec_toggle.action_item.set_enabled(self._dec_enabled(has_long))
    if self.dec_toggle.action_item.get_state() and not self.dec_toggle.action_item.enabled:
      ui_state.params.remove("DynamicExperimentalControl")
      self.dec_toggle.action_item.set_state(False)

    for toggle in (
      self.phone_speed_source,
      self.carrot_active_speed,
      self.auto_turn_control,
      self.traffic_stop,
    ):
      toggle.action_item.set_enabled(ui_state.is_offroad())

    for item in (
      self.curve_speed_mode,
      self.turn_speed_mode,
      self.navigation_decel_rate,
      self.traffic_light_mode,
      self.cruise_decel,
      self.atc_decel,
      self.stop_distance,
      self.dynamic_following,
      self.decel_follow_boost,
      self.follow_gap_1,
      self.follow_gap_2,
      self.follow_gap_3,
      self.follow_gap_4,
    ):
      item.action_item.set_enabled(ui_state.is_offroad())

    show_custom_acc_desc = False

    if ui_state.is_offroad():
      new_custom_acc_desc = tr(ONROAD_ONLY_DESCRIPTION)
      show_custom_acc_desc = True
    else:
      if has_long or has_icbm:
        if has_long and ui_state.CP.pcmCruise:
          new_custom_acc_desc = tr(ACC_PCMCRUISE_DISABLED_DESCRIPTION)
          show_custom_acc_desc = True
        else:
          new_custom_acc_desc = tr(ACC_ENABLED_DESCRIPTION)
      else:
        new_custom_acc_desc = tr(ACC_NOLONG_DESCRIPTION)
        show_custom_acc_desc = True
        self.custom_acc_toggle.action_item.set_state(False)

    if self.custom_acc_toggle.description != new_custom_acc_desc:
      self.custom_acc_toggle.set_description(new_custom_acc_desc)
      if show_custom_acc_desc:
        self.custom_acc_toggle.show_description(True)

    self._on_custom_acc_toggle(self.custom_acc_toggle.action_item.get_state())

  def _on_custom_acc_toggle(self, state):
    self.custom_acc_short_increment.set_visible(state)
    self.custom_acc_long_increment.set_visible(state)
    self.custom_acc_short_increment.action_item.set_enabled(self.custom_acc_toggle.action_item.enabled)
    self.custom_acc_long_increment.action_item.set_enabled(self.custom_acc_toggle.action_item.enabled)

  @staticmethod
  def _dec_enabled(has_long: bool) -> bool:
    return bool(ui_state.is_offroad() and has_long)

  @staticmethod
  def _auto_percent_label(value: int) -> str:
    return tr("Auto") if value < 0 else f"{value}%"

  @staticmethod
  def _curve_mode_label(value: int) -> str:
    return {
      0: tr("Off"),
      1: tr("Sunny"),
      2: tr("Carrot"),
      3: tr("Fusion"),
    }.get(value, str(value))

  @staticmethod
  def _turn_mode_label(value: int) -> str:
    return {
      0: tr("Off"),
      1: tr("Carrot"),
      2: tr("Sunny"),
      3: tr("Fusion"),
    }.get(value, str(value))

  @staticmethod
  def _traffic_mode_label(value: int) -> str:
    return {
      0: tr("Off"),
      1: tr("Signal"),
      2: tr("Signal+Map"),
      3: tr("Strict"),
    }.get(value, str(value))
