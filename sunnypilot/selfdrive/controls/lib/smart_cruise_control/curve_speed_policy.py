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


def _param_int(params: Params, key: str, default: int) -> int:
  get_int = getattr(params, "get_int", None)
  if callable(get_int):
    try:
      return int(get_int(key))
    except Exception:
      pass
  try:
    raw = params.get(key, return_default=True)
  except TypeError:
    raw = params.get(key)
  except Exception:
    raw = default
  if raw is None:
    raw = default
  if isinstance(raw, bytes):
    raw = raw.decode("utf-8", errors="ignore")
  try:
    return int(float(raw))
  except (TypeError, ValueError):
    return int(default)


def _mode(params: Params | None = None) -> CurveSpeedControlMode:
  if params is None:
    params = Params()

  try:
    return CurveSpeedControlMode(_param_int(params, "CurveSpeedControlMode", CurveSpeedControlMode.sunny.value))
  except (KeyError, TypeError, ValueError):
    return CurveSpeedControlMode.sunny


def sunny_vision_curve_enabled(params: Params | None = None) -> bool:
  return _mode(params) in (CurveSpeedControlMode.sunny, CurveSpeedControlMode.fusion)


def carrot_curve_inputs_enabled(params: Params | None = None) -> bool:
  return _mode(params) in (CurveSpeedControlMode.carrot, CurveSpeedControlMode.fusion)


def sunny_map_speed_enabled(_params: Params | None = None) -> bool:
  return False
