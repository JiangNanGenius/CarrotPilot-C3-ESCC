import struct
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


@pytest.mark.parametrize("firmware_root", FIRMWARE_ROOTS)
def test_f4_linker_uses_full_sram_with_stack_guard(firmware_root: Path):
  linker = (firmware_root / "board/stm32f4/stm32f4_flash.ld").read_text()

  # The legacy boot-mode mailbox is part of the installed bootstub ABI. The
  # stack is independent and must use the full, 256 KiB STM32F413 SRAM1.
  assert "enter_bootloader_mode = 0x2001FFFC" in linker
  assert "_estack = ORIGIN(RAM) + LENGTH(RAM)" in linker
  assert "_Min_Stack_Size = 0x4000" in linker
  assert ".sram2 (NOLOAD)" in linker
  assert "ASSERT(_ebss + _Min_Stack_Size <= _estack" in linker
  assert "ASSERT(_ebss <= enter_bootloader_mode" in linker

  queues = (firmware_root / "board/drivers/can_common.h").read_text()
  assert '__attribute__((section(".sram2"))) can_buffer(rx_q, CAN_RX_BUFFER_SIZE)' in queues


def test_owned_firmware_build_tracks_linker_and_signing_inputs():
  build = (ROOT / "panda_tici/SConscript").read_text()
  assert "env.Depends(bootstub_elf, linkerscript)" in build
  assert "env.Depends(main_elf, linkerscript)" in build
  assert "env.Depends(signed, [sign_py_node, cert_node])" in build

  # Firmware metadata must describe this checkout, not a stale tracked Panda
  # artifact copied from a release snapshot.
  assert "version = get_version(BUILDER, BUILD_TYPE)" in build
  assert "shutil.copy" not in build
  assert "SOURCE_DIR" not in build

  size_gate = (ROOT / "panda_tici/scripts/check_fw_size.py").read_text()
  assert '".sram2": 64*1024' in size_gate
  assert "static_end > boot_mailbox" in size_gate
  assert "static_end + stack_guard > stack_top" in size_gate
  assert "results = [check_space(file, mcu) for file, mcu in checks]" in size_gate
  assert "sys.exit(0 if all(results) else 1)" in size_gate


@pytest.mark.parametrize("firmware_root", FIRMWARE_ROOTS)
@pytest.mark.parametrize("name", ("panda", "panda_h7"))
def test_committed_signed_firmware_matches_raw_binary(firmware_root: Path, name: str):
  raw = (firmware_root / f"board/obj/{name}.bin").read_bytes()
  signed = (firmware_root / f"board/obj/{name}.bin.signed").read_bytes()

  declared_length = int.from_bytes(signed[:4], "little")
  assert declared_length == len(raw) + 8
  assert len(signed) == declared_length + 128
  assert signed[4:len(raw)] == raw[4:]
  assert signed[len(raw):declared_length] == b"VERS" + struct.pack("<I", 2)


@pytest.mark.parametrize("firmware_root", FIRMWARE_ROOTS)
def test_classic_can_rejects_fd_and_oversized_packets_before_copy(firmware_root: Path):
  comms = (firmware_root / "board/can_comms.h").read_text()
  assert "can_packet_header_valid(can_write_buffer.data[0])" in comms
  assert "can_packet_header_valid(data[pos])" in comms
  assert "if (!can_packet_data_valid(&can_packet))" in comms

  common = (firmware_root / "board/drivers/can_common.h").read_text()
  assert "if (!can_packet_data_valid(to_push))" in common
  assert "return can_packet_data_valid(packet)" in common

  bxcan = (firmware_root / "board/drivers/bxcan.h").read_text()
  assert "MIN(CANx->sFIFOMailBox[0].RDTR & 0xFU, 8U)" in bxcan
