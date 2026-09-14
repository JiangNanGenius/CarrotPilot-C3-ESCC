import pytest
from types import SimpleNamespace

from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.map_controller import (
  calculate_velocity, time_to_velocity, velocities_from_param,
)


@pytest.mark.parametrize('v,a,target,jerk', [(20, 0, 19, -0.6), (15, 0.5, 14, -0.6), (12, -0.5, 11, -0.6)])
def test_curve_time_satisfies_velocity_equation(v, a, target, jerk):
  t = time_to_velocity(v, a, target, jerk)
  assert t is not None and t > 0
  assert calculate_velocity(t, jerk, a, v) == pytest.approx(target)


def test_linear_invalid_and_already_at_target():
  assert time_to_velocity(20, -1, 19, 0) == 1
  assert time_to_velocity(20, 0, 19, 0) is None
  assert time_to_velocity(20, 0, 20, -0.6) == 0
  assert time_to_velocity(float('nan'), 0, 19, -0.6) is None


@pytest.mark.parametrize('raw', ['{', '{}', '[null]', '[{"velocity":3}]',
                               '[{"latitude":91,"longitude":0,"velocity":3}]',
                               '[{"latitude":0,"longitude":0,"velocity":NaN}]'])
def test_invalid_map_snapshot_is_not_a_planner_exception(raw):
  assert velocities_from_param('MapTargetVelocities', SimpleNamespace(get=lambda key: raw)) == []


def test_valid_map_snapshot_preserved():
  raw = '[{"latitude":-33,"longitude":151,"velocity":10}]'
  assert velocities_from_param('MapTargetVelocities', SimpleNamespace(get=lambda key: raw))[0]['velocity'] == 10
