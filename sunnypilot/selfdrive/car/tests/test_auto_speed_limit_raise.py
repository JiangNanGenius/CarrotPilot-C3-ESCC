from types import SimpleNamespace as NS

from openpilot.sunnypilot.selfdrive.car.cruise_ext import (
  AUTO_SPEED_RAISE_STABLE_FRAMES, ButtonType, VCruiseHelperSP, auto_speed_limit_raise, owns_cruise_set_speed,
)


def test_auto_raise_steps_toward_road_limit_ratio():
  assert auto_speed_limit_raise(40.0, 60.0, 1.0) == 60.0
  assert auto_speed_limit_raise(58.0, 60.0, 1.0) == 60.0
  assert auto_speed_limit_raise(60.0, 60.0, 1.1) == 66.0


def test_auto_raise_requires_valid_limit_and_only_raises():
  assert auto_speed_limit_raise(40.0, 60.0, 0.0) == 40.0
  assert auto_speed_limit_raise(70.0, 60.0, 1.0) == 70.0
  assert auto_speed_limit_raise(40.0, 60.0, 1.0, inputs_valid=False) == 40.0
  assert auto_speed_limit_raise(140.0, 130.0, 1.2) == 145.0


def test_software_owned_set_speed_includes_seltos_mixed_flags():
  assert owns_cruise_set_speed(pcm_cruise=False, pcm_cruise_speed=True)
  assert owns_cruise_set_speed(pcm_cruise=True, pcm_cruise_speed=False)
  assert not owns_cruise_set_speed(pcm_cruise=True, pcm_cruise_speed=True)


def make_helper():
  helper = VCruiseHelperSP.__new__(VCruiseHelperSP)
  helper.CP = NS(pcmCruise=False)
  helper.CP_SP = NS(pcmCruiseSpeed=True)
  helper.v_cruise_kph = 40.0
  helper.v_cruise_cluster_kph = 40.0
  helper.current_speed_limit_valid = True
  helper.speed_limit_kph = 50.0
  helper.speed_limit_final_kph = 50.0
  helper.auto_speed_limit_ratio = 1.2
  helper.auto_speed_raise_candidate_kph = None
  helper.auto_speed_raise_candidate_frames = 0
  helper.auto_speed_raise_stable_limit_kph = None
  helper.auto_speed_raise_pending = False
  helper.auto_speed_raise_paused = False
  helper.auto_speed_enabled_prev = False
  return helper


def run_frames(helper, count, road_limit=50.0, button_events=(), posted_limit=None):
  helper.speed_limit_final_kph = road_limit
  helper.speed_limit_kph = road_limit if posted_limit is None else posted_limit
  cs = NS(buttonEvents=list(button_events), brakePressed=False, gasPressed=False, vEgo=10.0)
  for _ in range(count):
    helper.update_auto_speed_limit_raise(cs, True, True)


def test_stable_new_limit_raises_ceiling_without_a_lead():
  helper = make_helper()
  run_frames(helper, AUTO_SPEED_RAISE_STABLE_FRAMES - 1)
  assert helper.v_cruise_kph == 40.0
  run_frames(helper, 1)
  assert helper.v_cruise_kph == 60.0


def test_planning_offset_is_not_multiplied_into_auto_raise_ceiling():
  helper = make_helper()
  run_frames(helper, AUTO_SPEED_RAISE_STABLE_FRAMES, road_limit=52.0, posted_limit=50.0)
  assert helper.v_cruise_kph == 60.0


def test_manual_decrease_holds_same_limit_until_higher_limit():
  helper = make_helper()
  run_frames(helper, AUTO_SPEED_RAISE_STABLE_FRAMES)
  helper.v_cruise_kph = helper.v_cruise_cluster_kph = 45.0
  release_minus = NS(pressed=False, type=ButtonType.decelCruise)
  run_frames(helper, 1, button_events=(release_minus,))
  run_frames(helper, AUTO_SPEED_RAISE_STABLE_FRAMES, road_limit=50.0)
  assert helper.v_cruise_kph == 45.0

  run_frames(helper, AUTO_SPEED_RAISE_STABLE_FRAMES, road_limit=60.0)
  assert helper.v_cruise_kph == 72.0
