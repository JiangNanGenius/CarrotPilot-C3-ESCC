"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from enum import IntEnum

from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.selfdrive.ui.sunnypilot.layouts.settings.cruise_sub_layouts.speed_limit_settings import SpeedLimitSettingsLayout
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp, option_item_sp, simple_button_item_sp, multiple_button_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller


class PanelType(IntEnum):
  CRUISE = 0
  SLA = 1
  CARROT = 2


ONROAD_ONLY_DESCRIPTION = tr_noop("Start the vehicle to check vehicle compatibility.")


class CruiseLayout(Widget):
  def __init__(self):
    super().__init__()
    self._current_panel = PanelType.CRUISE
    self._speed_limit_layout = SpeedLimitSettingsLayout(lambda: self._set_current_panel(PanelType.CRUISE))
    self._carrot_params = CarrotParams()
    self._carrot_controls = []

    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _carrot_toggle(self, key, title, description=""):
    item = toggle_item_sp(
      title=title,
      description=description,
      initial_state=self._carrot_params.get_bool(key),
      callback=lambda state: self._carrot_params.put_bool(key, state),
    )
    self._carrot_controls.append((item, key, None))
    return item

  def _carrot_selector(self, key, title, labels, values, description=""):
    current = self._carrot_params.get_int(key)
    idx = values.index(current) if current in values else 0

    def _on_select(i):
      if 0 <= i < len(values):
        self._carrot_params.put_int(key, values[i])

    item = multiple_button_item_sp(
      title=title,
      description=description,
      buttons=labels,
      selected_index=idx,
      callback=_on_select,
    )
    self._carrot_controls.append((item, key, values))
    return item

  def _refresh_carrot_controls(self):
    """Re-read the durable Carrot store whenever the panel is opened."""
    for item, key, values in self._carrot_controls:
      if values is None:
        item.action_item.set_state(self._carrot_params.get_bool(key))
      else:
        value = self._carrot_params.get_int(key)
        item.action_item.set_selected_button(values.index(value) if value in values else 0)

  def _initialize_items(self):
    # Carrot 功能（只保留 SunnyPilot 没有的增量项）
    # 限速偏移/安全系数用 SunnyPilot 原生的 Speed Limit 设置（Speed Limit 按钮里），不重复
    self.speed_reference = self._carrot_selector(
      "LongitudinalSpeedReference", "实际速度基准",
      ["轮速", "仪表"], [0, 1],
      description="仪表模式会校正实际纵向目标，使车辆仪表显示贴合设定速度；不使用 GPS。")

    self.carrot_speed_limit = self._carrot_toggle(
      "CarrotSpeedLimitEnable", "导航限速源",
      "把导航 App 提供的限速也加入巡航上限。关闭后只使用下方 Speed Limit 中选择的车辆、地图或视觉限速源。")

    self.carrot_traffic_stop = self._carrot_toggle(
      "CarrotTrafficStopEnable", "红绿灯停车",
      "视觉模型判断前方需要停车时提前减速。仍需驾驶员观察信号灯并随时接管；识别不确定时不要依赖此功能。")

    # Carrot 纵向设定（只保留必要的：跟车距离/停车距离/前加加速度）
    self.carrot_tfollow_gap1 = self._carrot_selector(
      "TFollowGap1", "跟车距离 1 档",
      ["0.8s", "1.1s", "1.4s", "1.7s"], [80, 110, 140, 170],
      description="1 档跟车时间。数值越大，留给前车的距离越远；默认 1.1 秒。")

    self.carrot_tfollow_gap2 = self._carrot_selector(
      "TFollowGap2", "跟车距离 2 档",
      ["1.0s", "1.2s", "1.5s", "1.8s"], [100, 120, 150, 180],
      description="2 档跟车时间。数值越大，留给前车的距离越远；默认 1.2 秒。")

    self.carrot_tfollow_gap3 = self._carrot_selector(
      "TFollowGap3", "跟车距离 3 档",
      ["1.2s", "1.4s", "1.7s", "2.0s"], [120, 140, 170, 200],
      description="3 档跟车时间。数值越大，留给前车的距离越远；默认 1.4 秒。")

    self.carrot_tfollow_gap4 = self._carrot_selector(
      "TFollowGap4", "跟车距离 4 档",
      ["1.4s", "1.6s", "2.0s", "2.4s"], [140, 160, 200, 240],
      description="4 档跟车时间。数值越大，留给前车的距离越远；默认 1.6 秒。")

    self.carrot_stop_distance = self._carrot_selector(
      "StopDistanceCarrot", "停车距离",
      ["3m", "4m", "6m", "8m", "10m"], [300, 400, 600, 800, 1000],
      description="车辆最终停在前车或模型停点之前的目标余量；默认 6 米。识别结果不可靠时仍需驾驶员制动。")

    self.carrot_jlead_factor = self._carrot_selector(
      "JLeadFactor3", "前加加速度平滑",
      ["0", "0.5", "1.0", "2.0", "3.0"], [0, 50, 100, 200, 300],
      description="控制前车加减速变化传给本车的程度。0 最平滑；数值越大反应越直接，也更容易顿挫。默认 0。")

    # SunnyPilot 原生功能
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
      description=tr("Choose how much the cruise set speed changes for short and long button presses."),
      param="CustomAccIncrementsEnabled",
      callback=self._on_custom_acc_toggle)

    self.custom_acc_short_increment = option_item_sp(
      title=tr("Short Press Increment"),
      param="CustomAccShortPressIncrement",
      min_value=1, max_value=10, value_change_step=1,
      description=tr("Cruise-speed change for each short press of the steering-wheel +/- button."),
      inline=True)

    self.custom_acc_long_increment = option_item_sp(
      title=tr("Long Press Increment"),
      param="CustomAccLongPressIncrement",
      value_map={1: 1, 2: 5, 3: 10},
      min_value=1, max_value=3, value_change_step=1,
      description=tr("Cruise-speed change while holding the steering-wheel +/- button."),
      inline=True)

    self.sla_settings_button = simple_button_item_sp(
      button_text=lambda: tr("Speed Limit"),
      button_width=800,
      callback=lambda: self._set_current_panel(PanelType.SLA)
    )

    self.dec_toggle = toggle_item_sp(
      title=tr("Enable Dynamic Experimental Control"),
      description=tr("Enable toggle to allow the model to determine when to use sunnypilot ACC or sunnypilot End to End Longitudinal."),
      param="DynamicExperimentalControl")

    items = [
      self.speed_reference,
      self.carrot_speed_limit,
      self.carrot_traffic_stop,
      self.carrot_tfollow_gap1,
      self.carrot_tfollow_gap2,
      self.carrot_tfollow_gap3,
      self.carrot_tfollow_gap4,
      self.carrot_stop_distance,
      self.carrot_jlead_factor,
      self.dec_toggle,
      self.scc_v_toggle,
      self.scc_m_toggle,
      self.custom_acc_toggle,
      self.custom_acc_short_increment,
      self.custom_acc_long_increment,
      self.sla_settings_button,
    ]
    return items

  def _render(self, rect):
    if self._current_panel == PanelType.SLA:
      self._speed_limit_layout.render(rect)
    else:
      self._scroller.render(rect)

  def show_event(self):
    self._set_current_panel(PanelType.CRUISE)
    self._refresh_carrot_controls()
    self._scroller.show_event()
    self.custom_acc_toggle.show_description(True)

  def _set_current_panel(self, panel: PanelType):
    self._current_panel = panel
    if panel == PanelType.SLA:
      self._speed_limit_layout.show_event()

  def _update_state(self):
    super()._update_state()

    if ui_state.CP is not None and ui_state.CP_SP is not None:
      has_long = ui_state.has_longitudinal_control

      if has_long:
        self.custom_acc_toggle.action_item.set_enabled((not ui_state.CP.pcmCruise) and ui_state.is_offroad())
        self.dec_toggle.action_item.set_enabled(has_long)
        self.scc_v_toggle.action_item.set_enabled(True)
        self.scc_m_toggle.action_item.set_enabled(True)
      else:
        ui_state.params.remove("CustomAccIncrementsEnabled")
        ui_state.params.remove("DynamicExperimentalControl")
        ui_state.params.remove("SmartCruiseControlVision")
        ui_state.params.remove("SmartCruiseControlMap")
        self.custom_acc_toggle.action_item.set_enabled(False)
        self.dec_toggle.action_item.set_enabled(False)
        self.scc_v_toggle.action_item.set_enabled(False)
        self.scc_m_toggle.action_item.set_enabled(False)

    else:
      has_long = False

    show_custom_acc_desc = False

    if ui_state.is_offroad():
      new_custom_acc_desc = tr(ONROAD_ONLY_DESCRIPTION)
      show_custom_acc_desc = True
    else:
      if has_long:
        if has_long and ui_state.CP.pcmCruise:
          new_custom_acc_desc = tr("This feature is not supported on this platform due to vehicle limitations.")
          show_custom_acc_desc = True
        else:
          new_custom_acc_desc = tr("Enable custom Short & Long press increments for cruise speed increase/decrease.")
      else:
        new_custom_acc_desc = tr("This feature can only be used with sunnypilot longitudinal control enabled.")
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
