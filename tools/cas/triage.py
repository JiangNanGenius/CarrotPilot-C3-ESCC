from enum import IntEnum


class TriageType(IntEnum):
  EXCLUDE = 0
  T1_GOOD = 1
  T2_OFFSET = 2
  T3_STRONG_INTERVENTION = 3
  T4_WEAK_INTERVENTION = 4
  T5_MANUAL = 5


TRIAGE_WEIGHTS = {
  TriageType.EXCLUDE: 0.0,
  TriageType.T1_GOOD: 0.3,
  TriageType.T2_OFFSET: 0.6,
  TriageType.T3_STRONG_INTERVENTION: 1.0,
  TriageType.T4_WEAK_INTERVENTION: 0.5,
  TriageType.T5_MANUAL: 0.1,
}

_FLAG_BY_NAME = {
  "exclude": TriageType.EXCLUDE,
  "t1good": TriageType.T1_GOOD,
  "t2offset": TriageType.T2_OFFSET,
  "t3strongintervention": TriageType.T3_STRONG_INTERVENTION,
  "t4weakintervention": TriageType.T4_WEAK_INTERVENTION,
  "t5manual": TriageType.T5_MANUAL,
}


def coerce_triage(value) -> TriageType:
  if isinstance(value, TriageType):
    return value
  try:
    return TriageType(int(value))
  except (TypeError, ValueError):
    pass

  name = str(value).split(".")[-1].replace("_", "").lower()
  return _FLAG_BY_NAME.get(name, TriageType.EXCLUDE)


def classify_sample(lat_active: bool, steering_pressed: bool, steering_torque_driver: float,
                    v_ego: float, lateral_offset: float,
                    weak_threshold: float = 0.2, strong_threshold: float = 0.8) -> TriageType:
  if v_ego < 5.0:
    return TriageType.EXCLUDE
  if not lat_active:
    return TriageType.T5_MANUAL
  if steering_pressed and abs(steering_torque_driver) >= strong_threshold:
    return TriageType.T3_STRONG_INTERVENTION
  if steering_pressed and abs(steering_torque_driver) >= weak_threshold:
    return TriageType.T4_WEAK_INTERVENTION
  if abs(lateral_offset) > 0.25:
    return TriageType.T2_OFFSET
  return TriageType.T1_GOOD
