"""
Genius Pilot curve-speed owner policy.

The user-facing `CurveSpeedControlMode` owns Sunny curve-speed participation in
the personal C3 alpha. Legacy SCC-V/SCC-M params remain hidden/inert.
"""
from __future__ import annotations

from enum import IntEnum

from openpilot.common.params import Params


class CurveSpeedControlMode(IntEnum):
  off = 0
  sunny = 1
  carrot = 2
  fusion = 3


def _mode(params: Params | None = None) -> CurveSpeedControlMode:
  if params is None:
    params = Params()

  try:
    return CurveSpeedControlMode(int(params.get_int("CurveSpeedControlMode")))
  except (KeyError, TypeError, ValueError):
    return CurveSpeedControlMode.sunny


def sunny_vision_curve_enabled(params: Params | None = None) -> bool:
  return _mode(params) in (CurveSpeedControlMode.sunny, CurveSpeedControlMode.fusion)


def carrot_curve_inputs_enabled(params: Params | None = None) -> bool:
  return _mode(params) in (CurveSpeedControlMode.carrot, CurveSpeedControlMode.fusion)


def sunny_map_speed_enabled(_params: Params | None = None) -> bool:
  return False
