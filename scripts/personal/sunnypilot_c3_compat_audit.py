#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

WATCHED_PATHS = (
  "launch_openpilot.sh",
  "launch_chffrplus.sh",
  "launch_env.sh",
  "sunnypilot/system/hardware/c3",
  "system/version.py",
  "system/hardware/__init__.py",
  "system/hardware/tici/hardware.h",
  "system/hardware/hardwared.py",
  "system/manager/process_config.py",
  "selfdrive/ui/installer/installer.cc",
  "selfdrive/modeld",
  "sunnypilot/modeld_v2",
  "sunnypilot/models/manager.py",
  "sunnypilot/models/helpers.py",
)

REFERENCE_REFS = {
  "sunnypilotStaging": "refs/remotes/sunnypilot/staging",
  "sunnypilotReleaseTizi": "refs/remotes/sunnypilot/release-tizi",
  "mroneDevc3": "refs/remotes/mrone-openpilot/devc3",
  "mroneRes": "refs/remotes/mrone-openpilot/res",
}

FORBIDDEN_RUNTIME_PROCESS_NAMES = (
  "manage_athenad",
  '"uploader"',
  "manage_sunnylinkd",
  "sunnylink_registration_manager",
  "statsd_sp",
  "backup_manager",
)

FORBIDDEN_PRIVATE_TOKENS = (
  "op.mr-one",
  "mr-one.cn",
  "jihulab.com/mr-one",
  "device_client",
  "private_registration",
)


def run_git(args: list[str]) -> tuple[int, str]:
  proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
  return proc.returncode, (proc.stdout + proc.stderr).strip()


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def file_exists(rel: str) -> bool:
  return (ROOT / rel).exists()


def status(name: str, ok: bool, detail: str, missing: bool = False) -> dict[str, Any]:
  return {
    "name": name,
    "status": "missing" if missing else ("pass" if ok else "fail"),
    "ok": bool(ok),
    "detail": detail,
  }


def local_ref(ref: str) -> dict[str, Any]:
  code, out = run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"])
  return {
    "ref": ref,
    "available": code == 0,
    "commit": out.splitlines()[0] if code == 0 and out else "",
    "error": "" if code == 0 else out[:240],
  }


def diff_summary(ref: str) -> dict[str, Any]:
  code, _ = run_git(["merge-base", "--is-ancestor", ref, "HEAD"])
  range_expr = f"{ref}..HEAD" if code == 0 else f"{ref}...HEAD"
  diff_code, out = run_git(["diff", "--name-status", range_expr, "--", *WATCHED_PATHS])
  if diff_code != 0:
    diff_code, out = run_git(["diff", "--name-status", f"{ref}..HEAD", "--", *WATCHED_PATHS])
  lines = [line for line in out.splitlines() if line.strip()] if diff_code == 0 else []
  return {
    "range": range_expr,
    "available": diff_code == 0,
    "changedFiles": lines,
    "changeCount": len(lines),
    "error": "" if diff_code == 0 else out[:240],
  }


def reference_state() -> dict[str, Any]:
  refs: dict[str, Any] = {}
  for name, ref in REFERENCE_REFS.items():
    ref_state = local_ref(ref)
    if ref_state["available"]:
      ref_state["diffToHead"] = diff_summary(ref)
    refs[name] = ref_state
  return refs


def process_config_runtime_blocked(process_config: str) -> bool:
  return all(token not in process_config for token in FORBIDDEN_RUNTIME_PROCESS_NAMES)


def private_tokens_absent(*texts: str) -> bool:
  combined = "\n".join(texts).lower()
  return all(token.lower() not in combined for token in FORBIDDEN_PRIVATE_TOKENS)


