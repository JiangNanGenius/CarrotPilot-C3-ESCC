from types import SimpleNamespace as NS

import pytest

from openpilot.selfdrive.controls.lib.cruise_target_policy import CruiseTargetPolicy
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlannerSP


def planner_and_state():
  planner = LongitudinalPlannerSP.__new__(LongitudinalPlannerSP)
  planner.cruise_policy = CruiseTargetPolicy()
  planner.carrot_speed_limit = NS(enabled=True)
  planner.speed_reference = NS(reference=1)
  planner.events_sp = None
  planner.scc = NS(update=lambda *args: None,
                   vision=NS(output_v_target=100, output_a_target=0),
                   map=NS(output_v_target=100, output_a_target=0))
  planner.resolver = NS(update=lambda *args: None, speed_limit_valid=True, speed_limit_last_valid=True,
                        speed_limit=40 / 3.6, speed_limit_final=40 / 3.6,
                        speed_limit_final_last=40 / 3.6, distance=0, speed_camera_active=False)
  # A native SLA that is inactive must not remove the independent road limit.
  planner.sla = NS(update=lambda *args: None, output_v_target=100, output_a_target=0)
  sm = {'carState': NS(vCruiseCluster=80, vEgoCluster=40 / 3.6, vEgo=38 / 3.6,
                      gasPressed=False, brakePressed=False, standstill=False),
        'carControl': NS(enabled=True, cruiseControl=NS(override=False))}
  return planner, sm


def update(planner, sm):
  return planner.update_targets(sm, sm['carState'].vEgo, 0, 80 / 3.6)[0] * 3.6


def test_native_inactive_sla_cannot_raise_ceiling_target():
  planner, sm = planner_and_state()
  assert update(planner, sm) == pytest.approx(40)


@pytest.mark.parametrize('curve', ['vision', 'map'])
def test_curve_is_temporarily_bypassed_after_instrument_pedal_release(curve):
  planner, sm = planner_and_state()
  update(planner, sm)
  sm['carState'].gasPressed = True
  update(planner, sm)
  sm['carState'].gasPressed = False
  sm['carState'].vEgoCluster = 60 / 3.6
  sm['carState'].vEgo = 55 / 3.6
  assert update(planner, sm) == pytest.approx(60)
  getattr(planner.scc, curve).output_v_target = 32 / 3.6
  assert update(planner, sm) == pytest.approx(60)
  assert planner.cruise_policy.override == pytest.approx(60 / 3.6)
  planner.resolver.speed_limit = planner.resolver.speed_limit_final = 50 / 3.6
  update(planner, sm)
  assert planner.cruise_policy.override is None


def test_disabled_mode_retains_native_target_selection():
  planner, sm = planner_and_state()
  planner.carrot_speed_limit.enabled = False
  assert update(planner, sm) == pytest.approx(80)


def test_camera_enforcement_clears_driver_override():
  planner, sm = planner_and_state()
  update(planner, sm)
  sm['carState'].gasPressed = True
  sm['carState'].vEgoCluster = 60 / 3.6
  update(planner, sm)
  sm['carState'].gasPressed = False
  assert update(planner, sm) == pytest.approx(60)
  planner.resolver.speed_camera_active = True
  assert update(planner, sm) == pytest.approx(40)
  assert planner.cruise_policy.override is None
