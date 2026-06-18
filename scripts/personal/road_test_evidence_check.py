#!/usr/bin/env python3
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PASS_LINES = [
  "Seltos real-car test: PASS",
  "AlwaysOffline ACC power-cycle test: PASS",
  "ESCC 0x2AB observed: PASS",
  "Low-speed road test: PASS",
  "Rollback target recorded: PASS",
]

REQUIRED_LOG_FIELDS = [
  "日期",
  "设备",
  "车辆",
  "分支",
  "commit",
  "tag",
  "设备快照文件",
  "回滚目标",
]

EMPTY_MARKERS = {
  "",
  "PENDING",
  "TODO",
  "TBD",
  "N/A",
  "无",
  "未填",
  "待填",
}

TRUE_VALUES = {"1", "true", "True", "TRUE", "yes", "YES", "on", "ON"}
FALSE_VALUES = {"0", "false", "False", "FALSE", "no", "NO", "off", "OFF"}
EVIDENCE_LOG_CANDIDATES = [
  "road-test-log.md",
  "road-test-log-draft.md",
]
EVIDENCE_SNAPSHOT_CANDIDATES = [
  "device-snapshot.md",
  "carrotpilot-c3-escc-snapshot.md",
]
EVIDENCE_NAVIPILOT_CANDIDATES = [
  "navipilot-live-check.json",
]


class EvidenceError(Exception):
  pass


def resolve_path(path: str) -> Path:
  p = Path(path).expanduser()
  if not p.is_absolute():
    p = ROOT / p
  return p


def read_text(path: str) -> Tuple[Path, str]:
  p = resolve_path(path)
  if not p.exists():
    raise EvidenceError(f"file not found: {path}")
  return p, p.read_text(encoding="utf-8")


def unique_paths(paths: Sequence[str]) -> List[str]:
  seen = set()
  result: List[str] = []
  for path in paths:
    resolved = str(resolve_path(path))
    if resolved in seen:
      continue
    seen.add(resolved)
    result.append(resolved)
  return result


def is_filled(value: str) -> bool:
  stripped = value.strip()
  return stripped not in EMPTY_MARKERS and not stripped.startswith("<missing")


def find_first_file(base: Path, names: Sequence[str]) -> Optional[Path]:
  for name in names:
    path = base / name
    if path.is_file():
      return path
  return None


def validate_evidence_manifest(base: Path) -> None:
  manifest = base / "manifest.json"
  if not manifest.exists():
    return
  try:
    data = json.loads(manifest.read_text(encoding="utf-8"))
  except Exception as exc:
    raise EvidenceError(f"{manifest}: cannot read evidence manifest: {exc}") from exc

  static_code = data.get("static_check_exit_code")
  if static_code != 0:
    raise EvidenceError(f"{manifest}: static_check_exit_code must be 0, got {static_code!r}")


def inspect_evidence_dir(path: str) -> Tuple[Optional[str], List[str]]:
  base = resolve_path(path)
  if not base.exists():
    raise EvidenceError(f"evidence directory not found: {path}")
  if not base.is_dir():
    raise EvidenceError(f"evidence directory must be an unpacked folder, got: {path}")

  validate_evidence_manifest(base)

  log_path = find_first_file(base, EVIDENCE_LOG_CANDIDATES)
  snapshot_path = find_first_file(base, EVIDENCE_SNAPSHOT_CANDIDATES)
  snapshots = [str(snapshot_path)] if snapshot_path is not None else []
  return str(log_path) if log_path is not None else None, snapshots


def inspect_navipilot_evidence_dir(path: str) -> List[str]:
  base = resolve_path(path)
  if not base.exists() or not base.is_dir():
    raise EvidenceError(f"evidence directory must be an unpacked folder, got: {path}")
  nav_path = find_first_file(base, EVIDENCE_NAVIPILOT_CANDIDATES)
  return [str(nav_path)] if nav_path is not None else []


