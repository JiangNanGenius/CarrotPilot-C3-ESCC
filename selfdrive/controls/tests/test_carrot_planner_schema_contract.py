import ast
from pathlib import Path

from cereal import car, log


ROOT = Path(__file__).resolve().parents[3]
CARROT_PLANNER = ROOT / "selfdrive/carrot/carrot_functions.py"
LONGITUDINAL_PLANNER = ROOT / "selfdrive/controls/lib/longitudinal_planner.py"


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
