#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]

SAFE_PARAM_KEYS = [
  "AlwaysOffline",
  "DisableUpdates",
  "EnableConnect",
  "EnableEscc",
  "HyundaiCameraSCC",
  "CanfdHDA2",
  "EnableRadarTracks",
  "EnableRadarTracksResult",
  "EnableAmapNaviStatus",
  "RadarLatFactor",
  "EnableCornerRadar",
  "CarrotLearningActive",
  "CarrotLearningAutoApply",
  "CarrotTunerApplyLat",
  "CarrotTunerApplyLong",
  "CarrotLearningPopupReady",
  "DrivingModelName",
  "PendingModelName",
  "IsOnroad",
  "Passive",
  "CompletedTrainingVersion",
  "DisengageOnAccelerator",
  "AutoGasCancelSpeed",
]

BINARY_PARAM_KEYS = [
  "CarParams",
  "CarParamsCache",
]

PARAM_ROOTS = [
  Path("/data/params/d"),
  Path("/data/params"),
  Path("/persist/comma/params/d"),
]

PROCESS_PATTERNS = {
  "manager_process_seen": r"(^|[ /])manager(\.py)?($|[ \t])",
  "controlsd_process_seen": r"(^|[ /])controlsd(\.py)?($|[ \t])",
  "plannerd_process_seen": r"(^|[ /])plannerd(\.py)?($|[ \t])",
  "radard_process_seen": r"(^|[ /])radard(\.py)?($|[ \t])",
  "carrot_man_process_seen": r"(^|[ /])carrot_man(\.py)?($|[ \t])",
  "carrot_server_process_seen": r"(^|[ /])carrot_server(\.py)?($|[ \t])",
  "updated_process_seen": r"(^|[ /])updated(\.py)?($|[ \t])",
  "connect_process_seen": r"(^|[ /])(manage_athenad|athenad)($|[ \t])",
  "uploader_process_seen": r"(^|[ /])uploader($|[ \t])",
}

OFFLINE_FORBIDDEN_PROCESS_KEYS = [
  "updated_process_seen",
  "connect_process_seen",
  "uploader_process_seen",
]

MODEL_SELECTOR_STATUS_FILE = Path("/data/model_selector_status")


