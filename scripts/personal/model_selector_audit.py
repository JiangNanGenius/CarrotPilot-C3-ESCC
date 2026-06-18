#!/usr/bin/env python3
import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
SOURCE_REF_CANDIDATES = [
  "origin/happymaj11r/carrot-wip-model_selector",
  "tracking/model-selector",
]
SOURCE_FILES = [
  "carrot/model_selector/README.md",
  "carrot/model_selector/config.py",
  "carrot/model_selector/manifest.py",
  "carrot/model_selector/downloader.py",
  "carrot/model_selector/validator.py",
  "carrot/model_selector/installer.py",
  "carrot/model_selector/modeld_runner.py",
  "carrot/model_selector/web/routes.py",
]


@dataclass
class Check:
  name: str
  ok: bool
  detail: str


def run_git(args: Sequence[str]) -> Tuple[int, str]:
  proc = subprocess.run(
    ["git", *args],
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  return proc.returncode, proc.stdout.strip()


def ref_exists(ref: str) -> bool:
  code, _ = run_git(["rev-parse", "--verify", "--quiet", ref])
  return code == 0


def resolve_source_ref(explicit: Optional[str] = None) -> str:
  refs = [explicit] if explicit else SOURCE_REF_CANDIDATES
  for ref in refs:
    if ref and ref_exists(ref):
      return ref
  raise RuntimeError("model selector source ref not found; fetch origin happymaj11r/carrot-wip-model_selector")


def git_show(ref: str, path: str) -> str:
  code, output = run_git(["show", f"{ref}:{path}"])
  if code != 0:
    raise RuntimeError(f"cannot read {ref}:{path}: {output}")
  return output


def worktree_text(path: str) -> str:
  p = ROOT / path
  if not p.exists() or not p.is_file():
    return ""
  return p.read_text(encoding="utf-8", errors="replace")


def path_exists(path: str) -> bool:
  return (ROOT / path).exists()


def contains(text: str, needle: str) -> bool:
  return needle in text


def all_contains(text: str, needles: Sequence[str]) -> Tuple[bool, List[str]]:
  missing = [needle for needle in needles if needle not in text]
  return not missing, missing


def check_source_contract(ref: str) -> List[Check]:
  texts = {path: git_show(ref, path) for path in SOURCE_FILES}
  checks: List[Check] = []

  required_files_missing = []
  for file in SOURCE_FILES:
    code, _ = run_git(["cat-file", "-e", f"{ref}:{file}"])
    if code != 0:
      required_files_missing.append(file)
  checks.append(Check("source files", not required_files_missing, "missing: " + ", ".join(required_files_missing) if required_files_missing else "all expected files present"))

  ok, missing = all_contains(texts["carrot/model_selector/README.md"], [
    "\ub450 \uc5d4\uc9c4 \uc644\uc804 \ubd84\ub9ac",
    "modeld_runner",
    "DrivingModelName",
    "PendingModelName",
    "\uae30\ubcf8 \ubaa8\ub378 \ubcf5\uc6d0",
  ])
  checks.append(Check("source design notes", ok, "missing: " + ", ".join(missing) if missing else "documents split engine, params, reset flow"))

  ok, missing = all_contains(texts["carrot/model_selector/config.py"], [
    'MODELS_DIR = Path("/data/models")',
    'MODELS_TMP_DIR = Path("/data/models_tmp")',
    "MODELS_JSON_URL",
    "ALLOWED_URL_PREFIX",
    "ALLOWED_ONNX_FILES",
    '"driving_vision.onnx"',
    '"driving_policy.onnx"',
    '"driving_on_policy.onnx"',
    '"driving_off_policy.onnx"',
    'PARAM_DRIVING_MODEL_NAME = "DrivingModelName"',
    'PARAM_PENDING_MODEL_NAME = "PendingModelName"',
    "MODEL_ID_REGEX",
  ])
  checks.append(Check("source config guardrails", ok, "missing: " + ", ".join(missing) if missing else "paths, allowlists, params, model id regex present"))

  ok, missing = all_contains(texts["carrot/model_selector/manifest.py"], [
    "to_canonical_json",
    "Ed25519PublicKey",
    "key_id",
    "signature",
    "MODEL_SIGNING_KEYS",
    "ALLOWED_ONNX_FILES",
    "minimum_selector_version",
  ])
  checks.append(Check("source manifest verification", ok, "missing: " + ", ".join(missing) if missing else "canonical JSON and Ed25519 signature checks present"))

  ok, missing = all_contains(texts["carrot/model_selector/downloader.py"], [
    "_validate_model_id",
    "_validate_url",
    "ALLOWED_URL_PREFIX",
    "ALLOWED_ONNX_FILES",
    "sha256 mismatch",
    "size mismatch",
    ".part",
    "driving_vision.onnx",
  ])
  checks.append(Check("source download verification", ok, "missing: " + ", ".join(missing) if missing else "id/url/file allowlists plus size and sha256 checks present"))

  ok, missing = all_contains(texts["carrot/model_selector/validator.py"], [
    "driving_vision",
    "driving_on_policy",
    "driving_policy",
    "driving_off_policy",
    "is_valid_model_dir",
    "describe",
  ])
  checks.append(Check("source installed-model validator", ok, "missing: " + ", ".join(missing) if missing else "vision + policy validation with optional off policy present"))

  ok, missing = all_contains(texts["carrot/model_selector/installer.py"], [
    "compile_pending",
    "reset_to_default",
    "_atomic_swap",
    "_restore_backup_if_needed",
    "PendingModelName",
    "DrivingModelName",
    "compile3.py",
    "compile_warp.py",
  ])
  checks.append(Check("source installer safety", ok, "missing: " + ", ".join(missing) if missing else "boot compile, atomic swap, backup restore, reset flow present"))

  ok, missing = all_contains(texts["carrot/model_selector/modeld_runner.py"], [
    "upstream_modeld",
    "carrot_modeld",
    "is_valid_model_dir",
    "/data/model_selector_status",
    "running upstream modeld",
  ])
  checks.append(Check("source modeld fallback", ok, "missing: " + ", ".join(missing) if missing else "custom engine fallback to upstream modeld present"))

  ok, missing = all_contains(texts["carrot/model_selector/web/routes.py"], [
    "/api/models/list",
    "/api/models/status",
    "/api/models/install",
    "/api/models/apply",
    "/api/models/reset",
    "fetch_and_verify",
    "download_model",
    "sudo",
    "reboot",
  ])
  checks.append(Check("source web routes", ok, "missing: " + ", ".join(missing) if missing else "list/status/install/apply/reset routes present"))
  return checks


def check_current_branch_boundary() -> List[Check]:
  markers = {
    "model selector package": path_exists("carrot/model_selector") or path_exists("openpilot/carrot/model_selector"),
    "model routes": contains(worktree_text("selfdrive/carrot/server/features/models.py"), "/api/models/install") or contains(worktree_text("selfdrive/carrot/server/app_factory.py"), "model_selector"),
    "model params": contains(worktree_text("common/params_keys.h"), "DrivingModelName") or contains(worktree_text("common/params_keys.h"), "PendingModelName"),
    "modeld runner": contains(worktree_text("system/manager/process_config.py"), "model_selector.modeld_runner"),
    "boot compile": contains(worktree_text("system/manager/manager.py"), "boot_compile"),
    "web models tab": (
      contains(worktree_text("selfdrive/carrot/web/index.html"), "page_models")
      or contains(worktree_text("selfdrive/carrot/web/index.html"), "btnModels")
      or contains(worktree_text("selfdrive/carrot/web/js/app.js"), "/models/page_models.js")
    ),
  }
  present = [name for name, value in markers.items() if value]
  if not present:
    return [Check("current branch integration boundary", True, "model selector is not integrated into the default C3 line")]

  required = {
    "package": markers["model selector package"],
    "params": markers["model params"],
    "modeld runner": markers["modeld runner"],
    "boot compile": markers["boot compile"],
    "web routes": markers["model routes"],
    "web tab": markers["web models tab"],
  }
  missing = [name for name, value in required.items() if not value]
  checks = [
    Check("current branch integration boundary", not missing, "present markers: " + ", ".join(present) + ("; missing: " + ", ".join(missing) if missing else "")),
  ]

  if markers["modeld runner"]:
    process_config = worktree_text("system/manager/process_config.py")
    safe = "selfdrive.modeld.modeld" in process_config or "model_selector.modeld_runner" in process_config
    checks.append(Check("current modeld process registration", safe, "modeld process mentions runner/default modeld" if safe else "modeld process registration unclear"))
  return checks


def print_checks(title: str, checks: Sequence[Check]) -> None:
  print(title)
  for check in checks:
    state = "PASS" if check.ok else "FAIL"
    print(f"[{state}] {check.name}: {check.detail}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit model selector source and current integration boundary.")
  parser.add_argument("--source-ref", help="git ref for the model selector reference branch")
  parser.add_argument("--source-only", action="store_true", help="only check the reference branch source contract")
  parser.add_argument("--boundary-only", action="store_true", help="only check current branch integration boundary")
  args = parser.parse_args()

  failures = 0
  print("Model selector audit")
  print("repo:", ROOT)

  if not args.boundary_only:
    try:
      ref = resolve_source_ref(args.source_ref)
      code, sha = run_git(["rev-parse", "--short=12", ref])
      print(f"source ref: {ref} @ {sha if code == 0 else 'unknown'}")
      source_checks = check_source_contract(ref)
      print_checks("## Source Contract", source_checks)
      failures += sum(1 for check in source_checks if not check.ok)
    except Exception as exc:
      failures += 1
      print("## Source Contract")
      print(f"[FAIL] source contract: {exc}")

  if not args.source_only:
    boundary_checks = check_current_branch_boundary()
    print_checks("## Current Branch Boundary", boundary_checks)
    failures += sum(1 for check in boundary_checks if not check.ok)

  if failures:
    print(f"FAILED: {failures} model selector audit check(s)")
    return 2
  print("OK: model selector audit passed")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
