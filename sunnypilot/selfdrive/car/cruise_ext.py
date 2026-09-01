"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import numpy as np

from cereal import car, custom
from opendbc.car import structs
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_assist import ACTIVE_STATES as SLA_ACTIVE_STATES
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.helpers import compare_cluster_target

ButtonType = car.CarState.ButtonEvent.Type
SpeedLimitAssistState = custom.LongitudinalPlanSP.SpeedLimit.AssistState

CRUISE_BUTTON_TIMER = {ButtonType.decelCruise: 0, ButtonType.accelCruise: 0,
                       ButtonType.setCruise: 0, ButtonType.resumeCruise: 0,
                       ButtonType.cancel: 0, ButtonType.mainCruise: 0}

V_CRUISE_MIN = 8
V_CRUISE_MAX = 145
V_CRUISE_UNSET = 255
AUTO_SPEED_RAISE_INTERVAL_FRAMES = 100


def auto_speed_limit_raise(current_kph: float, road_limit_kph: float, ratio: float,
                           lead_status: bool, lead_distance_m: float, lead_speed_kph: float,
                           inputs_valid: bool = True) -> float:
  """Return one conservative 5 km/h upward step, matching Carrot's lead-gated behavior."""
  ceiling_kph = min(V_CRUISE_MAX, road_limit_kph * ratio)
  lead_is_pulling_away = lead_status and 0.0 < lead_distance_m < 60.0 and lead_speed_kph + 5.0 > current_kph
  if not inputs_valid or ratio <= 0.0 or road_limit_kph <= 0.0 or not lead_is_pulling_away or current_kph >= ceiling_kph:
    return current_kph
  return float(min(current_kph + 5.0, ceiling_kph))


def owns_cruise_set_speed(pcm_cruise: bool, pcm_cruise_speed: bool) -> bool:
  return not pcm_cruise or not pcm_cruise_speed


def update_manual_button_timers(CS: car.CarState, button_timers: dict[car.CarState.ButtonEvent.Type, int]) -> None:
  # increment timer for buttons still pressed
  for k in button_timers:
    if button_timers[k] > 0:
      button_timers[k] += 1

  for b in CS.buttonEvents:
    if b.type.raw in button_timers:
      # Start/end timer and store current state on change of button pressed
      button_timers[b.type.raw] = 1 if b.pressed else 0


