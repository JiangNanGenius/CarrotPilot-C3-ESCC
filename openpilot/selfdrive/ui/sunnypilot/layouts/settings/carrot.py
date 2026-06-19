"""
Local-only Genius Pilot / Carrot feature settings.
"""
from enum import IntEnum

import pyray as rl

from openpilot.common.params import Params, UnknownKeyName
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import LineSeparatorSP, button_item_sp, option_item_sp, toggle_item_sp
from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog
from openpilot.system.ui.widgets.network import NavButton
from openpilot.system.ui.widgets.scroller_tici import Scroller


class PanelType(IntEnum):
  HOME = 0
  SPEED = 1
  LONGITUDINAL = 2
  AUTOTUNER = 3
  STEERING = 4
  FISHOP = 5
  LOCAL = 6


LOCKED_CONTROL_PARAMS = {
  "CarrotActiveSpeedControlEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotTrafficStopEnabled",
  "FishopAutoOvertakeEnabled",
}

SUNNY_CONFLICT_PARAMS = {
  "IntelligentCruiseButtonManagement",
  "SmartCruiseControlVision",
  "SmartCruiseControlMap",
}


class CarrotLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._available_params = {}
    self._toggles = {}
    self._all_items = []
    self._current_panel = PanelType.HOME

    self._back_button = NavButton(tr("Back"))
    self._back_button.set_click_callback(lambda: self._set_current_panel(PanelType.HOME))

    self._scrollers = {
      PanelType.HOME: Scroller(self._home_items(), line_separator=True, spacing=0),
      PanelType.SPEED: Scroller(self._speed_items(), line_separator=True, spacing=0),
      PanelType.LONGITUDINAL: Scroller(self._longitudinal_items(), line_separator=True, spacing=0),
      PanelType.AUTOTUNER: Scroller(self._autotuner_items(), line_separator=True, spacing=0),
      PanelType.STEERING: Scroller(self._steering_items(), line_separator=True, spacing=0),
      PanelType.FISHOP: Scroller(self._fishop_items(), line_separator=True, spacing=0),
      PanelType.LOCAL: Scroller(self._local_items(), line_separator=True, spacing=0),
    }

  def _param_available(self, param: str) -> bool:
    if param not in self._available_params:
      try:
        self._params.check_key(param)
        self._available_params[param] = True
      except UnknownKeyName:
        self._available_params[param] = False
    return self._available_params[param]

  def _param_bool(self, param: str) -> bool:
    if not self._param_available(param):
      return False
    try:
      return self._params.get_bool(param)
    except UnknownKeyName:
      self._available_params[param] = False
      return False

  def _toggle_enabled(self, param: str, enabled) -> bool:
    if not self._param_available(param):
      return False
    return enabled() if callable(enabled) else bool(enabled)

  def _description(self, param: str, description):
    def wrapped() -> str:
      text = description() if callable(description) else description
      if not self._param_available(param):
        text += "\n\n" + tr("This setting is waiting for the updated Genius Pilot parameter table. Update or reinstall this alpha build before using it.")
      return text
    return wrapped

  def _toggle(self, param: str, title, description, enabled=True):
    toggle = toggle_item_sp(
      title=title,
      description=self._description(param, description),
      param=param if self._param_available(param) else None,
      initial_state=self._param_bool(param),
      enabled=lambda param=param, enabled=enabled: self._toggle_enabled(param, enabled),
    )
    self._toggles[param] = toggle
    self._all_items.append(toggle)
    return toggle

  def _option(self, param: str, title, min_value: int, max_value: int, description, value_change_step: int = 1, label_callback=None):
    item = option_item_sp(
      title=title,
      param=param,
      min_value=min_value,
      max_value=max_value,
      description=self._description(param, description),
      value_change_step=value_change_step,
      enabled=lambda param=param: self._param_available(param) and ui_state.is_offroad(),
      label_callback=label_callback,
    )
    self._all_items.append(item)
    return item

  def _home_button(self, panel: PanelType, title: str, description: str):
    item = button_item_sp(
      title=lambda: tr(title),
      button_text=lambda: tr("OPEN"),
      description=lambda: tr(description),
      callback=lambda panel=panel: self._set_current_panel(panel),
    )
    self._all_items.append(item)
    return item

  def _home_items(self):
    return [
      self._home_button(
        PanelType.SPEED,
        "Speed Limit, Maps, and Navigation",
        "Phone/APN/N, vehicle, and map speed-limit behavior. Map overlay stays optional and does not become speed truth by default.",
      ),
      self._home_button(
        PanelType.LONGITUDINAL,
        "Cruise and Longitudinal Control",
        "Cruise distance, stop distance, lead behavior, Sunny DEC candidate mode, and locked high-risk Carrot control outputs.",
      ),
      self._home_button(
        PanelType.AUTOTUNER,
        "Auto-Tuner",
        "Local learning, recommendation apply gates, and tuning history. Auto apply remains off by default.",
      ),
      self._home_button(
        PanelType.STEERING,
        "Steering and Path",
        "Path offset and steering response values used by the Carrot tuning workflow.",
      ),
      self._home_button(
        PanelType.FISHOP,
        "Fishop Hardware",
        "Lane curve, lidar lane data, blindspot, navigation gate, and auto-overtake evidence. Control output remains locked.",
      ),
      self._home_button(
        PanelType.LOCAL,
        "Local Web and Evidence",
        "Local Carrot Web/API, branch conflict notes, and safe testing reminders. This is local LAN, not cloud pairing.",
      ),
    ]

  def _speed_items(self):
    return [
      self._toggle(
        "CarrotPhoneSpeedLimitEnabled",
        lambda: tr("Phone Speed Limit Source"),
        lambda: tr("Use fresh APN/N, Navipilot, or Carrot phone speed-limit data before the vehicle and map sources. Stale phone data times out automatically."),
        True,
      ),
      self._toggle(
        "CarrotMapOverlayEnabled",
        lambda: tr("Carrot Map Overlay"),
        lambda: tr("Show the optional Carrot route/map overlay. Default is Off; when Off, external map SDKs and map iframes are not loaded."),
        lambda: ui_state.is_offroad(),
      ),
      LineSeparatorSP(40),
      self._toggle(
        "CarrotActiveSpeedControlEnabled",
        lambda: tr("Carrot Active Speed Control"),
        lambda: tr("Locked Off in this alpha. The resolver can show speed-limit evidence, but this control-output path is not enabled yet."),
        False,
      ),
      self._toggle(
        "CarrotAutoTurnControlEnabled",
        lambda: tr("Carrot Auto Turn Slowdown"),
        lambda: tr("Locked Off in this alpha. Turn/curve evidence can be collected, but automatic slowdown must be validated separately."),
        False,
      ),
      self._toggle(
        "CarrotTrafficStopEnabled",
        lambda: tr("Carrot Traffic Light Stop"),
        lambda: tr("Locked Off in this alpha. Traffic-light stop logic is not allowed to command braking until separate real-car validation is complete."),
        False,
      ),
    ]

  def _longitudinal_items(self):
    return [
      self._toggle(
        "DynamicExperimentalControl",
        lambda: tr("Sunny DEC Dynamic Experimental Control"),
        lambda: tr("Candidate advanced longitudinal mode from SunnyPilot. Default is Off. It may switch between classic longitudinal and experimental/E2E behavior, so do not combine it with unvalidated Carrot active speed, turn slowdown, or traffic-light stop outputs."),
        self._dec_enabled,
      ),
      LineSeparatorSP(40),
      self._option(
        "StopDistanceCarrot",
        lambda: tr("Stop Distance"),
        300,
        1200,
        lambda: tr("Carrot stop-distance target used by the tuning workflow. Keep your known-good value until braking logs are reviewed."),
        10,
        lambda v: f"{v / 100:.2f} m",
      ),
      self._option(
        "DynamicTFollow",
        lambda: tr("Dynamic Following"),
        0,
        100,
        lambda: tr("Dynamic following strength. This is a tuning target and should be changed slowly after log review."),
        5,
        lambda v: f"{v}%",
      ),
      self._option(
        "TFollowDecelBoost",
        lambda: tr("Deceleration Follow Boost"),
        0,
        100,
        lambda: tr("Extra follow-distance behavior during deceleration. Higher values can feel more conservative."),
        5,
        lambda v: f"{v}%",
      ),
      LineSeparatorSP(40),
      self._option("TFollowGap1", lambda: tr("Follow Gap 1"), 70, 300, lambda: tr("Time gap preset 1 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      self._option("TFollowGap2", lambda: tr("Follow Gap 2"), 80, 350, lambda: tr("Time gap preset 2 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      self._option("TFollowGap3", lambda: tr("Follow Gap 3"), 90, 400, lambda: tr("Time gap preset 3 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      self._option("TFollowGap4", lambda: tr("Follow Gap 4"), 100, 450, lambda: tr("Time gap preset 4 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      LineSeparatorSP(40),
      self._option("CruiseMaxVals0", lambda: tr("Cruise Accel Limit 0"), 20, 260, lambda: tr("Carrot cruise acceleration table entry. Preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals1", lambda: tr("Cruise Accel Limit 1"), 20, 260, lambda: tr("Carrot cruise acceleration table entry. Preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals2", lambda: tr("Cruise Accel Limit 2"), 20, 240, lambda: tr("Carrot cruise acceleration table entry. Preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals3", lambda: tr("Cruise Accel Limit 3"), 20, 220, lambda: tr("Carrot cruise acceleration table entry. Preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals4", lambda: tr("Cruise Accel Limit 4"), 20, 200, lambda: tr("Carrot cruise acceleration table entry. Preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals5", lambda: tr("Cruise Accel Limit 5"), 20, 180, lambda: tr("Carrot cruise acceleration table entry. Preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals6", lambda: tr("Cruise Accel Limit 6"), 20, 160, lambda: tr("Carrot cruise acceleration table entry. Preserve known-good values unless Auto-Tuner recommends a change."), 5),
      LineSeparatorSP(40),
      self._option("JLeadFactor3", lambda: tr("Lead Response Factor"), -200, 300, lambda: tr("Lead-vehicle response tuning target. Change only after comparing braking and lead-distance logs."), 10),
    ]

  def _autotuner_items(self):
    return [
      self._toggle(
        "CarrotLearningActive",
        lambda: tr("Auto-Tuner Learning"),
        lambda: tr("Collect local driving evidence and prepare tuning recommendations. This does not apply changes by itself."),
        True,
      ),
      self._toggle(
        "CarrotLearningAutoApply",
        lambda: tr("Auto-Tuner Auto Apply"),
        lambda: tr("Default is Off. Auto-apply is available only while parked and should stay Off until recommendations are reviewed after real drives."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "CarrotTunerApplyLat",
        lambda: tr("Apply Lateral Recommendations"),
        lambda: tr("Allow Auto-Tuner to apply lateral tuning recommendations when a manual or parked apply action is used."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "CarrotTunerApplyLong",
        lambda: tr("Apply Longitudinal Recommendations"),
        lambda: tr("Allow Auto-Tuner to apply longitudinal tuning recommendations when a manual or parked apply action is used."),
        lambda: ui_state.is_offroad(),
      ),
      LineSeparatorSP(40),
      self._tracked_item(button_item_sp(
        title=lambda: tr("Apply Pending Recommendation"),
        button_text=lambda: tr("APPLY"),
        description=lambda: tr("Manual apply is blocked while onroad. Review the recommendation first; this changes stored tuning values."),
        callback=lambda: self._confirm_flag("CarrotLearningApply", tr("Apply pending Auto-Tuner recommendation?")),
        enabled=lambda: ui_state.is_offroad(),
      )),
      self._tracked_item(button_item_sp(
        title=lambda: tr("Ignore Pending Recommendation"),
        button_text=lambda: tr("IGNORE"),
        description=lambda: tr("Clear the current recommendation without changing tuning values."),
        callback=lambda: self._confirm_flag("CarrotLearningIgnore", tr("Ignore the pending Auto-Tuner recommendation?")),
        enabled=lambda: ui_state.is_offroad(),
      )),
      self._tracked_item(button_item_sp(
        title=lambda: tr("Clear Learning Data"),
        button_text=lambda: tr("CLEAR"),
        description=lambda: tr("Clear collected Auto-Tuner learning data and pending recommendations. Historical applied records are kept unless factory reset is used."),
        callback=lambda: self._confirm_flag("CarrotLearningClear", tr("Clear Auto-Tuner learning data?")),
        enabled=lambda: ui_state.is_offroad(),
      )),
      self._tracked_item(button_item_sp(
        title=lambda: tr("Factory Reset Tuning History"),
        button_text=lambda: tr("RESET"),
        description=lambda: tr("Clear Auto-Tuner history and recommendations. This does not restore every driving parameter by itself."),
        callback=lambda: self._confirm_flag("CarrotTunerFactoryReset", tr("Factory reset Auto-Tuner history?")),
        enabled=lambda: ui_state.is_offroad(),
      )),
    ]

  def _steering_items(self):
    return [
      self._option(
        "PathOffset",
        lambda: tr("Path Offset"),
        -150,
        150,
        lambda: tr("Lane/path lateral offset used by Carrot tuning. Zero is neutral; keep your known-good value unless testing carefully."),
        5,
        lambda v: f"{v / 100:.2f} m",
      ),
      self._option(
        "SteerActuatorDelay",
        lambda: tr("Steer Actuator Delay"),
        0,
        200,
        lambda: tr("Additional steering actuator delay target used by Auto-Tuner. Change only while parked and after reviewing logs."),
        5,
        lambda v: f"{v / 100:.2f} s",
      ),
      self._option(
        "SteerRatioRate",
        lambda: tr("Steer Ratio Rate"),
        50,
        150,
        lambda: tr("Steering ratio scaling target. 100 is neutral."),
        5,
        lambda v: f"{v}%",
      ),
    ]

  def _fishop_items(self):
    return [
      self._toggle(
        "FishopLaneCurveEnabled",
        lambda: tr("Fishop Lane Curve Input"),
        lambda: tr("Enable local Fishop lane-curve sensor input collection. This is an input gate only and does not enable automatic lane changes."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "FishopLidarBlindspotEnabled",
        lambda: tr("Fishop Lidar Blindspot Input"),
        lambda: tr("Enable local Fishop lidar blindspot input collection. This is evidence/input data until road-tested gates are added."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "FishopLidarLaneDataEnabled",
        lambda: tr("Fishop Lidar Lane Data Input"),
        lambda: tr("Enable local Fishop lidar lane-data input collection. This does not modify steering or lane-change output in this alpha."),
        lambda: ui_state.is_offroad(),
      ),
      LineSeparatorSP(40),
      self._toggle(
        "FishopAutoOvertakeEnabled",
        lambda: tr("Fishop Auto Overtake"),
        lambda: tr("Locked Off in this alpha. Lane and blindspot hardware can be logged, but automatic overtaking is not connected to control output."),
        False,
      ),
    ]

  def _local_items(self):
    return [
      self._tracked_item(button_item_sp(
        title=lambda: tr("Local Carrot Web"),
        button_text=lambda: tr("INFO"),
        description=lambda: tr("Use the device LAN address with port 7000 for the local Carrot Web/API page. This is a local service, not cloud pairing."),
        callback=self._show_web_info,
      )),
      self._tracked_item(button_item_sp(
        title=lambda: tr("Branch Conflict Notes"),
        button_text=lambda: tr("INFO"),
        description=lambda: tr("Sunny DEC is a candidate advanced longitudinal feature. ICBM, SCC-V, and SCC-M overlap more directly with Carrot cruise behavior and remain hidden or inert in this personal alpha."),
        callback=self._show_conflict_info,
      )),
    ]

  def _tracked_item(self, item):
    self._all_items.append(item)
    return item

  def _dec_enabled(self) -> bool:
    return (self._param_available("DynamicExperimentalControl") and ui_state.is_offroad()
            and ui_state.CP is not None and ui_state.has_longitudinal_control
            and not any(self._param_bool(param) for param in LOCKED_CONTROL_PARAMS))

  def _set_current_panel(self, panel: PanelType):
    self._current_panel = panel
    self._scrollers[self._current_panel].show_event()
    self._show_descriptions()

  def _confirm_flag(self, param: str, message: str):
    if not self._param_available(param):
      gui_app.push_widget(alert_dialog(tr("This setting is waiting for the updated Genius Pilot parameter table. Update or reinstall this alpha build before using it.")))
      return

    def _callback(result: DialogResult):
      if result == DialogResult.CONFIRM:
        self._params.put_bool(param, True)

    gui_app.push_widget(ConfirmDialog(message, tr("Confirm"), callback=_callback))

  @staticmethod
  def _show_web_info():
    gui_app.push_widget(alert_dialog(tr("Connect to the device on the same local network and open http://<device-ip>:7000. For your current bench device this is usually http://192.168.100.174:7000.")))

  @staticmethod
  def _show_conflict_info():
    gui_app.push_widget(alert_dialog(tr("Conflict policy: keep Sunny DEC as an off-by-default candidate; keep ICBM, SCC-V, and SCC-M hidden or inert because they can overlap with Carrot button, curve, map, and speed-limit control paths.")))

  def _show_descriptions(self):
    for item in self._all_items:
      if hasattr(item, "show_description"):
        item.show_description(True)

  def _update_state(self):
    super()._update_state()

    for param in SUNNY_CONFLICT_PARAMS:
      self._params.remove(param)

    for param in LOCKED_CONTROL_PARAMS:
      if self._param_bool(param):
        self._params.put_bool(param, False)

    if self._param_bool("DynamicExperimentalControl") and not self._dec_enabled():
      self._params.put_bool("DynamicExperimentalControl", False)

    for param, toggle in self._toggles.items():
      toggle.action_item.set_state(self._param_bool(param))
      if param in LOCKED_CONTROL_PARAMS:
        toggle.action_item.set_enabled(False)

  def _render(self, rect):
    if self._current_panel == PanelType.HOME:
      self._scrollers[self._current_panel].render(rect)
      return

    self._back_button.set_position(rect.x, rect.y + 20)
    self._back_button.render()
    content_rect = rl.Rectangle(rect.x, rect.y + self._back_button.rect.height + 40,
                                rect.width, rect.height - self._back_button.rect.height - 40)
    self._scrollers[self._current_panel].render(content_rect)

  def show_event(self):
    self._set_current_panel(PanelType.HOME)
    self._show_descriptions()
