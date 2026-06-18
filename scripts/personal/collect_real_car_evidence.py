#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
INSTALL_TARGETS = ROOT / "docs/personal/INSTALL_TARGETS.json"
ROAD_TEST_TEMPLATE = ROOT / "docs/personal/ROAD_TEST_LOG_TEMPLATE.md"


def run(cmd: Sequence[str]) -> Tuple[int, str]:
  proc = subprocess.run(
    list(cmd),
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  return proc.returncode, proc.stdout.strip()


def git_value(args: Sequence[str]) -> str:
  code, output = run(["git", *args])
  return output if code == 0 and output else "unknown"


def read_install_targets() -> Dict[str, object]:
  try:
    return json.loads(INSTALL_TARGETS.read_text(encoding="utf-8"))
  except Exception:
    return {}


def default_output_dir() -> Path:
  stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
  device_media = Path("/data/media/0")
  base = device_media if device_media.exists() else Path("/tmp")
  return base / f"carrotpilot-c3-escc-evidence-{stamp}"


def clean_output_dir(path: Path, force: bool) -> None:
  if path.exists():
    if force:
      shutil.rmtree(path)
    elif any(path.iterdir()):
      raise RuntimeError(f"output directory already exists and is not empty: {path}")
  path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8")


def markdown_list(items: Sequence[str]) -> str:
  return "\n".join(f"- {item}" for item in items)


def build_road_test_draft(snapshot_name: str) -> str:
  template = ROAD_TEST_TEMPLATE.read_text(encoding="utf-8")
  today = dt.date.today().isoformat()
  tags = git_value(["tag", "--points-at", "HEAD"]).replace("\n", ", ")
  targets = read_install_targets()
  rollback = str(targets.get("rollback_base_ref") or "origin/c3-wip")
  replacements = {
    "- 日期：": f"- 日期：{today}",
    "- 分支：": f"- 分支：{git_value(['branch', '--show-current'])}",
    "- commit：": f"- commit：{git_value(['rev-parse', '--short=12', 'HEAD'])}",
    "- tag：": f"- tag：{tags or str(targets.get('current_static_tag') or 'unknown')}",
    "- 设备快照文件：": f"- 设备快照文件：{snapshot_name}",
    "- 回滚目标：": f"- 回滚目标：{rollback}",
  }
  for old, new in replacements.items():
    template = template.replace(old, new, 1)
  return template


def build_checklist(output_dir: Path, sample_seconds: int, archive_path: Optional[Path], navipilot_check: bool) -> str:
  files = [
    "`static-check.md`: C3 parked static check report",
    "`device-snapshot.md`: privacy-safe device snapshot",
    "`road-test-log-draft.md`: road-test log draft to fill after driving",
    "`manifest.json`: command, commit, tag, and file summary",
    "`static-check-output.txt`: raw output from the static check command",
  ]
  if navipilot_check:
    files.extend([
      "`navipilot-live-check.md`: C3-side 7000/7705/7706 endpoint check for the Navipilot APP",
      "`navipilot-live-check.json`: machine-readable Navipilot endpoint check result",
    ])
  if archive_path is not None:
    files.append(f"`{archive_path.name}`: optional tar.gz copy of this evidence folder")

  lines: List[str] = []
  lines.append("# CarrotPilot-C3-ESCC Evidence Bundle")
  lines.append("")
  lines.append("This folder is designed for real-car validation on a C3 before any stable tag.")
  lines.append("It avoids VIN, dongle id, tokens, full params, and route identifiers.")
  lines.append("")
  lines.append("## Files")
  lines.append("")
  lines.append(markdown_list(files))
  lines.append("")
  lines.append("## Use")
  lines.append("")
  lines.append("- Keep `EnableEscc=0` for the first static and low-risk checks.")
  lines.append("- Only enable `EnableEscc=1` while parked and ready to observe ESCC 0x2AB.")
  lines.append("- After a successful ACC/CAN power-cycle boot, run `record_power_cycle_boot.py` and collect a new evidence bundle.")
  lines.append("- For a stable tag, rerun collection with `--sample-seconds 20` after ESCC is enabled and visible.")
  lines.append("- For read-only AmapNavi status bridge validation, enable `EnableAmapNaviStatus=1` while parked and collect with `--sample-seconds 20`.")
  lines.append("- Fill `road-test-log-draft.md` only after the matching test has really passed.")
  lines.append("- Do not publicly share manually added VIN, dongle id, tokens, WiFi secrets, or route data.")
  lines.append("")
  lines.append("## Current Run")
  lines.append("")
  lines.append(f"- Evidence folder: `{output_dir}`")
  lines.append(f"- Messaging sample seconds: `{sample_seconds}`")
  if archive_path is not None:
    lines.append(f"- Archive: `{archive_path}`")
  lines.append("")
  lines.append("## Evidence Readiness")
  lines.append("")
  lines.append("After copying this folder to the computer, first run the staged readiness report:")
  lines.append("")
  lines.append("```bash")
  lines.append("python3 scripts/personal/evidence_readiness_report.py \\")
  lines.append("  --evidence-dir /path/to/this-evidence-folder")
  lines.append("```")
  lines.append("")
  lines.append("It shows which stages are ready and which stable requirements are still missing.")
  lines.append("")
  lines.append("## Stable Evidence Check")
  lines.append("")
  lines.append("After filling the road-test log and clearing the readiness report, run the strict stable gate:")
  lines.append("")
  lines.append("```bash")
  lines.append("python3 scripts/personal/road_test_evidence_check.py \\")
  lines.append("  --evidence-dir /path/to/this-evidence-folder \\")
  lines.append("  --require-device-snapshot \\")
  lines.append("  --require-carparams-summary \\")
  lines.append("  --require-offline-process-guard \\")
  lines.append("  --require-power-cycle-boot \\")
  lines.append("  --require-escc-sample")
  lines.append("```")
  lines.append("")
  lines.append("For CP搭子 / Navipilot validation, add `--require-cplink-sample` to the same command.")
  lines.append("For read-only AmapNavi status bridge validation, add `--require-amap-navi-sample`.")
  if navipilot_check:
    lines.append("")
    lines.append("For C3-side Navipilot APP endpoint validation, also add `--require-navipilot-live-check`.")
  lines.append("")
  return "\n".join(lines)


def make_archive(output_dir: Path) -> Path:
  archive_path = output_dir.with_suffix(".tar.gz")
  if archive_path.exists():
    archive_path.unlink()
  with tarfile.open(archive_path, "w:gz") as tar:
    tar.add(output_dir, arcname=output_dir.name)
  return archive_path


def build_static_command(args: argparse.Namespace, output_dir: Path) -> List[str]:
  cmd = [
    sys.executable,
    "scripts/personal/c3_static_check.py",
    "--output",
    str(output_dir / "static-check.md"),
    "--snapshot-output",
    str(output_dir / "device-snapshot.md"),
    "--sample-seconds",
    str(max(args.sample_seconds, 0)),
  ]
  if args.target_tag:
    cmd.extend(["--target-tag", args.target_tag])
  if args.allow_branch:
    cmd.append("--allow-branch")
  if args.skip_preflight:
    cmd.append("--skip-preflight")
  return cmd


def build_navipilot_command(args: argparse.Namespace, output_dir: Path) -> Optional[List[str]]:
  if not args.navipilot_check:
    return None
  cmd = [
    sys.executable,
    "scripts/personal/navipilot_live_check.py",
    "--host",
    args.navipilot_host,
    "--listen-seconds",
    str(max(args.navipilot_listen_seconds, 0)),
    "--output",
    str(output_dir / "navipilot-live-check.md"),
    "--json-output",
    str(output_dir / "navipilot-live-check.json"),
  ]
  if args.navipilot_param_write_probe:
    cmd.append("--param-write-probe")
  if args.navipilot_send_test_nav:
    cmd.append("--send-test-nav")
  return cmd


def build_manifest(
  output_dir: Path,
  static_cmd: Sequence[str],
  static_code: int,
  archive_path: Optional[Path],
  navipilot_cmd: Optional[Sequence[str]],
  navipilot_code: Optional[int],
) -> Dict[str, object]:
  targets = read_install_targets()
  files = sorted(p.name for p in output_dir.iterdir() if p.is_file())
  if archive_path is not None:
    files.append(archive_path.name)
  return {
    "version": 1,
    "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "repo": str(ROOT),
    "branch": git_value(["branch", "--show-current"]),
    "commit": git_value(["rev-parse", "--short=12", "HEAD"]),
    "tags": git_value(["tag", "--points-at", "HEAD"]),
    "git_status": git_value(["status", "--short"]),
    "current_static_tag": targets.get("current_static_tag"),
    "daily_install_target": targets.get("daily_install_target"),
    "rollback_base_ref": targets.get("rollback_base_ref"),
    "static_check_command": list(static_cmd),
    "static_check_exit_code": static_code,
    "navipilot_live_check_command": list(navipilot_cmd) if navipilot_cmd is not None else None,
    "navipilot_live_check_exit_code": navipilot_code,
    "files": files,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Collect a privacy-safe C3 real-car validation evidence folder.")
  parser.add_argument("--output-dir", help="folder to write; defaults to /data/media/0 on C3 or /tmp elsewhere")
  parser.add_argument("--sample-seconds", type=int, default=0, help="sample live CAN/CarrotMan messaging in the device snapshot")
  parser.add_argument("--target-tag", help="expected static/test tag for c3_static_check.py")
  parser.add_argument("--allow-branch", action="store_true", help="allow running from a branch instead of the target tag")
  parser.add_argument("--skip-preflight", action="store_true", help="skip repository preflight checks inside c3_static_check.py")
  parser.add_argument("--navipilot-check", action="store_true", help="also run C3-side Navipilot APP endpoint check and store its report")
  parser.add_argument("--navipilot-host", default="127.0.0.1", help="host for navipilot_live_check.py; use 127.0.0.1 on the C3")
  parser.add_argument("--navipilot-listen-seconds", type=float, default=3.0, help="seconds to listen for UDP 7705 during --navipilot-check")
  parser.add_argument("--navipilot-param-write-probe", action="store_true", help="probe /api/param_set by writing ExperimentalMode back to its current value")
  parser.add_argument("--navipilot-send-test-nav", action="store_true", help="send parked test navigation packets to UDP 7706 during --navipilot-check")
  parser.add_argument("--archive", action="store_true", help="also create a tar.gz archive beside the evidence folder")
  parser.add_argument("--force", action="store_true", help="replace output directory when it already exists")
  args = parser.parse_args()

  output_dir = Path(args.output_dir).expanduser() if args.output_dir else default_output_dir()
  if not output_dir.is_absolute():
    output_dir = ROOT / output_dir

  try:
    clean_output_dir(output_dir, args.force)

    static_cmd = build_static_command(args, output_dir)
    static_code, static_output = run(static_cmd)
    write_text(output_dir / "static-check-output.txt", static_output + "\n")

    navipilot_cmd = build_navipilot_command(args, output_dir)
    navipilot_code: Optional[int] = None
    if navipilot_cmd is not None:
      navipilot_code, navipilot_output = run(navipilot_cmd)
      write_text(output_dir / "navipilot-live-check-output.txt", navipilot_output + "\n")

    write_text(output_dir / "road-test-log-draft.md", build_road_test_draft("device-snapshot.md"))

    archive_path: Optional[Path] = None
    write_text(output_dir / "README.md", build_checklist(output_dir, max(args.sample_seconds, 0), archive_path, bool(navipilot_cmd)))
    manifest = build_manifest(output_dir, static_cmd, static_code, archive_path, navipilot_cmd, navipilot_code)
    write_text(output_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    if args.archive:
      archive_path = make_archive(output_dir)
      write_text(output_dir / "README.md", build_checklist(output_dir, max(args.sample_seconds, 0), archive_path, bool(navipilot_cmd)))
      manifest = build_manifest(output_dir, static_cmd, static_code, archive_path, navipilot_cmd, navipilot_code)
      write_text(output_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(f"wrote evidence folder: {output_dir}")
    if archive_path is not None:
      print(f"wrote archive: {archive_path}")
    if static_code != 0:
      print("static check failed; inspect static-check.md and static-check-output.txt before driving")
      return static_code
    if navipilot_code not in (None, 0):
      print("Navipilot endpoint check failed; inspect navipilot-live-check.md/json before APP testing")
      return navipilot_code
    print("OK: evidence folder collected")
    return 0
  except Exception as exc:
    print("real-car evidence collection failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
