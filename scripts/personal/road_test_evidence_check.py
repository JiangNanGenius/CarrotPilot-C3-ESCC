#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


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


def is_filled(value: str) -> bool:
  stripped = value.strip()
  return stripped not in EMPTY_MARKERS and not stripped.startswith("<missing")


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


def validate_snapshots(snapshot_paths: Sequence[str], require_device_snapshot: bool, require_escc_sample: bool) -> List[Dict[str, str]]:
  if require_device_snapshot and not snapshot_paths:
    raise EvidenceError("stable evidence requires at least one --device-snapshot copied from the C3")

  snapshots: List[Dict[str, str]] = []
  for path in snapshot_paths:
    resolved, text = read_text(path)
    snapshots.append(validate_snapshot_text(str(resolved), text))

  if require_escc_sample:
    found = False
    for values in snapshots:
      enable_escc = values.get("EnableEscc", "").strip() in TRUE_VALUES
      escc_bus0 = int_value(values, "escc_0x2ab_bus0")
      sample_enabled = values.get("enabled", "").strip() in TRUE_VALUES
      sample_ok = values.get("ok", "").strip() in TRUE_VALUES
      if enable_escc and sample_enabled and sample_ok and escc_bus0 > 0:
        found = True
        break
    if not found:
      raise EvidenceError("stable evidence requires a sampled snapshot with EnableEscc=1, enabled=True, ok=True, and escc_0x2ab_bus0 > 0")
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
"""
  validate_log(good_log)
  validate_snapshot_text("self-test snapshot", good_snapshot)
  validate_snapshots_from_text([("self-test snapshot", good_snapshot)], require_escc_sample=True)

  try:
    validate_log(good_log.replace("ESCC 0x2AB observed: PASS", "ESCC 0x2AB observed: PENDING"))
  except EvidenceError:
    pass
  else:
    raise EvidenceError("self-test failed: missing PASS line was accepted")


def validate_snapshots_from_text(items: Sequence[Tuple[str, str]], require_escc_sample: bool) -> List[Dict[str, str]]:
  snapshots = [validate_snapshot_text(name, text) for name, text in items]
  if require_escc_sample:
    found = False
    for values in snapshots:
      enable_escc = values.get("EnableEscc", "").strip() in TRUE_VALUES
      sample_enabled = values.get("enabled", "").strip() in TRUE_VALUES
      sample_ok = values.get("ok", "").strip() in TRUE_VALUES
      if enable_escc and sample_enabled and sample_ok and int_value(values, "escc_0x2ab_bus0") > 0:
        found = True
        break
    if not found:
      raise EvidenceError("self-test failed: ESCC sample was not detected")
  return snapshots


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate real-car evidence before promoting a personal C3 ESCC tag.")
  parser.add_argument("--road-test-log", help="completed road-test markdown log")
  parser.add_argument("--device-snapshot", action="append", default=[], help="privacy-safe snapshot generated on the C3; may be repeated")
  parser.add_argument("--require-device-snapshot", action="store_true", help="fail when no device snapshot is supplied")
  parser.add_argument("--require-escc-sample", action="store_true", help="require EnableEscc=1 and sampled 0x2AB bus0 count > 0")
  parser.add_argument("--self-test", action="store_true", help="run built-in parser checks")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("OK: road-test evidence checker self-test passed")
      return 0

    if not args.road_test_log:
      raise EvidenceError("--road-test-log is required unless --self-test is used")

    log_path, log_text = read_text(args.road_test_log)
    fields = validate_log(log_text)
    snapshots = validate_snapshots(args.device_snapshot, args.require_device_snapshot, args.require_escc_sample)

    print("Road-test evidence check")
    print(f"repo: {ROOT}")
    print(f"road-test log: {log_path}")
    print(f"vehicle: {fields.get('车辆')}")
    print(f"tag: {fields.get('tag')}")
    print(f"device snapshots checked: {len(snapshots)}")
    if args.require_escc_sample:
      print("ESCC sample: required and present")
    print("OK: road-test evidence is sufficient for the requested gate")
    return 0
  except EvidenceError as exc:
    print("road-test evidence check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