def run(cmd: Sequence[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=str(cwd or ROOT),
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout.strip()
  except OSError as exc:
    return 127, f"{cmd[0]} unavailable: {exc}"


def git_value(args: Sequence[str]) -> str:
  code, output = run(["git", *args])
  return output if code == 0 and output else "unknown"


def read_param_file(key: str) -> Optional[Path]:
  for root in PARAM_ROOTS:
    path = root / key
    if path.exists() and path.is_file():
      return path
  return None


def sanitize_param_value(data: bytes) -> str:
  if not data:
    return ""
  if len(data) > 512:
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f"<large value: {len(data)} bytes, sha256:{digest}>"
  try:
    text = data.decode("utf-8", errors="strict")
  except UnicodeDecodeError:
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f"<binary value: {len(data)} bytes, sha256:{digest}>"
  text = text.replace("\x00", "").strip()
  if len(text) > 200:
    return text[:200] + "...<truncated>"
  return text


def read_safe_params() -> Dict[str, str]:
  values: Dict[str, str] = {}
  for key in SAFE_PARAM_KEYS:
    path = read_param_file(key)
    if path is None:
      values[key] = "<missing>"
      continue
    values[key] = sanitize_param_value(path.read_bytes())
  return values


def read_binary_param_summaries() -> Dict[str, str]:
  values: Dict[str, str] = {}
  for key in BINARY_PARAM_KEYS:
    path = read_param_file(key)
    if path is None:
      values[key] = "<missing>"
      continue
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()[:16]
    values[key] = f"{len(data)} bytes, sha256:{digest}"
  return values


def param_is_present(value: object) -> bool:
  text = safe_text(value).strip()
  return bool(text) and not text.startswith("<missing")


def read_model_selector_status(safe_params: Dict[str, str]) -> Dict[str, object]:
  status: Dict[str, object] = {
    "model_selector_status_available": False,
    "model_selector_status_path": str(MODEL_SELECTOR_STATUS_FILE),
    "model_selector_engine": "default_upstream_assumed",
    "model_selector_custom_active": False,
    "model_selector_pending_active": param_is_present(safe_params.get("PendingModelName")),
    "model_selector_current_model": safe_params.get("DrivingModelName", "<missing>"),
    "model_selector_pending_model": safe_params.get("PendingModelName", "<missing>"),
    "model_selector_pid": "",
    "model_selector_started": "",
    "model_selector_describe": "status file missing; default upstream modeld assumed",
  }
  if not MODEL_SELECTOR_STATUS_FILE.exists() or not MODEL_SELECTOR_STATUS_FILE.is_file():
    return status

  try:
    raw = MODEL_SELECTOR_STATUS_FILE.read_text(encoding="utf-8", errors="replace")
  except OSError as exc:
    status["model_selector_status_error"] = str(exc)[:160]
    return status

  parsed: Dict[str, str] = {}
  for line in raw.splitlines():
    if "=" not in line:
      continue
    key, value = line.split("=", 1)
    parsed[key.strip()] = value.strip()

  engine = sanitize_param_value(parsed.get("engine", "").encode("utf-8"))
  describe = sanitize_param_value(parsed.get("describe", "").encode("utf-8"))
  status.update({
    "model_selector_status_available": True,
    "model_selector_engine": engine or "unknown",
    "model_selector_custom_active": engine == "carrot_modeld",
    "model_selector_pid": sanitize_param_value(parsed.get("pid", "").encode("utf-8")),
    "model_selector_started": sanitize_param_value(parsed.get("started", "").encode("utf-8")),
    "model_selector_describe": describe or "<missing>",
  })
  return status


def enum_name(value: object) -> str:
  try:
    return str(value).split(".")[-1]
  except Exception:
    return str(value)


def read_binary_param(key: str) -> Optional[bytes]:
  path = read_param_file(key)
  if path is None:
    return None
  return path.read_bytes()


def summarize_car_params() -> Dict[str, object]:
  data = read_binary_param("CarParams")
  if data is None:
    return {"CarParamsDecoded": "<missing>"}
  try:
    from cereal import car  # type: ignore
    cp = car.CarParams.from_bytes(data)
  except Exception as exc:
    return {
      "CarParamsDecoded": "error",
      "CarParamsDecodeError": str(exc)[:200],
    }

  safety_configs: List[str] = []
  try:
    for cfg in cp.safetyConfigs:
      model = enum_name(safe_attr(cfg, "safetyModel"))
      param = safe_int(safe_attr(cfg, "safetyParam"))
      safety_configs.append(f"{model}:{param}")
  except Exception:
    safety_configs = []

  return {
    "CarParamsDecoded": "ok",
    "carName": safe_text(safe_attr(cp, "carName")),
    "carFingerprint": safe_text(safe_attr(cp, "carFingerprint")),
    "fingerprintSource": enum_name(safe_attr(cp, "fingerprintSource")),
    "networkLocation": enum_name(safe_attr(cp, "networkLocation")),
    "openpilotLongitudinalControl": bool(safe_attr(cp, "openpilotLongitudinalControl", False)),
    "pcmCruise": bool(safe_attr(cp, "pcmCruise", False)),
    "dashcamOnly": bool(safe_attr(cp, "dashcamOnly", False)),
    "flags": safe_int(safe_attr(cp, "flags")),
    "spFlags": safe_int(safe_attr(cp, "spFlags")),
    "safetyConfigs": ", ".join(safety_configs) if safety_configs else "<none>",
    "carFwCount": safe_len(safe_attr(cp, "carFw", [])),
  }


def process_snapshot() -> List[str]:
  code, output = run(["ps", "-A"])
  if code != 0:
    return ["<ps unavailable>"]
  lines = []
  for line in output.splitlines():
    if "py_compile" in line or "device_snapshot.py" in line:
      continue
    if any(re.search(pattern, line) for pattern in PROCESS_PATTERNS.values()):
      lines.append(line.strip())
  return lines or ["<no matching processes>"]


def process_diagnostics(lines: Sequence[str]) -> Dict[str, object]:
  text = "\n".join(lines)
  available = "<ps unavailable>" not in text
  values: Dict[str, object] = {"process_snapshot_available": available}
  for key, pattern in PROCESS_PATTERNS.items():
    values[key] = available and bool(re.search(pattern, text))
  values["offline_forbidden_processes_seen"] = any(bool(values[key]) for key in OFFLINE_FORBIDDEN_PROCESS_KEYS)
  return values


def safe_attr(obj: object, name: str, default: object = None) -> object:
  try:
    return getattr(obj, name, default)
  except Exception:
    return default


def safe_int(value: object, default: int = 0) -> int:
  try:
    return int(value)  # type: ignore[arg-type]
  except Exception:
    return default


def safe_float(value: object, default: float = 0.0) -> float:
  try:
    return float(value)  # type: ignore[arg-type]
  except Exception:
    return default


def safe_text(value: object) -> str:
  try:
    return str(value or "")
  except Exception:
    return ""


def safe_len(value: object) -> int:
  try:
    return len(value)  # type: ignore[arg-type]
  except Exception:
    return 0


def update_cplink_diagnostics(result: Dict[str, object], carrot_msg: object) -> None:
  road_limit = safe_int(safe_attr(carrot_msg, "nRoadLimitSpeed"))
  x_spd_type = safe_int(safe_attr(carrot_msg, "xSpdType"), -1)
  x_spd_dist = safe_int(safe_attr(carrot_msg, "xSpdDist"))
  x_turn_info = safe_int(safe_attr(carrot_msg, "xTurnInfo"), -1)
  x_dist_to_turn = safe_int(safe_attr(carrot_msg, "xDistToTurn"))
  carrot_cmd = safe_text(safe_attr(carrot_msg, "carrotCmd")).strip()
  lat = safe_float(safe_attr(carrot_msg, "xPosLat"))
  lon = safe_float(safe_attr(carrot_msg, "xPosLon"))

  result["cplink_updates_seen"] = True
  if road_limit > 0:
    result["cplink_speed_limit_seen"] = True
  if x_spd_type >= 0 or x_spd_dist > 0:
    result["cplink_sdi_seen"] = True
  if x_turn_info > 0 or x_dist_to_turn > 0:
    result["cplink_tbt_seen"] = True
  if abs(lat) > 0.0001 and abs(lon) > 0.0001:
    result["cplink_gps_seen"] = True
  if carrot_cmd == "LANECHANGE":
    result["cplink_lanechange_cmd_seen"] = True

  result["last_carrotMan"] = {
    "activeCarrot": safe_int(safe_attr(carrot_msg, "activeCarrot")),
    "nRoadLimitSpeed": road_limit,
    "xSpdType": x_spd_type,
    "xSpdLimit": safe_int(safe_attr(carrot_msg, "xSpdLimit")),
    "xSpdDist": x_spd_dist,
    "xTurnInfo": x_turn_info,
    "xDistToTurn": x_dist_to_turn,
    "carrotCmdIndex": safe_int(safe_attr(carrot_msg, "carrotCmdIndex")),
    "carrotCmd": carrot_cmd,
    "trafficState": safe_int(safe_attr(carrot_msg, "trafficState")),
  }


def update_nav_instruction_diagnostics(result: Dict[str, object], nav_msg: object) -> None:
  maneuver_distance = safe_float(safe_attr(nav_msg, "maneuverDistance"))
  speed_limit = safe_float(safe_attr(nav_msg, "speedLimit"))
  maneuver_type = safe_text(safe_attr(nav_msg, "maneuverType")).strip()
  maneuver_modifier = safe_text(safe_attr(nav_msg, "maneuverModifier")).strip()

  result["cplink_updates_seen"] = True
  if speed_limit > 0:
    result["cplink_speed_limit_seen"] = True
  if maneuver_distance > 0 or maneuver_type not in {"", "invalid"}:
    result["cplink_tbt_seen"] = True

  result["last_navInstructionCarrot"] = {
    "maneuverDistance": round(maneuver_distance, 1),
    "maneuverType": maneuver_type,
    "maneuverModifier": maneuver_modifier,
    "distanceRemaining": round(safe_float(safe_attr(nav_msg, "distanceRemaining")), 1),
    "timeRemaining": round(safe_float(safe_attr(nav_msg, "timeRemaining")), 1),
    "speedLimit": round(speed_limit, 2),
  }


def update_amap_navi_diagnostics(result: Dict[str, object], amap_msg: object) -> None:
  left_blind = safe_int(safe_attr(amap_msg, "leftBlind"))
  right_blind = safe_int(safe_attr(amap_msg, "rightBlind"))
  line_valid = bool(safe_attr(amap_msg, "lineValid", False))
  left_line = safe_int(safe_attr(amap_msg, "leftLine"), -1)
  right_line = safe_int(safe_attr(amap_msg, "rightLine"), -1)

  result["amap_navi_updates_seen"] = True
  if line_valid or left_line >= 0 or right_line >= 0:
    result["amap_navi_lane_seen"] = True
  if left_blind != 0:
    result["amap_navi_left_blind_seen"] = True
  if right_blind != 0:
    result["amap_navi_right_blind_seen"] = True

  result["last_amapNavi"] = {
    "leftBlind": left_blind,
    "rightBlind": right_blind,
    "lineValid": line_valid,
    "leftLine": left_line,
    "rightLine": right_line,
  }


def sample_messaging(seconds: int) -> Dict[str, object]:
  result: Dict[str, object] = {
    "enabled": seconds > 0,
    "seconds": seconds,
    "ok": False,
    "error": "",
    "can_messages": 0,
    "escc_0x2ab_bus0": 0,
    "escc_0x2ab_all_buses": 0,
    "carrotMan_updates": 0,
    "navInstructionCarrot_updates": 0,
    "amapNavi_updates": 0,
    "cplink_updates_seen": False,
    "cplink_speed_limit_seen": False,
    "cplink_sdi_seen": False,
    "cplink_tbt_seen": False,
    "cplink_gps_seen": False,
    "cplink_lanechange_cmd_seen": False,
    "amap_navi_updates_seen": False,
    "amap_navi_lane_seen": False,
    "amap_navi_left_blind_seen": False,
    "amap_navi_right_blind_seen": False,
    "last_carrotMan": {},
    "last_navInstructionCarrot": {},
    "last_amapNavi": {},
  }
  if seconds <= 0:
    return result

  try:
    import cereal.messaging as messaging  # type: ignore
  except Exception as exc:
    result["error"] = f"cannot import cereal.messaging: {exc}"
    return result

  try:
    sm = messaging.SubMaster(["can", "carrotMan", "navInstructionCarrot", "amapNavi"])
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
      sm.update(100)
      if sm.updated.get("can", False):
        for can_msg in sm["can"]:
          result["can_messages"] = int(result["can_messages"]) + 1
          if getattr(can_msg, "address", None) == 0x2AB:
            result["escc_0x2ab_all_buses"] = int(result["escc_0x2ab_all_buses"]) + 1
            if getattr(can_msg, "src", None) == 0:
              result["escc_0x2ab_bus0"] = int(result["escc_0x2ab_bus0"]) + 1
      if sm.updated.get("carrotMan", False):
        result["carrotMan_updates"] = int(result["carrotMan_updates"]) + 1
        update_cplink_diagnostics(result, sm["carrotMan"])
      if sm.updated.get("navInstructionCarrot", False):
        result["navInstructionCarrot_updates"] = int(result["navInstructionCarrot_updates"]) + 1
        update_nav_instruction_diagnostics(result, sm["navInstructionCarrot"])
      if sm.updated.get("amapNavi", False):
        result["amapNavi_updates"] = int(result["amapNavi_updates"]) + 1
        update_amap_navi_diagnostics(result, sm["amapNavi"])
    result["ok"] = True
  except Exception as exc:
    result["error"] = str(exc)
  return result


def markdown_table(items: Dict[str, object]) -> List[str]:
  lines = ["| Key | Value |", "| --- | --- |"]
  for key in sorted(items):
    value = str(items[key]).replace("\n", "<br>")
    lines.append(f"| `{key}` | {value} |")
  return lines


def build_report(sample_seconds: int) -> str:
  now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
  safe_params = read_safe_params()
  binary_params = read_binary_param_summaries()
  model_selector = read_model_selector_status(safe_params)
  car_params = summarize_car_params()
  processes = process_snapshot()
  process_summary = process_diagnostics(processes)
  sample = sample_messaging(sample_seconds)

  lines: List[str] = []
  lines.append("# CarrotPilot-C3-ESCC Device Snapshot")
  lines.append("")
  lines.append("This snapshot intentionally avoids VIN, dongle id, tokens, and route identifiers.")
  lines.append("")
  lines.append("## Build")
  lines.extend(markdown_table({
    "timestamp": now,
    "repo": str(ROOT),
    "branch": git_value(["branch", "--show-current"]),
    "commit": git_value(["rev-parse", "--short=12", "HEAD"]),
    "tags": git_value(["tag", "--points-at", "HEAD"]),
    "status": git_value(["status", "--short"]),
  }))
  lines.append("")
  lines.append("## Device")
  lines.extend(markdown_table({
    "platform": platform.platform(),
    "python": sys.version.split()[0],
    "cwd": os.getcwd(),
  }))
  lines.append("")
  lines.append("## Safe Params")
  lines.extend(markdown_table(safe_params))
  lines.append("")
  lines.append("## Binary Param Summaries")
  lines.extend(markdown_table(binary_params))
  lines.append("")
  lines.append("## Model Selector Status")
  lines.extend(markdown_table(model_selector))
  lines.append("")
  lines.append("## CarParams Summary")
  lines.extend(markdown_table(car_params))
  lines.append("")
  lines.append("## Process Summary")
  lines.extend(markdown_table(process_summary))
  lines.append("")
  lines.append("## Process Snapshot")
  for line in processes:
    lines.append(f"- `{line}`")
  lines.append("")
  lines.append("## Messaging Sample")
  lines.extend(markdown_table(sample))
  lines.append("")
  lines.append("## Manual Notes")
  lines.append("- Car selected on device:")
  lines.append("- ESCC 0x2AB visible in CAN tool: yes/no")
  lines.append("- SCC/AEB/FCW warning on dash: yes/no")
  lines.append("- ACC/CAN power-cycle boot result:")
  lines.append("- CPlink/Navipilot app connection result:")
  lines.append("")
  return "\n".join(lines) + "\n"


def main() -> int:
  parser = argparse.ArgumentParser(description="Collect a privacy-safe on-device validation snapshot.")
  parser.add_argument("--sample-seconds", type=int, default=0, help="sample live messaging for CAN/CarrotMan counts")
  parser.add_argument("--output", help="write markdown report to this path")
  args = parser.parse_args()

  report = build_report(max(args.sample_seconds, 0))
  if args.output:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"wrote {output}")
  else:
    print(report)
  return 0


if __name__ == "__main__":
  sys.exit(main())
