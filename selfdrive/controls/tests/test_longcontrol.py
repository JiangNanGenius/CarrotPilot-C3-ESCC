"""Exercise the current off/pid/stopping API, not the removed starting state."""
import pytest
from cereal import custom

from openpilot.selfdrive.controls.lib.longcontrol import LongCtrlState, long_control_state_trans


@pytest.mark.parametrize('current', [LongCtrlState.off, LongCtrlState.pid, LongCtrlState.stopping])
def test_disengagement_always_exits(current):
  cp = custom.CarParamsSP.new_message()
  assert long_control_state_trans(cp, False, current, False, False, False) == LongCtrlState.off


@pytest.mark.parametrize('current', [LongCtrlState.off, LongCtrlState.stopping])
@pytest.mark.parametrize('stop,brake,standstill', [(True, False, False), (False, True, False), (False, False, True)])
def test_hold_conditions_prevent_start(current, stop, brake, standstill):
  cp = custom.CarParamsSP.new_message()
  assert long_control_state_trans(cp, True, current, stop, brake, standstill) == LongCtrlState.stopping


@pytest.mark.parametrize('current', [LongCtrlState.off, LongCtrlState.stopping])
def test_clear_hold_enters_pid(current):
  cp = custom.CarParamsSP.new_message()
  assert long_control_state_trans(cp, True, current, False, False, False) == LongCtrlState.pid


def test_stop_request_leaves_pid():
  cp = custom.CarParamsSP.new_message()
  assert long_control_state_trans(cp, True, LongCtrlState.pid, True, False, False) == LongCtrlState.stopping


def test_gas_interceptor_only_ignores_cruise_standstill():
  cp = custom.CarParamsSP.new_message(enableGasInterceptor=True)
  assert long_control_state_trans(cp, True, LongCtrlState.stopping, False, False, True) == LongCtrlState.pid
  assert long_control_state_trans(cp, True, LongCtrlState.stopping, False, True, True) == LongCtrlState.stopping
