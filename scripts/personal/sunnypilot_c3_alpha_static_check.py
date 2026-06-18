#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8")


def read_tree(rel: str, suffixes: tuple[str, ...]) -> str:
  root = ROOT / rel
  chunks: list[str] = []
  for path in root.rglob("*"):
    if not path.is_file() or path.suffix not in suffixes:
      continue
    if path.stat().st_size > 1_000_000:
      continue
    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
  return "\n".join(chunks)


def po_has_translation(po_text: str, msgid: str) -> bool:
  marker = f'msgid "{msgid}"'
  idx = po_text.find(marker)
  if idx < 0:
    return False
  for line in po_text[idx:].splitlines()[1:6]:
    if line.startswith('msgid "'):
      return False
    if line.startswith('msgstr "') and line != 'msgstr ""':
      return True
  return False


def find_token_in_tree(rel: str, tokens: tuple[str, ...], suffixes: tuple[str, ...]) -> tuple[str, str] | None:
  root = ROOT / rel
  rg = shutil.which("rg")
  if rg is not None:
    glob_args: list[str] = []
    for suffix in suffixes:
      glob_args.extend(["--glob", f"*{suffix}"])
    for token in tokens:
      result = subprocess.run(
        [
          rg,
          "--fixed-strings",
          "--line-number",
          "--glob", "!**/tests/**",
          "--glob", "!**/test/**",
          *glob_args,
          token,
          str(root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
      )
      if result.returncode == 0:
        first = result.stdout.splitlines()[0].split(":", 1)[0]
        return token, str(Path(first).resolve().relative_to(ROOT))

  skip_dirs = {"__pycache__", ".git", "tests", "test"}
  for path in root.rglob("*"):
    if not path.is_file() or path.suffix not in suffixes:
      continue
    if any(part in skip_dirs for part in path.relative_to(root).parts):
      continue
    if path.stat().st_size > 1_000_000:
      continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    for token in tokens:
      if token in text:
        return token, str(path.relative_to(ROOT))
  return None


def require(name: str, condition: bool, detail: str) -> bool:
  if condition:
    print(f"PASS {name}")
    return True
  print(f"FAIL {name}: {detail}")
  return False


AUTO_TUNER_DEFAULTS = {
  "CarrotActiveSpeedControlEnabled": 0,
  "CarrotAutoTurnControlEnabled": 0,
  "CarrotLearningActive": 0,
  "CarrotLearningAutoApply": 0,
  "CarrotLearningApply": 0,
  "CarrotLearningIgnore": 0,
  "CarrotLearningClear": 0,
  "CarrotLearningPopupReady": 0,
  "CarrotNaviDebug": "{}",
  "CarrotNaviEvent": "{}",
  "CarrotNaviImage": "{}",
  "CarrotPhoneSpeedLimit": 0,
  "CarrotPhoneSpeedLimitEnabled": 1,
  "CarrotPhoneSpeedLimitUpdatedAt": 0,
  "CarrotMapOverlayEnabled": 0,
  "CarrotNavigationEvent": "{}",
  "CarrotTrafficStopEnabled": 0,
  "CarrotTunerApplyLat": 1,
  "CarrotTunerApplyLong": 1,
  "CarrotTunerFactoryReset": 0,
  "ExperimentalMode": 0,
  "ExperimentalModeConfirmed": 0,
  "FishopAutoOvertakeEnabled": 0,
  "IsMetric": 1,
  "IsOnroad": 0,
  "OffroadMode": 0,
  "OpenpilotEnabledToggle": 1,
  "SpeedLimitMode": 1,
  "SpeedLimitOffsetType": 0,
  "SpeedLimitPolicy": 5,
  "SpeedLimitValueOffset": 0,
  "SshEnabled": 0,
  "CruiseMaxVals0": 160,
  "CruiseMaxVals1": 200,
  "CruiseMaxVals2": 160,
  "CruiseMaxVals3": 130,
  "CruiseMaxVals4": 110,
  "CruiseMaxVals5": 95,
  "CruiseMaxVals6": 80,
  "DynamicTFollow": 0,
  "JLeadFactor3": 0,
  "PathOffset": 0,
  "SteerActuatorDelay": 0,
  "SteerRatioRate": 100,
  "StopDistanceCarrot": 550,
  "TFollowDecelBoost": 10,
  "TFollowGap1": 110,
  "TFollowGap2": 120,
  "TFollowGap3": 140,
  "TFollowGap4": 160,
}


class FakeParams:
  shared_store: dict[str, bytes] = {}

  @classmethod
  def reset(cls) -> None:
    cls.shared_store = {key: str(value).encode("utf-8") for key, value in AUTO_TUNER_DEFAULTS.items()}

  def __init__(self):
    if not self.shared_store:
      self.reset()
    self.store = self.shared_store

  def get(self, key, *args, **_kwargs):
    return self.store.get(key)

  def get_int(self, key):
    raw = self.get(key)
    try:
      return int((raw or b"0").decode("utf-8"))
    except Exception:
      return 0

  def get_bool(self, key):
    raw = self.get(key)
    if raw is None:
      return False
    try:
      return raw.decode("utf-8").strip().lower() in ("1", "true", "on", "yes")
    except Exception:
      return False

  def put(self, key, value):
    if isinstance(value, bytes):
      self.store[key] = value
    elif isinstance(value, (dict, list)):
      self.store[key] = json.dumps(value, separators=(",", ":")).encode("utf-8")
    else:
      self.store[key] = str(value).encode("utf-8")

  def put_int(self, key, value):
    self.put(key, str(int(value)))

  def put_bool(self, key, value):
    self.put(key, "1" if value else "0")

  def put_float(self, key, value):
    self.put(key, f"{float(value):.6f}")

  def remove(self, key):
    self.store.pop(key, None)


def import_file(module_name: str, rel: str):
  spec = importlib.util.spec_from_file_location(module_name, str(ROOT / rel))
  if spec is None or spec.loader is None:
    raise RuntimeError(f"unable to import {rel}")
  module = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = module
  spec.loader.exec_module(module)
  return module


CAPNP_FIELD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+@([0-9]+)\s*(?::|;)")
CAPNP_BLOCK_RE = re.compile(
  r"\b(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b|"
  r"([A-Za-z_][A-Za-z0-9_]*)\s*:(?:group|union)\b|"
  r"\bunion\b"
)


def capnp_duplicate_report(rel: str) -> str:
  scopes: list[str] = [rel]
  seen_names: dict[str, dict[str, int]] = {}
  seen_tags: dict[str, dict[int, tuple[str, int]]] = {}

  for line_no, raw_line in enumerate(read(rel).splitlines(), start=1):
    code = raw_line.split("#", 1)[0].strip()
    if not code:
      continue

    leading_closes = len(code) - len(code.lstrip("}"))
    for _ in range(leading_closes):
      if len(scopes) > 1:
        scopes.pop()

    match = CAPNP_FIELD_RE.match(code)
    if match:
      name = match.group(1)
      tag = int(match.group(2))
      scope = ".".join(scopes)
      names = seen_names.setdefault(scope, {})
      tags = seen_tags.setdefault(scope, {})
      if name in names:
        return f"{rel}:{line_no} duplicates field/enum name {name!r}; first seen at line {names[name]}"
      if tag in tags:
        first_name, first_line = tags[tag]
        return f"{rel}:{line_no} duplicates tag @{tag}; first used by {first_name!r} at line {first_line}"
      names[name] = line_no
      tags[tag] = (name, line_no)

    opens = code.count("{")
    for _ in range(opens):
      block_match = CAPNP_BLOCK_RE.search(code)
      if block_match:
        block_name = block_match.group(1) or block_match.group(2) or "union"
      else:
        block_name = f"block@{line_no}"
      scopes.append(block_name)

    trailing_closes = code.count("}") - leading_closes
    for _ in range(max(trailing_closes, 0)):
      if len(scopes) > 1:
        scopes.pop()

  return ""


def check_schema_contract() -> tuple[bool, str]:
  custom_capnp = read("cereal/custom.capnp")
  log_capnp = read("cereal/log.capnp")

  for rel in ("cereal/custom.capnp", "cereal/log.capnp"):
    duplicate = capnp_duplicate_report(rel)
    if duplicate:
      return False, duplicate

  expected_structs = (
    "struct ModelManagerSP @",
    "struct LongitudinalPlanSP @",
    "struct CarParamsSP @",
    "struct CarControlSP @",
    "struct BackupManagerSP @",
    "struct CarStateSP @",
    "struct ModelDataV2SP @",
  )
  for token in expected_structs:
    if token not in custom_capnp:
      return False, f"custom.capnp missing {token}"

  for token in (
    "phone @3;",
    "sourceLabel @9 :Text;",
    "speedLimitFinal @5 :Float32;",
    "speedLimitFinalLast @6 :Float32;",
  ):
    if token not in custom_capnp:
      return False, f"custom.capnp missing speed-limit schema token {token!r}"

  expected_log_fields = {
    "modelManagerSP": "Custom.ModelManagerSP",
    "longitudinalPlanSP": "Custom.LongitudinalPlanSP",
    "carParamsSP": "Custom.CarParamsSP",
    "backupManagerSP": "Custom.BackupManagerSP",
    "carStateSP": "Custom.CarStateSP",
    "modelDataV2SP": "Custom.ModelDataV2SP",
  }
  for service, schema_type in expected_log_fields.items():
    if f"{service} @" not in log_capnp or schema_type not in log_capnp:
      return False, f"log.capnp missing event field {service}: {schema_type}"

  return True, ""


def check_services_contract() -> tuple[bool, str]:
  try:
    services = import_file("alpha_cereal_services_static_check", "cereal/services.py")
  except Exception as exc:
    return False, f"unable to import cereal/services.py directly: {exc}"

  generated_header = services.build_header()
  checked_in_header = read("cereal/services.h")
  if generated_header.rstrip("\n") != checked_in_header.rstrip("\n"):
    return False, "cereal/services.h is out of sync with cereal/services.py"

  service_list = services.SERVICE_LIST
  expected = {
    "modelManagerSP": (False, 1.0, 1, services.QueueSize.BIG),
    "longitudinalPlanSP": (True, 20.0, 10, services.QueueSize.SMALL),
    "carParamsSP": (True, 0.02, 1, services.QueueSize.SMALL),
    "carStateSP": (True, 100.0, 10, services.QueueSize.SMALL),
    "modelDataV2SP": (True, 20.0, None, services.QueueSize.BIG),
  }
  for name, (should_log, frequency, decimation, queue_size) in expected.items():
    service = service_list.get(name)
    if service is None:
      return False, f"SERVICE_LIST missing {name}"
    if service.should_log != should_log or abs(service.frequency - frequency) > 0.0001:
      return False, f"{name} has unexpected logging/frequency"
    if service.decimation != decimation or service.queue_size != queue_size:
      return False, f"{name} has unexpected decimation/queue size"

  for name in ("carState", "selfdriveState", "controlsState", "pandaStates", "modelV2", "drivingModelData", "cameraOdometry"):
    if name not in service_list:
      return False, f"SERVICE_LIST missing base service {name}"

  return True, ""


def check_carrot_web_asset_syntax() -> tuple[bool, str]:
  try:
    import yaml  # type: ignore[import-untyped]
  except Exception as exc:
    return False, f"PyYAML unavailable, cannot parse settings_ui_src YAML: {exc}"

  json_paths = [
    ROOT / "sunnypilot/sunnylink/settings_ui.json",
    ROOT / "sunnypilot/sunnylink/settings_ui.schema.json",
  ]
  json_paths.extend((ROOT / "selfdrive/carrot").rglob("*.json"))
  for path in json_paths:
    try:
      json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
      return False, f"{path.relative_to(ROOT)} is not valid JSON: {exc}"

  for path in (ROOT / "sunnypilot/sunnylink/settings_ui_src").rglob("*.yaml"):
    try:
      yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
      return False, f"{path.relative_to(ROOT)} is not valid YAML: {exc}"

  try:
    compiler = import_file("alpha_settings_ui_compile_static_check", "sunnypilot/sunnylink/tools/compile_settings_ui.py")
    compiled = compiler.compile_schema(str(ROOT / "sunnypilot/sunnylink/settings_ui_src"))
    committed = json.loads(read("sunnypilot/sunnylink/settings_ui.json"))
  except Exception as exc:
    return False, f"settings_ui source compile failed: {exc}"
  if compiled != committed:
    return False, "settings_ui.json is out of sync with settings_ui_src"

  js_paths = sorted((ROOT / "selfdrive/carrot").rglob("*.js"))
  if js_paths:
    node = shutil.which("node")
    if node is None:
      return False, "Carrot Web JS assets exist but node is unavailable for syntax checks"
    for path in js_paths:
      result = subprocess.run([node, "--check", str(path)], cwd=ROOT, capture_output=True, text=True, check=False)
      if result.returncode != 0:
        return False, f"{path.relative_to(ROOT)} failed node --check: {result.stderr.strip()}"

  return True, ""


def check_fishop_overtake_safety_contract() -> tuple[bool, str]:
  fishop_hardware = read("selfdrive/carrot/fishop_hardware.py")
  carrot_server = read("selfdrive/carrot/carrot_server.py")

  # Stage 0/1 contract: fishop overtaking is evidence only. It must not enter
  # controls until a later staged suggestion path explicitly uses the existing
  # lane-change helper with turn-signal, blindspot, driver, speed, and vehicle gates.
  blocked_control_tokens = ("FishopAutoOvertakeEnabled", "AUTO_OVERTAKE", "OVERTAKE", "overtake_request", "overtake")
  for root in ("selfdrive/controls", "selfdrive/car", "opendbc_repo/opendbc/car"):
    found = find_token_in_tree(root, blocked_control_tokens, (".py", ".cc", ".cpp", ".h", ".hpp"))
    if found is not None:
      token, path = found
      return False, f"{token!r} appears in {path} before the staged safety chain exists"

  parser_forbidden = (
    "log.Desire",
    "LaneChangeState",
    "LaneChangeDirection",
    "lateralManeuverPlan",
    "leftBlinker",
    "rightBlinker",
    "leftBlindspot",
    "rightBlindspot",
    "desiredCurvature",
    "CarControl",
    "PubMaster",
    "sendcan",
    "desire_helper",
    "planner",
  )
  for token in parser_forbidden:
    if token in fishop_hardware:
      return False, f"fishop hardware parser references control/safety-chain token {token!r}"

  server_forbidden = (
    "log.Desire",
    "LaneChangeState",
    "LaneChangeDirection",
    "lateralManeuverPlan",
    "leftBlinker",
    "rightBlinker",
    "leftBlindspot",
    "rightBlindspot",
    "desiredCurvature",
    "CarControl",
    "PubMaster",
    "sendcan",
    "desire_helper",
  )
  for token in server_forbidden:
    if token in carrot_server:
      return False, f"Carrot Web/navigation bridge references control/safety-chain token {token!r}"

  required_parser_tokens = (
    "CONTROL_OUTPUT_ENABLED = False",
    '"controlOutputEnabled": CONTROL_OUTPUT_ENABLED',
    '"readOnly": True',
    '"overtake": overtake',
    "OVERTAKE_MAX_AGE_S = 1.0",
    '"laneQuality": self.quality(fresh)',
    '"dynamicBlind": self.dynamic_blind(targets_fresh)',
    '"directionality": {',
    '"suggestionPreview"',
    '"stage": "display_only"',
    '"emitsLateralCommand": False',
    '"alphaAction": "record_only"',
    '"usesExistingLaneChangeChain": False',
  )
  for token in required_parser_tokens:
    if token not in fishop_hardware:
      return False, f"fishop hardware parser missing read-only overtaking contract token {token!r}"

  required_server_tokens = (
    '"FishopAutoOvertakeEnabled": {"type": "bool", "default": False, "writable": False}',
    '"OVERTAKE"',
    '"AUTO_OVERTAKE"',
    "commandIgnored",
    "highRiskCommandSeen",
  )
  for token in required_server_tokens:
    if token not in carrot_server:
      return False, f"Carrot Web/navigation bridge missing high-risk command guard token {token!r}"

  return True, ""


def check_carrot_learning_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    learning = import_file("alpha_carrot_learning_static_check", "selfdrive/carrot/carrot_learning.py")
    learner = learning.CarrotLearner()

    learner.update(80, True, True, False, lead_drel=30, lead_v_kph=70, gas_val=0.3)
    if learner.params.get("CarrotLearningData") is not None:
      return False, "inactive learner wrote CarrotLearningData"

    learner.params.put_bool("CarrotLearningActive", True)
    for _ in range(160):
      learner.update(80, True, True, False, lead_drel=40, lead_v_kph=75, gas_val=0.4)
    learner.update(0, False, False, True)

    raw = learner.params.get("CarrotLearningRecommend")
    if not raw:
      return False, "active learner did not create a recommendation"
    payload = json.loads(raw.decode("utf-8"))
    if "CruiseMaxVals4" not in payload.get("recommendations", {}):
      return False, "learner recommendation missing CruiseMaxVals4"
    if learner.params.get_int("CruiseMaxVals4") != 110:
      return False, "learner changed target params before apply"

    learner.params.put_bool("IsOnroad", True)
    learner.params.put_bool("CarrotLearningApply", True)
    learner.update(0, False, False, False)
    if learner.params.get_int("CruiseMaxVals4") != 110:
      return False, "learner applied recommendations while IsOnroad=1"
    if learner.params.get_bool("CarrotLearningApply"):
      return False, "CarrotLearningApply did not reset after blocked onroad apply"
    if not learner.params.get("CarrotLearningRecommend"):
      return False, "blocked onroad apply cleared the pending recommendation"

    learner.params.put_bool("IsOnroad", False)
    learner.params.put_bool("CarrotLearningApply", True)
    learner.update(0, False, False, False)
    if learner.params.get_int("CruiseMaxVals4") <= 110:
      return False, "offroad manual apply did not apply recommendation"
    if learner.params.get("CarrotLearningRecommend"):
      return False, "manual apply did not clear pending recommendation"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_phone_speed_limit_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_static_check", "selfdrive/carrot/carrot_server.py")
    result = server.set_phone_speed_limit({"speedLimit": 50, "source": "navipilot"})
    if not result.get("accepted"):
      return False, "phone speed endpoint did not accept a normal speed limit"
    raw_speed = FakeParams.shared_store.get("CarrotPhoneSpeedLimit", b"0").decode("utf-8")
    if abs(float(raw_speed) - 13.888889) > 0.001:
      return False, f"phone speed endpoint wrote {raw_speed}, expected m/s for 50 kph"
    raw_source = FakeParams.shared_store.get("CarrotPhoneSpeedLimitSource", b"").decode("utf-8")
    if raw_source != "navipilot":
      return False, "phone speed endpoint did not preserve the local source label"
    state = server.phone_speed_state()
    if not state.get("fresh") or state.get("speedLimitKph") != 50.0:
      return False, "phone speed state did not report fresh 50 kph data"

    server.set_phone_speed_limit({"nRoadLimitSpeed": 0, "nSdiSpeedLimit": 40, "source": "apn"})
    state = server.phone_speed_state()
    if not state.get("fresh") or state.get("speedLimitKph") != 40.0 or state.get("source") != "apn":
      return False, "phone speed endpoint did not skip zero road limit and use SDI fallback"

    server.set_phone_speed_limit({"action": "clear"})
    state = server.phone_speed_state()
    if state.get("fresh") or state.get("speedLimitMS") != 0.0:
      return False, "phone speed clear action did not invalidate the phone source"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_route_speed_truth_contract() -> tuple[bool, str]:
  custom_capnp = read("cereal/custom.capnp")
  resolver = read("sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_resolver.py")
  common = read("sunnypilot/selfdrive/controls/lib/speed_limit/common.py")
  planner = read("sunnypilot/selfdrive/controls/lib/longitudinal_planner.py")
  carrot_server = read("selfdrive/carrot/carrot_server.py")

  try:
    speed_limit_start = custom_capnp.index("struct SpeedLimit {")
    source_start = custom_capnp.index("enum Source {", speed_limit_start)
    source_end = custom_capnp.index("\n    }", source_start)
    source_enum = custom_capnp[source_start:source_end]
  except ValueError:
    return False, "unable to locate LongitudinalPlanSP.SpeedLimit.Source enum"

  required_sources = ("none @0;", "car @1;", "map @2;", "phone @3;")
  if not all(source in source_enum for source in required_sources):
    return False, "SpeedLimit.Source must remain limited to none/car/map/phone"
  for token in ("route", "vrtx", "mapbox", "kakao", "carrot", "navigation"):
    if token in source_enum.lower():
      return False, f"SpeedLimit.Source must not include route/map overlay source token {token}"

  control_surfaces = {
    "speed_limit_resolver.py": resolver,
    "speed_limit/common.py": common,
    "longitudinal_planner.py": planner,
  }
  banned_control_tokens = (
    "route",
    "Route",
    "vrtx",
    "Mapbox",
    "mapbox",
    "Kakao",
    "kakao",
    "CarrotRoute",
    "CarrotNavi",
    "CarrotNavigationEvent",
  )
  for name, text in control_surfaces.items():
    for token in banned_control_tokens:
      if token in text:
        return False, f"{name} contains route/map overlay token {token}"

  if "Policy.phone_priority: [SpeedLimitSource.phone, SpeedLimitSource.car, SpeedLimitSource.map]" not in resolver:
    return False, "phone_priority must stay ordered phone > car > map"
  if "self._get_from_phone_data()" not in resolver or "self._get_from_car_state(sm)" not in resolver or "self._get_from_map_data(sm)" not in resolver:
    return False, "resolver must collect only phone, car, and map speed-limit sources"

  try:
    kph_start = carrot_server.index("PHONE_SPEED_LIMIT_KPH_FIELDS = (")
    kph_end = carrot_server.index(")", kph_start)
    kph_fields = carrot_server[kph_start:kph_end]
    ms_start = carrot_server.index("PHONE_SPEED_LIMIT_MS_FIELDS = (")
    ms_end = carrot_server.index(")", ms_start)
    ms_fields = carrot_server[ms_start:ms_end]
  except ValueError:
    return False, "unable to locate phone speed-limit field allowlists"

  for token in ("route", "vrtx", "points", "coordinates", "vpPosPointLat", "vpPosPointLon", "latitude", "longitude"):
    if f'"{token}"' in kph_fields or f'"{token}"' in ms_fields:
      return False, f"phone speed-limit allowlist must not accept route/position field {token}"
  for token in ("nRoadLimitSpeed", "nSdiSpeedLimit", "nSdiPlusSpeedLimit", "speedLimitKph"):
    if f'"{token}"' not in kph_fields:
      return False, f"phone speed-limit allowlist missing expected speed field {token}"

  if 'NAVI_EVENT_TYPES = ("complexCrossroad", "rgdata", "vrtx", "ssinf", "sinf", "route")' not in carrot_server:
    return False, "Carrot route/vrtx input must remain a navigation event type, not a resolver source"
  if 'elif event_type in ("vrtx", "route"):' not in carrot_server or 'summary["routePointCount"] = _navi_route_count(event_payload)' not in carrot_server:
    return False, "route/vrtx compatibility input must be summarized as routePointCount evidence"
  if '"controlOutput": False' not in carrot_server:
    return False, "Carrot route/navigation compatibility events must remain read-only"
  for token in ("Mapbox", "mapbox", "Kakao", "kakao"):
    if token in carrot_server:
      return False, f"Carrot Web/server must not load {token} as a speed-limit truth source"

  return True, ""


def check_model_manager_download_contract() -> tuple[bool, str]:
  manager = read("sunnypilot/models/manager.py")
  helpers = read("sunnypilot/models/helpers.py")

  required_manager_tokens = (
    "_download_temp_path",
    "temp_path = self._download_temp_path(full_path)",
    "await self._download_chunked(url, temp_path, artifact)",
    "await self._download_file(url, temp_path, artifact)",
    "if not await verify_file(temp_path, expected_hash)",
    "self._install_downloaded_artifact(temp_path, full_path)",
    "self._cleanup_download_artifact(temp_path)",
    "os.replace(temp_path, full_path)",
    "os.replace(temp_chunk_path, final_chunk_path)",
    "os.replace(temp_chunk_paths[0], final_manifest)",
  )
  for token in required_manager_tokens:
    if token not in manager:
      return False, f"models_manager missing atomic download token: {token}"

  if "await self._download_chunked(url, full_path, artifact)" in manager or "await self._download_file(url, full_path, artifact)" in manager:
    return False, "models_manager must not download directly into the active artifact path"
  if "for f in [full_path]" in manager or "if filename in p" in manager:
    return False, "download failure must not delete the existing active artifact path"

  verify_index = manager.find("if not await verify_file(temp_path, expected_hash)")
  install_index = manager.find("self._install_downloaded_artifact(temp_path, full_path)")
  active_put_index = manager.find('self.params.put("ModelManager_ActiveBundle", self.active_bundle.to_dict(), block=True)')
  if not (0 <= verify_index < install_index < active_put_index):
    return False, "models_manager must hash-check temp artifacts before install and write active bundle only after bundle download succeeds"

  if "validate_active_bundle(self.params, self.available_models)" not in manager:
    return False, "models_manager must validate active bundle before publishing/downloading state"
  if 'params.remove("ModelManager_ActiveBundle")' not in helpers or "ModelRunnerTypeCache" not in helpers:
    return False, "invalid active bundle must reset to stock runner"
  if "_bundle_is_valid_locally" not in helpers or "_verify_file(os.path.join(model_root, file_name), expected_hash)" not in helpers:
    return False, "active bundle validation must re-hash local artifacts"

  return True, ""


def check_carrot_learning_api_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_learning_static_check", "selfdrive/carrot/carrot_server.py")
    payload = {
      "version": 1,
      "source": "static-check",
      "created_at": 1234.0,
      "recommendations": {
        "CruiseMaxVals4": {
          "category": "long",
          "current": 110,
          "recommended": 120,
          "reason": "static check",
          "evidence": {"sample": True},
        },
      },
    }
    FakeParams.shared_store["CruiseMaxVals4"] = b"110"
    FakeParams.shared_store["CarrotLearningRecommend"] = json.dumps(payload).encode("utf-8")
    state = server.get_learning_state()
    recs = state.get("recommendations", [])
    if state.get("recommendationSummary", {}).get("pending") != 1 or len(recs) != 1:
      return False, "Carrot learning API did not report one pending recommendation"
    rec = recs[0]
    if rec.get("capturedCurrentValue") != 110 or rec.get("currentValue") != 110 or rec.get("recommendedValue") != 120:
      return False, "Carrot learning API did not expose captured/current/recommended values"
    if rec.get("applied") is not False or rec.get("state") != "pending" or rec.get("liveDelta") != 10:
      return False, "Carrot learning API did not distinguish a pending recommendation"

    FakeParams.shared_store["CruiseMaxVals4"] = b"120"
    applied_state = server.get_learning_state()
    applied_rec = applied_state.get("recommendations", [])[0]
    if applied_rec.get("currentValue") != 120 or applied_rec.get("appliedValue") != 120:
      return False, "Carrot learning API did not expose the applied/current value"
    if applied_rec.get("applied") is not True or applied_rec.get("state") != "applied" or applied_rec.get("liveDelta") != 0:
      return False, "Carrot learning API did not mark the recommendation as applied"
    if applied_state.get("recommendationSummary", {}).get("applied") != 1:
      return False, "Carrot learning API did not summarize applied recommendations"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_params_api_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_params_static_check", "selfdrive/carrot/carrot_server.py")
    state = server.params_bulk_state(["ExperimentalMode", "ExperimentalModeConfirmed", "OffroadMode", "SpeedFromPCM", "AlwaysOffroad", "DeviceType"])
    if not state.get("hasParams"):
      return False, "params bulk state did not report fake Params"
    values = state.get("values", {})
    writable = state.get("writable", {})
    read_only = state.get("readOnly", {})
    if values.get("ExperimentalMode") is not False or writable.get("ExperimentalMode") is not True:
      return False, "ExperimentalMode was not exposed as a writable bool"
    if values.get("ExperimentalModeConfirmed") is not False or writable.get("ExperimentalModeConfirmed") is not True:
      return False, "ExperimentalModeConfirmed was not exposed as a writable bool"
    if values.get("OffroadMode") is not False or writable.get("OffroadMode") is not False:
      return False, "OffroadMode must be read-only through local API"
    if values.get("SpeedFromPCM") != 1 or writable.get("SpeedFromPCM") is not False or read_only.get("SpeedFromPCM") is not True:
      return False, "SpeedFromPCM must be visible for Navipilot compatibility but read-only on this Kia build"
    if values.get("AlwaysOffroad") != 0 or writable.get("AlwaysOffroad") is not False:
      return False, "legacy unknown AlwaysOffroad must only read as an inert default"
    if values.get("DeviceType") != "unknown" or writable.get("DeviceType") is not False:
      return False, "DeviceType must be a read-only virtual value"
    if state.get("has_params") is not True or "AlwaysOffroad" not in state.get("unknown", []):
      return False, "params_bulk_state must expose jixie-compatible has_params and unknown metadata"
    if server.get_param_values(["ExperimentalMode"]).get("ExperimentalMode") is not False:
      return False, "get_param_values compatibility helper did not mirror bulk values"

    result = server.set_param_from_api("ExperimentalMode", 1)
    if not result.get("changed") or FakeParams.shared_store.get("ExperimentalMode") != b"1":
      return False, "param_set did not write ExperimentalMode"
    compat_result = server.set_param_value("ExperimentalModeConfirmed", 1)
    if not compat_result.get("changed") or FakeParams.shared_store.get("ExperimentalModeConfirmed") != b"1":
      return False, "set_param_value compatibility helper did not write ExperimentalModeConfirmed"
    unchanged = server.set_param_from_api("ExperimentalMode", True)
    if unchanged.get("changed"):
      return False, "same-value param_set should report unchanged"
    server.set_param_from_api("SpeedLimitMode", 3)
    if FakeParams.shared_store.get("SpeedLimitMode") != b"2":
      return False, "SpeedLimitMode must clamp local API writes to warning, not assist"

    for blocked_name in ("OffroadMode", "SpeedFromPCM", "CarrotTrafficStopEnabled", "FishopAutoOvertakeEnabled"):
      try:
        server.set_param_from_api(blocked_name, 1)
        return False, f"{blocked_name} should be read-only through local API"
      except ValueError:
        pass

    FakeParams.shared_store["IsOnroad"] = b"1"
    try:
      server.set_param_from_api("ExperimentalMode", 0)
      return False, "onroad param change was not blocked"
    except RuntimeError:
      pass
    unchanged_onroad = server.set_param_from_api("ExperimentalMode", True)
    if unchanged_onroad.get("changed"):
      return False, "same-value onroad write probe should remain unchanged"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_navigation_event_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_navigation_static_check", "selfdrive/carrot/carrot_server.py")
    route_only = {
      "route": [{"latitude": 1.2345, "longitude": 2.3456}],
      "vrtx": [{"latitude": 1.2346, "longitude": 2.3457}],
      "vpPosPointLat": 1.2345,
      "vpPosPointLon": 2.3456,
    }
    route_result = server.record_navigation_event(route_only, "route-only")
    route_event = route_result.get("event", {})
    if route_event.get("speedLimitKph") != 0.0 or route_event.get("speedLimitSourceField") != "":
      return False, "route-only navigation input must not become a speed-limit source"
    if route_result.get("phoneSpeed", {}).get("accepted") is not False:
      return False, "route-only navigation input must not update CarrotPhoneSpeedLimit"
    if FakeParams.shared_store.get("CarrotPhoneSpeedLimit", b"0").decode("utf-8") != "0":
      return False, "route-only navigation input changed stored phone speed limit"

    payload = {
      "carrotIndex": 7,
      "carrotCmd": "OVERTAKE",
      "carrotArg": "left",
      "nRoadLimitSpeed": 0,
      "nSdiSpeedLimit": 60,
      "nSdiDist": 240,
      "nSdiType": 7,
      "nSdiPlusSpeedLimit": 50,
      "nSdiPlusDist": 600,
      "nTBTDist": 500,
      "nTBTTurnType": 12,
      "speedBumpDistance": 80,
      "modelSpeedKph": 45,
      "trafficRedLightOn": True,
      "szTBTMainTextNext": "static check",
      "latitude": 1.234567,
      "longitude": 2.345678,
    }
    result = server.record_navigation_event(payload, "udp-7706")
    event = result.get("event", {})
    if not result.get("recorded") or not isinstance(event, dict):
      return False, "navigation event was not recorded"
    if not event.get("commandIgnored") or not event.get("highRiskCommandSeen"):
      return False, "high-risk navigation command was not recorded as ignored evidence"
    if event.get("speedLimitKph") != 60.0 or event.get("speedLimitSourceField") != "nSdiSpeedLimit":
      return False, "navigation event did not use SDI speed fallback"
    hazards = event.get("hazards", {})
    if hazards.get("sdi", {}).get("type") != 7 or hazards.get("sdi", {}).get("plusDistanceM") != 600.0:
      return False, "navigation event did not preserve SDI/plus camera hazard evidence"
    if hazards.get("speedBump", {}).get("distanceM") != 80.0 or hazards.get("speedBump", {}).get("available") is not True:
      return False, "navigation event did not preserve speed-bump evidence"
    if event.get("modelSpeed", {}).get("speedKph") != 45.0 or event.get("modelSpeed", {}).get("controlOutput") is not False:
      return False, "navigation event did not preserve read-only model speed evidence"
    preview = event.get("controlPreview", {})
    if preview.get("trafficStop", {}).get("candidate") is not True or preview.get("trafficStop", {}).get("controlOutput") is not False:
      return False, "navigation event did not produce read-only traffic-stop preview"
    if preview.get("autoTurn", {}).get("candidate") is not True or preview.get("activeSpeed", {}).get("candidate") is not True:
      return False, "navigation event did not produce auto-turn/active-speed evidence previews"
    if preview.get("overtake", {}).get("state") != "ignored_command" or preview.get("controlOutput") is not False:
      return False, "navigation event must keep overtake commands as ignored read-only evidence"
    raw_speed = FakeParams.shared_store.get("CarrotPhoneSpeedLimit", b"0").decode("utf-8")
    if abs(float(raw_speed) - 16.666667) > 0.001:
      return False, "navigation event did not update phone speed limit in m/s"
    raw_event = json.loads(FakeParams.shared_store.get("CarrotNavigationEvent", b"{}").decode("utf-8"))
    if raw_event.get("ignoredCommand") != "OVERTAKE":
      return False, "CarrotNavigationEvent did not persist ignored command evidence"
    if raw_event.get("controlOutput") is not False or raw_event.get("readOnly") is not True:
      return False, "CarrotNavigationEvent must persist read-only/no-control boundary"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_carrot_feature_gates_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_feature_gates_static_check", "selfdrive/carrot/carrot_server.py")
    for key in (
      "CarrotTrafficStopEnabled",
      "CarrotAutoTurnControlEnabled",
      "CarrotActiveSpeedControlEnabled",
      "CarrotLearningAutoApply",
      "FishopAutoOvertakeEnabled",
    ):
      FakeParams.shared_store[key] = b"1"

    payload = {
      "carrotCmd": "OVERTAKE",
      "nRoadLimitSpeed": 70,
      "nSdiSpeedLimit": 60,
      "nSdiDist": 200,
      "nTBTDist": 320,
      "nTBTTurnType": 12,
      "modelSpeedKph": 45,
      "trafficRedLightOn": True,
    }
    server.record_navigation_event(payload, "feature-gate-static-check")
    recommendation = {
      "source": "feature-gate-static-check",
      "created_at": 1234,
      "recommendations": {
        "CruiseMaxVals4": {
          "category": "long",
          "current": 110,
          "recommended": 120,
          "reason": "gate check",
        },
      },
    }
    FakeParams.shared_store["CarrotLearningRecommend"] = json.dumps(recommendation).encode("utf-8")

    gate = server.carrot_feature_gate_state()
    if gate.get("controlOutput") is not False or gate.get("controlOutputAllowed") is not False:
      return False, "feature gate reported control output as available"
    if gate.get("allBlocked") is not True:
      return False, "feature gate did not block every high-risk feature"
    features = gate.get("features", {})
    for key in ("trafficStop", "autoTurn", "activeSpeed", "autoTunerAutoApply", "fishopAutoOvertake"):
      feature = features.get(key, {})
      if feature.get("enabledParam") is not True:
        return False, f"{key} did not reflect enabled test param"
      if feature.get("readyForControl") is not False or feature.get("controlOutput") is not False or feature.get("readOnly") is not True:
        return False, f"{key} is not held at read-only/no-control"
      reasons = feature.get("blockingReasons", [])
      if "real_car_gate_missing" not in reasons or "control_output_disabled" not in reasons:
        return False, f"{key} missing real-car/control-output blocking reasons"
    for key in ("trafficStop", "autoTurn", "activeSpeed", "autoTunerAutoApply"):
      if features.get(key, {}).get("candidate") is not True:
        return False, f"{key} did not preserve candidate evidence"
    if "fishopAutoOvertake" not in gate.get("enabledFeatures", []):
      return False, "fishop auto overtake was not represented in enabled feature summary"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_status_broadcast_runtime() -> tuple[bool, str]:
  FakeParams.reset()
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  previous_params = sys.modules.get("openpilot.common.params")
  sys.modules["openpilot.common.params"] = params_mod
  try:
    server = import_file("alpha_carrot_server_status_static_check", "selfdrive/carrot/carrot_server.py")

    class Obj:
      def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    class FakeSm:
      alive = {
        "carState": True,
        "selfdriveState": True,
        "controlsState": True,
        "longitudinalPlanSP": True,
        "carStateSP": True,
      }

      def __init__(self):
        self.messages = {
          "carState": Obj(vEgoCluster=10.0, vEgo=9.0, vCruiseCluster=88.0, vCruise=87.0,
                          cruiseState=Obj(speedCluster=25.0, speed=24.0), logCarrot="status ok",
                          standstill=False, canValid=True),
          "selfdriveState": Obj(active=True, enabled=True),
          "controlsState": Obj(deprecated=Obj(vCruiseCluster=0.0, vCruise=0.0)),
          "longitudinalPlanSP": Obj(speedLimit=Obj(resolver=Obj(speedLimitValid=True, speedLimitFinal=20.0,
                                                                 speedLimit=18.0, sourceLabel="phone"))),
          "carStateSP": Obj(speedLimit=19.0),
        }

      def __getitem__(self, service):
        return self.messages[service]

    runtime = server.update_messaging_status_from_sm(FakeSm())
    if runtime.get("vEgoKph") != 36.0 or runtime.get("vCruiseKph") != 88.0:
      return False, "messaging status helper did not derive car speed or cruise speed"
    if runtime.get("carCruiseSpeedKph") != 90.0 or runtime.get("speedLimitKph") != 72.0:
      return False, "messaging status helper did not derive cluster cruise or speed-limit state"
    if runtime.get("logCarrot") != "status ok":
      return False, "messaging status helper did not preserve log_carrot evidence"
    if runtime.get("active") is not True or runtime.get("enabled") is not True or runtime.get("canValid") is not True:
      return False, "messaging status helper did not derive selfdrive/CAN state"

    server.record_navigation_event({
      "nRoadLimitSpeed": 0,
      "nSdiSpeedLimit": 60,
      "nSdiDist": 240,
      "nSdiType": 7,
      "nSdiPlusDist": 600,
      "nTBTDist": 500,
      "nTBTTurnType": 12,
      "speedBumpDistance": 80,
      "modelSpeedKph": 45,
      "trafficRedLightOn": True,
      "szTBTMainTextNext": "status check",
    }, "udp-7706")
    FakeParams.shared_store["IsOnroad"] = b"1"
    payload = server.build_status_payload({
      "available": True,
      "lastUpdateAt": 1234.0,
      "vEgoKph": 48.6,
      "vCruiseKph": 82.0,
      "carCruiseSpeedKph": 80.0,
      "logCarrot": "status ok",
      "active": True,
      "enabled": True,
      "standstill": False,
      "canValid": True,
      "speedLimitKph": 60.0,
      "speedLimitSource": "phone",
    }, {
      "available": True,
      "port": server.NAVI_HTTP_PORT,
      "lastError": "",
    }, {
      "available": True,
      "port": server.NAVI_TCP_PORT,
      "lastError": "",
    })
    for key in ("Carrot2", "IsOnroad", "CarrotRouteActive", "ip", "port", "navi_http_port", "navi_tcp_port", "log_carrot",
                "active", "v_ego_kph", "v_cruise_kph", "carcruiseSpeed", "tbt_dist", "sdi_dist", "xState", "trafficState"):
      if key not in payload:
        return False, f"status payload missing {key}"
    if payload.get("CarrotRouteActive") is not True or payload.get("port") != server.NAVIGATION_UDP_PORT:
      return False, "status payload did not expose CarrotMan-compatible discovery fields"
    if payload.get("navi_http_port") != server.NAVI_HTTP_PORT or payload.get("naviHttpAvailable") is not True:
      return False, "status payload did not expose the active navigation HTTP compatibility server"
    if payload.get("navi_tcp_port") != server.NAVI_TCP_PORT or payload.get("naviTcpAvailable") is not True:
      return False, "status payload did not expose the active navigation TCP compatibility server"
    if payload.get("carrotManCompatible") is not True or payload.get("carrotManControlStateAvailable") is not False:
      return False, "status payload did not declare the read-only CarrotMan compatibility boundary"
    if payload.get("log_carrot") != "status ok":
      return False, "status payload did not expose log_carrot evidence"
    if payload.get("active") is not True or payload.get("v_ego_kph") != 48.6 or payload.get("v_cruise_kph") != 82.0:
      return False, "status payload did not expose runtime messaging state"
    if payload.get("carcruiseSpeed") != 80.0 or payload.get("speedLimitKph") != 60.0 or payload.get("speedLimitSource") != "phone":
      return False, "status payload did not expose cruise/speed-limit messaging state"
    if payload.get("messagingAvailable") is not True or payload.get("messagingLastUpdateAt") != 1234.0:
      return False, "status payload did not expose messaging evidence"
    if payload.get("tbt_dist") != 500 or payload.get("sdi_dist") != 240:
      return False, "status payload did not expose latest navigation distances"
    if payload.get("sdi_speed") != 60 or payload.get("phoneSpeedLimitKph") != 60.0:
      return False, "status payload did not expose latest SDI/phone speed"
    if payload.get("sdi_type") != 7 or payload.get("sdi_plus_dist") != 600.0:
      return False, "status payload did not expose SDI type/plus-distance evidence"
    if payload.get("speedBumpAvailable") is not True or payload.get("speedBumpDist") != 80.0:
      return False, "status payload did not expose speed-bump evidence"
    if payload.get("modelSpeedAvailable") is not True or payload.get("modelSpeedKph") != 45.0:
      return False, "status payload did not expose model-speed evidence"
    preview = payload.get("carrotControlPreview", {})
    if preview.get("trafficStop", {}).get("controlOutput") is not False or preview.get("trafficStop", {}).get("candidate") is not True:
      return False, "status payload did not expose read-only traffic-stop preview"
    if preview.get("autoTurn", {}).get("candidate") is not True or preview.get("activeSpeed", {}).get("candidate") is not True:
      return False, "status payload did not expose auto-turn/active-speed previews"
    if payload.get("navigationHazards", {}).get("controlOutput") is not False or payload.get("navigationModelSpeed", {}).get("controlOutput") is not False:
      return False, "status payload navigation evidence must remain read-only"
    if payload.get("phoneSpeedLimitFresh") is not True or payload.get("phoneSpeedLimitEnabled") is not True:
      return False, "status payload did not expose phone speed freshness/enabled evidence"
    if payload.get("speedLimitPolicyName") != "phone_priority" or payload.get("speedLimitModeName") != "information":
      return False, "status payload did not expose speed-limit policy/mode evidence"
    if payload.get("speedLimitOffsetTypeName") != "off" or payload.get("speedLimitOffsetValue") != 0 or payload.get("speedLimitOffsetUnit") != "":
      return False, "status payload did not expose zero-offset evidence"
    evidence = payload.get("speedLimitEvidence", {})
    if evidence.get("resolvedSource") != "phone" or evidence.get("phone", {}).get("fresh") is not True:
      return False, "status payload did not expose nested speed-limit evidence"
    if payload.get("xState") != 0 or payload.get("trafficState") != 0:
      return False, "xState and trafficState must stay inert until Carrot control migration"
    if payload.get("controlOutput") is not False:
      return False, "status payload must explicitly remain read-only"

    navi_result = server.record_navi_http_event(
      {"navi_http_state": server.default_navi_http_state()},
      {"sinf": {"distance": 123, "redLightOn": True, "redLightRemainTime": 8}},
      "",
    )
    if not navi_result.get("recorded") or navi_result.get("type") != "sinf":
      return False, "navigation HTTP compatibility handler did not record sinf"
    if navi_result.get("controlOutput") is not False:
      return False, "navigation HTTP compatibility handler must remain read-only"
    raw_navi = json.loads(FakeParams.shared_store.get("CarrotNaviEvent", b"{}").decode("utf-8"))
    if raw_navi.get("type") != "sinf" or raw_navi.get("controlOutput") is not False:
      return False, "navigation HTTP compatibility handler did not persist a read-only event"
    tcp_app = {"navi_tcp_state": server.default_navi_tcp_state()}
    tcp_result = server.record_navi_tcp_event(tcp_app, {"rgdata": {"nRoadLimitSpeed": 70, "nSdiSpeedLimit": 60, "nTBTDist": 456}})
    if not tcp_result.get("recorded") or tcp_result.get("type") != "rgdata":
      return False, "navigation TCP compatibility handler did not record rgdata"
    if tcp_result.get("controlOutput") is not False:
      return False, "navigation TCP compatibility handler must remain read-only"
    if tcp_app["navi_tcp_state"].get("receivedTypes", {}).get("rgdata") != 1:
      return False, "navigation TCP compatibility handler did not update TCP evidence state"
    return True, ""
  except Exception as exc:
    return False, str(exc)
  finally:
    if previous_params is None:
      sys.modules.pop("openpilot.common.params", None)
    else:
      sys.modules["openpilot.common.params"] = previous_params


def check_fishop_release_gate_runtime() -> tuple[bool, str]:
  try:
    snapshot = import_file("alpha_snapshot_release_gate_static_check", "scripts/personal/sunnypilot_c3_alpha_snapshot.py")
    safe_params = {
      "SunnylinkEnabled": "0",
      "EnableSunnylinkUploader": "0",
      "OnroadUploads": "0",
    }
    process = {"available": True, "cloudForbiddenSeen": False}
    car_params = {"available": True, "carFingerprint": "KIA_SELTOS_2023", "dashcamOnly": False}
    car_params_sp = {"available": True, "enhancedSccDetected": True, "esccSafetyParamSet": True}
    messaging = {"enabled": True, "last": {"pandaStates": [{"controlsAllowed": True, "safetyModel": "hyundai"}]}}
    fishop = {
      "inputAvailable": True,
      "parseError": "",
      "snapshot": {
        "sensorOnline": True,
        "lane": {"fresh": True},
        "blindspot": {"fresh": True},
        "overtake": {"suggestionPreview": {
          "readOnly": True,
          "controlOutput": False,
          "emitsLateralCommand": False,
          "stage": "display_only",
          "decision": "ready_for_suggestion",
        }},
      },
    }
    gate = snapshot.summarize_fishop_release_gate(safe_params, process, car_params, car_params_sp, messaging, fishop)
    if gate.get("readyForNextStageReview") is not True or gate.get("blockingChecks") != []:
      return False, "complete synthetic evidence did not pass the fishop release gate"
    if gate.get("checks", {}).get("esccDetected", {}).get("status") != "pass":
      return False, "ESCC evidence check did not pass with enhanced SCC and ESCC safetyParam"

    process["cloudForbiddenSeen"] = True
    blocked = snapshot.summarize_fishop_release_gate(safe_params, process, car_params, car_params_sp, messaging, fishop)
    if blocked.get("readyForNextStageReview") is not False or "cloudProcessesAbsent" not in blocked.get("blockingChecks", []):
      return False, "cloud process evidence did not block the fishop release gate"

    process["cloudForbiddenSeen"] = False
    car_params_sp["enhancedSccDetected"] = False
    blocked = snapshot.summarize_fishop_release_gate(safe_params, process, car_params, car_params_sp, messaging, fishop)
    if blocked.get("readyForNextStageReview") is not False or "esccDetected" not in blocked.get("blockingChecks", []):
      return False, "missing ESCC evidence did not block the fishop release gate"
    return True, ""
  except Exception as exc:
    return False, str(exc)


def visible_korean_text_report() -> str:
  korean_re = re.compile(r"[가-힣]")
  scan_roots = (
    "README.md",
    "docs/personal",
    "selfdrive/carrot",
    "selfdrive/ui/layouts",
    "selfdrive/ui/mici/layouts",
    "selfdrive/ui/sunnypilot/layouts",
    "selfdrive/ui/sunnypilot/mici/layouts",
    "selfdrive/ui/sunnypilot/onroad",
    "selfdrive/ui/sunnypilot/widgets",
    "system/ui/lib",
    "system/ui/sunnypilot/widgets",
    "system/ui/widgets",
    "sunnypilot/sunnylink/settings_ui_src",
  )
  suffixes = {".cc", ".h", ".html", ".json", ".md", ".py", ".ts", ".tsx", ".yaml", ".yml"}
  skipped = {
    Path("selfdrive/ui/translations/app_ko.po"),
  }
  skipped_dirs = {
    Path("selfdrive/ui/translations"),
  }
  hits: list[str] = []

  for root_rel in scan_roots:
    root = ROOT / root_rel
    paths = [root] if root.is_file() else sorted(root.rglob("*"))
    for path in paths:
      if not path.is_file() or path.suffix not in suffixes:
        continue
      rel = path.relative_to(ROOT)
      if rel in skipped:
        continue
      if any(rel == skipped_dir or skipped_dir in rel.parents for skipped_dir in skipped_dirs):
        continue
      if path.stat().st_size > 200_000:
        continue
      text = path.read_text(encoding="utf-8", errors="ignore")
      for line_no, line in enumerate(text.splitlines(), start=1):
        if korean_re.search(line):
          hits.append(f"{rel}:{line_no}: {line.strip()[:120]}")
          if len(hits) >= 8:
            return "; ".join(hits)
  return ""


def main() -> int:
  failures = 0

  process_config = read("system/manager/process_config.py")
  for proc_name in (
    "manage_athenad",
    '"uploader"',
    "manage_sunnylinkd",
    "sunnylink_registration_manager",
    "statsd_sp",
    "backup_manager",
    "sunnylink_uploader",
  ):
    failures += not require(
      f"cloud process disabled: {proc_name}",
      proc_name not in process_config,
      "process_config.py still references a disabled cloud/upload process",
    )
  failures += not require("models_manager only offroad", 'PythonProcess("models_manager", "sunnypilot.models.manager", only_offroad)' in process_config,
                          "models_manager must remain an offroad-only process")
  failures += not require("stock modeld guarded by stock runner", 'PythonProcess("modeld", "selfdrive.modeld.modeld", and_(only_onroad, is_stock_model))' in process_config,
                          "stock modeld must only run when the active runner is stock")
  failures += not require("tinygrad modeld guarded by tinygrad runner", 'NativeProcess("modeld_tinygrad", "sunnypilot/modeld_v2", ["./modeld"], and_(only_onroad, is_tinygrad_model))' in process_config,
                          "modeld_tinygrad must only run onroad when the active runner is tinygrad")
  failures += not require("local statsd retained", 'PythonProcess("statsd", "system.statsd", always_run)' in process_config,
                          "local system.statsd should stay available for local-only stats evidence")
  failures += not require("local carrot web retained", 'PythonProcess("carrot_server", "selfdrive.carrot.carrot_server", always_run)' in process_config,
                          "local Carrot Web server must be registered as an always-run local process")
  ok, detail = check_services_contract()
  failures += not require("services contract check", ok, detail or "cereal services contract check failed")

  params = read("common/params_keys.h")
  failures += not require("OffroadMode param exists", '{"OffroadMode", {CLEAR_ON_MANAGER_START, BOOL}}' in params,
                          "OffroadMode must be the only Always Offroad param")
  failures += not require("no AlwaysOffline alias", "AlwaysOffline" not in params and "AlwaysOffroad" not in params,
                          "do not add confusing AlwaysOffline/AlwaysOffroad aliases in alpha")
  failures += not require("Sunnylink default off", '{"SunnylinkEnabled", {PERSISTENT, BOOL, "0"}}' in params,
                          "SunnylinkEnabled must default to 0")
  failures += not require("OnroadUploads default off", '{"OnroadUploads", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "OnroadUploads must default to 0 even though uploader is removed")
  failures += not require("CarrotMapOverlay default off", '{"CarrotMapOverlayEnabled", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "CarrotMapOverlayEnabled must default to 0")
  failures += not require("Carrot learning active default off", '{"CarrotLearningActive", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "CarrotLearningActive must default to 0")
  failures += not require("Carrot learning auto-apply default off", '{"CarrotLearningAutoApply", {PERSISTENT | BACKUP, BOOL, "0"}}' in params,
                          "CarrotLearningAutoApply must default to 0")
  for key in (
    "CarrotLearningData",
    "CarrotLearningRecommend",
    "CarrotLearningPopupReady",
    "CarrotLearningHistory",
    "CarrotLearningPopupSource",
    "CarrotLearningApply",
    "CarrotLearningIgnore",
    "CarrotLearningClear",
    "CarrotTunerApplyLat",
    "CarrotTunerApplyLong",
    "CarrotTunerFactoryReset",
    "CarrotDSPRecommend",
  ):
    failures += not require(f"Auto-Tuner param exists: {key}", f'{{"{key}", ' in params,
                            f"{key} must be registered for Auto-Tuner migration")
  for key in (
    "CruiseMaxVals0",
    "CruiseMaxVals1",
    "CruiseMaxVals2",
    "CruiseMaxVals3",
    "CruiseMaxVals4",
    "CruiseMaxVals5",
    "CruiseMaxVals6",
    "TFollowGap1",
    "TFollowGap2",
    "TFollowGap3",
    "TFollowGap4",
    "JLeadFactor3",
    "PathOffset",
    "SteerActuatorDelay",
    "SteerRatioRate",
    "DynamicTFollow",
    "TFollowDecelBoost",
    "StopDistanceCarrot",
  ):
    failures += not require(f"Auto-Tuner target param exists: {key}", f'{{"{key}", ' in params,
                            f"{key} must be registered before Carrot control migration")
  failures += not require("Carrot phone limit enabled", '{"CarrotPhoneSpeedLimitEnabled", {PERSISTENT | BACKUP, BOOL, "1"}}' in params,
                          "CarrotPhoneSpeedLimitEnabled must exist and default to 1")
  failures += not require("Carrot navigation event param exists", '{"CarrotNavigationEvent", {CLEAR_ON_MANAGER_START, JSON}}' in params,
                          "CarrotNavigationEvent must record the latest local navigation input and clear on manager start")
  for key in ("CarrotNaviDebug", "CarrotNaviEvent", "CarrotNaviImage"):
    failures += not require(f"Carrot navi HTTP param exists: {key}", f'{{"{key}", {{CLEAR_ON_MANAGER_START, JSON}}}}' in params,
                            f"{key} must record local navigation HTTP evidence and clear on manager start")
  failures += not require("SpeedLimitPolicy phone priority default", '{"SpeedLimitPolicy", {PERSISTENT | BACKUP, INT, "5"}}' in params,
                          "SpeedLimitPolicy must default to phone_priority")
  failures += not require("SpeedLimitOffsetType default off", '{"SpeedLimitOffsetType", {PERSISTENT | BACKUP, INT, "0"}}' in params,
                          "SpeedLimitOffsetType must default to off")
  failures += not require("SpeedLimitValueOffset default zero", '{"SpeedLimitValueOffset", {PERSISTENT | BACKUP, INT, "0"}}' in params,
                          "SpeedLimitValueOffset must default to 0")
  for key in (
    "FishopAutoOvertakeEnabled",
    "FishopLaneCurveEnabled",
    "FishopLidarBlindspotEnabled",
    "FishopLidarLaneDataEnabled",
  ):
    failures += not require(f"{key} default off", f'{{"{key}", {{PERSISTENT | BACKUP, BOOL, "0"}}}}' in params,
                            f"{key} must exist and default to 0")

  fishop_hardware = read("selfdrive/carrot/fishop_hardware.py")
  carrot_learning = read("selfdrive/carrot/carrot_learning.py")
  carrot_server = read("selfdrive/carrot/carrot_server.py")
  fishop_sample = read("scripts/personal/fishop_hardware_sample.py")
  alpha_snapshot = read("scripts/personal/sunnypilot_c3_alpha_snapshot.py")
  failures += not require("Auto-Tuner learner module exists", "class CarrotLearner" in carrot_learning
                          and "def apply_recommendations" in carrot_learning,
                          "CarrotLearner core module must exist in alpha")
  failures += not require("Auto-Tuner learner default uses bool gate", 'get_bool("CarrotLearningActive")' in carrot_learning,
                          "CarrotLearner must use the alpha bool default gate")
  failures += not require("Auto-Tuner apply blocked onroad", 'get_bool("IsOnroad")' in carrot_learning
                          and "if self.is_onroad()" in carrot_learning,
                          "CarrotLearner must not apply recommendations while onroad")
  ok, detail = check_carrot_learning_runtime()
  failures += not require("Auto-Tuner runtime guard", ok, detail or "runtime guard check failed")
  ok, detail = check_carrot_learning_api_runtime()
  failures += not require("Auto-Tuner Web recommendation/applied value runtime", ok, detail or "Auto-Tuner Web value separation runtime check failed")
  failures += not require("Carrot Web local server exists", "LOCAL_WEB_PORT = 7000" in carrot_server
                          and "def make_app" in carrot_server and "web.run_app" in carrot_server,
                          "carrot_server must provide the local port-7000 aiohttp service")
  ok, detail = check_carrot_web_asset_syntax()
  failures += not require("Carrot Web JS/JSON/YAML syntax", ok, detail or "Carrot Web/settings UI asset syntax check failed")
  for route in ("/api/health", "/api/params_bulk", "/api/param_set", "/api/status_broadcast", "/api/carrot_learning", "/api/carrot_feature_gates", "/api/fishop_hardware", "/api/navigation_event", "/api/phone_speed_limit"):
    failures += not require(f"Carrot Web route exists: {route}", route in carrot_server,
                            f"carrot_server missing {route}")
  failures += not require("Carrot Web params API whitelist", "PARAM_API_DEFS" in carrot_server
                          and '"ExperimentalMode": {"type": "bool", "default": False, "writable": True}' in carrot_server
                          and '"OffroadMode": {"type": "bool", "default": False, "writable": False}' in carrot_server
                          and '"SpeedFromPCM": {"type": "int", "default": 1, "writable": False' in carrot_server
                          and '"FishopAutoOvertakeEnabled": {"type": "bool", "default": False, "writable": False}' in carrot_server,
                          "Carrot Web params API must expose only an explicit whitelist and keep high-risk/Mazda-only params read-only")
  failures += not require("Carrot Web params API preserves Navipilot response contract",
                          'app.router.add_post("/api/params_bulk", api_params_bulk)' in carrot_server
                          and '"has_params": params is not None' in carrot_server
                          and '"source": "local_safe_whitelist"' in carrot_server
                          and "def get_param_values" in carrot_server
                          and "def set_param_value" in carrot_server,
                          "local params API must remain compatible with jixie Navipilot /api/params_bulk and /api/param_set callers")
  failures += not require("Carrot Web params API blocks onroad changes", 'params.get_bool("IsOnroad") and changed' in carrot_server
                          and "Cannot change params while onroad" in carrot_server,
                          "param_set must reject changed values while onroad")
  failures += not require("Carrot Web params API clamps active speed mode", '"SpeedLimitMode": {"type": "int", "default": 1, "writable": True, "min": 0, "max": 2}' in carrot_server,
                          "local param_set must not enable SpeedLimitMode assist through the phone API")
  ok, detail = check_params_api_runtime()
  failures += not require("Carrot Web params API runtime", ok, detail or "params API runtime check failed")
  failures += not require("Carrot Web status broadcast exists", "STATUS_BROADCAST_PORT = 7705" in carrot_server
                          and "STATUS_BROADCAST_TARGETS" in carrot_server
                          and "def build_status_payload" in carrot_server
                          and "status_broadcast_loop" in carrot_server,
                          "Carrot Web must provide a local UDP 7705 status broadcaster for Navipilot")
  failures += not require("Carrot Web status broadcast reads messaging",
                          "MESSAGING_STATUS_SERVICES" in carrot_server
                          and '"carState"' in carrot_server and '"selfdriveState"' in carrot_server
                          and '"longitudinalPlanSP"' in carrot_server and '"carStateSP"' in carrot_server
                          and "from cereal import messaging" in carrot_server
                          and "messaging.SubMaster(list(MESSAGING_STATUS_SERVICES))" in carrot_server
                          and "update_messaging_status_from_sm" in carrot_server,
                          "UDP 7705 status broadcast must read carState/selfdriveState/speed-limit state through a local SubMaster cache")
  for key in ("Carrot2", "IsOnroad", "CarrotRouteActive", "ip", "port", "navi_http_port", "navi_tcp_port", "log_carrot",
              "active", "v_ego_kph", "v_cruise_kph", "carcruiseSpeed", "tbt_dist", "sdi_dist", "sdi_type",
              "speedBumpDist", "modelSpeedKph", "carrotControlPreview", "navigationHazards", "xState", "trafficState"):
    failures += not require(f"7705 status key exists: {key}", f'"{key}"' in carrot_server,
                            f"UDP 7705 status broadcast must include {key}")
  failures += not require("Carrot Web status broadcast declares compatibility boundary",
                          "carrotManCompatible" in carrot_server
                          and "carrotManControlStateAvailable" in carrot_server
                          and "naviHttpAvailable" in carrot_server
                          and "NAVI_HTTP_PORT = 7713" in carrot_server
                          and "NAVI_TCP_PORT = 7712" in carrot_server
                          and "start_navi_tcp" in carrot_server
                          and "asyncio.start_server" in carrot_server
                          and "start_navi_http" in carrot_server
                          and "web.TCPSite(runner, DEFAULT_HOST, NAVI_HTTP_PORT)" in carrot_server,
                          "UDP 7705 status must be compatible with CP app discovery and expose bound 7712/7713 services only when available")
  failures += not require("Carrot Web status broadcast local-only", "255.255.255.255" in carrot_server
                          and "127.0.0.1" in carrot_server and "allow_broadcast=True" in carrot_server
                          and "controlOutput" in carrot_server,
                          "UDP 7705 broadcast must stay local/LAN and explicitly read-only")
  ok, detail = check_status_broadcast_runtime()
  failures += not require("Carrot Web status broadcast runtime", ok, detail or "status broadcast runtime check failed")
  failures += not require("Carrot Web navigation UDP input", "NAVIGATION_UDP_PORT = 7706" in carrot_server
                          and "class NavigationUdpProtocol" in carrot_server
                          and "record_navigation_event(payload, \"udp-7706\")" in carrot_server,
                          "Carrot Web must listen for local Navipilot/APN UDP 7706 navigation JSON")
  failures += not require("Carrot Web navigation input remains evidence-only", "CarrotNavigationEvent" in carrot_server
                          and "commandIgnored" in carrot_server and "highRiskCommandSeen" in carrot_server
                          and "HIGH_RISK_NAV_COMMANDS" in carrot_server,
                          "navigation input must record commands as ignored evidence, not execute them")
  failures += not require("Carrot Web navigation evidence covers hazards and model speed",
                          "NAVIGATION_SPEED_BUMP_DISTANCE_FIELDS" in carrot_server
                          and "NAVIGATION_MODEL_SPEED_KPH_FIELDS" in carrot_server
                          and '"hazards": hazards' in carrot_server
                          and '"modelSpeed": model_speed' in carrot_server
                          and '"controlPreview"' in carrot_server,
                          "navigation input must preserve SDI, speed-bump, model-speed, and control-preview evidence")
  failures += not require("Carrot Web navigation evidence panel",
                          'id="navigation-panel"' in carrot_server
                          and "refreshNavigationEvidence" in carrot_server
                          and 'fetch("/api/navigation_event", {cache: "no-store"})' in carrot_server
                          and 'id="navigation-speed-bump"' in carrot_server
                          and 'id="navigation-model-speed"' in carrot_server
                          and 'id="navigation-traffic-stop"' in carrot_server
                          and 'id="navigation-active-speed"' in carrot_server,
                          "Carrot Web home page must expose read-only navigation, speed-bump, model-speed, and control-preview evidence")
  failures += not require("Carrot Web navigation HTTP compatibility exists",
                          '"/api/navi/{tmap_version}"' in carrot_server
                          and '"/api/navi"' in carrot_server
                          and "record_navi_http_event" in carrot_server
                          and "CarrotNaviEvent" in carrot_server
                          and "CarrotNaviDebug" in carrot_server
                          and "CarrotNaviImage" in carrot_server,
                          "Carrot Web must provide the old CarrotMan /api/navi HTTP compatibility entry points")
  failures += not require("Carrot Web navigation TCP compatibility exists",
                          "handle_navi_tcp_client" in carrot_server
                          and "record_navi_tcp_event" in carrot_server
                          and "NAVI_TCP_MAX_LINE_BYTES" in carrot_server
                          and '"tcp-7712"' in carrot_server,
                          "Carrot Web must provide the old CarrotMan 7712 line-delimited TCP navigation compatibility input")
  failures += not require("Carrot Web navigation HTTP remains evidence-only",
                          "controlOutput\": False" in carrot_server
                          and "record_navigation_event(nav_payload" in carrot_server
                          and "NAVI_IMAGE_BASE64_MAX_CHARS" in carrot_server,
                          "navigation HTTP/TCP input must persist evidence and sanitized navigation state without control output")
  for forbidden in ("PubMaster", "CarControl", "sendcan", "desire_helper", "LateralPlan"):
    failures += not require(f"Carrot Web navigation omits control output {forbidden}", forbidden not in carrot_server,
                            "navigation UDP/API input must not publish controls or touch lane-change/planner outputs")
  ok, detail = check_navigation_event_runtime()
  failures += not require("Carrot Web navigation runtime", ok, detail or "navigation runtime check failed")
  failures += not require("Carrot Web feature gate API",
                          "HIGH_RISK_FEATURE_GATES" in carrot_server
                          and "def carrot_feature_gate_state" in carrot_server
                          and "def api_carrot_feature_gates" in carrot_server
                          and '"readyForControl": False' in carrot_server
                          and '"controlOutputAllowed": False' in carrot_server
                          and '"real_car_gate_missing"' in carrot_server
                          and 'app.router.add_get("/api/carrot_feature_gates", api_carrot_feature_gates)' in carrot_server,
                          "Carrot high-risk controls must be exposed through a read-only real-car gate API")
  ok, detail = check_carrot_feature_gates_runtime()
  failures += not require("Carrot Web feature gate runtime", ok,
                          detail or "Carrot feature gate runtime check failed")
  failures += not require("Carrot Web phone speed API writes resolver params",
                          "def set_phone_speed_limit" in carrot_server
                          and "CarrotPhoneSpeedLimitUpdatedAt" in carrot_server
                          and "CarrotPhoneSpeedLimitSource" in carrot_server
                          and "KPH_TO_MS" in carrot_server
                          and "params.put(key, float(value))" in carrot_server,
                          "Carrot Web must expose a local phone speed API that writes resolver params in m/s")
  failures += not require("Carrot Web phone speed API reports freshness",
                          "PHONE_SPEED_LIMIT_MAX_AGE_S = 10.0" in carrot_server
                          and '"fresh": fresh' in carrot_server,
                          "Carrot Web phone speed state must report the same freshness window as the resolver")
  failures += not require("Carrot Web speed-limit evidence exposes offset and freshness",
                          "def speed_limit_evidence_state" in carrot_server
                          and "SPEED_LIMIT_OFFSET_TYPE_NAMES" in carrot_server
                          and '"speedLimitEvidence": speed_limit_evidence' in carrot_server
                          and '"phoneSpeedLimitAgeSec"' in carrot_server
                          and '"speedLimitOffsetTypeName"' in carrot_server
                          and '"speedLimitOffsetValue"' in carrot_server
                          and '"speedLimitOffsetUnit"' in carrot_server,
                          "Carrot Web status/health must expose source, phone freshness, offset type/value/unit, and nested speed-limit evidence")
  ok, detail = check_phone_speed_limit_runtime()
  failures += not require("Carrot Web phone speed runtime", ok, detail or "phone speed runtime check failed")
  failures += not require("Carrot Web blocks onroad Auto-Tuner apply", 'params.get_bool("IsOnroad")' in carrot_server
                          and "Cannot apply Auto-Tuner recommendations while onroad" in carrot_server,
                          "Carrot Web must refuse Auto-Tuner apply while onroad")
  failures += not require("Carrot Web distinguishes Auto-Tuner recommendation and applied values",
                          '"capturedCurrentValue"' in carrot_server
                          and '"currentValue"' in carrot_server
                          and '"recommendedValue"' in carrot_server
                          and '"appliedValue"' in carrot_server
                          and '"liveDelta"' in carrot_server
                          and '"recommendationSummary"' in carrot_server,
                          "Carrot Web must clearly distinguish captured/current, recommended, and applied Auto-Tuner values")
  failures += not require("Carrot Web Auto-Tuner local panel",
                          'id="auto-tuner-panel"' in carrot_server
                          and "refreshAutoTuner" in carrot_server
                          and "postAutoTunerAction" in carrot_server
                          and 'fetch("/api/carrot_learning", {cache: "no-store"})' in carrot_server
                          and 'fetch("/api/carrot_learning", {' in carrot_server
                          and 'method: "POST"' in carrot_server
                          and 'JSON.stringify({action})' in carrot_server
                          and 'id="auto-tuner-apply"' in carrot_server
                          and 'id="auto-tuner-ignore"' in carrot_server
                          and 'id="auto-tuner-clear"' in carrot_server
                          and 'id="auto-tuner-recommendations"' in carrot_server
                          and "captured/current/recommended" in carrot_server
                          and "renderRecommendations" in carrot_server
                          and "renderAutoTuner" in carrot_server,
                          "Carrot Web must expose the local Auto-Tuner state panel with read, apply, ignore, and clear actions")
  failures += not require("Carrot Web control gate panel",
                          'id="control-gates-panel"' in carrot_server
                          and "refreshFeatureGates" in carrot_server
                          and 'fetch("/api/carrot_feature_gates", {cache: "no-store"})' in carrot_server
                          and "gateSummary" in carrot_server
                          and 'id="control-gate-traffic-stop"' in carrot_server
                          and 'id="control-gate-auto-turn"' in carrot_server
                          and 'id="control-gate-active-speed"' in carrot_server
                          and 'id="control-gate-auto-tuner"' in carrot_server
                          and 'id="control-gate-fishop-overtake"' in carrot_server,
                          "Carrot Web home page must show read-only high-risk control gate status")
  failures += not require("Carrot Web fishop hardware read-only panel",
                          'id="fishop-panel"' in carrot_server
                          and "refreshFishopHardware" in carrot_server
                          and 'fetch("/api/fishop_hardware", {cache: "no-store"})' in carrot_server
                          and 'id="fishop-lane-curve"' in carrot_server
                          and 'id="fishop-lane-quality"' in carrot_server
                          and 'id="fishop-lidar-blind"' in carrot_server
                          and 'id="fishop-targets"' in carrot_server
                          and 'id="fishop-dynamic-risk"' in carrot_server
                          and 'id="fishop-overtake-path"' in carrot_server
                          and 'id="fishop-overtake-suggestion"' in carrot_server
                          and "laneQualitySummary" in carrot_server
                          and "dynamicRiskSummary" in carrot_server
                          and "suggestionSummary" in carrot_server
                          and "snapshot.controlOutputEnabled ? \"control enabled\" : \"read-only\"" in carrot_server
                          and 'method:' not in carrot_server[carrot_server.index('async function refreshFishopHardware'):carrot_server.index('setInterval(refreshFishopHardware')],
                          "Carrot Web must show fishop lane/curve/lidar/target evidence through read-only GET only")
  for forbidden in ("requests.", "urllib.", "websocket", "ClientSession", "common.api", "SunnylinkApi", "DongleId"):
    failures += not require(f"Carrot Web omits cloud client token {forbidden}", forbidden not in carrot_server,
                            "local Carrot Web must not include outbound cloud/client code")
  for forbidden in ("subprocess", "tmux", "terminal", "shell=True", "os.system"):
    failures += not require(f"Carrot Web alpha omits high-risk tool {forbidden}", forbidden not in carrot_server,
                            "alpha Carrot Web should not expose terminal/tools before explicit migration gates")
  failures += not require("fishop hardware read-only module exists", "class FishopHardwareState" in fishop_hardware
                          and "CONTROL_OUTPUT_ENABLED = False" in fishop_hardware
                          and "FISHOP_PROTOCOL" in fishop_hardware,
                          "fishop hardware parser must exist and remain read-only")
  failures += not require("fishop hardware parser covers latest protocol fields",
                          "leftLaneBlind" in fishop_hardware
                          and "rightLaneBlind" in fishop_hardware
                          and "lf_vrel" in fishop_hardware
                          and "distTimeMs" in fishop_hardware
                          and "LANE_QUALITY_KEYS" in fishop_hardware
                          and "laneProbabilities" in fishop_hardware
                          and "roadEdgeDistancesM" in fishop_hardware
                          and "modelV2.orientationRate.z fallback" in fishop_hardware
                          and "leftLidarOnline" in fishop_hardware
                          and "rightCameraOnline" in fishop_hardware
                          and "lidar_car_lblind" in fishop_hardware
                          and "remoteCmd" in fishop_hardware
                          and "DYNAMIC_BLIND_REFERENCE_DEFAULTS" in fishop_hardware
                          and "def _side_object_risk" in fishop_hardware
                          and '"dynamicBlind": self.dynamic_blind(targets_fresh)' in fishop_hardware
                          and "_overtake_suggestion_preview" in fishop_hardware
                          and '"suggestionPreview"]' in fishop_hardware
                          and '"directionality": {' in fishop_hardware
                          and "fishop/openpilot:selfdrive/carrot/amap_navi.py" in fishop_hardware,
                          "fishop hardware parser must preserve lane, lidar, camera, target, dynamic-risk, and command evidence fields from amap_navi.py")
  for forbidden in ("socket", "PubMaster", "SubMaster", "CarControl", "CANParser", "sendto", ".bind(", "desire_helper", "blinker_ctrl"):
    failures += not require(f"fishop hardware parser omits {forbidden}", forbidden not in fishop_hardware,
                            "fishop hardware parser must not open network sockets, publish controls, or touch lane-change control")
  ok, detail = check_fishop_overtake_safety_contract()
  failures += not require("fishop auto-overtake safety chain gate", ok, detail or "fishop auto-overtake safety chain gate failed")
  failures += not require("fishop hardware sample tool exists", "FishopHardwareState" in fishop_sample and "SAMPLE_PAYLOADS" in fishop_sample,
                          "fishop hardware sample tool must normalize captured JSON payloads")
  failures += not require("alpha snapshot tool exists", "CarrotPilot-C3-ESCC SunnyPilot Alpha Snapshot" in alpha_snapshot
                          and "MESSAGING_SERVICES" in alpha_snapshot and "fishopHardware" in alpha_snapshot,
                          "alpha snapshot must collect model, process, params, and fishop evidence")
  failures += not require("alpha snapshot records CarParamsSP ESCC evidence",
                          "def summarize_car_params_sp" in alpha_snapshot
                          and '"enhancedSccDetected"' in alpha_snapshot
                          and '"esccSafetyParamSet"' in alpha_snapshot
                          and '"carParamsSP": car_params_sp' in alpha_snapshot,
                          "alpha snapshot must decode CarParamsSP and expose ENHANCED_SCC/ESCC safetyParam evidence")
  failures += not require("alpha snapshot records fishop release gate",
                          "def summarize_fishop_release_gate" in alpha_snapshot
                          and '"fishopReleaseGate": summarize_fishop_release_gate' in alpha_snapshot
                          and '"readyForNextStageReview"' in alpha_snapshot
                          and '"requiredBeforeControl"' in alpha_snapshot
                          and "--require-fishop-release-gate" in alpha_snapshot,
                          "alpha snapshot must summarize the fishop pre-control evidence gate")
  ok, detail = check_fishop_release_gate_runtime()
  failures += not require("alpha snapshot fishop release gate runtime", ok,
                          detail or "fishop release gate runtime check failed")
  failures += not require("alpha snapshot records Auto-Tuner summary", '"CarrotLearningActive"' in alpha_snapshot
                          and '"autoTuner"' in alpha_snapshot and "summarize_auto_tuner" in alpha_snapshot
                          and '"recommendationsPreview"' in alpha_snapshot and '"appliedRecommendationCount"' in alpha_snapshot,
                          "alpha snapshot must summarize Auto-Tuner state")
  failures += not require("alpha snapshot records navigation event", '"CarrotNavigationEvent"' in alpha_snapshot,
                          "alpha snapshot must include the latest sanitized navigation event")
  failures += not require("alpha snapshot summarizes navigation evidence",
                          "def summarize_navigation_event" in alpha_snapshot
                          and "navigation = summarize_navigation_event()" in alpha_snapshot
                          and '"navigationEvidence": navigation' in alpha_snapshot
                          and '"hazards": hazards' in alpha_snapshot
                          and '"modelSpeed": model_speed' in alpha_snapshot
                          and '"controlPreview": control_preview' in alpha_snapshot,
                          "alpha snapshot must summarize SDI, speed-bump, model-speed, and read-only control-preview evidence")
  failures += not require("alpha snapshot records speed-limit evidence",
                          '"speedLimitEvidence"' in alpha_snapshot
                          and "summarize_speed_limit" in alpha_snapshot
                          and '"offsetTypeName"' in alpha_snapshot
                          and '"phone"' in alpha_snapshot
                          and '"resolver"' in alpha_snapshot
                          and '"speedLimitOffset"' in alpha_snapshot,
                          "alpha snapshot must summarize speed-limit source, phone freshness, resolver, and offset evidence")
  failures += not require("alpha snapshot records Carrot feature gates",
                          "HIGH_RISK_FEATURE_GATES" in alpha_snapshot
                          and "def summarize_carrot_feature_gates" in alpha_snapshot
                          and '"carrotFeatureGates": carrot_feature_gates' in alpha_snapshot
                          and '"readyForControl": False' in alpha_snapshot
                          and '"controlOutputAllowed": False' in alpha_snapshot
                          and "real_car_gate_missing" in alpha_snapshot,
                          "alpha snapshot must summarize high-risk Carrot/fishop control gates as blocked until real-car evidence")
  for key in ("CarrotNaviDebug", "CarrotNaviEvent", "CarrotNaviImage"):
    failures += not require(f"alpha snapshot records navigation HTTP evidence: {key}", f'"{key}"' in alpha_snapshot,
                            f"alpha snapshot must include {key} for 7713 navigation HTTP evidence")
  failures += not require("alpha snapshot records carrot_server process", '"carrot_server"' in alpha_snapshot,
                          "alpha snapshot must report local Carrot Web process state")
  for service_name in ("modelV2", "drivingModelData", "cameraOdometry", "modelManagerSP", "longitudinalPlanSP", "carStateSP", "pandaStates"):
    failures += not require(f"alpha snapshot samples {service_name}", f'"{service_name}"' in alpha_snapshot,
                            f"alpha snapshot must sample {service_name}")
  failures += not require("alpha snapshot records panda output state", "safetyModel" in alpha_snapshot
                          and "controlsAllowed" in alpha_snapshot and "powerSaveEnabled" in alpha_snapshot
                          and "harnessStatus" in alpha_snapshot,
                          "alpha snapshot must report panda safety/output state")
  for disabled_process in ("manage_athenad", "uploader", "manage_sunnylinkd", "sunnylink_registration_manager", "statsd_sp", "backup_manager"):
    failures += not require(f"alpha snapshot checks cloud process {disabled_process}", disabled_process in alpha_snapshot,
                            f"alpha snapshot must report disabled cloud process {disabled_process}")

  settings = read("selfdrive/ui/sunnypilot/layouts/settings/settings.py")
  device_settings = read("selfdrive/ui/sunnypilot/layouts/settings/device.py")
  settings_ui_device = read("sunnypilot/sunnylink/settings_ui_src/pages/device.yaml")
  settings_ui_json = read("sunnypilot/sunnylink/settings_ui.json")
  zh_chs_po = read("selfdrive/ui/translations/app_zh-CHS.po")
  zh_cht_po = read("selfdrive/ui/translations/app_zh-CHT.po")
  languages_json = read("selfdrive/ui/translations/languages.json")
  multilang = read("system/ui/lib/multilang.py")
  font_process = read("selfdrive/assets/fonts/process.py")
  mici_settings = read("selfdrive/ui/sunnypilot/mici/layouts/settings.py")
  main_onboarding = read("selfdrive/ui/layouts/onboarding.py")
  mici_onboarding = read("selfdrive/ui/mici/layouts/onboarding.py")
  hardwared = read("system/hardware/hardwared.py")
  panda_safety = read("selfdrive/pandad/panda_safety.cc")
  pandad = read("selfdrive/pandad/pandad.cc")
  system_statsd = read("system/statsd.py")
  failures += not require("Sunnylink panel removed", "SunnylinkLayout" not in settings and "SUNNYLINK" not in settings,
                          "Sunnylink panel is still wired into settings")
  failures += not require("MICI Sunnylink panel removed", "SunnylinkLayoutMici" not in mici_settings and "sunnylink_btn" not in mici_settings,
                          "MICI Sunnylink panel is still wired into settings")
  failures += not require("Onroad Uploads setting removed", "Onroad Uploads" not in device_settings,
                          "Device settings still expose Onroad Uploads")
  failures += not require("OnroadUploads removed from settings-ui", "OnroadUploads" not in settings_ui_device + settings_ui_json,
                          "settings-ui source or compiled JSON still exposes OnroadUploads")
  failures += not require("Sunnylink removed from settings-ui", all(key not in settings_ui_device + settings_ui_json for key in ("SunnylinkEnabled", "EnableSunnylinkUploader")),
                          "settings-ui must not expose Sunnylink cloud toggles")
  korean_report = visible_korean_text_report()
  failures += not require("visible UI omits Korean text", not korean_report,
                          korean_report or "default-visible UI/docs must not include Korean text")
  failures += not require("Korean language option hidden", '"한국어"' not in languages_json
                          and '"ko"' not in languages_json
                          and '"ko"' not in multilang
                          and "'ko':" not in multilang
                          and '"ko"' not in font_process,
                          "personal alpha should expose Chinese/English-oriented language choices without Korean as a visible option")
  risk_text = settings_ui_device + settings_ui_json + read("sunnypilot/sunnylink/settings_ui_src/pages/cruise.yaml") + read("sunnypilot/sunnylink/settings_ui_src/pages/models.yaml") + read("sunnypilot/sunnylink/settings_ui_src/pages/developer.yaml")
  for token in (
    "Phone First",
    "stale phone data",
    "offset is 0",
    "panda is held in no-output mode",
    "parked updates",
    "stock model",
    "offroad",
    "Auto-Tuner Learning",
    "blocked while onroad",
    "Carrot Active Speed Control",
    "Traffic Light Stop",
    "fishop Auto Overtake Input",
    "evidence-only",
    "do not publish desire, planner, steering, or CAN commands",
  ):
    failures += not require(f"settings risk description exists: {token}", token in risk_text,
                            "settings UI source and compiled JSON must explain defaults, risk boundaries, and when not to enable high-risk features")
  failures += not require("Carrot Web safety boundary panel",
                          'id="safety-boundaries"' in carrot_server
                          and "Cloud services" in carrot_server
                          and "Speed offset" in carrot_server
                          and "fishop hardware" in carrot_server
                          and "control outputs stay disabled" in carrot_server,
                          "Carrot Web home page must explain local/cloud, speed, Auto-Tuner, fishop, and control-output boundaries")
  for msgid in (
    "Controls the state of the device after boot/sleep. Use Offroad only for parked updates or harness debugging.",
    "Offroad: Device will boot into parked maintenance mode and keep panda in no-output mode.",
    "Stock is the default. Select or download custom model bundles only while offroad; failed bundles fall back to stock or the last valid model.",
    "Only available while offroad. Do not change model bundles during a drive.",
    "Information: Displays the resolved speed limit only. This is the default and does not change cruise targets.",
    "Assist: May adjust cruise targets on supported cars. Use only after phone, car, and map sources have been verified.",
    "None: No offset. This is the default and safest setting.",
    "Phone First: Use fresh APN/N, Navipilot, or Carrot phone data first. Stale phone data times out, then falls back to vehicle, then OpenStreetMap/mapd.",
  ):
    failures += not require(f"Simplified Chinese safety translation exists: {msgid[:40]}", po_has_translation(zh_chs_po, msgid),
                            "critical risk/default descriptions must remain translated in app_zh-CHS.po")
    failures += not require(f"Traditional Chinese safety translation exists: {msgid[:40]}", po_has_translation(zh_cht_po, msgid),
                            "critical risk/default descriptions must remain translated in app_zh-CHT.po")
  failures += not require("TICI onboarding skips Sunnylink", "SunnylinkOnboarding" not in main_onboarding,
                          "Main onboarding still imports Sunnylink onboarding")
  failures += not require("MICI onboarding skips Sunnylink", "SunnylinkConsentPage" not in mici_onboarding,
                          "MICI onboarding still imports Sunnylink consent")
  failures += not require("OffroadMode blocks onroad", 'offroad_mode = params.get_bool("OffroadMode")' in hardwared
                          and 'startup_conditions["not_always_offroad"] = not offroad_mode' in hardwared
                          and 'onroad_conditions["not_always_offroad"] = not offroad_mode' in hardwared,
                          "hardwared must use OffroadMode to keep the device offroad")
  failures += not require("OffroadMode forces panda no-output", 'params_.getBool("OffroadMode")' in panda_safety
                          and "always_offroad = panda_safety.getOffroadMode()" in pandad
                          and "&& !always_offroad" in pandad
                          and "SafetyModel::NO_OUTPUT" in pandad,
                          "pandad must drive panda to NO_OUTPUT while OffroadMode keeps ignition_local false")
  failures += not require("system statsd local-only", "sock.bind(STATS_SOCKET)" in system_statsd
                          and "atomic_write(stats_path)" in system_statsd
                          and all(token not in system_statsd for token in ("requests.", "urllib.", "websocket", "create_connection", "UPLOAD_SESS", "common.api")),
                          "system.statsd must remain local-only and must not upload over the network")
  for token in ("mapbox.com", "api.mapbox", "mapboxgl", "MapboxGL", "dapi.kakao", "kakao.maps", "<iframe"):
    found = None
    for root in ("selfdrive/carrot", "selfdrive/ui"):
      found = find_token_in_tree(root, (token,), (".py", ".cc", ".h", ".html", ".js", ".json", ".yaml"))
      if found is not None:
        break
    failures += not require(f"map overlay omits external loader {token}", found is None,
                            "CarrotMapOverlayEnabled defaults off, so UI/Carrot Web must not load external map SDKs or iframe overlays by default")

  values = read("opendbc_repo/opendbc/car/hyundai/values.py")
  car_fingerprints = read("opendbc_repo/opendbc/car/fingerprints.py")
  hyundai_fingerprints = read("opendbc_repo/opendbc/car/hyundai/fingerprints.py")
  fingerprints_ext = read("opendbc_repo/opendbc/sunnypilot/car/hyundai/fingerprints_ext.py")
  failures += not require("KIA_SELTOS_2023 exists", "KIA_SELTOS_2023 = HyundaiPlatformConfig" in values,
                          "KIA_SELTOS_2023 must be a normal SCC HyundaiPlatformConfig")
  failures += not require("KIA_SELTOS_2023 reuses Seltos specs", "KIA_SELTOS.specs" in values,
                          "KIA_SELTOS_2023 should reuse KIA_SELTOS specs")
  failures += not require("KIA_SELTOS_2023 manual mapping exists", '"KIA SELTOS 2023": HYUNDAI.KIA_SELTOS_2023' in car_fingerprints,
                          "KIA SELTOS 2023 manual mapping missing")
  failures += not require("KIA_SELTOS_2023 FW entry exists", "CAR.KIA_SELTOS_2023" in hyundai_fingerprints,
                          "KIA_SELTOS_2023 FW fingerprint entry missing")
  failures += not require("Seltos Non-SCC personal entry removed",
                          "KIA_SELTOS_2023_NON_SCC" not in values + car_fingerprints + hyundai_fingerprints + fingerprints_ext,
                          "KIA_SELTOS_2023_NON_SCC should not be selectable or auto-matched in this build")

  interface = read("opendbc_repo/opendbc/car/hyundai/interface.py")
  failures += not require("ESCC auto-detect preserved", "if ESCC_MSG in fingerprint[0]" in interface and "ENHANCED_SCC" in interface,
                          "0x2AB ESCC auto-detection missing")
  escc_surfaces = params + settings + device_settings + mici_settings + values + car_fingerprints + hyundai_fingerprints + fingerprints_ext
  failures += not require("no manual ESCC toggle", all(key not in escc_surfaces for key in ("EnableEscc", "EnableESCC", "ESCCEnabled")),
                          "ESCC must be detected from the 0x2AB hardware message, not exposed as a normal user toggle")

  models_helpers = read("sunnypilot/models/helpers.py")
  models_manager = read("sunnypilot/models/manager.py")
  failures += not require("model runner defaults stock", "runner_type = custom.ModelManagerSP.Runner.stock" in models_helpers,
                          "model runner must default to stock without a valid active bundle")
  failures += not require("invalid active bundle resets stock", 'params.remove("ModelManager_ActiveBundle")' in models_helpers
                          and "ModelRunnerTypeCache" in models_helpers and "Runner.stock" in models_helpers,
                          "invalid active bundle must clear active bundle and reset runner cache to stock")
  failures += not require("model manager validates active bundle", "validate_active_bundle(self.params, self.available_models)" in models_manager,
                          "models_manager must validate active bundle before publishing state")
  failures += not require("model download request cleared", 'self.params.remove("ModelManager_DownloadIndex")' in models_manager,
                          "models_manager must clear download request after handling it")
  ok, detail = check_model_manager_download_contract()
  failures += not require("model manager atomic download and rollback contract", ok,
                          detail or "model downloads must verify temp artifacts before replacing files or writing active bundle")

  try:
    from openpilot.selfdrive.carrot.fishop_hardware import FishopHardwareState
    fishop_state = FishopHardwareState()
    fishop_state.update_from_payload({"resp": "lane", "left_lane": 2, "right_lane": 1, "lineValid": True,
                                      "max_curve": 0.018, "lat_a": 0.21, "prob": True,
                                      "l_line_prob": 0.9, "r_line_prob": 0.8,
                                      "l_lane_width": 3.2, "r_lane_width": 3.3, "lane_width": 3.25,
                                      "l_edge_dist": 1.8, "r_edge_dist": 2.1, "atc_state": 0, "blinker": 0}, 1000.0)
    fishop_state.update_from_payload({"device": "lidar", "resp": "blindspot", "detect_side": 3, "lidar_id": 0,
                                      "dist_time": 123456, "lidar_lblind": True, "lidar_car_lblind": True,
                                      "rf_drel": 4200, "rb_drel": -1800, "rf_xrel": 850, "rf_vrel": -1.2,
                                      "v_ego_mps": 15.0}, 1000.0)
    fishop_state.update_from_payload({"device": "camera", "resp": "cam_blind", "detect_side": 2, "right_blind": True}, 1000.0)
    fishop_state.update_from_payload({"device": "overtake", "index": 7, "cmd": "OVERTAKE", "arg": "left",
                                      "request": True, "direction": "left"}, 1000.0)
    fishop_snapshot = fishop_state.to_dict(1000.5)
    failures += not require("fishop parser preserves lane evidence", fishop_snapshot["lane"]["leftLine"] == 2
                            and fishop_snapshot["lane"]["rightLine"] == 1 and fishop_snapshot["lane"]["fresh"]
                            and fishop_snapshot["lane"]["leftLaneBlind"] and fishop_snapshot["lane"]["rightLaneBlind"],
                            "fishop parser must expose lane evidence without using it for control")
    lane_quality = fishop_snapshot["lane"]["laneQuality"]
    failures += not require("fishop parser preserves lane quality evidence", lane_quality["readOnly"]
                            and lane_quality["controlOutput"] is False
                            and lane_quality["curveAvailable"]
                            and lane_quality["modelEvidenceAvailable"]
                            and lane_quality["laneProbabilities"]["leftInner"] == 0.9
                            and lane_quality["laneWidthsM"]["center"] == 3.25
                            and lane_quality["roadEdgeDistancesM"]["left"] == 1.8
                            and lane_quality["atcState"] == 0
                            and lane_quality["blinker"] == 0,
                            "fishop parser must expose lane curve/model quality evidence as read-only")
    failures += not require("fishop parser preserves blindspot evidence", fishop_snapshot["blindspot"]["leftLidarBlind"]
                            and fishop_snapshot["blindspot"]["leftLidarCarBlind"]
                            and fishop_snapshot["blindspot"]["leftLidarOnline"]
                            and fishop_snapshot["blindspot"]["rightLidarOnline"]
                            and fishop_snapshot["blindspot"]["rightCameraOnline"]
                            and fishop_snapshot["blindspot"]["rightCameraBlind"]
                            and fishop_snapshot["blindspot"]["distTimeMs"] == 123456
                            and fishop_snapshot["blindspot"]["targets"]["rf_vrel"] == -1.2
                            and fishop_snapshot["blindspot"]["fresh"],
                            "fishop parser must expose blindspot evidence while fresh")
    dynamic_blind = fishop_snapshot["blindspot"]["dynamicBlind"]
    failures += not require("fishop dynamic blind preview stays read-only", dynamic_blind["readOnly"]
                            and dynamic_blind["controlOutput"] is False
                            and dynamic_blind["available"]
                            and dynamic_blind["vEgoMps"] == 15.0
                            and dynamic_blind["referenceDefaults"]["DynamicBlindRange"] == 0
                            and dynamic_blind["referenceDefaults"]["LidarFrontVRelDistTimeSec"] == 3.0
                            and dynamic_blind["riskPreview"]["rf"]["risk"]
                            and dynamic_blind["activeRiskPreview"] == ["rf"],
                            "dynamic blind preview must mirror fishop risk math as evidence only")
    failures += not require("fishop parser records overtake read-only", fishop_snapshot["overtake"]["commandSeen"]
                            and fishop_snapshot["overtake"]["readOnly"]
                            and fishop_snapshot["overtake"]["directionality"]["alphaAction"] == "record_only"
                            and fishop_snapshot["overtake"]["directionality"]["controlOutput"] is False
                            and fishop_snapshot["overtake"]["directionality"]["usesExistingLaneChangeChain"] is False
                            and fishop_snapshot["overtake"]["suggestionPreview"]["readOnly"]
                            and fishop_snapshot["overtake"]["suggestionPreview"]["controlOutput"] is False
                            and fishop_snapshot["overtake"]["suggestionPreview"]["emitsLateralCommand"] is False
                            and fishop_snapshot["overtake"]["cmdIndex"] == 7
                            and fishop_snapshot["overtake"]["remoteCmd"] == "OVERTAKE"
                            and not fishop_snapshot["controlOutputEnabled"],
                            "fishop overtake input must be evidence-only and never enable control output")
    blocked_preview = fishop_snapshot["overtake"]["suggestionPreview"]
    failures += not require("fishop overtake suggestion blocks unsafe evidence", blocked_preview["decision"] == "blocked"
                            and blocked_preview["readyForSuggestion"] is False
                            and blocked_preview["direction"] == "left"
                            and "left lane line blocks the suggestion" in blocked_preview["reasons"]
                            and "left blindspot evidence blocks the suggestion" in blocked_preview["reasons"],
                            "fishop suggestion preview must block stale, lane-line, and blindspot evidence before any later stage")
    failures += not require("fishop parser omits overtake action output", all(key not in fishop_snapshot["overtake"] for key in ("desire", "laneChange", "execute", "control"))
                            and fishop_snapshot["overtake"]["requested"] and fishop_snapshot["overtake"]["direction"] == "left",
                            "fishop overtake evidence must not expose desire/lane-change/control action fields")
    failures += not require("fishop parser reports sensor freshness", fishop_snapshot["sensorOnline"]
                            and fishop_snapshot["protocol"]["laneListenPort"] == 4213
                            and fishop_snapshot["lastUpdateMonotonicSec"] == 1000.0
                            and fishop_snapshot["lane"]["lastUpdateMonotonicSec"] == 1000.0,
                            "fishop parser must expose sensorOnline and last-update evidence")
    stale_snapshot = fishop_state.to_dict(1003.0)
    failures += not require("fishop stale lane invalid", not stale_snapshot["lane"]["fresh"]
                            and not stale_snapshot["lane"]["lineValid"]
                            and not stale_snapshot["lane"]["laneQuality"]["lineEvidenceAvailable"]
                            and stale_snapshot["lane"]["laneQuality"]["atcState"] is None,
                            "stale fishop lane input must not stay valid")
    failures += not require("fishop stale blindspot clears active bits", not stale_snapshot["blindspot"]["fresh"]
                            and not stale_snapshot["blindspot"]["leftLidarBlind"]
                            and not stale_snapshot["blindspot"]["rightCameraBlind"]
                            and not stale_snapshot["blindspot"]["targetsFresh"]
                            and not stale_snapshot["blindspot"]["dynamicBlind"]["available"]
                            and stale_snapshot["blindspot"]["dynamicBlind"]["activeRiskPreview"] == [],
                            "stale fishop blindspot input must not stay active")
    failures += not require("fishop stale overtake suggestion blocks", not stale_snapshot["overtake"]["suggestionPreview"]["readyForSuggestion"]
                            and "overtake command is stale" in stale_snapshot["overtake"]["suggestionPreview"]["reasons"],
                            "stale overtake input must not stay suggestable")

    clear_state = FishopHardwareState()
    clear_state.update_from_payload({"resp": "lane", "left_lane": 0, "right_lane": 0, "lineValid": True}, 2000.0)
    clear_state.update_from_payload({"device": "lidar", "resp": "blindspot", "detect_side": 3,
                                     "lidar_lblind": False, "lidar_rblind": False,
                                     "lidar_car_lblind": False, "lidar_car_rblind": False}, 2000.0)
    clear_state.update_from_payload({"device": "camera", "resp": "cam_blind", "detect_side": 3,
                                     "left_blind": False, "right_blind": False}, 2000.0)
    clear_state.update_from_payload({"device": "overtake", "index": 8, "cmd": "OVERTAKE", "arg": "right",
                                     "request": True}, 2000.0)
    clear_preview = clear_state.to_dict(2000.2)["overtake"]["suggestionPreview"]
    failures += not require("fishop overtake suggestion ready only when evidence is clear", clear_preview["decision"] == "ready_for_suggestion"
                            and clear_preview["readyForSuggestion"] is True
                            and clear_preview["direction"] == "right"
                            and clear_preview["reasons"] == []
                            and clear_preview["emitsLateralCommand"] is False,
                            "clean fishop evidence may only produce a display-only suggestion preview")
  except Exception as exc:
    failures += not require("fishop parser import/sample", False, f"fishop parser import/sample failed: {exc}")

  custom_capnp = read("cereal/custom.capnp")
  resolver = read("sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_resolver.py")
  common = read("sunnypilot/selfdrive/controls/lib/speed_limit/common.py")
  planner = read("sunnypilot/selfdrive/controls/lib/longitudinal_planner.py")
  ok, detail = check_schema_contract()
  failures += not require("schema contract check", ok, detail or "capnp schema text contract check failed")
  failures += not require("percentage speed offset exists", "percentage = 2" in common and "self.offset_value * 0.01 * self.speed_limit" in resolver,
                          "speed limit resolver must support percentage offsets")
  failures += not require("phone speed source schema", "phone @3;" in custom_capnp and "sourceLabel @9 :Text;" in custom_capnp,
                          "custom.capnp must expose phone source and sourceLabel")
  failures += not require("phone_priority policy exists", "phone_priority = 5" in common,
                          "speed limit policy enum must include phone_priority")
  failures += not require("phone resolver timeout", "PHONE_SPEED_LIMIT_MAX_AGE_S" in resolver and "CarrotPhoneSpeedLimitUpdatedAt" in resolver,
                          "resolver must reject stale phone speed data")
  failures += not require("phone source priority", "Policy.phone_priority: [SpeedLimitSource.phone, SpeedLimitSource.car, SpeedLimitSource.map]" in resolver,
                          "phone_priority must resolve phone, car, then map")
  ok, detail = check_route_speed_truth_contract()
  failures += not require("route/map overlay not speed truth", ok,
                          detail or "Mapbox/Kakao/Carrot route must stay display/evidence-only, not a speed-limit truth source")
  failures += not require("source label published", "resolver.sourceLabel = self.resolver.source_label" in planner,
                          "longitudinal planner must publish resolver sourceLabel")

  return 1 if failures else 0


if __name__ == "__main__":
  raise SystemExit(main())
