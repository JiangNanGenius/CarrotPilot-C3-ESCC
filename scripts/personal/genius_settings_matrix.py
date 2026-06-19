#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX_MD = ROOT / "docs/personal/SETTINGS_MATRIX.md"
MATRIX_JSON = ROOT / "docs/personal/settings_matrix.json"


@dataclass(frozen=True)
class Reference:
  name: str
  ref: str
  category: str


REFERENCES = (
  Reference("ajouatom-carrot-wip", "refs/remotes/carrot-audit/ajouatom-carrot-wip", "carrot"),
  Reference("ajouatom-c3-wip", "refs/remotes/carrot-audit/ajouatom-c3-wip", "carrot-c3"),
  Reference("jixiexiaoge-atune", "refs/remotes/carrot-audit/jixiexiaoge-atune", "mechanical-atune"),
  Reference("jixiexiaoge-cp", "refs/remotes/carrot-audit/jixiexiaoge-cp", "mechanical-carrot"),
  Reference("jixiexiaoge-release-new", "refs/remotes/carrot-audit/jixiexiaoge-release-new", "mechanical-release"),
  Reference("dhvms-carrotpilot-master", "refs/remotes/carrot-audit/dhvms-carrotpilot-master", "escc"),
)

REFERENCE_TOKEN_CACHE: dict[str, set[str]] | None = None


@dataclass(frozen=True)
class MatrixRow:
  key: str
  owner: str
  category: str
  current_key: str | None
  default: str | None = None
  source_keys: tuple[str, ...] = field(default_factory=tuple)
  required_sources: tuple[str, ...] = field(default_factory=tuple)
  ui_surface: str = ""
  api: bool = False
  units: str = ""
  inverse_semantics: str = "no"
  consumer_tokens: tuple[str, ...] = field(default_factory=tuple)
  forbid_tokens: tuple[str, ...] = field(default_factory=tuple)
  notes: str = ""


