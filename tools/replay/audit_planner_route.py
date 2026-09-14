#!/usr/bin/env python3
"""Open-loop planner audit with all parameter writes blocked; no publishers."""
import argparse
from collections import defaultdict
from contextlib import ExitStack
import json
import math
import time
from pathlib import Path
from unittest.mock import patch  # noqa: TID251 - stdlib write guard for this offline tool

from cereal import messaging
from openpilot.common.params import Params
from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.tools.lib.logreader import LogReader


class RecordedMessages(dict):
  def __init__(self):
    super().__init__()
    self.alive = defaultdict(bool)
    self.valid = defaultdict(bool)
    self.updated = defaultdict(bool)
    self.recv_frame = defaultdict(int)
    self.recv_time = defaultdict(float)
    self.logMonoTime = defaultdict(int)
    self.frame = 0

  def all_checks(self, service_list=None):
    return all(self.alive[k] and self.valid[k] for k in (service_list or self))


def audit(route):
  files = sorted(Path('/data/media/0/realdata').glob(f'{route}--*/rlog.zst'), key=lambda p: int(p.parent.name.rsplit('--', 1)[1]))
  sm = RecordedMessages()
  services = ['carState', 'carControl', 'controlsState', 'radarState', 'modelV2', 'selfdriveState',
              'liveParameters', 'carStateSP', 'carrotMan', 'liveMapDataSP', 'gpsLocation', 'gpsLocationExternal']
  for key in services:
    sm[key] = getattr(messaging.new_message(key), key)
  cp = None
  cp_sp = None
  planner = None
  first = None
  count = 0
  write_attempts = 0
  rows = []
  last_second = -1

  def blocked_write(*args, **kwargs):
    nonlocal write_attempts
    write_attempts += 1

  with ExitStack() as stack:
    for name in ('put', 'put_bool', 'put_int', 'put_float'):
      stack.enter_context(patch.object(Params, name, blocked_write))
    stack.enter_context(patch.object(CarrotParams, '_write_raw', blocked_write))
    for path in files:
      for msg in LogReader(str(path), sort_by_time=True):
        t = msg.logMonoTime / 1e9
        first = t if first is None else first
        name = msg.which()
        if name == 'carParams':
          cp = msg.carParams
        if name == 'carParamsSP':
          cp_sp = msg.carParamsSP
        if name not in sm:
          continue
        sm[name] = getattr(msg, name)
        sm.logMonoTime[name] = msg.logMonoTime
        sm.valid[name] = msg.valid
        if name != 'modelV2' or cp is None or cp_sp is None:
          continue
        sm.frame += 1
        for key in services:
          sm.updated[key] = key == 'modelV2'
          sm.alive[key] = 0 <= t - sm.logMonoTime[key] / 1e9 < (2 if key in ('carrotMan', 'liveMapDataSP') else 0.25)
          sm.recv_time[key] = time.monotonic() - (t - sm.logMonoTime[key] / 1e9)
          sm.recv_frame[key] = sm.frame if sm.alive[key] else 0
        if not all(sm.alive[k] and sm.valid[k] for k in ('carState', 'carControl', 'controlsState', 'radarState', 'modelV2')):
          continue
        if planner is None:
          planner = LongitudinalPlanner(cp, cp_sp)
        planner.update(sm)
        if not math.isfinite(planner.output_a_target):
          raise AssertionError('Non-finite planner acceleration')
        if planner.mpc.solution_status != 0 or planner.carrot_planner_faulted:
          raise AssertionError('Planner/solver failed')
        count += 1
        second = int(t-first)
        if second != last_second and (150 <= second <= 162 or 250 <= second <= 305):
          last_second = second
          cs = sm['carState']
          rows.append({'t': second, 'ceiling': round(cs.vCruiseCluster),
                       'road': round(planner.resolver.speed_limit*3.6), 'roadValid': planner.resolver.speed_limit_valid,
                       'candidateTarget': round(planner.cruise_target_speed, 1),
                       'candidateAccel': round(float(planner.output_a_target), 2),
                       'shouldStop': bool(planner.output_should_stop), 'longEnabled': sm['carControl'].enabled})
  return {'route': route, 'frames': count, 'blocked_parameter_writes': write_attempts, 'rows': rows,
          'limitations': 'Open-loop, current settings. Map memory not recorded. No closed-loop stopping-distance claim.'}


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('route')
  args = parser.parse_args()
  print(json.dumps(audit(args.route), ensure_ascii=False, indent=2))
