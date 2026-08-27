from openpilot.selfdrive.carrot.carrot_params import CarrotParams


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