def collect_evidence_inputs(
  road_test_log: Optional[str],
  device_snapshots: Sequence[str],
  evidence_dirs: Sequence[str],
) -> Tuple[Optional[str], List[str]]:
  bundle_logs: List[str] = []
  bundle_snapshots: List[str] = []
  for evidence_dir in evidence_dirs:
    log_path, snapshot_paths = inspect_evidence_dir(evidence_dir)
    if log_path:
      bundle_logs.append(log_path)
    bundle_snapshots.extend(snapshot_paths)

  selected_log = road_test_log or (bundle_logs[0] if bundle_logs else None)
  snapshots = unique_paths([*device_snapshots, *bundle_snapshots])
  return selected_log, snapshots


def collect_navipilot_inputs(navipilot_live_checks: Sequence[str], evidence_dirs: Sequence[str]) -> List[str]:
  bundle_navipilot: List[str] = []
  for evidence_dir in evidence_dirs:
    bundle_navipilot.extend(inspect_navipilot_evidence_dir(evidence_dir))
  return unique_paths([*navipilot_live_checks, *bundle_navipilot])


def parse_log_fields(text: str) -> Dict[str, str]:
  fields: Dict[str, str] = {}
  for line in text.splitlines():
    match = re.match(r"^-\s*([^:：]+)\s*[:：]\s*(.*)$", line)
    if match:
      fields[match.group(1).strip()] = match.group(2).strip()
  return fields


def validate_log(text: str) -> Dict[str, str]:
  missing_pass = [line for line in REQUIRED_PASS_LINES if line not in text]
  if missing_pass:
    raise EvidenceError("road-test log is missing required PASS lines:\n" + "\n".join(missing_pass))

  fields = parse_log_fields(text)
  missing_fields = [field for field in REQUIRED_LOG_FIELDS if not is_filled(fields.get(field, ""))]
  if missing_fields:
    raise EvidenceError("road-test log has blank required fields:\n" + "\n".join(missing_fields))

  device = fields.get("设备", "")
  vehicle = fields.get("车辆", "")
  if "C3" not in device:
    raise EvidenceError("road-test log device field must identify the C3 device")
  if "Seltos 2023" not in vehicle or "CAN" not in vehicle:
    raise EvidenceError("road-test log vehicle field must identify Kia Seltos 2023 pure CAN")
  return fields


def parse_markdown_table_values(text: str) -> Dict[str, str]:
  values: Dict[str, str] = {}
  for raw_line in text.splitlines():
    line = raw_line.strip()
    if not line.startswith("|") or "`" not in line:
      continue
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if len(cells) < 2:
      continue
    key = cells[0].strip("` ")
    value = cells[1].strip()
    if key:
      values[key] = value
  return values


def int_value(values: Dict[str, str], key: str) -> int:
  raw = values.get(key, "").strip()
  try:
    return int(raw)
  except ValueError as exc:
    raise EvidenceError(f"snapshot value `{key}` must be an integer, got {raw!r}") from exc


def require_bool(values: Dict[str, str], key: str, expected: bool, label: str) -> None:
  raw = values.get(key, "").strip()
  allowed = TRUE_VALUES if expected else FALSE_VALUES
  if raw not in allowed:
    want = "true/on/1" if expected else "false/off/0"
    raise EvidenceError(f"{label}: snapshot `{key}` must be {want}, got {raw!r}")


def bool_value(values: Dict[str, str], key: str) -> bool:
  return values.get(key, "").strip() in TRUE_VALUES


def require_carparams_summary(values: Dict[str, str], label: str) -> None:
  decoded = values.get("CarParamsDecoded", "").strip()
  fingerprint = values.get("carFingerprint", "").strip()
  car_name = values.get("carName", "").strip()
  safety = values.get("safetyConfigs", "").strip()
  if decoded != "ok":
    raise EvidenceError(f"{label}: CarParamsDecoded must be ok, got {decoded!r}")
  if not is_filled(car_name):
    raise EvidenceError(f"{label}: carName is missing from CarParams summary")
  if not is_filled(fingerprint) or "SELTOS" not in fingerprint.upper():
    raise EvidenceError(f"{label}: carFingerprint must identify Seltos, got {fingerprint!r}")
  if not is_filled(safety) or safety == "<none>":
    raise EvidenceError(f"{label}: safetyConfigs summary is missing")