def local_checks() -> list[dict[str, Any]]:
  launch_openpilot = read("launch_openpilot.sh")
  c3_launch = read("sunnypilot/system/hardware/c3/launch_chffrplus.sh")
  c3_env = read("sunnypilot/system/hardware/c3/launch_env.sh")
  root_launch = read("launch_chffrplus.sh")
  version = read("system/version.py")
  hardware_init = read("system/hardware/__init__.py")
  tici_hw = read("system/hardware/tici/hardware.h")
  hardwared = read("system/hardware/hardwared.py")
  process_config = read("system/manager/process_config.py")
  installer = read("selfdrive/ui/installer/installer.cc")
  manager = read("sunnypilot/models/manager.py")
  model_helpers = read("sunnypilot/models/helpers.py")

  c3_files = (
    "sunnypilot/system/hardware/c3/launch_chffrplus.sh",
    "sunnypilot/system/hardware/c3/launch_env.sh",
    "sunnypilot/system/hardware/c3/agnos.json",
  )

  return [
    status(
      "c3_launcher_redirect",
      "comma tici" in launch_openpilot
      and "sunnypilot/system/hardware/c3/launch_chffrplus.sh" in launch_openpilot
      and 'exec "$C3_LAUNCH_SH"' in launch_openpilot,
      "launch_openpilot.sh must send comma tici devices to the C3 launcher",
    ),
    status(
      "c3_hardware_bundle_present",
      all(file_exists(path) for path in c3_files),
      "C3 launcher, environment, and AGNOS manifest must exist",
    ),
    status(
      "c3_launcher_uses_tici_agnos_tools",
      "system/hardware/tici/agnos.py" in c3_launch
      and "system/hardware/tici/updater" in c3_launch
      and 'AGNOS_VERSION="12.8"' in c3_env
      and 'STAGING_ROOT="/data/safe_staging"' in c3_env,
      "C3 launcher should reuse TICI AGNOS tooling and the C3 safe staging root",
    ),
    status(
      "root_launcher_keeps_shutdown_policy",
      "power_monitor.should_shutdown" in hardwared
      and "DoShutdown" in hardwared
      and "DisableShutdown" not in hardwared
      and "NeverShutdown" not in hardwared,
      "Power policy must retain normal shutdown checks instead of Mr.One-style never-shutdown behavior",
    ),
    status(
      "tici_device_detection_not_c4_or_c3x",
      "TICI = os.path.isfile('/TICI')" in hardware_init
      and '"tici", cereal::InitData::DeviceType::TICI' in tici_hw
      and '"tizi", cereal::InitData::DeviceType::TIZI' in tici_hw
      and "C3X" not in hardware_init + tici_hw
      and "C4" not in hardware_init + tici_hw,
      "Clone C3 devices that identify as tici must stay on the TICI/TIZI path, not C4/C3X",
    ),
    status(
      "c3_channels_are_tici_compatible",
      "C3_TICI_BRANCHES" in version
      and "alpha-sunnypilot-c3" in version
      and "experimental/sunnypilot-011-c3" in version
      and '"-c3" in self.channel' in version
      and 'return "tici"' in version,
      "C3 branches must be channel_type=tici so hardwared does not block comma tici devices",
    ),
    status(
      "installer_supports_tici_tizi_binary_install",
      "Hardware::get_device_type() == cereal::InitData::DeviceType::TICI" in installer
      and "Hardware::get_device_type() == cereal::InitData::DeviceType::TIZI" in installer
      and "migrated_branch = BRANCH_STR" in installer
      and "cachedFetch" in installer,
      "Binary installer must handle TICI/TIZI display/setup and keep the requested alpha branch unless migrated intentionally",
    ),
    status(
      "model_runner_split_present",
      "def is_stock_model" in process_config
      and "def is_tinygrad_model" in process_config
      and 'PythonProcess("modeld", "selfdrive.modeld.modeld"' in process_config
      and 'NativeProcess("modeld_tinygrad", "sunnypilot/modeld_v2"' in process_config
      and "get_active_model_runner" in process_config,
      "Stock modeld and Sunny tinygrad modeld_v2 must be selected by ModelRunnerTypeCache/active bundle",
    ),
    status(
      "model_manager_local_active_bundle_validation",
      "validate_active_bundle(self.params, self.available_models)" in manager
      and "verify_file" in manager
      and "def validate_active_bundle" in model_helpers
      and "def _verify_file" in model_helpers
      and "sha256" in model_helpers
      and "ModelManager_ActiveBundle" in manager
      and "ModelRunnerTypeCache" in model_helpers
      and "Runner.stock" in model_helpers,
      "Model manager must validate active bundles and keep runner cache evidence",
    ),
    status(
      "cloud_and_upload_managers_not_registered",
      process_config_runtime_blocked(process_config),
      "Mr.One/Sunnylink/comma cloud, upload, statsd_sp, and backup managers must not be registered",
    ),
    status(
      "mrone_private_tokens_absent_from_runtime_paths",
      private_tokens_absent(launch_openpilot, c3_launch, root_launch, version, hardwared, process_config, installer),
      "Do not import Mr.One private registration/client/server tokens into runtime paths",
    ),
    status(
      "local_update_and_model_services_retained",
      'PythonProcess("updated", "system.updated.updated", only_offroad, enabled=not PC)' in process_config
      and 'PythonProcess("models_manager", "sunnypilot.models.manager", only_offroad)' in process_config
      and 'PythonProcess("carrot_server", "selfdrive.carrot.carrot_server", always_run)' in process_config
      and 'NativeProcess("mapd", Paths.mapd_root()' in process_config,
      "Local updater, models manager, Carrot Web, and mapd local services must remain available",
    ),
  ]


def build_report() -> dict[str, Any]:
  code, head = run_git(["rev-parse", "--short=12", "HEAD"])
  code_branch, branch = run_git(["branch", "--show-current"])
  checks = local_checks()
  return {
    "metadata": {
      "title": "CarrotPilot-C3-ESCC C3/TICI Compatibility Audit",
      "repo": str(ROOT),
      "branch": branch if code_branch == 0 else "",
      "commit": head if code == 0 else "",
    },
    "references": reference_state(),
    "checks": checks,
    "failedChecks": [check["name"] for check in checks if not check["ok"]],
    "missingReferenceRefs": [
      name for name, ref_state in reference_state().items()
      if not ref_state.get("available", False) and name.startswith("mrone")
    ],
    "policy": {
      "mroneUsage": "reference-only; do not import private registration, upload, cloud, never-shutdown, or broad safety/opendbc changes",
      "c3UserHardware": "Chinese clone C3 identifying as comma tici, not C3X/C4",
      "branchGate": "alpha-sunnypilot-c3 and experimental/sunnypilot-011-c3 are treated as tici-compatible channels",
    },
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit C3/TICI compatibility boundaries for the SunnyPilot alpha line.")
  parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
  parser.add_argument("--strict", action="store_true", help="fail if any local compatibility check fails")
  parser.add_argument("--require-mrone-refs", action="store_true", help="also fail when Mr.One local refs are missing")
  args = parser.parse_args()

  report = build_report()
  print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
  if args.strict and report["failedChecks"]:
    return 2
  if args.require_mrone_refs and report["missingReferenceRefs"]:
    return 3
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
