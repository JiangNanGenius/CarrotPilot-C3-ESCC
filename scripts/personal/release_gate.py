#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
TAG_RE = re.compile(r"^carrotpilot-c3-escc-(\d{8})-(static|test|stable)(\d*)$")
TOKEN_RE = r"github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]{36,}|gho_[A-Za-z0-9]{36,}|ghu_[A-Za-z0-9]{36,}|ghs_[A-Za-z0-9]{36,}"
OLD_NAMES = [
  "CarrotPilot-C3-" + "Seltos-" + "ESCC",
  "C3-" + "Seltos-" + "ESCC",
  "Celtos-" + "ESCC",
  "Seltos-" + "ESCC",
  "Celtos " + "ESCC",
  "Seltos " + "ESCC",
]
OLD_NAME_RE = "|".join(re.escape(name) for name in OLD_NAMES)

class GateError(Exception):
  pass


def git(args: Sequence[str], check: bool = False) -> Tuple[int, str]:
  proc = subprocess.run(
    ["git", *args],
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  output = proc.stdout.strip()
  if check and proc.returncode != 0:
    raise GateError(f"git {' '.join(args)} failed:\n{output}")
  return proc.returncode, output


def run(cmd: Sequence[str], extra_env: Optional[dict[str, str]] = None) -> None:
  print("$ " + " ".join(cmd))
  env = os.environ.copy()
  if extra_env:
    env.update(extra_env)
  proc = subprocess.run(
    list(cmd),
    cwd=str(ROOT),
    env=env,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  if proc.stdout:
    print(proc.stdout.rstrip())
  if proc.returncode != 0:
    raise GateError(f"command failed: {' '.join(cmd)}")


def require_clean_worktree() -> None:
  _, status = git(["status", "--short"], check=True)
  if status:
    raise GateError("worktree is not clean; commit or stash changes before tagging")


def require_ref_contains(base: str, tip: str, label: str) -> None:
  code, _ = git(["merge-base", "--is-ancestor", base, tip])
  if code != 0:
    raise GateError(f"{label}: {tip} does not contain {base}")


def require_no_grep(pattern: str, label: str) -> None:
  code, output = git(["grep", "-n", "-E", pattern, "--", "."])
  if code == 0:
    raise GateError(f"{label} found:\n{output}")
  if code != 1:
    raise GateError(f"{label} scan failed:\n{output}")


def validate_tag(tag: str, kind: str) -> None:
  match = TAG_RE.match(tag)
  if not match:
    raise GateError(
      "tag must look like carrotpilot-c3-escc-YYYYMMDD-static1, "
      "carrotpilot-c3-escc-YYYYMMDD-test1, or carrotpilot-c3-escc-YYYYMMDD-stable"
    )
  if match.group(2) != kind:
    raise GateError(f"tag kind mismatch: tag says {match.group(2)}, --kind says {kind}")

  code, _ = git(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"])
  if code == 0:
    raise GateError(f"tag already exists: {tag}")


def validate_stable_evidence(path: Optional[str], snapshots: Sequence[str], evidence_dirs: Sequence[str]) -> None:
  if not path and not evidence_dirs:
    raise GateError("stable tags require --road-test-log or --evidence-dir")
  cmd = [
    sys.executable,
    "scripts/personal/road_test_evidence_check.py",
    "--require-device-snapshot",
    "--require-escc-sample",
    "--require-carparams-summary",
    "--require-offline-process-guard",
    "--require-power-cycle-boot",
  ]
  if path:
    cmd.extend(["--road-test-log", path])
  for snapshot in snapshots:
    cmd.extend(["--device-snapshot", snapshot])
  for evidence_dir in evidence_dirs:
    cmd.extend(["--evidence-dir", evidence_dir])
  run(cmd)


def run_static_checks(pending_tag: Optional[str]) -> None:
  env = {"CARROTPILOT_PENDING_RELEASE_TAG": pending_tag} if pending_tag else None
  run([sys.executable, "scripts/personal/update_audit.py"])
  run([sys.executable, "scripts/personal/smoke_check.py"], extra_env=env)
  run([sys.executable, "scripts/personal/escc_offline_preflight.py", "--no-manual"])
  run([sys.executable, "scripts/personal/cplink_preflight.py", "--no-manual"])
  run(["git", "diff", "--check"])


def create_tag(tag: str, kind: str, road_test_log: Optional[str], snapshots: Sequence[str], evidence_dirs: Sequence[str]) -> None:
  head_code, head = git(["rev-parse", "--short=10", "HEAD"], check=True)
  if head_code != 0:
    raise GateError("cannot read HEAD")
  if kind == "stable":
    message = (
      f"{tag}\n\n"
      "Stable personal CarrotPilot C3 ESCC tag.\n"
      f"Road-test log: {road_test_log or '<from evidence dir>'}\n"
      f"Device snapshots: {', '.join(snapshots) if snapshots else '<from evidence dir>'}\n"
      f"Evidence dirs: {', '.join(evidence_dirs) if evidence_dirs else '<none>'}\n"
      "Use only after matching the recorded hardware and vehicle setup."
    )
  elif kind == "test":
    message = (
      f"{tag}\n\n"
      "Controlled-test personal CarrotPilot C3 ESCC tag.\n"
      "Not a stable release and not a completed real-car validation result.\n"
      "Use only for parked checks, evidence collection, and limited low-speed testing with a ready rollback target."
    )
  else:
    message = (
      f"{tag}\n\n"
      "Static-check personal CarrotPilot C3 ESCC tag.\n"
      "Not a stable release and not a real-car validation result.\n"
      "Use only for controlled install or bench/static testing before road use."
    )
  run(["git", "tag", "-a", tag, "-m", message])


def main() -> int:
  parser = argparse.ArgumentParser(description="Gate personal C3 ESCC release tags.")
  parser.add_argument("--tag", required=True, help="release tag to validate or create")
  parser.add_argument("--kind", choices=["static", "test", "stable"], required=True)
  parser.add_argument("--road-test-log", help="required for stable tags")
  parser.add_argument("--device-snapshot", action="append", default=[], help="required for stable tags; may be repeated")
  parser.add_argument("--evidence-dir", action="append", default=[], help="unpacked collect_real_car_evidence.py folder; may be repeated")
  parser.add_argument("--run-checks", action="store_true", help="run all static checks before allowing tag")
  parser.add_argument("--create-tag", action="store_true", help="create annotated local tag after checks pass")
  args = parser.parse_args()

  try:
    print("Personal release gate")
    print(f"repo: {ROOT}")
    print(f"tag : {args.tag}")
    print(f"kind: {args.kind}")

    validate_tag(args.tag, args.kind)
    require_clean_worktree()
    require_ref_contains("origin/c3-wip", "HEAD", "latest C3 base")
    require_ref_contains("personal/c3-escc", "HEAD", "ESCC / Always Offline protection line")
    require_no_grep(TOKEN_RE, "GitHub token-like secret")
    require_no_grep(OLD_NAME_RE, "old repo/project name")

    if args.kind == "stable":
      validate_stable_evidence(args.road_test_log, args.device_snapshot, args.evidence_dir)
    else:
      print("note: static/test tags are not stable and do not prove real-car validation")

    if args.run_checks:
      pending_tag = args.tag if args.kind in {"static", "test"} else None
      run_static_checks(pending_tag)

    if args.create_tag:
      create_tag(args.tag, args.kind, args.road_test_log, args.device_snapshot, args.evidence_dir)
      print(f"created local tag: {args.tag}")
    else:
      print("gate passed; no tag created")
    return 0
  except GateError as exc:
    print("release gate failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
