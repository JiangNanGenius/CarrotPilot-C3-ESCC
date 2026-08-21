import pytest

from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.selfdrive.controls.lib.speed_reference import INSTRUMENT_SPEED, WHEEL_SPEED, SpeedReference


def make_reference(tmp_path, mode):
  params = CarrotParams(param_dir=str(tmp_path / "carrot"))
  params.put_int("LongitudinalSpeedReference", mode)
  return SpeedReference(params)


def test_instrument_reference_scales_target_to_cluster_speed(tmp_path):
  reference = make_reference(tmp_path, INSTRUMENT_SPEED)

  target = 100 / 3.6
  adjusted = reference.update(target, v_ego=100 / 3.6, v_ego_cluster=104 / 3.6, a_ego=0.0)

  assert adjusted == pytest.approx((100 / 3.6) * (100 / 104))
  assert adjusted < target


def test_instrument_reference_never_raises_target(tmp_path):
  reference = make_reference(tmp_path, INSTRUMENT_SPEED)

  target = 100 / 3.6
  adjusted = reference.update(target, v_ego=100 / 3.6, v_ego_cluster=95 / 3.6, a_ego=0.0)

  assert adjusted == target


def test_wheel_reference_keeps_target_unchanged(tmp_path):
  reference = make_reference(tmp_path, WHEEL_SPEED)

  target = 100 / 3.6
  adjusted = reference.update(target, v_ego=100 / 3.6, v_ego_cluster=104 / 3.6, a_ego=0.0)

  assert adjusted == target


def test_unstable_or_missing_cluster_speed_falls_back_safely(tmp_path):
  reference = make_reference(tmp_path, INSTRUMENT_SPEED)
  target = 100 / 3.6

  assert reference.update(target, v_ego=100 / 3.6, v_ego_cluster=0.0, a_ego=0.0) == target
  assert reference.update(target, v_ego=100 / 3.6, v_ego_cluster=104 / 3.6, a_ego=1.0) == target

