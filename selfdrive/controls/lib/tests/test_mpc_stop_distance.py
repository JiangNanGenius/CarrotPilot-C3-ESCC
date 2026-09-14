import numpy as np
import pytest
from cereal import log

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc, PARAM_DIM


def solve(distance):
  radar = log.RadarState.new_message()
  radar.leadOne.status = True
  radar.leadOne.dRel = 30.0
  radar.leadOne.vLead = 0.0
  radar.leadOne.aLeadTau = 1.5
  mpc = LongitudinalMpc()
  mpc.set_weights(prev_accel_constraint=False)
  mpc.set_cur_state(8.0, 0.0)
  for _ in range(5):
    mpc.update(radar, stop_distance=distance)
  assert mpc.solution_status == 0
  assert np.all(np.isfinite(mpc.v_solution))
  return mpc


@pytest.mark.parametrize('distance', [3.0, 6.0, 8.0, 12.0])
def test_generated_solver_accepts_runtime_distance(distance):
  mpc = solve(distance)
  assert PARAM_DIM == 7
  np.testing.assert_allclose(mpc.params[:, 6], distance)


def test_larger_buffer_does_not_plan_a_closer_stop():
  short, long = solve(6.0), solve(8.0)
  assert long.x_sol[-1, 0] <= short.x_sol[-1, 0] + 0.05
