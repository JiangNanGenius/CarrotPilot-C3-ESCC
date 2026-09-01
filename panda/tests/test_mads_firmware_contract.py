from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_ROOTS = (ROOT / "panda", ROOT / "panda_tici")


def _case_body(source: str, case: str, next_case: str) -> str:
  start = source.index(f"case {case}:")
  end = source.index(f"case {next_case}:", start)
  return source[start:end]


@pytest.mark.parametrize("firmware_root", FIRMWARE_ROOTS)
def test_mads_configuration_reaches_safety(firmware_root: Path):
  source = (firmware_root / "board/main_comms.h").read_text()
  body = _case_body(source, "0xdf", "0xe0")

  # Alternative experience and SP safety flags may only be changed before a
  # car safety mode is loaded. Both are required by the MADS/Hyundai safety
  # state machine; assigning the numeric mode alone leaves MADS disabled.
  guard = body.index("if (!is_car_safety_mode(current_safety_mode))")
  alternative = body.index("alternative_experience = req->param1", guard)
  safety_param_sp = body.index("current_safety_param_sp = req->param2", alternative)
  apply_mads = body.index("mads_set_alternative_experience(&alternative_experience)", safety_param_sp)
  assert guard < alternative < safety_param_sp < apply_mads


@pytest.mark.parametrize("firmware_root", FIRMWARE_ROOTS)
def test_mads_heartbeat_is_wired_fail_closed(firmware_root: Path):
  comms = (firmware_root / "board/main_comms.h").read_text()
  heartbeat = _case_body(comms, "0xf3", "0xf6")
  assert "heartbeat_engaged = (req->param1 == 1U)" in heartbeat
  assert "heartbeat_engaged_mads = (req->param2 == 1U)" in heartbeat

  main = (firmware_root / "board/main.c").read_text()
  assert main.count("mads_heartbeat_engaged_check();") == 1
  lost = main.index("// clear heartbeat engaged state")
  silent = main.index("set_safety_mode(SAFETY_SILENT", lost)
  fail_closed = main[lost:silent]
  assert "heartbeat_engaged_mads = false" in fail_closed
  assert "mads_exit_controls(MADS_DISENGAGE_REASON_HEARTBEAT_ENGAGED_MISMATCH)" in fail_closed


def test_host_sends_separate_mads_heartbeat_channel():
  panda = (ROOT / "selfdrive/pandad/panda.cc").read_text()
  pandad = (ROOT / "selfdrive/pandad/pandad.cc").read_text()
  assert "control_write(0xf3, engaged, engaged_mads)" in panda
  assert 'allAliveAndValid({"selfdriveStateSP"}) && mads.getEnabled()' in pandad


def test_host_configures_mads_before_entering_car_safety_mode():
  source = (ROOT / "selfdrive/pandad/panda_safety.cc").read_text()
  start = source.index("void PandaSafety::setSafetyMode")
  end = source.index("bool PandaSafety::getOffroadMode", start)
  body = source[start:end]

  # Firmware intentionally rejects 0xdf in a car safety mode. The host must
  # send alternativeExperience and the SP flags while Panda is still in a
  # non-car mode, then enter the selected vehicle safety mode.
  configure_mads = body.index("panda_->set_alternative_experience(alternative_experience, safety_param_sp)")
  configure_car = body.index("panda_->set_safety_model(safety_model, safety_param)")
  assert configure_mads < configure_car


def test_firmware_can_packet_version_is_declared_by_packet_owner():
  packet = (ROOT / "opendbc_repo/opendbc/safety/can.h").read_text()
  host = (ROOT / "panda/python/__init__.py").read_text()
  assert "#define CAN_PACKET_VERSION 4U" in packet
  assert "CAN_PACKET_VERSION = 4" in host
  assert "#ifdef STM32F4" in packet
  assert "#define CANPACKET_DATA_SIZE_MAX 8U" in packet
  assert "#define CANFD" in packet
  assert "#define CANPACKET_DATA_SIZE_MAX 64U" in packet

  safety = (ROOT / "opendbc_repo/opendbc/safety/safety.h").read_text()
  assert '#ifdef CANFD\n  #include "opendbc/safety/modes/hyundai_canfd.h"' in safety
  assert "#ifdef CANFD\n    {SAFETY_HYUNDAI_CANFD, &hyundai_canfd_hooks}," in safety
