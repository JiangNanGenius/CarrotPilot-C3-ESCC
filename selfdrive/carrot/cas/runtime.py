from __future__ import annotations

from collections import deque
from pathlib import Path
import math
import re
import time

from openpilot.common.params import Params
try:
  from openpilot.selfdrive.carrot.cas.features import FEATURE_SCHEMA, CASFeatureState, build_feature_vector
  from openpilot.selfdrive.carrot.cas.metadata import eps_firmware_hash
  from openpilot.selfdrive.carrot.cas.model import CASModel
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import FEATURE_SCHEMA, CASFeatureState, build_feature_vector
  from selfdrive.carrot.cas.metadata import eps_firmware_hash
  from selfdrive.carrot.cas.model import CASModel


CAS_DIR = Path(__file__).resolve().parent
WEIGHTS_DIR = CAS_DIR / "weights"

# Runtime is called at ~100 Hz from latcontrol_*.
_HZ = 100
_OFFSET_5S = 5 * _HZ
_OFFSET_60S = 60 * _HZ
_CENTERING_FULL_M = 0.5  # |offset| >= this -> score 0; offset == 0 -> score 100


def _norm_name(value: str) -> str:
  return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _param_text(params: Params, key: str) -> str:
  value = params.get(key)
  if value is None:
    return ""
  if isinstance(value, bytes):
    return value.decode("utf-8", "ignore").strip()
  return str(value).strip()


