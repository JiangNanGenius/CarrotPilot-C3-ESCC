import asyncio
from types import SimpleNamespace

from openpilot.selfdrive.carrot.server.features import system
from openpilot.selfdrive.carrot.server.services import device_info


class FakeNativeParams:
  def __init__(self):
    self.values = {
      "CalibrationParams": b"calibration",
      "LiveTorqueParameters": b"torque",
      "LiveParameters": b"parameters",
      "LiveParametersV2": b"parameters-v2",
      "LiveDelay": b"delay",
    }

  def put_bool(self, key, value):
    self.values[key] = bool(value)

  def remove(self, key):
    self.values.pop(key, None)


def test_web_power_actions_write_native_params(monkeypatch):
  native = FakeNativeParams()
  monkeypatch.setattr(system, "NativeParams", lambda: native)
  request = SimpleNamespace(app={})

  assert asyncio.run(system.api_reboot(request)).status == 200
  assert asyncio.run(system.api_poweroff(request)).status == 200

  assert native.values["DoReboot"] is True
  assert native.values["DoShutdown"] is True


def test_web_recalibration_clears_native_learned_params_and_requests_restart(monkeypatch):
  native = FakeNativeParams()
  monkeypatch.setattr(system, "NativeParams", lambda: native)
  request = SimpleNamespace(app={})

  assert asyncio.run(system.api_recalibrate(request)).status == 200

  for key in ("CalibrationParams", "LiveTorqueParameters", "LiveParameters", "LiveParametersV2", "LiveDelay"):
    assert key not in native.values
  assert native.values["OnroadCycleRequested"] is True
  assert native.values["DoReboot"] is True


def test_calibration_status_reads_native_params(monkeypatch):
  reads = []

  class FakeNativeReader:
    def get(self, key):
      reads.append(key)
      return None

  monkeypatch.setattr(device_info, "NativeParams", FakeNativeReader)

  assert device_info.get_calibration_status() == {"calibrated": False, "pitch": None, "yaw": None}
  assert reads == ["CalibrationParams"]
