from types import SimpleNamespace

import pytest

from opendbc.car.lateral import apply_driver_steer_torque_limits
from opendbc.car.hyundai.carcontroller import CarController, MAX_ANGLE_FRAMES


def make_controller():
  controller = CarController.__new__(CarController)
  controller.angle_limit_counter = 0
  return controller


@pytest.mark.parametrize(("seconds", "expected_frames"), [
  (0.1, MAX_ANGLE_FRAMES),
  (0.9, MAX_ANGLE_FRAMES),
  (1.0, 99),
  (2.0, 199),
  (3.0, 199),
])
def test_eps_fault_trigger_is_clamped_to_panda_safe_interval(seconds, expected_frames):
  controller = make_controller()
  controller.configure_steering_assist(True, seconds, 105)

  assert controller.eps_angle_fault_protection
  assert controller.eps_angle_fault_frames == expected_frames


@pytest.mark.parametrize(("percent", "expected_scale"), [
  (90, 1.0),
  (100, 1.0),
  (105, 1.05),
  (110, 1.1),
  (120, 1.1),
])
def test_steering_gain_never_expands_hard_torque_limit(percent, expected_scale):
  controller = make_controller()
  controller.configure_steering_assist(False, 0.9, percent)

  assert not controller.eps_angle_fault_protection
  assert controller.steer_torque_scale == pytest.approx(expected_scale)


def test_eps_protection_defaults_are_safe_without_runtime_configuration():
  controller = make_controller()
  controller.eps_angle_fault_protection = True
  controller.eps_angle_fault_frames = MAX_ANGLE_FRAMES
  controller.steer_torque_scale = 1.05

  assert controller.eps_angle_fault_frames >= MAX_ANGLE_FRAMES
  assert controller.steer_torque_scale <= 1.1


def test_gain_is_still_clamped_by_vehicle_torque_limit():
  limits = SimpleNamespace(
    STEER_MAX=384,
    STEER_DRIVER_ALLOWANCE=50,
    STEER_DRIVER_FACTOR=1,
    STEER_DRIVER_MULTIPLIER=2,
    STEER_DELTA_UP=500,
    STEER_DELTA_DOWN=500,
  )
  scaled_request = round(limits.STEER_MAX * 1.1)

  assert apply_driver_steer_torque_limits(scaled_request, 0, 0, limits) == limits.STEER_MAX
