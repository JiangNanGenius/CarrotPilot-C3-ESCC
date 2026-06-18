#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASELINE_PATH = ROOT / "docs/personal/UPSTREAM_BASELINES.json"

sys.path.insert(0, str(SCRIPT_DIR))
import update_audit  # noqa: E402


@dataclass(frozen=True)
class SourcePlan:
  name: str
  purpose: str
  remote_ref: str
  local_ref: str
  remote_oid: str
  local_oid: str
  remote_ahead: int
  local_ahead: int
  status: str
  high_risk_files: List[str]
  new_commits: List[str]

  @property
  def can_fast_forward(self) -> bool:
    return self.status == "remote-ahead"


def git(args: Sequence[str], check: bool = False) -> str:
  proc = subprocess.run(
    ["git", *args],
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  output = proc.stdout.strip()
  if check and proc.returncode != 0:
    raise RuntimeError("git %s failed:\n%s" % (" ".join(args), output))
  if proc.returncode != 0:
    return ""
  return output


def full_rev(ref: str) -> str:
  return git(["rev-parse", ref])


def short_rev(ref: str) -> str:
  output = git(["rev-parse", "--short=10", ref])
  return output or "missing"


def ref_exists(ref: str) -> bool:
  return bool(git(["rev-parse", "--verify", "--quiet", ref]))


def is_ancestor(base: str, tip: str) -> bool:
  proc = subprocess.run(
    ["git", "merge-base", "--is-ancestor", base, tip],
    cwd=str(ROOT),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )
  return proc.returncode == 0


def rev_count(base: str, tip: str) -> int:
  output = git(["rev-list", "--count", f"{base}..{tip}"])
  try:
    return int(output)
  except ValueError:
    return -1


def status_for(local_ahead: int, remote_ahead: int) -> str:
  if local_ahead == 0 and remote_ahead == 0:
    return "aligned"
  if local_ahead == 0 and remote_ahead > 0:
    return "remote-ahead"
  if local_ahead > 0 and remote_ahead == 0:
    return "local-ahead"
  if local_ahead > 0 and remote_ahead > 0:
    return "diverged"
  return "unknown"


def read_new_commits(local_ref: str, remote_ref: str, limit: int) -> List[str]:
  output = git(["log", "--oneline", f"--max-count={limit}", f"{local_ref}..{remote_ref}"])
  if not output:
    return []
  return output.splitlines()


def read_changed_files(local_ref: str, remote_ref: str) -> List[str]:
  output = git(["diff", "--name-only", f"{local_ref}..{remote_ref}"])
  if not output:
    return []
  return output.splitlines()


def build_plan(max_commits: int, max_files: int) -> List[SourcePlan]:
  plans: List[SourcePlan] = []
  for source in update_audit.SOURCES:
    if not ref_exists(source.local_ref) or not ref_exists(source.remote_ref):
      plans.append(SourcePlan(
        name=source.name,
        purpose=source.purpose,
        remote_ref=source.remote_ref,
        local_ref=source.local_ref,
        remote_oid=short_rev(source.remote_ref),
        local_oid=short_rev(source.local_ref),
        remote_ahead=-1,
        local_ahead=-1,
        status="missing-ref",
        high_risk_files=[],
        new_commits=[],
      ))
      continue

    local_ahead = rev_count(source.remote_ref, source.local_ref)
    remote_ahead = rev_count(source.local_ref, source.remote_ref)
    status = status_for(local_ahead, remote_ahead)
    changed = read_changed_files(source.local_ref, source.remote_ref) if remote_ahead > 0 else []
    risky = update_audit.high_risk_matches(changed)[:max_files]
    commits = read_new_commits(source.local_ref, source.remote_ref, max_commits) if remote_ahead > 0 else []
    plans.append(SourcePlan(
      name=source.name,
      purpose=source.purpose,
      remote_ref=source.remote_ref,
      local_ref=source.local_ref,
      remote_oid=short_rev(source.remote_ref),
      local_oid=short_rev(source.local_ref),
      remote_ahead=remote_ahead,
      local_ahead=local_ahead,
      status=status,
      high_risk_files=risky,
      new_commits=commits,
    ))
  return plans


def print_plan(plans: Sequence[SourcePlan]) -> None:
  print("Personal upstream update plan")
  print(f"repo: {ROOT}")
  branch = git(["branch", "--show-current"]) or "(detached)"
  print(f"current branch: {branch} @ {short_rev('HEAD')}")
  print()

  for plan in plans:
    print(f"## {plan.name}")
    print(f"purpose: {plan.purpose}")
    print(f"local : {plan.local_ref} @ {plan.local_oid}")
    print(f"remote: {plan.remote_ref} @ {plan.remote_oid}")
    print(f"status: {plan.status}")
    if plan.remote_ahead > 0:
      print(f"remote ahead: {plan.remote_ahead} commit(s)")
      if plan.new_commits:
        print("new commits:")
        for commit in plan.new_commits:
          print(f"- {commit}")
      if plan.high_risk_files:
        print("high-risk files:")
        for path in plan.high_risk_files:
          print(f"- {path}")
      else:
        print("high-risk files: none in listed paths")
    if plan.status == "diverged":
      print("action: manual review required before syncing this tracking ref")
    elif plan.status == "remote-ahead":
      print("action: review, then fast-forward local tracking ref")
    elif plan.status == "local-ahead":
      print("action: local tracking ref is ahead; do not overwrite without review")
    elif plan.status == "aligned":
      print("action: no sync needed")
    else:
      print("action: fix missing refs/remotes first")
    print()

  fast_forward = [plan for plan in plans if plan.can_fast_forward]
  risky = [plan for plan in plans if plan.high_risk_files]
  diverged = [plan for plan in plans if plan.status == "diverged"]

  print("## Suggested next commands")
  print("- python3 scripts/personal/update_audit.py --fetch")
  print("- python3 scripts/personal/upstream_update_plan.py --fetch")
  if fast_forward:
    print("- python3 scripts/personal/upstream_update_plan.py --fetch --apply-tracking")
    print("- python3 scripts/personal/smoke_check.py")
    print("- python3 scripts/personal/escc_offroad_preflight.py --no-manual")
    print("- python3 scripts/personal/cplink_preflight.py --no-manual")
    print("- python3 scripts/personal/upstream_update_plan.py --write-baselines")
  else:
    print("- no local tracking fast-forward is currently needed")
  if risky:
    print("- high-risk paths changed: run the full update checklist before any test tag")
  if diverged:
    print("- one or more tracking refs diverged: inspect manually before applying updates")


def apply_tracking(plans: Sequence[SourcePlan]) -> int:
  applied = 0
  for plan in plans:
    if not plan.can_fast_forward:
      continue
    if not is_ancestor(plan.local_ref, plan.remote_ref):
      raise RuntimeError(f"{plan.local_ref} is not an ancestor of {plan.remote_ref}")
    old_oid = full_rev(plan.local_ref)
    new_oid = full_rev(plan.remote_ref)
    git(["update-ref", f"refs/heads/{plan.local_ref}", new_oid, old_oid], check=True)
    print(f"fast-forwarded {plan.local_ref}: {plan.local_oid} -> {plan.remote_oid}")
    applied += 1
  if applied == 0:
    print("no tracking refs needed fast-forwarding")
  return applied


def write_baselines(plans: Sequence[SourcePlan]) -> None:
  baselines: Dict[str, str] = {}
  for plan in plans:
    oid = full_rev(plan.local_ref)
    if not oid:
      raise RuntimeError(f"cannot resolve {plan.local_ref}")
    baselines[plan.local_ref] = oid

  data = {
    "updated_at": date.today().isoformat(),
    "project": "CarrotPilot-C3-ESCC",
    "description": (
      "Reviewed upstream/tracking baselines used by GitHub Actions Upstream Watch. "
      "ajouatom/openpilot:c3-wip is treated as the current CarrotPilot / CarPad C3 main source."
    ),
    "baselines": baselines,
  }
  BASELINE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(f"wrote {BASELINE_PATH.relative_to(ROOT)}")


def self_test() -> None:
  cases = [
    ((0, 0), "aligned"),
    ((0, 3), "remote-ahead"),
    ((2, 0), "local-ahead"),
    ((1, 1), "diverged"),
    ((-1, -1), "unknown"),
  ]
  for args, expected in cases:
    actual = status_for(*args)
    if actual != expected:
      raise AssertionError(f"status_for{args} expected {expected}, got {actual}")
  print("OK: upstream update plan self-test passed")


def main() -> int:
  parser = argparse.ArgumentParser(description="Create a safe local plan for pulling reviewed upstream CarrotPilot sources.")
  parser.add_argument("--fetch", action="store_true", help="fetch configured source remotes before planning")
  parser.add_argument("--apply-tracking", action="store_true", help="fast-forward local upstream/tracking refs that are strictly behind")
  parser.add_argument("--write-baselines", action="store_true", help="rewrite docs/personal/UPSTREAM_BASELINES.json from local tracking refs")
  parser.add_argument("--strict", action="store_true", help="return non-zero when any source is not aligned")
  parser.add_argument("--max-commits", type=int, default=8, help="number of new commit titles to print for each source")
  parser.add_argument("--max-files", type=int, default=20, help="number of high-risk changed files to print for each source")
  parser.add_argument("--self-test", action="store_true", help="run pure classification self-test")
  args = parser.parse_args()

  if args.self_test:
    self_test()
    return 0

  if args.fetch:
    update_audit.fetch_sources(update_audit.SOURCES)

  plans = build_plan(args.max_commits, args.max_files)
  print_plan(plans)

  if args.apply_tracking:
    apply_tracking(plans)
    plans = build_plan(args.max_commits, args.max_files)

  if args.write_baselines:
    write_baselines(plans)

  if args.strict and any(plan.status != "aligned" for plan in plans):
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
