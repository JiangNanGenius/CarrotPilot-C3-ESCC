#!/usr/bin/env python3
"""One scoped C3 release: verify/backup, stop manager, replace coherent files.

Run on the device with --apply only after native tests/replay. No model or
parameter writes. Caller must verify imports and reboot after success.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

PROD = Path('/data/openpilot')
STAGE = Path('/data/codex-validation-20260909-dYONvd')
BACKUP = Path('/data/codex-cruise-release-backup-20260909')
MANIFEST = STAGE / 'artifacts/20260909-scc-recovery/release-files.txt'


def digest(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def manager_pids():
  result = []
  for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
      continue
    try:
      args = (proc / 'cmdline').read_bytes().split(b'\0')
      if b'./manager.py' in args and (proc / 'cwd').resolve() == PROD / 'system/manager':
        result.append(int(proc.name))
    except (FileNotFoundError, PermissionError, ProcessLookupError):
      continue
  return result


def offroad_check():
  probe = '''
from cereal import messaging
from openpilot.common.params import Params
sm = messaging.SubMaster(['deviceState', 'pandaStates', 'managerState'])
for _ in range(8):
  sm.update(500)
  if all(sm.alive[s] and sm.valid[s] for s in ('deviceState','pandaStates','managerState')): break
assert all(sm.alive[s] and sm.valid[s] for s in ('deviceState','pandaStates','managerState')), 'No fresh offroad evidence'
assert not Params().get_bool('IsOnroad') and not sm['deviceState'].started
assert not any(p.ignitionLine or p.ignitionCan for p in sm['pandaStates'])
assert not any(p.running and p.name in ('controlsd','plannerd','card') for p in sm['managerState'].processes)
print('fresh offroad gate passed')
'''
  subprocess.run(['/usr/local/venv/bin/python', '-c', probe], cwd=PROD, env={**os.environ, 'PYTHONPATH': str(PROD)}, check=True)


def main(apply):
  assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROD, text=True).strip() == '0498a35497800ba9514459187f04d3099a41b834'
  files = MANIFEST.read_text().splitlines()
  assert len(files) == len(set(files)) and len(files) < 100
  for name in files:
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert (STAGE / name).is_file() and not (STAGE / name).is_symlink(), name
    assert not (PROD / name).is_symlink(), name
  allowed_dirty = set(files)
  changes = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=PROD, text=True).splitlines()
  assert all(line[3:] in allowed_dirty for line in changes), 'Unrelated production changes; inspect before proceeding'
  offroad_check()
  hashes = {name: digest(STAGE / name) for name in files}
  print(json.dumps({'files': len(files), 'bytes': sum((STAGE / n).stat().st_size for n in files), 'manager': manager_pids()}))
  if not apply:
    return
  assert not BACKUP.exists(), 'Never overwrite the original backup'
  BACKUP.mkdir(mode=0o700)
  old = {}
  for name in files:
    src = PROD / name
    old[name] = digest(src) if src.exists() else None
    if src.exists():
      dst = BACKUP / 'files' / name
      dst.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(src, dst)
  # Snapshot the resolved stores, not paramsd's short-lived staging files at
  # the root. Native d is a symlink; copying it alone would not back up values.
  for store in ('d', 'd_carrot'):
    shutil.copytree(Path('/data/params') / store, BACKUP / 'params' / store,
                    ignore=shutil.ignore_patterns('.tmp*', '*.tmp'))
  (BACKUP / 'manifest.json').write_text(json.dumps({'before': old, 'after': hashes}, indent=2))
  os.sync()
  offroad_check()
  pids = manager_pids()
  assert pids
  # Parent forwards SIGTERM to its child, whose finally block stops all workers.
  os.kill(min(pids), signal.SIGTERM)
  deadline = time.monotonic() + 45
  while manager_pids() and time.monotonic() < deadline:
    time.sleep(0.5)
  assert not manager_pids(), 'Manager did not shut down; no files replaced'
  replaced = []
  try:
    for name in files:
      src, dst = STAGE / name, PROD / name
      assert digest(src) == hashes[name], 'Stage changed during deployment'
      dst.parent.mkdir(parents=True, exist_ok=True)
      temp = dst.with_name(dst.name + '.codex-release-tmp')
      assert not temp.exists()
      shutil.copy2(src, temp)
      os.replace(temp, dst)
      replaced.append(name)
    os.sync()
    assert all(digest(PROD / name) == hashes[name] for name in files)
    (BACKUP / 'DEPLOYED').touch()
    print('DEPLOYED: all hashes matched; manager stopped; reboot and verify required', flush=True)
  except BaseException:
    for name in replaced:
      dst = PROD / name
      if old[name] is None:
        archive = BACKUP / 'failed-new-files' / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        os.replace(dst, archive)
      else:
        temp = dst.with_name(dst.name + '.codex-rollback-tmp')
        shutil.copy2(BACKUP / 'files' / name, temp)
        os.replace(temp, dst)
    os.sync()
    raise


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--apply', action='store_true')
  main(parser.parse_args().apply)
