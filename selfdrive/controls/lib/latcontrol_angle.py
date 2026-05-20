import math
import numpy as np

from cereal import log
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.selfdrive.carrot.cas.runtime import CASRuntime

STEER_ANGLE_SATURATION_THRESHOLD = 2.5  # Degrees


class LatControlAngle(LatControl):
  def __init__(self, CP, CI):
    super().__init__(CP, CI)
    self.sat_check_min_speed = 5.
    self.cas = CASRuntime(CP, "angle")

  def update(self, active, CS, VM, params, steer_limited_by_controls, desired_curvature, CC, curvature_limited,
             model_data=None, lateral_plan=None, lateral_delay: float = 0.0):
    angle_log = log.ControlsState.LateralAngleState.new_message()

    if not active:
      angle_log.active = False
      angle_steers_des = float(CS.steeringAngleDeg)
    else:
      angle_log.active = True
      angle_steers_des = math.degrees(VM.get_steer_from_curvature(-desired_curvature, CS.vEgo, params.roll))
      angle_steers_des += params.angleOffsetDeg
      actual_curvature = -VM.calc_curvature(math.radians(CS.steeringAngleDeg - params.angleOffsetDeg), CS.vEgo, params.roll)
      actual_lateral_accel = actual_curvature * CS.vEgo ** 2
      cas_delta, cas_alpha, cas_log = self.cas.update(CS, params, desired_curvature, actual_lateral_accel,
                                                      model_data=model_data, CC=CC,
                                                      lateral_plan=lateral_plan, lateral_delay=lateral_delay)
      angle_steers_des += cas_alpha * cas_delta
      if cas_log:
        angle_log.casLog = cas_log

    angle_control_saturated = abs(angle_steers_des - CS.steeringAngleDeg) > STEER_ANGLE_SATURATION_THRESHOLD
    angle_log.saturated = bool(self._check_saturation(angle_control_saturated, CS, False, curvature_limited))
    angle_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    angle_log.steeringAngleDesiredDeg = float(angle_steers_des) if not CS.steeringPressed else float(CS.steeringAngleDeg)
    return 0, float(angle_steers_des), angle_log
