from cereal import car

from openpilot.selfdrive.monitoring.dmonitoringd import dmonitoring_inputs_valid
from openpilot.selfdrive.monitoring.helpers import driver_monitoring_wrong_gear


class FakeSubMaster:
  def __init__(self, *, updated=None, valid=None, log_mono_time=None, freq_ok=None):
    services = ['driverStateV2', 'liveCalibration', 'modelV2', 'carState', 'selfdriveState', 'carControl']
    self.updated = dict.fromkeys(services, True) | (updated or {})
    self.valid = dict.fromkeys(services, True) | (valid or {})
    self.logMonoTime = dict.fromkeys(services, 10_000_000_000) | (log_mono_time or {})
    self.freq_ok = dict.fromkeys(services, True) | (freq_ok or {})


def test_valid_inputs_are_not_rejected_by_frequency_jitter():
  assert dmonitoring_inputs_valid(FakeSubMaster(freq_ok={'driverStateV2': False, 'liveCalibration': False}))


def test_invalid_or_stale_input_still_fails_closed():
  assert not dmonitoring_inputs_valid(FakeSubMaster(updated={'driverStateV2': False}))
  assert not dmonitoring_inputs_valid(FakeSubMaster(valid={'carState': False}))
  assert not dmonitoring_inputs_valid(FakeSubMaster(log_mono_time={'liveCalibration': 8_000_000_000}))


def test_driver_monitoring_accepts_forward_sport_gears():
  gear = car.CarState.GearShifter
  for drivable in (gear.drive, gear.low, gear.sport, gear.manumatic):
    assert not driver_monitoring_wrong_gear(drivable)
  for blocked in (gear.park, gear.reverse, gear.neutral, gear.unknown):
    assert driver_monitoring_wrong_gear(blocked)
