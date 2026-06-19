"""
Local-only Genius Pilot / Carrot feature settings.
"""
from openpilot.common.params import Params, UnknownKeyName
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.sunnypilot.widgets.list_view import LineSeparatorSP, button_item_sp, toggle_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.confirm_dialog import alert_dialog
from openpilot.system.ui.widgets.scroller_tici import Scroller


LOCKED_CONTROL_PARAMS = {
  "CarrotActiveSpeedControlEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotTrafficStopEnabled",
  "FishopAutoOvertakeEnabled",
}


class CarrotLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._toggles = {}
    self._available_params = {}
    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

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

  def _initialize_items(self):
    self._toggle_defs = {
      "CarrotPhoneSpeedLimitEnabled": (
        lambda: tr("Phone Speed Limit Source"),
        lambda: tr("Use fresh APN/N, Navipilot, or Carrot phone speed-limit data before the vehicle and map sources. Stale phone data times out automatically."),
        True,
      ),
      "CarrotMapOverlayEnabled": (
        lambda: tr("Carrot Map Overlay"),
        lambda: tr("Show the optional Carrot route/map overlay. Default is Off; when Off, external map SDKs and map iframes are not loaded."),
        lambda: ui_state.is_offroad(),
      ),
      "CarrotLearningActive": (
        lambda: tr("Auto-Tuner Learning"),
        lambda: tr("Collect local driving evidence and prepare tuning recommendations. This does not apply changes by itself."),
        True,
      ),
      "CarrotLearningAutoApply": (
        lambda: tr("Auto-Tuner Auto Apply"),
        lambda: tr("Default is Off. Auto-apply is available only while parked and should stay Off until recommendations are reviewed after real drives."),
        lambda: ui_state.is_offroad(),
      ),
      "CarrotTunerApplyLat": (
        lambda: tr("Apply Lateral Recommendations"),
        lambda: tr("Allow Auto-Tuner to apply lateral tuning recommendations when a manual or parked apply action is used."),
        lambda: ui_state.is_offroad(),
      ),
      "CarrotTunerApplyLong": (
        lambda: tr("Apply Longitudinal Recommendations"),
        lambda: tr("Allow Auto-Tuner to apply longitudinal tuning recommendations when a manual or parked apply action is used."),
        lambda: ui_state.is_offroad(),
      ),
      "FishopLaneCurveEnabled": (
        lambda: tr("Fishop Lane Curve Input"),
        lambda: tr("Enable local Fishop lane-curve sensor input collection. This is an input gate only and does not enable automatic lane changes."),
        lambda: ui_state.is_offroad(),
      ),
      "FishopLidarBlindspotEnabled": (
        lambda: tr("Fishop Lidar Blindspot Input"),
        lambda: tr("Enable local Fishop lidar blindspot input collection. This is evidence/input data until road-tested gates are added."),
        lambda: ui_state.is_offroad(),
      ),
      "FishopLidarLaneDataEnabled": (
        lambda: tr("Fishop Lidar Lane Data Input"),
        lambda: tr("Enable local Fishop lidar lane-data input collection. This does not modify steering or lane-change output in this alpha."),
        lambda: ui_state.is_offroad(),
      ),
      "CarrotActiveSpeedControlEnabled": (
        lambda: tr("Carrot Active Speed Control"),
        lambda: tr("Locked Off in this alpha. The resolver can show speed-limit evidence, but this control-output path is not enabled yet."),
        False,
      ),
      "CarrotAutoTurnControlEnabled": (
        lambda: tr("Carrot Auto Turn Slowdown"),
        lambda: tr("Locked Off in this alpha. Turn/curve evidence can be collected, but automatic slowdown must be validated separately."),
        False,
      ),
      "CarrotTrafficStopEnabled": (
        lambda: tr("Carrot Traffic Light Stop"),
        lambda: tr("Locked Off in this alpha. Traffic-light stop logic is not allowed to command braking until separate real-car validation is complete."),
        False,
      ),
      "FishopAutoOvertakeEnabled": (
        lambda: tr("Fishop Auto Overtake"),
        lambda: tr("Locked Off in this alpha. Lane and blindspot hardware can be logged, but automatic overtaking is not connected to control output."),
        False,
      ),
    }

    items = []
    for param, (title, description, enabled) in self._toggle_defs.items():
      toggle = toggle_item_sp(
        title=title,
        description=self._description(param, description),
        param=param if self._param_available(param) else None,
        initial_state=self._param_bool(param),
        enabled=lambda param=param, enabled=enabled: self._toggle_enabled(param, enabled),
      )
      self._toggles[param] = toggle
      items.append(toggle)

      if param in {"CarrotLearningAutoApply", "CarrotTunerApplyLong", "FishopLidarLaneDataEnabled"}:
        items.append(LineSeparatorSP(40))

    self._web_info_button = button_item_sp(
      title=lambda: tr("Local Carrot Web"),
      button_text=lambda: tr("INFO"),
      description=lambda: tr("Use the device LAN address with port 7000 for the local Carrot Web/API page. This is a local service, not cloud pairing."),
      callback=self._show_web_info,
    )
    items.append(self._web_info_button)

    return items

  @staticmethod
  def _show_web_info():
    gui_app.push_widget(alert_dialog(tr("Connect to the device on the same local network and open http://<device-ip>:7000. For your current bench device this is usually http://192.168.100.174:7000.")))

  def _update_state(self):
    super()._update_state()

    for param in LOCKED_CONTROL_PARAMS:
      if self._param_bool(param):
        self._params.put_bool(param, False)

    for param, toggle in self._toggles.items():
      toggle.action_item.set_state(self._param_bool(param))
      if param in LOCKED_CONTROL_PARAMS:
        toggle.action_item.set_enabled(False)

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
    for toggle in self._toggles.values():
      toggle.show_description(True)
    self._web_info_button.show_description(True)