MATRIX: tuple[MatrixRow, ...] = (
  MatrixRow("SunnylinkEnabled", "removed_cloud", "cloud", "SunnylinkEnabled", "0", ("SunnylinkEnabled",), notes="Param may remain for compatibility, but no UI or process may honor it."),
  MatrixRow("EnableSunnylinkUploader", "removed_cloud", "cloud", "EnableSunnylinkUploader", None, ("EnableSunnylinkUploader",), notes="Legacy Sunny uploader switch is inert; ui_state forces it back to false if an old value exists."),
  MatrixRow("OnroadUploads", "removed_cloud", "cloud", "OnroadUploads", "0", ("OnroadUploads",), notes="Uploader is removed; value cannot start upload code."),
  MatrixRow("EnableConnect", "removed_cloud", "cloud", None, None, ("EnableConnect",), notes="Do not reintroduce comma/OpenPilot cloud connect."),
  MatrixRow("OffroadMode", "local_network_update", "parked_power", "OffroadMode", None, ("OffroadMode", "AlwaysOffroad", "AlwaysOffline"), ui_surface="mici_offroad", notes="Only parked-maintenance mode. Local LAN remains available."),
  MatrixRow("DynamicExperimentalControl", "sunny_primitive", "longitudinal", "DynamicExperimentalControl", "0", ("DynamicExperimentalControl",), ui_surface="cruise+carrot", api=True, notes="Retain as Sunny DEC candidate, default off."),
  MatrixRow("IntelligentCruiseButtonManagement", "removed_sunny_conflict", "longitudinal", "IntelligentCruiseButtonManagement", None, ("IntelligentCruiseButtonManagement",), notes="Hidden/inert because Carrot owns cruise-button behavior."),
  MatrixRow("SmartCruiseControlVision", "removed_sunny_conflict", "speed", "SmartCruiseControlVision", "0", ("SmartCruiseControlVision",), notes="Hidden/inert because Carrot/Sunny curve selector owns curve behavior."),
  MatrixRow("SmartCruiseControlMap", "removed_sunny_conflict", "speed", "SmartCruiseControlMap", "0", ("SmartCruiseControlMap",), notes="Hidden/inert because Carrot map/phone/speed resolver owns map speed behavior."),
  MatrixRow("CarrotPhoneSpeedLimitEnabled", "carrot", "speed_limit", "CarrotPhoneSpeedLimitEnabled", "1", ("CarrotPhoneSpeedLimitEnabled", "CarrotNaviDebug", "CarrotNaviImage"), ui_surface="cruise+carrot", api=True, notes="Fresh APN/N/Navipilot/Carrot phone speed source."),
  MatrixRow("CarrotMapOverlayEnabled", "carrot", "maps", "CarrotMapOverlayEnabled", "0", ("MapboxStyle", "GMapKey", "MapboxPublicKey"), ui_surface="carrot", api=True, notes="Mapbox/Kakao overlay remains optional and default off."),
  MatrixRow("SpeedLimitPolicy", "carrot", "speed_limit", "SpeedLimitPolicy", "5", ("SpeedLimitPolicy",), ui_surface="speed_limit", api=True, notes="Phone-first resolver policy."),
  MatrixRow("SpeedLimitMode", "carrot", "speed_limit", "SpeedLimitMode", "1", ("SpeedLimitMode",), ui_surface="speed_limit", api=True, notes="Speed-limit display/assist mode."),
  MatrixRow("SpeedLimitOffsetType", "carrot", "speed_limit", "SpeedLimitOffsetType", "0", ("SpeedLimitOffsetType",), ui_surface="speed_limit", api=True, units="mode", notes="Default no offset."),
  MatrixRow("SpeedLimitValueOffset", "carrot", "speed_limit", "SpeedLimitValueOffset", "0", ("SpeedLimitValueOffset",), ui_surface="speed_limit", api=True, units="km/h or percent", notes="Default zero."),
  MatrixRow("CurveSpeedControlMode", "carrot", "curve_speed", "CurveSpeedControlMode", "1", ("AutoCurveSpeedFactor", "MapTurnSpeedFactor", "ModelTurnSpeedFactor", "VisionCurveSpeedController"), ui_surface="cruise+carrot", api=True, notes="Off/Sunny/Carrot/Balanced selector; Balanced is the user-facing label for internal fusion mode and owns Sunny SCC-V participation while SCC-M stays inert."),
  MatrixRow("AutoCurveSpeedLowerLimit", "carrot", "curve_speed", "AutoCurveSpeedLowerLimit", "30", ("AutoCurveSpeedLowerLimit",), ui_surface="carrot", api=True, units="km/h"),
  MatrixRow("AutoCurveSpeedFactor", "carrot", "curve_speed", "AutoCurveSpeedFactor", "120", ("AutoCurveSpeedFactor",), ui_surface="carrot", api=True, units="percent", notes="Higher makes Carrot curve detection more sensitive, usually lowers curve target speed, and slows earlier; lower-limit clamp can make further increases ineffective."),
  MatrixRow("AutoCurveSpeedAggressiveness", "carrot", "curve_speed", "AutoCurveSpeedAggressiveness", "100", ("AutoCurveSpeedAggressiveness",), ui_surface="carrot", api=True, units="percent", notes="Carrot-compatible secondary curve knob. Current active path primarily uses AutoCurveSpeedFactor; keep 100 unless a controller or Auto-Tuner recommendation uses it."),
  MatrixRow("AutoNaviSpeedDecelRate", "carrot", "navigation_speed", "AutoNaviSpeedDecelRate", "120", ("AutoNaviSpeedDecelRate",), ui_surface="cruise+carrot", api=True, units="percent", inverse_semantics="yes", notes="Lower values slow from farther away for navigation speed events; higher values delay the slowdown."),
  MatrixRow("CarrotActiveSpeedControlEnabled", "carrot", "active_control_gate", "CarrotActiveSpeedControlEnabled", "0", ("AutoCruiseControl", "AutoSpeedUptoRoadSpeedLimit"), ui_surface="cruise+carrot", api=True, notes="User-toggleable while offroad; controls active speed path gate."),
  MatrixRow("CarrotAutoTurnControlEnabled", "carrot", "active_control_gate", "CarrotAutoTurnControlEnabled", "0", ("AutoTurnControl", "AutoTurnControlSpeedTurn", "AutoTurnControlTurnEnd"), ui_surface="cruise+carrot", api=True),
  MatrixRow("CarrotTrafficStopEnabled", "carrot", "active_control_gate", "CarrotTrafficStopEnabled", "0", ("TrafficLight", "TrafficLightDetectMode"), ui_surface="cruise+carrot", api=True),
  MatrixRow("TurnSpeedControlMode", "carrot", "turn_speed", "TurnSpeedControlMode", "1", ("TurnSpeedControlMode",), ui_surface="cruise+carrot", api=True, notes="Off/Carrot/Sunny/Balanced selector."),
  MatrixRow("AutoTurnControl", "carrot", "turn_speed", "AutoTurnControl", "0", ("AutoTurnControl",), ui_surface="carrot", api=True, units="bool-int"),
  MatrixRow("AutoTurnControlSpeedTurn", "carrot", "turn_speed", "AutoTurnControlSpeedTurn", "20", ("AutoTurnControlSpeedTurn",), ui_surface="carrot", api=True, units="km/h"),
  MatrixRow("AutoTurnControlTurnEnd", "carrot", "turn_speed", "AutoTurnControlTurnEnd", "6", ("AutoTurnControlTurnEnd",), ui_surface="carrot", api=True, units="s/threshold"),
  MatrixRow("AutoTurnMapChange", "carrot", "turn_speed", "AutoTurnMapChange", "0", ("AutoTurnMapChange",), ui_surface="carrot", api=True, units="bool-int"),
  MatrixRow("TrafficLightDetectMode", "carrot", "traffic_light", "TrafficLightDetectMode", "2", ("TrafficLightDetectMode",), ui_surface="cruise+carrot", api=True),
  MatrixRow("TrafficStopDistanceAdjust", "carrot", "traffic_light", "TrafficStopDistanceAdjust", "-150", ("TrafficStopDistanceAdjust",), ui_surface="carrot", api=True, units="cm", notes="Negative values stop earlier/farther before the line; positive values stop later/closer."),
  MatrixRow("CarrotRainWet", "carrot", "driving_mode", "CarrotRainWet", "0", ("CarrotRainWet",), ui_surface="carrot", api=True),
  MatrixRow("MyDrivingMode", "carrot", "driving_mode", "MyDrivingMode", "3", ("MyDrivingModeAuto",), ui_surface="carrot", api=True),
  MatrixRow("MyDrivingModeAuto", "carrot", "driving_mode", "MyDrivingModeAuto", "0", ("MyDrivingModeAuto",), ui_surface="carrot", api=True),
  MatrixRow("CruiseEcoControl", "carrot", "longitudinal", "CruiseEcoControl", "2", ("CruiseEcoControl",), ui_surface="carrot", api=True),
  MatrixRow("CarrotCruiseDecel", "carrot", "longitudinal", "CarrotCruiseDecel", "-1", ("CarrotCruiseDecel",), ui_surface="cruise+carrot", api=True, units="percent/auto", notes="-1 means Auto."),
  MatrixRow("CarrotCruiseAtcDecel", "carrot", "longitudinal", "CarrotCruiseAtcDecel", "-1", ("CarrotCruiseAtcDecel",), ui_surface="cruise+carrot", api=True, units="percent/auto", notes="-1 means Auto."),
  MatrixRow("StopDistanceCarrot", "carrot", "longitudinal", "StopDistanceCarrot", "550", ("StopDistanceCarrot",), ui_surface="carrot+cruise", api=True, units="cm"),
  MatrixRow("DynamicTFollow", "carrot", "following", "DynamicTFollow", "0", ("DynamicTFollow",), ui_surface="carrot+cruise", api=True, units="percent"),
  MatrixRow("TFollowDecelBoost", "carrot", "following", "TFollowDecelBoost", "10", ("TFollowDecelBoost",), ui_surface="carrot+cruise", api=True, units="percent"),
  MatrixRow("TFollowSpeedFactor", "carrot", "following", "TFollowSpeedFactor", "0", ("TFollowSpeedFactor",), ui_surface="carrot", api=True, units="signed percent"),
  MatrixRow("DynamicTFollowLC", "carrot", "following", "DynamicTFollowLC", "100", ("DynamicTFollowLC",), ui_surface="carrot", api=True, units="percent"),
  MatrixRow("EnableSpeedTF", "carrot", "following", "EnableSpeedTF", "0", ("EnableSpeedTF",), ui_surface="carrot", api=True, units="bool-int"),
  MatrixRow("TFollowGap1", "carrot", "following", "TFollowGap1", "110", ("TFollowGap1",), ui_surface="carrot+cruise", api=True, units="centiseconds"),
  MatrixRow("TFollowGap2", "carrot", "following", "TFollowGap2", "120", ("TFollowGap2",), ui_surface="carrot+cruise", api=True, units="centiseconds"),
  MatrixRow("TFollowGap3", "carrot", "following", "TFollowGap3", "140", ("TFollowGap3",), ui_surface="carrot+cruise", api=True, units="centiseconds"),
  MatrixRow("TFollowGap4", "carrot", "following", "TFollowGap4", "160", ("TFollowGap4",), ui_surface="carrot+cruise", api=True, units="centiseconds"),
  MatrixRow("CruiseMaxVals0", "carrot", "accel_table", "CruiseMaxVals0", "160", ("CruiseMaxVals0",), ui_surface="carrot", api=True, units="0.01 m/s^2 @ 0 km/h", notes="Higher allows stronger acceleration in this speed band."),
  MatrixRow("CruiseMaxVals1", "carrot", "accel_table", "CruiseMaxVals1", "200", ("CruiseMaxVals1",), ui_surface="carrot", api=True, units="0.01 m/s^2 @ 10 km/h", notes="Higher allows stronger acceleration in this speed band."),
  MatrixRow("CruiseMaxVals2", "carrot", "accel_table", "CruiseMaxVals2", "160", ("CruiseMaxVals2",), ui_surface="carrot", api=True, units="0.01 m/s^2 @ 40 km/h", notes="Higher allows stronger acceleration in this speed band."),
  MatrixRow("CruiseMaxVals3", "carrot", "accel_table", "CruiseMaxVals3", "130", ("CruiseMaxVals3",), ui_surface="carrot", api=True, units="0.01 m/s^2 @ 60 km/h", notes="Higher allows stronger acceleration in this speed band."),
  MatrixRow("CruiseMaxVals4", "carrot", "accel_table", "CruiseMaxVals4", "110", ("CruiseMaxVals4",), ui_surface="carrot", api=True, units="0.01 m/s^2 @ 80 km/h", notes="Higher allows stronger acceleration in this speed band."),
  MatrixRow("CruiseMaxVals5", "carrot", "accel_table", "CruiseMaxVals5", "95", ("CruiseMaxVals5",), ui_surface="carrot", api=True, units="0.01 m/s^2 @ 110 km/h", notes="Higher allows stronger acceleration in this speed band."),
  MatrixRow("CruiseMaxVals6", "carrot", "accel_table", "CruiseMaxVals6", "80", ("CruiseMaxVals6",), ui_surface="carrot", api=True, units="0.01 m/s^2 @ 140 km/h", notes="Higher allows stronger acceleration in this speed band."),
  MatrixRow("LongTuningKpV", "carrot", "longitudinal_tune", "LongTuningKpV", "100", ("LongTuningKpV",), ui_surface="carrot", api=True, units="percent", notes="Higher reacts harder to speed error; lower can reduce overshoot/oscillation."),
  MatrixRow("LongTuningKiV", "carrot", "longitudinal_tune", "LongTuningKiV", "0", ("LongTuningKiV",), ui_surface="carrot", api=True, units="percent"),
  MatrixRow("LongTuningKf", "carrot", "longitudinal_tune", "LongTuningKf", "100", ("LongTuningKf",), ui_surface="carrot", api=True, units="percent"),
  MatrixRow("LongActuatorDelay", "carrot", "longitudinal_tune", "LongActuatorDelay", "20", ("LongActuatorDelay",), ui_surface="carrot", api=True, units="0.01 s", notes="Higher anticipates slower actuator response; too high may feel early."),
  MatrixRow("VEgoStopping", "carrot", "longitudinal_tune", "VEgoStopping", "50", ("VEgoStopping",), ui_surface="carrot", api=True, units="0.01 m/s", notes="Higher can smooth harsh stops; too high can enter stopping behavior early."),
  MatrixRow("RadarReactionFactor", "carrot", "longitudinal_tune", "RadarReactionFactor", "100", ("RadarReactionFactor",), ui_surface="carrot", api=True, units="percent"),
  MatrixRow("JLeadFactor3", "carrot", "longitudinal_tune", "JLeadFactor3", "0", ("JLeadFactor3",), ui_surface="carrot", api=True),
  MatrixRow("AChangeCostStarting", "carrot", "longitudinal_tune", "AChangeCostStarting", "10", ("AChangeCostStarting",), ui_surface="carrot", api=True),
  MatrixRow("CarrotLearningActive", "carrot", "auto_tuner", "CarrotLearningActive", "0", ("CarrotLearningActive",), ui_surface="carrot", api=True),
  MatrixRow("CarrotLearningAutoApply", "carrot", "auto_tuner", "CarrotLearningAutoApply", "0", ("CarrotLearningAutoApply",), ui_surface="carrot", api=True, notes="Default off. Manual apply is offroad-only."),
  MatrixRow("CarrotTunerApplyLat", "carrot", "auto_tuner", "CarrotTunerApplyLat", "1", ("CarrotTunerApplyLat",), ui_surface="carrot", api=True),
  MatrixRow("CarrotTunerApplyLong", "carrot", "auto_tuner", "CarrotTunerApplyLong", "1", ("CarrotTunerApplyLong",), ui_surface="carrot", api=True),
  MatrixRow("PathOffset", "carrot", "steering_path", "PathOffset", "0", ("PathOffset", "IQLanePlannerPathOffset"), ui_surface="carrot", api=True, units="cm", notes="0 is neutral; negative shifts left, positive shifts right."),
  MatrixRow("SteerActuatorDelay", "carrot", "steering_path", "SteerActuatorDelay", "0", ("SteerActuatorDelay",), ui_surface="carrot", api=True, units="0.01 s", notes="0 uses live/default delay; higher adds custom delay compensation."),
  MatrixRow("SteerRatioRate", "carrot", "steering_path", "SteerRatioRate", "100", ("SteerRatioRate",), ui_surface="carrot", api=True, units="percent", notes="100 is neutral."),
  MatrixRow("UseLaneLineSpeed", "carrot", "steering_path", "UseLaneLineSpeed", "0", ("UseLaneLineSpeed", "IQLanePlannerUseLaneLineSpeed"), ui_surface="carrot", api=True, units="bool-int"),
  MatrixRow("UseLaneLineCurveSpeed", "carrot", "steering_path", "UseLaneLineCurveSpeed", "0", ("UseLaneLineCurveSpeed",), ui_surface="carrot", api=True, units="bool-int"),
  MatrixRow("FishopLaneCurveEnabled", "fishop", "fishop_hardware", "FishopLaneCurveEnabled", "0", ("FishopLaneCurveEnabled", "UseLaneLineCurveSpeed"), ui_surface="carrot", api=True),
  MatrixRow("FishopLidarBlindspotEnabled", "fishop", "fishop_hardware", "FishopLidarBlindspotEnabled", "0", ("FishopLidarBlindspotEnabled", "lidar_car_lblind"), ui_surface="carrot", api=True),
  MatrixRow("FishopLidarLaneDataEnabled", "fishop", "fishop_hardware", "FishopLidarLaneDataEnabled", "0", ("FishopLidarLaneDataEnabled", "LaneLineCheck"), ui_surface="carrot", api=True),
  MatrixRow("FishopAutoOvertakeEnabled", "fishop", "fishop_hardware", "FishopAutoOvertakeEnabled", "0", ("FishopAutoOvertakeEnabled", "overtake"), ui_surface="carrot", api=True, notes="Setting is user-toggleable; output remains display/read-only until safety chain is validated."),
  MatrixRow("KIA_SELTOS_2023", "escc_vehicle_interface", "vehicle", None, None, ("ENHANCED_SCC", "KIA_SELTOS", "0x2AB"), ui_surface="vehicle_selector", notes="Pure CAN SCC Seltos profile; ESCC is automatic through 0x2AB."),
  MatrixRow("ModelManager_ActiveBundle", "model_manager", "models", "ModelManager_ActiveBundle", None, ("ModelManager_ActiveBundle",), ui_surface="models", notes="Sunny model manager retained; switching stays offroad; missing/invalid bundle means stock."),
  MatrixRow("GeniusVisualMode", "visualization", "onroad_visual", "GeniusVisualMode", "2", ("ShowPathMode", "ShowLaneInfo", "ShowRadarInfo"), ui_surface="visuals", api=True, notes="Mutually exclusive base preset: Sunny minimal, Carrot dense lane/path/lead/radar, Balanced default with Sunny HUD structure and Carrot road cues."),
  MatrixRow("GeniusLaneLineStyle", "visualization", "onroad_visual", "GeniusLaneLineStyle", "1", ("ShowLaneInfo", "LaneLineCheck"), ui_surface="visuals", api=True, notes="Lane-line style detail; may be adjusted after choosing a preset."),
  MatrixRow("GeniusLeadRadarVisualMode", "visualization", "onroad_visual", "GeniusLeadRadarVisualMode", "1", ("ShowRadarInfo", "RadarTrackId"), ui_surface="visuals", api=True, notes="Lead/ radar detail: Sunny chevron, Carrot box, or radar speed labels."),
  MatrixRow("GeniusLaneChangeVisuals", "visualization", "onroad_visual", "GeniusLaneChangeVisuals", "1", ("LaneChange", "laneChange"), ui_surface="visuals", api=True, notes="Display-only lane-change intent cues from existing onroad events."),
  MatrixRow("GeniusCarrotWorldOverlay", "visualization", "onroad_visual", "GeniusCarrotWorldOverlay", "0", ("ClusterHudRadarInfo", "ShowRadarInfo", "leftLaneLine", "leadsLeft"), ui_surface="visuals", api=True, notes="Independent Carrot world evidence overlay: side-lane, blindspot, lane-change, lead, and radar cues. Safe subset only; ajouatom-only side radar/lane schema remains a mapped follow-up."),
  MatrixRow("GeniusFishopVisualOverlay", "visualization", "onroad_visual", "GeniusFishopVisualOverlay", "0", ("lidar_car_lblind", "FishopLidarBlindspotEnabled"), ui_surface="visuals", api=True, notes="Independent top-layer Fishop/lidar evidence overlay; never a base preset or control gate."),
)


