import json
from pathlib import Path

try:
  from openpilot.selfdrive.carrot.cas.features import FEATURE_SCHEMA, FEATURE_SPEC
  from openpilot.selfdrive.carrot.cas.metadata import FORMAT_VERSION
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import FEATURE_SCHEMA, FEATURE_SPEC
  from selfdrive.carrot.cas.metadata import FORMAT_VERSION


def build_json_model(car: str, kind: str, model, input_mean, input_std, validation,
                     trained_at: str, trained_on_hours: float, alpha_max: float,
                     trained_by: str = "jominki354", use_steering_angle: bool = True,
                     eps_firmware_hash: str = "",
                     output_clip: tuple[float, float] = (-0.3, 0.3),
                     vego_min: float = 5.0, vego_max: float = 35.0,
                     lateral_delay_at_train: float = 0.0,
                     trained_rlog_count: int = 0,
                     car_names: list[str] | None = None,
                     friction_override: bool = False):
  layers = []
  for i, layer in enumerate(model.layers):
    W, b, activation = layer
    layers.append({
      f"W_{i}": W.tolist(),
      f"b_{i}": b.tolist(),
      "activation": activation,
    })

  return {
    "format_version": FORMAT_VERSION,
    "model_type": f"cas_{kind}",
    "kind": kind,
    "car": car,
    "car_names": list(car_names) if car_names else [car],
    "eps_firmware_hash": eps_firmware_hash,
    "feature_schema": FEATURE_SCHEMA,
    "trained_at": trained_at,
    "trained_by": trained_by,
    "trained_on_hours": float(trained_on_hours),
    "trained_rlog_count": int(trained_rlog_count),
    "input_size": len(FEATURE_SPEC),
    "output_size": 1,
    "input_mean": input_mean.tolist(),
    "input_std": input_std.tolist(),
    "feature_spec": FEATURE_SPEC,
    "layers": layers,
    "alpha_max": float(alpha_max),
    "output_clip": [float(output_clip[0]), float(output_clip[1])],
    "vego_min": float(vego_min),
    "vego_max": float(vego_max),
    "lateral_delay_at_train": float(lateral_delay_at_train),
    "use_steering_angle": bool(use_steering_angle),
    "friction_override": bool(friction_override),
    "validation": validation,
  }


def write_json_model(path, payload):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, sort_keys=True)
    f.write("\n")
