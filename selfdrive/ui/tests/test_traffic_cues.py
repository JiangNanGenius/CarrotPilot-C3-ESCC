import pytest

from openpilot.selfdrive.ui.traffic_cues import TrafficCues


def sample(cues, t, **kwargs):
  inputs = dict(healthy=True, enabled=True, traffic_state=0, speed=0.0, long_active=True, brake=False, gas=False)
  inputs.update(kwargs)
  return cues.update(t, **inputs)


def run(cues, start, count, **kwargs):
  return [sample(cues, (start + i) * 0.05, **kwargs) for i in range(count)]


def test_detection_is_debounced_and_only_once():
  cues = TrafficCues()
  assert run(cues, 0, 100, traffic_state=1).count('detected') == 1
  run(cues, 100, 5)
  assert 'detected' not in run(cues, 105, 20, traffic_state=1)
  run(cues, 125, 25)
  assert run(cues, 150, 30, traffic_state=1).count('detected') == 1


def test_actual_start_not_green_state_triggers_once():
  cues = TrafficCues()
  assert 'starting' not in run(cues, 0, 25, traffic_state=2)
  assert run(cues, 25, 100, speed=0.5).count('starting') == 1


def test_stationary_filter_noise_does_not_prevent_start_chime():
  cues = TrafficCues()
  run(cues, 0, 25, speed=-0.01)
  assert run(cues, 25, 20, speed=0.5).count('starting') == 1


@pytest.mark.parametrize('override', [dict(brake=True), dict(gas=True), dict(long_active=False),
                                     dict(healthy=False), dict(enabled=False), dict(speed=float('nan'))])
def test_override_or_invalid_data_disarms_start(override):
  cues = TrafficCues()
  run(cues, 0, 25)
  sample(cues, 1.25, **override)
  assert 'starting' not in run(cues, 26, 30, speed=0.5)


def test_no_start_after_stale_gap_or_process_start_in_motion():
  cues = TrafficCues()
  assert 'starting' not in run(cues, 0, 25, speed=0.5)
  run(cues, 25, 25)
  assert 'starting' not in run(cues, 70, 25, speed=0.5)


def test_short_stop_and_speed_noise_do_not_trigger():
  cues = TrafficCues()
  run(cues, 0, 10)
  assert 'starting' not in run(cues, 10, 10, speed=0.5)
  run(cues, 20, 25)
  assert sample(cues, 2.25, speed=0.4) is None
  assert sample(cues, 2.30, speed=0.2) is None
  assert sample(cues, 2.35, speed=0.4) is None
