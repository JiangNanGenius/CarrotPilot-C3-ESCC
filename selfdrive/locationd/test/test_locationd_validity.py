from openpilot.selfdrive.locationd.locationd import location_inputs_valid


class FakeSubMaster:
  def __init__(self, *, camera_updated=True, camera_valid=True, calibration_alive=True, calibration_valid=True):
    self.updated = {'cameraOdometry': camera_updated}
    self.valid = {
      'cameraOdometry': camera_valid,
      'liveCalibration': calibration_valid,
    }
    self.alive = {'liveCalibration': calibration_alive}


def test_location_inputs_do_not_depend_on_noncritical_car_state():
  assert location_inputs_valid(FakeSubMaster())


def test_location_inputs_reject_stale_or_invalid_publishers():
  assert not location_inputs_valid(FakeSubMaster(camera_valid=False))
  assert not location_inputs_valid(FakeSubMaster(calibration_alive=False))
  assert not location_inputs_valid(FakeSubMaster(calibration_valid=False))
  assert not location_inputs_valid(FakeSubMaster(camera_updated=False))
