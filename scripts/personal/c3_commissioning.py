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


def default_output_dir() -> Path:
  stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
  media = Path("/data/media/0")
  base = media if media.exists() else Path("/tmp")
  return base / f"carrotpilot-c3-escc-commissioning-{stamp}"


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


def build_migration_command(args: argparse.Namespace) -> Optional[List[str]]:
  if not args.migration_input:
    return None
  cmd = [
    sys.executable,
    "scripts/personal/params_migration.py",
    "import",
    "--input",
    args.migration_input,
  ]
  if args.apply_migration:
    cmd.append("--apply")
  return cmd


def build_evidence_command(args: argparse.Namespace, evidence_dir: Path) -> List[str]:
  cmd = [
    sys.executable,
    "scripts/personal/collect_real_car_evidence.py",
    "--output-dir",
    str(evidence_dir),
    "--sample-seconds",
    str(max(args.sample_seconds, 0)),
    "--force",
  ]
  if args.target_tag:
    cmd.extend(["--target-tag", args.target_tag])
  if args.allow_branch:
    cmd.append("--allow-branch")
  if args.skip_preflight:
    cmd.append("--skip-preflight")
  return cmd


def build_readiness_command(evidence_dir: Path) -> List[str]:
  return [
    sys.executable,
    "scripts/personal/evidence_readiness_report.py",
    "--evidence-dir",
    str(evidence_dir),
  ]


def make_archive(output_dir: Path) -> Path:
  archive_path = output_dir.with_suffix(".tar.gz")
  if archive_path.exists():
    archive_path.unlink()
  with tarfile.open(archive_path, "w:gz") as tar:
    tar.add(output_dir, arcname=output_dir.name)
  return archive_path


def markdown_status(label: str, code: Optional[int]) -> str:
  if code is None:
    return "SKIPPED"
  return "PASS" if code == 0 else "FAIL"


def build_readme(manifest: Dict[str, object]) -> str:
  migration_mode = manifest.get("migration_mode") or "skipped"
  archive = manifest.get("archive") or "<none>"
  lines: List[str] = []
  lines.append("# CarrotPilot-C3-ESCC C3 Commissioning")
  lines.append("")
  lines.append("This folder records the first safe setup pass after installing the personal C3 build.")
  lines.append("It is designed for parked checks, migration review, and evidence collection before any stable tag.")
  lines.append("")
  lines.append("## Summary")
  lines.append("")
  lines.append("| Step | Result |")
  lines.append("| --- | --- |")
  lines.append(f"| Params migration | {markdown_status('migration', manifest.get('migration_exit_code'))} |")
  lines.append(f"| Evidence collection | {markdown_status('evidence', manifest.get('evidence_exit_code'))} |")
  lines.append(f"| Evidence readiness report | {markdown_status('readiness', manifest.get('readiness_exit_code'))} |")
  lines.append("")
  lines.append("## Files")
  lines.append("")
  lines.append("- `manifest.json`: machine-readable summary of this run.")
  lines.append("- `migration-import-output.txt`: safe params import dry-run or apply output.")
  lines.append("- `evidence-readiness.txt`: staged readiness summary for stable release evidence.")
  lines.append("- `evidence/`: static check, device snapshot, road-test draft, and raw evidence bundle files.")
  lines.append("")
  lines.append("## Current Run")
  lines.append("")
  lines.append(f"- Migration mode: `{migration_mode}`")
  lines.append(f"- Migration input: `{manifest.get('migration_input') or '<none>'}`")
  lines.append(f"- Evidence folder: `{manifest.get('evidence_dir')}`")
  lines.append(f"- Archive: `{archive}`")
  lines.append("")
  lines.append("## Next")
  lines.append("")
  lines.append("- If migration was a dry-run, inspect `migration-import-output.txt` before rerunning with `--apply-migration`.")
  lines.append("- Keep `EnableEscc=0` until parked static checks pass.")
  lines.append("- For ESCC evidence, enable ESCC only while parked and rerun with `--sample-seconds 20`.")
  lines.append("- Fill `evidence/road-test-log-draft.md` only after the matching real-car test has actually passed.")
  lines.append("- Do not create a stable tag until `evidence-readiness.txt` shows every required stable stage ready.")
  lines.append("")
  return "\n".join(lines)


