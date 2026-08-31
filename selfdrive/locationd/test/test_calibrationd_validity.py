from openpilot.selfdrive.locationd.calibrationd import calibration_inputs_valid


class FakeSubMaster:
  def __init__(self, *, camera_updated=True, camera_valid=True):
    self.updated = {'cameraOdometry': camera_updated}
    self.valid = {'cameraOdometry': camera_valid}


def test_publish_valid_is_clocked_only_by_camera_odometry():
  assert calibration_inputs_valid(FakeSubMaster())


def test_publish_invalid_for_missing_or_invalid_camera_odometry():
  assert not calibration_inputs_valid(FakeSubMaster(camera_valid=False))
  assert not calibration_inputs_valid(FakeSubMaster(camera_updated=False))
