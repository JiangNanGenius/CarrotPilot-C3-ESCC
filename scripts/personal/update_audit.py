#!/usr/bin/env python3
import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]


HIGH_RISK_PATHS = [
  "opendbc_repo/opendbc/car/hyundai/",
  "opendbc_repo/opendbc/dbc/",
  "panda/board/safety/",
  "common/params_keys.h",
  "cereal/",
  "selfdrive/controls/",
  "selfdrive/carrot/",
  "selfdrive/carrot_settings.json",
  "selfdrive/apilot.json",
  "system/manager/process_config.py",
]


@dataclass(frozen=True)
class Source:
  name: str
  remote: str
  remote_ref: str
  local_ref: str
  purpose: str


SOURCES = [
  Source("C3 CarrotPilot base", "origin", "origin/c3-wip", "upstream/c3-wip", "main base for C3 clone"),
  Source("C4 side line", "origin", "origin/carrot-wip", "tracking/c4", "low-priority side line"),
  Source("jixie atune", "jixie", "jixie/atune", "tracking/jixie-atune", "Auto-Tuner and web features"),
  Source("jixie CP app", "jixie", "jixie/master", "tracking/jixie-master", "CP搭子 / Navipilot app reference"),
  Source("fishop cp", "fishop", "fishop/cp", "tracking/fishop-cp", "ESCC and China app/nav reference"),
]


class Audit:
  def __init__(self) -> None:
    self.failures: List[str] = []
    self.warnings: List[str] = []
    self.notes: List[str] = []

  def fail(self, message: str) -> None:
    self.failures.append(message)

  def warn(self, message: str) -> None:
    self.warnings.append(message)

  def note(self, message: str) -> None:
    self.notes.append(message)


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
    raise RuntimeError(f"git {' '.join(args)} failed:\n{output}")
  return proc.returncode, output


def ref_exists(ref: str) -> bool:
  code, _ = git(["rev-parse", "--verify", "--quiet", ref])
  return code == 0


def rev(ref: str) -> str:
  code, output = git(["rev-parse", "--short=10", ref])
  return output if code == 0 else "missing"


def is_ancestor(base: str, tip: str) -> bool:
  code, _ = git(["merge-base", "--is-ancestor", base, tip])
  return code == 0


def ahead_count(base: str, tip: str) -> int:
  code, output = git(["rev-list", "--count", f"{base}..{tip}"])
  if code != 0:
    return -1
  try:
    return int(output)
  except ValueError:
    return -1


def commit_titles(base: str, tip: str, limit: int) -> List[str]:
  code, output = git(["log", "--oneline", f"--max-count={limit}", f"{base}..{tip}"])
  if code != 0 or not output:
    return []
  return output.splitlines()


def changed_files(base: str, tip: str) -> List[str]:
  code, output = git(["diff", "--name-only", f"{base}..{tip}"])
  if code != 0 or not output:
    return []
  return output.splitlines()


def high_risk_matches(files: Iterable[str]) -> List[str]:
  matches: List[str] = []
  for file in files:
    for path in HIGH_RISK_PATHS:
      if path.endswith("/"):
        if file.startswith(path):
          matches.append(file)
          break
      elif file == path:
        matches.append(file)
        break
  return matches


def fetch_sources(sources: Sequence[Source]) -> None:
  seen = []
  for source in sources:
    if source.remote in seen:
      continue
    seen.append(source.remote)
    code, output = git(["fetch", source.remote])
    if code != 0:
      raise RuntimeError(f"git fetch {source.remote} failed:\n{output}")


def print_list(title: str, items: Sequence[str], max_items: int) -> None:
  if not items:
    return
  print(f"  {title}:")
  for item in items[:max_items]:
    print(f"    - {item}")
  remaining = len(items) - max_items
  if remaining > 0:
    print(f"    - ... {remaining} more")


