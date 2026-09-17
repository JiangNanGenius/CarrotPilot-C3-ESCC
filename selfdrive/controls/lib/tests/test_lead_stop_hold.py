from openpilot.selfdrive.controls.lib.lead_stop_hold import LeadStopHold


def update(hold, **kwargs):
  values = dict(lead_status=True, lead_distance=4.5, lead_speed=0.0,
                ego_speed=1.0, desired_gap=3.5, engaged=True, gas=False)
  values.update(kwargs)
  return hold.update(**values)


def test_stopped_lead_arms_only_in_low_speed_braking_envelope():
  hold = LeadStopHold()
  assert not update(hold, lead_distance=10.0)
  assert not update(hold, ego_speed=3.0, lead_distance=5.0)
  assert update(hold, ego_speed=1.0, lead_distance=4.5)


def test_short_radar_dropout_keeps_hold_but_long_dropout_releases():
  hold = LeadStopHold()
  assert update(hold)
  for _ in range(10):
    assert update(hold, lead_status=False, lead_distance=0.0)
  for _ in range(20):
    active = update(hold, lead_status=False, lead_distance=0.0)
  assert not active


def test_lead_must_move_stably_before_release():
  hold = LeadStopHold()
  assert update(hold)
  for _ in range(9):
    assert update(hold, lead_distance=5.0, lead_speed=1.0)
  assert not update(hold, lead_distance=5.0, lead_speed=1.0)


def test_gas_or_disengagement_releases_immediately():
  hold = LeadStopHold()
  assert update(hold)
  assert not update(hold, gas=True)
  assert update(hold)
  assert not update(hold, engaged=False)
