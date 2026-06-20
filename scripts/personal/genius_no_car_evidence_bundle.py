#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
TITLE = "Genius Pilot No-Car Evidence Bundle"
DEFAULT_OUTPUT_ROOT = Path.home() / "Desktop" / "CarrotPilot-C3-ESCC-device-evidence"
INSTALLER_URL = "https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x"
DISABLED_CLOUD_PROCESSES = (
  "manage_athenad",
  "uploader",
  "manage_sunnylinkd",
  "sunnylink_registration_manager",
  "statsd_sp",
  "backup_manager",
)


def py() -> str:
  return sys.executable


def replay_py() -> str:
  candidate = Path("/tmp/gp-replay-py312/bin/python")
  return str(candidate) if candidate.exists() else py()


def read(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def run(cmd: Sequence[str], timeout_s: int) -> dict[str, Any]:
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=ROOT,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      check=False,
      timeout=timeout_s,
    )
    return {
      "ok": proc.returncode == 0,
      "returnCode": proc.returncode,
      "command": list(cmd),
      "output": proc.stdout,
      "timeoutS": timeout_s,
    }
  except subprocess.TimeoutExpired as exc:
    output = ""
    if exc.stdout:
      output += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
    if exc.stderr:
      output += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
    return {
      "ok": False,
      "returnCode": None,
      "command": list(cmd),
      "output": f"timed out after {timeout_s}s\n{output}".strip(),
      "timeoutS": timeout_s,
    }


def git_text(*args: str) -> str:
  result = run(["git", *args], 30)
  return str(result["output"]).strip()


def parse_version() -> dict[str, Any]:
  version_h = read("sunnypilot/common/version.h")
  version = re.search(r'SUNNYPILOT_VERSION "([^"]+)"', version_h)
  base = re.search(r'SUNNYPILOT_BASE_VERSION "([^"]+)"', version_h)
  patch_date = re.search(r'GENIUS_PILOT_PATCH_DATE "([^"]+)"', version_h)
  patch_number = re.search(r"GENIUS_PILOT_PATCH_NUMBER (\d+)", version_h)
  return {
    "version": version.group(1) if version else "",
    "base": base.group(1) if base else "",
    "patchDate": patch_date.group(1) if patch_date else "",
    "patchNumber": int(patch_number.group(1)) if patch_number else None,
  }


def cloud_process_evidence() -> dict[str, Any]:
  process_config = read("system/manager/process_config.py")
  manager = read("system/manager/manager.py")
  params = read("common/params_keys.h")
  process_rows = {}
  for name in DISABLED_CLOUD_PROCESSES:
    registered = bool(re.search(rf'(PythonProcess|NativeProcess)\("{re.escape(name)}"', process_config))
    mentioned = name in process_config
    process_rows[name] = {
      "registeredProcess": registered,
      "mentionedInProcessConfig": mentioned,
      "ok": not registered,
    }
  sunnylink_default_off = re.search(r'\{"SunnylinkEnabled",\s*\{[^}]*BOOL,\s*"0"\}\}', params) is not None
  onroad_uploads_default_off = re.search(r'\{"OnroadUploads",\s*\{[^}]*BOOL,\s*"0"\}\}', params) is not None
  return {
    "ok": all(row["ok"] for row in process_rows.values())
    and sunnylink_default_off
    and onroad_uploads_default_off,
    "disabledCloudProcesses": process_rows,
    "managerIgnoresAthenadUploader": 'ignore += ["manage_athenad", "uploader"]' in manager,
    "sunnylinkDefaultOff": sunnylink_default_off,
    "onroadUploadsDefaultOff": onroad_uploads_default_off,
  }


def command_specs(full_gate: bool) -> list[tuple[str, list[str], int]]:
  release_gate = [py(), "scripts/personal/sunnypilot_c3_alpha_release_gate.py", "--json"]
  if full_gate:
    release_gate.insert(-1, "--full")
  return [
    ("release_gate", release_gate, 420 if full_gate else 180),
    ("installer_audit", [py(), "scripts/personal/sunnypilot_c3_installer_audit.py", "--json"], 60),
    ("c3_touch_contract", [py(), "scripts/personal/genius_c3_touch_contract.py", "--json"], 30),
    ("super_advanced_contract", [py(), "scripts/personal/genius_super_advanced_contract.py", "--json"], 30),
    ("model_manager_contract", [replay_py(), "scripts/personal/genius_model_manager_contract.py", "--json"], 60),
    ("offline_replay_check_self_test", [py(), "scripts/personal/genius_offline_replay_check.py", "--self-test"], 30),
    ("ui_replay_check", [py(), "scripts/personal/genius_ui_replay_check.py", "--json"], 30),
  ]


