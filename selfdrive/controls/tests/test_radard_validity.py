from openpilot.selfdrive.controls.radard import RADAR_INPUT_MAX_AGE_NS, radar_inputs_valid


class FakeSubMaster:
  def __init__(self, *, model_updated=True, valid=True, car_state_age_ns=0, tracks_age_ns=0):
    model_time = 10_000_000_000
    self.updated = {'modelV2': model_updated}
    self.valid = {s: valid for s in ('modelV2', 'carState', 'liveTracks')}
    self.logMonoTime = {
      'modelV2': model_time,
      'carState': model_time - car_state_age_ns,
      'liveTracks': model_time - tracks_age_ns,
    }

  def all_valid(self, services):
    return all(self.valid[s] for s in services)


def test_radar_validity_accepts_observed_scheduling_jitter():
  assert radar_inputs_valid(FakeSubMaster(car_state_age_ns=int(0.151 * 1e9)))


def test_radar_validity_still_rejects_stale_or_invalid_inputs():
  assert not radar_inputs_valid(FakeSubMaster(car_state_age_ns=RADAR_INPUT_MAX_AGE_NS + 1))
  assert not radar_inputs_valid(FakeSubMaster(tracks_age_ns=RADAR_INPUT_MAX_AGE_NS + 1))
  assert not radar_inputs_valid(FakeSubMaster(valid=False))
  assert not radar_inputs_valid(FakeSubMaster(model_updated=False))
