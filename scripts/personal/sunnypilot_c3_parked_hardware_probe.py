#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]

PROCESS_PATTERNS = {
  "camerad": r"(^|[ /])camerad($|[ \t])",
  "modeld": r"(^|[ /.])(selfdrive\.modeld\.modeld|modeld)($|[ \t])",
  "modeld_tinygrad": r"(^|[ /.])(sunnypilot/modeld_v2/modeld|modeld_tinygrad|selfdrive\.modeld\.modeld_tinygrad)($|[ \t])",
  "sensord": r"(^|[ /.])(system\.sensord\.sensord|sensord)($|[ \t])",
  "soundd": r"(^|[ /.])(selfdrive\.ui\.soundd|soundd)($|[ \t])",
}

CAMERA_SERVICES = ("roadCameraState", "wideRoadCameraState", "driverCameraState")
MODEL_SERVICES = ("modelV2", "drivingModelData", "cameraOdometry", "modelDataV2SP")
IMU_SERVICES = ("accelerometer", "gyroscope", "temperatureSensor")
CONTROL_PUB_SERVICES = (
  "deviceState",
  "carState",
  "pandaStates",
  "carControl",
  "liveCalibration",
  "driverMonitoringState",
  "selfdriveState",
  "selfdriveStateSP",
  "soundPressure",
  "liveDelay",
)
MANUAL_PROCESS_LOG_DIR = Path("/tmp/genius_parked_hardware_probe")


def ps_snapshot() -> str:
  try:
    proc = subprocess.run(
      ["ps", "-A", "-o", "pid,args"],
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      check=False,
      timeout=5,
    )
    return proc.stdout
  except Exception as exc:
    return f"<ps unavailable: {exc}>"


def process_seen(name: str, ps_text: str | None = None) -> bool:
  pattern = PROCESS_PATTERNS[name]
  text = ps_snapshot() if ps_text is None else ps_text
  return re.search(pattern, text, re.MULTILINE) is not None


def safe_attr(obj: Any, attr: str, default: Any = None) -> Any:
  try:
    return getattr(obj, attr)
  except Exception:
    return default


def enum_text(value: Any) -> str:
  try:
    return str(value).split(".")[-1]
  except Exception:
    return str(value)


def service_summary(message: Any) -> dict[str, Any]:
  summary: dict[str, Any] = {}
  for field in ("frameId", "timestampSof", "timestampEof", "sensor"):
    value = safe_attr(message, field, None)
    if value is not None:
      summary[field] = enum_text(value) if field == "sensor" else int(value)
  union_field = safe_attr(message, "which", lambda: None)()
  if union_field:
    summary["which"] = str(union_field)
  if union_field == "acceleration":
    summary["acceleration"] = [float(v) for v in message.acceleration.v]
  elif union_field == "gyroUncalibrated":
    summary["gyroUncalibrated"] = [float(v) for v in message.gyroUncalibrated.v]
  elif union_field == "temperature":
    summary["temperature"] = float(message.temperature)
  return summary


def process_env() -> dict[str, str]:
  env = os.environ.copy()
  venv_bin = Path("/usr/local/venv/bin")
  if venv_bin.exists():
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
  pythonpath = env.get("PYTHONPATH", "")
  env["PYTHONPATH"] = str(ROOT) if not pythonpath else f"{ROOT}:{pythonpath}"
  return env


def start_manual_process(name: str, manual_processes: dict[str, subprocess.Popen]) -> dict[str, Any]:
  if name != "modeld_tinygrad":
    raise ValueError(f"unsupported manual process: {name}")
  MANUAL_PROCESS_LOG_DIR.mkdir(parents=True, exist_ok=True)
  stdout_path = MANUAL_PROCESS_LOG_DIR / f"{name}.stdout"
  stderr_path = MANUAL_PROCESS_LOG_DIR / f"{name}.stderr"
  stdout = stdout_path.open("wb")
  stderr = stderr_path.open("wb")
  proc = subprocess.Popen(
    ["./modeld"],
    cwd=str(ROOT / "sunnypilot/modeld_v2"),
    env=process_env(),
    stdout=stdout,
    stderr=stderr,
    start_new_session=True,
  )
  stdout.close()
  stderr.close()
  manual_processes[name] = proc
  time.sleep(1.2)
  return {
    "name": name,
    "kind": "manual",
    "alreadyRunning": False,
    "started": True,
    "pid": int(proc.pid or 0),
    "runningAfterStart": proc.poll() is None,
    "exitCodeAfterStart": proc.poll(),
    "stdout": str(stdout_path),
    "stderr": str(stderr_path),
  }