PARAM_RE = re.compile(r'^\s*\{"(?P<key>[^"]+)",\s*\{(?P<body>.*)\}\s*\},?\s*$')


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
  return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)


def git_show(ref: str, path: str) -> str:
  proc = run_git(["show", f"{ref}:{path}"])
  return proc.stdout if proc.returncode == 0 else ""


def parse_params(text: str) -> dict[str, dict[str, str]]:
  params: dict[str, dict[str, str]] = {}
  for line in text.splitlines():
    match = PARAM_RE.match(line)
    if not match:
      continue
    body = match.group("body")
    quoted = re.findall(r'"([^"]*)"', body)
    value_type = ""
    for part in body.split(","):
      candidate = part.strip().strip("{}")
      if candidate in {"BOOL", "INT", "FLOAT", "STRING", "BYTES", "JSON"}:
        value_type = candidate
        break
    params[match.group("key")] = {
      "type": value_type,
      "default": quoted[-1] if quoted else "<none>",
      "raw": body.strip(),
    }
  return params


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def current_context() -> dict[str, str]:
  return {
    "params": read("common/params_keys.h"),
    "carrot_ui": read("selfdrive/ui/sunnypilot/layouts/settings/carrot.py"),
    "cruise_ui": read("selfdrive/ui/sunnypilot/layouts/settings/cruise.py"),
    "visuals_ui": read("selfdrive/ui/sunnypilot/layouts/settings/visuals.py"),
    "vehicle_selector": read("sunnypilot/selfdrive/car/car_list.json") + read("opendbc_repo/opendbc/car/hyundai/values.py"),
    "carrot_server": read("selfdrive/carrot/carrot_server.py"),
    "process_config": read("system/manager/process_config.py"),
    "ui_state": read("selfdrive/ui/sunnypilot/ui_state.py"),
    "version": read("sunnypilot/common/version.h"),
  }