def require_offline_process_guard(values: Dict[str, str], label: str) -> None:
  require_bool(values, "AlwaysOffline", True, label)
  require_bool(values, "EnableConnect", False, label)
  require_bool(values, "process_snapshot_available", True, label)
  require_bool(values, "offline_forbidden_processes_seen", False, label)
  for key in ["updated_process_seen", "connect_process_seen", "uploader_process_seen"]:
    require_bool(values, key, False, label)


def require_power_cycle_boot(values: Dict[str, str], label: str) -> None:
  require_bool(values, "PowerCycleBootOk", True, label)
  snapshot_commit = values.get("commit", "").strip()
  recorded_commit = values.get("PowerCycleBootCommit", "").strip()
  recorded_at = values.get("PowerCycleBootRecordedAt", "").strip()
  if not is_filled(snapshot_commit) or snapshot_commit == "unknown":
    raise EvidenceError(f"{label}: snapshot commit is missing")
  if not is_filled(recorded_commit) or recorded_commit == "unknown":
    raise EvidenceError(f"{label}: PowerCycleBootCommit is missing")
  if snapshot_commit[:12] != recorded_commit[:12]:
    raise EvidenceError(
      f"{label}: PowerCycleBootCommit {recorded_commit!r} does not match snapshot commit {snapshot_commit!r}"
    )
  if not is_filled(recorded_at):
    raise EvidenceError(f"{label}: PowerCycleBootRecordedAt is missing")


def require_model_selector_status(values: Dict[str, str], label: str) -> None:
  required = [
    "DrivingModelName",
    "PendingModelName",
    "model_selector_status_available",
    "model_selector_engine",
    "model_selector_custom_active",
    "model_selector_pending_active",
    "model_selector_current_model",
    "model_selector_pending_model",
    "model_selector_describe",
  ]
  missing = [key for key in required if key not in values]
  if missing:
    raise EvidenceError(f"{label}: model selector status is missing:\n" + "\n".join(missing))
  if bool_value(values, "model_selector_pending_active"):
    pending = values.get("model_selector_pending_model", "")
    raise EvidenceError(f"{label}: model selector has pending model install/reboot state: {pending!r}")
  engine = values.get("model_selector_engine", "").strip()
  if engine not in {"default_upstream_assumed", "upstream_modeld", "carrot_modeld"}:
    raise EvidenceError(f"{label}: unexpected model selector engine: {engine!r}")


def validate_snapshot_text(name: str, text: str) -> Dict[str, str]:
  if "# CarrotPilot-C3-ESCC Device Snapshot" not in text:
    raise EvidenceError(f"{name}: not a CarrotPilot-C3-ESCC device snapshot")
  if "This snapshot intentionally avoids VIN" not in text:
    raise EvidenceError(f"{name}: privacy warning is missing")

  values = parse_markdown_table_values(text)
  required = [
    "branch",
    "commit",
    "AlwaysOffline",
    "EnableConnect",
    "EnableEscc",
    "CanfdHDA2",
    "HyundaiCameraSCC",
    "CarParams",
    "process_snapshot_available",
    "offline_forbidden_processes_seen",
    "updated_process_seen",
    "connect_process_seen",
    "uploader_process_seen",
    "enabled",
    "ok",
    "escc_0x2ab_bus0",
  ]
  missing = [key for key in required if not is_filled(values.get(key, ""))]
  if missing:
    raise EvidenceError(f"{name}: snapshot is missing required values:\n" + "\n".join(missing))

  if values.get("branch") == "unknown" or values.get("commit") == "unknown":
    raise EvidenceError(f"{name}: snapshot must include a real branch and commit")
  require_bool(values, "AlwaysOffline", True, name)
  require_bool(values, "EnableConnect", False, name)
  require_bool(values, "process_snapshot_available", True, name)
  require_bool(values, "CanfdHDA2", False, name)
  require_bool(values, "HyundaiCameraSCC", False, name)
  if values.get("CarParams") == "<missing>":
    raise EvidenceError(f"{name}: CarParams summary is missing; run snapshot on the C3 after car setup")
  return values


