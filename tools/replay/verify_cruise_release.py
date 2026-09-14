#!/usr/bin/env python3
"""Read-only deployed bundle, saved-setting and offroad health verification."""
import hashlib
import json
from pathlib import Path
import time

from cereal import messaging
from openpilot.selfdrive.carrot.carrot_params import CarrotParams


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


backup = Path('/data/codex-cruise-release-backup-20260909')
manifest = json.loads((backup / 'manifest.json').read_text())
mismatches = [name for name, digest in manifest['after'].items() if sha(Path('/data/openpilot') / name) != digest]
assert not mismatches, mismatches
changed_carrot = [p.name for p in (backup / 'params/d_carrot').iterdir()
                  if p.is_file() and sha(p) != sha(Path('/data/params/d_carrot') / p.name)]
assert not changed_carrot, changed_carrot
for key in ('CalibrationParams', 'LiveTorqueParameters'):
  assert sha(backup / 'params/d' / key) == sha(Path('/data/params/d') / key), key
sm = messaging.SubMaster(['deviceState', 'pandaStates', 'managerState'])
end = time.monotonic() + 12
while time.monotonic() < end:
  sm.update(500)
assert all(sm.alive[s] and sm.valid[s] for s in ('deviceState', 'pandaStates', 'managerState'))
assert not sm['deviceState'].started
processes = {p.name: {'running': p.running, 'shouldRun': p.shouldBeRunning, 'exitCode': p.exitCode}
             for p in sm['managerState'].processes}
assert processes['ui']['running'], processes['ui']
bad = {k: v for k, v in processes.items() if v['shouldRun'] and not v['running']}
params = CarrotParams()
print(json.dumps({'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  'files_verified': len(manifest['after']), 'saved_carrot_settings_unchanged': True,
                  'calibration_unchanged': True, 'onroad': sm['deviceState'].started,
                  'panda_count': len(sm['pandaStates']), 'unexpected_stopped_processes': bad,
                  'ui': processes['ui'], 'settings': {k: params.get_int(k) for k in
                    ('TrafficCueSound', 'StopDistanceCarrot', 'TrafficStopBufferCm', 'CarrotSpeedLimitEnable', 'LongitudinalSpeedReference')}}, indent=2))
