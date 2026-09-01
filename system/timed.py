#!/usr/bin/env python3
import datetime
import subprocess
import time
from typing import NoReturn

import cereal.messaging as messaging
from openpilot.common.time_helpers import min_date, MAX_DATE, system_time_valid
from openpilot.common.swaglog import cloudlog
from openpilot.common.params import Params
from openpilot.common.gps import get_gps_location_service

TIME_CHECKPOINT_PARAM = "LastKnownSystemTime"
TIME_CHECKPOINT_INTERVAL = datetime.timedelta(hours=1)
DURABLE_TIME_PARAMS = (TIME_CHECKPOINT_PARAM, "LastUpdateTime", "UpdaterLastFetchTime")


def utc_now() -> datetime.datetime:
  return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def as_utc_naive(value: datetime.datetime) -> datetime.datetime:
  if value.tzinfo is not None:
    return value.astimezone(datetime.UTC).replace(tzinfo=None)
  return value


def valid_time(value: datetime.datetime) -> bool:
  return min_date() < value < MAX_DATE


def set_time(new_time: datetime.datetime) -> bool:
  new_time = as_utc_naive(new_time)
  diff = utc_now() - new_time
  if abs(diff) < datetime.timedelta(seconds=10):
    cloudlog.debug(f"Time diff too small: {diff}")
    return False

  cloudlog.debug(f"Setting time to {new_time}")
  try:
    subprocess.run(f"TZ=UTC date -s '{new_time}'", shell=True, check=True)
  except subprocess.CalledProcessError:
    cloudlog.exception("timed.failed_setting_time")
    return False
  return True


def restore_time_from_durable_state(params: Params) -> datetime.datetime | None:
  """Keep rebooted offline devices from falling behind their last known UTC."""
  candidates = []
  for key in DURABLE_TIME_PARAMS:
    try:
      value = params.get(key)
      if isinstance(value, datetime.datetime):
        value = as_utc_naive(value)
        if valid_time(value):
          candidates.append(value)
    except Exception:
      cloudlog.exception(f"timed.failed_reading_{key}")

  if not candidates:
    return None

  newest_known_time = max(candidates)
  if newest_known_time > utc_now() + datetime.timedelta(seconds=10):
    cloudlog.warning(f"Restoring time from durable state: {newest_known_time}")
    set_time(newest_known_time)
  return newest_known_time


def update_time_checkpoint(params: Params, last_checkpoint: datetime.datetime | None,
                           now: datetime.datetime | None = None, *, force: bool = False,
                           trusted: bool = False) -> datetime.datetime | None:
  """Persist a bounded-rate wall-clock floor for the next offline boot."""
  now = as_utc_naive(now or utc_now())
  if not valid_time(now):
    return last_checkpoint

  if last_checkpoint is not None:
    last_checkpoint = as_utc_naive(last_checkpoint)
    if now <= last_checkpoint and not trusted:
      return last_checkpoint
    if not force and abs(now - last_checkpoint) < TIME_CHECKPOINT_INTERVAL:
      return last_checkpoint

  try:
    params.put(TIME_CHECKPOINT_PARAM, now)
  except Exception:
    cloudlog.exception("timed.failed_writing_time_checkpoint")
    return last_checkpoint
  return now


def main() -> NoReturn:
  """
    timed has two responsibilities:
    - getting the current time from GPS
    - publishing the time in the logs

    AGNOS will also use NTP to update the time.
  """

  params = Params()
  last_checkpoint = restore_time_from_durable_state(params)
  last_started = params.get_bool("IsOnroad")
  gps_location_service = get_gps_location_service(params)

  pm = messaging.PubMaster(['clocks'])
  sm = messaging.SubMaster([gps_location_service, 'deviceState'])
  while True:
    sm.update(1000)

    started_changed = False
    if sm.updated['deviceState']:
      started = sm['deviceState'].started
      started_changed = started != last_started
      last_started = started
    last_checkpoint = update_time_checkpoint(params, last_checkpoint, force=started_changed)

    msg = messaging.new_message('clocks')
    msg.valid = system_time_valid()
    msg.clocks.wallTimeNanos = time.time_ns()
    pm.send('clocks', msg)

    gps = sm[gps_location_service]
    gps_time = datetime.datetime.fromtimestamp(gps.unixTimestampMillis / 1000., datetime.UTC).replace(tzinfo=None)
    if not sm.updated[gps_location_service] or (time.monotonic() - sm.logMonoTime[gps_location_service] / 1e9) > 2.0:
      continue
    if not gps.hasFix:
      continue
    if gps_time < min_date() or gps_time > MAX_DATE:
      continue

    if set_time(gps_time):
      last_checkpoint = update_time_checkpoint(params, last_checkpoint, gps_time, force=True, trusted=True)
    time.sleep(10)

if __name__ == "__main__":
  main()
