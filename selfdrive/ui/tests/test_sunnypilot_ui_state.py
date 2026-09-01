from openpilot.selfdrive.ui.sunnypilot.ui_state import UIStateSP


class RecordingParams:
  def __init__(self):
    self.removed = []

  def remove(self, key):
    self.removed.append(key)


def test_missing_car_params_does_not_erase_persistent_preferences():
  state = UIStateSP.__new__(UIStateSP)
  state.CP = None
  state.has_longitudinal_control = False
  state.params = RecordingParams()

  state._enforce_constraints()

  assert state.params.removed == []


def test_incompatible_or_mock_car_params_do_not_erase_preferences():
  state = UIStateSP.__new__(UIStateSP)
  state.CP = object()
  state.has_longitudinal_control = False
  state.params = RecordingParams()

  state._enforce_constraints()

  assert state.params.removed == []
