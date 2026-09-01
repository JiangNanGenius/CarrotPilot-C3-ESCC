"""Carrot speed limit consumer — lightweight, feature-flagged.

Adds the Carrot companion's planned ceiling (``carrotMan.desiredSpeed``, km/h)
by lowering ``v_cruise``. ``desiredSource`` preserves whether that ceiling came
from vision, route geometry, a navigation limit, a vehicle limit forwarded by
Carrot, or a driver override. Sunnypilot's native vehicle/map resolver remains
independent and keeps its own source policy, offset, confirmation and UI.

It NEVER outputs brakes/acceleration — braking stays solely with sunny's
e2e ``modelV2.shouldStop`` / MPC, so there is no double-trigger. It only
lowers ``v_cruise`` and the MPC naturally plans the deceleration.

The enable flag is read via CarrotParams (file-backed, bypasses the C++
check_key registry) so the settings menu can toggle it without rebuilding
the prebuilt params_pyx.so.
"""

from enum import IntEnum

from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.common.constants import CV

# Sanity bounds for the carrot nav-app speed limit (km/h).
_MIN_NAV_SPEED_KPH = 10.0
_MAX_NAV_SPEED_KPH = 150.0
_PARAM_REFRESH_FRAMES = 100


class CarrotSpeedLimitSource(IntEnum):
  none = 0
  navigation = 1
  visionCurve = 2
  mapCurve = 3
  vehicleLimit = 4
  trafficLight = 5
  safetyDecel = 6
  driver = 7


_CARROT_DESIRED_SOURCE_MAP = {
  # Model-derived turn ceiling.
  "model": CarrotSpeedLimitSource.visionCurve,
  # Navigation route geometry / turn-by-turn turn controller.
  "atc": CarrotSpeedLimitSource.mapCurve,
  "atc2": CarrotSpeedLimitSource.mapCurve,
  "route": CarrotSpeedLimitSource.mapCurve,
  # carrot_man.vturn_speed is computed from modelV2 orientation/velocity.
  "vturn": CarrotSpeedLimitSource.visionCurve,
  # The vehicle-front-camera limit forwarded by Carrot.
  "hda": CarrotSpeedLimitSource.vehicleLimit,
  # Navigation road, camera, section, police, Waze, and speed-bump ceilings.
  "road": CarrotSpeedLimitSource.navigation,
  "cam": CarrotSpeedLimitSource.navigation,
  "section": CarrotSpeedLimitSource.navigation,
  "police": CarrotSpeedLimitSource.navigation,
  "waze": CarrotSpeedLimitSource.navigation,
  "bump": CarrotSpeedLimitSource.navigation,
  # Future-compatible explicit authority names.
  "traffic": CarrotSpeedLimitSource.trafficLight,
  "trafficlight": CarrotSpeedLimitSource.trafficLight,
  "red": CarrotSpeedLimitSource.trafficLight,
  "safety": CarrotSpeedLimitSource.safetyDecel,
  "safetydecel": CarrotSpeedLimitSource.safetyDecel,
  "decel": CarrotSpeedLimitSource.safetyDecel,
  # Pressing the accelerator can raise Carrot's constraint to a driver-chosen
  # floor. It is no longer a navigation authority at that point.
  "gas": CarrotSpeedLimitSource.driver,
  "driver": CarrotSpeedLimitSource.driver,
}


def classify_carrot_desired_source(source) -> CarrotSpeedLimitSource:
  """Classify a Carrot desiredSource; unknown companion values stay external."""
  normalized = str(source).strip().lower().replace("_", "").replace("-", "")
  return _CARROT_DESIRED_SOURCE_MAP.get(normalized, CarrotSpeedLimitSource.navigation)


class CarrotSpeedLimit:
  def __init__(self, params=None):
    self.params = params or CarrotParams()
    self.enabled = self.params.get_bool("CarrotSpeedLimitEnable")
    self.frame = 0
    self.active_source = CarrotSpeedLimitSource.none

  def _refresh_enabled(self) -> None:
    if self.frame % _PARAM_REFRESH_FRAMES == 0:
      self.enabled = self.params.get_bool("CarrotSpeedLimitEnable")
    self.frame += 1

  def update(self, sm, v_cruise_ms: float) -> float:
    self._refresh_enabled()
    self.active_source = CarrotSpeedLimitSource.none
    if not self.enabled:
      return v_cruise_ms

    # carrot nav-app limit (km/h -> m/s). Alive alone is insufficient: an
    # explicitly invalid packet must never retain a stale speed constraint.
    try:
      if sm.alive['carrotMan'] and sm.valid['carrotMan']:
        carrot_man = sm['carrotMan']
        desired_kph = float(carrot_man.desiredSpeed)
        desired_ms = desired_kph * CV.KPH_TO_MS
        if _MIN_NAV_SPEED_KPH < desired_kph <= _MAX_NAV_SPEED_KPH and desired_ms < v_cruise_ms:
          self.active_source = classify_carrot_desired_source(carrot_man.desiredSource)
          return desired_ms
    except Exception:
      pass

    return v_cruise_ms
