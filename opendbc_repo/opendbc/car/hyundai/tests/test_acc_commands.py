from types import SimpleNamespace

from opendbc.can import CANPacker, CANParser
from opendbc.car.structs import CarParams
from opendbc.car.hyundai.hyundaican import create_acc_commands
from opendbc.car.hyundai.values import HyundaiSafetyFlags
from opendbc.safety.tests.libsafety import libsafety_py
from opendbc.sunnypilot.car.hyundai.lead_data_ext import CanLeadData
from opendbc.sunnypilot.car.hyundai.values import HyundaiSafetyFlagsSP


class FakeEscc:
  enabled = True

  @staticmethod
  def update_scc12(values):
    values.update({
      "AEB_CmdAct": 1,
      "CF_VSM_Warn": 1,
      "CF_VSM_DecCmdAct": 1,
      "CR_VSM_DecCmd": 0.5,
      "AEB_Status": 2,
    })


def _create_acc_messages(long_actuation_allowed: bool | None, long_override: bool = True):
  packer = CANPacker("hyundai_kia_generic")
  tuning = SimpleNamespace(
    stopping=True,
    desired_accel=-1.25,
    actual_accel=-1.0,
    comfort_band_upper=0.1,
    comfort_band_lower=0.2,
    jerk_upper=1.5,
    jerk_lower=2.5,
  )
  hud = SimpleNamespace(leadDistanceBars=2)
  CP = SimpleNamespace(flags=0)
  kwargs = {}
  if long_actuation_allowed is not None:
    kwargs["long_actuation_allowed"] = long_actuation_allowed

  return create_acc_commands(
    packer, enabled=True, accel=-1.25, upper_jerk=1.5, idx=7,
    lead_data=CanLeadData(2, 20.0, -1.0, True), hud_control=hud,
    set_speed=40.0, stopping=True, long_override=long_override, use_fca=False,
    CP=CP, main_cruise_enabled=True, tuning=tuning, ESCC=FakeEscc(),
    **kwargs,
  )


def _parse(messages, name, address):
  parser = CANParser("hyundai_kia_generic", [(name, 0)], 0)
  msg = next(msg for msg in messages if msg[0] == address)
  parser.update([1, [msg]])
  return parser.vl[name]


def test_gas_override_contract_clears_stale_accel_but_preserves_override_and_escc_aeb():
  messages = _create_acc_messages(long_actuation_allowed=False, long_override=True)
  scc12 = _parse(messages, "SCC12", 0x421)
  scc14 = _parse(messages, "SCC14", 0x389)

  assert scc12["ACCMode"] == 2
  assert scc12["StopReq"] == 0
  assert scc12["aReqRaw"] == 0
  assert scc12["aReqValue"] == 0
  assert scc14["ACCMode"] == 2
  assert scc14["JerkUpperLimit"] == 1.5
  assert scc14["JerkLowerLimit"] == 2.5

  # ESCC owns the stock AEB passthrough fields independently of openpilot's
  # acceleration request. Pedal takeover must not erase those safety signals.
  assert scc12["AEB_CmdAct"] == 1
  assert scc12["CF_VSM_DecCmdAct"] == 1
  assert scc12["CR_VSM_DecCmd"] == 0.5
  assert scc12["AEB_Status"] == 2


def test_brake_contract_uses_inactive_modes_and_clears_stale_accel():
  messages = _create_acc_messages(long_actuation_allowed=False, long_override=False)
  scc12 = _parse(messages, "SCC12", 0x421)
  scc14 = _parse(messages, "SCC14", 0x389)

  assert scc12["ACCMode"] == 0
  assert scc12["StopReq"] == 0
  assert scc12["aReqRaw"] == 0
  assert scc12["aReqValue"] == 0
  assert scc14["ACCMode"] == 4


def test_active_longitudinal_contract_is_unchanged():
  messages = _create_acc_messages(long_actuation_allowed=True)
  legacy_default_messages = _create_acc_messages(long_actuation_allowed=None)
  scc12 = _parse(messages, "SCC12", 0x421)
  scc14 = _parse(messages, "SCC14", 0x389)

  assert messages == legacy_default_messages
  assert messages == [
    (0x420, bytes.fromhex("712851c890a16900"), 0),
    (0x421, bytes.fromhex("12c0328263736117"), 0),
    (0x389, bytes.fromhex("85f2c80002080002"), 0),
  ]
  assert scc12["ACCMode"] == 2
  assert scc12["StopReq"] == 1
  assert scc12["aReqRaw"] == -1.25
  assert scc12["aReqValue"] == -1.0
  assert scc14["ACCMode"] == 2
  assert scc14["JerkUpperLimit"] == 1.5
  assert scc14["JerkLowerLimit"] == 2.5


def test_inactive_scc12_is_accepted_after_gas_or_brake_revokes_longitudinal_authority():
  safety = libsafety_py.libsafety
  safety.set_current_safety_param_sp(HyundaiSafetyFlagsSP.ESCC)
  safety.set_safety_hooks(CarParams.SafetyModel.hyundai, HyundaiSafetyFlags.LONG)
  safety.init_tests()

  gas_scc12 = next(msg for msg in _create_acc_messages(False, long_override=True) if msg[0] == 0x421)
  gas_packet = libsafety_py.make_CANPacket(gas_scc12[0], gas_scc12[2], gas_scc12[1])
  safety.set_controls_allowed(True)
  safety.set_gas_pressed_prev(True)
  assert safety.safety_tx_hook(gas_packet)

  brake_scc12 = next(msg for msg in _create_acc_messages(False, long_override=False) if msg[0] == 0x421)
  brake_packet = libsafety_py.make_CANPacket(brake_scc12[0], brake_scc12[2], brake_scc12[1])
  safety.set_controls_allowed(False)
  safety.set_gas_pressed_prev(False)
  assert safety.safety_tx_hook(brake_packet)