def audit_worktree(report: Audit) -> str:
  _, branch = git(["branch", "--show-current"])
  code, status = git(["status", "--short"])
  if code != 0:
    report.fail("cannot read git status")
  elif status:
    report.warn("worktree has uncommitted changes")

  if ref_exists("origin/c3-wip") and not is_ancestor("origin/c3-wip", "HEAD"):
    report.fail("HEAD does not contain latest fetched origin/c3-wip")
  if ref_exists("personal/c3-escc") and not is_ancestor("personal/c3-escc", "HEAD"):
    report.fail("current branch does not contain personal/c3-escc protection line")

  return branch or "(detached)"


def audit_source(source: Source, report: Audit, max_commits: int, max_files: int) -> None:
  print(f"\n## {source.name}")
  print(f"purpose: {source.purpose}")
  print(f"local : {source.local_ref} @ {rev(source.local_ref)}")
  print(f"remote: {source.remote_ref} @ {rev(source.remote_ref)}")

  missing = [ref for ref in (source.local_ref, source.remote_ref) if not ref_exists(ref)]
  if missing:
    report.warn(f"{source.name}: missing ref(s): {', '.join(missing)}")
    return

  if is_ancestor(source.remote_ref, source.local_ref) and is_ancestor(source.local_ref, source.remote_ref):
    print("status: aligned")
    return

  local_ahead = ahead_count(source.remote_ref, source.local_ref)
  remote_ahead = ahead_count(source.local_ref, source.remote_ref)
  print(f"status: local ahead {local_ahead}, remote ahead {remote_ahead}")

  if remote_ahead > 0:
    report.warn(f"{source.name}: remote has {remote_ahead} new commit(s) since local tracking ref")
    print_list("new commits", commit_titles(source.local_ref, source.remote_ref, max_commits), max_commits)
    files = changed_files(source.local_ref, source.remote_ref)
    risky = high_risk_matches(files)
    if risky:
      report.warn(f"{source.name}: new commits touch high-risk paths")
      print_list("high-risk files", risky, max_files)
    else:
      print("  high-risk files: none")

  if local_ahead > 0 and remote_ahead > 0:
    report.warn(f"{source.name}: local tracking ref and remote ref diverged")
  elif local_ahead > 0:
    report.note(f"{source.name}: local tracking ref is ahead of remote")


def print_next_steps(report: Audit) -> None:
  print("\n## Required personal checks after merge or rebase")
  print("- python3 scripts/personal/smoke_check.py")
  print("- python3 scripts/personal/escc_offline_preflight.py --no-manual")
  print("- python3 scripts/personal/cplink_preflight.py --no-manual")
  print("- manual car checks from docs/personal/UPDATE_CHECKLIST.md before any road use")

  if report.failures:
    print("\n## Failures")
    for item in report.failures:
      print(f"- {item}")
  if report.warnings:
    print("\n## Warnings")
    for item in report.warnings:
      print(f"- {item}")
  if report.notes:
    print("\n## Notes")
    for item in report.notes:
      print(f"- {item}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit personal CarrotPilot upstream update state.")
  parser.add_argument("--fetch", action="store_true", help="fetch configured remotes before auditing")
  parser.add_argument("--strict", action="store_true", help="return non-zero when warnings are present")
  parser.add_argument("--max-commits", type=int, default=8, help="number of new commit titles to print")
  parser.add_argument("--max-files", type=int, default=20, help="number of high-risk changed files to print")
  args = parser.parse_args()

  report = Audit()

  print("Personal upstream update audit")
  print(f"repo: {ROOT}")

  if args.fetch:
    fetch_sources(SOURCES)

  branch = audit_worktree(report)
  print(f"current branch: {branch} @ {rev('HEAD')}")

  for source in SOURCES:
    audit_source(source, report, args.max_commits, args.max_files)

  print_next_steps(report)

  if report.failures:
    return 2
  if args.strict and report.warnings:
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