def tail_file(path: Path, limit: int = 4000) -> str:
  try:
    data = path.read_bytes()
  except FileNotFoundError:
    return ""
  except Exception as exc:
    return f"<unable to read {path}: {exc}>"
  text = data[-limit:].decode("utf-8", "replace")
  return text.strip()


def stop_manual_process(name: str, manual_processes: dict[str, subprocess.Popen]) -> dict[str, Any]:
  proc = manual_processes.get(name)
  if proc is None:
    return {"name": name, "kind": "manual", "stopped": True, "exitCode": None, "runningAfterStop": process_seen(name)}
  if proc.poll() is None:
    try:
      os.killpg(proc.pid, signal.SIGINT)
    except ProcessLookupError:
      pass
    try:
      proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
      try:
        os.killpg(proc.pid, signal.SIGKILL)
      except ProcessLookupError:
        pass
      proc.wait(timeout=5)
  return {
    "name": name,
    "kind": "manual",
    "stopped": True,
    "exitCode": proc.poll(),
    "runningAfterStop": process_seen(name),
  }


def start_process(name: str, managed_processes: dict[str, Any],
                  manual_processes: dict[str, subprocess.Popen]) -> dict[str, Any]:
  before = ps_snapshot()
  if process_seen(name, before):
    return {"name": name, "alreadyRunning": True, "started": False, "pid": 0}
  if name == "modeld_tinygrad":
    return start_manual_process(name, manual_processes)
  proc = managed_processes[name]
  proc.start()
  time.sleep(0.8)
  return {
    "name": name,
    "alreadyRunning": False,
    "started": True,
    "pid": int(proc.proc.pid or 0) if proc.proc is not None else 0,
    "runningAfterStart": process_seen(name),
  }


def stop_process(name: str, managed_processes: dict[str, Any],
                 manual_processes: dict[str, subprocess.Popen]) -> dict[str, Any]:
  if name in manual_processes:
    return stop_manual_process(name, manual_processes)
  proc = managed_processes[name]
  try:
    code = proc.stop(retry=True, block=True)
  except Exception as exc:
    return {"name": name, "stopped": False, "error": str(exc)[:240]}
  return {"name": name, "stopped": True, "exitCode": code, "runningAfterStop": process_seen(name)}


def ensure_car_params(params: Any, car: Any, messaging: Any) -> tuple[Any, bool]:
  raw = params.get("CarParams")
  if raw:
    try:
      return messaging.log_from_bytes(raw, car.CarParams), False
    except Exception:
      pass

  cp = car.CarParams(notCar=True, wheelbase=1.0, steerRatio=10.0)
  params.put("CarParams", cp.to_bytes(), block=True)
  return cp, True


def make_publishers(messaging: Any, car: Any, log: Any, HARDWARE: Any) -> tuple[Any, dict[str, Any]]:
  pm = messaging.PubMaster(list(CONTROL_PUB_SERVICES))
  msgs = {service: messaging.new_message(service) for service in CONTROL_PUB_SERVICES if service != "pandaStates"}

  msgs["deviceState"].deviceState.started = True
  msgs["deviceState"].deviceState.deviceType = HARDWARE.get_device_type()

  msgs["carState"].carState.vEgo = 0.0
  msgs["carState"].carState.standstill = True
  msgs["carControl"].carControl.latActive = False
  msgs["liveCalibration"].liveCalibration.rpyCalib = [0.0, 0.0, 0.0]
  msgs["soundPressure"].soundPressure.soundPressureWeightedDb = 60.0
  msgs["liveDelay"].liveDelay.lateralDelay = 0.0

  panda = messaging.new_message("pandaStates", 1)
  panda.pandaStates[0].ignitionLine = True
  panda.pandaStates[0].ignitionCan = True
  panda.pandaStates[0].pandaType = log.PandaState.PandaType.uno
  panda.pandaStates[0].safetyModel = car.CarParams.SafetyModel.silent
  msgs["pandaStates"] = panda

  return pm, msgs


