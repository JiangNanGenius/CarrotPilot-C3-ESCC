from opendbc.can import CANPacker
from opendbc.car.hyundai.hyundaican import create_lfahda_mfc


def _hda_fields(enabled: bool, planned_target_speed: float, lfa_icon: int = 2):
  packer = CANPacker("hyundai_kia_generic")
  address, dat, bus = create_lfahda_mfc(packer, enabled, lfa_icon, planned_target_speed)
  return address, bus, {
    "hda_usm": dat[0] & 0x3,
    "hda_icon": (dat[0] >> 3) & 0x3,
    "hda_set_speed": dat[1],
    "lfa_icon": dat[3] & 0x3,
  }


def test_hda_cluster_reports_active_state_and_dynamic_planner_target():
  address, bus, fields = _hda_fields(True, 32.0)
  assert (address, bus) == (0x485, 0)
  assert fields == {"hda_usm": 2, "hda_icon": 2, "hda_set_speed": 32, "lfa_icon": 2}


def test_lfahda_mfc_uses_stock_eight_byte_contract():
  packer = CANPacker("hyundai_kia_generic")
  address, dat, bus = create_lfahda_mfc(packer, True, 2, 32.0)

  assert (address, bus) == (0x485, 0)
  assert len(dat) == 8
  assert dat[4:] == bytes(4)


def test_hda_cluster_hides_speed_when_longitudinal_is_disabled():
  _, _, fields = _hda_fields(False, 100.0, lfa_icon=0)
  assert fields == {"hda_usm": 2, "hda_icon": 0, "hda_set_speed": 0, "lfa_icon": 0}
