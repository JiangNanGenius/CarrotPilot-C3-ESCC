from openpilot.selfdrive.locationd.paramsd import paramsd_inputs_valid


class FakeSubMaster:
  def __init__(self, *, alive=None, valid=None, freq_ok=None):
    services = ('livePose', 'liveCalibration', 'carState')
    self.alive = dict.fromkeys(services, True) | (alive or {})
    self.valid = dict.fromkeys(services, True) | (valid or {})
    self.freq_ok = dict.fromkeys(services, True) | (freq_ok or {})

  def all_alive(self, services):
    return all(self.alive[s] for s in services)

  def all_valid(self, services):
    return all(self.valid[s] for s in services)

  def all_checks(self, services):
    return self.all_alive(services) and self.all_valid(services) and all(self.freq_ok[s] for s in services)


def test_auxiliary_frequency_jitter_does_not_invalidate_live_parameters():
  sm = FakeSubMaster(freq_ok={'carState': False})

  assert paramsd_inputs_valid(sm)


def test_primary_frequency_and_all_message_health_still_fail_closed():
  assert not paramsd_inputs_valid(FakeSubMaster(freq_ok={'livePose': False}))
  assert not paramsd_inputs_valid(FakeSubMaster(freq_ok={'liveCalibration': False}))
  assert not paramsd_inputs_valid(FakeSubMaster(alive={'carState': False}))
  assert not paramsd_inputs_valid(FakeSubMaster(valid={'liveCalibration': False}))
