from types import SimpleNamespace as NS

import pytest

from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.vision_controller import SmartCruiseControlVision
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET


class Messages(dict):
  alive = {'modelV2': True}
  valid = {'modelV2': True}


@pytest.mark.parametrize('rates,velocities', [([], [10] * 33), ([0] * 33, []), ([float('nan')] * 33, [10] * 33)])
def test_missing_model_curve_cannot_crash_planner(rates, velocities):
  sm = Messages(modelV2=NS(orientationRate=NS(z=rates), velocity=NS(x=velocities)))
  vision = SmartCruiseControlVision()
  vision.update(sm, True, False, 10, 0, 15)
  assert not vision.is_active
  assert vision.output_v_target == V_CRUISE_UNSET


def test_straight_path_has_no_infinite_target():
  sm = Messages(modelV2=NS(orientationRate=NS(z=[0] * 33), velocity=NS(x=[10] * 33)),
                controlsState=NS(curvature=0))
  vision = SmartCruiseControlVision()
  vision.update(sm, True, False, 10, 0, 15)
  assert vision.v_target == V_CRUISE_UNSET


@pytest.mark.parametrize('speed,override,expected', [(10., False, True), (5., False, False), (10., True, False)])
def test_original_threshold_enters_only_with_speed_and_authority(speed, override, expected):
  sm = Messages(modelV2=NS(orientationRate=NS(z=[0.3] * 33), velocity=NS(x=[10.] * 33)),
                controlsState=NS(curvature=0))
  vision = SmartCruiseControlVision()
  vision.params = NS(get_bool=lambda key: True, get_int=lambda key: 100)
  vision.enabled = True
  for _ in range(3):
    vision.update(sm, True, override, speed, 0, 15)
  assert vision._entering_pred_lat_acc_th == 1.3
  assert vision.is_active == expected
  if expected:
    assert vision.output_v_target < 15
