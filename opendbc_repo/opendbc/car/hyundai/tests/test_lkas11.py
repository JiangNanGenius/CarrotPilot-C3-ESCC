from opendbc.can import CANPacker, CANParser
from opendbc.car import gen_empty_fingerprint
from opendbc.car.hyundai.hyundaican import create_lkas11
from opendbc.car.hyundai.interface import CarInterface
from opendbc.car.hyundai.values import CAR


LKAS11_STOCK_VALUES = {
  "CF_Lkas_LdwsActivemode": 0,
  "CF_Lkas_LdwsSysState": 0,
  "CF_Lkas_SysWarning": 0,
  "CF_Lkas_LdwsLHWarning": 0,
  "CF_Lkas_LdwsRHWarning": 0,
  "CF_Lkas_HbaLamp": 0,
  "CF_Lkas_FcwBasReq": 0,
  "CF_Lkas_HbaSysState": 0,
  "CF_Lkas_FcwOpt": 0,
  "CF_Lkas_HbaOpt": 0,
  "CF_Lkas_FcwSysState": 0,
  "CF_Lkas_FcwCollisionWarning": 0,
  "CF_Lkas_FusionState": 0,
  "CF_Lkas_FcwOpt_USM": 1,
  "CF_Lkas_LdwsOpt_USM": 0,
}


def _create_and_parse_lkas11(car_fingerprint):
  CP = CarInterface.get_params(car_fingerprint, gen_empty_fingerprint(), [], False, False, False)
  packer = CANPacker("hyundai_kia_generic")
  parser = CANParser("hyundai_kia_generic", [("LKAS11", 0)], 0)

  msg = create_lkas11(
    packer, frame=7, CP=CP, apply_torque=42, steer_req=True,
    torque_fault=False, lkas11=LKAS11_STOCK_VALUES,
    sys_warning=True, sys_state=3, enabled=True,
    left_lane=True, right_lane=False,
    left_lane_depart=1, right_lane_depart=0,
    lkas_icon=3,
  )
  parser.update([1, [msg]])
  return msg, parser.vl["LKAS11"]


def test_seltos_2023_lkas11_matches_established_seltos_cluster_contract():
  seltos_2021_msg, seltos_2021 = _create_and_parse_lkas11(CAR.KIA_SELTOS)
  seltos_2023_msg, seltos_2023 = _create_and_parse_lkas11(CAR.KIA_SELTOS_2023)

  # The 2023 platform was introduced as a separate fingerprint of the same
  # CAN Seltos platform. Keep its LKAS/cluster encoding identical to the
  # established 2021 path, including the CRC checksum.
  assert seltos_2023_msg == seltos_2021_msg
  assert seltos_2023["CF_Lkas_LdwsActivemode"] == 1
  assert seltos_2023["CF_Lkas_LdwsOpt_USM"] == 2
  assert seltos_2023["CF_Lkas_FcwOpt_USM"] == 3
  assert seltos_2023["CF_Lkas_SysWarning"] == 4
  assert seltos_2023["CF_Lkas_LdwsSysState"] == 3
  assert seltos_2023["CR_Lkas_StrToqReq"] == 42
  assert seltos_2023["CF_Lkas_ActToi"] == 1
  assert seltos_2023["CF_Lkas_MsgCount"] == 7
