#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))


def lateral_offset_metrics(offsets) -> dict[str, float]:
  arr = np.asarray(list(offsets), dtype=np.float32)
  if arr.size == 0:
    return {"count": 0, "mean_abs": 0.0, "std": 0.0, "max_abs": 0.0}
  return {
    "count": int(arr.size),
    "mean_abs": float(np.mean(np.abs(arr))),
    "std": float(np.std(arr)),
    "max_abs": float(np.max(np.abs(arr))),
  }


def prediction_metrics(y_true, y_pred, weights=None) -> dict[str, float]:
  y_true = np.asarray(y_true, dtype=np.float32).reshape(-1)
  y_pred = np.asarray(y_pred, dtype=np.float32).reshape(-1)
  if y_true.size == 0:
    return {"count": 0, "mae": 0.0, "rmse": 0.0, "weighted_rmse": 0.0}

  err = y_pred - y_true
  rmse = float(np.sqrt(np.mean(err * err)))
  mae = float(np.mean(np.abs(err)))
  out = {"count": int(y_true.size), "mae": mae, "rmse": rmse, "weighted_rmse": rmse}
  if weights is not None:
    w = np.asarray(weights, dtype=np.float32).reshape(-1)
    denom = float(np.sum(w))
    if denom > 1e-6:
      out["weighted_rmse"] = float(np.sqrt(np.sum(w * err * err) / denom))
  return out


def format_counts(counts) -> dict[str, int]:
  return {str(key): int(value) for key, value in sorted(counts.items(), key=lambda item: str(item[0]))}


def array_metrics(values, percentiles=(50, 90, 95, 99)) -> dict[str, float]:
  arr = np.asarray(list(values), dtype=np.float32).reshape(-1)
  if arr.size == 0:
    out = {"count": 0, "mean": 0.0, "mean_abs": 0.0, "std": 0.0, "max_abs": 0.0}
    for pct in percentiles:
      out[f"p{pct}_abs"] = 0.0
    return out

  out = {
    "count": int(arr.size),
    "mean": float(np.mean(arr)),
    "mean_abs": float(np.mean(np.abs(arr))),
    "std": float(np.std(arr)),
    "max_abs": float(np.max(np.abs(arr))),
  }
  abs_arr = np.abs(arr)
  for pct in percentiles:
    out[f"p{pct}_abs"] = float(np.percentile(abs_arr, pct))
  return out


def evaluate_model(model, samples):
  from tools.cas.triage import TriageType

  deltas = []
  applied = []
  max_abs_zs = []
  blocked = Counter()
  gate_pass = 0

  for sample in samples:
    delta, max_abs_z = model.evaluate(sample.features)
    alpha = float(model.alpha_max)
    v_ego = float(sample.features[0]) if sample.features else 0.0

    if v_ego < 5.0:
      alpha = 0.0
      blocked["low_speed"] += 1
    elif sample.flag in (TriageType.T3_STRONG_INTERVENTION, TriageType.T4_WEAK_INTERVENTION, TriageType.T5_MANUAL):
      alpha = 0.0
      blocked["driver_or_manual"] += 1
    elif not np.isfinite(delta) or abs(delta) > 3.0:
      alpha = 0.0
      blocked["delta_limit"] += 1
    elif max_abs_z > 3.0:
      alpha = 0.0
      blocked["input_z_limit"] += 1
    else:
      gate_pass += 1

    deltas.append(float(delta))
    applied.append(float(alpha * delta))
    max_abs_zs.append(float(max_abs_z))

  count = len(samples)
  return {
    "delta": array_metrics(deltas),
    "applied_delta": array_metrics(applied),
    "max_abs_z": array_metrics(max_abs_zs),
    "gate_pass_count": int(gate_pass),
    "gate_pass_rate": float(gate_pass / count) if count else 0.0,
    "blocked_counts": format_counts(blocked),
  }


def main():
  parser = argparse.ArgumentParser(description="Validate a CAS JSON model against rlogs.")
  parser.add_argument("--model", required=True, help="CAS JSON model path")
  parser.add_argument("--rlogs", nargs="+", required=True, help="rlog files, route URLs, or directories")
  parser.add_argument("--sample-stride", type=int, default=10)
  parser.add_argument("--min-file-age-sec", type=float, default=0.0, help="skip recently modified rlogs")
  parser.add_argument("--max-sources", type=int, help="limit number of expanded rlog sources")
  parser.add_argument("--workers", type=int, default=1, help="parallel rlog parser workers")
  parser.add_argument("--offset-horizon", type=float, default=0.5)
  parser.add_argument("--offset-gain", type=float, default=0.35)
  parser.add_argument("--driver-torque-scale", type=float, default=0.25)
  parser.add_argument("--driver-torque-sign", type=float, default=1.0)
  parser.add_argument("--target-clip", type=float, default=0.5)
  parser.add_argument("--include-manual", action="store_true")
  parser.add_argument("--output", help="optional JSON summary output path")
  parser.add_argument("--audit-dir", help="write detailed raw/audit logs to this directory")
  parser.add_argument("--audit-samples", action="store_true", help="write collected sample records to samples.jsonl")
  args = parser.parse_args()

  from tools.cas.train import AuditLogger, build_targets, collect_samples, expand_sources, install_openpilot_aliases, source_inventory
  install_openpilot_aliases()
  try:
    from openpilot.selfdrive.carrot.cas.model import CASModel
  except ModuleNotFoundError:
    from selfdrive.carrot.cas.model import CASModel

  sources = expand_sources(args.rlogs, args.min_file_age_sec)
  if args.max_sources is not None:
    sources = sources[:args.max_sources]
  audit = AuditLogger(Path(args.audit_dir).expanduser() if args.audit_dir else None, args.audit_samples)
  audit.write_json("source_inventory.json", source_inventory(sources))
  audit.write_json("validate_args.json", vars(args))
  samples, duration_h, message_counts = collect_samples(sources, max(args.sample_stride, 1), audit, args.workers)
  x, y, weights, target_counts, offsets = build_targets(
    samples,
    args.offset_horizon,
    args.offset_gain,
    args.driver_torque_scale,
    args.driver_torque_sign,
    args.target_clip,
    args.include_manual,
  )

  model = CASModel(args.model)
  if x.size:
    predictions = np.asarray([model.evaluate(row)[0] for row in x], dtype=np.float32)
    target_metrics = prediction_metrics(y, predictions, weights)
  else:
    target_metrics = prediction_metrics([], [])

  collected_counts = Counter(sample.flag.name for sample in samples)
  summary = {
    "model": str(Path(args.model)),
    "car": model.car,
    "model_type": model.model_type,
    "alpha_max": float(model.alpha_max),
    "source_count": len(sources),
    "duration_hours": float(duration_h),
    "collected_samples": len(samples),
    "usable_samples": int(x.shape[0]) if x.ndim else 0,
    "message_counts": format_counts(message_counts),
    "collected_triage_counts": format_counts(collected_counts),
    "target_triage_counts": format_counts(target_counts),
    "offset_metrics": lateral_offset_metrics(offsets),
    "target_metrics": target_metrics,
    "output_metrics": evaluate_model(model, samples),
  }

  text = json.dumps(summary, indent=2, sort_keys=True)
  print(text)
  if args.output:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")
  audit.write_json("validate_summary.json", summary)


if __name__ == "__main__":
  main()
