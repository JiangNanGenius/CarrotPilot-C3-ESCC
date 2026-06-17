#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


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
  Source("ajouatom CarrotPilot / CarPad C3 base", "origin", "origin/c3-wip", "upstream/c3-wip", "current C3 main source"),
  Source("C4 side line", "origin", "origin/carrot-wip", "tracking/c4", "low-priority side line"),
  Source("jixie atune", "jixie", "jixie/atune", "tracking/jixie-atune", "Auto-Tuner and web features"),
  Source("jixie CP app", "jixie", "jixie/master", "tracking/jixie-master", "CP搭子 / Navipilot app reference"),
  Source("jixie Navipilot Android app", "jixie-navipilot", "jixie-navipilot/CPdazi", "tracking/jixie-navipilot", "Android CP搭子 app, driving report, model switcher, and overtake UI"),
  Source("ajouatom model selector reference", "origin", "origin/happymaj11r/carrot-wip-model_selector", "tracking/model-selector", "model selector reference line; source-tracked only, not default C3 integration"),
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


def load_baselines(path: str) -> Dict[str, str]:
  baseline_path = Path(path)
  if not baseline_path.is_absolute():
    baseline_path = ROOT / baseline_path
  data = json.loads(baseline_path.read_text(encoding="utf-8"))
  baselines = data.get("baselines", {})
  if not isinstance(baselines, dict):
    raise RuntimeError("baseline file must contain a baselines object")
  return {str(ref): str(commit) for ref, commit in baselines.items()}


def resolve_ref(ref: str, baselines: Dict[str, str]) -> str:
  return baselines.get(ref, ref)


def ref_exists(ref: str, baselines: Dict[str, str]) -> bool:
  code, _ = git(["rev-parse", "--verify", "--quiet", resolve_ref(ref, baselines)])
  return code == 0


def rev(ref: str, baselines: Dict[str, str]) -> str:
  target = resolve_ref(ref, baselines)
  code, output = git(["rev-parse", "--short=10", target])
  if code != 0 and ref in baselines:
    return baselines[ref][:10] + " (not fetched)"
  return output if code == 0 else "missing"


def is_ancestor(base: str, tip: str, baselines: Dict[str, str]) -> bool:
  code, _ = git(["merge-base", "--is-ancestor", resolve_ref(base, baselines), resolve_ref(tip, baselines)])
  return code == 0


def ahead_count(base: str, tip: str, baselines: Dict[str, str]) -> int:
  code, output = git(["rev-list", "--count", f"{resolve_ref(base, baselines)}..{resolve_ref(tip, baselines)}"])
  if code != 0:
    return -1
  try:
    return int(output)
  except ValueError:
    return -1


def commit_titles(base: str, tip: str, baselines: Dict[str, str], limit: int) -> List[str]:
  code, output = git(["log", "--oneline", f"--max-count={limit}", f"{resolve_ref(base, baselines)}..{resolve_ref(tip, baselines)}"])
  if code != 0 or not output:
    return []
  return output.splitlines()


def changed_files(base: str, tip: str, baselines: Dict[str, str]) -> List[str]:
  code, output = git(["diff", "--name-only", f"{resolve_ref(base, baselines)}..{resolve_ref(tip, baselines)}"])
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


def audit_worktree(report: Audit, baselines: Dict[str, str]) -> str:
  _, branch = git(["branch", "--show-current"])
  code, status = git(["status", "--short"])
  if code != 0:
    report.fail("cannot read git status")
  elif status:
    report.warn("worktree has uncommitted changes")

  if ref_exists("origin/c3-wip", baselines) and not is_ancestor("origin/c3-wip", "HEAD", baselines):
    report.fail("HEAD does not contain latest fetched origin/c3-wip")
  if ref_exists("personal/c3-escc", baselines) and not is_ancestor("personal/c3-escc", "HEAD", baselines):
    report.fail("current branch does not contain personal/c3-escc protection line")

  return branch or "(detached)"


def audit_source(source: Source, report: Audit, baselines: Dict[str, str], max_commits: int, max_files: int) -> None:
  print(f"\n## {source.name}")
  print(f"purpose: {source.purpose}")
  local_label = "baseline" if source.local_ref in baselines else "local"
  print(f"{local_label:<6}: {source.local_ref} @ {rev(source.local_ref, baselines)}")
  print(f"remote: {source.remote_ref} @ {rev(source.remote_ref, baselines)}")

  missing = [ref for ref in (source.local_ref, source.remote_ref) if not ref_exists(ref, baselines)]
  if missing:
    report.warn(f"{source.name}: missing ref(s): {', '.join(missing)}")
    return

  if is_ancestor(source.remote_ref, source.local_ref, baselines) and is_ancestor(source.local_ref, source.remote_ref, baselines):
    print("status: aligned")
    return

  local_ahead = ahead_count(source.remote_ref, source.local_ref, baselines)
  remote_ahead = ahead_count(source.local_ref, source.remote_ref, baselines)
  print(f"status: local ahead {local_ahead}, remote ahead {remote_ahead}")

  if remote_ahead > 0:
    report.warn(f"{source.name}: remote has {remote_ahead} new commit(s) since local tracking ref")
    print_list("new commits", commit_titles(source.local_ref, source.remote_ref, baselines, max_commits), max_commits)
    files = changed_files(source.local_ref, source.remote_ref, baselines)
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
  parser.add_argument("--baseline-file", help="JSON file with baseline commits for CI or public-repo audits")
  parser.add_argument("--strict", action="store_true", help="return non-zero when warnings are present")
  parser.add_argument("--max-commits", type=int, default=8, help="number of new commit titles to print")
  parser.add_argument("--max-files", type=int, default=20, help="number of high-risk changed files to print")
  args = parser.parse_args()

  report = Audit()
  baselines = load_baselines(args.baseline_file) if args.baseline_file else {}

  print("Personal upstream update audit")
  print(f"repo: {ROOT}")

  if args.fetch:
    fetch_sources(SOURCES)

  branch = audit_worktree(report, baselines)
  print(f"current branch: {branch} @ {rev('HEAD', baselines)}")
  if baselines:
    print(f"baseline file: {args.baseline_file}")

  for source in SOURCES:
    audit_source(source, report, baselines, args.max_commits, args.max_files)

  print_next_steps(report)

  if report.failures:
    return 2
  if args.strict and report.warnings:
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