def validate_snapshots(
  snapshot_paths: Sequence[str],
  require_device_snapshot: bool,
  require_escc_sample: bool,
  require_cplink_sample: bool,
  require_amap_navi_sample: bool,
  require_model_selector_status_flag: bool,
  require_offline_guard: bool,
  require_carparams: bool,
  require_power_cycle_boot_flag: bool = False,
) -> List[Dict[str, str]]:
  if require_device_snapshot and not snapshot_paths:
    raise EvidenceError("stable evidence requires at least one --device-snapshot copied from the C3")

  snapshots: List[Dict[str, str]] = []
  for path in snapshot_paths:
    resolved, text = read_text(path)
    snapshots.append(validate_snapshot_text(str(resolved), text))

  if require_escc_sample:
    found = False
    for values in snapshots:
      enable_escc = bool_value(values, "EnableEscc")
      escc_bus0 = int_value(values, "escc_0x2ab_bus0")
      sample_enabled = bool_value(values, "enabled")
      sample_ok = bool_value(values, "ok")
      if enable_escc and sample_enabled and sample_ok and escc_bus0 > 0:
        found = True
        break
    if not found:
      raise EvidenceError("stable evidence requires a sampled snapshot with EnableEscc=1, enabled=True, ok=True, and escc_0x2ab_bus0 > 0")

  if require_cplink_sample:
    found = False
    for values in snapshots:
      sample_enabled = bool_value(values, "enabled")
      sample_ok = bool_value(values, "ok")
      updates_seen = bool_value(values, "cplink_updates_seen")
      nav_seen = any(bool_value(values, key) for key in [
        "cplink_speed_limit_seen",
        "cplink_sdi_seen",
        "cplink_tbt_seen",
        "cplink_gps_seen",
      ])
      carrot_updates = int_value(values, "carrotMan_updates")
      nav_updates = int_value(values, "navInstructionCarrot_updates")
      if sample_enabled and sample_ok and updates_seen and nav_seen and (carrot_updates > 0 or nav_updates > 0):
        found = True
        break
    if not found:
      raise EvidenceError(
        "CPlink evidence requires a sampled snapshot with enabled=True, ok=True, "
        "CPlink updates, and at least one speed/TBT/SDI/GPS navigation field"
      )

  if require_amap_navi_sample:
    found = False
    for values in snapshots:
      sample_enabled = bool_value(values, "enabled")
      sample_ok = bool_value(values, "ok")
      bridge_enabled = bool_value(values, "EnableAmapNaviStatus")
      updates_seen = bool_value(values, "amap_navi_updates_seen")
      amap_updates = int_value(values, "amapNavi_updates")
      if sample_enabled and sample_ok and bridge_enabled and updates_seen and amap_updates > 0:
        found = True
        break
    if not found:
      raise EvidenceError(
        "AmapNavi evidence requires a sampled snapshot with EnableAmapNaviStatus=1, "
        "enabled=True, ok=True, and amapNavi_updates > 0"
      )

  if require_model_selector_status_flag:
    found = False
    for values in snapshots:
      try:
        require_model_selector_status(values, "model selector status")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError(
        "model selector evidence requires a device snapshot with model selector status fields "
        "and no pending model install/reboot state"
      )

  if require_carparams:
    found = False
    for values in snapshots:
      try:
        require_carparams_summary(values, "CarParams summary")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError("evidence requires a decoded Seltos CarParams summary")

  if require_offline_guard:
    found = False
    for values in snapshots:
      try:
        require_offline_process_guard(values, "offline process guard")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError(
        "offline evidence requires AlwaysOffline=1, EnableConnect=0, process snapshot available, "
        "and no updated/connect/uploader process visible"
      )

  if require_power_cycle_boot_flag:
    found = False
    for values in snapshots:
      try:
        require_power_cycle_boot(values, "ACC/CAN power-cycle boot")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError(
        "power-cycle evidence requires PowerCycleBootOk=1 recorded after reboot, "
        "PowerCycleBootCommit matching the snapshot commit, and PowerCycleBootRecordedAt present"
      )
  return snapshots


