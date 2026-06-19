import pyray as rl

from openpilot.common.params import Params
from openpilot.system.ui.lib.scroll_panel2 import ScrollState
from openpilot.system.ui.widgets.scroller import NavScroller
from openpilot.selfdrive.ui.mici.widgets.button import BigButton
from openpilot.selfdrive.ui.mici.layouts.settings.toggles import TogglesLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.network.network_layout import NetworkLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.device import DeviceLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.developer import DeveloperLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.software import SoftwareLayoutMici
from openpilot.system.ui.lib.application import gui_app, FontWeight, MousePos

TAP_OPEN_DELAY = 0.12
TAP_MAX_MOVE = 18


class SettingsBigButton(BigButton):
  def _get_label_font_size(self):
    return 64


class SettingsLayout(NavScroller):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._tap_candidate: SettingsBigButton | None = None
    self._tap_start_pos: MousePos | None = None
    self._tap_start_t = 0.0

    toggles_panel = TogglesLayoutMici()
    toggles_btn = SettingsBigButton("toggles", "", gui_app.texture("icons_mici/settings.png", 64, 64))
    toggles_btn.set_click_callback(lambda: gui_app.push_widget(toggles_panel))

    network_panel = NetworkLayoutMici()
    network_btn = SettingsBigButton("network", "", gui_app.texture("icons_mici/settings/network/wifi_strength_full.png", 76, 56))
    network_btn.set_click_callback(lambda: gui_app.push_widget(network_panel))

    device_panel = DeviceLayoutMici()
    device_btn = SettingsBigButton("device", "", gui_app.texture("icons_mici/settings/device_icon.png", 72, 58))
    device_btn.set_click_callback(lambda: gui_app.push_widget(device_panel))

    software_panel = SoftwareLayoutMici()
    software_btn = SettingsBigButton("software", "", gui_app.texture("icons_mici/settings/software.png", 64, 75))
    software_btn.set_click_callback(lambda: gui_app.push_widget(software_panel))

    developer_panel = DeveloperLayoutMici()
    developer_btn = SettingsBigButton("developer", "", gui_app.texture("icons_mici/settings/developer_icon.png", 64, 60))
    developer_btn.set_click_callback(lambda: gui_app.push_widget(developer_panel))

    self._scroller.add_widgets([
      toggles_btn,
      network_btn,
      device_btn,
      software_btn,
      developer_btn,
    ])

    self._font_medium = gui_app.font(FontWeight.MEDIUM)

  def _settings_button_at(self, mouse_pos: MousePos) -> SettingsBigButton | None:
    for item in reversed(self._scroller._items):
      if isinstance(item, SettingsBigButton) and item.enabled and item.is_visible and rl.check_collision_point_rec(mouse_pos, item.rect):
        return item
    return None

  def _tap_moved_too_far(self, mouse_pos: MousePos) -> bool:
    if self._tap_start_pos is None:
      return True
    return abs(mouse_pos.x - self._tap_start_pos.x) > TAP_MAX_MOVE or abs(mouse_pos.y - self._tap_start_pos.y) > TAP_MAX_MOVE

  def _clear_menu_tap(self):
    self._tap_candidate = None
    self._tap_start_pos = None
    self._tap_start_t = 0.0

  def _open_tap_candidate(self):
    candidate = self._tap_candidate
    self._clear_menu_tap()
    if candidate is None or gui_app.get_active_widget() is not self:
      return
    if candidate._click_callback:
      candidate._click_callback()

  def _update_state(self):
    super()._update_state()

    if self._tap_candidate is None:
      return

    last_event = gui_app.last_mouse_event
    if self._tap_moved_too_far(last_event.pos) or self._scroller.scroll_panel.state == ScrollState.MANUAL_SCROLL:
      self._clear_menu_tap()
    elif last_event.left_down and rl.get_time() - self._tap_start_t >= TAP_OPEN_DELAY:
      self._open_tap_candidate()
    elif not last_event.left_down and rl.get_time() - self._tap_start_t > 0.5:
      self._clear_menu_tap()

  def _handle_mouse_press(self, mouse_pos: MousePos):
    super()._handle_mouse_press(mouse_pos)
    self._tap_candidate = self._settings_button_at(mouse_pos)
    self._tap_start_pos = mouse_pos if self._tap_candidate is not None else None
    self._tap_start_t = rl.get_time() if self._tap_candidate is not None else 0.0

  def _handle_mouse_release(self, mouse_pos: MousePos):
    super()._handle_mouse_release(mouse_pos)
    if self._tap_candidate is not None and not self._tap_moved_too_far(mouse_pos) and self._scroller.scroll_panel.state != ScrollState.MANUAL_SCROLL:
      self._open_tap_candidate()
    else:
      self._clear_menu_tap()
