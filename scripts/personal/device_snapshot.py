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
  "RadarLatFactor",
  "EnableCornerRadar",
  "CarrotLearningActive",
  "CarrotLearningAutoApply",
  "CarrotTunerApplyLat",
  "CarrotTunerApplyLong",
  "CarrotLearningPopupReady",
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


def run(cmd: Sequence[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
  proc = subprocess.run(
    list(cmd),
    cwd=str(cwd or ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  return proc.returncode, proc.stdout.strip()


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


def process_snapshot() -> List[str]:
  code, output = run(["ps", "-A"])
  if code != 0:
    return ["<ps unavailable>"]
  patterns = [
    r"(^|[ /])manager(\.py)?($|[ \t])",
    r"(^|[ /])controlsd(\.py)?($|[ \t])",
    r"(^|[ /])plannerd(\.py)?($|[ \t])",
    r"(^|[ /])radard(\.py)?($|[ \t])",
    r"(^|[ /])carrot_man(\.py)?($|[ \t])",
    r"(^|[ /])carrot_server(\.py)?($|[ \t])",
    r"(^|[ /])updated(\.py)?($|[ \t])",
    r"(^|[ /])manage_athenad($|[ \t])",
    r"(^|[ /])uploader($|[ \t])",
  ]
  lines = []
  for line in output.splitlines():
    if "py_compile" in line or "device_snapshot.py" in line:
      continue
    if any(re.search(pattern, line) for pattern in patterns):
      lines.append(line.strip())
  return lines or ["<no matching processes>"]


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
    "last_carrotMan": {},
  }
  if seconds <= 0:
    return result

  try:
    import cereal.messaging as messaging  # type: ignore
  except Exception as exc:
    result["error"] = f"cannot import cereal.messaging: {exc}"
    return result

  try:
    sm = messaging.SubMaster(["can", "carrotMan", "navInstructionCarrot"])
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
        msg = sm["carrotMan"]
        result["last_carrotMan"] = {
          "nRoadLimitSpeed": getattr(msg, "nRoadLimitSpeed", None),
          "xSpdType": getattr(msg, "xSpdType", None),
          "xTurnInfo": getattr(msg, "xTurnInfo", None),
          "carrotCmd": getattr(msg, "carrotCmd", None),
        }
      if sm.updated.get("navInstructionCarrot", False):
        result["navInstructionCarrot_updates"] = int(result["navInstructionCarrot_updates"]) + 1
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
  lines.append("## Process Snapshot")
  for line in process_snapshot():
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
