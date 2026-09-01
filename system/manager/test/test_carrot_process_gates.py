from openpilot.system.manager.process_config import enable_app_navi_status, enable_xiaoge_data


class FakeCarrotGateParams:
  def __init__(self, values):
    self.values = values

  def get_int(self, key, default=0):
    return int(self.values.get(key, default))

  def get_bool(self, key):
    raise AssertionError("legacy Carrot integer gate must not use get_bool")


def test_amap_process_gate_uses_carrot_integer_fallback():
  assert enable_app_navi_status(False, FakeCarrotGateParams({"EnableAmapNaviStatus": 1}), None)
  assert not enable_app_navi_status(False, FakeCarrotGateParams({"EnableAmapNaviStatus": 0}), None)


def test_share_data_process_gate_uses_carrot_integer_fallback():
  assert enable_xiaoge_data(False, FakeCarrotGateParams({"ShareData": 1}), None)
  assert not enable_xiaoge_data(False, FakeCarrotGateParams({"ShareData": 0}), None)
