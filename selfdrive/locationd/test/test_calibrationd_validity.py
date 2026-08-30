from openpilot.selfdrive.locationd.calibrationd import CAR_STATE_MAX_AGE_NS, calibration_inputs_valid


class FakeSubMaster:
  def __init__(self, *, camera_updated=True, valid=True, car_state_age_ns=0):
    camera_time = 10_000_000_000
    self.updated = {'cameraOdometry': camera_updated}
    self.valid = {'cameraOdometry': valid, 'carState': valid}
    self.logMonoTime = {
      'cameraOdometry': camera_time,
      'carState': camera_time - car_state_age_ns,
    }

  def all_valid(self, services):
    assert services == ['cameraOdometry', 'carState']
    return all(self.valid[s] for s in services)


def test_publish_valid_for_observed_car_state_jitter():
  assert calibration_inputs_valid(FakeSubMaster(car_state_age_ns=int(0.151 * 1e9)))


def test_publish_invalid_for_stale_or_invalid_inputs():
  assert not calibration_inputs_valid(FakeSubMaster(car_state_age_ns=CAR_STATE_MAX_AGE_NS + 1))
  assert not calibration_inputs_valid(FakeSubMaster(valid=False))
  assert not calibration_inputs_valid(FakeSubMaster(camera_updated=False))
