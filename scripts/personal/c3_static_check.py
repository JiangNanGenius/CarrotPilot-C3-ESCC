#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
INSTALL_TARGETS = ROOT / "docs/personal/INSTALL_TARGETS.json"
DEFAULT_OUTPUT = Path("/data/media/0/carrotpilot-c3-escc-static-check.md")

PARAM_ROOTS = [
  Path("/data/params/d"),
  Path("/data/params"),
  Path("/persist/comma/params/d"),
]

EXPECTED_PARKED_PARAMS = {
  "AlwaysOffroad": "0",
  "EnableConnect": "0",
  "EnableEscc": "0",
  "HyundaiCameraSCC": "0",
  "CanfdHDA2": "0",
  "EnableRadarTracks": "0",
  "EnableAmapNaviStatus": "0",
}


class CheckResult:
  def __init__(self, name: str, ok: bool, detail: str):
    self.name = name
    self.ok = ok
    self.detail = detail


def run(cmd: Sequence[str]) -> Tuple[int, str]:
  proc = subprocess.run(
    list(cmd),
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  return proc.returncode, proc.stdout.strip()


def git(args: Sequence[str]) -> Tuple[int, str]:
  return run(["git", *args])


def read_install_targets() -> Dict[str, object]:
  return json.loads(INSTALL_TARGETS.read_text(encoding="utf-8"))


def read_param_file(key: str) -> Optional[str]:
  for root in PARAM_ROOTS:
    path = root / key
    if path.exists() and path.is_file():
      data = path.read_bytes()
      try:
        return data.decode("utf-8", errors="strict").replace("\x00", "").strip()
      except UnicodeDecodeError:
        return "<binary>"
  return None


def boolish(value: Optional[str]) -> Optional[str]:
  if value is None:
    return None
  value = value.strip()
  if value in {"1", "true", "True", "TRUE", "on", "ON", "yes", "YES"}:
    return "1"
  if value in {"0", "false", "False", "FALSE", "off", "OFF", "no", "NO"}:
    return "0"
  return value


def check_target_tag(target_tag: str, allow_branch: bool) -> CheckResult:
  code, head = git(["rev-parse", "HEAD"])
  if code != 0:
    return CheckResult("git head", False, head)
  code, tag_commit = git(["rev-list", "-n", "1", target_tag])
  if code != 0:
    pending_tag = os.environ.get("CARROTPILOT_PENDING_RELEASE_TAG")
    if allow_branch and pending_tag == target_tag:
      return CheckResult("target tag", True, f"{target_tag} is pending at current HEAD")
    if allow_branch:
      return CheckResult("target tag", True, f"{target_tag} is missing, but --allow-branch was used")
    return CheckResult("target tag exists", False, tag_commit)
  code, tags = git(["tag", "--points-at", "HEAD"])
  if code != 0:
    tags = ""
  if head == tag_commit:
    return CheckResult("target tag", True, f"HEAD matches {target_tag}; tags at HEAD: {tags or '<none>'}")
  if allow_branch:
    return CheckResult("target tag", True, f"HEAD does not match {target_tag}, but --allow-branch was used")
  return CheckResult("target tag", False, f"HEAD {head[:12]} does not match {target_tag} {tag_commit[:12]}")


def check_manifest_target(target_tag: str) -> CheckResult:
  try:
    data = read_install_targets()
  except Exception as exc:
    return CheckResult("install target manifest", False, str(exc))
  current_static = data.get("current_static_tag")
  daily_target = data.get("daily_install_target")
  if current_static != target_tag:
    return CheckResult("install target manifest", False, f"current_static_tag={current_static!r}, expected {target_tag!r}")
  if daily_target is not None:
    return CheckResult("install target manifest", False, f"daily_install_target must stay null before stable, got {daily_target!r}")
  return CheckResult("install target manifest", True, f"current_static_tag={current_static}; daily_install_target=null")


def check_params() -> List[CheckResult]:
  results: List[CheckResult] = []
  for key, expected in EXPECTED_PARKED_PARAMS.items():
    raw = read_param_file(key)
    actual = boolish(raw)
    if actual is None:
      results.append(CheckResult(f"param {key}", True, f"missing on disk; code default should apply, expected {expected}"))
    elif actual == expected:
      results.append(CheckResult(f"param {key}", True, f"{actual}"))
    else:
      results.append(CheckResult(f"param {key}", False, f"got {raw!r}, expected {expected!r}"))
  return results


def run_preflight(label: str, cmd: Sequence[str], skip: bool) -> CheckResult:
  if skip:
    return CheckResult(label, True, "skipped")
  code, output = run(cmd)
  if code == 0:
    return CheckResult(label, True, "passed")
  return CheckResult(label, False, output[-2000:])


def write_snapshot(path: Path, sample_seconds: int) -> CheckResult:
  cmd = [
    sys.executable,
    "scripts/personal/device_snapshot.py",
    "--output",
    str(path),
  ]
  if sample_seconds > 0:
    cmd.extend(["--sample-seconds", str(sample_seconds)])
  code, output = run(cmd)
  if code == 0:
    return CheckResult("device snapshot", True, f"{path}")
  return CheckResult("device snapshot", False, output[-2000:])


def markdown_report(results: Sequence[CheckResult], target_tag: str, snapshot_path: Path) -> str:
  lines: List[str] = []
  lines.append("# CarrotPilot-C3-ESCC Static Check")
  lines.append("")
  lines.append(f"- Target tag: `{target_tag}`")
  lines.append(f"- Snapshot: `{snapshot_path}`")
  lines.append("")
  lines.append("## Results")
  lines.append("")
  lines.append("| Check | Result | Detail |")
  lines.append("| --- | --- | --- |")
  for result in results:
    state = "PASS" if result.ok else "FAIL"
    detail = result.detail.replace("\n", "<br>")
    lines.append(f"| {result.name} | {state} | {detail} |")
  lines.append("")
  lines.append("## Next")
  lines.append("")
  lines.append("- If any check failed, do not drive with this build yet.")
  lines.append("- Keep `EnableEscc=0` until parked static checks pass.")
  lines.append("- After a successful ACC/CAN power-cycle boot, run `record_power_cycle_boot.py` and collect a new snapshot.")
  lines.append("- After enabling ESCC while parked, rerun with `--sample-seconds 20` to capture 0x2AB evidence.")
  lines.append("- Use the generated device snapshot together with `ROAD_TEST_LOG_TEMPLATE.md` before any stable tag.")
  lines.append("")
  return "\n".join(lines)


def main() -> int:
  parser = argparse.ArgumentParser(description="Run a privacy-safe static check on a C3 after installing the personal static tag.")
  parser.add_argument("--target-tag", help="expected tag; defaults to current_static_tag in INSTALL_TARGETS.json")
  parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="write this check report to a markdown file")
  parser.add_argument("--snapshot-output", default="/data/media/0/carrotpilot-c3-escc-snapshot.md", help="write device snapshot here")
  parser.add_argument("--sample-seconds", type=int, default=0, help="sample live messaging for the device snapshot")
  parser.add_argument("--allow-branch", action="store_true", help="allow running from a branch instead of the target tag")
  parser.add_argument("--skip-preflight", action="store_true", help="skip repository static preflight scripts")
  args = parser.parse_args()

  try:
    target_tag = args.target_tag
    if not target_tag:
      data = read_install_targets()
      target_tag = str(data.get("current_static_tag") or "")
    if not target_tag:
      raise RuntimeError("target tag is empty")

    snapshot_path = Path(args.snapshot_output)
    results: List[CheckResult] = [
      check_manifest_target(target_tag),
      check_target_tag(target_tag, args.allow_branch),
      run_preflight("install target check", [sys.executable, "scripts/personal/install_target_check.py"], args.skip_preflight),
      run_preflight("Seltos profile check", [sys.executable, "scripts/personal/seltos_profile_check.py"], args.skip_preflight),
      run_preflight("ESCC/AlwaysOffroad preflight", [sys.executable, "scripts/personal/escc_offroad_preflight.py", "--no-manual"], args.skip_preflight),
      run_preflight("CPlink preflight", [sys.executable, "scripts/personal/cplink_preflight.py", "--no-manual"], args.skip_preflight),
    ]
    results.extend(check_params())
    results.append(write_snapshot(snapshot_path, max(args.sample_seconds, 0)))

    report = markdown_report(results, target_tag, snapshot_path)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"wrote {output_path}")
    for result in results:
      state = "PASS" if result.ok else "FAIL"
      print(f"[{state}] {result.name}: {result.detail}")
    return 0 if all(result.ok for result in results) else 2
  except Exception as exc:
    print("C3 static check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
