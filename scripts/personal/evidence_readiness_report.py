#!/usr/bin/env python3
import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import road_test_evidence_check as rtc


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class StageResult:
  name: str
  ok: bool
  required_for_stable: bool
  detail: str


def stage_result(name: str, required_for_stable: bool, fn: Callable[[], str]) -> StageResult:
  try:
    detail = fn()
    return StageResult(name, True, required_for_stable, detail)
  except Exception as exc:
    return StageResult(name, False, required_for_stable, str(exc))


def collect_inputs(
  road_test_log: Optional[str],
  device_snapshots: Sequence[str],
  evidence_dirs: Sequence[str],
) -> Tuple[Optional[str], List[str]]:
  return rtc.collect_evidence_inputs(road_test_log, device_snapshots, evidence_dirs)


def check_inputs(road_test_log: Optional[str], snapshot_paths: Sequence[str]) -> str:
  pieces = []
  if road_test_log:
    pieces.append(f"road-test log: {road_test_log}")
  else:
    pieces.append("road-test log: missing")
  pieces.append(f"device snapshots: {len(snapshot_paths)}")
  if not road_test_log and not snapshot_paths:
    raise rtc.EvidenceError("no road-test log or device snapshot was found")
  return "; ".join(pieces)


def check_device_snapshot(snapshot_paths: Sequence[str]) -> str:
  snapshots = rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_carparams=False,
  )
  return f"validated snapshots: {len(snapshots)}"


def check_carparams(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_carparams=True,
  )
  return "decoded Seltos CarParams summary present"


def check_escc_sample(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=True,
    require_cplink_sample=False,
    require_carparams=False,
  )
  return "EnableEscc=1 sample with escc_0x2ab_bus0 > 0 present"


def check_cplink_sample(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=True,
    require_carparams=False,
  )
  return "CP搭子/Navipilot sampled navigation data present"


def check_road_log(road_test_log: Optional[str]) -> str:
  if not road_test_log:
    raise rtc.EvidenceError("road-test log is missing")
  log_path, log_text = rtc.read_text(road_test_log)
  fields = rtc.validate_log(log_text)
  return f"validated road-test log: {log_path}; tag={fields.get('tag')}"


def check_stable_ready(road_test_log: Optional[str], snapshot_paths: Sequence[str]) -> str:
  if not road_test_log:
    raise rtc.EvidenceError("stable gate needs a completed road-test log")
  _, log_text = rtc.read_text(road_test_log)
  rtc.validate_log(log_text)
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=True,
    require_cplink_sample=False,
    require_carparams=True,
  )
  return "stable evidence gate requirements are satisfied"


def build_results(
  road_test_log: Optional[str],
  device_snapshots: Sequence[str],
  evidence_dirs: Sequence[str],
) -> List[StageResult]:
  try:
    selected_log, snapshot_paths = collect_inputs(road_test_log, device_snapshots, evidence_dirs)
  except Exception as exc:
    selected_log, snapshot_paths = None, []
    input_error = str(exc)
  else:
    input_error = ""

  results = [
    stage_result("evidence inputs", True, lambda: (_raise(input_error) if input_error else check_inputs(selected_log, snapshot_paths))),
    stage_result("device snapshot", True, lambda: check_device_snapshot(snapshot_paths)),
    stage_result("CarParams summary", True, lambda: check_carparams(snapshot_paths)),
    stage_result("ESCC 0x2AB sample", True, lambda: check_escc_sample(snapshot_paths)),
    stage_result("completed road-test log", True, lambda: check_road_log(selected_log)),
    stage_result("stable gate readiness", True, lambda: check_stable_ready(selected_log, snapshot_paths)),
    stage_result("CP搭子/Navipilot sample", False, lambda: check_cplink_sample(snapshot_paths)),
  ]
  return results


def _raise(message: str) -> str:
  raise rtc.EvidenceError(message)


def print_results(results: Sequence[StageResult]) -> None:
  print("CarrotPilot-C3-ESCC evidence readiness report")
  print("repo:", ROOT)
  for result in results:
    if result.ok:
      state = "PASS"
    elif result.required_for_stable:
      state = "TODO"
    else:
      state = "OPTIONAL"
    print(f"[{state}] {result.name}: {result.detail}")

  missing = [r.name for r in results if r.required_for_stable and not r.ok]
  if missing:
    print("Stable readiness: NOT READY")
    print("Missing required stage(s): " + ", ".join(missing))
  else:
    print("Stable readiness: READY")


def self_test() -> None:
  good_log = """
# Test
- 日期：2026-06-18
- 设备：C3 中国克隆版
- 车辆：Kia Seltos 2023，纯 CAN
- 分支：personal/c3-escc-atune
- commit：abcdef123456
- tag：carrotpilot-c3-escc-20260618-test1
- 设备快照文件：device-snapshot.md
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
  with tempfile.TemporaryDirectory() as tmp:
    bundle = Path(tmp)
    (bundle / "road-test-log-draft.md").write_text(good_log, encoding="utf-8")
    (bundle / "device-snapshot.md").write_text(good_snapshot, encoding="utf-8")
    (bundle / "manifest.json").write_text('{"static_check_exit_code": 0}\n', encoding="utf-8")
    results = build_results(None, [], [str(bundle)])
    required_failures = [r for r in results if r.required_for_stable and not r.ok]
    if required_failures:
      raise rtc.EvidenceError("self-test failed: good bundle was not stable-ready")

    partial = Path(tmp) / "partial"
    partial.mkdir()
    (partial / "device-snapshot.md").write_text(good_snapshot.replace("| `escc_0x2ab_bus0` | 12 |", "| `escc_0x2ab_bus0` | 0 |"), encoding="utf-8")
    (partial / "manifest.json").write_text('{"static_check_exit_code": 0}\n', encoding="utf-8")
    partial_results = build_results(None, [], [str(partial)])
    if not any(r.name == "stable gate readiness" and not r.ok for r in partial_results):
      raise rtc.EvidenceError("self-test failed: partial bundle looked stable-ready")


def main() -> int:
  parser = argparse.ArgumentParser(description="Summarize which real-car evidence stages are ready before a stable tag.")
  parser.add_argument("--road-test-log", help="completed road-test markdown log")
  parser.add_argument("--device-snapshot", action="append", default=[], help="privacy-safe snapshot generated on the C3; may be repeated")
  parser.add_argument("--evidence-dir", action="append", default=[], help="unpacked collect_real_car_evidence.py folder; may be repeated")
  parser.add_argument("--fail-when-not-ready", action="store_true", help="exit non-zero when stable readiness is incomplete")
  parser.add_argument("--self-test", action="store_true", help="run built-in readiness checks")
  args = parser.parse_args()

  if args.self_test:
    self_test()
    print("OK: evidence readiness report self-test passed")
    return 0

  results = build_results(args.road_test_log, args.device_snapshot, args.evidence_dir)
  print_results(results)
  stable_ready = all(r.ok for r in results if r.required_for_stable)
  return 2 if args.fail_when_not_ready and not stable_ready else 0


if __name__ == "__main__":
  raise SystemExit(main())
