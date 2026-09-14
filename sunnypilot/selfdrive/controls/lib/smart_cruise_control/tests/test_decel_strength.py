import pytest

from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control import apply_decel_strength


def test_full_strength_is_native_output():
  assert apply_decel_strength(10.0, -1.0, 15.0, 0.2, 100) == pytest.approx((10.0, -1.0))


def test_half_strength_halves_speed_and_acceleration_departure():
  assert apply_decel_strength(10.0, -1.0, 15.0, 0.2, 50) == pytest.approx((12.5, -0.4))


def test_strength_is_bounded_and_never_raises_above_setpoint():
  assert apply_decel_strength(20.0, 0.1, 15.0, 0.1, 70)[0] == 15.0
  assert apply_decel_strength(10.0, -1.0, 15.0, 0.0, 20)[0] == pytest.approx(12.5)
  assert apply_decel_strength(10.0, -1.0, 15.0, 0.0, 120)[0] == pytest.approx(10.0)
