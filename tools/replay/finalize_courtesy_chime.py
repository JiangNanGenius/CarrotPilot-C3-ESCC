#!/usr/bin/env python3
"""Scoped follow-up to the recorded release; preserve global QuietMode."""
import json
import os
import runpy
import shutil
import signal

from cereal import messaging

deploy = runpy.run_path('/data/codex-validation-20260909-dYONvd/tools/replay/deploy_cruise_release.py')
deploy['offroad_check']()
prod, stage, backup, digest = (deploy[k] for k in ('PROD', 'STAGE', 'BACKUP', 'digest'))
paths = ['selfdrive/ui/soundd.py', 'selfdrive/ui/sunnypilot/layouts/settings/cruise.py', 'selfdrive/carrot_settings.json']
manifest_path = backup / 'manifest.json'
manifest = json.loads(manifest_path.read_text())
assert not (backup / 'quiet-scope').exists()
for name in paths:
  assert digest(prod / name) == manifest['after'][name]
  target = backup / 'quiet-scope' / name
  target.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(prod / name, target)
shutil.copy2(manifest_path, backup / 'quiet-scope/previous-manifest.json')
for name in paths:
  target = prod / name
  temp = target.with_name(target.name + '.courtesy-tmp')
  assert not temp.exists()
  shutil.copy2(stage / name, temp)
  os.replace(temp, target)
  manifest['after'][name] = digest(target)
temp_manifest = backup / 'manifest-quiet-tmp.json'
temp_manifest.write_text(json.dumps(manifest, indent=2))
os.replace(temp_manifest, manifest_path)
os.sync()
sm = messaging.SubMaster(['managerState'])
for _ in range(6):
  sm.update(500)
  if sm.alive['managerState'] and sm.valid['managerState']:
    break
assert sm.alive['managerState'] and sm.valid['managerState']
ui = next(p for p in sm['managerState'].processes if p.name == 'ui' and p.running)
os.kill(ui.pid, signal.SIGTERM)
print('Three-file courtesy sound scope update deployed; manager restarting UI; global QuietMode unchanged.')
