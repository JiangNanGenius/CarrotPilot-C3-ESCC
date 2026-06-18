#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "selfdrive/carrot_settings.json"
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")


REQUIRED_DESCRIPTIONS = {
  "LateralTorqueFriction": ["转向摩擦补偿", "抖动", "0-50"],
  "CruiseOnDist": ["松开油门", "前车距离", "0 表示不使用"],
  "CruiseEcoControl": ["平顺", "节能", "实车验证"],
  "StopDistanceCarrot": ["目标停车距离", "前车", "停止点"],
  "AChangeCostStarting": ["起步加速代价", "起步越快", "柔和"],
  "CruiseSpeedUnitBasic": ["巡航按键", "基础步进"],
  "AlwaysOffline": ["离线", "注册", "更新", "远程连接"],
  "EnableConnect": ["注册", "远程连接", "克隆 C3", "默认关闭", "重启"],
  "EnableEscc": ["ESCC", "纯 CAN", "0x2AB"],
  "HyundaiCameraSCC": ["Seltos 2023", "纯 CAN", "保持 0"],
  "CanfdHDA2": ["CANFD", "Seltos 2023", "保持 0"],
  "IsLdwsCar": ["LDWS", "LFA/LKAS", "保持 0"],
  "EnableRadarTracks": ["Seltos 2023", "0x2AB", "-2", "-1", "0", "1", "2", "3"],
  "RadarLatFactor": ["误判", "前车"],
  "EnableCornerRadar": ["角雷达", "保持 0"],
  "SoftwareMenu": ["软件/服务", "内存", "异常重启"],
  "MuteDoor": ["信号异常", "建议关闭"],
  "MuteSeatbelt": ["信号异常", "建议关闭"],
  "CarrotLearningActive": ["建议值", "不会自动修改"],
  "CarrotLearningAutoApply": ["不建议", "默认关闭"],
  "ShowRadarInfo": ["仅影响屏幕显示", "不改变雷达或纵控逻辑"],
  "ShowRouteInfo": ["CP搭子", "导航", "0", "1"],
  "ModelTurnSpeedFactor": ["0.1 秒", "0 表示不使用"],
  "AutoNaviSpeedDecelRate": ["0.01m/s²", "越早", "越晚"],
  "EnableAmapNaviStatus": ["默认关闭", "车道线", "原车盲区", "不接收 APP 命令", "不启用自动超车"],
  "ClusterHud": ["默认关闭", "外接", "manager"],
  "ClusterHudEncoder": ["自动", "硬件 H264", "JPEG"],
  "ClusterHudLiveFps": ["C3", "10 FPS"],
  "ClusterHudPriority": ["1-99", "影响其它进程"],
  "ShowModelView": ["C4", "C3", "默认"],
  "HapticFeedbackWhenSpeedCamera": ["对应硬件", "0", "3"],
  "CarrotCruiseDecel": ["Carrot 巡航", "-1"],
  "CarrotCruiseAtcDecel": ["ATC", "Carrot 巡航", "-1"],
  "LongTuningKpV": ["比例增益", "现代/起亚"],
  "LongTuningKf": ["前馈", "现代/起亚"],
  "LongTuningKiV": ["积分增益", "保持 0"],
  "LongActuatorDelay": ["执行器延迟", "现代/起亚"],
  "AutoTurnControl": ["自动变道", "转弯控速", "需要导航"],
  "AutoTurnControlSpeedTurn": ["目标速度", "0 表示不使用"],
  "AutoTurnControlTurnEnd": ["当前速度", "越早退出"],
  "AutoTurnMapChange": ["只影响显示", "不改变控制逻辑"],
  "CruiseButtonTest1": ["非纵向控制", "按键信号"],
  "CruiseButtonTest2": ["非纵向控制", "暂停"],
  "CruiseButtonTest3": ["非纵向控制", "次数"],
  "PaddleMode": ["动能回收拨片", "Carrot 巡航"],
  "AutoGasTokSpeed": ["轻点油门", "0.6 秒"],
  "HDPuse": ["HDP/CCNC", "保持 0"],
  "DisableMinSteerSpeed": ["S-MDPS", "低速转向"],
  "MaxTimeOffroadMin": ["ACC/CAN", "先断电"],
  "DisableDM": ["驾驶员监控", "WebRTC"],
  "AutoRoadSpeedAdjust": ["道路限速", "当前巡航目标"],
  "ShowPathMode": ["仅影响显示", "箭头样式"],
  "ShowPathColor": ["仅影响显示", "20 自动"],
  "ShowPathModeLane": ["仅影响显示", "箭头样式"],
  "ShowPathColorLane": ["仅影响显示", "20 自动"],
  "LaneLineCheck": ["黄线", "实线", "转向力矩"],
  "HotspotOnBoot": ["USIM", "保持关闭"],
  "TFollowGap1": ["时间间隔", "跟车越远"],
  "TFollowGap2": ["时间间隔", "跟车越远"],
  "TFollowGap3": ["时间间隔", "跟车越远"],
  "TFollowGap4": ["时间间隔", "跟车越远"],
  "DynamicTFollow": ["动态调整", "跟车时间"],
  "EnableSpeedTF": ["车速分段", "100km/h"],
  "DynamicTFollowLC": ["变道开始", "临时缩短"],
  "TFollowDecelBoost": ["减速", "跟车时间"],
  "AutoCurveSpeedLowerLimit": ["自动弯道减速", "最低速度", "后车"],
  "MyDrivingMode": ["纵向控制", "普通", "路测"],
  "TrafficLightDetectMode": ["红绿灯", "停车起步", "识别稳定"],
}


REQUIRED_CN_FIELDS = [
  "PathOffset",
  "CameraYawTrimDeg",
  "LateralTorqueFriction",
  "LatSuspendAngleDeg",
  "CruiseOnDist",
  "CruiseEcoControl",
  "StopDistanceCarrot",
  "AChangeCostStarting",
  "CruiseSpeedUnitBasic",
  "TrafficStopDistanceAdjust",
  "AlwaysOffline",
  "EnableConnect",
  "IsLdwsCar",
  "SoftwareMenu",
  "AutoCurveSpeedLowerLimit",
  "MyDrivingMode",
  "TrafficLightDetectMode",
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
  "EnableAmapNaviStatus",
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
  "CarrotCruiseDecel",
  "CarrotCruiseAtcDecel",
  "LongTuningKpV",
  "LongTuningKf",
  "LongTuningKiV",
  "LongActuatorDelay",
  "AutoTurnControl",
  "AutoTurnControlSpeedTurn",
  "AutoTurnControlTurnEnd",
  "AutoTurnMapChange",
  "LfaButtonMode",
  "CruiseButtonTest1",
  "CruiseButtonTest2",
  "CruiseButtonTest3",
  "PaddleMode",
  "AutoGasTokSpeed",
  "HDPuse",
  "DisableMinSteerSpeed",
  "MaxTimeOffroadMin",
  "DisableDM",
  "AutoRoadSpeedAdjust",
  "ShowPathMode",
  "ShowPathColor",
  "ShowPathModeLane",
  "ShowPathColorLane",
  "LaneLineCheck",
  "HotspotOnBoot",
  "TFollowGap1",
  "TFollowGap2",
  "TFollowGap3",
  "TFollowGap4",
  "DynamicTFollow",
  "EnableSpeedTF",
  "DynamicTFollowLC",
  "TFollowDecelBoost",
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
