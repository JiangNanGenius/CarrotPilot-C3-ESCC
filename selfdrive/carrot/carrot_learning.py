import json
import time

from openpilot.selfdrive.carrot.carrot_params import CarrotParams as Params


DT = 0.1
SPEED_BANDS_KPH = [0, 10, 40, 60, 80, 110, 140]
ACCEL_KEYS = [f"CruiseMaxVals{i}" for i in range(len(SPEED_BANDS_KPH))]
TFOLLOW_KEYS = ["TFollowGap1", "TFollowGap2", "TFollowGap3", "TFollowGap4"]

PARAM_LIMITS = {
  "CruiseMaxVals0": (50, 300),
  "CruiseMaxVals1": (50, 300),
  "CruiseMaxVals2": (40, 250),
  "CruiseMaxVals3": (30, 220),
  "CruiseMaxVals4": (20, 200),
  "CruiseMaxVals5": (20, 180),
  "CruiseMaxVals6": (20, 160),
  "TFollowGap1": (70, 300),
  "TFollowGap2": (80, 350),
  "TFollowGap3": (90, 400),
  "TFollowGap4": (100, 450),
  "JLeadFactor3": (-200, 300),
  "PathOffset": (-150, 150),
  "SteerActuatorDelay": (0, 200),
  "SteerRatioRate": (50, 150),
  "DynamicTFollow": (0, 100),
  "TFollowDecelBoost": (0, 100),
  "StopDistanceCarrot": (300, 1200),
}

LAT_KEYS = {
  "PathOffset",
  "SteerActuatorDelay",
  "SteerRatioRate",
}

LONG_KEYS = {
  *ACCEL_KEYS,
  *TFOLLOW_KEYS,
  "JLeadFactor3",
  "DynamicTFollow",
  "TFollowDecelBoost",
  "StopDistanceCarrot",
}


def _clamp(key, value):
  low, high = PARAM_LIMITS.get(key, (-100000, 100000))
  return int(max(low, min(high, value)))


def _speed_band(v_ego_kph):
  for i in range(len(SPEED_BANDS_KPH) - 1, -1, -1):
    if v_ego_kph >= SPEED_BANDS_KPH[i]:
      return i
  return 0


def _default_data():
  return {
    "version": 1,
    "drive_sec": 0.0,
    "accel": [{"gas_sec": 0.0, "brake_after_gas_sec": 0.0, "max_gas": 0.0} for _ in ACCEL_KEYS],
    "follow": [{"gas_sec": 0.0, "brake_sec": 0.0, "min_drel": 999.0} for _ in TFOLLOW_KEYS],
    "brake": {"count": 0, "lead_drel_sum": 0.0, "lead_vrel_sum": 0.0},
    "steer": {
      "straight_samples": 0,
      "straight_angle_sum": 0.0,
      "curve_entries": 0,
      "curve_overrides": 0,
      "last_steer_deg": 0.0,
      "in_curve": False,
    },
    "last_updated": 0.0,
  }


