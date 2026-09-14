"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.constants import CV

MIN_V = 20 * CV.KPH_TO_MS  # Do not operate under 20 km/h


def apply_decel_strength(raw_v_target: float, raw_a_target: float, v_setpoint: float,
                         a_ego: float, strength_percent: int) -> tuple[float, float]:
  """Blend an active curve request toward the inactive cruise baseline."""
  strength = max(50, min(100, int(strength_percent))) * 0.01
  v_target = v_setpoint - strength * max(0.0, v_setpoint - raw_v_target)
  a_target = a_ego + strength * (raw_a_target - a_ego)
  return float(v_target), float(a_target)