def validate_navipilot_live_checks(paths: Sequence[str], require_navipilot_live_check: bool) -> List[Dict[str, object]]:
  if require_navipilot_live_check and not paths:
    raise EvidenceError("Navipilot evidence requires navipilot-live-check.json from the C3")

  reports: List[Dict[str, object]] = []
  for path in paths:
    resolved = resolve_path(path)
    if not resolved.exists():
      raise EvidenceError(f"Navipilot live check file not found: {path}")
    try:
      data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
      raise EvidenceError(f"{resolved}: cannot read Navipilot live check JSON: {exc}") from exc
    if not isinstance(data, dict):
      raise EvidenceError(f"{resolved}: Navipilot live check JSON must be an object")
    reports.append(data)

  if require_navipilot_live_check:
    found = False
    errors: List[str] = []
    for data in reports:
      overall_ok = bool_value_obj(data.get("overall_ok"))
      param_ok = bool_value_obj(data.get("param_bulk_ok"))
      status_requested = bool_value_obj(data.get("udp_7705_listen_requested"))
      status_ok = not status_requested or (
        bool_value_obj(data.get("udp_7705_seen")) and bool_value_obj(data.get("udp_7705_required_keys_ok"))
      )
      if overall_ok and param_ok and status_ok:
        found = True
        break
      errors.append(
        "overall_ok=%r param_bulk_ok=%r udp_7705_seen=%r udp_7705_required_keys_ok=%r"
        % (
          data.get("overall_ok"),
          data.get("param_bulk_ok"),
          data.get("udp_7705_seen"),
          data.get("udp_7705_required_keys_ok"),
        )
      )
    if not found:
      raise EvidenceError("Navipilot live check did not pass: " + "; ".join(errors))
  return reports


def bool_value_obj(value: object) -> bool:
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return value != 0
  return str(value).strip() in TRUE_VALUES


