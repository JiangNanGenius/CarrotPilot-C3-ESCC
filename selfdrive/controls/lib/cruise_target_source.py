"""Pure mappings for the driver-facing cruise target source contract."""

from cereal import custom, log

from openpilot.selfdrive.carrot.carrot_speed_limit import CarrotSpeedLimitSource
from openpilot.selfdrive.controls.lib.speed_reference import INSTRUMENT_SPEED


CruiseTargetSource = log.LongitudinalPlan.CruiseTargetSource
SunnyPlanSource = custom.LongitudinalPlanSP.LongitudinalPlanSource
SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source


def base_cruise_target_source(sunny_source, resolver_source, speed_reference: int):
  """Map Sunny's selected ceiling to the driver-facing source contract."""
  if sunny_source == SunnyPlanSource.sccVision:
    return CruiseTargetSource.visionCurve
  if sunny_source == SunnyPlanSource.sccMap:
    return CruiseTargetSource.mapCurve
  if sunny_source == SunnyPlanSource.speedLimitAssist:
    if resolver_source == SpeedLimitSource.car:
      return CruiseTargetSource.vehicleLimit
    if resolver_source == SpeedLimitSource.map:
      return CruiseTargetSource.mapLimit
  return CruiseTargetSource.instrumentSet if speed_reference == INSTRUMENT_SPEED else CruiseTargetSource.wheelSet


def carrot_cruise_target_source(carrot_source, speed_reference: int):
  """Map Carrot's reported authority without changing its speed constraint."""
  source_map = {
    CarrotSpeedLimitSource.navigation: CruiseTargetSource.navigationLimit,
    CarrotSpeedLimitSource.visionCurve: CruiseTargetSource.visionCurve,
    CarrotSpeedLimitSource.mapCurve: CruiseTargetSource.mapCurve,
    CarrotSpeedLimitSource.vehicleLimit: CruiseTargetSource.vehicleLimit,
    CarrotSpeedLimitSource.trafficLight: CruiseTargetSource.trafficLight,
    CarrotSpeedLimitSource.safetyDecel: CruiseTargetSource.safetyDecel,
  }
  if carrot_source == CarrotSpeedLimitSource.driver:
    return CruiseTargetSource.instrumentSet if speed_reference == INSTRUMENT_SPEED else CruiseTargetSource.wheelSet
  # An active but future/unknown companion source is still external; never
  # mislabel it as the driver's configured maximum.
  return source_map.get(carrot_source, CruiseTargetSource.navigationLimit)


def control_and_display_cruise_targets(speed_reference, target_speed: float, v_ego: float,
                                       v_ego_cluster: float, a_ego: float) -> tuple[float, float]:
  """Return the internal wheel target and the unscaled driver-facing target."""
  return speed_reference.update(target_speed, v_ego, v_ego_cluster, a_ego), target_speed
