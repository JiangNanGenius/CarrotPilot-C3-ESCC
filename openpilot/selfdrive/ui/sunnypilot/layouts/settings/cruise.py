"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from enum import IntEnum

from openpilot.selfdrive.ui.sunnypilot.layouts.settings.cruise_sub_layouts.speed_limit_settings import SpeedLimitSettingsLayout
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp, option_item_sp, simple_button_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller


class PanelType(IntEnum):
  CRUISE = 0
  SLA = 1


ICBM_DESC = tr_noop("When enabled, Genius Pilot will attempt to manage the built-in cruise control buttons " +
                    "by emulating button presses for limited longitudinal control.")
ICMB_UNAVAILABLE = tr_noop("Intelligent Cruise Button Management is currently unavailable on this platform.")
ICMB_UNAVAILABLE_LONG_AVAILABLE = tr_noop("Disable the Genius Pilot Longitudinal Control (alpha) toggle to allow Intelligent Cruise Button Management.")
ICMB_UNAVAILABLE_LONG_UNAVAILABLE = tr_noop("Genius Pilot Longitudinal Control is the default longitudinal control for this platform.")
CARROT_CRUISE_POLICY = tr_noop("This personal build keeps cruise-speed behavior aligned with CarrotPilot. SunnyPilot ICBM, SCC-V, and SCC-M stay hidden. Sunny DEC is available in Cruise and Super Advanced settings.")
DEC_DESCRIPTION = tr_noop("Sunny dynamic experimental control. It can switch between classic longitudinal and E2E-style behavior when available.")

ACC_ENABLED_DESCRIPTION = tr_noop("Enable custom Short & Long press increments for cruise speed increase/decrease.")
ACC_NOLONG_DESCRIPTION = tr_noop("This feature can only be used with Genius Pilot longitudinal control enabled.")
ACC_PCMCRUISE_DISABLED_DESCRIPTION = tr_noop("This feature is not supported on this platform due to vehicle limitations.")
ONROAD_ONLY_DESCRIPTION = tr_noop("Start the vehicle to check vehicle compatibility.")


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

    self.dec_toggle = toggle_item_sp(
      title=lambda: tr("Sunny DEC Dynamic Experimental Control"),
      description=lambda: tr(DEC_DESCRIPTION),
      param="DynamicExperimentalControl")

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
      self.sla_settings_button,
      self.dec_toggle,
      self.stop_distance,
      self.dynamic_following,
      self.decel_follow_boost,
      self.follow_gap_1,
      self.follow_gap_2,
      self.follow_gap_3,
      self.follow_gap_4,
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
    self.dec_toggle.show_description(True)
    self.stop_distance.show_description(True)
    self.dynamic_following.show_description(True)
    self.custom_acc_toggle.show_description(True)

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

    for item in (
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
