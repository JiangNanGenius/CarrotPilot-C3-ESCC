import importlib
from types import SimpleNamespace

import pytest


PANDA_MODULES = ("panda.python", "panda_tici.python")


class FakeLogger:
  def __init__(self):
    self.debug_calls = []
    self.warning_calls = []
    self.exception_calls = []

  def debug(self, *args):
    self.debug_calls.append(args)

  def warning(self, *args):
    self.warning_calls.append(args)

  def exception(self, *args):
    self.exception_calls.append(args)


class FakeUsbDevice:
  def __init__(self, module, serial_results, *, bcd_device=0x2300, libusb_handle=None):
    self.module = module
    self.serial_results = iter(serial_results)
    self.bcd_device = bcd_device
    self.libusb_handle = libusb_handle

  def getVendorID(self):
    return self.module.Panda.USB_VIDS[0]

  def getProductID(self):
    return self.module.Panda.USB_PIDS[0]

  def getSerialNumber(self):
    result = next(self.serial_results)
    if isinstance(result, Exception):
      raise result
    return result

  def getbcdDevice(self):
    return self.bcd_device

  def open(self):
    assert self.libusb_handle is not None
    return self.libusb_handle


class FakeUsbContext:
  def __init__(self, devices):
    self.devices = devices
    self.opened = False
    self.closed = False

  def open(self):
    self.opened = True

  def close(self):
    self.closed = True

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc, traceback):
    return False

  def getDeviceList(self, *, skip_on_error):
    assert skip_on_error
    return self.devices


class FakeLibusbHandle:
  MISSING_HW_TYPE_RESPONSE = b'\xff\x00\xc1\x3e\xde\xad\xd0\x0d'

  def __init__(self):
    self.claimed_interfaces = []
    self.control_writes = []
    self.closed = False

  def setAutoDetachKernelDriver(self, enabled):
    self.auto_detach = enabled

  def claimInterface(self, interface):
    self.claimed_interfaces.append(interface)

  def controlRead(self, request_type, request, value, index, length, timeout):
    if request == 0xc1:
      return self.MISSING_HW_TYPE_RESPONSE
    if request == 0xdd:
      return bytes((17, 4, 5))
    raise AssertionError(f"unexpected control read: {request:#x}")

  def controlWrite(self, request_type, request, value, index, data, timeout):
    self.control_writes.append((request_type, request, value, index, data, timeout))
    return 0

  def close(self):
    self.closed = True


@pytest.fixture(params=PANDA_MODULES)
def panda_module(request):
  module = importlib.import_module(request.param)
  module.Panda._usb_unavailable_last_log_t = None
  module.Panda._usb_list_unavailable = False
  yield module
  module.Panda._usb_unavailable_last_log_t = None
  module.Panda._usb_list_unavailable = False


def install_usb_context(monkeypatch, module, devices):
  monkeypatch.setattr(module.usb1, "USBContext", lambda: FakeUsbContext(devices))


def install_logger(monkeypatch, module):
  logger = FakeLogger()
  monkeypatch.setattr(module, "logger", logger)
  return logger


def test_usb_list_preserves_successful_discovery(monkeypatch, panda_module):
  serial = "a" * 24
  panda_module.Panda._usb_unavailable_last_log_t = 1.0
  install_usb_context(monkeypatch, panda_module, [FakeUsbDevice(panda_module, [serial])])
  logger = install_logger(monkeypatch, panda_module)

  assert panda_module.Panda.usb_list() == [serial]
  assert not panda_module.Panda.usb_list_unavailable()
  assert panda_module.Panda._usb_unavailable_last_log_t is None
  assert logger.warning_calls == []
  assert logger.exception_calls == []


def test_usb_list_reports_invalid_serial_without_logging_error(monkeypatch, panda_module):
  install_usb_context(monkeypatch, panda_module, [FakeUsbDevice(panda_module, ["short-serial"])])
  logger = install_logger(monkeypatch, panda_module)

  assert panda_module.Panda.usb_list() == []
  assert not panda_module.Panda.usb_list_unavailable()
  assert logger.warning_calls == [("found device with panda descriptors but invalid serial: %s", "short-serial")]
  assert logger.exception_calls == []


@pytest.mark.parametrize("error_name", ("USBErrorAccess", "USBErrorBusy"))
def test_usb_list_throttles_transient_unavailable_errors(monkeypatch, panda_module, error_name):
  error_type = getattr(panda_module.usb1, error_name)
  device = FakeUsbDevice(panda_module, [error_type(), error_type(), error_type()])
  install_usb_context(monkeypatch, panda_module, [device])
  logger = install_logger(monkeypatch, panda_module)
  now = [0.0]
  monkeypatch.setattr(panda_module, "time", SimpleNamespace(monotonic=lambda: now[0]))

  assert panda_module.Panda.usb_list() == []
  assert panda_module.Panda.usb_list_unavailable()
  now[0] = 5.0
  assert panda_module.Panda.usb_list() == []
  assert panda_module.Panda.usb_list_unavailable()
  now[0] = 31.0
  assert panda_module.Panda.usb_list() == []
  assert panda_module.Panda.usb_list_unavailable()

  assert len(logger.warning_calls) == 2
  assert all("not accessible yet" in call[0] for call in logger.warning_calls)
  assert logger.exception_calls == []


