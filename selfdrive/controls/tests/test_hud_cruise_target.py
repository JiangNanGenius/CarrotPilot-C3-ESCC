import math

from openpilot.common.constants import CV
from openpilot.selfdrive.controls.controlsd import planner_hud_set_speed


def test_vehicle_hud_uses_dynamic_planner_target():
  assert planner_hud_set_speed(40.0, 32.0) == 32.0 * CV.KPH_TO_MS


def test_vehicle_hud_falls_back_to_configured_max_for_invalid_plan():
  assert planner_hud_set_speed(40.0, 0.0) == 40.0 * CV.KPH_TO_MS
  assert planner_hud_set_speed(40.0, math.nan) == 40.0 * CV.KPH_TO_MS
