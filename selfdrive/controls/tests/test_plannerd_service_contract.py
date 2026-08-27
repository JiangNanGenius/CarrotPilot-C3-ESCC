import ast
from pathlib import Path

import pytest

from openpilot.selfdrive.controls.lib.longitudinal_planner import get_processing_delay


ROOT = Path(__file__).resolve().parents[3]
PLANNERD = ROOT / "selfdrive/controls/plannerd.py"
LONGITUDINAL_PLANNER = ROOT / "selfdrive/controls/lib/longitudinal_planner.py"


def _submaster_services() -> set[str]:
  tree = ast.parse(PLANNERD.read_text())
  for node in ast.walk(tree):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
      continue
    if node.func.attr != "SubMaster" or not node.args or not isinstance(node.args[0], ast.List):
      continue
    return {
      element.value for element in node.args[0].elts
      if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }
  raise AssertionError("plannerd SubMaster service list not found")


def _planner_service_reads() -> set[str]:
  tree = ast.parse(LONGITUDINAL_PLANNER.read_text())
  services: set[str] = set()
  for node in ast.walk(tree):
    if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name) or node.value.id != "sm":
      continue
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
      services.add(node.slice.value)
  return services


def test_longitudinal_planner_only_reads_subscribed_services():
  missing = _planner_service_reads() - _submaster_services()
  assert not missing, f"longitudinal planner reads unsubscribed services: {sorted(missing)}"


def test_legacy_vehicle_parameter_service_is_not_reintroduced():
  assert "vehicleParameters" not in _planner_service_reads()
  assert "liveParameters" in _planner_service_reads()


def test_optional_navigation_services_do_not_invalidate_base_plan():
  source = PLANNERD.read_text()
  for service in ("liveMapDataSP", "carStateSP", "carrotMan"):
    assert service in source
  for keyword in ("ignore_alive=ignore_services", "ignore_avg_freq=ignore_services", "ignore_valid=ignore_services"):
    assert keyword in source


def test_processing_delay_uses_nanoseconds_consistently():
  assert get_processing_delay(10_050_000_000, 10_000_000_000) == pytest.approx(0.05)