def test_usb_list_success_resets_unavailable_throttle(monkeypatch, panda_module):
  serial = "b" * 24
  device = FakeUsbDevice(panda_module, [panda_module.usb1.USBErrorAccess(), serial, panda_module.usb1.USBErrorBusy()])
  install_usb_context(monkeypatch, panda_module, [device])
  logger = install_logger(monkeypatch, panda_module)
  now = [0.0]
  monkeypatch.setattr(panda_module, "time", SimpleNamespace(monotonic=lambda: now[0]))

  assert panda_module.Panda.usb_list() == []
  assert panda_module.Panda.usb_list_unavailable()
  now[0] = 1.0
  assert panda_module.Panda.usb_list() == [serial]
  assert not panda_module.Panda.usb_list_unavailable()
  now[0] = 2.0
  assert panda_module.Panda.usb_list() == []
  assert panda_module.Panda.usb_list_unavailable()

  assert len(logger.warning_calls) == 2
  assert logger.exception_calls == []


def test_usb_list_keeps_traceback_for_unexpected_errors(monkeypatch, panda_module):
  install_usb_context(monkeypatch, panda_module, [FakeUsbDevice(panda_module, [RuntimeError("descriptor failure")])])
  logger = install_logger(monkeypatch, panda_module)

  assert panda_module.Panda.usb_list() == []
  assert not panda_module.Panda.usb_list_unavailable()
  assert logger.warning_calls == []
  assert logger.exception_calls == [("error connecting to panda",)]


def test_usb_list_handles_context_access_error_without_traceback(monkeypatch, panda_module):
  class InaccessibleUsbContext:
    def __enter__(self):
      raise panda_module.usb1.USBErrorAccess()

    def __exit__(self, exc_type, exc, traceback):
      return False

  monkeypatch.setattr(panda_module.usb1, "USBContext", InaccessibleUsbContext)
  logger = install_logger(monkeypatch, panda_module)

  assert panda_module.Panda.usb_list() == []
  assert panda_module.Panda.usb_list_unavailable()
  assert len(logger.warning_calls) == 1
  assert logger.exception_calls == []


@pytest.mark.parametrize(("bcd_device", "expected_mcu_name", "expected_bcd_hw_type", "assume_f4"), (
  (0x0700, "H7", bytearray(b'\x07'), False),
  (0x2300, "F4", None, True),
))
def test_legacy_bootstub_uses_bcd_device_for_mcu_detection(monkeypatch, panda_module, bcd_device, expected_mcu_name,
                                                          expected_bcd_hw_type, assume_f4):
  serial = "c" * 24
  libusb_handle = FakeLibusbHandle()
  device = FakeUsbDevice(panda_module, [serial], bcd_device=bcd_device, libusb_handle=libusb_handle)
  install_usb_context(monkeypatch, panda_module, [device])
  install_logger(monkeypatch, panda_module)

  panda = object.__new__(panda_module.Panda)
  panda._handle_open = False
  panda._connect_serial = serial
  panda._disable_checks = False
  panda._can_speed_kbps = 500
  panda.connect()

  expected_mcu = getattr(panda_module.McuType, expected_mcu_name)
  assert panda._bcd_hw_type == expected_bcd_hw_type
  assert panda._assume_f4_mcu is assume_f4
  assert panda._mcu_type is expected_mcu
  assert panda._mcu_type.config.app_fn == ("panda_h7.bin.signed" if expected_mcu_name == "H7" else "panda.bin.signed")


def test_spi_list_accepts_five_field_connect_contract(monkeypatch, panda_module):
  serial_bytes = bytes(range(12))
  serial = serial_bytes.hex()

  class FakeSpiHandle:
    PROTOCOL_VERSION = 3

    def get_protocol_version(self):
      return serial_bytes + bytes((0, 0xcc, self.PROTOCOL_VERSION))

  monkeypatch.setattr(panda_module, "PandaSpiHandle", FakeSpiHandle)

  context, handle, connected_serial, bootstub, bcd = panda_module.Panda.spi_connect(None)
  assert (context, connected_serial, bootstub, bcd) == (None, serial, False, None)
  assert isinstance(handle, FakeSpiHandle)
  assert panda_module.Panda.spi_list() == [serial]


@pytest.mark.parametrize("jungle_module_name", ("panda.board.jungle", "panda_tici.board.jungle"))
def test_panda_jungle_spi_override_uses_five_field_contract(jungle_module_name):
  jungle_module = importlib.import_module(jungle_module_name)

  assert jungle_module.PandaJungle.spi_connect(None) == (None, None, None, None, None)
  assert jungle_module.PandaJungle.spi_list() == []
