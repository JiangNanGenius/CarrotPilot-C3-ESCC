"""Carrot speed limit consumer — lightweight, feature-flagged.

Applies a combined speed limit by lowering ``v_cruise``:
  1. sunny resolver's camera/CAN limit (``carStateSP.speedLimit``, i.e. the
     vehicle's front camera reading speed-limit signs over CAN) + map limit
     (``liveMapDataSP.speedLimit``), already merged per ``SpeedLimitPolicy``;
  2. carrot's nav-app limit (``carrotMan.desiredSpeed``, km/h).

It NEVER outputs brakes/acceleration — braking stays solely with sunny's
e2e ``modelV2.shouldStop`` / MPC, so there is no double-trigger. It only
lowers ``v_cruise`` and the MPC naturally plans the deceleration.

The enable flag is read via CarrotParams (file-backed, bypasses the C++
check_key registry) so the settings menu can toggle it without rebuilding
the prebuilt params_pyx.so.
"""

from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.common.constants import CV

# Sanity bounds for the carrot nav-app speed limit (km/h).
_MIN_NAV_SPEED_KPH = 10.0
_MAX_NAV_SPEED_KPH = 150.0


class CarrotSpeedLimit:
  def __init__(self):
    self.params = CarrotParams()
    self.enabled = self.params.get_bool("CarrotSpeedLimitEnable")

  def update(self, sm, v_cruise_ms: float, resolver_speed_limit_ms: float) -> float:
    if not self.enabled:
      return v_cruise_ms

    result = v_cruise_ms

    # 1. camera/CAN + map limit from sunny resolver (m/s, already merged)
    if resolver_speed_limit_ms > 0:
      result = min(result, resolver_speed_limit_ms)

    # 2. carrot nav-app limit (km/h -> m/s)
    try:
      if sm.alive['carrotMan']:
        desired_kph = float(sm['carrotMan'].desiredSpeed)
        if _MIN_NAV_SPEED_KPH < desired_kph <= _MAX_NAV_SPEED_KPH:
          result = min(result, desired_kph * CV.KPH_TO_MS)
    except Exception:
      pass

    # 3. OSM 独立源（不依赖导航 App）
    try:
      if sm.alive['liveMapDataSP']:
        osm_limit_ms = float(sm['liveMapDataSP'].speedLimit)
        if osm_limit_ms > 0:
          result = min(result, osm_limit_ms)
    except Exception:
      pass

    return result
