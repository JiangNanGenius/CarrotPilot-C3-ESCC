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


PRECONTROL_FEATURE_PARAMS = {
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
    if not self._param_available(param):
      item = button_item_sp(
        title=title,
        button_text=lambda: tr("WAIT"),
        description=self._description(param, description),
        enabled=False,
      )
      self._all_items.append(item)
      return item

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

  @staticmethod
  def _percent_label(value: int) -> str:
    return f"{value}%"

  @staticmethod
  def _signed_percent_label(value: int) -> str:
    return f"{value:+d}%"

  @staticmethod
  def _kph_label(value: int) -> str:
    return f"{value} km/h"

  @staticmethod
  def _seconds_100_label(value: int) -> str:
    return f"{value / 100:.2f} s"

  @staticmethod
  def _distance_100_label(value: int) -> str:
    return f"{value / 100:.2f} m"

  @staticmethod
  def _mps_100_label(value: int) -> str:
    return f"{value / 100:.2f} m/s"

  @staticmethod
  def _signed_distance_100_label(value: int) -> str:
    return f"{value / 100:+.2f} m"

  @staticmethod
  def _auto_percent_label(value: int) -> str:
    return "Auto" if value < 0 else f"{value}%"

  @staticmethod
  def _curve_mode_label(value: int) -> str:
    return {
      0: "Off",
      1: "Sunny",
      2: "Carrot",
      3: "Balanced",
    }.get(value, str(value))

  @staticmethod
  def _turn_mode_label(value: int) -> str:
    return {
      0: "Off",
      1: "Carrot",
      2: "Sunny",
      3: "Balanced",
    }.get(value, str(value))

  @staticmethod
  def _eco_mode_label(value: int) -> str:
    return {
      0: "Off",
      1: "Mild",
      2: "Normal",
      3: "Strong",
    }.get(value, str(value))

  @staticmethod
  def _driving_mode_label(value: int) -> str:
    return {
      0: "Eco",
      1: "Comfort",
      2: "Normal",
      3: "Carrot",
      4: "Sport",
      5: "Auto",
    }.get(value, str(value))

  @staticmethod
  def _traffic_mode_label(value: int) -> str:
    return {
      0: "Off",
      1: "Signal",
      2: "Signal+Map",
      3: "Strict",
    }.get(value, str(value))

  @staticmethod
  def _toggle_label(value: int) -> str:
    return "On" if value else "Off"

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
        "Cruise distance, stop distance, lead behavior, Sunny DEC, ATC, driving mode, and Carrot active speed settings.",
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
        "Lane curve, lidar lane data, blindspot, navigation gate, and auto-overtake settings for the extra hardware.",
      ),
      self._home_button(
        PanelType.LOCAL,
        "Local Web and Diagnostics",
        "Local Carrot Web/API, branch relationship notes, and diagnostics. This is local LAN, not cloud pairing.",
      ),
    ]

  def _speed_items(self):
    return [
      self._toggle(
        "CarrotPhoneSpeedLimitEnabled",
        lambda: tr("Phone Speed Limit Source"),
        lambda: tr("Use APN/N, Navipilot, or Carrot phone speed-limit data before vehicle and map speed-limit sources. Stale phone data times out automatically."),
        True,
      ),
      self._toggle(
        "CarrotMapOverlayEnabled",
        lambda: tr("Carrot Map Overlay"),
        lambda: tr("Show the optional Carrot route/map overlay. Default is Off; when Off, external map SDKs and map iframes are not loaded."),
        lambda: ui_state.is_offroad(),
      ),
      self._option(
        "CurveSpeedControlMode",
        lambda: tr("Curve Speed Control Mode"),
        0,
        3,
        lambda: tr("Select the curve-speed strategy: Off, Sunny, Carrot, or Balanced. Balanced keeps Sunny curve quality and Carrot navigation/phone inputs together."),
        1,
        self._curve_mode_label,
      ),
      self._option(
        "AutoCurveSpeedLowerLimit",
        lambda: tr("Curve Speed Lower Limit"),
        10,
        120,
        lambda: tr("Lowest target speed allowed for automatic curve slowdown."),
        5,
        self._kph_label,
      ),
      self._option(
        "AutoCurveSpeedFactor",
        lambda: tr("Curve Speed Factor"),
        50,
        250,
        lambda: tr("Main Carrot curve-speed scaling value. Higher values make curve detection more sensitive, usually lowering the curve target speed and slowing earlier. If the lower-limit speed is already reached, raising this may have no further effect."),
        5,
        self._percent_label,
      ),
      self._option(
        "AutoCurveSpeedAggressiveness",
        lambda: tr("Curve Speed Aggressiveness"),
        50,
        200,
        lambda: tr("Secondary Carrot-compatible curve knob. Current active curve slowdown primarily uses Curve Speed Factor; keep this near 100 unless a later controller or Auto-Tuner recommendation explicitly uses it."),
        5,
        self._percent_label,
      ),
      self._option(
        "AutoNaviSpeedDecelRate",
        lambda: tr("Navigation Decel Rate"),
        50,
        300,
        lambda: tr("Navigation-event deceleration scale. Lower values start slowing from farther away; higher values delay the slowdown and can feel later/stronger."),
        5,
        self._percent_label,
      ),
      LineSeparatorSP(40),
      self._toggle(
        "CarrotActiveSpeedControlEnabled",
        lambda: tr("Carrot Active Speed Control"),
        lambda: tr("Allow Carrot speed-limit, navigation, and model-speed logic to adjust the cruise target."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "CarrotAutoTurnControlEnabled",
        lambda: tr("Carrot Auto Turn Slowdown"),
        lambda: tr("Use Carrot navigation and curve information to slow for turns and junctions."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "CarrotTrafficStopEnabled",
        lambda: tr("Carrot Traffic Light Stop"),
        lambda: tr("Use Carrot traffic-light input for red-light stop behavior."),
        lambda: ui_state.is_offroad(),
      ),
      self._option(
        "TrafficLightDetectMode",
        lambda: tr("Traffic Light Detect Mode"),
        0,
        3,
        lambda: tr("Select the traffic-light detection mode used by Carrot red-light stop."),
        1,
        self._traffic_mode_label,
      ),
      self._option(
        "TrafficStopDistanceAdjust",
        lambda: tr("Traffic Stop Distance Adjust"),
        -500,
        500,
        lambda: tr("Fine adjustment for red-light stopping distance. Negative values stop earlier."),
        10,
        self._signed_distance_100_label,
      ),
      self._toggle(
        "CarrotRainWet",
        lambda: tr("Rain / Wet Road Mode"),
        lambda: tr("Use more conservative Carrot speed and following behavior for wet roads."),
        lambda: ui_state.is_offroad(),
      ),
    ]

  def _longitudinal_items(self):
    return [
      self._toggle(
        "DynamicExperimentalControl",
        lambda: tr("Sunny DEC Dynamic Experimental Control"),
        lambda: tr("Sunny dynamic experimental control. It can switch between classic longitudinal and E2E-style behavior when available."),
        self._dec_enabled,
      ),
      LineSeparatorSP(40),
      self._option(
        "MyDrivingMode",
        lambda: tr("Carrot Driving Mode"),
        0,
        5,
        lambda: tr("Primary Carrot driving style preset for cruise, following, and acceleration behavior."),
        1,
        self._driving_mode_label,
      ),
      self._option(
        "MyDrivingModeAuto",
        lambda: tr("Auto Driving Mode"),
        0,
        1,
        lambda: tr("Allow Carrot to switch driving mode automatically from road and navigation context."),
        1,
        self._toggle_label,
      ),
      self._option(
        "CruiseEcoControl",
        lambda: tr("Cruise Eco Control"),
        0,
        3,
        lambda: tr("Cruise economy strength. Higher values soften acceleration and can reduce unnecessary speed changes."),
        1,
        self._eco_mode_label,
      ),
      self._option(
        "CarrotCruiseDecel",
        lambda: tr("Cruise Decel"),
        -1,
        200,
        lambda: tr("Carrot cruise deceleration target. Auto uses the current Carrot default."),
        5,
        self._auto_percent_label,
      ),
      self._option(
        "CarrotCruiseAtcDecel",
        lambda: tr("ATC Decel"),
        -1,
        200,
        lambda: tr("Deceleration target used by Auto Turn Control. Auto uses the current Carrot default."),
        5,
        self._auto_percent_label,
      ),
      LineSeparatorSP(40),
      self._option(
        "StopDistanceCarrot",
        lambda: tr("Stop Distance"),
        300,
        1200,
        lambda: tr("Carrot stop-distance target for longitudinal stopping behavior."),
        10,
        lambda v: f"{v / 100:.2f} m",
      ),
      self._option(
        "DynamicTFollow",
        lambda: tr("Dynamic Following"),
        0,
        100,
        lambda: tr("Dynamic following strength for Carrot longitudinal behavior."),
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
      self._option(
        "TFollowSpeedFactor",
        lambda: tr("Speed Follow Factor"),
        -100,
        100,
        lambda: tr("Adjusts following distance by speed. Positive values add more gap at higher speeds."),
        5,
        self._signed_percent_label,
      ),
      self._option(
        "DynamicTFollowLC",
        lambda: tr("Lane Change Follow"),
        50,
        200,
        lambda: tr("Following-distance adjustment around lane-change behavior."),
        5,
        self._percent_label,
      ),
      self._option(
        "EnableSpeedTF",
        lambda: tr("Speed-Based Follow"),
        0,
        1,
        lambda: tr("Enable speed-based following-distance adjustment."),
        1,
        self._toggle_label,
      ),
      LineSeparatorSP(40),
      self._option("TFollowGap1", lambda: tr("Follow Gap 1"), 70, 300, lambda: tr("Time gap preset 1 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      self._option("TFollowGap2", lambda: tr("Follow Gap 2"), 80, 350, lambda: tr("Time gap preset 2 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      self._option("TFollowGap3", lambda: tr("Follow Gap 3"), 90, 400, lambda: tr("Time gap preset 3 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      self._option("TFollowGap4", lambda: tr("Follow Gap 4"), 100, 450, lambda: tr("Time gap preset 4 used by Carrot tuning."), 5, lambda v: f"{v / 100:.2f} s"),
      LineSeparatorSP(40),
      self._option("CruiseMaxVals0", lambda: tr("Cruise Accel Limit 0 km/h"), 20, 260, lambda: tr("Maximum requested cruise acceleration near 0 km/h, in 0.01 m/s^2 units. Higher feels stronger; preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals1", lambda: tr("Cruise Accel Limit 10 km/h"), 20, 260, lambda: tr("Maximum requested cruise acceleration near 10 km/h, in 0.01 m/s^2 units. Higher feels stronger; preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals2", lambda: tr("Cruise Accel Limit 40 km/h"), 20, 240, lambda: tr("Maximum requested cruise acceleration near 40 km/h, in 0.01 m/s^2 units. Higher feels stronger; preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals3", lambda: tr("Cruise Accel Limit 60 km/h"), 20, 220, lambda: tr("Maximum requested cruise acceleration near 60 km/h, in 0.01 m/s^2 units. Higher feels stronger; preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals4", lambda: tr("Cruise Accel Limit 80 km/h"), 20, 200, lambda: tr("Maximum requested cruise acceleration near 80 km/h, in 0.01 m/s^2 units. Higher feels stronger; preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals5", lambda: tr("Cruise Accel Limit 110 km/h"), 20, 180, lambda: tr("Maximum requested cruise acceleration near 110 km/h, in 0.01 m/s^2 units. Higher feels stronger; preserve known-good values unless Auto-Tuner recommends a change."), 5),
      self._option("CruiseMaxVals6", lambda: tr("Cruise Accel Limit 140 km/h"), 20, 160, lambda: tr("Maximum requested cruise acceleration near 140 km/h, in 0.01 m/s^2 units. Higher feels stronger; preserve known-good values unless Auto-Tuner recommends a change."), 5),
      LineSeparatorSP(40),
      self._option("LongTuningKpV", lambda: tr("Longitudinal Kp"), 0, 300, lambda: tr("Carrot longitudinal proportional gain. Higher reacts harder to speed error; lower can reduce overshoot or oscillation."), 5, self._percent_label),
      self._option("LongTuningKiV", lambda: tr("Longitudinal Ki"), 0, 300, lambda: tr("Carrot longitudinal integral gain scaling."), 5, self._percent_label),
      self._option("LongTuningKf", lambda: tr("Longitudinal Kf"), 0, 300, lambda: tr("Carrot longitudinal feed-forward scaling."), 5, self._percent_label),
      self._option("LongActuatorDelay", lambda: tr("Long Actuator Delay"), 0, 200, lambda: tr("Longitudinal actuator delay in 0.01 s units. Higher anticipates slower actuator response; too high may feel early."), 5, self._seconds_100_label),
      self._option("VEgoStopping", lambda: tr("Stopping Speed Threshold"), 0, 150, lambda: tr("Stopping detection threshold in 0.01 m/s units. Higher can smooth harsh stops; too high can enter stopping behavior early."), 5, self._mps_100_label),
      self._option("RadarReactionFactor", lambda: tr("Radar Reaction Factor"), 0, 300, lambda: tr("Lead-vehicle radar reaction strength. Higher values react more strongly to lead changes."), 5, self._percent_label),
      self._option("JLeadFactor3", lambda: tr("Lead Response Factor"), -200, 300, lambda: tr("Lead-vehicle response tuning factor."), 10),
      self._option("AChangeCostStarting", lambda: tr("Accel Change Cost"), 0, 100, lambda: tr("Smoothness cost for acceleration changes at the start of a maneuver."), 1),
    ]

  def _autotuner_items(self):
    return [
      self._toggle(
        "CarrotLearningActive",
        lambda: tr("Auto-Tuner Learning"),
        lambda: tr("Collect local driving data and prepare tuning recommendations. This does not apply changes by itself."),
        True,
      ),
      self._toggle(
        "CarrotLearningAutoApply",
        lambda: tr("Auto-Tuner Auto Apply"),
        lambda: tr("Automatically apply Auto-Tuner recommendations while parked."),
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
        "TurnSpeedControlMode",
        lambda: tr("Turn Speed Control Mode"),
        0,
        3,
        lambda: tr("Select the turn-speed strategy: Off, Carrot, Sunny, or Balanced."),
        1,
        self._turn_mode_label,
      ),
      self._option(
        "AutoTurnControl",
        lambda: tr("Auto Turn Control"),
        0,
        1,
        lambda: tr("Enable Carrot automatic turn-control behavior."),
        1,
        self._toggle_label,
      ),
      self._option(
        "AutoTurnControlSpeedTurn",
        lambda: tr("Turn Control Speed"),
        5,
        80,
        lambda: tr("Target turn-control speed used around tight turns and intersections."),
        5,
        self._kph_label,
      ),
      self._option(
        "AutoTurnControlTurnEnd",
        lambda: tr("Turn End Distance"),
        1,
        30,
        lambda: tr("Distance threshold used to end automatic turn-control behavior."),
        1,
        lambda v: f"{v} m",
      ),
      self._option(
        "AutoTurnMapChange",
        lambda: tr("Map Turn Adaptation"),
        0,
        1,
        lambda: tr("Allow map and navigation events to adjust turn-control behavior."),
        1,
        self._toggle_label,
      ),
      LineSeparatorSP(40),
      self._option(
        "PathOffset",
        lambda: tr("Path Offset"),
        -150,
        150,
        lambda: tr("Lane/path lateral offset used by Carrot tuning. Zero is neutral; negative shifts left, positive shifts right."),
        5,
        lambda v: f"{v / 100:.2f} m",
      ),
      self._option(
        "SteerActuatorDelay",
        lambda: tr("Steer Actuator Delay"),
        0,
        200,
        lambda: tr("Additional steering actuator delay target used by Auto-Tuner. Zero uses live/default delay; higher adds custom delay compensation."),
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
      self._option(
        "UseLaneLineSpeed",
        lambda: tr("Lane Line Speed"),
        0,
        1,
        lambda: tr("Use lane-line information in Carrot speed behavior."),
        1,
        self._toggle_label,
      ),
      self._option(
        "UseLaneLineCurveSpeed",
        lambda: tr("Lane Line Curve Speed"),
        0,
        1,
        lambda: tr("Use lane-line curvature as an input for curve-speed behavior."),
        1,
        self._toggle_label,
      ),
    ]

  def _fishop_items(self):
    return [
      self._toggle(
        "FishopLaneCurveEnabled",
        lambda: tr("Fishop Lane Curve Input"),
        lambda: tr("Enable Fishop lane-curve sensor input."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "FishopLidarBlindspotEnabled",
        lambda: tr("Fishop Lidar Blindspot Input"),
        lambda: tr("Enable Fishop lidar blindspot input."),
        lambda: ui_state.is_offroad(),
      ),
      self._toggle(
        "FishopLidarLaneDataEnabled",
        lambda: tr("Fishop Lidar Lane Data Input"),
        lambda: tr("Enable Fishop lidar lane-data input."),
        lambda: ui_state.is_offroad(),
      ),
      LineSeparatorSP(40),
      self._toggle(
        "FishopAutoOvertakeEnabled",
        lambda: tr("Fishop Auto Overtake"),
        lambda: tr("Enable Fishop automatic overtake behavior using lane and blindspot inputs."),
        lambda: ui_state.is_offroad(),
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
        description=lambda: tr("Review how Sunny DEC, NNLC, Carrot speed logic, ATC, and Fishop hardware settings relate to each other."),
        callback=self._show_conflict_info,
      )),
    ]

  def _tracked_item(self, item):
    self._all_items.append(item)
    return item

  def _dec_enabled(self) -> bool:
    return (self._param_available("DynamicExperimentalControl") and ui_state.is_offroad()
            and ui_state.CP is not None and ui_state.has_longitudinal_control)

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
    gui_app.push_widget(alert_dialog(tr("Sunny DEC controls longitudinal mode selection. Carrot speed logic, ATC, red-light stop, and Fishop hardware settings are separate Genius Pilot feature paths. ICBM, SCC-V, and SCC-M are hidden here so cruise behavior stays Carrot-style.")))

  def _show_descriptions(self):
    for item in self._all_items:
      if hasattr(item, "show_description"):
        item.show_description(True)

  def _update_state(self):
    super()._update_state()

    for param in SUNNY_CONFLICT_PARAMS:
      self._params.remove(param)

    if self._param_bool("DynamicExperimentalControl") and not self._dec_enabled():
      self._params.put_bool("DynamicExperimentalControl", False)

    for param, toggle in self._toggles.items():
      toggle.action_item.set_state(self._param_bool(param))

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