def self_test() -> None:
  good_log = """
# Test
- 日期：2026-06-17
- 设备：C3 中国克隆版
- 车辆：Kia Seltos 2023，纯 CAN
- 分支：personal/c3-escc-atune
- commit：abcdef123456
- tag：carrotpilot-c3-escc-20260617-test1
- 设备快照文件：snapshot.md
- 回滚目标：origin/c3-wip
Seltos real-car test: PASS
AlwaysOffline ACC power-cycle test: PASS
ESCC 0x2AB observed: PASS
Low-speed road test: PASS
Rollback target recorded: PASS
"""
  good_snapshot = """
# CarrotPilot-C3-ESCC Device Snapshot

This snapshot intentionally avoids VIN, dongle id, tokens, and route identifiers.

| Key | Value |
| --- | --- |
| `branch` | personal/c3-escc-atune |
| `commit` | abcdef123456 |
| `AlwaysOffline` | 1 |
| `EnableConnect` | 0 |
| `EnableEscc` | 1 |
| `CanfdHDA2` | 0 |
| `HyundaiCameraSCC` | 0 |
| `EnableAmapNaviStatus` | 1 |
| `DrivingModelName` | <missing> |
| `PendingModelName` | <missing> |
| `CarParams` | 200 bytes, sha256:abc |
| `PowerCycleBootOk` | 1 |
| `PowerCycleBootCommit` | abcdef123456 |
| `PowerCycleBootTag` | carrotpilot-c3-escc-20260617-test1 |
| `PowerCycleBootRecordedAt` | 2026-06-17T10:00:00+00:00 |
| `process_snapshot_available` | True |
| `offline_forbidden_processes_seen` | False |
| `updated_process_seen` | False |
| `connect_process_seen` | False |
| `uploader_process_seen` | False |
| `enabled` | True |
| `ok` | True |
| `escc_0x2ab_bus0` | 12 |
| `carrotMan_updates` | 4 |
| `navInstructionCarrot_updates` | 2 |
| `amapNavi_updates` | 3 |
| `cplink_updates_seen` | True |
| `cplink_speed_limit_seen` | True |
| `cplink_sdi_seen` | False |
| `cplink_tbt_seen` | True |
| `cplink_gps_seen` | False |
| `cplink_lanechange_cmd_seen` | False |
| `amap_navi_updates_seen` | True |
| `amap_navi_lane_seen` | True |
| `amap_navi_left_blind_seen` | False |
| `amap_navi_right_blind_seen` | False |
| `model_selector_status_available` | False |
| `model_selector_engine` | default_upstream_assumed |
| `model_selector_custom_active` | False |
| `model_selector_pending_active` | False |
| `model_selector_current_model` | <missing> |
| `model_selector_pending_model` | <missing> |
| `model_selector_describe` | status file missing; default upstream modeld assumed |
| `CarParamsDecoded` | ok |
| `carName` | hyundai |
| `carFingerprint` | KIA_SELTOS_2023 |
| `fingerprintSource` | fixed |
| `networkLocation` | fwdCamera |
| `safetyConfigs` | hyundaiLegacy:1024 |
| `spFlags` | 1 |
"""
  good_navipilot = {
    "overall_ok": True,
    "param_bulk_ok": True,
    "udp_7705_listen_requested": True,
    "udp_7705_seen": True,
    "udp_7705_required_keys_ok": True,
  }
  validate_log(good_log)
  validate_snapshot_text("self-test snapshot", good_snapshot)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_escc_sample=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_cplink_sample=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_amap_navi_sample=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_model_selector_status_flag=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_offline_guard=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_carparams=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_power_cycle_boot_flag=True)
  validate_navipilot_live_checks_from_objects([good_navipilot], require_navipilot_live_check=True)

  with tempfile.TemporaryDirectory() as tmp:
    bundle = Path(tmp)
    (bundle / "road-test-log-draft.md").write_text(good_log, encoding="utf-8")
    (bundle / "device-snapshot.md").write_text(good_snapshot, encoding="utf-8")
    (bundle / "navipilot-live-check.json").write_text(json.dumps(good_navipilot), encoding="utf-8")
    (bundle / "manifest.json").write_text('{"static_check_exit_code": 0}\n', encoding="utf-8")
    bundle_log, bundle_snapshots = collect_evidence_inputs(None, [], [str(bundle)])
    bundle_navipilot = collect_navipilot_inputs([], [str(bundle)])
    if not bundle_log or len(bundle_snapshots) != 1:
      raise EvidenceError("self-test failed: evidence bundle was not discovered")
    if len(bundle_navipilot) != 1:
      raise EvidenceError("self-test failed: Navipilot live check was not discovered")
    validate_log(read_text(bundle_log)[1])
    validate_snapshots(
      bundle_snapshots,
      require_device_snapshot=True,
      require_escc_sample=True,
      require_cplink_sample=True,
      require_amap_navi_sample=True,
      require_model_selector_status_flag=True,
      require_offline_guard=True,
      require_carparams=True,
      require_power_cycle_boot_flag=True,
    )
    validate_navipilot_live_checks(bundle_navipilot, require_navipilot_live_check=True)

  try:
    validate_log(good_log.replace("ESCC 0x2AB observed: PASS", "ESCC 0x2AB observed: PENDING"))
  except EvidenceError:
    pass
  else:
    raise EvidenceError("self-test failed: missing PASS line was accepted")

  try:
    validate_snapshots_from_text(
      [("self-test snapshot", good_snapshot.replace("PowerCycleBootCommit` | abcdef123456", "PowerCycleBootCommit` | stalecommit"))],
      require_power_cycle_boot_flag=True,
    )
  except EvidenceError:
    pass
  else:
    raise EvidenceError("self-test failed: stale power-cycle commit was accepted")

  try:
    validate_navipilot_live_checks_from_objects([{**good_navipilot, "overall_ok": False}], require_navipilot_live_check=True)
  except EvidenceError:
    pass
  else:
    raise EvidenceError("self-test failed: bad Navipilot live check was accepted")


