#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "selfdrive/carrot_settings.json"
HANGUL_RE = re.compile(r"[가-힣]")


REQUIRED_DESCRIPTIONS = {
  "AlwaysOffline": ["离线", "注册", "更新", "远程连接"],
  "EnableEscc": ["ESCC", "纯 CAN", "0x2AB"],
  "HyundaiCameraSCC": ["Seltos 2023", "纯 CAN", "保持 0"],
  "CanfdHDA2": ["CANFD", "Seltos 2023", "保持 0"],
  "EnableRadarTracks": ["-2", "-1", "0", "1", "2", "3"],
  "RadarLatFactor": ["误判", "前车"],
  "EnableCornerRadar": ["角雷达", "保持 0"],
  "MuteDoor": ["信号异常", "建议关闭"],
  "MuteSeatbelt": ["信号异常", "建议关闭"],
  "CarrotLearningActive": ["建议值", "不会自动修改"],
  "CarrotLearningAutoApply": ["不建议", "默认关闭"],
  "ShowRadarInfo": ["仅影响屏幕显示", "不改变雷达或纵控逻辑"],
  "ShowRouteInfo": ["CP搭子", "导航", "0", "1"],
  "ModelTurnSpeedFactor": ["0.1 秒", "0 表示不使用"],
  "AutoNaviSpeedDecelRate": ["0.01m/s²", "越早", "越晚"],
  "ClusterHud": ["默认关闭", "外接", "manager"],
  "ClusterHudEncoder": ["自动", "硬件 H264", "JPEG"],
  "ClusterHudLiveFps": ["C3", "10 FPS"],
  "ClusterHudPriority": ["1-99", "影响其它进程"],
  "ShowModelView": ["C4", "C3", "默认"],
  "HapticFeedbackWhenSpeedCamera": ["对应硬件", "0", "3"],
}


REQUIRED_CN_FIELDS = [
  "PathOffset",
  "CameraYawTrimDeg",
  "LatSuspendAngleDeg",
  "TrafficStopDistanceAdjust",
  "ShowDebugUI",
  "ShowPathEnd",
  "ShowDeviceState",
  "ShowRouteInfo",
  "ShowRadarInfo",
  "ShowPathColorCruiseOff",
  "CanfdDebug",
  "AutoNaviSpeedCtrlEnd",
  "AutoNaviSpeedCtrlMode",
  "AutoRoadSpeedLimitOffset",
  "AutoNaviSpeedBumpTime",
  "AutoNaviSpeedBumpSpeed",
  "AutoNaviSpeedDecelRate",
  "AutoNaviCountDownMode",
  "TurnSpeedControlMode",
  "MapTurnSpeedFactor",
  "ModelTurnSpeedFactor",
  "AutoNaviSpeedSafetyFactor",
  "ShowModelView",
  "ClusterHud",
  "ClusterHudDebug",
  "ClusterHudBrightness",
  "ClusterHudEncoder",
  "ClusterHudTheme",
  "ClusterHudLiveFps",
  "ClusterHudScreenMode",
  "ClusterHudRadarInfo",
  "ClusterHudRadarDisplay",
  "ClusterHudRadarSourceColor",
  "ClusterHudCoreMode",
  "ClusterHudPriority",
  "ClusterHudCameraViewMode",
  "HapticFeedbackWhenSpeedCamera",
]


def load_params() -> Dict[str, Dict[str, object]]:
  with SETTINGS.open("r", encoding="utf-8") as f:
    data = json.load(f)
  return {item["name"]: item for item in data.get("params", []) if item.get("name")}


def has_text(item: Dict[str, object], field: str) -> bool:
  return bool(str(item.get(field, "")).strip())


def main() -> int:
  params = load_params()
  failures: List[str] = []

  for name, item in params.items():
    for field in ("cgroup", "ctitle", "cdescr"):
      value = str(item.get(field, ""))
      if HANGUL_RE.search(value):
        failures.append(f"{name}.{field} contains Korean text")

  for name in REQUIRED_CN_FIELDS:
    item = params.get(name)
    if not item:
      failures.append(f"missing setting: {name}")
      continue
    for field in ("cgroup", "ctitle", "cdescr"):
      if not has_text(item, field):
        failures.append(f"{name}.{field} is empty")

  for name, needles in REQUIRED_DESCRIPTIONS.items():
    item = params.get(name)
    if not item:
      failures.append(f"missing setting: {name}")
      continue
    cdescr = str(item.get("cdescr", ""))
    if not cdescr.strip():
      failures.append(f"{name}.cdescr is empty")
      continue
    for needle in needles:
      if needle not in cdescr:
        failures.append(f"{name}.cdescr missing {needle!r}")

  print("Chinese settings audit")
  print("repo:", ROOT)
  print("checked params:", len(params))
  if failures:
    for failure in failures:
      print("[FAIL]", failure)
    return 1
  print("OK: selected Chinese setting descriptions are present and guarded")
  return 0


if __name__ == "__main__":
  sys.exit(main())