def publish_inputs(pm: Any, msgs: dict[str, Any], car: Any, alert: Any | None,
                   publish_errors: dict[str, str]) -> None:
  if alert is None:
    msgs["selfdriveState"].selfdriveState.alertSound = car.CarControl.HUDControl.AudibleAlert.none
  else:
    msgs["selfdriveState"].selfdriveState.alertSound = alert
  for service, msg in msgs.items():
    try:
      pm.send(service, msg)
      try:
        msg.clear_write_flag()
      except Exception:
        pass
    except Exception as exc:
      publish_errors.setdefault(service, str(exc)[:240])


def sample_existing_services(messaging: Any, services: tuple[str, ...], seconds: float) -> dict[str, Any]:
  result: dict[str, Any] = {
    "seconds": seconds,
    "updates": {service: 0 for service in services},
    "valid": {service: False for service in services},
  }
  sm = messaging.SubMaster(list(services))
  deadline = time.monotonic() + max(0.0, seconds)
  while time.monotonic() < deadline:
    sm.update(20)
    for service in services:
      if sm.updated.get(service, False):
        result["updates"][service] += 1
        result["valid"][service] = bool(sm.valid.get(service, False))
  return result


def sample_messages(messaging: Any, seconds: float, publisher: Callable[[Any | None], None],
                    sound_alert: Any | None, sound_duration: float) -> dict[str, Any]:
  services = [*CAMERA_SERVICES, *MODEL_SERVICES, *IMU_SERVICES]
  result: dict[str, Any] = {
    "seconds": seconds,
    "updates": {service: 0 for service in services},
    "valid": {service: False for service in services},
    "last": {},
  }
  sm = messaging.SubMaster(services)
  deadline = time.monotonic() + seconds
  sound_deadline = time.monotonic() + max(0.0, sound_duration)
  while time.monotonic() < deadline:
    alert = sound_alert if time.monotonic() < sound_deadline else None
    publisher(alert)
    sm.update(20)
    for service in services:
      if sm.updated.get(service, False):
        result["updates"][service] += 1
        result["valid"][service] = bool(sm.valid.get(service, False))
        result["last"][service] = service_summary(sm[service])
  for _ in range(10):
    publisher(None)
    time.sleep(0.02)
  return result