def surface_text(row: MatrixRow, ctx: dict[str, str]) -> str:
  if row.ui_surface.startswith("carrot"):
    return ctx["carrot_ui"]
  if row.ui_surface == "cruise" or row.ui_surface in {"carrot+cruise", "cruise+carrot"}:
    return ctx["carrot_ui"] + ctx["cruise_ui"]
  if row.ui_surface == "speed_limit":
    return read("selfdrive/ui/sunnypilot/layouts/settings/cruise_sub_layouts/speed_limit_policy.py") + read("selfdrive/ui/sunnypilot/layouts/settings/cruise_sub_layouts/speed_limit_settings.py")
  if row.ui_surface == "visuals":
    return ctx["visuals_ui"]
  if row.ui_surface == "vehicle_selector":
    return ctx["vehicle_selector"]
  if row.ui_surface == "models":
    return read("selfdrive/ui/sunnypilot/layouts/settings/models.py")
  if row.ui_surface == "mici_offroad":
    return read("selfdrive/ui/sunnypilot/mici/layouts/settings.py") + read("system/hardware/hardwared.py")
  return ""


def all_source_tokens() -> list[str]:
  tokens: set[str] = set()
  for row in MATRIX:
    tokens.update(row.source_keys or (row.key,))
  return sorted(tokens)


