#!/usr/bin/env python3
import argparse
import json
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


def collect_navipilot_inputs(
  navipilot_live_checks: Sequence[str],
  evidence_dirs: Sequence[str],
) -> List[str]:
  return rtc.collect_navipilot_inputs(navipilot_live_checks, evidence_dirs)


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
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_carparams=False,
  )
  return f"validated snapshots: {len(snapshots)}"


def check_carparams(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_carparams=True,
  )
  return "decoded Seltos CarParams summary present"


def check_escc_sample(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=True,
    require_cplink_sample=False,
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_carparams=False,
  )
  return "EnableEscc=1 sample with escc_0x2ab_bus0 > 0 present"


def check_cplink_sample(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=True,
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_carparams=False,
  )
  return "CP搭子/Navipilot sampled navigation data present"


def check_amap_navi_sample(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_amap_navi_sample=True,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_carparams=False,
  )
  return "read-only AmapNavi status bridge sample present"


def check_model_selector_status(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_amap_navi_sample=False,
    require_model_selector_status_flag=True,
    require_offroad_update_guard_flag=False,
    require_carparams=False,
  )
  return "read-only model selector status captured with no pending model install"


def check_offroad_update_guard(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=True,
    require_carparams=False,
  )
  return "AlwaysOffroad keeps the device offroad while local Web/update services stay visible"


def check_default_connect_guard(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_default_connect_guard_flag=True,
    require_carparams=False,
  )
  return "default boot uses AlwaysOffroad=0, EnableConnect=0, and no connect/uploader process"


def check_power_cycle_boot(snapshot_paths: Sequence[str]) -> str:
  rtc.validate_snapshots(
    snapshot_paths,
    require_device_snapshot=True,
    require_escc_sample=False,
    require_cplink_sample=False,
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_carparams=False,
    require_power_cycle_boot_flag=True,
  )
  return "ACC/CAN power-cycle boot confirmation matches the snapshot commit"


def check_navipilot_live(navipilot_paths: Sequence[str]) -> str:
  reports = rtc.validate_navipilot_live_checks(navipilot_paths, require_navipilot_live_check=True)
  return f"C3-side Navipilot endpoint check present: {len(reports)} report(s)"


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
    require_amap_navi_sample=False,
    require_model_selector_status_flag=False,
    require_offroad_update_guard_flag=False,
    require_default_connect_guard_flag=True,
    require_carparams=True,
    require_power_cycle_boot_flag=True,
  )
  return "stable evidence gate requirements are satisfied"