def initialize_speaker(HARDWARE: Any) -> dict[str, Any]:
  result = {"requested": True, "powerSaveDisabled": False, "amplifierInitialized": False, "error": ""}
  try:
    HARDWARE.set_power_save(False)
    result["powerSaveDisabled"] = True
  except Exception as exc:
    result["error"] = f"set_power_save failed: {exc}"
  try:
    amplifier = getattr(HARDWARE, "amplifier", None)
    if amplifier is not None:
      result["amplifierInitialized"] = bool(amplifier.initialize_configuration())
  except Exception as exc:
    result["error"] = (result["error"] + "; " if result["error"] else "") + f"amp init failed: {exc}"
  return result


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
  sys.path.insert(0, str(ROOT))
  from cereal import car, log, messaging
  from openpilot.common.params import Params
  from openpilot.system.hardware import HARDWARE
  from openpilot.system.manager.process_config import managed_processes, is_tinygrad_model

  params = Params()
  cp, created_car_params = ensure_car_params(params, car, messaging)
  model_proc = "modeld_tinygrad" if is_tinygrad_model(False, params, cp) else "modeld"
  preexisting: dict[str, Any] = {}
  if not args.skip_imu:
    preexisting["imu"] = sample_existing_services(messaging, IMU_SERVICES, args.pre_sample_seconds)
  preexisting["sensordProcessSeen"] = process_seen("sensord") if not args.skip_imu else False
  existing_imu = preexisting.get("imu", {}).get("updates", {})
  existing_motion_updates = int(existing_imu.get("accelerometer", 0) or 0) + int(existing_imu.get("gyroscope", 0) or 0)

  requested: list[str] = []
  if not args.skip_camera or not args.skip_model:
    requested.append("camerad")
  if not args.skip_model:
    requested.append(model_proc)
  if not args.skip_imu and not preexisting["sensordProcessSeen"] and existing_motion_updates <= 0:
    requested.append("sensord")
  if not args.skip_sound:
    requested.append("soundd")

  started: list[str] = []
  manual_processes: dict[str, subprocess.Popen] = {}
  process_actions: list[dict[str, Any]] = []
  cleanup_actions: list[dict[str, Any]] = []
  speaker = {"requested": False}
  result: dict[str, Any] = {
    "title": "Genius Pilot C3 Parked Hardware Probe",
    "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "repo": str(ROOT),
    "sampleSeconds": args.sample_seconds,
    "modelProcess": model_proc,
    "createdTemporaryCarParams": created_car_params,
    "requestedProcesses": requested,
    "processes": process_actions,
    "cleanup": cleanup_actions,
    "speaker": speaker,
    "preexisting": preexisting,
    "publishErrors": {},
    "messages": {},
    "postProcessSeen": {},
    "ok": False,
  }

  try:
    if not args.skip_sound:
      speaker.update(initialize_speaker(HARDWARE))

    for name in requested:
      action = start_process(name, managed_processes, manual_processes)
      process_actions.append(action)
      if action.get("started"):
        started.append(name)

    pm, msgs = make_publishers(messaging, car, log, HARDWARE)
    publish_errors: dict[str, str] = result["publishErrors"]
    sound_alert = car.CarControl.HUDControl.AudibleAlert.engage if not args.skip_sound else None
    result["messages"] = sample_messages(
      messaging,
      max(0.0, args.sample_seconds),
      lambda alert: publish_inputs(pm, msgs, car, alert, publish_errors),
      sound_alert,
      args.sound_seconds,
    )
  except Exception as exc:
    result["error"] = str(exc)[:400]
  finally:
    for name in reversed(started):
      cleanup_actions.append(stop_process(name, managed_processes, manual_processes))
    if created_car_params:
      try:
        params.remove("CarParams")
      except Exception:
        pass

  ps_after = ps_snapshot()
  result["postProcessSeen"] = {name: process_seen(name, ps_after) for name in requested}
  result["manualLogs"] = {
    name: {
      "stdoutTail": tail_file(MANUAL_PROCESS_LOG_DIR / f"{name}.stdout"),
      "stderrTail": tail_file(MANUAL_PROCESS_LOG_DIR / f"{name}.stderr"),
    }
    for name in manual_processes
  }
  updates = result.get("messages", {}).get("updates", {})
  camera_ok = args.skip_camera or any(int(updates.get(service, 0) or 0) > 0 for service in CAMERA_SERVICES)
  model_ok = args.skip_model or all(int(updates.get(service, 0) or 0) > 0 for service in ("modelV2", "cameraOdometry"))
  imu_ok = args.skip_imu or all(int(updates.get(service, 0) or 0) > 0 for service in ("accelerometer", "gyroscope"))
  sound_ok = args.skip_sound or any(action.get("name") == "soundd" and (action.get("alreadyRunning") or action.get("runningAfterStart")) for action in process_actions)
  cleanup_ok = all(action.get("stopped") for action in cleanup_actions)
  result["checks"] = {
    "cameraMessages": camera_ok,
    "modelMessages": model_ok,
    "imuMessages": imu_ok,
    "sounddStartedOrAlreadyRunning": sound_ok,
    "startedProcessesStopped": cleanup_ok,
  }
  result["ok"] = bool(camera_ok and model_ok and imu_ok and sound_ok and cleanup_ok and not result.get("error"))
  return result


def self_test() -> int:
  required = (
    "modeld_tinygrad",
    "camerad",
    "sensord",
    "soundd",
    "cameraOdometry",
    "accelerometer",
    "gyroscope",
    "AudibleAlert.engage",
    "--with-sound",
    "if not args.with_sound",
    "startedProcessesStopped",
  )
  text = Path(__file__).read_text(encoding="utf-8")
  missing = [token for token in required if token not in text]
  if missing:
    print("FAIL parked hardware probe self-test: missing " + ", ".join(missing))
    return 1
  print("PASS parked hardware probe self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Run a parked C3 hardware probe for cameras, modeld, IMU, and optional speaker checks.")
  parser.add_argument("--pre-sample-seconds", type=float, default=1.0)
  parser.add_argument("--sample-seconds", type=float, default=12.0)
  parser.add_argument("--sound-seconds", type=float, default=1.2)
  parser.add_argument("--skip-camera", action="store_true")
  parser.add_argument("--skip-model", action="store_true")
  parser.add_argument("--skip-imu", action="store_true")
  parser.add_argument("--skip-sound", action="store_true")
  parser.add_argument("--with-sound", action="store_true", help="explicitly play a short audible alert during the speaker probe")
  parser.add_argument("--output", type=Path)
  parser.add_argument("--pretty", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()
  if not args.with_sound:
    args.skip_sound = True

  report = run_probe(args)
  text = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True)
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
  else:
    print(text)
  return 0 if report["ok"] else 2


if __name__ == "__main__":
  raise SystemExit(main())
