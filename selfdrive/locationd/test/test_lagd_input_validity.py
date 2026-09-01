from openpilot.selfdrive.locationd.lagd import lagd_inputs_valid


class FakeSubMaster:
  def __init__(self, *, updated=None, valid=None, log_mono_time=None, freq_ok=None):
    services = ('livePose', 'liveCalibration', 'carState', 'controlsState', 'carControl')
    self.updated = dict.fromkeys(services, True) | (updated or {})
    self.valid = dict.fromkeys(services, True) | (valid or {})
    self.logMonoTime = dict.fromkeys(services, 10_000_000_000) | (log_mono_time or {})
    self.freq_ok = dict.fromkeys(services, True) | (freq_ok or {})


def test_auxiliary_frequency_jitter_does_not_invalidate_live_delay():
  assert lagd_inputs_valid(FakeSubMaster(freq_ok={'carState': False, 'carControl': False}))


def test_reference_and_dependency_health_still_fail_closed():
  assert not lagd_inputs_valid(FakeSubMaster(updated={'livePose': False}))
  assert not lagd_inputs_valid(FakeSubMaster(valid={'livePose': False}))
  assert not lagd_inputs_valid(FakeSubMaster(valid={'liveCalibration': False}))
  assert not lagd_inputs_valid(FakeSubMaster(log_mono_time={'controlsState': 9_000_000_000}))
