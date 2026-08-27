from openpilot.sunnypilot.selfdrive.car.cruise_ext import auto_speed_limit_raise, owns_cruise_set_speed


def test_auto_raise_steps_toward_road_limit_ratio():
  assert auto_speed_limit_raise(40.0, 60.0, 1.0, True, 35.0, 42.0) == 45.0
  assert auto_speed_limit_raise(58.0, 60.0, 1.0, True, 35.0, 60.0) == 60.0
  assert auto_speed_limit_raise(60.0, 60.0, 1.1, True, 35.0, 65.0) == 65.0


def test_auto_raise_requires_enabled_ratio_and_safe_lead_gate():
  assert auto_speed_limit_raise(40.0, 60.0, 0.0, True, 35.0, 60.0) == 40.0
  assert auto_speed_limit_raise(40.0, 60.0, 1.0, False, 35.0, 60.0) == 40.0
  assert auto_speed_limit_raise(40.0, 60.0, 1.0, True, 75.0, 60.0) == 40.0
  assert auto_speed_limit_raise(40.0, 60.0, 1.0, True, 35.0, 20.0) == 40.0


def test_software_owned_set_speed_includes_seltos_mixed_flags():
  assert owns_cruise_set_speed(pcm_cruise=False, pcm_cruise_speed=True)
  assert owns_cruise_set_speed(pcm_cruise=True, pcm_cruise_speed=False)
  assert not owns_cruise_set_speed(pcm_cruise=True, pcm_cruise_speed=True)