def build_manifest(
  args: argparse.Namespace,
  output_dir: Path,
  evidence_dir: Path,
  migration_cmd: Optional[Sequence[str]],
  migration_code: Optional[int],
  evidence_cmd: Sequence[str],
  evidence_code: int,
  readiness_cmd: Sequence[str],
  readiness_code: int,
  archive_path: Optional[Path],
) -> Dict[str, object]:
  return {
    "version": 1,
    "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "repo": str(ROOT),
    "branch": git_value(["branch", "--show-current"]),
    "commit": git_value(["rev-parse", "--short=12", "HEAD"]),
    "tags": git_value(["tag", "--points-at", "HEAD"]),
    "git_status": git_value(["status", "--short"]),
    "output_dir": str(output_dir),
    "migration_input": args.migration_input,
    "migration_mode": "apply" if args.apply_migration else ("dry-run" if args.migration_input else "skipped"),
    "migration_command": list(migration_cmd) if migration_cmd else None,
    "migration_exit_code": migration_code,
    "evidence_dir": str(evidence_dir),
    "evidence_command": list(evidence_cmd),
    "evidence_exit_code": evidence_code,
    "readiness_command": list(readiness_cmd),
    "readiness_exit_code": readiness_code,
    "sample_seconds": max(args.sample_seconds, 0),
    "archive": str(archive_path) if archive_path else None,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Run the first parked commissioning flow for the personal C3 ESCC build.")
  parser.add_argument("--output-dir", help="folder to write; defaults to /data/media/0 on C3 or /tmp elsewhere")
  parser.add_argument("--migration-input", help="safe params JSON exported from a working old version")
  parser.add_argument("--apply-migration", action="store_true", help="write params from --migration-input; omitted means dry-run")
  parser.add_argument("--sample-seconds", type=int, default=0, help="sample live CAN/CarrotMan messaging in the evidence snapshot")
  parser.add_argument("--target-tag", help="expected static/test tag passed to c3_static_check.py")
  parser.add_argument("--allow-branch", action="store_true", help="allow running from a branch instead of the target tag")
  parser.add_argument("--skip-preflight", action="store_true", help="skip repository preflight checks inside c3_static_check.py")
  parser.add_argument("--archive", action="store_true", help="also create a tar.gz archive beside the commissioning folder")
  parser.add_argument("--force", action="store_true", help="replace output directory when it already exists")
  args = parser.parse_args()

  if args.apply_migration and not args.migration_input:
    print("commissioning failed: --apply-migration requires --migration-input")
    return 2

  output_dir = Path(args.output_dir).expanduser() if args.output_dir else default_output_dir()
  if not output_dir.is_absolute():
    output_dir = ROOT / output_dir
  evidence_dir = output_dir / "evidence"

  try:
    clean_output_dir(output_dir, args.force)

    migration_cmd = build_migration_command(args)
    migration_code: Optional[int] = None
    if migration_cmd:
      migration_code, migration_output = run(migration_cmd)
      write_text(output_dir / "migration-import-output.txt", migration_output + "\n")
    else:
      write_text(output_dir / "migration-import-output.txt", "SKIPPED: no --migration-input was provided.\n")

    evidence_cmd = build_evidence_command(args, evidence_dir)
    evidence_code, evidence_output = run(evidence_cmd)
    write_text(output_dir / "evidence-collection-output.txt", evidence_output + "\n")

    readiness_cmd = build_readiness_command(evidence_dir)
    readiness_code, readiness_output = run(readiness_cmd)
    write_text(output_dir / "evidence-readiness.txt", readiness_output + "\n")

    archive_path: Optional[Path] = output_dir.with_suffix(".tar.gz") if args.archive else None
    manifest = build_manifest(
      args,
      output_dir,
      evidence_dir,
      migration_cmd,
      migration_code,
      evidence_cmd,
      evidence_code,
      readiness_cmd,
      readiness_code,
      archive_path,
    )
    write_text(output_dir / "README.md", build_readme(manifest))
    write_text(output_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    if args.archive:
      archive_path = make_archive(output_dir)

    print(f"wrote commissioning folder: {output_dir}")
    if archive_path:
      print(f"wrote archive: {archive_path}")
    if migration_code not in {None, 0}:
      print("params migration step failed; inspect migration-import-output.txt")
      return migration_code
    if evidence_code != 0:
      print("evidence collection failed; inspect evidence-collection-output.txt and evidence/static-check.md")
      return evidence_code
    if readiness_code != 0:
      print("readiness report failed; inspect evidence-readiness.txt")
      return readiness_code
    print("OK: C3 commissioning flow finished")
    return 0
  except Exception as exc:
    print("commissioning failed:", exc)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