def reference_token_cache() -> dict[str, set[str]]:
  global REFERENCE_TOKEN_CACHE
  if REFERENCE_TOKEN_CACHE is not None:
    return REFERENCE_TOKEN_CACHE

  token_list = all_source_tokens()
  cache: dict[str, set[str]] = {}
  for ref in REFERENCES:
    if run_git(["rev-parse", "--verify", ref.ref]).returncode != 0:
      cache[ref.name] = set()
      continue

    args = ["grep", "-I", "-h", "-F"]
    for token in token_list:
      args.extend(["-e", token])
    args.extend([ref.ref, "--", "common/params_keys.h", "selfdrive", "sunnypilot", "opendbc_repo"])
    proc = run_git(args)
    found: set[str] = set()
    if proc.returncode == 0:
      for line in proc.stdout.splitlines():
        for token in token_list:
          if token in line:
            found.add(token)
    cache[ref.name] = found

  REFERENCE_TOKEN_CACHE = cache
  return cache


def reference_hits(row: MatrixRow) -> dict[str, bool]:
  cache = reference_token_cache()
  hits: dict[str, bool] = {}
  for ref in REFERENCES:
    hits[ref.name] = any(key in cache.get(ref.name, set()) for key in (row.source_keys or (row.key,)))
  return hits