def build_results(
  road_test_log: Optional[str],
  device_snapshots: Sequence[str],
  navipilot_live_checks: Sequence[str],
  evidence_dirs: Sequence[str],
) -> List[StageResult]:
  try:
    selected_log, snapshot_paths = collect_inputs(road_test_log, device_snapshots, evidence_dirs)
  except Exception as exc:
    selected_log, snapshot_paths = None, []
    input_error = str(exc)
  else:
    input_error = ""
  try:
    navipilot_paths = collect_navipilot_inputs(navipilot_live_checks, evidence_dirs)
  except Exception:
    navipilot_paths = []

  results = [
    stage_result("evidence inputs", True, lambda: (_raise(input_error) if input_error else check_inputs(selected_log, snapshot_paths))),
    stage_result("device snapshot", True, lambda: check_device_snapshot(snapshot_paths)),
    stage_result("CarParams summary", True, lambda: check_carparams(snapshot_paths)),
    stage_result("default boot/connect guard", True, lambda: check_default_connect_guard(snapshot_paths)),
    stage_result("ACC/CAN power-cycle boot", True, lambda: check_power_cycle_boot(snapshot_paths)),
    stage_result("ESCC 0x2AB sample", True, lambda: check_escc_sample(snapshot_paths)),
    stage_result("completed road-test log", True, lambda: check_road_log(selected_log)),
    stage_result("stable gate readiness", True, lambda: check_stable_ready(selected_log, snapshot_paths)),
    stage_result("AlwaysOffroad update/debug guard", False, lambda: check_offroad_update_guard(snapshot_paths)),
    stage_result("CP搭子/Navipilot sample", False, lambda: check_cplink_sample(snapshot_paths)),
    stage_result("AmapNavi status bridge sample", False, lambda: check_amap_navi_sample(snapshot_paths)),
    stage_result("Model selector status", False, lambda: check_model_selector_status(snapshot_paths)),
    stage_result("Navipilot live endpoint check", False, lambda: check_navipilot_live(navipilot_paths)),
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
C3 default boot/connect test: PASS
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
| `AlwaysOffroad` | 0 |
| `EnableConnect` | 0 |
| `SoftwareMenu` | 1 |
| `EnableEscc` | 1 |
| `CanfdHDA2` | 0 |
| `HyundaiCameraSCC` | 0 |
| `EnableAmapNaviStatus` | 1 |
| `DrivingModelName` | <missing> |
| `PendingModelName` | <missing> |
| `CarParams` | 200 bytes, sha256:abc |
| `PowerCycleBootOk` | 1 |
| `PowerCycleBootCommit` | abcdef123456 |
| `PowerCycleBootTag` | carrotpilot-c3-escc-20260618-test1 |
| `PowerCycleBootRecordedAt` | 2026-06-18T10:00:00+00:00 |
| `IsOnroad` | False |
| `process_snapshot_available` | True |
| `connect_forbidden_processes_seen` | False |
| `carrot_server_process_seen` | True |
| `updated_process_seen` | True |
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
  with tempfile.TemporaryDirectory() as tmp:
    bundle = Path(tmp)
    (bundle / "road-test-log-draft.md").write_text(good_log, encoding="utf-8")
    (bundle / "device-snapshot.md").write_text(good_snapshot, encoding="utf-8")
    (bundle / "navipilot-live-check.json").write_text(json.dumps(good_navipilot), encoding="utf-8")
    (bundle / "manifest.json").write_text('{"static_check_exit_code": 0}\n', encoding="utf-8")
    results = build_results(None, [], [], [str(bundle)])
    required_failures = [r for r in results if r.required_for_stable and not r.ok]
    if required_failures:
      raise rtc.EvidenceError("self-test failed: good bundle was not stable-ready")
    if not any(r.name == "Navipilot live endpoint check" and r.ok for r in results):
      raise rtc.EvidenceError("self-test failed: Navipilot endpoint check did not pass")
    if not any(r.name == "AmapNavi status bridge sample" and r.ok for r in results):
      raise rtc.EvidenceError("self-test failed: AmapNavi status bridge sample did not pass")
    if not any(r.name == "Model selector status" and r.ok for r in results):
      raise rtc.EvidenceError("self-test failed: model selector status did not pass")

    partial = Path(tmp) / "partial"
    partial.mkdir()
    (partial / "device-snapshot.md").write_text(good_snapshot.replace("| `escc_0x2ab_bus0` | 12 |", "| `escc_0x2ab_bus0` | 0 |"), encoding="utf-8")
    (partial / "manifest.json").write_text('{"static_check_exit_code": 0}\n', encoding="utf-8")
    partial_results = build_results(None, [], [], [str(partial)])
    if not any(r.name == "stable gate readiness" and not r.ok for r in partial_results):
      raise rtc.EvidenceError("self-test failed: partial bundle looked stable-ready")


def main() -> int:
  parser = argparse.ArgumentParser(description="Summarize which real-car evidence stages are ready before a stable tag.")
  parser.add_argument("--road-test-log", help="completed road-test markdown log")
  parser.add_argument("--device-snapshot", action="append", default=[], help="privacy-safe snapshot generated on the C3; may be repeated")
  parser.add_argument("--navipilot-live-check", action="append", default=[], help="JSON report from navipilot_live_check.py; may be repeated")
  parser.add_argument("--evidence-dir", action="append", default=[], help="unpacked collect_real_car_evidence.py folder; may be repeated")
  parser.add_argument("--fail-when-not-ready", action="store_true", help="exit non-zero when stable readiness is incomplete")
  parser.add_argument("--self-test", action="store_true", help="run built-in readiness checks")
  args = parser.parse_args()

  if args.self_test:
    self_test()
    print("OK: evidence readiness report self-test passed")
    return 0

  results = build_results(args.road_test_log, args.device_snapshot, args.navipilot_live_check, args.evidence_dir)
  print_results(results)
  stable_ready = all(r.ok for r in results if r.required_for_stable)
  return 2 if args.fail_when_not_ready and not stable_ready else 0


if __name__ == "__main__":
  raise SystemExit(main())
