from types import SimpleNamespace

import pytest

from openpilot.common.constants import CV
from openpilot.selfdrive.carrot.carrot_speed_limit import CarrotSpeedLimit, CarrotSpeedLimitSource, classify_carrot_desired_source
from openpilot.selfdrive.carrot.carrot_traffic_stop import CarrotTrafficStop
from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner, traffic_stop_target_speed


class FakeParams:
  def __init__(self, enabled=True):
    self.enabled = enabled

  def get_bool(self, _key):
    return self.enabled


class FakeSubMaster:
  def __init__(self, desired_speed=0, desired_source="road", traffic_state=0, *, alive=True, valid=True):
    self.alive = {"carrotMan": True, "liveMapDataSP": True}
    self.alive["carrotMan"] = alive
    self.valid = {"carrotMan": valid, "liveMapDataSP": True}
    self.data = {
      "carrotMan": SimpleNamespace(desiredSpeed=desired_speed, desiredSource=desired_source, trafficState=traffic_state),
    }

  def __getitem__(self, key):
    return self.data[key]


def test_nav_speed_limit_reports_navigation_source():
  limiter = CarrotSpeedLimit(FakeParams())
  sm = FakeSubMaster(desired_speed=80)

  target = limiter.update(sm, 120 * CV.KPH_TO_MS)

  assert target == pytest.approx(80 * CV.KPH_TO_MS)
  assert limiter.active_source == CarrotSpeedLimitSource.navigation


@pytest.mark.parametrize("desired_source,expected", [
  ("model", CarrotSpeedLimitSource.visionCurve),
  ("vturn", CarrotSpeedLimitSource.visionCurve),
  ("route", CarrotSpeedLimitSource.mapCurve),
  ("atc2", CarrotSpeedLimitSource.mapCurve),
  ("hda", CarrotSpeedLimitSource.vehicleLimit),
  ("bump", CarrotSpeedLimitSource.navigation),
  ("traffic_light", CarrotSpeedLimitSource.trafficLight),
  ("safety-decel", CarrotSpeedLimitSource.safetyDecel),
  ("gas", CarrotSpeedLimitSource.driver),
  ("future-source", CarrotSpeedLimitSource.navigation),
])
def test_desired_source_classification_is_truthful_and_future_safe(desired_source, expected):
  assert classify_carrot_desired_source(desired_source) == expected

  limiter = CarrotSpeedLimit(FakeParams())
  target = limiter.update(FakeSubMaster(desired_speed=60, desired_source=desired_source), 100 * CV.KPH_TO_MS)

  assert target == pytest.approx(60 * CV.KPH_TO_MS)
  assert limiter.active_source == expected


def test_disabled_speed_limit_clears_active_source():
  limiter = CarrotSpeedLimit(FakeParams(False))
  sm = FakeSubMaster(desired_speed=40)

  assert limiter.update(sm, 100 * CV.KPH_TO_MS) == pytest.approx(100 * CV.KPH_TO_MS)
  assert limiter.active_source == CarrotSpeedLimitSource.none


@pytest.mark.parametrize("health", [{"alive": False}, {"valid": False}])
def test_stale_nav_speed_and_red_light_fail_closed(health):
  sm = FakeSubMaster(desired_speed=40, traffic_state=1, **health)
  limiter = CarrotSpeedLimit(FakeParams())
  stop = CarrotTrafficStop(FakeParams())

  assert limiter.update(sm, 100 * CV.KPH_TO_MS) == pytest.approx(100 * CV.KPH_TO_MS)
  assert limiter.active_source == CarrotSpeedLimitSource.none
  assert stop.update(sm, 20.0) == 20.0
  assert not stop.active


def test_invalid_nav_green_relinquishes_start_authority():
  planner = CarrotPlanner.__new__(CarrotPlanner)
  planner.carrot_stay_stop = True
  planner.trafficState_carrot = 1
  planner.activeCarrot = 2
  planner.xDistToTurn = 20
  planner.atcType = "turn right"
  sm = FakeSubMaster(traffic_state=2, valid=False)

  target, atc_active = planner._update_carrot_man(sm, 0.0, 40.0)

  assert target == 40.0
  assert not atc_active
  assert planner.trafficState_carrot == 0
  assert not planner.carrot_stay_stop
  assert planner.activeCarrot == 0


def test_red_light_stop_reports_active_state():
  stop = CarrotTrafficStop(FakeParams())
  stop.refresh_enabled()

  assert stop.update(FakeSubMaster(traffic_state=1), 20.0) == 0.0
  assert stop.active
  assert stop.update(FakeSubMaster(traffic_state=2), 20.0) == 20.0
  assert not stop.active


def test_traffic_stop_safety_buffer_only_lowers_allowed_speed():
  stop_distance = 12.0
  comfort_brake = 2.4
  buffers = [0.0, 1.0, 2.0, 4.0, stop_distance, stop_distance + 1.0]

  speed_limits = [traffic_stop_target_speed(stop_distance, comfort_brake, buffer) for buffer in buffers]

  assert all(next_speed <= speed for speed, next_speed in zip(speed_limits, speed_limits[1:], strict=False))
  assert speed_limits[0] > speed_limits[2] > speed_limits[-1]
  assert speed_limits[-1] == 0.0


def test_traffic_stop_short_distance_is_not_artificially_extended():
  # A close 3 m detection with a 2 m margin has only 1 m of usable travel;
  # the old max(stop_dist, 5) path incorrectly treated it as 4 m after margin.
  assert traffic_stop_target_speed(3.0, 2.4, 2.0) == pytest.approx((2.0 * 2.4 * 1.0) ** 0.5)
