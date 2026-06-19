#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LEGACY_C3_RESCUE_PASSWORD = "".join(("C3", "Debug", "123456"))

GIT_BLOB_FIRST_PATHS = {
  "sunnypilot/models/helpers.py",
}

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
  "system/ui/lib/wifi_manager.py",
  "selfdrive/ui/installer/installer.cc",
  "selfdrive/ui/widgets/ssh_key.py",
  "selfdrive/ui/layouts/settings/developer.py",
  "selfdrive/ui/mici/layouts/settings/developer.py",
  "selfdrive/ui/sunnypilot/layouts/settings/settings.py",
  "selfdrive/ui/sunnypilot/layouts/settings/network.py",
  "selfdrive/ui/layouts/settings/software.py",
  "selfdrive/ui/sunnypilot/layouts/settings/software.py",
  "selfdrive/ui/sunnypilot/layouts/settings/models.py",
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
  try:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=15)
    return proc.returncode, (proc.stdout + proc.stderr).strip()
  except subprocess.TimeoutExpired as exc:
    cmd = " ".join(["git", *args])
    output = ((exc.stdout or "") + (exc.stderr or "")).strip()
    return 124, f"{cmd} timed out after 15s\n{output}".strip()


def materialize_path(path: Path) -> None:
  if sys.platform != "darwin" or shutil.which("brctl") is None:
    return
  try:
    subprocess.run(
      ["brctl", "download", str(path)],
      cwd=ROOT,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
      timeout=3,
    )
  except Exception:
    pass


def read_git_blob(rel: str) -> str | None:
  for spec in (f":{rel}", f"HEAD:{rel}"):
    try:
      proc = subprocess.run(
        ["git", "show", spec],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
      )
    except subprocess.TimeoutExpired:
      continue
    if proc.returncode == 0:
      return proc.stdout
  return None


def read(rel: str) -> str:
  if rel in GIT_BLOB_FIRST_PATHS:
    text = read_git_blob(rel)
    if text is not None:
      return text
  path = ROOT / rel
  materialize_path(path)
  try:
    return path.read_text(encoding="utf-8", errors="ignore")
  except OSError:
    text = read_git_blob(rel)
    if text is not None:
      return text
    raise


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


def reference_state(include_diffs: bool = False) -> dict[str, Any]:
  refs: dict[str, Any] = {}
  for name, ref in REFERENCE_REFS.items():
    ref_state = local_ref(ref)
    if include_diffs and ref_state["available"]:
      ref_state["diffToHead"] = diff_summary(ref)
    refs[name] = ref_state
  return refs


def process_config_runtime_blocked(process_config: str) -> bool:
  return all(token not in process_config for token in FORBIDDEN_RUNTIME_PROCESS_NAMES)


def private_tokens_absent(*texts: str) -> bool:
  combined = "\n".join(texts).lower()
  return all(token.lower() not in combined for token in FORBIDDEN_PRIVATE_TOKENS)


def token_inside_internal_block(text: str, token: str) -> bool:
  start = text.find("#ifdef INTERNAL")
  token_index = text.find(token)
  end = text.find("#endif", start)
  return start >= 0 and end >= 0 and start < token_index < end


