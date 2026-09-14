#!/usr/bin/env python3
"""Recorded traffic-stop timing, sampled at 5 Hz. No publishers or writes."""
import argparse
import json
from pathlib import Path

from openpilot.tools.lib.logreader import LogReader


def audit(route):
  files = sorted(Path('/data/media/0/realdata').glob(f'{route}--*/rlog.zst'), key=lambda p: int(p.parent.name.rsplit('--', 1)[1]))
  state, times, valid = {}, {}, {}
  first = None
  last_sample = -1
  rows = []
  for path in files:
    for msg in LogReader(str(path), sort_by_time=True):
      t = msg.logMonoTime / 1e9
      first = t if first is None else first
      name = msg.which()
      if name not in ('carState', 'carControl', 'longitudinalPlan', 'radarState', 'modelV2'):
        continue
      state[name], times[name], valid[name] = getattr(msg, name), t, msg.valid
      if name != 'longitudinalPlan' or int((t-first)*5) == last_sample:
        continue
      last_sample = int((t-first)*5)
      required = ('carState', 'carControl', 'radarState', 'modelV2', 'longitudinalPlan')
      if not all(s in state and valid[s] and 0 <= t-times[s] < 0.3 for s in required):
        continue
      cs, cc, radar, model, p = (state[s] for s in required)
      rows.append(dict(t=round(t-first, 2), v=round(cs.vEgo*3.6, 2), a=round(cs.aEgo, 2),
                       command=round(cc.actuators.accel, 2), planAccel=round(p.aTarget, 2),
                       active=cc.longActive, brake=cs.brakePressed, gas=cs.gasPressed,
                       traffic=int(p.trafficState), stopPoint=round(p.trafficStopDistance, 2),
                       target=round(p.cruiseTargetSpeed, 2), source=str(p.cruiseTargetSource),
                       mpcSource=str(p.longitudinalPlanSource), shouldStop=p.shouldStop,
                       lead=radar.leadOne.status, dRel=round(radar.leadOne.dRel, 2),
                       modelEndX=round(model.position.x[-1], 2) if model.position.x else None,
                       modelEndV=round(model.velocity.x[-1], 2) if model.velocity.x else None))
  return dict(route=route, segments=len(files), rows=rows,
              limitations='Recorded planner output, not new inference or ground-truth lamp color. Corrupted events limit coverage.')


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('route')
  print(json.dumps(audit(parser.parse_args().route), ensure_ascii=False))
