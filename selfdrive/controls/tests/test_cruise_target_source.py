import pytest

from cereal import custom, log
from openpilot.selfdrive.carrot.carrot_speed_limit import CarrotSpeedLimitSource
from openpilot.selfdrive.controls.lib.cruise_target_source import (
  base_cruise_target_source,
  carrot_cruise_target_source,
  control_and_display_cruise_targets,
)
from openpilot.selfdrive.controls.lib.speed_reference import INSTRUMENT_SPEED, WHEEL_SPEED


CruiseTargetSource = log.LongitudinalPlan.CruiseTargetSource
SunnyPlanSource = custom.LongitudinalPlanSP.LongitudinalPlanSource
SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source


@pytest.mark.parametrize("sunny_source,resolver_source,speed_reference,expected", [
  (SunnyPlanSource.cruise, SpeedLimitSource.none, INSTRUMENT_SPEED, CruiseTargetSource.instrumentSet),
  (SunnyPlanSource.cruise, SpeedLimitSource.none, WHEEL_SPEED, CruiseTargetSource.wheelSet),
  (SunnyPlanSource.sccVision, SpeedLimitSource.none, INSTRUMENT_SPEED, CruiseTargetSource.visionCurve),
  (SunnyPlanSource.sccMap, SpeedLimitSource.none, INSTRUMENT_SPEED, CruiseTargetSource.mapCurve),
  (SunnyPlanSource.speedLimitAssist, SpeedLimitSource.car, INSTRUMENT_SPEED, CruiseTargetSource.vehicleLimit),
  (SunnyPlanSource.speedLimitAssist, SpeedLimitSource.map, INSTRUMENT_SPEED, CruiseTargetSource.mapLimit),
  (SunnyPlanSource.speedLimitAssist, SpeedLimitSource.none, INSTRUMENT_SPEED, CruiseTargetSource.instrumentSet),
])
def test_base_cruise_target_source(sunny_source, resolver_source, speed_reference, expected):
  assert base_cruise_target_source(sunny_source, resolver_source, speed_reference) == expected


@pytest.mark.parametrize("carrot_source,speed_reference,expected", [
  (CarrotSpeedLimitSource.navigation, INSTRUMENT_SPEED, CruiseTargetSource.navigationLimit),
  (CarrotSpeedLimitSource.visionCurve, INSTRUMENT_SPEED, CruiseTargetSource.visionCurve),
  (CarrotSpeedLimitSource.mapCurve, INSTRUMENT_SPEED, CruiseTargetSource.mapCurve),
  (CarrotSpeedLimitSource.vehicleLimit, INSTRUMENT_SPEED, CruiseTargetSource.vehicleLimit),
  (CarrotSpeedLimitSource.trafficLight, INSTRUMENT_SPEED, CruiseTargetSource.trafficLight),
  (CarrotSpeedLimitSource.safetyDecel, INSTRUMENT_SPEED, CruiseTargetSource.safetyDecel),
  (CarrotSpeedLimitSource.driver, INSTRUMENT_SPEED, CruiseTargetSource.instrumentSet),
  (CarrotSpeedLimitSource.driver, WHEEL_SPEED, CruiseTargetSource.wheelSet),
])
def test_carrot_cruise_target_source(carrot_source, speed_reference, expected):
  assert carrot_cruise_target_source(carrot_source, speed_reference) == expected


def test_instrument_reference_keeps_driver_facing_target_unscaled():
  class InstrumentReference:
    @staticmethod
    def update(target, *_args):
      return target * 0.96

  control_target, display_target = control_and_display_cruise_targets(InstrumentReference(), 40.0, 0.0, 0.0, 0.0)

  assert control_target == pytest.approx(38.4)
  assert display_target == pytest.approx(40.0)
