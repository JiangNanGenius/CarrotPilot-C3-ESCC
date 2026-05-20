from __future__ import annotations

from collections import deque
from pathlib import Path
import math
import re
import time

from openpilot.common.params import Params
try:
  from openpilot.selfdrive.carrot.cas.features import CASFeatureState, build_feature_vector
  from openpilot.selfdrive.carrot.cas.model import CASModel
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import CASFeatureState, build_feature_vector
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
    self.intervention_count = 0
    self._was_pressed = False
    self.last_intervention_t: float | None = None
    self.session_start_t = time.monotonic()
    self.load_model()

  def load_model(self):
    self.model = None
    self.model_name = ""
    self.params.remove(self.model_param)
    if not WEIGHTS_DIR.exists():
      return

    car_name = _norm_name(getattr(self.CP, "carFingerprint", ""))
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
      names = [_norm_name(path.stem), _norm_name(candidate.car)]
      score = max((len(name) for name in names if name and (name in car_name or car_name in name)), default=-1)
      if score > best_score:
        best_path = path
        best_score = score

    if best_path is None:
      return

    self.model = CASModel(best_path)
    self.model_name = self.model.car or best_path.stem
    self.params.put_nonblocking(self.model_param, self.model_name.replace("_", " "))

  def update(self, CS, params, desired_curvature: float, measured_lateral_accel: float,
             model_data=None, CC=None, lateral_plan=None, lateral_delay: float = 0.0) -> tuple[float, float, list[float]]:
    if self.model is None or not self.params.get_bool(self.enabled_param):
      return 0.0, 0.0, []

    features = build_feature_vector(self.feature_state, CS, params, desired_curvature,
                                    measured_lateral_accel, model_data=model_data, CC=CC,
                                    lateral_plan=lateral_plan, lateral_delay=lateral_delay)
    delta, max_abs_z = self.model.evaluate(features)
    alpha = self._alpha(CS, delta, max_abs_z)
    raw_delta = float(delta)
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
    pressed = bool(CS.steeringPressed)
    if pressed and not self._was_pressed:
      self.intervention_count += 1
      self.last_intervention_t = time.monotonic()
    self._was_pressed = pressed

    sec_since_intervention = -1.0
    if self.last_intervention_t is not None:
      sec_since_intervention = float(time.monotonic() - self.last_intervention_t)
    session_minutes = max((time.monotonic() - self.session_start_t) / 60.0, 1e-3)
    intervention_rate_per_min = float(self.intervention_count) / session_minutes

    # Append diagnostics to casLog. Order is fixed; HUD reads by index from
    # the end (see selfdrive/ui/carrot.cc CAS overlay).
    # Layout: features (20) + extras (11).
    extras = [
      raw_delta,                          # [-11] NN raw output (pre-alpha)
      float(delta),                       # [-10] applied delta (post-alpha gate)
      float(alpha),                        # [ -9] alpha (final, post multiplicative gate)
      float(max_abs_z),                    # [ -8] distribution z
      offset_now,                          # [ -7] m, instantaneous lateral offset
      offset_5s_avg,                       # [ -6] m, 5 s rolling mean (signed)
      offset_60s_avg,                      # [ -5] m, 60 s rolling mean (signed)
      mean_abs_5s,                         # [ -4] m, 5 s rolling |offset| mean
      centering_score,                     # [ -3] 0..100
      float(self.intervention_count),      # [ -2] cumulative interventions this session
      sec_since_intervention,              # [ -1] s since last (or -1.0 if none)
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

    alpha_max = max(0.0, min(1.0, float(self.model.alpha_max)))
    return alpha_max * gate_speed * gate_distribution
