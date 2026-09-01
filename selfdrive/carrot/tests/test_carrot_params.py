from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.selfdrive.carrot.server.services import params as server_params


def test_custom_params_use_persistent_namespace(tmp_path, monkeypatch):
  monkeypatch.setenv("OPENPILOT_PREFIX", "test")

  params = CarrotParams(str(tmp_path))
  params.put_bool("CarrotSpeedLimitEnable", False)
  params.put_int("TFollowGap1", 120)
  params.put_int("AutoSpeedUptoRoadSpeedLimit", 110)
  params.put_bool("BrakeCruiseAutoResume", True)

  assert params._param_dir == str(tmp_path / "test_carrot")
  assert not (tmp_path / "test" / "CarrotSpeedLimitEnable").exists()
  assert not CarrotParams(str(tmp_path)).get_bool("CarrotSpeedLimitEnable")
  assert CarrotParams(str(tmp_path)).get_int("TFollowGap1") == 120
  assert CarrotParams(str(tmp_path)).get_int("AutoSpeedUptoRoadSpeedLimit") == 110
  assert CarrotParams(str(tmp_path)).get_bool("BrakeCruiseAutoResume")


class FakeParamStore:
  def __init__(self, registered=()):
    self.registered = set(registered)
    self.values = {}
    self.cleared = False

  def check_key(self, key):
    if key not in self.registered:
      raise server_params.UnknownKeyName(key)
    return key

  def get(self, key, block=False, return_default=False):
    return self.values.get(key)

  def put(self, key, value, block=True):
    self.values[key] = value

  def get_bool(self, key, block=False):
    return bool(self.values.get(key, False))

  def put_bool(self, key, value, block=True):
    self.values[key] = bool(value)

  def get_int(self, key, default=0, block=False):
    return int(self.values.get(key, default))

  def put_int(self, key, value, block=True):
    self.values[key] = int(value)

  def get_float(self, key, default=0.0, block=False):
    return float(self.values.get(key, default))

  def put_float(self, key, value, block=True):
    self.values[key] = float(value)

  def put_nonblocking(self, key, value):
    self.values[key] = value

  def put_bool_nonblocking(self, key, value):
    self.values[key] = bool(value)

  def remove(self, key):
    self.values.pop(key, None)

  def get_type(self, key):
    return server_params.ParamKeyType.BOOL

  def get_default_value(self, key):
    return None

  def all_keys(self, flag=None):
    return list(self.values)

  def clear_all(self, tx_flag=None):
    self.cleared = True
    self.values.clear()


def test_server_params_manifest_path_and_typical_owned_key():
  assert server_params._CARROT_SETTINGS_PATH.endswith("/selfdrive/carrot_settings.json")
  assert "AutoSpeedUptoRoadSpeedLimit" in server_params.CARROT_OWNED_PARAMS


def test_routed_params_keeps_carrot_owned_registry_overlap_in_carrot_store():
  native = FakeParamStore({"OpenpilotEnabledToggle", "CarrotSpeedLimitEnable", "CarrotTrafficStopEnable"})
  carrot = FakeParamStore()
  params = server_params.RoutedParams(native_params=native, carrot_params=carrot)

  params.put_bool("OpenpilotEnabledToggle", False)
  params.put_bool("CarrotSpeedLimitEnable", False)
  params.put_bool("CarrotTrafficStopEnable", True)
  params.put_int("AutoSpeedUptoRoadSpeedLimit", 110)

  assert native.values == {"OpenpilotEnabledToggle": False}
  assert carrot.values == {
    "CarrotSpeedLimitEnable": False,
    "CarrotTrafficStopEnable": True,
    "AutoSpeedUptoRoadSpeedLimit": 110,
  }


def test_routed_params_backup_and_reset_remain_carrot_scoped():
  native = FakeParamStore({"OpenpilotEnabledToggle"})
  native.values["OpenpilotEnabledToggle"] = True
  carrot = FakeParamStore()
  carrot.values["TFollowGap1"] = 120
  params = server_params.RoutedParams(native_params=native, carrot_params=carrot)

  assert params.all_keys() == ["TFollowGap1"]
  params.clear_all()

  assert carrot.cleared
  assert native.values == {"OpenpilotEnabledToggle": True}


def test_web_get_set_helpers_route_device_and_carrot_toggles(monkeypatch):
  native = FakeParamStore({"OpenpilotEnabledToggle", "CarrotTrafficStopEnable"})
  carrot = FakeParamStore()
  monkeypatch.setattr(server_params, "NativeParams", lambda: native)
  monkeypatch.setattr(server_params, "CarrotParams", lambda: carrot)

  server_params.set_param_value("OpenpilotEnabledToggle", False)
  server_params.set_param_value("CarrotTrafficStopEnable", True)

  assert server_params.get_param_value("OpenpilotEnabledToggle", True) is False
  assert server_params.get_param_value("CarrotTrafficStopEnable", False) is True
  assert native.values == {"OpenpilotEnabledToggle": False}
  assert carrot.values == {"CarrotTrafficStopEnable": True}
