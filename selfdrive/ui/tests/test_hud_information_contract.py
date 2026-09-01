from cereal import log, messaging

from openpilot.selfdrive.ui.sunnypilot.onroad.hud_renderer import cruise_source_label, radar_packet_status


CruiseTargetSource = log.LongitudinalPlan.CruiseTargetSource


def _label(source, plan_alive=True):
  return cruise_source_label(plan_alive, source)


def test_cruise_source_uses_authoritative_final_constraint():
  assert _label(CruiseTargetSource.trafficLight) == "红灯停车"
  assert _label(CruiseTargetSource.vehicleLimit) == "车辆限速"
  assert _label(CruiseTargetSource.mapLimit) == "地图限速"
  assert _label(CruiseTargetSource.navigationLimit) == "导航限速"
  assert _label(CruiseTargetSource.visionCurve) == "视觉弯道"
  assert _label(CruiseTargetSource.mapCurve) == "地图弯道"
  assert _label(CruiseTargetSource.safetyDecel) == "安全减速"


def test_cruise_source_accepts_serialized_capnp_reader_enum():
  msg = messaging.new_message("longitudinalPlan")
  msg.longitudinalPlan.cruiseTargetSource = CruiseTargetSource.visionCurve

  reader_source = msg.as_reader().longitudinalPlan.cruiseTargetSource
  assert reader_source == CruiseTargetSource.visionCurve
  assert hash(reader_source) != hash(CruiseTargetSource.visionCurve)
  assert _label(reader_source) == "视觉弯道"


def test_cruise_source_explains_selected_speed_reference():
  assert _label(CruiseTargetSource.instrumentSet) == "仪表定速"
  assert _label(CruiseTargetSource.wheelSet) == "实际车速"
  assert _label(CruiseTargetSource.instrumentSet, plan_alive=False) == "不可用"


def test_escc_green_requires_a_valid_error_free_radar_packet():
  assert radar_packet_status(True, False) == "healthy"
  assert radar_packet_status(True, True) == "fault"
  assert radar_packet_status(False, False) == "invalid"
  assert radar_packet_status(False, True) == "invalid"
