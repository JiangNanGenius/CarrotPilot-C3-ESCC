#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

try:
  from openpilot.selfdrive.carrot.cas.features import FEATURE_SPEC
  from openpilot.tools.cas.export_json import write_json_model
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import FEATURE_SPEC
  from tools.cas.export_json import write_json_model


def build_dummy(car: str, kind: str, alpha_max: float):
  return {
    "format_version": 1,
    "model_type": f"cas_{kind}",
    "car": car,
    "eps_firmware_hash": "",
    "trained_on_hours": 0.0,
    "trained_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    "trained_by": "jominki354",
    "input_size": len(FEATURE_SPEC),
    "output_size": 1,
    "input_mean": np.zeros(len(FEATURE_SPEC), dtype=np.float32).tolist(),
    "input_std": np.ones(len(FEATURE_SPEC), dtype=np.float32).tolist(),
    "feature_spec": FEATURE_SPEC,
    "layers": [
      {
        "W_0": np.zeros((len(FEATURE_SPEC), 1), dtype=np.float32).tolist(),
        "b_0": [0.0],
        "activation": "identity",
      },
    ],
    "alpha_max": float(alpha_max),
    "validation": {
      "status": "dummy",
      "mean_lateral_offset_m": None,
    },
    "friction_override": False,
    "use_steering_angle": True,
  }


def main():
  parser = argparse.ArgumentParser(description="Create a zero-output CAS JSON model.")
  parser.add_argument("--car", required=True)
  parser.add_argument("--output", required=True)
  parser.add_argument("--kind", choices=("torque", "angle"), default="torque")
  parser.add_argument("--alpha-max", type=float, default=0.0)
  args = parser.parse_args()

  output = Path(args.output)
  write_json_model(output, build_dummy(args.car, args.kind, args.alpha_max))
  print(f"wrote: {output}")


if __name__ == "__main__":
  main()
