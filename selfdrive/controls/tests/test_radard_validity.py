from openpilot.selfdrive.controls.radard import radar_inputs_valid


class FakeSubMaster:
  def __init__(self, *, model_updated=True, model_valid=True, car_state_valid=True,
               tracks_alive=True, tracks_valid=True):
    self.updated = {'modelV2': model_updated}
    self.valid = {
      'modelV2': model_valid,
      'carState': car_state_valid,
      'liveTracks': tracks_valid,
    }
    self.alive = {'liveTracks': tracks_alive}


def test_radar_validity_accepts_noncritical_car_state_alive_jitter():
  assert radar_inputs_valid(FakeSubMaster())


def test_radar_validity_still_rejects_stale_or_invalid_inputs():
  assert not radar_inputs_valid(FakeSubMaster(model_valid=False))
  assert not radar_inputs_valid(FakeSubMaster(car_state_valid=False))
  assert not radar_inputs_valid(FakeSubMaster(tracks_alive=False))
  assert not radar_inputs_valid(FakeSubMaster(tracks_valid=False))
  assert not radar_inputs_valid(FakeSubMaster(model_updated=False))
