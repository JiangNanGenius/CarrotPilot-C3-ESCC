from __future__ import annotations

from pathlib import Path
import math
import re

from openpilot.common.params import Params
try:
  from openpilot.selfdrive.carrot.cas.features import CASFeatureState, build_feature_vector
  from openpilot.selfdrive.carrot.cas.model import CASModel
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import CASFeatureState, build_feature_vector
  from selfdrive.carrot.cas.model import CASModel


CAS_DIR = Path(__file__).resolve().parent
WEIGHTS_DIR = CAS_DIR / "weights"


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
    if alpha <= 0.0:
      delta = 0.0

    cas_log = features + [float(delta), float(alpha), float(max_abs_z)]
    return float(delta), float(alpha), cas_log

  def _alpha(self, CS, delta: float, max_abs_z: float) -> float:
    if self.model is None:
      return 0.0
    if CS.steeringPressed or CS.vEgo < 5.0:
      return 0.0
    if not math.isfinite(delta) or abs(delta) > 3.0:
      return 0.0
    if max_abs_z > 3.0:
      return 0.0
    return max(0.0, min(1.0, float(self.model.alpha_max)))
