import pyray as rl
import json
import time
from dataclasses import dataclass
from collections.abc import Callable
from cereal import log
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight, MousePos, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

from openpilot.selfdrive.ui.sunnypilot.layouts.sidebar import SidebarSP

SIDEBAR_WIDTH = 300
METRIC_HEIGHT = 126
METRIC_WIDTH = 240
METRIC_MARGIN = 30
FONT_SIZE = 35
SETTINGS_TAP_MAX_MOVE = 56
PHONE_INPUT_FRESH_S = 10.0
PHONE_INPUT_STALE_S = 60.0
NAVIGATION_INPUT_FRESH_S = 30.0
GPS_GOOD_ACCURACY_M = 20.0
GPS_WEAK_ACCURACY_M = 100.0
STATUS_METRIC_Y_OFFSETS = (318, 450, 582, 714)

SETTINGS_BTN = rl.Rectangle(50, 35, 200, 117)
HOME_BTN = rl.Rectangle(60, 860, 180, 180)

ThermalStatus = log.DeviceState.ThermalStatus
NetworkType = log.DeviceState.NetworkType


# Color scheme
class Colors:
  WHITE = rl.WHITE
  WHITE_DIM = rl.Color(255, 255, 255, 85)
  GRAY = rl.Color(84, 84, 84, 255)

  # Status colors
  GOOD = rl.WHITE
  WARNING = rl.Color(218, 202, 37, 255)
  DANGER = rl.Color(201, 34, 49, 255)

  # UI elements
  METRIC_BORDER = rl.Color(255, 255, 255, 85)
  BUTTON_NORMAL = rl.WHITE
  BUTTON_PRESSED = rl.Color(255, 255, 255, 166)


NETWORK_TYPES = {
  NetworkType.none: tr_noop("--"),
  NetworkType.wifi: tr_noop("Wi-Fi"),
  NetworkType.ethernet: tr_noop("ETH"),
  NetworkType.cell2G: tr_noop("2G"),
  NetworkType.cell3G: tr_noop("3G"),
  NetworkType.cell4G: tr_noop("LTE"),
  NetworkType.cell5G: tr_noop("5G"),
}

TEMP_FALLBACK_TEXT = tr_noop("--C")
TEMP_SCALAR_FIELDS = ("maxTempC", "memoryTempC", "dspTempC", "intakeTempC", "exhaustTempC", "gnssTempC", "bottomSocTempC")
TEMP_LIST_FIELDS = ("cpuTempC", "gpuTempC", "pmicTempC", "modemTempC")


def _add_temperature_value(values: list[float], value) -> None:
  try:
    temp = float(value)
  except (TypeError, ValueError):
    return

  if temp > 0:
    values.append(temp)


def _temperature_values(device_state) -> list[float]:
  values: list[float] = []
  for field in TEMP_SCALAR_FIELDS:
    _add_temperature_value(values, getattr(device_state, field, 0.0))

  for field in TEMP_LIST_FIELDS:
    for temp in getattr(device_state, field, []):
      _add_temperature_value(values, temp)

  for zone in getattr(device_state, "thermalZones", []):
    _add_temperature_value(values, getattr(zone, "temp", 0.0))

  return values


def format_device_temperature(device_state) -> str:
  values = _temperature_values(device_state)
  if not values:
    return TEMP_FALLBACK_TEXT
  return f"{int(round(max(values)))}C"


def _params_get(params, key: str, default=None):
  try:
    value = params.get(key)
  except Exception:
    return default
  return default if value is None else value


def _params_get_float(params, key: str, default: float = 0.0) -> float:
  value = _params_get(params, key, default)
  if isinstance(value, bytes):
    value = value.decode("utf-8", errors="ignore")
  try:
    return float(value)
  except (TypeError, ValueError):
    return default


def _params_get_bool(params, key: str, default: bool = False) -> bool:
  try:
    return params.get_bool(key)
  except Exception:
    value = _params_get(params, key, b"1" if default else b"0")
    if isinstance(value, bytes):
      value = value.decode("utf-8", errors="ignore")
    return str(value).strip().lower() in ("1", "true", "t", "yes", "on")


def _params_get_json(params, key: str) -> dict:
  value = _params_get(params, key, b"{}")
  if isinstance(value, bytes):
    value = value.decode("utf-8", errors="ignore")
  if isinstance(value, dict):
    return value
  try:
    decoded = json.loads(value or "{}")
  except (TypeError, ValueError):
    return {}
  return decoded if isinstance(decoded, dict) else {}


