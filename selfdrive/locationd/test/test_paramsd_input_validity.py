from openpilot.selfdrive.locationd.paramsd import paramsd_inputs_valid


class FakeSubMaster:
  def __init__(self, *, updated=None, valid=None, log_mono_time=None, freq_ok=None):
    services = ('livePose', 'liveCalibration', 'carState')
    self.updated = dict.fromkeys(services, True) | (updated or {})
    self.valid = dict.fromkeys(services, True) | (valid or {})
    self.logMonoTime = dict.fromkeys(services, 10_000_000_000) | (log_mono_time or {})
    self.freq_ok = dict.fromkeys(services, True) | (freq_ok or {})


def test_auxiliary_frequency_jitter_does_not_invalidate_live_parameters():
  sm = FakeSubMaster(freq_ok={'carState': False})

  assert paramsd_inputs_valid(sm)


def test_reference_and_dependency_health_still_fail_closed():
  assert not paramsd_inputs_valid(FakeSubMaster(updated={'livePose': False}))
  assert not paramsd_inputs_valid(FakeSubMaster(valid={'livePose': False}))
  assert not paramsd_inputs_valid(FakeSubMaster(valid={'liveCalibration': False}))
  assert not paramsd_inputs_valid(FakeSubMaster(log_mono_time={'carState': 9_000_000_000}))


def test_repeated_producer_timestamp_is_not_fresh():
  sm = FakeSubMaster()
  assert paramsd_inputs_valid(sm)
  assert not paramsd_inputs_valid(sm)

  sm.logMonoTime['livePose'] += 50_000_000
  assert paramsd_inputs_valid(sm)