def validate_snapshots_from_text(
  items: Sequence[Tuple[str, str]],
  require_escc_sample: bool = False,
  require_cplink_sample: bool = False,
  require_amap_navi_sample: bool = False,
  require_model_selector_status_flag: bool = False,
  require_offline_guard: bool = False,
  require_carparams: bool = False,
  require_power_cycle_boot_flag: bool = False,
) -> List[Dict[str, str]]:
  snapshots = [validate_snapshot_text(name, text) for name, text in items]
  if require_escc_sample:
    found = False
    for values in snapshots:
      enable_escc = bool_value(values, "EnableEscc")
      sample_enabled = bool_value(values, "enabled")
      sample_ok = bool_value(values, "ok")
      if enable_escc and sample_enabled and sample_ok and int_value(values, "escc_0x2ab_bus0") > 0:
        found = True
        break
    if not found:
      raise EvidenceError("self-test failed: ESCC sample was not detected")
  if require_cplink_sample:
    found = False
    for values in snapshots:
      nav_seen = any(bool_value(values, key) for key in [
        "cplink_speed_limit_seen",
        "cplink_sdi_seen",
        "cplink_tbt_seen",
        "cplink_gps_seen",
      ])
      if bool_value(values, "enabled") and bool_value(values, "ok") and bool_value(values, "cplink_updates_seen") and nav_seen:
        found = True
        break
    if not found:
      raise EvidenceError("self-test failed: CPlink sample was not detected")
  if require_amap_navi_sample:
    found = False
    for values in snapshots:
      if (
        bool_value(values, "enabled")
        and bool_value(values, "ok")
        and bool_value(values, "EnableAmapNaviStatus")
        and bool_value(values, "amap_navi_updates_seen")
        and int_value(values, "amapNavi_updates") > 0
      ):
        found = True
        break
    if not found:
      raise EvidenceError("self-test failed: AmapNavi sample was not detected")
  if require_model_selector_status_flag:
    found = False
    for values in snapshots:
      try:
        require_model_selector_status(values, "self-test snapshot")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError("self-test failed: model selector status was not detected")
  if require_carparams:
    found = False
    for values in snapshots:
      try:
        require_carparams_summary(values, "self-test snapshot")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError("self-test failed: CarParams summary was not detected")
  if require_offline_guard:
    found = False
    for values in snapshots:
      try:
        require_offline_process_guard(values, "self-test snapshot")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError("self-test failed: offline process guard was not detected")
  if require_power_cycle_boot_flag:
    found = False
    for values in snapshots:
      try:
        require_power_cycle_boot(values, "self-test snapshot")
        found = True
        break
      except EvidenceError:
        continue
    if not found:
      raise EvidenceError("self-test failed: power-cycle boot evidence was not detected")
  return snapshots


