"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import random
import time

import pytest
from pytest_mock import MockerFixture

from cereal import custom
from openpilot.common.constants import CV
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit import LIMIT_MAX_MAP_DATA_AGE

from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import (
  ALL_SOURCES, SpeedLimitResolver, get_segmented_speed_limit_offset,
)
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.common import OffsetType, Policy

SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source


def create_mock(properties, mocker: MockerFixture):
  mock = mocker.MagicMock()
  for _property, value in properties.items():
    setattr(mock, _property, value)
  return mock


def setup_sm_mock(mocker: MockerFixture):
  cruise_speed_limit = random.uniform(0, 120)
  live_map_data_limit = random.uniform(0, 120)

  car_state = create_mock({
    'gasPressed': False,
    'brakePressed': False,
    'standstill': False,
  }, mocker)
  car_state_sp = create_mock({
    'speedLimit': cruise_speed_limit,
  }, mocker)
  live_map_data = create_mock({
    'speedLimit': live_map_data_limit,
    'speedLimitValid': True,
    'speedLimitAhead': 0.,
    'speedLimitAheadValid': 0.,
    'speedLimitAheadDistance': 0.,
  }, mocker)
  gps_data = create_mock({
    # Wall-clock GPS time must not be used as a monotonic freshness clock.
    'unixTimestampMillis': 1_800_000_000_000,
  }, mocker)
  sm_mock = mocker.MagicMock()
  sm_mock.alive = {'liveMapDataSP': True, 'carStateSP': True}
  sm_mock.valid = {'liveMapDataSP': True, 'carStateSP': True}
  sm_mock.recv_time = {'liveMapDataSP': time.monotonic()}
  sm_mock.__getitem__.side_effect = lambda key: {
    'carState': car_state,
    'liveMapDataSP': live_map_data,
    'carStateSP': car_state_sp,
    'gpsLocation': gps_data,
  }[key]
  return sm_mock


parametrized_policies = pytest.mark.parametrize(
  "policy, sm_key, function_key", [
    (Policy.car_state_only, 'carStateSP', SpeedLimitSource.car),
    (Policy.car_state_priority, 'carStateSP', SpeedLimitSource.car),
    (Policy.map_data_only, 'liveMapDataSP', SpeedLimitSource.map),
    (Policy.map_data_priority, 'liveMapDataSP', SpeedLimitSource.map),
  ],
  ids=lambda val: val.name if hasattr(val, 'name') else str(val)
)


