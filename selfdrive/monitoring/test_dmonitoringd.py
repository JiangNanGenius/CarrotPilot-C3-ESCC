from openpilot.selfdrive.monitoring.dmonitoringd import dmonitoring_inputs_valid, inputs_alive_and_valid


class FakeSubMaster:
  def __init__(self, alive, valid, freq_ok):
    self.alive = alive
    self.valid = valid
    self.freq_ok = freq_ok

  def all_alive(self, services):
    return all(self.alive[s] for s in services)

  def all_valid(self, services):
    return all(self.valid[s] for s in services)

  def all_checks(self, services):
    return self.all_alive(services) and self.all_valid(services) and all(self.freq_ok[s] for s in services)


def test_valid_inputs_are_not_rejected_by_frequency_jitter():
  services = ['driverStateV2', 'carState']
  sm = FakeSubMaster(
    alive=dict.fromkeys(services, True),
    valid=dict.fromkeys(services, True),
    freq_ok={'driverStateV2': True, 'carState': False},
  )

  assert inputs_alive_and_valid(sm, services)


def test_invalid_or_dead_input_still_fails_closed():
  services = ['driverStateV2', 'carState']

  dead = FakeSubMaster(
    alive={'driverStateV2': True, 'carState': False},
    valid=dict.fromkeys(services, True),
    freq_ok=dict.fromkeys(services, True),
  )
  invalid = FakeSubMaster(
    alive=dict.fromkeys(services, True),
    valid={'driverStateV2': True, 'carState': False},
    freq_ok=dict.fromkeys(services, True),
  )

  assert not inputs_alive_and_valid(dead, services)
  assert not inputs_alive_and_valid(invalid, services)


def test_model_and_calibration_frequency_remain_safety_checked():
  services = ['driverStateV2', 'liveCalibration', 'modelV2', 'carState', 'selfdriveState', 'carControl']
  base = dict.fromkeys(services, True)
  sm = FakeSubMaster(base, base, base | {'liveCalibration': False})
  assert not dmonitoring_inputs_valid(sm)

  sm = FakeSubMaster(base, base, base | {'carState': False})
  assert dmonitoring_inputs_valid(sm)