class CarrotLearner:
  def __init__(self):
    self.params = Params()
    self.data = self._load()
    self.current_gap = 2
    self.has_driven = False
    self.prev_brake_pressed = False
    self.last_save_t = time.monotonic()

  def is_active(self):
    return self.params.get_int("CarrotLearningActive") == 1

  def set_current_gap(self, gap):
    self.current_gap = int(max(1, min(4, gap)))

  def update(self, v_ego_kph, gas_pressed, engaged, gear_park, steer_deg=0.0,
             steer_pressed=False, brake_pressed=False, lead_drel=0.0,
             lead_v_kph=0.0, a_ego=0.0, lead_jlead=0.0, v_cruise_kph=0.0,
             gas_val=0.0, brake_val=0.0):
    self._handle_control_flags()

    if not self.is_active():
      return

    if gear_park:
      if self.has_driven:
        self._save()
        self._publish_recommendations("parking")
        self.has_driven = False
      self.prev_brake_pressed = brake_pressed
      return

    if not engaged or v_ego_kph < 3.0:
      self.prev_brake_pressed = brake_pressed
      return

    self.has_driven = True
    self.data["drive_sec"] = round(float(self.data.get("drive_sec", 0.0)) + DT, 1)
    self.data["last_updated"] = time.time()

    self._learn_accel(v_ego_kph, gas_pressed, brake_pressed, gas_val)
    self._learn_follow(v_ego_kph, gas_pressed, brake_pressed, lead_drel)
    self._learn_brake(v_ego_kph, brake_pressed, lead_drel, lead_v_kph)
    self._learn_steer(v_ego_kph, steer_deg, steer_pressed)

    self.prev_brake_pressed = brake_pressed
    if time.monotonic() - self.last_save_t > 30.0:
      self._save()
      self.last_save_t = time.monotonic()

  def _handle_control_flags(self):
    if self.params.get_bool("CarrotLearningClear"):
      self._clear_learning_data()
      self.params.put_bool("CarrotLearningClear", False)

    if self.params.get_bool("CarrotLearningApply"):
      self.apply_recommendations(manual=True)
      self.params.put_bool("CarrotLearningApply", False)

    if self.params.get_bool("CarrotLearningIgnore"):
      self._clear_pending_recommendation()
      self.params.put_bool("CarrotLearningIgnore", False)

    if self.params.get_bool("CarrotTunerFactoryReset"):
      self._clear_learning_data()
      self.params.remove("CarrotLearningHistory")
      self.params.put_bool("CarrotTunerFactoryReset", False)

  def _learn_accel(self, v_ego_kph, gas_pressed, brake_pressed, gas_val):
    idx = _speed_band(v_ego_kph)
    band = self.data["accel"][idx]
    if gas_pressed:
      band["gas_sec"] = round(float(band.get("gas_sec", 0.0)) + DT, 1)
      band["max_gas"] = max(float(band.get("max_gas", 0.0)), float(gas_val or 0.0))
    if gas_pressed and brake_pressed:
      band["brake_after_gas_sec"] = round(float(band.get("brake_after_gas_sec", 0.0)) + DT, 1)

  def _learn_follow(self, v_ego_kph, gas_pressed, brake_pressed, lead_drel):
    if not (40.0 <= v_ego_kph and 5.0 < lead_drel < 150.0):
      return

    gap_idx = self.current_gap - 1
    gap = self.data["follow"][gap_idx]
    gap["min_drel"] = min(float(gap.get("min_drel", 999.0)), float(lead_drel))
    if gas_pressed:
      gap["gas_sec"] = round(float(gap.get("gas_sec", 0.0)) + DT, 1)
    if brake_pressed:
      gap["brake_sec"] = round(float(gap.get("brake_sec", 0.0)) + DT, 1)

  def _learn_brake(self, v_ego_kph, brake_pressed, lead_drel, lead_v_kph):
    if not brake_pressed or self.prev_brake_pressed:
      return
    if not (20.0 <= v_ego_kph and 0.0 < lead_drel < 100.0):
      return

    brake = self.data["brake"]
    brake["count"] = int(brake.get("count", 0)) + 1
    brake["lead_drel_sum"] = round(float(brake.get("lead_drel_sum", 0.0)) + float(lead_drel), 2)
    brake["lead_vrel_sum"] = round(float(brake.get("lead_vrel_sum", 0.0)) + max(0.0, v_ego_kph - lead_v_kph), 2)

  def _learn_steer(self, v_ego_kph, steer_deg, steer_pressed):
    steer = self.data["steer"]
    prev_steer = float(steer.get("last_steer_deg", 0.0))
    steer_rate = abs(float(steer_deg) - prev_steer) / DT

    if v_ego_kph >= 40.0 and abs(steer_deg) < 5.0 and not steer_pressed:
      steer["straight_samples"] = int(steer.get("straight_samples", 0)) + 1
      steer["straight_angle_sum"] = round(float(steer.get("straight_angle_sum", 0.0)) + float(steer_deg), 3)

    entering_curve = v_ego_kph >= 30.0 and abs(steer_deg) >= 5.0 and steer_rate >= 10.0
    if entering_curve and not bool(steer.get("in_curve", False)):
      steer["curve_entries"] = int(steer.get("curve_entries", 0)) + 1
      steer["in_curve"] = True
    elif not entering_curve and abs(steer_deg) < 3.0:
      steer["in_curve"] = False

    if bool(steer.get("in_curve", False)) and steer_pressed:
      steer["curve_overrides"] = int(steer.get("curve_overrides", 0)) + 1

    steer["last_steer_deg"] = float(steer_deg)

  def _load(self):
    raw = self.params.get("CarrotLearningData")
    if not raw:
      return _default_data()
    try:
      data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception:
      return _default_data()
    default = _default_data()
    default.update(data)
    return default

  def _save(self):
    self.params.put("CarrotLearningData", json.dumps(self.data, separators=(",", ":")).encode("utf-8"))

  def _param_enabled(self, key, default=True):
    raw = self.params.get(key)
    if raw is None:
      return default
    return self.params.get_int(key) != 0

  def _add_recommendation(self, recs, key, recommended, reason, evidence):
    current = self.params.get_int(key)
    recommended = _clamp(key, recommended)
    if recommended == current:
      return

    category = "lat" if key in LAT_KEYS else "long"
    if category == "lat" and not self._param_enabled("CarrotTunerApplyLat", True):
      return
    if category == "long" and not self._param_enabled("CarrotTunerApplyLong", True):
      return

    recs[key] = {
      "category": category,
      "current": current,
      "recommended": recommended,
      "reason": reason,
      "evidence": evidence,
    }

  def _calc_recommendations(self):
    recs = {}

    for i, key in enumerate(ACCEL_KEYS):
      band = self.data["accel"][i]
      gas_sec = float(band.get("gas_sec", 0.0))
      brake_after_gas_sec = float(band.get("brake_after_gas_sec", 0.0))
      current = self.params.get_int(key)
      if gas_sec >= 10.0:
        self._add_recommendation(
          recs, key, int(current * 1.10),
          "Driver often presses accelerator while openpilot is engaged in this speed band.",
          {"gas_sec": gas_sec, "band_kph": SPEED_BANDS_KPH[i]},
        )
      elif brake_after_gas_sec >= 5.0:
        self._add_recommendation(
          recs, key, int(current * 0.93),
          "Driver brakes soon after acceleration in this speed band.",
          {"brake_after_gas_sec": brake_after_gas_sec, "band_kph": SPEED_BANDS_KPH[i]},
        )

    for i, key in enumerate(TFOLLOW_KEYS):
      gap = self.data["follow"][i]
      gas_sec = float(gap.get("gas_sec", 0.0))
      brake_sec = float(gap.get("brake_sec", 0.0))
      current = self.params.get_int(key)
      if brake_sec >= 10.0:
        self._add_recommendation(
          recs, key, current + 5,
          "Driver often brakes while following a lead car in this gap mode.",
          {"brake_sec": brake_sec, "gap": i + 1, "min_drel": gap.get("min_drel", 999.0)},
        )
      elif gas_sec >= 15.0:
        self._add_recommendation(
          recs, key, current - 5,
          "Driver often presses accelerator while following a lead car in this gap mode.",
          {"gas_sec": gas_sec, "gap": i + 1, "min_drel": gap.get("min_drel", 999.0)},
        )

    brake = self.data["brake"]
    brake_count = int(brake.get("count", 0))
    if brake_count >= 5:
      avg_drel = float(brake.get("lead_drel_sum", 0.0)) / max(1, brake_count)
      current = self.params.get_int("JLeadFactor3")
      if avg_drel < 30.0:
        recommended = current + 20
        reason = "Manual braking usually happens close to the lead car."
      else:
        recommended = current + 10
        reason = "Manual braking events indicate lead response could be more conservative."
      self._add_recommendation(
        recs, "JLeadFactor3", recommended, reason,
        {"brake_count": brake_count, "avg_lead_drel": round(avg_drel, 1)},
      )

    steer = self.data["steer"]
    straight_samples = int(steer.get("straight_samples", 0))
    if straight_samples >= 200:
      avg_steer = float(steer.get("straight_angle_sum", 0.0)) / straight_samples
      if abs(avg_steer) >= 1.5:
        current = self.params.get_int("PathOffset")
        self._add_recommendation(
          recs, "PathOffset", current + int(round(avg_steer * 10.0)),
          "Straight-road steering angle shows a persistent lane-centering bias.",
          {"straight_samples": straight_samples, "avg_steer_deg": round(avg_steer, 2)},
        )

    curve_entries = int(steer.get("curve_entries", 0))
    curve_overrides = int(steer.get("curve_overrides", 0))
    if curve_entries >= 10 and curve_overrides / max(1, curve_entries) >= 0.5:
      current = self.params.get_int("SteerActuatorDelay")
      self._add_recommendation(
        recs, "SteerActuatorDelay", current + 10,
        "Driver often overrides steering during curve entry.",
        {"curve_entries": curve_entries, "curve_overrides": curve_overrides},
      )

    return recs

  def _publish_recommendations(self, source):
    recs = self._calc_recommendations()
    if not recs:
      return

    payload = {
      "version": 1,
      "source": source,
      "created_at": time.time(),
      "auto_apply": False,
      "recommendations": recs,
    }
    self.params.put("CarrotLearningRecommend", json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    self.params.put("CarrotLearningPopupSource", source)
    self.params.put_bool("CarrotLearningPopupReady", True)
    if self.params.get_bool("CarrotLearningAutoApply"):
      self.apply_recommendations(manual=False)

  def apply_recommendations(self, manual=False):
    if not manual and not self.params.get_bool("CarrotLearningAutoApply"):
      return False

    raw = self.params.get("CarrotLearningRecommend")
    if not raw:
      return False
    try:
      payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception:
      return False

    applied = {}
    for key, info in payload.get("recommendations", {}).items():
      if key not in PARAM_LIMITS:
        continue
      category = info.get("category", "long")
      if category == "lat" and not self._param_enabled("CarrotTunerApplyLat", True):
        continue
      if category == "long" and not self._param_enabled("CarrotTunerApplyLong", True):
        continue
      recommended = _clamp(key, int(info["recommended"]))
      self.params.put_int(key, recommended)
      applied[key] = recommended

    if applied:
      self._append_history(payload, applied, "manual" if manual else "auto")
      self.params.remove("CarrotLearningRecommend")
      self.params.put_bool("CarrotLearningPopupReady", False)
    return bool(applied)

  def _append_history(self, payload, applied, mode):
    raw = self.params.get("CarrotLearningHistory")
    try:
      history = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw) if raw else []
    except Exception:
      history = []
    history.append({
      "applied_at": time.time(),
      "mode": mode,
      "source": payload.get("source", ""),
      "applied": applied,
    })
    self.params.put("CarrotLearningHistory", json.dumps(history[-50:], separators=(",", ":")).encode("utf-8"))

  def _clear_learning_data(self):
    self.data = _default_data()
    self.has_driven = False
    self.params.remove("CarrotLearningData")
    self._clear_pending_recommendation()

  def _clear_pending_recommendation(self):
    self.params.remove("CarrotLearningRecommend")
    self.params.remove("CarrotLearningPopupSource")
    self.params.put_bool("CarrotLearningPopupReady", False)


class DrivingStyleProfiler:
  def update(self, *args, **kwargs):
    return

  def get_profile_progress(self):
    return {"is_ready": False}