def safe_slug(value: str) -> str:
  return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "item"


def write_text(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8")


def build_bundle(output_root: Path, full_gate: bool) -> dict[str, Any]:
  version = parse_version()
  commit = git_text("rev-parse", "HEAD")
  short_commit = commit[:8]
  branch = git_text("rev-parse", "--abbrev-ref", "HEAD")
  timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  bundle_dir = output_root / f"no_car_{safe_slug(version['version'])}_{short_commit}_{timestamp}"
  commands_dir = bundle_dir / "commands"
  bundle_dir.mkdir(parents=True, exist_ok=False)
  commands_dir.mkdir(parents=True, exist_ok=True)

  command_results: dict[str, dict[str, Any]] = {}
  for name, cmd, timeout_s in command_specs(full_gate):
    result = run(cmd, timeout_s)
    command_results[name] = {k: v for k, v in result.items() if k != "output"}
    write_text(commands_dir / f"{safe_slug(name)}.txt", str(result["output"]))

  installer_output = (commands_dir / "installer_audit.txt").read_text(encoding="utf-8", errors="replace")
  installer_report: dict[str, Any] = {}
  try:
    installer_report = json.loads(installer_output)
  except json.JSONDecodeError:
    installer_report = {"ok": False, "parseError": "installer audit did not return JSON"}

  report = {
    "title": TITLE,
    "ok": all(result["ok"] for result in command_results.values()) and cloud_process_evidence()["ok"],
    "createdAtUtc": timestamp,
    "repo": str(ROOT),
    "branch": branch,
    "commit": commit,
    "version": version,
    "installer": {
      "url": INSTALLER_URL,
      "sha256": installer_report.get("sha256", ""),
      "size": installer_report.get("size", 0),
      "ok": installer_report.get("ok", False),
    },
    "remoteRefs": git_text("ls-remote", "origin", "experimental/sunnypilot-011-c3", "alpha-sunnypilot-c3"),
    "gitStatus": git_text("status", "--short", "--branch"),
    "cloudProcessEvidence": cloud_process_evidence(),
    "commands": command_results,
  }

  write_text(bundle_dir / "bundle.json", json.dumps(report, indent=2, sort_keys=True))
  summary = [
    f"# {TITLE}",
    "",
    f"- Version: `{version['version']}`",
    f"- Branch: `{branch}`",
    f"- Commit: `{commit}`",
    f"- Installer: `{INSTALLER_URL}`",
    f"- Installer SHA256: `{report['installer']['sha256']}`",
    f"- Cloud process evidence: `{'PASS' if report['cloudProcessEvidence']['ok'] else 'FAIL'}`",
    f"- Command evidence: `{'PASS' if all(item['ok'] for item in command_results.values()) else 'FAIL'}`",
    "",
    "## Commands",
    "",
  ]
  for name, result in command_results.items():
    summary.append(f"- `{name}`: `{'PASS' if result['ok'] else 'FAIL'}`")
  write_text(bundle_dir / "SUMMARY.md", "\n".join(summary) + "\n")

  archive_path = bundle_dir.parent / f"{bundle_dir.name}.tar.gz"
  with tarfile.open(archive_path, "w:gz") as archive:
    archive.add(bundle_dir, arcname=bundle_dir.name)
  report["bundleDir"] = str(bundle_dir)
  report["archive"] = str(archive_path)
  write_text(bundle_dir / "bundle.json", json.dumps(report, indent=2, sort_keys=True))
  return report


def self_test() -> int:
  version = parse_version()
  cloud = cloud_process_evidence()
  specs = command_specs(full_gate=False)
  ok = (
    bool(version["version"])
    and cloud["ok"]
    and any(name == "release_gate" for name, _, _ in specs)
    and any(name == "installer_audit" for name, _, _ in specs)
    and any(name == "c3_touch_contract" for name, _, _ in specs)
  )
  if not ok:
    print(json.dumps({"version": version, "cloud": cloud, "specs": [name for name, _, _ in specs]}, indent=2, sort_keys=True))
    return 1
  print(f"PASS {TITLE} self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description=TITLE)
  parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
  parser.add_argument("--full-gate", action="store_true", help="run the full release gate inside the bundle")
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report = build_bundle(args.output_root, args.full_gate)
  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    print(f"{'PASS' if report['ok'] else 'FAIL'} {TITLE}")
    print(f"bundle={report['bundleDir']}")
    print(f"archive={report['archive']}")
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
