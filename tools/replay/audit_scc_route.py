#!/usr/bin/env python3
"""Read-only model/SCC replay. Never publishes messages or changes parameters."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from openpilot.tools.lib.logreader import LogReader
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control import MIN_V
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.vision_controller import SmartCruiseControlVision


class ReplayMessages(dict):
  def __init__(self):
    super().__init__()
    self.alive = {}
    self.valid = {}
    self.times = {}


def audit(route, root):
  files = sorted(Path(root).glob(f'{route}--*/rlog.zst'), key=lambda p: int(p.parent.name.rsplit('--', 1)[1]))
  sm = ReplayMessages()
  vision = SmartCruiseControlVision()
  counts = Counter()
  logged_states = Counter()
  maxima = {'all': 0., 'eligible': 0.}
  first = None
  stop_rows = []
  last_stop_second = -1
  activation_examples = []
  for path in files:
    for msg in LogReader(str(path), sort_by_time=True):
      t = msg.logMonoTime / 1e9
      first = t if first is None else first
      name = msg.which()
      if name not in ('modelV2', 'carState', 'carControl', 'controlsState', 'longitudinalPlanSP', 'longitudinalPlan', 'radarState'):
        continue
      sm[name] = getattr(msg, name)
      sm.times[name] = t
      sm.valid[name] = msg.valid
      if name == 'longitudinalPlanSP' and msg.valid:
        p = sm[name]
        logged_states[(str(p.smartCruiseControl.vision.state), str(p.smartCruiseControl.map.state))] += 1
      if name != 'modelV2':
        continue
      required = ('modelV2', 'carState', 'carControl', 'controlsState')
      for key in required:
        sm.alive[key] = key in sm and 0 <= t - sm.times[key] < 0.25
      if not all(sm.alive[key] and sm.valid[key] for key in required):
        counts['missing_or_stale_input'] += 1
        continue
      cs, cc = sm['carState'], sm['carControl']
      rate = np.asarray(sm['modelV2'].orientationRate.z)
      velocity = np.asarray(sm['modelV2'].velocity.x)
      if rate.shape == velocity.shape and len(rate) > 1 and np.all(np.isfinite(rate * velocity)):
        predicted = float(np.percentile(np.abs(rate) * velocity, 97))
        maxima['all'] = max(maxima['all'], predicted)
        eligible = cc.enabled and not cc.cruiseControl.override and cs.vEgo > MIN_V
        if eligible:
          counts['eligible'] += 1
          maxima['eligible'] = max(maxima['eligible'], predicted)
          if predicted >= vision._entering_pred_lat_acc_th:
            counts['eligible_above_entry_threshold'] += 1
      vision.update(sm, cc.enabled, cc.cruiseControl.override, cs.vEgo, cs.aEgo, cs.vCruise / 3.6)
      counts['replayed_model_frames'] += 1
      if vision.is_active:
        counts['replay_active'] += 1
        if vision.output_v_target < cs.vCruise / 3.6:
          counts['replay_target_below_cruise'] += 1
        if len(activation_examples) < 8:
          activation_examples.append([round(t-first, 2), round(cs.vEgo*3.6, 1), round(vision.max_pred_lat_acc, 3),
                                      round(vision.output_v_target*3.6, 1)])
      second = int(t-first)
      if 145 <= second <= 175 and second != last_stop_second:
        last_stop_second = second
        p, radar = sm.get('longitudinalPlan'), sm.get('radarState')
        row = {'t': second, 'speed': round(cs.vEgo*3.6, 2), 'aEgo': round(cs.aEgo, 2),
               'longActive': cc.longActive, 'brake': cs.brakePressed, 'actuatorAccel': round(cc.actuators.accel, 2)}
        if p is not None:
          row.update(planSource=str(p.longitudinalPlanSource), target=round(p.cruiseTargetSpeed, 1),
                     shouldStop=p.shouldStop, traffic=p.trafficState, stopPoint=round(p.trafficStopDistance, 2))
        if radar is not None:
          row.update(dRel=round(radar.leadOne.dRel, 2), leadValid=radar.leadOne.status,
                     leadSpeed=round(radar.leadOne.vLead, 2))
        stop_rows.append(row)
  return {'route': route, 'segments': len(files), 'threshold': vision._entering_pred_lat_acc_th,
          'min_speed_kph': MIN_V*3.6, 'feature_enabled_now': vision.enabled, 'counts': dict(counts),
          'predicted_lat_accel_max': maxima, 'logged_states': {str(k): v for k, v in logged_states.items()},
          'activation_examples': activation_examples, 'near_stop': stop_rows,
          'limitations': 'Current vision settings; open-loop. Map targets not logged. Check reader warnings; dRel is not bumper clearance.'}


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('route')
  parser.add_argument('--root', default='/data/media/0/realdata')
  args = parser.parse_args()
  print(json.dumps(audit(args.route, args.root), ensure_ascii=False, indent=2))
