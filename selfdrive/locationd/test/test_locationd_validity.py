from openpilot.selfdrive.locationd.locationd import CALIBRATION_MAX_AGE_NS, CAR_STATE_MAX_AGE_NS, location_inputs_valid


class FakeSubMaster:
  def __init__(self, *, camera_updated=True, valid=True, car_state_age_ns=0, calibration_age_ns=0):
    camera_time = 10_000_000_000
    self.updated = {'cameraOdometry': camera_updated}
    self.valid = {s: valid for s in ('cameraOdometry', 'carState', 'liveCalibration')}
    self.logMonoTime = {
      'cameraOdometry': camera_time,
      'carState': camera_time - car_state_age_ns,
      'liveCalibration': camera_time - calibration_age_ns,
    }

  def all_valid(self, services):
    return all(self.valid[s] for s in services)


def test_location_inputs_accept_observed_scheduling_jitter():
  assert location_inputs_valid(FakeSubMaster(
    car_state_age_ns=int(0.151 * 1e9),
    calibration_age_ns=int(0.5 * 1e9),
  ))


def test_location_inputs_reject_stale_or_invalid_publishers():
  assert not location_inputs_valid(FakeSubMaster(car_state_age_ns=CAR_STATE_MAX_AGE_NS + 1))
  assert not location_inputs_valid(FakeSubMaster(calibration_age_ns=CALIBRATION_MAX_AGE_NS + 1))
  assert not location_inputs_valid(FakeSubMaster(valid=False))
  assert not location_inputs_valid(FakeSubMaster(camera_updated=False))