def _source_short_label(source: str) -> str:
  text = str(source or "").strip()
  lowered = text.lower()
  if "nav" in lowered or "7706" in lowered or "7712" in lowered or "7713" in lowered:
    return tr_noop("NAVI")
  if "apn" in lowered:
    return tr_noop("APN")
  if "sdi" in lowered:
    return tr_noop("SDI")
  if "carrot" in lowered:
    return tr_noop("CARROT")
  return tr_noop("PHONE")


def _age_since(timestamp: float) -> float | None:
  if timestamp <= 0.0:
    return None
  return max(0.0, time.time() - timestamp)


@dataclass(slots=True)
class MetricData:
  label: str
  value: str
  color: rl.Color

  def update(self, label: str, value: str, color: rl.Color):
    self.label = label
    self.value = value
    self.color = color


class Sidebar(Widget, SidebarSP):
  def __init__(self):
    Widget.__init__(self)
    SidebarSP.__init__(self)
    self._net_type = NETWORK_TYPES.get(NetworkType.none)
    self._net_strength = 0

    self._temp_status = MetricData(tr_noop("TEMP"), TEMP_FALLBACK_TEXT, Colors.GOOD)
    self._panda_status = MetricData(tr_noop("VEHICLE"), tr_noop("ONLINE"), Colors.GOOD)
    self._phone_status = MetricData(tr_noop("PHONE"), tr_noop("OFF"), Colors.GRAY)
    self._gps_status = MetricData(tr_noop("GPS"), tr_noop("OFF"), Colors.GRAY)
    self._recording_audio = False

    self._home_img = gui_app.texture("images/button_home.png", HOME_BTN.width, HOME_BTN.height)
    self._flag_img = gui_app.texture("images/button_flag.png", HOME_BTN.width, HOME_BTN.height)
    self._settings_img = gui_app.texture("images/button_settings.png", SETTINGS_BTN.width, SETTINGS_BTN.height)
    self._mic_img = gui_app.texture("icons/microphone.png", 30, 30)
    self._mic_indicator_rect = rl.Rectangle(0, 0, 0, 0)
    self._font_regular = gui_app.font(FontWeight.NORMAL)
    self._font_bold = gui_app.font(FontWeight.SEMI_BOLD)

    # Callbacks
    self._on_settings_click: Callable | None = None
    self._on_flag_click: Callable | None = None
    self._open_settings_callback: Callable | None = None
    self._settings_press_pos: MousePos | None = None

  def set_callbacks(self, on_settings: Callable | None = None, on_flag: Callable | None = None,
                    open_settings: Callable | None = None):
    self._on_settings_click = on_settings
    self._on_flag_click = on_flag
    self._open_settings_callback = open_settings

  def _render(self, rect: rl.Rectangle):
    # Background
    rl.draw_rectangle_rec(rect, rl.BLACK)

    self._draw_buttons(rect)
    self._draw_network_indicator(rect)
    self._draw_metrics(rect)

  def _update_state(self):
    sm = ui_state.sm
    if not sm.updated['deviceState']:
      return

    device_state = sm['deviceState']

    self._recording_audio = ui_state.recording_audio
    self._update_network_status(device_state)
    self._update_temperature_status(device_state)
    self._update_panda_status()
    self._update_phone_status()
    self._update_gps_status()
    SidebarSP._update_sunnylink_status(self)

  def _update_network_status(self, device_state):
    self._net_type = NETWORK_TYPES.get(device_state.networkType.raw, tr_noop("Unknown"))
    strength = device_state.networkStrength
    self._net_strength = max(0, min(5, strength.raw + 1)) if strength.raw > 0 else 0

  def _update_temperature_status(self, device_state):
    thermal_status = device_state.thermalStatus
    temp_text = format_device_temperature(device_state)

    if thermal_status == ThermalStatus.ok:
      self._temp_status.update(tr_noop("TEMP"), temp_text, Colors.GOOD)
    else:
      self._temp_status.update(tr_noop("TEMP"), temp_text, Colors.DANGER)

  def _update_panda_status(self):
    if ui_state.panda_type == log.PandaState.PandaType.unknown:
      self._panda_status.update(tr_noop("NO"), tr_noop("PANDA"), Colors.DANGER)
    else:
      self._panda_status.update(tr_noop("VEHICLE"), tr_noop("ONLINE"), Colors.GOOD)

  def _update_phone_status(self):
    params = ui_state.params
    if not _params_get_bool(params, "CarrotPhoneSpeedLimitEnabled", True):
      self._phone_status.update(tr_noop("PHONE"), tr_noop("OFF"), Colors.GRAY)
      return

    speed_ms = _params_get_float(params, "CarrotPhoneSpeedLimit", 0.0)
    phone_updated_at = _params_get_float(params, "CarrotPhoneSpeedLimitUpdatedAt", 0.0)
    phone_age = _age_since(phone_updated_at)
    source_raw = _params_get(params, "CarrotPhoneSpeedLimitSource", b"")
    if isinstance(source_raw, bytes):
      source_raw = source_raw.decode("utf-8", errors="ignore")

    nav_event = _params_get_json(params, "CarrotNavigationEvent")
    nav_age = _age_since(float(nav_event.get("updatedAt", 0.0) or 0.0))

    if speed_ms > 0.0 and phone_age is not None and phone_age <= PHONE_INPUT_FRESH_S:
      self._phone_status.update(tr_noop("PHONE"), _source_short_label(source_raw), Colors.GOOD)
    elif nav_age is not None and nav_age <= NAVIGATION_INPUT_FRESH_S:
      self._phone_status.update(tr_noop("PHONE"), _source_short_label(str(nav_event.get("source", ""))), Colors.GOOD)
    elif (phone_age is not None and phone_age <= PHONE_INPUT_STALE_S) or (nav_age is not None and nav_age <= PHONE_INPUT_STALE_S):
      self._phone_status.update(tr_noop("PHONE"), tr_noop("STALE"), Colors.WARNING)
    else:
      self._phone_status.update(tr_noop("PHONE"), tr_noop("OFF"), Colors.GRAY)

  def _gps_message(self):
    sm = ui_state.sm
    for service in ("gpsLocationExternal", "gpsLocation"):
      if sm.valid.get(service, False):
        return sm[service]
    return None

  def _update_gps_status(self):
    gps_data = self._gps_message()
    if gps_data is None:
      self._gps_status.update(tr_noop("GPS"), tr_noop("OFF"), Colors.GRAY)
      return

    if not bool(gps_data.hasFix):
      self._gps_status.update(tr_noop("GPS"), tr_noop("NO FIX"), Colors.WARNING)
      return

    accuracy = float(gps_data.horizontalAccuracy)
    satellites = int(gps_data.satelliteCount)
    if accuracy > 0.0 and accuracy <= GPS_GOOD_ACCURACY_M:
      self._gps_status.update(tr_noop("GPS"), f"{int(round(accuracy))}m", Colors.GOOD)
    elif satellites > 0 and accuracy <= 0.0:
      self._gps_status.update(tr_noop("GPS"), f"{satellites}SAT", Colors.GOOD)
    elif accuracy > 0.0 and accuracy <= GPS_WEAK_ACCURACY_M:
      self._gps_status.update(tr_noop("GPS"), tr_noop("WEAK"), Colors.WARNING)
    else:
      self._gps_status.update(tr_noop("GPS"), tr_noop("WEAK"), Colors.DANGER)

  def _open_settings_from_sidebar(self):
    if self._on_settings_click:
      self._on_settings_click()

  def _settings_tap_moved_too_far(self, mouse_pos: MousePos) -> bool:
    if self._settings_press_pos is None:
      return True
    return abs(mouse_pos.x - self._settings_press_pos.x) > SETTINGS_TAP_MAX_MOVE or abs(mouse_pos.y - self._settings_press_pos.y) > SETTINGS_TAP_MAX_MOVE

  def _handle_mouse_press(self, mouse_pos: MousePos):
    if rl.check_collision_point_rec(mouse_pos, SETTINGS_BTN):
      self._settings_press_pos = mouse_pos
    else:
      self._settings_press_pos = None

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if self._settings_press_pos is not None:
      should_open = rl.check_collision_point_rec(mouse_pos, SETTINGS_BTN) and not self._settings_tap_moved_too_far(mouse_pos)
      self._settings_press_pos = None
      if should_open:
        self._open_settings_from_sidebar()
      return

    if rl.check_collision_point_rec(mouse_pos, SETTINGS_BTN):
      if self._on_settings_click:
        self._open_settings_from_sidebar()
    elif rl.check_collision_point_rec(mouse_pos, HOME_BTN) and ui_state.started:
      if self._on_flag_click:
        self._on_flag_click()
    elif self._recording_audio and rl.check_collision_point_rec(mouse_pos, self._mic_indicator_rect):
      if self._open_settings_callback:
        self._open_settings_callback()

  def _draw_buttons(self, rect: rl.Rectangle):
    mouse_pos = rl.get_mouse_position()
    mouse_down = self.is_pressed and rl.is_mouse_button_down(rl.MouseButton.MOUSE_BUTTON_LEFT)

    # Settings button
    settings_down = mouse_down and rl.check_collision_point_rec(mouse_pos, SETTINGS_BTN)
    tint = Colors.BUTTON_PRESSED if settings_down else Colors.BUTTON_NORMAL
    rl.draw_texture_ex(self._settings_img, rl.Vector2(SETTINGS_BTN.x, SETTINGS_BTN.y), 0.0, 1.0, tint)

    # Home/Flag button
    flag_pressed = mouse_down and rl.check_collision_point_rec(mouse_pos, HOME_BTN)
    button_img = self._flag_img if ui_state.started else self._home_img

    tint = Colors.BUTTON_PRESSED if (ui_state.started and flag_pressed) else Colors.BUTTON_NORMAL
    rl.draw_texture_ex(button_img, rl.Vector2(HOME_BTN.x, HOME_BTN.y), 0.0, 1.0, tint)

    # Microphone button
    if self._recording_audio:
      self._mic_indicator_rect = rl.Rectangle(rect.x + rect.width - 130, rect.y + 245, 75, 40)

      mic_pressed = mouse_down and rl.check_collision_point_rec(mouse_pos, self._mic_indicator_rect)
      bg_color = rl.Color(Colors.DANGER.r, Colors.DANGER.g, Colors.DANGER.b, int(255 * 0.65)) if mic_pressed else Colors.DANGER

      rl.draw_rectangle_rounded(self._mic_indicator_rect, 1, 10, bg_color)
      rl.draw_texture_ex(self._mic_img, rl.Vector2(self._mic_indicator_rect.x + (self._mic_indicator_rect.width - self._mic_img.width) / 2,
                         self._mic_indicator_rect.y + (self._mic_indicator_rect.height - self._mic_img.height) / 2), 0.0, 1.0, Colors.WHITE)

  def _draw_network_indicator(self, rect: rl.Rectangle):
    # Signal strength dots
    x_start = rect.x + 58
    y_pos = rect.y + 196
    dot_size = 27
    dot_spacing = 37

    for i in range(5):
      color = Colors.WHITE if i < self._net_strength else Colors.GRAY
      x = int(x_start + i * dot_spacing + dot_size // 2)
      y = int(y_pos + dot_size // 2)
      rl.draw_circle(x, y, dot_size // 2, color)

    # Network type text
    text_y = rect.y + 247
    text_pos = rl.Vector2(rect.x + 58, text_y)
    rl.draw_text_ex(self._font_regular, tr(self._net_type), text_pos, FONT_SIZE, 0, Colors.WHITE)

  def _draw_metrics(self, rect: rl.Rectangle):
    metrics = (self._temp_status, self._panda_status, self._phone_status, self._gps_status)

    for metric, y_offset in zip(metrics, STATUS_METRIC_Y_OFFSETS):
      self._draw_metric(rect, metric, rect.y + y_offset)

  def _draw_metric(self, rect: rl.Rectangle, metric: MetricData, y: float):
    metric_rect = rl.Rectangle(rect.x + METRIC_MARGIN, y, METRIC_WIDTH, METRIC_HEIGHT)
    # Draw colored left edge (clipped rounded rectangle)
    edge_rect = rl.Rectangle(metric_rect.x + 4, metric_rect.y + 4, 100, 118)
    rl.begin_scissor_mode(int(metric_rect.x + 4), int(metric_rect.y), 18, int(metric_rect.height))
    rl.draw_rectangle_rounded(edge_rect, 0.3, 10, metric.color)
    rl.end_scissor_mode()

    # Draw border
    rl.draw_rectangle_rounded_lines_ex(metric_rect, 0.3, 10, 2, Colors.METRIC_BORDER)

    # Draw label and value
    labels = [tr(metric.label), tr(metric.value)]
    text_y = metric_rect.y + (metric_rect.height / 2 - len(labels) * FONT_SIZE * FONT_SCALE)
    for text in labels:
      text_size = measure_text_cached(self._font_bold, text, FONT_SIZE)
      text_y += text_size.y
      text_pos = rl.Vector2(
        metric_rect.x + 22 + (metric_rect.width - 22 - text_size.x) / 2,
        text_y
      )
      rl.draw_text_ex(self._font_bold, text, text_pos, FONT_SIZE, 0, Colors.WHITE)
