"""Ideal fixed-stop-point simulations; not a vehicle clearance guarantee."""
from collections import deque
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.carrot.carrot_functions import traffic_stop_target_speed
from openpilot.selfdrive.controls.lib.drive_helpers import should_stop
from openpilot.selfdrive.controls.lib.longitudinal_planner import get_cruise_accel


def simulate(speed, distance, buffer, legacy=False):
  cp = SimpleNamespace(steerRatio=15.0, wheelbase=2.6)
  dt = 0.05
  commands = deque([0.0] * 10)
  accel = 0.0
  for _ in range(2000):
    target = (2 * 2.4 * max(0, distance-buffer))**0.5 if legacy else traffic_stop_target_speed(distance, 2.4, buffer)
    accel = get_cruise_accel(False, target, speed, accel, 0.0, cp, dt, 0.0, True)
    commands.append(-2.0 if should_stop(speed, accel) else accel)
    actual = commands.popleft()
    new_speed = max(0.0, speed + actual * dt)
    distance -= (speed + new_speed) * dt / 2
    speed = new_speed
    if speed == 0:
      break
  return speed, distance


@pytest.mark.parametrize('speed,distance', [(40 / 3.6, 90.0), (60 / 3.6, 180.0)])
@pytest.mark.parametrize('buffer', [2.0, 4.0])
def test_timely_detection_stops_before_fixed_point(speed, distance, buffer):
  final_speed, remaining = simulate(speed, distance, buffer)
  assert final_speed == 0
  assert remaining > 0.5


def test_recorded_late_detection_is_not_claimed_recoverable_by_cruise_channel():
  # Preserve this negative safety boundary explicitly. The first attempted
  # no-overrun test failed at -1.61 m; changing a setting cannot add brake authority.
  speed, remaining = simulate(15.67 / 3.6, 10.19, 2.0)
  _, legacy_remaining = simulate(15.67 / 3.6, 10.19, 2.0, legacy=True)
  assert speed == 0
  assert remaining < 0  # still unsafe if recognition/control begins this late
  assert remaining > legacy_remaining  # corrected envelope mitigates, does not cure, late detection