def build_rows() -> list[dict[str, object]]:
  current_params = parse_params(read("common/params_keys.h"))
  rows: list[dict[str, object]] = []
  for row in MATRIX:
    hits = reference_hits(row)
    current = current_params.get(row.current_key or "", {})
    rows.append({
      **asdict(row),
      "current": current,
      "reference_hits": hits,
    })
  return rows


def check_matrix() -> tuple[bool, list[str]]:
  ctx = current_context()
  current_params = parse_params(ctx["params"])
  errors: list[str] = []

  owners = {row.owner for row in MATRIX}
  required_owners = {"carrot", "sunny_primitive", "fishop", "escc_vehicle_interface", "model_manager", "local_network_update", "removed_cloud"}
  missing_owners = required_owners - owners
  if missing_owners:
    errors.append(f"missing required owner classes: {sorted(missing_owners)}")

  for row in MATRIX:
    if row.current_key:
      if row.current_key not in current_params:
        errors.append(f"{row.key}: current param {row.current_key} missing")
      elif row.default is not None and current_params[row.current_key]["default"] != row.default:
        errors.append(f"{row.key}: default {current_params[row.current_key]['default']} != {row.default}")

    if row.required_sources:
      hits = reference_hits(row)
      for source in row.required_sources:
        if not hits.get(source, False):
          errors.append(f"{row.key}: required source {source} missing source key evidence")

    if row.ui_surface:
      text = surface_text(row, ctx)
      token = row.current_key or row.key
      if token and token not in text:
        errors.append(f"{row.key}: UI surface {row.ui_surface} does not mention {token}")

    if row.api and row.current_key and f'"{row.current_key}"' not in ctx["carrot_server"]:
      errors.append(f"{row.key}: Carrot Web API does not expose {row.current_key}")

    for token in row.consumer_tokens:
      if token not in "".join(ctx.values()):
        errors.append(f"{row.key}: consumer token missing: {token}")

    for token in row.forbid_tokens:
      if token in "".join(ctx.values()):
        errors.append(f"{row.key}: forbidden token present: {token}")

  cloud_text = ctx["carrot_ui"] + ctx["cruise_ui"] + ctx["visuals_ui"] + ctx["carrot_server"]
  for token in ('"EnableConnect"', '"SunnylinkEnabled"', '"EnableSunnylinkUploader"', '"OnroadUploads"'):
    if token in cloud_text and token != '"OnroadUploads"':
      errors.append(f"cloud token exposed in user/API surface: {token}")

  if "DynamicExperimentalControl" not in ctx["cruise_ui"] or "DynamicExperimentalControl" not in ctx["carrot_ui"]:
    errors.append("DEC is not exposed as a separate Cruise/Super Advanced candidate")
  if "LOCKED_CONTROL_PARAMS" in ctx["carrot_ui"]:
    errors.append("Carrot controls are still locked by UI")

  return not errors, errors


