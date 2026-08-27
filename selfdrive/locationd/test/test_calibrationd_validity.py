from openpilot.selfdrive.locationd.calibrationd import calibration_inputs_valid


class FakeSubMaster:
  def __init__(self, *, alive=True, valid=True, freq_ok=True):
    self.alive = alive
    self.valid = valid
    self.freq_ok = freq_ok

  def all_alive(self, services):
    assert services == ['cameraOdometry', 'carState']
    return self.alive

  def all_valid(self, services):
    assert services == ['cameraOdometry', 'carState']
    return self.valid

  def all_freq_ok(self, services):
    assert services == ['cameraOdometry', 'carState']
    return self.freq_ok

  def all_checks(self, services):
    return self.all_alive(services) and self.all_valid(services) and self.all_freq_ok(services)


def test_publish_valid_does_not_inherit_frequency_jitter():
  sm = FakeSubMaster(alive=True, valid=True, freq_ok=False)
  assert not sm.all_checks(['cameraOdometry', 'carState'])
  assert calibration_inputs_valid(sm)


def test_publish_invalid_for_missing_or_invalid_inputs():
  assert not calibration_inputs_valid(FakeSubMaster(alive=False, valid=True))
  assert not calibration_inputs_valid(FakeSubMaster(alive=True, valid=False))