class VCruiseHelperSP:
  def __init__(self, CP: structs.CarParams, CP_SP: structs.CarParamsSP) -> None:
    self.CP = CP
    self.CP_SP = CP_SP
    self.v_cruise_kph = V_CRUISE_UNSET
    self.v_cruise_cluster_kph = V_CRUISE_UNSET
    self.params = Params()
    self.carrot_params = CarrotParams()
    self.v_cruise_min = 0
    self.enabled_prev = False

    self.custom_acc_enabled = self.params.get_bool("CustomAccIncrementsEnabled")
    self.short_increment = self.params.get("CustomAccShortPressIncrement", return_default=True)
    self.long_increment = self.params.get("CustomAccLongPressIncrement", return_default=True)

    self.enable_button_timers = CRUISE_BUTTON_TIMER

    # Speed Limit Assist
    self.sla_state = SpeedLimitAssistState.disabled
    self.prev_sla_state = SpeedLimitAssistState.disabled
    self.has_speed_limit = False
    self.current_speed_limit_valid = False
    self.speed_limit_final_last = 0.
    self.speed_limit_final_last_kph = 0.
    self.speed_limit_final_kph = 0.
    self.prev_speed_limit_final_last_kph = 0.
    self.req_plus = False
    self.req_minus = False
    self.auto_speed_limit_ratio = 0.0
    self.auto_speed_raise_frames = 0
    self.auto_speed_raise_paused = False
    self.auto_speed_enabled_prev = False

  def read_custom_set_speed_params(self) -> None:
    self.custom_acc_enabled = self.params.get_bool("CustomAccIncrementsEnabled")
    self.short_increment = self.params.get("CustomAccShortPressIncrement", return_default=True)
    self.long_increment = self.params.get("CustomAccLongPressIncrement", return_default=True)
    self.auto_speed_limit_ratio = max(0.0, self.carrot_params.get_float("AutoSpeedUptoRoadSpeedLimit") * 0.01)

  def update_auto_speed_limit_raise(self, CS: car.CarState, radar_state, enabled: bool, inputs_valid: bool = True) -> None:
    """Optionally raise the driver's maximum toward the road limit.

    This never lowers the set speed and never changes the planner's final
    target directly. A manual minus/set press pauses it until a plus/resume
    press or a fresh engagement.
    """
    for be in CS.buttonEvents:
      if not be.pressed and be.type in (ButtonType.decelCruise, ButtonType.setCruise):
        self.auto_speed_raise_paused = True
      elif not be.pressed and be.type in (ButtonType.accelCruise, ButtonType.resumeCruise):
        self.auto_speed_raise_paused = False

    if enabled and not self.auto_speed_enabled_prev:
      self.auto_speed_raise_paused = False
    self.auto_speed_enabled_prev = enabled

    lead = radar_state.leadOne
    owns_set_speed = owns_cruise_set_speed(self.CP.pcmCruise, self.CP_SP.pcmCruiseSpeed)
    eligible = (enabled and owns_set_speed and self.auto_speed_limit_ratio > 0.0 and
                inputs_valid and self.current_speed_limit_valid and not self.auto_speed_raise_paused and not CS.brakePressed and
                not CS.gasPressed and CS.vEgo > 5.0 and lead.status)
    if not eligible:
      self.auto_speed_raise_frames = 0
      return

    self.auto_speed_raise_frames += 1
    if self.auto_speed_raise_frames < AUTO_SPEED_RAISE_INTERVAL_FRAMES:
      return
    self.auto_speed_raise_frames = 0

    raised_kph = auto_speed_limit_raise(self.v_cruise_kph, self.speed_limit_final_kph,
                                        self.auto_speed_limit_ratio, lead.status, lead.dRel,
                                        lead.vLeadK * CV.MS_TO_KPH, inputs_valid)
    if raised_kph > self.v_cruise_kph:
      self.v_cruise_kph = raised_kph
      self.v_cruise_cluster_kph = raised_kph

  def update_v_cruise_delta(self, long_press: bool, v_cruise_delta: float) -> tuple[bool, float]:
    if not self.custom_acc_enabled:
      v_cruise_delta = v_cruise_delta * (5 if long_press else 1)
      return long_press, v_cruise_delta

    # Apply user-specified multipliers to the base increment
    short_increment = np.clip(self.short_increment, 1, 10)
    long_increment = np.clip(self.long_increment, 1, 10)

    actual_increment = long_increment if long_press else short_increment
    round_to_nearest = actual_increment in (5, 10)
    v_cruise_delta = v_cruise_delta * actual_increment

    return round_to_nearest, v_cruise_delta

  def get_minimum_set_speed(self, is_metric: bool) -> None:
    if self.CP_SP.pcmCruiseSpeed:
      self.v_cruise_min = V_CRUISE_MIN
      return

    self.v_cruise_min = 30 if is_metric else 20

  def update_enabled_state(self, CS: car.CarState, enabled: bool) -> bool:
    # special enabled state for non pcmCruiseSpeed, unchanged for non pcmCruise
    if not self.CP_SP.pcmCruiseSpeed:
      update_manual_button_timers(CS, self.enable_button_timers)
      button_pressed = any(self.enable_button_timers[k] > 0 for k in self.enable_button_timers)

      if enabled and not self.enabled_prev:
        self.enabled_prev = not button_pressed
        enabled = False
      elif not enabled:
        self.enabled_prev = enabled

      return enabled and self.enabled_prev

    return enabled

  def update_speed_limit_assist(self, is_metric, LP_SP: custom.LongitudinalPlanSP, inputs_valid: bool = True) -> None:
    if not inputs_valid:
      self.has_speed_limit = False
      self.current_speed_limit_valid = False
      self.speed_limit_final_last = 0.
      self.speed_limit_final_last_kph = 0.
      self.speed_limit_final_kph = 0.
      self.sla_state = SpeedLimitAssistState.disabled
      self.req_plus = False
      self.req_minus = False
      return

    resolver = LP_SP.speedLimit.resolver
    self.has_speed_limit = resolver.speedLimitValid or resolver.speedLimitLastValid
    self.current_speed_limit_valid = resolver.speedLimitValid
    self.speed_limit_final_last = LP_SP.speedLimit.resolver.speedLimitFinalLast
    self.speed_limit_final_last_kph = self.speed_limit_final_last * CV.MS_TO_KPH
    self.speed_limit_final_kph = LP_SP.speedLimit.resolver.speedLimitFinal * CV.MS_TO_KPH
    self.sla_state = LP_SP.speedLimit.assist.state
    self.req_plus, self.req_minus = compare_cluster_target(self.v_cruise_cluster_kph * CV.KPH_TO_MS,
                                                           self.speed_limit_final_last, is_metric)

  @property
  def update_speed_limit_final_last_changed(self) -> bool:
    return self.has_speed_limit and bool(self.speed_limit_final_last_kph != self.prev_speed_limit_final_last_kph)

  def update_speed_limit_assist_pre_active_confirmed(self, button_type: car.CarState.ButtonEvent.Type) -> bool:
    if self.sla_state == SpeedLimitAssistState.preActive or self.prev_sla_state == SpeedLimitAssistState.preActive:
      if button_type == ButtonType.decelCruise and self.req_minus:
        return True
      if button_type == ButtonType.accelCruise and self.req_plus:
        return True

    return False

  def update_speed_limit_assist_v_cruise_non_pcm(self) -> None:
    if self.sla_state in SLA_ACTIVE_STATES and (self.prev_sla_state not in SLA_ACTIVE_STATES or
                                                self.update_speed_limit_final_last_changed):
      self.v_cruise_kph = np.clip(round(self.speed_limit_final_last_kph, 1), self.v_cruise_min, V_CRUISE_MAX)

    self.prev_sla_state = self.sla_state
    self.prev_speed_limit_final_last_kph = self.speed_limit_final_last_kph
