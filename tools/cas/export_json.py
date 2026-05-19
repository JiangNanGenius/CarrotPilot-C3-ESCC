import json
from pathlib import Path

try:
  from openpilot.selfdrive.carrot.cas.features import FEATURE_SPEC
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import FEATURE_SPEC


def build_json_model(car: str, kind: str, model, input_mean, input_std, validation,
                     trained_at: str, trained_on_hours: float, alpha_max: float,
                     trained_by: str = "jominki354", use_steering_angle: bool = True,
                     eps_firmware_hash: str = ""):
  layers = []
  for i, layer in enumerate(model.layers):
    W, b, activation = layer
    layers.append({
      f"W_{i}": W.tolist(),
      f"b_{i}": b.tolist(),
      "activation": activation,
    })

  return {
    "format_version": 1,
    "model_type": f"cas_{kind}",
    "car": car,
    "eps_firmware_hash": eps_firmware_hash,
    "trained_at": trained_at,
    "trained_by": trained_by,
    "trained_on_hours": float(trained_on_hours),
    "input_size": len(FEATURE_SPEC),
    "output_size": 1,
    "input_mean": input_mean.tolist(),
    "input_std": input_std.tolist(),
    "feature_spec": FEATURE_SPEC,
    "layers": layers,
    "alpha_max": float(alpha_max),
    "validation": validation,
    "friction_override": False,
    "use_steering_angle": bool(use_steering_angle),
  }


def write_json_model(path, payload):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, sort_keys=True)
    f.write("\n")
