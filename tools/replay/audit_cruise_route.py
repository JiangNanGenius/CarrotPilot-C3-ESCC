#!/usr/bin/env python3
"""Read-only qlog audit, grouped by monotonic time rather than wall clock.

Counts are sampled messages, never numbers of incidents or physical distances.
Does not start services, publish CAN, or write parameters.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from openpilot.tools.lib.logreader import LogReader


def audit(root, route):
  segments = sorted(Path(root).glob(f'{route}--*/qlog.zst'), key=lambda p: int(p.parent.name.rsplit('--', 1)[1]))
  events, sources = Counter(), Counter()
  intervals, invalid = {}, Counter()
  first = last = None
  close_stops = []
  state = {}
  processed = []
  for segment in segments:
    count = 0
    for msg in LogReader(str(segment)):
      t = msg.logMonoTime / 1e9
      first = t if first is None else min(first, t)
      last = t if last is None else max(last, t)
      name = msg.which()
      count += 1
      if not msg.valid:
        invalid[name] += 1
      if name in ('carState', 'carControl', 'radarState', 'longitudinalPlan') and msg.valid:
        state[name] = (t, getattr(msg, name))
      elif name in state and not msg.valid:
        state.pop(name)
      if name == 'onroadEvents':
        for event in msg.onroadEvents:
          key = str(event.name)
          events[key] += 1
          intervals.setdefault(key, [t, t])[1] = t
      elif name == 'longitudinalPlanSP':
        sources[str(msg.longitudinalPlanSP.longitudinalPlanSource)] += 1
      elif name == 'carState' and msg.valid and msg.carState.vEgo < 0.2:
        radar = state.get('radarState')
        control = state.get('carControl')
        if radar and control and 0 <= t - radar[0] < 0.3 and 0 <= t - control[0] < 0.3:
          lead = radar[1].leadOne
          if control[1].longActive and lead.status and lead.dRel < 3:
            close_stops.append((round(t - first, 2), round(lead.dRel, 2), bool(msg.carState.brakePressed)))
    processed.append({'segment': segment.parent.name, 'messages': count})
  return {'route': route, 'segments': processed, 'duration_seconds': None if first is None else last - first,
          'event_samples': events, 'event_first_last_seconds': {key: [a - first, b - first] for key, (a, b) in intervals.items()},
          'planner_source_samples': sources, 'invalid_envelope_samples': invalid,
          'active_close_stop_samples': len(close_stops), 'close_stop_examples': close_stops[:12],
          'limitations': 'qlog samples; reader corruption warnings must be reviewed; dRel is not bumper clearance'}


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('route')
  parser.add_argument('--root', default='/data/media/0/realdata')
  args = parser.parse_args()
  print(json.dumps(audit(args.root, args.route), ensure_ascii=False, indent=2))