def validate_navipilot_live_checks_from_objects(
  reports: Sequence[Dict[str, object]],
  require_navipilot_live_check: bool = False,
) -> List[Dict[str, object]]:
  if require_navipilot_live_check and not reports:
    raise EvidenceError("self-test failed: missing Navipilot live check was accepted")
  if require_navipilot_live_check:
    for data in reports:
      if (
        bool_value_obj(data.get("overall_ok"))
        and bool_value_obj(data.get("param_bulk_ok"))
        and (
          not bool_value_obj(data.get("udp_7705_listen_requested"))
          or (
            bool_value_obj(data.get("udp_7705_seen"))
            and bool_value_obj(data.get("udp_7705_required_keys_ok"))
          )
        )
      ):
        return list(reports)
    raise EvidenceError("self-test failed: Navipilot live check was not detected")
  return list(reports)


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate real-car evidence before promoting a personal C3 ESCC tag.")
  parser.add_argument("--road-test-log", help="completed road-test markdown log")
  parser.add_argument("--device-snapshot", action="append", default=[], help="privacy-safe snapshot generated on the C3; may be repeated")
  parser.add_argument("--navipilot-live-check", action="append", default=[], help="JSON report from navipilot_live_check.py; may be repeated")
  parser.add_argument("--evidence-dir", action="append", default=[], help="unpacked folder generated by collect_real_car_evidence.py; may be repeated")
  parser.add_argument("--require-device-snapshot", action="store_true", help="fail when no device snapshot is supplied")
  parser.add_argument("--require-escc-sample", action="store_true", help="require EnableEscc=1 and sampled 0x2AB bus0 count > 0")
  parser.add_argument("--require-cplink-sample", action="store_true", help="require a sampled CP搭子/Navipilot update with speed/TBT/SDI/GPS data")
  parser.add_argument("--require-amap-navi-sample", action="store_true", help="require a sampled read-only AmapNavi status bridge update")
  parser.add_argument("--require-model-selector-status", action="store_true", help="require read-only model selector status in the device snapshot")
  parser.add_argument("--require-offline-process-guard", action="store_true", help="require AlwaysOffline with no updated/connect/uploader process visible")
  parser.add_argument("--require-power-cycle-boot", action="store_true", help="require a matching post-ACC/CAN-power-cycle boot confirmation in the device snapshot")
  parser.add_argument("--require-navipilot-live-check", action="store_true", help="require C3-side 7000/7705 Navipilot endpoint check to pass")
  parser.add_argument("--require-carparams-summary", action="store_true", help="require a decoded Seltos CarParams summary")
  parser.add_argument("--self-test", action="store_true", help="run built-in parser checks")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("OK: road-test evidence checker self-test passed")
      return 0

    road_test_log, snapshot_paths = collect_evidence_inputs(args.road_test_log, args.device_snapshot, args.evidence_dir)
    navipilot_paths = collect_navipilot_inputs(args.navipilot_live_check, args.evidence_dir)
    if not road_test_log:
      raise EvidenceError("--road-test-log or --evidence-dir is required unless --self-test is used")

    log_path, log_text = read_text(road_test_log)
    fields = validate_log(log_text)
    snapshots = validate_snapshots(
      snapshot_paths,
      args.require_device_snapshot,
      args.require_escc_sample,
      args.require_cplink_sample,
      args.require_amap_navi_sample,
      args.require_model_selector_status,
      args.require_offline_process_guard,
      args.require_carparams_summary,
      args.require_power_cycle_boot,
    )
    navipilot_reports = validate_navipilot_live_checks(navipilot_paths, args.require_navipilot_live_check)

    print("Road-test evidence check")
    print(f"repo: {ROOT}")
    print(f"road-test log: {log_path}")
    if args.evidence_dir:
      print("evidence dirs checked: " + str(len(args.evidence_dir)))
    print(f"vehicle: {fields.get('车辆')}")
    print(f"tag: {fields.get('tag')}")
    print(f"device snapshots checked: {len(snapshots)}")
    print(f"Navipilot live checks checked: {len(navipilot_reports)}")
    if args.require_escc_sample:
      print("ESCC sample: required and present")
    if args.require_cplink_sample:
      print("CPlink sample: required and present")
    if args.require_amap_navi_sample:
      print("AmapNavi sample: required and present")
    if args.require_model_selector_status:
      print("Model selector status: required and present")
    if args.require_offline_process_guard:
      print("Offline process guard: required and present")
    if args.require_power_cycle_boot:
      print("ACC/CAN power-cycle boot: required and present")
    if args.require_carparams_summary:
      print("CarParams summary: required and present")
    if args.require_navipilot_live_check:
      print("Navipilot live endpoint check: required and present")
    print("OK: road-test evidence is sufficient for the requested gate")
    return 0
  except EvidenceError as exc:
    print("road-test evidence check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