def markdown(rows: list[dict[str, object]]) -> str:
  lines = [
    "# Genius Pilot Settings Matrix",
    "",
    "Generated by `scripts/personal/genius_settings_matrix.py --write-docs`.",
    "",
    "This matrix assigns one owner to each imported, retained, hidden, or removed setting family. It is intentionally conservative: cloud/connect settings are kept inert, Sunny overlap features are hidden or separated, and Carrot/Fishop settings stay explicit.",
    "",
    "| Setting | Owner | Category | Current key | Default | Sources with evidence | UI/API | Units | Inverse | Notes |",
    "|---|---|---|---|---|---|---|---|---|---|",
  ]
  for item in rows:
    hits = item["reference_hits"]
    source_names = ", ".join(name for name, present in hits.items() if present) or "-"
    ui_api = item["ui_surface"] or "-"
    if item["api"]:
      ui_api += "+api" if ui_api != "-" else "api"
    notes = str(item["notes"]).replace("|", "/")
    lines.append(
      f"| {item['key']} | {item['owner']} | {item['category']} | {item['current_key'] or '-'} | "
      f"{item['default'] if item['default'] is not None else '-'} | {source_names} | {ui_api} | "
      f"{item['units'] or '-'} | {item['inverse_semantics']} | {notes} |"
    )
  lines.append("")
  return "\n".join(lines)


def write_docs() -> None:
  rows = build_rows()
  MATRIX_JSON.write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True), encoding="utf-8")
  MATRIX_MD.write_text(markdown(rows), encoding="utf-8")


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate and generate the Genius Pilot per-setting owner matrix.")
  parser.add_argument("--write-docs", action="store_true", help="write docs/personal/SETTINGS_MATRIX.md and settings_matrix.json")
  parser.add_argument("--check", action="store_true", help="validate the matrix and generated docs")
  args = parser.parse_args()

  if args.write_docs:
    write_docs()

  ok, errors = check_matrix()
  docs_ok = MATRIX_MD.exists() and MATRIX_JSON.exists()
  if args.check and not docs_ok:
    errors.append("generated settings matrix docs are missing")
    ok = False

  if ok and (not args.check or docs_ok):
    print(f"PASS Genius settings matrix: {len(MATRIX)} rows")
    return 0

  for error in errors:
    print(f"FAIL {error}")
  return 1


if __name__ == "__main__":
  raise SystemExit(main())
