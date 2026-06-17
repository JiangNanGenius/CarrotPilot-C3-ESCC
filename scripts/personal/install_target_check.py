#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/personal/INSTALL_TARGETS.json"
TAG_RE = re.compile(r"^carrotpilot-c3-escc-(\d{8})-(static|test|stable)(\d*)$")
STABLE_EVIDENCE_LINES = [
  "Seltos real-car test: PASS",
  "AlwaysOffline ACC power-cycle test: PASS",
  "ESCC 0x2AB observed: PASS",
  "Low-speed road test: PASS",
  "Rollback target recorded: PASS",
]


class InstallTargetError(Exception):
  pass


def git(args: Sequence[str]) -> Tuple[int, str]:
  proc = subprocess.run(
    ["git", *args],
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  return proc.returncode, proc.stdout.strip()


def load_manifest() -> Dict[str, Any]:
  try:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
  except Exception as exc:
    raise InstallTargetError(f"cannot read {MANIFEST.relative_to(ROOT)}: {exc}") from exc
  if not isinstance(data, dict):
    raise InstallTargetError("install target manifest must be a JSON object")
  return data


def require_key(data: Dict[str, Any], key: str) -> Any:
  if key not in data:
    raise InstallTargetError(f"missing manifest key: {key}")
  return data[key]


def validate_tag_value(value: Optional[str], expected_kind: str, key: str) -> Optional[str]:
  if value is None:
    return None
  if not isinstance(value, str) or not value:
    raise InstallTargetError(f"{key} must be null or a non-empty string")
  match = TAG_RE.match(value)
  if not match:
    raise InstallTargetError(f"{key} is not a personal release tag: {value}")
  if match.group(2) != expected_kind:
    raise InstallTargetError(f"{key} must be a {expected_kind} tag, got {value}")
  return value


def require_commit_ref(ref: str, label: str) -> str:
  code, output = git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
  if code != 0 or not output:
    raise InstallTargetError(f"{label} does not resolve to a commit: {ref}")
  return output


def require_tag_exists(tag: Optional[str], key: str) -> Optional[str]:
  if tag is None:
    return None
  try:
    return require_commit_ref(f"refs/tags/{tag}", key)
  except InstallTargetError:
    pending_tag = os.environ.get("CARROTPILOT_PENDING_RELEASE_TAG")
    if key in {"current_static_tag", "current_test_tag"} and pending_tag == tag:
      return require_commit_ref("HEAD", key)
    raise


def require_ancestor(base: str, tip: str, label: str) -> None:
  code, _ = git(["merge-base", "--is-ancestor", base, tip])
  if code != 0:
    raise InstallTargetError(f"{label}: {base} is not in {tip}'s history")


def validate_stable_log(path_value: Optional[str]) -> None:
  if path_value is None:
    raise InstallTargetError("current_stable_tag requires stable_road_test_log")
  if not isinstance(path_value, str) or not path_value:
    raise InstallTargetError("stable_road_test_log must be a non-empty string")
  path = ROOT / path_value
  if not path.exists():
    raise InstallTargetError(f"stable road-test log is missing: {path_value}")
  text = path.read_text(encoding="utf-8")
  missing = [line for line in STABLE_EVIDENCE_LINES if line not in text]
  if missing:
    raise InstallTargetError("stable road-test log is missing required PASS lines:\n" + "\n".join(missing))


def validate_policy(data: Dict[str, Any]) -> None:
  project = require_key(data, "project")
  if project != "CarrotPilot-C3-ESCC":
    raise InstallTargetError(f"unexpected project name: {project}")

  policy_version = require_key(data, "policy_version")
  if policy_version != 1:
    raise InstallTargetError(f"unsupported install target policy version: {policy_version}")

  daily_target = require_key(data, "daily_install_target")
  static_tag = validate_tag_value(require_key(data, "current_static_tag"), "static", "current_static_tag")
  test_tag = validate_tag_value(require_key(data, "current_test_tag"), "test", "current_test_tag")
  stable_tag = validate_tag_value(require_key(data, "current_stable_tag"), "stable", "current_stable_tag")
  previous_stable_tag = validate_tag_value(require_key(data, "previous_stable_tag"), "stable", "previous_stable_tag")
  rollback_base_ref = require_key(data, "rollback_base_ref")
  stable_log = require_key(data, "stable_road_test_log")

  if not isinstance(rollback_base_ref, str) or not rollback_base_ref:
    raise InstallTargetError("rollback_base_ref must be a non-empty string")
  if static_tag is None and test_tag is None and stable_tag is None:
    raise InstallTargetError("at least one static, test, or stable tag must be recorded")

  tag_commits = {
    "current_static_tag": require_tag_exists(static_tag, "current_static_tag"),
    "current_test_tag": require_tag_exists(test_tag, "current_test_tag"),
    "current_stable_tag": require_tag_exists(stable_tag, "current_stable_tag"),
    "previous_stable_tag": require_tag_exists(previous_stable_tag, "previous_stable_tag"),
  }
  require_commit_ref(rollback_base_ref, "rollback_base_ref")

  if daily_target is None:
    if stable_tag is not None:
      raise InstallTargetError("daily_install_target should point to current_stable_tag when a stable tag exists")
  else:
    if daily_target != stable_tag:
      raise InstallTargetError("daily_install_target must be null or exactly current_stable_tag")

  if stable_tag is None:
    if daily_target is not None:
      raise InstallTargetError("daily_install_target must stay null until current_stable_tag is set")
    if previous_stable_tag is not None:
      raise InstallTargetError("previous_stable_tag should stay null until the first stable release")
    if stable_log is not None:
      raise InstallTargetError("stable_road_test_log should stay null until current_stable_tag is set")
  else:
    validate_stable_log(stable_log)
    if previous_stable_tag == stable_tag:
      raise InstallTargetError("previous_stable_tag must not equal current_stable_tag")

  head = require_commit_ref("HEAD", "HEAD")
  for key, commit in tag_commits.items():
    if commit is not None:
      require_ancestor(commit, head, key)


def main() -> int:
  try:
    data = load_manifest()
    validate_policy(data)
    print("Install target check")
    print(f"repo: {ROOT}")
    print(f"manifest: {MANIFEST.relative_to(ROOT)}")
    print(f"static tag: {data.get('current_static_tag')}")
    print(f"test tag: {data.get('current_test_tag') or 'none'}")
    print(f"stable tag: {data.get('current_stable_tag') or 'none'}")
    print(f"daily install target: {data.get('daily_install_target') or 'none'}")
    print("OK: install targets are internally consistent")
    return 0
  except InstallTargetError as exc:
    print("install target check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
