#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SENSOR_SERVICES = ("accelerometer", "gyroscope", "temperatureSensor")
MOTION_SERVICES = ("accelerometer", "gyroscope")
SENSORD_PATTERN = r"(^|[ /.])(system\.sensord\.sensord|sensord)($|[ \t])"


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


def sensord_seen(ps_text: str | None = None) -> bool:
  text = ps_snapshot() if ps_text is None else ps_text
  return re.search(SENSORD_PATTERN, text, re.MULTILINE) is not None


def enum_text(value: Any) -> str:
  try:
    return str(value).split(".")[-1]
  except Exception:
    return str(value)


def vector_norm(values: Any) -> float:
  vals = [float(v) for v in values]
  return math.sqrt(sum(v * v for v in vals))


def message_summary(msg: Any) -> dict[str, Any]:
  which = str(msg.which())
  body = getattr(msg, which)
  result: dict[str, Any] = {
    "which": which,
    "source": enum_text(getattr(body, "source", "")),
    "timestamp": int(getattr(body, "timestamp", 0)),
  }
  measurement = str(body.which())
  result["measurement"] = measurement
  value = getattr(body, measurement)
  if hasattr(value, "v"):
    values = [float(v) for v in value.v]
    result["values"] = values
    result["norm"] = vector_norm(values)
  else:
    result["value"] = float(value)
  return result


def sample_sensor_events(messaging: Any, seconds: float, wait_seconds: float) -> dict[str, Any]:
  socks: dict[str, Any] = {}
  poller = messaging.Poller()
  events: dict[str, list[Any]] = defaultdict(list)
  for service in SENSOR_SERVICES:
    socks[service] = messaging.sub_sock(service, poller=poller, timeout=100)

  deadline = time.monotonic() + max(0.0, wait_seconds)
  while time.monotonic() < deadline:
    if poller.poll(250):
      break
  time.sleep(0.2)
  for sock in socks.values():
    messaging.drain_sock_raw(sock)

  sample_deadline = time.monotonic() + max(0.0, seconds)
  while time.monotonic() < sample_deadline:
    for service, sock in socks.items():
      events[service].extend(messaging.drain_sock(sock))
    time.sleep(0.05)

  updates = {service: len(events.get(service, [])) for service in SENSOR_SERVICES}
  last = {}
  for service, msgs in events.items():
    if msgs:
      last[service] = message_summary(msgs[-1])
  return {
    "seconds": seconds,
    "updates": updates,
    "last": last,
    "stats": sensor_stats(events, seconds),
  }


def sensor_stats(events: dict[str, list[Any]], seconds: float) -> dict[str, Any]:
  stats: dict[str, Any] = {}
  for service, msgs in events.items():
    values = []
    timestamps = []
    for msg in msgs:
      summary = message_summary(msg)
      if "norm" in summary:
        values.append(float(summary["norm"]))
      elif "value" in summary:
        values.append(float(summary["value"]))
      timestamps.append(int(summary["timestamp"]))
    service_stats: dict[str, Any] = {
      "count": len(msgs),
      "frequencyHz": (len(msgs) / seconds) if seconds > 0 else 0.0,
    }
    if values:
      service_stats["mean"] = statistics.fmean(values)
      service_stats["min"] = min(values)
      service_stats["max"] = max(values)
      service_stats["std"] = statistics.pstdev(values) if len(values) > 1 else 0.0
    if len(timestamps) > 1:
      diffs_ms = [(b - a) / 1e6 for a, b in zip(timestamps, timestamps[1:]) if b >= a]
      if diffs_ms:
        service_stats["avgPeriodMs"] = statistics.fmean(diffs_ms)
        service_stats["maxPeriodMs"] = max(diffs_ms)
    stats[service] = service_stats
  return stats


def evaluate(sample: dict[str, Any], require_temperature: bool) -> dict[str, Any]:
  updates = sample.get("updates", {})
  stats = sample.get("stats", {})
  accel_count = int(updates.get("accelerometer", 0) or 0)
  gyro_count = int(updates.get("gyroscope", 0) or 0)
  temp_count = int(updates.get("temperatureSensor", 0) or 0)
  accel_mean = float(stats.get("accelerometer", {}).get("mean", 0.0) or 0.0)
  gyro_mean = float(stats.get("gyroscope", {}).get("mean", 0.0) or 0.0)
  checks = {
    "accelerometerPresent": accel_count > 0,
    "gyroscopePresent": gyro_count > 0,
    "temperaturePresent": (temp_count > 0) if require_temperature else True,
    "accelerometerValueSanity": accel_count > 0 and 5.0 <= accel_mean <= 15.0,
    "gyroscopeValueSanity": gyro_count > 0 and 0.0 <= gyro_mean <= 0.75,
  }
  checks["motionPresent"] = checks["accelerometerPresent"] and checks["gyroscopePresent"]
  checks["valueSanity"] = checks["accelerometerValueSanity"] and checks["gyroscopeValueSanity"]
  return checks


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
  sys.path.insert(0, str(ROOT))
  from cereal import messaging
  from openpilot.system.manager.process_config import managed_processes

  started = False
  before_seen = sensord_seen()
  result: dict[str, Any] = {
    "title": "Genius Pilot C3 IMU Probe",
    "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "repo": str(ROOT),
    "sampleSeconds": args.sample_seconds,
    "waitSeconds": args.wait_seconds,
    "preexistingSensord": before_seen,
    "startedSensord": False,
    "cleanup": {},
    "sample": {},
    "checks": {},
    "ok": False,
  }

  try:
    if not before_seen and not args.no_start:
      os.environ["LSM_SELF_TEST"] = "1"
      managed_processes["sensord"].start()
      started = True
      result["startedSensord"] = True
      time.sleep(1.0)
    result["sample"] = sample_sensor_events(messaging, args.sample_seconds, args.wait_seconds)
    result["checks"] = evaluate(result["sample"], args.require_temperature)
  except Exception as exc:
    result["error"] = str(exc)[:500]
  finally:
    if started:
      try:
        code = managed_processes["sensord"].stop(retry=True, block=True)
        result["cleanup"] = {"stopped": True, "exitCode": code, "sensordSeenAfterStop": sensord_seen()}
      except Exception as exc:
        result["cleanup"] = {"stopped": False, "error": str(exc)[:240], "sensordSeenAfterStop": sensord_seen()}

  required_checks = ("motionPresent", "valueSanity", "temperaturePresent")
  result["ok"] = bool(all(result.get("checks", {}).get(check, False) for check in required_checks) and not result.get("error"))
  return result


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    "Genius Pilot C3 IMU Probe",
    "system.sensord.sensord",
    "accelerometer",
    "gyroscope",
    "temperatureSensor",
    "LSM_SELF_TEST",
    "motionPresent",
    "valueSanity",
    "require_temperature",
  )
  missing = [token for token in required if token not in text]
  if missing:
    print("FAIL C3 IMU probe self-test: missing " + ", ".join(missing))
    return 1
  print("PASS C3 IMU probe self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Run a silent C3 IMU hardware probe based on the upstream sensord test shape.")
  parser.add_argument("--sample-seconds", type=float, default=5.0)
  parser.add_argument("--wait-seconds", type=float, default=5.0)
  parser.add_argument("--no-start", action="store_true", help="only subscribe to an already-running sensord")
  parser.add_argument("--require-temperature", action="store_true", default=True)
  parser.add_argument("--output", type=Path)
  parser.add_argument("--pretty", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

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