@pytest.mark.parametrize("resolver_class", [SpeedLimitResolver])
class TestSpeedLimitResolverValidation:

  @pytest.mark.parametrize('health_key', ['alive', 'valid'])
  def test_invalid_vehicle_limit_clears_source(self, resolver_class, health_key, mocker):
    resolver = resolver_class()
    sm = setup_sm_mock(mocker)
    resolver._get_from_car_state(sm)
    getattr(sm, health_key)['carStateSP'] = False
    resolver._get_from_car_state(sm)
    assert resolver.limit_solutions[SpeedLimitSource.car] == 0.0

  @pytest.mark.parametrize("policy", list(Policy), ids=lambda policy: policy.name)
  def test_initial_state(self, resolver_class, policy):
    resolver = resolver_class()
    resolver.policy = policy
    for source in ALL_SOURCES:
      if source in resolver.limit_solutions:
        assert resolver.limit_solutions[source] == 0.
        assert resolver.distance_solutions[source] == 0.

  @parametrized_policies
  def test_resolver(self, resolver_class, policy, sm_key, function_key, mocker: MockerFixture):
    resolver = resolver_class()
    resolver.policy = policy
    sm_mock = setup_sm_mock(mocker)
    source_speed_limit = sm_mock[sm_key].speedLimit

    # Assert the resolver
    resolver.update(source_speed_limit, sm_mock)
    assert resolver.speed_limit == source_speed_limit
    assert resolver.source == ALL_SOURCES[function_key]

  def test_resolver_combined(self, resolver_class, mocker: MockerFixture):
    resolver = resolver_class()
    resolver.policy = Policy.combined
    sm_mock = setup_sm_mock(mocker)
    socket_to_source = {'carStateSP': SpeedLimitSource.car, 'liveMapDataSP': SpeedLimitSource.map}
    minimum_key, minimum_speed_limit = min(
      ((key, sm_mock[key].speedLimit) for key in
       socket_to_source.keys()), key=lambda x: x[1])

    # Assert the resolver
    resolver.update(minimum_speed_limit, sm_mock)
    assert resolver.speed_limit == minimum_speed_limit
    assert resolver.source == socket_to_source[minimum_key]

  @parametrized_policies
  def test_parser(self, resolver_class, policy, sm_key, function_key, mocker: MockerFixture):
    resolver = resolver_class()
    resolver.policy = policy
    sm_mock = setup_sm_mock(mocker)
    source_speed_limit = sm_mock[sm_key].speedLimit

    # Assert the parsing
    resolver.update(source_speed_limit, sm_mock)
    assert resolver.limit_solutions[ALL_SOURCES[function_key]] == source_speed_limit
    assert resolver.distance_solutions[ALL_SOURCES[function_key]] == 0.

  @pytest.mark.parametrize("policy", list(Policy), ids=lambda policy: policy.name)
  def test_resolve_interaction_in_update(self, resolver_class, policy, mocker: MockerFixture):
    v_ego = 50
    resolver = resolver_class()
    resolver.policy = policy

    sm_mock = setup_sm_mock(mocker)
    resolver.update(v_ego, sm_mock)

    # After resolution
    assert resolver.speed_limit is not None
    assert resolver.distance is not None
    assert resolver.source is not None

  @pytest.mark.parametrize("policy", list(Policy), ids=lambda policy: policy.name)
  def test_old_map_data_ignored(self, resolver_class, policy, mocker: MockerFixture):
    resolver = resolver_class()
    resolver.policy = policy
    sm_mock = setup_sm_mock(mocker)
    sm_mock.recv_time['liveMapDataSP'] = time.monotonic() - 2 * LIMIT_MAX_MAP_DATA_AGE
    resolver._get_from_map_data(sm_mock)
    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.
    assert resolver.distance_solutions[SpeedLimitSource.map] == 0.

  @pytest.mark.parametrize("health_key", ["alive", "valid"])
  def test_dead_or_invalid_map_data_ignored(self, resolver_class, health_key, mocker: MockerFixture):
    resolver = resolver_class()
    sm_mock = setup_sm_mock(mocker)
    getattr(sm_mock, health_key)['liveMapDataSP'] = False

    resolver._get_from_map_data(sm_mock)

    assert resolver.limit_solutions[SpeedLimitSource.map] == 0.
    assert resolver.distance_solutions[SpeedLimitSource.map] == 0.


@pytest.mark.parametrize("posted,expected", [(40, 0), (60, 0), (70, 1), (80, 1), (90, 2), (110, 2)])
def test_metric_segmented_offset_boundaries(posted, expected):
  offset = get_segmented_speed_limit_offset(posted / 3.6, True, 0, 1, 2)
  assert offset * 3.6 == pytest.approx(expected)


@pytest.mark.parametrize("posted,expected", [(30, 0), (40, 0), (45, 1), (50, 1), (55, 2), (70, 2)])
def test_imperial_segmented_offset_boundaries(posted, expected):
  offset = get_segmented_speed_limit_offset(posted * CV.MPH_TO_MS, False, 0, 1, 2)
  assert offset * CV.MS_TO_MPH == pytest.approx(expected)


def test_segmented_mode_selects_one_offset_without_legacy_stacking():
  resolver = SpeedLimitResolver()
  resolver.is_metric = True
  resolver.speed_limit = 80 / 3.6
  resolver.offset_type = OffsetType.segmented
  resolver.offset_value = 30
  resolver.segmented_offset_low = 0
  resolver.segmented_offset_medium = 1
  resolver.segmented_offset_high = 2
  assert resolver._get_speed_limit_offset() * 3.6 == pytest.approx(1)
