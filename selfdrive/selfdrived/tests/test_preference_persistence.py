from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
SELFDRIVED = ROOT / "selfdrive/selfdrived/selfdrived.py"
CAR_INTERFACES = ROOT / "sunnypilot/selfdrive/car/interfaces.py"
SPEED_LIMIT_HELPERS = ROOT / "sunnypilot/selfdrive/controls/lib/speed_limit/helpers.py"
SPEED_LIMIT_ASSIST = ROOT / "sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_assist.py"
SPEED_LIMIT_SETTINGS = ROOT / "selfdrive/ui/sunnypilot/layouts/settings/cruise_sub_layouts/speed_limit_settings.py"
PREFERENCE_UI_FILES = (
  ROOT / "selfdrive/ui/layouts/settings/developer.py",
  ROOT / "selfdrive/ui/mici/layouts/settings/developer.py",
  ROOT / "selfdrive/ui/layouts/settings/toggles.py",
  ROOT / "selfdrive/ui/mici/layouts/settings/toggles.py",
)

DURABLE_PREFERENCES = (
  "AlphaLongitudinalEnabled",
  "ExperimentalMode",
  "NeuralNetworkLateralControl",
  "EnforceTorqueControl",
  "DynamicExperimentalControl",
  "CustomAccIncrementsEnabled",
  "SmartCruiseControlVision",
  "SmartCruiseControlMap",
  "SpeedLimitMode",
)
SPEED_LIMIT_ASSIST_MODE = 3


class PreferenceParams:
  def __init__(self):
    self.values = dict.fromkeys(DURABLE_PREFERENCES, True)
    self.values["SpeedLimitMode"] = SPEED_LIMIT_ASSIST_MODE
    self.removed = []
    self.writes = []

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def get(self, key, return_default=False):
    return self.values.get(key)

  def put(self, key, value):
    self.writes.append((key, value))
    self.values[key] = value

  def remove(self, key):
    self.removed.append(key)
    self.values.pop(key, None)


class FakeCarInterface:
  def __init__(self, CP, CP_SP):
    self.CP = CP
    self.CP_SP = CP_SP
    self.torque_tune_configurations = 0

  def configure_torque_tune(self, fingerprint, lateral_tuning):
    self.torque_tune_configurations += 1


def build_cp(*, fingerprint, steer_control_type, openpilot_longitudinal, alpha_longitudinal_available):
  return SimpleNamespace(
    brand="mock" if fingerprint == "MOCK" else "hyundai",
    carFingerprint=fingerprint,
    steerControlType=steer_control_type,
    openpilotLongitudinalControl=openpilot_longitudinal,
    alphaLongitudinalAvailable=alpha_longitudinal_available,
    lateralTuning=object(),
  )


def test_transient_incompatible_cp_does_not_erase_preferences(monkeypatch):
  from opendbc.car import structs
  from openpilot.selfdrive.selfdrived.selfdrived import runtime_experimental_mode
  from openpilot.sunnypilot.selfdrive.car import interfaces

  params = PreferenceParams()
  expected = params.values.copy()

  monkeypatch.setattr(
    interfaces,
    "get_nn_model_path",
    lambda CP: (f"/tmp/{CP.carFingerprint}.json", CP.carFingerprint, CP.carFingerprint != "MOCK"),
  )
  transient_cp = build_cp(
    fingerprint="MOCK",
    steer_control_type=structs.CarParams.SteerControlType.angle,
    openpilot_longitudinal=False,
    alpha_longitudinal_available=False,
  )
  transient_ci = FakeCarInterface(transient_cp, structs.CarParamsSP(pcmCruiseSpeed=True))

  interfaces.setup_interfaces(transient_ci, params)

  assert not interfaces._enforce_torque_lateral_control(transient_cp, params)
  assert not interfaces._initialize_neural_network_lateral_control(transient_cp, transient_ci.CP_SP, params)
  assert not runtime_experimental_mode(params, transient_cp)
  assert transient_ci.torque_tune_configurations == 0
  assert params.values == expected
  assert params.removed == []
  assert params.writes == []

  real_cp = build_cp(
    fingerprint="REAL_CAR",
    steer_control_type=structs.CarParams.SteerControlType.torque,
    openpilot_longitudinal=True,
    alpha_longitudinal_available=True,
  )
  real_ci = FakeCarInterface(real_cp, structs.CarParamsSP(pcmCruiseSpeed=False))

  interfaces.setup_interfaces(real_ci, params)

  assert interfaces._enforce_torque_lateral_control(real_cp, params)
  assert interfaces._initialize_neural_network_lateral_control(real_cp, real_ci.CP_SP, params)
  assert runtime_experimental_mode(params, real_cp)
  assert real_ci.torque_tune_configurations == 1
  assert params.values == expected
  assert params.removed == []
  assert params.writes == []


def test_selfdrived_never_removes_longitudinal_preferences():
  source = SELFDRIVED.read_text()

  assert 'remove("AlphaLongitudinalEnabled")' not in source
  assert 'remove("ExperimentalMode")' not in source
  assert 'return params.get_bool("ExperimentalMode") and CP.openpilotLongitudinalControl' in source


def test_car_capability_checks_do_not_mutate_durable_preferences():
  interface_source = CAR_INTERFACES.read_text()
  helper_source = SPEED_LIMIT_HELPERS.read_text()
  assist_source = SPEED_LIMIT_ASSIST.read_text()

  for preference in DURABLE_PREFERENCES[2:8]:
    assert f'remove("{preference}")' not in interface_source
  assert "_cleanup_unsupported_params(CP, CP_SP, params)" in interface_source
  assert 'put("SpeedLimitMode"' not in helper_source
  assert 'self.enabled = self.available and self.params.get("SpeedLimitMode"' in assist_source


def test_settings_ui_does_not_rewrite_unavailable_assist_preference():
  source = SPEED_LIMIT_SETTINGS.read_text()

  assert 'ui_state.params.put("SpeedLimitMode", int(SpeedLimitMode.warning))' not in source


def test_capability_gated_ui_does_not_remove_longitudinal_preferences():
  sources = {path: path.read_text() for path in PREFERENCE_UI_FILES}

  for path in PREFERENCE_UI_FILES[:2]:
    assert 'remove("AlphaLongitudinalEnabled")' not in sources[path]
  for path in PREFERENCE_UI_FILES[2:]:
    assert 'remove("ExperimentalMode")' not in sources[path]


def test_valid_event_frame_is_rejected_after_producer_dies():
  from openpilot.selfdrive.selfdrived.selfdrived import service_data_available

  stale_sm = SimpleNamespace(
    alive={"driverMonitoringState": False, "longitudinalPlanSP": False},
    valid={"driverMonitoringState": True, "longitudinalPlanSP": True},
  )

  assert not service_data_available(stale_sm, "driverMonitoringState")
  assert not service_data_available(stale_sm, "longitudinalPlanSP")

  stale_sm.alive = {"driverMonitoringState": True, "longitudinalPlanSP": True}
  assert service_data_available(stale_sm, "driverMonitoringState")
  assert service_data_available(stale_sm, "longitudinalPlanSP")
