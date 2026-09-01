from openpilot.selfdrive.locationd.torqued import torqued_inputs_valid, torqued_live_delay_usable


class FakeSubMaster:
  def __init__(self, *, alive=None, updated=None, valid=None, log_mono_time=None, freq_ok=None):
    services = ('livePose', 'carControl', 'carOutput', 'carState', 'liveCalibration', 'liveDelay')
    self.alive = dict.fromkeys(services, True) | (alive or {})
    self.updated = dict.fromkeys(services, True) | (updated or {})
    self.valid = dict.fromkeys(services, True) | (valid or {})
    self.logMonoTime = dict.fromkeys(services, 10_000_000_000) | (log_mono_time or {})
    self.freq_ok = dict.fromkeys(services, True) | (freq_ok or {})


def test_auxiliary_frequency_jitter_does_not_invalidate_live_torque_parameters():
  assert torqued_inputs_valid(FakeSubMaster(freq_ok={'carState': False, 'carOutput': False}))


def test_required_inputs_still_fail_closed():
  assert not torqued_inputs_valid(FakeSubMaster(updated={'livePose': False}))
  assert not torqued_inputs_valid(FakeSubMaster(valid={'livePose': False}))
  assert not torqued_inputs_valid(FakeSubMaster(valid={'liveCalibration': False}))
  assert not torqued_inputs_valid(FakeSubMaster(log_mono_time={'carOutput': 9_000_000_000}))


def test_live_delay_is_optional_but_invalid_packets_are_not_consumed():
  invalid_delay = FakeSubMaster(valid={'liveDelay': False})
  dead_delay = FakeSubMaster(alive={'liveDelay': False})

  assert torqued_inputs_valid(invalid_delay)
  assert torqued_inputs_valid(dead_delay)
  assert not torqued_live_delay_usable(invalid_delay)
  assert not torqued_live_delay_usable(dead_delay)
  assert torqued_live_delay_usable(FakeSubMaster(freq_ok={'liveDelay': False}))