class CASRuntime:
  def __init__(self, CP, kind: str):
    self.CP = CP
    self.kind = kind
    self.params = Params()
    self.feature_state = CASFeatureState()
    self.model: CASModel | None = None
    self.model_name = ""
    self.enabled_param = "CAS"
    self.model_param = "CASModelName"
    # Centering / intervention stats (cleared per session).
    self.offset_5s = deque(maxlen=_OFFSET_5S)
    self.offset_60s = deque(maxlen=_OFFSET_60S)
    # Strong/weak intervention split + last-seen timestamps.
    self.intervention_count = 0
    self.intervention_strong = 0
    self.intervention_weak = 0
    self.last_intervention_t: float | None = None
    self.last_strong_t: float | None = None
    self.last_weak_t: float | None = None
    self._was_pressed = False
    self.session_start_t = time.monotonic()
    # CAS accuracy: did delta push toward the centerline?
    # We log per-frame correctness over a 60-second window.
    self.acc_window = deque(maxlen=_OFFSET_60S)  # 1 = correct, 0 = wrong
    # Distribution-in flag history (vEgo inside vego_min..vego_max).
    self.dist_in_window = deque(maxlen=_OFFSET_60S * 5)  # 5 min window
    self.load_model()

  def load_model(self):
    self.model = None
    self.model_name = ""
    self.params.remove(self.model_param)
    if not WEIGHTS_DIR.exists():
      return

    runtime_names = [
      _norm_name(_param_text(self.params, "CarName")),
      _norm_name(_param_text(self.params, "CarSelected3")),
    ]
    runtime_names = [name for name in runtime_names if name and name != "MOCK"]
    runtime_eps_hash = eps_firmware_hash(getattr(self.CP, "carFw", []))
    expected_type = f"cas_{self.kind}"
    best_path = None
    best_score = -1
    for path in WEIGHTS_DIR.glob("*.json"):
      try:
        candidate = CASModel(path)
      except Exception:
        continue
      if candidate.model_type and candidate.model_type != expected_type:
        continue
      if candidate.feature_schema != FEATURE_SCHEMA:
        continue
      names = [_norm_name(path.stem), _norm_name(candidate.car)]
      names += [_norm_name(name) for name in candidate.car_names]
      name_score = max((len(name) for name in names for runtime_name in runtime_names
                        if name and runtime_name and (name in runtime_name or runtime_name in name)), default=-1)
      if name_score < 0:
        continue

      # Matching is by car name (from settings) and torque/angle kind only.
      # EPS hash is informational: matching hashes get a tiebreaker bonus,
      # but a mismatch (or missing hash) no longer disqualifies the model.
      eps_score = 0
      candidate_eps_hash = str(candidate.eps_firmware_hash or "").strip()
      if candidate_eps_hash and runtime_eps_hash and candidate_eps_hash == runtime_eps_hash:
        eps_score = 1000

      score = eps_score + name_score
      if score > best_score:
        best_path = path
        best_score = score

    runtime_car = runtime_names[0] if runtime_names else "<unknown>"
    if best_path is None:
      print(f"[CAS] no matching {expected_type} model for car={runtime_car} "
            f"eps={runtime_eps_hash or '<none>'}", flush=True)
      return

    self.model = CASModel(best_path)
    self.model_name = self.model.car or best_path.stem
    self.params.put_nonblocking(self.model_param, self.model_name.replace("_", " "))
    # Expose training hours for the HUD so users can see model trust at a glance.
    hours = float(self.model.meta.get("trained_on_hours", 0.0))
    self.params.put_nonblocking("CASModelHours", f"{hours:.2f}")
    eps_note = ""
    json_eps = str(self.model.eps_firmware_hash or "").strip()
    if json_eps and runtime_eps_hash and json_eps != runtime_eps_hash:
      eps_note = " (eps mismatch — name-matched, using anyway)"
    print(f"[CAS] matched {self.model.car} kind={self.kind} "
          f"eps={self.model.eps_firmware_hash or '<none>'} "
          f"runtime_eps={runtime_eps_hash or '<none>'} "
          f"hours={hours:.2f} alpha_max={self.model.alpha_max} "
          f"score={best_score}{eps_note}", flush=True)

  def update(self, CS, params, desired_curvature: float, measured_lateral_accel: float,
             model_data=None, CC=None, lateral_plan=None, lateral_delay: float = 0.0) -> tuple[float, float, list[float]]:
    if self.model is None or not self.params.get_bool(self.enabled_param):
      return 0.0, 0.0, []

    features = build_feature_vector(self.feature_state, CS, params, desired_curvature,
                                    measured_lateral_accel, model_data=model_data, CC=CC,
                                    lateral_plan=lateral_plan, lateral_delay=lateral_delay,
                                    t=time.monotonic())
    delta, max_abs_z = self.model.evaluate(features)
    alpha = self._alpha(CS, delta, max_abs_z)
    raw_delta = float(delta)
    applied_delta = float(alpha * raw_delta)
    if alpha <= 0.0:
      delta = 0.0

    # ── Centering / intervention bookkeeping ──
    # features layout (see features.py FEATURE_SPEC):
    #   [16] = lateralOffsetNow, [17] = lateralOffsetAvg5s (single sample),
    #   [0]  = vEgo
    offset_now = float(features[16]) if len(features) > 16 else 0.0
    self.offset_5s.append(offset_now)
    self.offset_60s.append(offset_now)

    offset_5s_avg = float(sum(self.offset_5s) / max(len(self.offset_5s), 1))
    offset_60s_avg = float(sum(self.offset_60s) / max(len(self.offset_60s), 1))

    # Rolling abs mean is a better centering score driver than signed average.
    abs_offsets_5s = [abs(v) for v in self.offset_5s]
    mean_abs_5s = float(sum(abs_offsets_5s) / max(len(abs_offsets_5s), 1))
    centering_score = max(0.0, min(100.0, (1.0 - mean_abs_5s / _CENTERING_FULL_M) * 100.0))

    # Intervention: rising edge of steeringPressed counts as one event.
    # Split strong / weak by the driver torque magnitude (mirrors lateral_data_marker).
    pressed = bool(CS.steeringPressed)
    now_t = time.monotonic()
    if pressed and not self._was_pressed:
      self.intervention_count += 1
      self.last_intervention_t = now_t
      driver_torque = abs(float(getattr(CS, "steeringTorque", 0.0)))
      if driver_torque >= 0.8:
        self.intervention_strong += 1
        self.last_strong_t = now_t
      elif driver_torque >= 0.2:
        self.intervention_weak += 1
        self.last_weak_t = now_t
      else:
        # Small touches still count toward weak.
        self.intervention_weak += 1
        self.last_weak_t = now_t
    self._was_pressed = pressed

    def _sec_since(last_t):
      return float(now_t - last_t) if last_t is not None else -1.0

    sec_since_intervention = _sec_since(self.last_intervention_t)
    sec_since_strong = _sec_since(self.last_strong_t)
    sec_since_weak = _sec_since(self.last_weak_t)
    session_seconds = max(now_t - self.session_start_t, 1e-3)

    # CAS accuracy: signed delta should push the car toward zero offset.
    # When offset > 0 (car is right of centerline) a left-pushing torque
    # is correct; sign convention follows offset >0=right / <0=left and
    # delta >0=correction-toward-right / <0=toward-left.
    # → correct when sign(delta) opposes sign(offset_now).
    correct = 0
    if abs(applied_delta) > 1e-4 and abs(offset_now) > 0.01:
      if (applied_delta > 0.0) != (offset_now > 0.0):
        correct = 1
    if abs(applied_delta) > 1e-4:
      self.acc_window.append(correct)
    accuracy_pct = 0.0
    if len(self.acc_window) > 0:
      accuracy_pct = 100.0 * sum(self.acc_window) / len(self.acc_window)

    # Distribution-in fraction: vEgo within learned vego_min..vego_max.
    if self.model is not None:
      in_dist = 1.0 if (self.model.vego_min <= CS.vEgo <= self.model.vego_max) else 0.0
    else:
      in_dist = 0.0
    self.dist_in_window.append(in_dist)
    dist_in_pct = 100.0 * sum(self.dist_in_window) / max(len(self.dist_in_window), 1)

    # Lane pattern code over the 60 s window (HUD turns this into Korean text).
    # 0 = stable, 1 = drift left, 2 = drift right, 3 = oscillating.
    if len(self.offset_60s) >= 50:
      sample = list(self.offset_60s)
      mean_off = sum(sample) / len(sample)
      var_off = sum((s - mean_off) ** 2 for s in sample) / len(sample)
      std_off = var_off ** 0.5
      if std_off > 0.05:
        lane_pattern = 3.0
      elif mean_off > 0.02:
        lane_pattern = 2.0
      elif mean_off < -0.02:
        lane_pattern = 1.0
      else:
        lane_pattern = 0.0
    else:
      lane_pattern = 0.0

    # Append diagnostics to casLog. Indexed from the end by carrot.cc.
    # Layout: features (20) + extras (19).
    extras = [
      raw_delta,                            # [-19]
      applied_delta,                        # [-18]
      float(alpha),                          # [-17]
      float(max_abs_z),                      # [-16]
      offset_now,                            # [-15]
      offset_5s_avg,                         # [-14]
      offset_60s_avg,                        # [-13]
      mean_abs_5s,                           # [-12]
      centering_score,                       # [-11]
      float(self.intervention_count),        # [-10]
      sec_since_intervention,                # [ -9]
      float(self.intervention_strong),       # [ -8]
      float(self.intervention_weak),         # [ -7]
      sec_since_strong,                      # [ -6]
      sec_since_weak,                        # [ -5]
      accuracy_pct,                          # [ -4]
      session_seconds,                       # [ -3]
      dist_in_pct,                           # [ -2]
      lane_pattern,                          # [ -1]
    ]
    cas_log = features + extras
    return float(delta), float(alpha), cas_log

  def _alpha(self, CS, delta: float, max_abs_z: float) -> float:
    # Multiplicative gate: alpha_final = alpha_max
    #   * gate_user (hard off if user pressed)
    #   * gate_speed (ramp 5..7 m/s)
    #   * gate_finite (hard off on NaN / extreme delta)
    #   * gate_distribution (ramp |z| 2.0..3.0)
    # Safety invariant I1 preserved: any factor 0 -> alpha 0 -> base output unchanged.
    if self.model is None:
      return 0.0

    if CS.steeringPressed:
      return 0.0
    if not math.isfinite(delta) or abs(delta) > 3.0:
      return 0.0

    # Speed ramp: 0 below vego_min, full +2 m/s above; taper near vego_max.
    vego_min = self.model.vego_min
    vego_max = self.model.vego_max
    if CS.vEgo < vego_min:
      return 0.0
    gate_speed_low = min(1.0, max(0.0, (CS.vEgo - vego_min) / 2.0))
    # Taper down in the last 5 m/s before vego_max (so high-speed extrapolation is gentle).
    if CS.vEgo >= vego_max:
      gate_speed_high = 0.0
    elif CS.vEgo > vego_max - 5.0:
      gate_speed_high = max(0.0, (vego_max - CS.vEgo) / 5.0)
    else:
      gate_speed_high = 1.0
    gate_speed = gate_speed_low * gate_speed_high

    # Distribution ramp: full below |z|=2, taper to 0 by |z|=3.
    if max_abs_z >= 3.0:
      return 0.0
    gate_distribution = 1.0 if max_abs_z <= 2.0 else max(0.0, (3.0 - max_abs_z))

    # CASAlphaOverride: 0 = use JSON default, 1~50 = override 0.01~0.50.
    # Safety gates (steeringPressed/NaN/speed/distribution) still apply on top.
    override = self.params.get_int("CASAlphaOverride")
    if override > 0:
      alpha_max = max(0.0, min(0.5, override / 100.0))
    else:
      alpha_max = max(0.0, min(1.0, float(self.model.alpha_max)))
    return alpha_max * gate_speed * gate_distribution