def local_checks() -> list[dict[str, Any]]:
  launch_openpilot = read("launch_openpilot.sh")
  c3_launch = read("sunnypilot/system/hardware/c3/launch_chffrplus.sh")
  c3_env = read("sunnypilot/system/hardware/c3/launch_env.sh")
  c3_rescue = read("sunnypilot/system/hardware/c3/rescue_ssh.sh")
  root_launch = read("launch_chffrplus.sh")
  params_keys = read("common/params_keys.h")
  version = read("system/version.py")
  hardware_init = read("system/hardware/__init__.py")
  tici_hw = read("system/hardware/tici/hardware.h")
  hardwared = read("system/hardware/hardwared.py")
  process_config = read("system/manager/process_config.py")
  wifi_manager = read("system/ui/lib/wifi_manager.py")
  installer = read("selfdrive/ui/installer/installer.cc")
  ssh_widget = read("selfdrive/ui/widgets/ssh_key.py")
  developer_layout = read("selfdrive/ui/layouts/settings/developer.py")
  mici_developer_layout = read("selfdrive/ui/mici/layouts/settings/developer.py")
  sp_settings = read("selfdrive/ui/sunnypilot/layouts/settings/settings.py")
  mici_settings = read("selfdrive/ui/mici/layouts/settings/settings.py")
  sp_network = read("selfdrive/ui/sunnypilot/layouts/settings/network.py")
  base_software = read("selfdrive/ui/layouts/settings/software.py")
  sp_software = read("selfdrive/ui/sunnypilot/layouts/settings/software.py")
  sp_models = read("selfdrive/ui/sunnypilot/layouts/settings/models.py")
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
      "public_installer_does_not_install_default_ssh_key",
      "GithubSshKeys" not in installer
      and "ssh-ed25519" not in installer
      and token_inside_internal_block(installer, "SshEnabled")
      and token_inside_internal_block(installer, "git remote set-url origin --push"),
      "Installer must not ship a default SSH public key; internal push remotes must stay inside the INTERNAL block only",
    ),
    status(
      "c3_rescue_ssh_is_bench_only",
      "CARROT_C3_RESCUE_ENABLE" in c3_rescue
      and "/data/carrotpilot/bench_rescue_enable" in c3_rescue
      and "/data/carrotpilot/bench_rescue_authorized_keys" in c3_rescue
      and "CARROT_C3_RESCUE_PASSWORD" in c3_rescue
      and "CARROT_C3_RESCUE_PUBKEY" in c3_rescue
      and "rescue_is_armed" in c3_rescue
      and "write_status \"disabled\"" in c3_rescue
      and "GithubSshKeys" not in c3_rescue
      and LEGACY_C3_RESCUE_PASSWORD not in c3_rescue
      and "RESCUE_PUBKEY=" not in c3_rescue,
      "C3 rescue SSH must be inert unless explicitly armed and must not ship a public password/key or write GithubSshKeys",
    ),
    status(
      "local_wifi_settings_retained",
      "class WifiManager" in wifi_manager
      and "NetworkManager" in wifi_manager
      and "WifiManager" in sp_settings
      and "PanelType.NETWORK" in sp_settings
      and "NetworkUISP" in sp_settings
      and "self._wifi_manager._request_scan()" in sp_network,
      "Local Wi-Fi settings and scan/connect UI must remain available without cloud services",
    ),
    status(
      "wifi_manager_jeepney_missing_fallback",
      "except ModuleNotFoundError:" in wifi_manager
      and "JEEPNEY_AVAILABLE = False" in wifi_manager
      and "Wi-Fi manager using nmcli fallback: python package 'jeepney' is unavailable" in wifi_manager
      and "self._nmcli_fallback = not JEEPNEY_AVAILABLE" in wifi_manager
      and "def _nmcli_rows" in wifi_manager
      and "nmcli" in wifi_manager
      and "self._exit = True" not in wifi_manager.split("if not JEEPNEY_AVAILABLE:", 1)[1].split("else:", 1)[0],
      "Clone C3 setup may not have jeepney; missing DBus Python bindings must not crash manager/UI startup",
    ),
    status(
      "local_ssh_keys_retained_without_cloud_dependency",
      '"GithubSshKeys", {PERSISTENT | BACKUP, STRING}' in params_keys
      and '"SshEnabled", {PERSISTENT | BACKUP, BOOL}' in params_keys
      and "normalize_ssh_public_keys" in ssh_widget
      and "set_manual_keys" in ssh_widget
      and "Paste a local public key to avoid GitHub lookup." in ssh_widget
      and "https://github.com/{username}.keys" in ssh_widget
      and "ssh_key_item" in developer_layout
      and "is_ssh_public_key_text" in mici_developer_layout
      and "manage_athenad" not in process_config,
      "SSH must keep local SshEnabled/GithubSshKeys params and allow manual public-key setup without athenad/cloud",
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
      "mici_comma_pairing_entry_removed",
      "PairBigButton" not in mici_settings
      and "PairingDialog" not in mici_settings
      and "connect.comma.ai" not in mici_settings,
      "MICI settings must not keep comma connect pairing buttons after cloud pairing is removed",
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
      and 'PythonProcess("mapd_manager", "sunnypilot.mapd.mapd_manager", always_run)' in process_config
      and 'NativeProcess("mapd", Paths.mapd_root()' in process_config,
      "Local updater, models manager, Carrot Web, mapd manager, and mapd local services must remain available",
    ),
    status(
      "local_update_and_model_ui_retained",
      "pkill -SIGUSR1 -f system.updated.updated" in base_software + sp_software
      and "pkill -SIGHUP -f system.updated.updated" in base_software + sp_software
      and "ModelManager_LastSyncTime" in sp_models
      and "ModelManager_DownloadIndex" in sp_models
      and "not a cloud pairing service" in sp_models,
      "Software update controls and offroad model list/download controls must remain available as active local maintenance",
    ),
  ]


def build_report(
  include_reference_diffs: bool = False,
  include_references: bool = True,
  include_git_metadata: bool = True,
) -> dict[str, Any]:
  if include_git_metadata:
    code, head = run_git(["rev-parse", "--short=12", "HEAD"])
    code_branch, branch = run_git(["branch", "--show-current"])
  else:
    code, head = 1, ""
    code_branch, branch = 1, ""
  checks = local_checks()
  refs = reference_state(include_reference_diffs) if include_references else {}
  return {
    "metadata": {
      "title": "CarrotPilot-C3-ESCC C3/TICI Compatibility Audit",
      "repo": str(ROOT),
      "branch": branch if code_branch == 0 else "",
      "commit": head if code == 0 else "",
    },
    "references": refs,
    "checks": checks,
    "failedChecks": [check["name"] for check in checks if not check["ok"]],
    "missingReferenceRefs": [
      name for name, ref_state in refs.items()
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
  parser.add_argument("--include-reference-diffs", action="store_true", help="include git diff summaries against local reference refs")
  parser.add_argument("--skip-reference-refs", action="store_true", help="skip optional reference ref discovery for fast local/static checks")
  parser.add_argument("--skip-git-metadata", action="store_true", help="skip optional branch/commit discovery for fast local/static checks")
  parser.add_argument("--require-mrone-refs", action="store_true", help="also fail when Mr.One local refs are missing")
  args = parser.parse_args()

  report = build_report(
    include_reference_diffs=args.include_reference_diffs and not args.skip_reference_refs,
    include_references=not args.skip_reference_refs,
    include_git_metadata=not args.skip_git_metadata,
  )
  print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
  if args.strict and report["failedChecks"]:
    return 2
  if args.require_mrone_refs and report["missingReferenceRefs"]:
    return 3
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
