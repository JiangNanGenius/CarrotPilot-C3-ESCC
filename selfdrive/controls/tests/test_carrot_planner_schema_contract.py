import ast
from pathlib import Path

from cereal import car, log


ROOT = Path(__file__).resolve().parents[3]
CARROT_PLANNER = ROOT / "selfdrive/carrot/carrot_functions.py"
LONGITUDINAL_PLANNER = ROOT / "selfdrive/controls/lib/longitudinal_planner.py"
LONGITUDINAL_MPC = ROOT / "selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py"
CRUISE_SETTINGS = ROOT / "selfdrive/ui/sunnypilot/layouts/settings/cruise.py"
RAW_CAPNP = ROOT / "selfdrive/carrot/web/js/realtime/raw_capnp.js"
WEB_SNAPSHOT = ROOT / "selfdrive/carrot/server/live_runtime/snapshot.py"


def _direct_attributes(tree: ast.AST, variable: str) -> set[str]:
  return {
    node.attr for node in ast.walk(tree)
    if isinstance(node, ast.Attribute)
    and isinstance(node.value, ast.Name)
    and node.value.id == variable
  }


def test_carrot_planner_only_reads_current_carstate_fields():
  tree = ast.parse(CARROT_PLANNER.read_text())
  invalid = _direct_attributes(tree, "carstate") - set(car.CarState.schema.fields)
  assert not invalid, f"CarrotPlanner reads missing CarState fields: {sorted(invalid)}"


def test_carrot_planner_only_reads_current_lead_fields():
  tree = ast.parse(CARROT_PLANNER.read_text())
  lead_fields = set(log.RadarState.new_message().leadOne.schema.fields)
  invalid = (_direct_attributes(tree, "lead") | _direct_attributes(tree, "leadOne")) - lead_fields
  assert not invalid, f"CarrotPlanner reads missing RadarState.LeadData fields: {sorted(invalid)}"


def test_longitudinal_planner_uses_current_lead_presence_field():
  tree = ast.parse(LONGITUDINAL_PLANNER.read_text())
  lead_fields = set(log.RadarState.new_message().leadOne.schema.fields)
  assert "status" in lead_fields

  invalid = set()
  for node in ast.walk(tree):
    if not isinstance(node, ast.Attribute):
      continue
    value = node.value
    if not isinstance(value, ast.Attribute) or value.attr != "leadOne":
      continue
    invalid.add(node.attr)

  invalid -= lead_fields
  assert not invalid, f"LongitudinalPlanner reads missing RadarState.LeadData fields: {sorted(invalid)}"


def test_longitudinal_mpc_only_reads_current_lead_fields():
  tree = ast.parse(LONGITUDINAL_MPC.read_text())
  lead_fields = set(log.RadarState.new_message().leadOne.schema.fields)
  invalid = _direct_attributes(tree, "lead") - lead_fields
  assert not invalid, f"LongitudinalMpc reads missing RadarState.LeadData fields: {sorted(invalid)}"


def test_carrot_planner_only_uses_current_longitudinal_personalities():
  source = CARROT_PLANNER.read_text()
  assert "LongitudinalPersonality.moreRelaxed" not in source


def test_carrot_planner_does_not_emit_unpublished_events():
  source = CARROT_PLANNER.read_text()
  assert "trafficSignChanged" not in source
  assert "trafficSignGreen" not in source
  assert "trafficStopping" not in source


def test_visual_stop_output_is_returned_to_longitudinal_planner():
  tree = ast.parse(CARROT_PLANNER.read_text())
  update = next(
    node for node in ast.walk(tree)
    if isinstance(node, ast.FunctionDef) and node.name == "update"
  )
  returns = [ast.unparse(node.value) for node in ast.walk(update) if isinstance(node, ast.Return)]
  assert "self.v_cruise * CV.MS_TO_KPH" in returns


def test_optional_carrot_planner_cannot_take_down_plannerd():
  source = LONGITUDINAL_PLANNER.read_text()
  assert "except Exception:" in source
  assert "self.carrot_planner_faulted = True" in source


def test_visual_stop_uses_the_same_feature_gate_as_nav_stop():
  source = LONGITUDINAL_PLANNER.read_text()
  assert "traffic_stop_enabled = self.carrot_traffic_stop.refresh_enabled()" in source
  assert "traffic_stop_enabled=traffic_stop_enabled" in source


def test_unwired_follow_controls_are_not_exposed():
  source = CRUISE_SETTINGS.read_text()
  for key in ("TFollowGap1", "TFollowGap2", "TFollowGap3", "TFollowGap4", "JLeadFactor3", "StopDistanceCarrot"):
    assert key not in source


def test_realtime_planner_does_not_construct_carrot_learner():
  assert "CarrotLearner" not in CARROT_PLANNER.read_text()


def test_web_runtime_does_not_decode_removed_schema_fields():
  source = RAW_CAPNP.read_text() + WEB_SNAPSHOT.read_text()
  for field in ("softHoldActive", "carrotCruise", "gearStep", "useLaneLineSpeed", "activeLaneLine", "jLead", "score"):
    assert f'"{field}"' not in source
