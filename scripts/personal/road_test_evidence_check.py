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
  require_carparams: bool,
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
  return snapshots


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
| `CarParams` | 200 bytes, sha256:abc |
| `enabled` | True |
| `ok` | True |
| `escc_0x2ab_bus0` | 12 |
| `carrotMan_updates` | 4 |
| `navInstructionCarrot_updates` | 2 |
| `cplink_updates_seen` | True |
| `cplink_speed_limit_seen` | True |
| `cplink_sdi_seen` | False |
| `cplink_tbt_seen` | True |
| `cplink_gps_seen` | False |
| `cplink_lanechange_cmd_seen` | False |
| `CarParamsDecoded` | ok |
| `carName` | hyundai |
| `carFingerprint` | KIA_SELTOS_2023 |
| `fingerprintSource` | fixed |
| `networkLocation` | fwdCamera |
| `safetyConfigs` | hyundaiLegacy:1024 |
| `spFlags` | 1 |
"""
  validate_log(good_log)
  validate_snapshot_text("self-test snapshot", good_snapshot)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_escc_sample=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_cplink_sample=True)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_carparams=True)

  with tempfile.TemporaryDirectory() as tmp:
    bundle = Path(tmp)
    (bundle / "road-test-log-draft.md").write_text(good_log, encoding="utf-8")
    (bundle / "device-snapshot.md").write_text(good_snapshot, encoding="utf-8")
    (bundle / "manifest.json").write_text('{"static_check_exit_code": 0}\n', encoding="utf-8")
    bundle_log, bundle_snapshots = collect_evidence_inputs(None, [], [str(bundle)])
    if not bundle_log or len(bundle_snapshots) != 1:
      raise EvidenceError("self-test failed: evidence bundle was not discovered")
    validate_log(read_text(bundle_log)[1])
    validate_snapshots(
      bundle_snapshots,
      require_device_snapshot=True,
      require_escc_sample=True,
      require_cplink_sample=True,
      require_carparams=True,
    )

  try:
    validate_log(good_log.replace("ESCC 0x2AB observed: PASS", "ESCC 0x2AB observed: PENDING"))
  except EvidenceError:
    pass
  else:
    raise EvidenceError("self-test failed: missing PASS line was accepted")


def validate_snapshots_from_text(
  items: Sequence[Tuple[str, str]],
  require_escc_sample: bool = False,
  require_cplink_sample: bool = False,
  require_carparams: bool = False,
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
  return snapshots


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate real-car evidence before promoting a personal C3 ESCC tag.")
  parser.add_argument("--road-test-log", help="completed road-test markdown log")
  parser.add_argument("--device-snapshot", action="append", default=[], help="privacy-safe snapshot generated on the C3; may be repeated")
  parser.add_argument("--evidence-dir", action="append", default=[], help="unpacked folder generated by collect_real_car_evidence.py; may be repeated")
  parser.add_argument("--require-device-snapshot", action="store_true", help="fail when no device snapshot is supplied")
  parser.add_argument("--require-escc-sample", action="store_true", help="require EnableEscc=1 and sampled 0x2AB bus0 count > 0")
  parser.add_argument("--require-cplink-sample", action="store_true", help="require a sampled CP搭子/Navipilot update with speed/TBT/SDI/GPS data")
  parser.add_argument("--require-carparams-summary", action="store_true", help="require a decoded Seltos CarParams summary")
  parser.add_argument("--self-test", action="store_true", help="run built-in parser checks")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("OK: road-test evidence checker self-test passed")
      return 0

    road_test_log, snapshot_paths = collect_evidence_inputs(args.road_test_log, args.device_snapshot, args.evidence_dir)
    if not road_test_log:
      raise EvidenceError("--road-test-log or --evidence-dir is required unless --self-test is used")

    log_path, log_text = read_text(road_test_log)
    fields = validate_log(log_text)
    snapshots = validate_snapshots(
      snapshot_paths,
      args.require_device_snapshot,
      args.require_escc_sample,
      args.require_cplink_sample,
      args.require_carparams_summary,
    )

    print("Road-test evidence check")
    print(f"repo: {ROOT}")
    print(f"road-test log: {log_path}")
    if args.evidence_dir:
      print("evidence dirs checked: " + str(len(args.evidence_dir)))
    print(f"vehicle: {fields.get('车辆')}")
    print(f"tag: {fields.get('tag')}")
    print(f"device snapshots checked: {len(snapshots)}")
    if args.require_escc_sample:
      print("ESCC sample: required and present")
    if args.require_cplink_sample:
      print("CPlink sample: required and present")
    if args.require_carparams_summary:
      print("CarParams summary: required and present")
    print("OK: road-test evidence is sufficient for the requested gate")
    return 0
  except EvidenceError as exc:
    print("road-test evidence check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
