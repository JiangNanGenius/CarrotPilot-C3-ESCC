from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math

import numpy as np

try:
  from openpilot.selfdrive.modeld.constants import ModelConstants
except ModuleNotFoundError:
  from selfdrive.modeld.constants import ModelConstants


FEATURE_SPEC = [
  "vEgo",
  "aEgo",
  "desiredLatAccel0",
  "desiredLatAccel03",
  "desiredLatAccel06",
  "desiredLatAccel10",
  "desiredLatAccel15",
  "measuredLatAccel",
  "steeringAngleDeg",
  "steeringRateDeg",
  "lateralJerkLookahead",
  "roll0",
  "roll05",
  "roll10",
  "pitch",
  "signDesiredCurvature",
  "lateralOffsetNow",
  "lateralOffsetAvg5s",
  "pastDesiredLatAccel03",
  "pastDesiredLatAccel01",
]
FEATURE_SCHEMA = "cas_v2_timed_20d"

FUTURE_TIMES = [0.0, 0.3, 0.6, 1.0, 1.5]
ROLL_FUTURE_TIMES = [0.0, 0.5, 1.0]
LAT_PLAN_MIN_IDX = 5


def sign(x: float) -> float:
  return 1.0 if x > 0.0 else (-1.0 if x < 0.0 else 0.0)


def roll_pitch_adjust(roll: float, pitch: float) -> float:
  return roll * math.cos(pitch)


def get_lookahead_value(future_vals, current_val: float) -> float:
  if len(future_vals) == 0:
    return current_val
  same_sign_vals = [v for v in future_vals if sign(float(v)) == sign(current_val)]
  if len(same_sign_vals) < len(future_vals):
    return 0.0
  return float(min(same_sign_vals + [current_val], key=lambda x: abs(x)))


@dataclass
class CASFeatureState:
  desired_lat_accels: deque = field(default_factory=deque)
  lateral_offsets: deque = field(default_factory=deque)
  fallback_t: float = 0.0


def _sample_time(state: CASFeatureState, t: float | None) -> float:
  if t is not None and math.isfinite(t):
    return float(t)
  state.fallback_t += 0.01
  return state.fallback_t


def _append_timed(values: deque, t: float, value: float, keep_s: float) -> None:
  values.append((t, float(value)))
  cutoff = t - keep_s
  while values and values[0][0] < cutoff:
    values.popleft()


def _mean_timed(values: deque) -> float:
  if not values:
    return 0.0
  return float(np.mean([value for _, value in values]))


def _past_value(values: deque, t: float, age_s: float, default: float) -> float:
  if not values:
    return float(default)
  target_t = t - age_s
  for sample_t, value in reversed(values):
    if sample_t <= target_t:
      return float(value)
  return float(values[0][1])


def _interp_model(seq, t: float, default: float = 0.0) -> float:
  if seq is None or len(seq) == 0:
    return default
  return float(np.interp(t, ModelConstants.T_IDXS[:len(seq)], list(seq)))


def _model_good(model_data) -> bool:
  return model_data is not None and len(model_data.acceleration.y) >= 2 and len(model_data.orientation.x) >= 2


def lane_center_offset(model_data, min_prob: float = 0.5) -> float | None:
  if model_data is None or len(model_data.laneLines) < 3:
    return None
  if len(model_data.laneLines[1].y) == 0 or len(model_data.laneLines[2].y) == 0:
    return None
  left_prob = float(model_data.laneLineProbs[1]) if len(model_data.laneLineProbs) > 1 else 0.0
  right_prob = float(model_data.laneLineProbs[2]) if len(model_data.laneLineProbs) > 2 else 0.0
  if left_prob < min_prob or right_prob < min_prob:
    return None
  left_y = float(model_data.laneLines[1].y[0])
  right_y = float(model_data.laneLines[2].y[0])
  width = abs(right_y - left_y)
  if width < 2.0 or width > 5.0:
    return None
  return 0.5 * (left_y + right_y)


def _lateral_offset(model_data, lateral_plan=None) -> float:
  lane_offset = lane_center_offset(model_data)
  if lane_offset is not None:
    return lane_offset
  if lateral_plan is not None and len(lateral_plan.position.y) > 1:
    return float(lateral_plan.position.y[1])
  if model_data is not None and len(model_data.position.y) > 1:
    return float(model_data.position.y[1])
  return 0.0


def build_feature_vector(state: CASFeatureState, CS, params, desired_curvature: float,
                         measured_lateral_accel: float, model_data=None, CC=None,
                         lateral_plan=None, lateral_delay: float = 0.0,
                         t: float | None = None) -> list[float]:
  sample_t = _sample_time(state, t)
  v_ego = float(CS.vEgo)
  a_ego = float(CS.aEgo)
  desired_lat_accel = float(desired_curvature * v_ego ** 2)
  _append_timed(state.desired_lat_accels, sample_t, desired_lat_accel, 0.5)

  offset_now = _lateral_offset(model_data, lateral_plan)
  _append_timed(state.lateral_offsets, sample_t, offset_now, 5.0)
  offset_avg = _mean_timed(state.lateral_offsets)

  pitch = 0.0
  if CC is not None and len(CC.orientationNED) > 1:
    pitch = float(CC.orientationNED[1])
  roll = roll_pitch_adjust(float(params.roll), pitch)

  future_lat_accels = []
  model_good = _model_good(model_data)
  for t in FUTURE_TIMES:
    adjusted_t = t + lateral_delay + 0.5 * a_ego * (t / max(v_ego, 1.0))
    future_lat_accels.append(_interp_model(model_data.acceleration.y if model_good else None,
                                           adjusted_t, desired_lat_accel))

  future_rolls = []
  for t in ROLL_FUTURE_TIMES:
    adjusted_t = t + lateral_delay + 0.5 * a_ego * (t / max(v_ego, 1.0))
    model_roll = _interp_model(model_data.orientation.x if model_good else None, adjusted_t, 0.0)
    model_pitch = _interp_model(model_data.orientation.y if model_good else None, adjusted_t, 0.0)
    future_rolls.append(roll_pitch_adjust(roll + model_roll, pitch + model_pitch))

  lateral_jerk_lookahead = 0.0
  if model_good:
    t_diffs = np.diff(ModelConstants.T_IDXS[:len(model_data.acceleration.y)])
    accel_diffs = np.diff(list(model_data.acceleration.y))
    predicted_jerks = accel_diffs / np.maximum(t_diffs, 1e-3)
    desired_jerk_time = max(0.3 + lateral_delay, 0.1)
    desired_jerk = (_interp_model(model_data.acceleration.y, desired_jerk_time, desired_lat_accel) - desired_lat_accel) / desired_jerk_time
    lateral_jerk_lookahead = get_lookahead_value(predicted_jerks[LAT_PLAN_MIN_IDX:16], float(desired_jerk))

  past_03 = _past_value(state.desired_lat_accels, sample_t, 0.3, desired_lat_accel)
  past_01 = _past_value(state.desired_lat_accels, sample_t, 0.1, desired_lat_accel)

  return [
    v_ego,
    a_ego,
    desired_lat_accel,
    *future_lat_accels[1:],
    float(measured_lateral_accel),
    float(CS.steeringAngleDeg),
    float(CS.steeringRateDeg),
    float(lateral_jerk_lookahead),
    *future_rolls,
    pitch,
    sign(desired_curvature),
    offset_now,
    offset_avg,
    float(past_03),
    float(past_01),
  ]
