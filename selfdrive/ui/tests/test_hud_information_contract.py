from cereal import custom, log

from openpilot.selfdrive.ui.sunnypilot.onroad.hud_renderer import cruise_source_label


LongitudinalPlanSource = log.LongitudinalPlan.LongitudinalPlanSource
SpeedLimitSource = custom.LongitudinalPlanSP.SpeedLimit.Source


def _label(**overrides):
  values = {
    "plan_alive": True,
    "plan_source": LongitudinalPlanSource.cruise,
    "traffic_state": "off",
    "speed_limit_active": False,
    "speed_limit_source": SpeedLimitSource.none,
    "vision_active": False,
    "map_active": False,
  }
  values.update(overrides)
  return cruise_source_label(**values)


def test_cruise_source_prioritizes_active_constraints():
  assert _label(traffic_state="red", speed_limit_active=True) == "红灯停车"
  assert _label(speed_limit_active=True, speed_limit_source=SpeedLimitSource.car) == "车辆限速"
  assert _label(speed_limit_active=True, speed_limit_source=SpeedLimitSource.map) == "地图限速"
  assert _label(vision_active=True) == "视觉弯道"
  assert _label(map_active=True) == "地图弯道"


def test_cruise_source_explains_base_planner_target():
  assert _label(plan_source=LongitudinalPlanSource.lead0) == "前车跟随"
  assert _label(plan_source=LongitudinalPlanSource.e2e) == "模型规划"
  assert _label() == "驾驶设定"
  assert _label(plan_alive=False) == "不可用"
