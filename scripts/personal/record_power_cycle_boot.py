#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
GIT_TIMEOUT_S = 12.0
PARAM_ROOTS = [
  Path("/data/params/d"),
  Path("/data/params"),
  Path("/persist/comma/params/d"),
]

PARAM_KEYS = [
  "PowerCycleBootOk",
  "PowerCycleBootCommit",
  "PowerCycleBootTag",
  "PowerCycleBootRecordedAt",
]


class PowerCycleRecordError(Exception):
  pass


def run(cmd: Sequence[str], timeout: float = GIT_TIMEOUT_S) -> Tuple[int, str]:
  env = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
  }
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=str(ROOT),
      env=env,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      timeout=timeout,
    )
  except subprocess.TimeoutExpired:
    return 124, f"{cmd[0]} timed out after {timeout:.0f}s"
  except OSError as exc:
    return 127, f"{cmd[0]} unavailable: {exc}"
  return proc.returncode, proc.stdout.strip()


def git_value(args: Sequence[str], missing: str = "unknown") -> str:
  code, output = run(["git", "-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args])
  return output if code == 0 and output else missing


def resolve_params_dir(raw: Optional[str]) -> Path:
  if raw:
    return Path(raw).expanduser()
  for root in PARAM_ROOTS:
    if root.exists():
      return root
  return PARAM_ROOTS[0]


def write_param(params_dir: Path, key: str, value: str, dry_run: bool) -> None:
  path = params_dir / key
  print(f"{'would write' if dry_run else 'write'} {path}: {value!r}")
  if dry_run:
    return
  params_dir.mkdir(parents=True, exist_ok=True)
  tmp = path.with_name(f"{path.name}.tmp")
  tmp.write_text(value, encoding="utf-8")
  tmp.replace(path)


def values_for_record() -> Dict[str, str]:
  return {
    "PowerCycleBootOk": "1",
    "PowerCycleBootCommit": git_value(["rev-parse", "--short=12", "HEAD"]),
    "PowerCycleBootTag": git_value(["tag", "--points-at", "HEAD"], missing="").replace("\n", ", "),
    "PowerCycleBootRecordedAt": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
  }


def values_for_clear() -> Dict[str, str]:
  return {
    "PowerCycleBootOk": "0",
    "PowerCycleBootCommit": "",
    "PowerCycleBootTag": "",
    "PowerCycleBootRecordedAt": "",
  }


def record(params_dir: Path, clear: bool, dry_run: bool) -> Dict[str, str]:
  values = values_for_clear() if clear else values_for_record()
  commit = values.get("PowerCycleBootCommit", "")
  if not clear and (not commit or commit == "unknown"):
    raise PowerCycleRecordError("cannot record power-cycle evidence because current git commit is unknown")
  for key in PARAM_KEYS:
    write_param(params_dir, key, values[key], dry_run)
  return values


def self_test() -> None:
  with tempfile.TemporaryDirectory() as tmp:
    params_dir = Path(tmp)
    values = record(params_dir, clear=False, dry_run=False)
    if (params_dir / "PowerCycleBootOk").read_text(encoding="utf-8") != "1":
      raise PowerCycleRecordError("self-test failed to write PowerCycleBootOk=1")
    if (params_dir / "PowerCycleBootCommit").read_text(encoding="utf-8") != values["PowerCycleBootCommit"]:
      raise PowerCycleRecordError("self-test failed to write matching commit")
    record(params_dir, clear=True, dry_run=False)
    if (params_dir / "PowerCycleBootOk").read_text(encoding="utf-8") != "0":
      raise PowerCycleRecordError("self-test failed to clear PowerCycleBootOk")


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Record that the current build booted successfully after an ACC/CAN power cycle."
  )
  parser.add_argument("--params-dir", help="params directory; defaults to /data/params/d on the C3")
  parser.add_argument("--clear", action="store_true", help="clear the recorded confirmation for a new install/test")
  parser.add_argument("--dry-run", action="store_true", help="print the params that would be written")
  parser.add_argument("--self-test", action="store_true", help="run parser/write self-test in a temporary folder")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("OK: power-cycle boot recorder self-test passed")
      return 0
    params_dir = resolve_params_dir(args.params_dir)
    values = record(params_dir, clear=args.clear, dry_run=args.dry_run)
    if args.clear:
      print("OK: cleared power-cycle boot confirmation")
    else:
      print("OK: recorded power-cycle boot confirmation")
      print(f"commit: {values['PowerCycleBootCommit']}")
      print(f"tag: {values['PowerCycleBootTag'] or '<none>'}")
    return 0
  except PowerCycleRecordError as exc:
    print("power-cycle boot recorder failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
