from openpilot.selfdrive.locationd.torqued import torqued_inputs_valid, torqued_live_delay_usable


class FakeSubMaster:
  def __init__(self, *, alive=None, valid=None, freq_ok=None):
    services = ('livePose', 'carControl', 'carOutput', 'carState', 'liveCalibration', 'liveDelay')
    self.alive = dict.fromkeys(services, True) | (alive or {})
    self.valid = dict.fromkeys(services, True) | (valid or {})
    self.freq_ok = dict.fromkeys(services, True) | (freq_ok or {})

  def all_alive(self, services):
    return all(self.alive[s] for s in services)

  def all_valid(self, services):
    return all(self.valid[s] for s in services)

  def all_checks(self, services):
    return self.all_alive(services) and self.all_valid(services) and all(self.freq_ok[s] for s in services)


def test_auxiliary_frequency_jitter_does_not_invalidate_live_torque_parameters():
  assert torqued_inputs_valid(FakeSubMaster(freq_ok={'carState': False, 'carOutput': False}))


def test_required_inputs_still_fail_closed():
  assert not torqued_inputs_valid(FakeSubMaster(freq_ok={'livePose': False}))
  assert not torqued_inputs_valid(FakeSubMaster(freq_ok={'liveCalibration': False}))
  assert not torqued_inputs_valid(FakeSubMaster(alive={'carOutput': False}))
  assert not torqued_inputs_valid(FakeSubMaster(valid={'liveCalibration': False}))


def test_live_delay_is_optional_but_invalid_packets_are_not_consumed():
  invalid_delay = FakeSubMaster(valid={'liveDelay': False})
  dead_delay = FakeSubMaster(alive={'liveDelay': False})

  assert torqued_inputs_valid(invalid_delay)
  assert torqued_inputs_valid(dead_delay)
  assert not torqued_live_delay_usable(invalid_delay)
  assert not torqued_live_delay_usable(dead_delay)
  assert torqued_live_delay_usable(FakeSubMaster(freq_ok={'liveDelay': False}))
