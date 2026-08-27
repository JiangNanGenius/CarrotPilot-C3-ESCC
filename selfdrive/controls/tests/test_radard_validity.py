from openpilot.selfdrive.controls.radard import radar_inputs_valid


class FakeSubMaster:
  def __init__(self, *, alive=True, valid=True, freq_ok=True):
    self._alive = alive
    self._valid = valid
    self._freq_ok = freq_ok

  def all_alive(self):
    return self._alive

  def all_valid(self):
    return self._valid

  def all_freq_ok(self):
    return self._freq_ok


def test_radar_validity_accepts_healthy_variable_cadence_inputs():
  assert radar_inputs_valid(FakeSubMaster(freq_ok=False))


def test_radar_validity_still_rejects_stale_or_invalid_inputs():
  assert not radar_inputs_valid(FakeSubMaster(alive=False))
  assert not radar_inputs_valid(FakeSubMaster(valid=False))
