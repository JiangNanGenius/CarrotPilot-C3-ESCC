#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

try:
  from openpilot.selfdrive.carrot.cas.features import FEATURE_SPEC
  from openpilot.selfdrive.carrot.cas.model import CASModel
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import FEATURE_SPEC
  from selfdrive.carrot.cas.model import CASModel


def _norm_car_name(car: str) -> str:
  return car.replace(" ", "_").upper()


def load_payload(path: Path):
  with open(path, "r", encoding="utf-8") as f:
    return json.load(f)


def validate_candidate(path: Path, car: str | None, kind: str | None,
                       max_alpha: float, min_hours: float):
  payload = load_payload(path)
  model = CASModel(path)

  errors = []
  if payload.get("format_version") != 1:
    errors.append("format_version must be 1")
  if payload.get("feature_spec") != FEATURE_SPEC:
    errors.append("feature_spec does not match runtime FEATURE_SPEC")
  if car is not None and _norm_car_name(model.car) != _norm_car_name(car):
    errors.append(f"car mismatch: expected {car}, got {model.car}")
  if kind is not None and model.model_type != f"cas_{kind}":
    errors.append(f"model_type mismatch: expected cas_{kind}, got {model.model_type}")
  if model.alpha_max < 0.0 or model.alpha_max > max_alpha:
    errors.append(f"alpha_max {model.alpha_max} exceeds limit {max_alpha}")
  if float(payload.get("trained_on_hours", 0.0)) < min_hours:
    errors.append(f"trained_on_hours {payload.get('trained_on_hours', 0.0)} is below {min_hours}")

  model.evaluate([0.0] * model.input_size)
  return payload, model, errors


def default_output_path(model: CASModel) -> Path:
  name = _norm_car_name(model.car or Path(model.params_file).stem)
  return REPO_ROOT / "selfdrive" / "carrot" / "cas" / "weights" / f"{name}.json"


def main():
  parser = argparse.ArgumentParser(description="Promote a validated CAS candidate JSON into device weights.")
  parser.add_argument("--candidate", required=True, help="candidate CAS JSON path")
  parser.add_argument("--output", help="destination weights JSON path")
  parser.add_argument("--car", help="expected car name")
  parser.add_argument("--kind", choices=("torque", "angle"), help="expected CAS model kind")
  parser.add_argument("--max-alpha", type=float, default=0.1)
  parser.add_argument("--min-hours", type=float, default=0.0)
  parser.add_argument("--force", action="store_true", help="overwrite existing output")
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  candidate = Path(args.candidate)
  payload, model, errors = validate_candidate(candidate, args.car, args.kind, args.max_alpha, args.min_hours)
  output = Path(args.output) if args.output else default_output_path(model)

  if errors:
    for error in errors:
      print(f"ERROR: {error}")
    raise SystemExit(1)
  if output.exists() and not args.force and not args.dry_run:
    print(f"ERROR: output exists: {output} (use --force)")
    raise SystemExit(1)

  print(f"candidate: {candidate}")
  print(f"car: {model.car}")
  print(f"model_type: {model.model_type}")
  print(f"trained_on_hours: {payload.get('trained_on_hours', 0.0)}")
  print(f"alpha_max: {model.alpha_max}")
  print(f"output: {output}")

  if args.dry_run:
    print("dry-run: no files written")
    return

  output.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(candidate, output)
  print("promoted")


if __name__ == "__main__":
  main()
