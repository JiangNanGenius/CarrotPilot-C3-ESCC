#!/usr/bin/env python3
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import types

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))


def install_openpilot_aliases():
  openpilot_pkg = sys.modules.get("openpilot")
  if openpilot_pkg is None:
    openpilot_pkg = types.ModuleType("openpilot")
    openpilot_pkg.__path__ = [str(REPO_ROOT)]
    sys.modules["openpilot"] = openpilot_pkg

  for name in ("common", "tools", "selfdrive", "system", "cereal"):
    if f"openpilot.{name}" in sys.modules:
      continue
    try:
      module = __import__(name)
    except ModuleNotFoundError:
      continue
    setattr(openpilot_pkg, name, module)
    sys.modules[f"openpilot.{name}"] = module

  if "openpilot.system.hardware.hw" not in sys.modules:
    hardware_pkg = types.ModuleType("openpilot.system.hardware")
    hw_pkg = types.ModuleType("openpilot.system.hardware.hw")

    class Paths:
      @staticmethod
      def swaglog_root():
        return "/tmp/cas_swaglog"

      @staticmethod
      def swaglog_ipc():
        return "ipc:///tmp/cas_logmessage"

    hw_pkg.Paths = Paths
    sys.modules["openpilot.system.hardware"] = hardware_pkg
    sys.modules["openpilot.system.hardware.hw"] = hw_pkg

try:
  from openpilot.selfdrive.carrot.cas.features import CASFeatureState, build_feature_vector, lane_center_offset
  from openpilot.tools.cas.export_json import build_json_model, write_json_model
  from openpilot.tools.cas.triage import TRIAGE_WEIGHTS, TriageType, classify_sample, coerce_triage
  from openpilot.tools.cas.validate import format_counts, lateral_offset_metrics, prediction_metrics
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import CASFeatureState, build_feature_vector, lane_center_offset
  from tools.cas.export_json import build_json_model, write_json_model
  from tools.cas.triage import TRIAGE_WEIGHTS, TriageType, classify_sample, coerce_triage
  from tools.cas.validate import format_counts, lateral_offset_metrics, prediction_metrics


LOG_FILENAMES = {"rlog", "rlog.bz2", "rlog.zst", "raw_log.bz2"}
LOG_SUFFIXES = ("--rlog", "--rlog.bz2", "--rlog.zst", "--raw_log.bz2")


@dataclass
class Sample:
  t: float
  features: list[float]
  flag: TriageType
  offset: float
  driver_torque: float


class NumpyMLP:
  def __init__(self, input_size: int, hidden_sizes: tuple[int, ...] = (32, 16), seed: int = 0):
    rng = np.random.default_rng(seed)
    sizes = (input_size, *hidden_sizes, 1)
    self.layers = []
    for i in range(len(sizes) - 1):
      scale = np.sqrt(2.0 / max(sizes[i], 1))
      W = rng.normal(0.0, scale, size=(sizes[i], sizes[i + 1])).astype(np.float32)
      b = np.zeros(sizes[i + 1], dtype=np.float32)
      activation = "identity" if i == len(sizes) - 2 else "tanh"
      self.layers.append((W, b, activation))

  @staticmethod
  def _activate(x, activation):
    if activation == "tanh":
      return np.tanh(x)
    return x

  @staticmethod
  def _activation_grad(y, activation):
    if activation == "tanh":
      return 1.0 - y * y
    return np.ones_like(y)

  def predict(self, x):
    out = x
    for W, b, activation in self.layers:
      out = self._activate(out @ W + b, activation)
    return out

  def fit(self, x, y, weights, epochs: int, batch_size: int, lr: float, l2: float, seed: int):
    rng = np.random.default_rng(seed)
    y = y.reshape(-1, 1).astype(np.float32)
    weights = weights.reshape(-1, 1).astype(np.float32)
    m_w = [np.zeros_like(W) for W, _, _ in self.layers]
    v_w = [np.zeros_like(W) for W, _, _ in self.layers]
    m_b = [np.zeros_like(b) for _, b, _ in self.layers]
    v_b = [np.zeros_like(b) for _, b, _ in self.layers]
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    step = 0

    for _ in range(epochs):
      order = rng.permutation(x.shape[0])
      for start in range(0, x.shape[0], batch_size):
        idx = order[start:start + batch_size]
        xb, yb, wb = x[idx], y[idx], weights[idx]

        activations = [xb]
        pre_activations = []
        out = xb
        for W, b, activation in self.layers:
          z = out @ W + b
          out = self._activate(z, activation)
          pre_activations.append(z)
          activations.append(out)

        denom = max(float(np.sum(wb)), 1e-6)
        grad = 2.0 * wb * (activations[-1] - yb) / denom
        grads_w = []
        grads_b = []
        for layer_idx in reversed(range(len(self.layers))):
          W, _, activation = self.layers[layer_idx]
          grad = grad * self._activation_grad(activations[layer_idx + 1], activation)
          grad_w = activations[layer_idx].T @ grad + l2 * W
          grad_b = np.sum(grad, axis=0)
          grads_w.append(grad_w)
          grads_b.append(grad_b)
          grad = grad @ W.T
        grads_w.reverse()
        grads_b.reverse()

        step += 1
        for i, (W, b, activation) in enumerate(self.layers):
          m_w[i] = beta1 * m_w[i] + (1.0 - beta1) * grads_w[i]
          v_w[i] = beta2 * v_w[i] + (1.0 - beta2) * (grads_w[i] * grads_w[i])
          m_b[i] = beta1 * m_b[i] + (1.0 - beta1) * grads_b[i]
          v_b[i] = beta2 * v_b[i] + (1.0 - beta2) * (grads_b[i] * grads_b[i])
          W -= lr * (m_w[i] / (1.0 - beta1 ** step)) / (np.sqrt(v_w[i] / (1.0 - beta2 ** step)) + eps)
          b -= lr * (m_b[i] / (1.0 - beta1 ** step)) / (np.sqrt(v_b[i] / (1.0 - beta2 ** step)) + eps)
          self.layers[i] = (W.astype(np.float32), b.astype(np.float32), activation)


def train_torch_mlp(x, y, weights, input_size: int, hidden_sizes: tuple[int, ...],
                    epochs: int, batch_size: int, lr: float, l2: float,
                    seed: int, device_name: str):
  import torch

  if device_name == "auto":
    device_name = "cuda" if torch.cuda.is_available() else "cpu"
  device = torch.device(device_name)
  torch.manual_seed(seed)

  sizes = (input_size, *hidden_sizes, 1)
  modules = []
  activations = []
  for i in range(len(sizes) - 1):
    layer = torch.nn.Linear(sizes[i], sizes[i + 1])
    torch.nn.init.kaiming_normal_(layer.weight, nonlinearity="linear")
    torch.nn.init.zeros_(layer.bias)
    modules.append(layer)
    activations.append("identity" if i == len(sizes) - 2 else "tanh")
  modules = torch.nn.ModuleList(modules).to(device)

  x_t = torch.as_tensor(x, dtype=torch.float32, device=device)
  y_t = torch.as_tensor(y.reshape(-1, 1), dtype=torch.float32, device=device)
  w_t = torch.as_tensor(weights.reshape(-1, 1), dtype=torch.float32, device=device)
  optimizer = torch.optim.AdamW(modules.parameters(), lr=lr, weight_decay=l2)
  generator = torch.Generator(device=device)
  generator.manual_seed(seed)

  def forward(batch):
    out = batch
    for layer, activation in zip(modules, activations, strict=True):
      out = layer(out)
      if activation == "tanh":
        out = torch.tanh(out)
    return out

  for _ in range(epochs):
    order = torch.randperm(x_t.shape[0], generator=generator, device=device)
    for start in range(0, x_t.shape[0], batch_size):
      idx = order[start:start + batch_size]
      pred = forward(x_t[idx])
      denom = torch.clamp(torch.sum(w_t[idx]), min=1e-6)
      loss = torch.sum(w_t[idx] * torch.square(pred - y_t[idx])) / denom
      optimizer.zero_grad(set_to_none=True)
      loss.backward()
      optimizer.step()

  model = NumpyMLP(input_size, hidden_sizes=hidden_sizes, seed=seed)
  model.layers = []
  for layer, activation in zip(modules, activations, strict=True):
    W = layer.weight.detach().cpu().numpy().T.astype(np.float32)
    b = layer.bias.detach().cpu().numpy().astype(np.float32)
    model.layers.append((W, b, activation))
  return model, str(device)


def train_model(x, y, weights, input_size: int, backend: str, device: str,
                epochs: int, batch_size: int, lr: float, l2: float, seed: int):
  if backend == "auto":
    try:
      import torch
      backend = "torch" if torch.cuda.is_available() else "numpy"
    except ModuleNotFoundError:
      backend = "numpy"

  if backend == "torch":
    try:
      return train_torch_mlp(x, y, weights, input_size, (32, 16), epochs, batch_size, lr, l2, seed, device)
    except ModuleNotFoundError as e:
      raise RuntimeError("PyTorch backend requested, but torch is not installed") from e

  model = NumpyMLP(input_size, seed=seed)
  model.fit(x, y, weights, epochs, batch_size, lr, l2, seed)
  return model, "numpy"


def _stable_file(path: Path, min_file_age_sec: float) -> bool:
  if min_file_age_sec <= 0.0:
    return True
  try:
    return time.time() - path.stat().st_mtime >= min_file_age_sec
  except OSError:
    return False


def expand_sources(sources: list[str], min_file_age_sec: float = 0.0) -> list[str]:
  expanded = []
  for source in sources:
    path = Path(source).expanduser()
    if path.is_dir():
      files = sorted(p for p in path.rglob("*")
                     if (p.name in LOG_FILENAMES or p.name.endswith(LOG_SUFFIXES)) and _stable_file(p, min_file_age_sec))
      expanded.extend(str(p) for p in files)
    else:
      if not path.exists() or _stable_file(path, min_file_age_sec):
        expanded.append(source)
  return expanded


def _to_float(value, default: float = 0.0) -> float:
  try:
    return float(value)
  except (TypeError, ValueError):
    return default


def _lateral_state(controls_state):
  try:
    which = controls_state.lateralControlState.which()
    return getattr(controls_state.lateralControlState, which)
  except Exception:
    return None


def _measured_lateral_accel(controls_state, car_state) -> float:
  lateral_state = _lateral_state(controls_state)
  if lateral_state is not None and hasattr(lateral_state, "actualLateralAccel"):
    return _to_float(lateral_state.actualLateralAccel)
  return _to_float(controls_state.curvature) * _to_float(car_state.vEgo) ** 2


def _lateral_offset(model_data, lateral_plan) -> float:
  lane_offset = lane_center_offset(model_data)
  if lane_offset is not None:
    return lane_offset
  if lateral_plan is not None and len(lateral_plan.position.y) > 1:
    return _to_float(lateral_plan.position.y[1])
  if model_data is not None and len(model_data.position.y) > 1:
    return _to_float(model_data.position.y[1])
  return 0.0


def _latest_lateral_delay(live_delay) -> float:
  if live_delay is None:
    return 0.0
  return _to_float(getattr(live_delay, "lateralDelay", 0.0))


def _flag_from_message(info):
  if info is None:
    return None
  return coerce_triage(getattr(info, "lateralLearningFlag", TriageType.EXCLUDE))


def collect_samples(sources: list[str], sample_stride: int) -> tuple[list[Sample], float, Counter]:
  install_openpilot_aliases()
  try:
    from openpilot.tools.lib.logreader import LogReader
  except ModuleNotFoundError:
    from tools.lib.logreader import LogReader

  samples: list[Sample] = []
  counts = Counter()
  feature_state = CASFeatureState()
  latest = SimpleNamespace(
    carState=None,
    liveParameters=None,
    modelV2=None,
    carControl=None,
    lateralPlan=None,
    liveDelay=None,
    lateralLearningInfo=None,
  )
  first_t = None
  last_t = None
  frame = 0

  for source in sources:
    for msg in LogReader(source):
      which = msg.which()
      counts[which] += 1
      t = msg.logMonoTime * 1e-9
      first_t = t if first_t is None else min(first_t, t)
      last_t = t if last_t is None else max(last_t, t)

      if which == "carState":
        latest.carState = msg.carState
      elif which == "liveParameters":
        latest.liveParameters = msg.liveParameters
      elif which == "modelV2":
        latest.modelV2 = msg.modelV2
      elif which == "carControl":
        latest.carControl = msg.carControl
      elif which == "lateralPlan":
        latest.lateralPlan = msg.lateralPlan
      elif which == "liveDelay":
        latest.liveDelay = msg.liveDelay
      elif which == "lateralLearningInfo":
        latest.lateralLearningInfo = msg.lateralLearningInfo
      elif which == "controlsState":
        if latest.carState is None or latest.liveParameters is None:
          continue
        frame += 1
        if frame % sample_stride != 0:
          continue

        controls_state = msg.controlsState
        car_control = latest.carControl or SimpleNamespace(latActive=False, orientationNED=[], angularVelocity=[])
        offset = _lateral_offset(latest.modelV2, latest.lateralPlan)
        flag = _flag_from_message(latest.lateralLearningInfo)
        if flag is None:
          flag = classify_sample(bool(getattr(car_control, "latActive", False)),
                                 bool(latest.carState.steeringPressed),
                                 _to_float(latest.carState.steeringTorque),
                                 _to_float(latest.carState.vEgo), offset)

        features = build_feature_vector(
          feature_state,
          latest.carState,
          latest.liveParameters,
          _to_float(getattr(controls_state, "desiredCurvature", getattr(controls_state, "curvature", 0.0))),
          _measured_lateral_accel(controls_state, latest.carState),
          model_data=latest.modelV2,
          CC=car_control,
          lateral_plan=latest.lateralPlan,
          lateral_delay=_latest_lateral_delay(latest.liveDelay),
        )
        samples.append(Sample(t, features, flag, offset, _to_float(latest.carState.steeringTorque)))

  duration_h = 0.0 if first_t is None or last_t is None else max(0.0, (last_t - first_t) / 3600.0)
  return samples, duration_h, counts


def build_targets(samples: list[Sample], offset_horizon: float, offset_gain: float,
                  driver_torque_scale: float, driver_torque_sign: float,
                  target_clip: float, include_manual: bool):
  times = [sample.t for sample in samples]
  offsets = np.asarray([sample.offset for sample in samples], dtype=np.float32)
  x, y, w, flags, used_offsets = [], [], [], [], []

  for i, sample in enumerate(samples):
    flag = sample.flag
    weight = TRIAGE_WEIGHTS.get(flag, 0.0)
    if weight <= 0.0:
      continue

    target = 0.0
    if flag == TriageType.T2_OFFSET:
      j = min(bisect_left(times, sample.t + offset_horizon), len(samples) - 1)
      target = -offset_gain * float(offsets[j])
    elif flag in (TriageType.T3_STRONG_INTERVENTION, TriageType.T4_WEAK_INTERVENTION):
      target = driver_torque_sign * driver_torque_scale * sample.driver_torque
    elif flag == TriageType.T5_MANUAL:
      if not include_manual:
        continue
      target = driver_torque_sign * driver_torque_scale * sample.driver_torque

    x.append(sample.features)
    y.append(float(np.clip(target, -target_clip, target_clip)))
    w.append(float(weight))
    flags.append(flag.name)
    used_offsets.append(sample.offset)

  return (np.asarray(x, dtype=np.float32),
          np.asarray(y, dtype=np.float32),
          np.asarray(w, dtype=np.float32),
          Counter(flags),
          used_offsets)


def train_val_split(x, y, w, val_ratio: float):
  split = int(x.shape[0] * (1.0 - val_ratio))
  split = min(max(split, 1), x.shape[0] - 1)
  return (x[:split], y[:split], w[:split]), (x[split:], y[split:], w[split:])


def normalize(train_x, val_x):
  mean = np.mean(train_x, axis=0).astype(np.float32)
  std = np.std(train_x, axis=0).astype(np.float32)
  std = np.where(np.abs(std) < 1e-6, 1.0, std).astype(np.float32)
  return (train_x - mean) / std, (val_x - mean) / std, mean, std


def update_history(history_dir: Path, car: str, output: Path, validation: dict):
  history_dir = history_dir.expanduser() / car
  history_dir.mkdir(parents=True, exist_ok=True)
  history_path = history_dir / "history.json"
  history = []
  if history_path.exists():
    with open(history_path, "r", encoding="utf-8") as f:
      history = json.load(f)
  history.append({
    "trained_at": validation["trained_at"],
    "output": str(output),
    "validation": validation,
  })
  with open(history_path, "w", encoding="utf-8") as f:
    json.dump(history, f, indent=2, sort_keys=True)
    f.write("\n")


def default_checkpoint_path(history_dir: Path, car: str, kind: str, trained_at: str) -> Path:
  safe_time = trained_at.replace("+00:00", "Z").replace(":", "").replace("-", "").replace("T", "_")
  safe_car = car.replace(" ", "_").upper()
  return history_dir.expanduser() / safe_car / "checkpoints" / f"{safe_time}_{kind}.json"


def main():
  parser = argparse.ArgumentParser(description="Train/export a CAS JSON model from rlogs.")
  parser.add_argument("--rlogs", nargs="+", required=True, help="rlog files, route URLs, or directories")
  parser.add_argument("--car", required=True, help="car fingerprint/name for the exported model")
  parser.add_argument("--output", help="candidate JSON path; defaults to ~/.cas_train/<car>/checkpoints/")
  parser.add_argument("--kind", choices=("torque", "angle"), default="torque")
  parser.add_argument("--epochs", type=int, default=60)
  parser.add_argument("--batch-size", type=int, default=2048)
  parser.add_argument("--lr", type=float, default=1e-3)
  parser.add_argument("--l2", type=float, default=1e-5)
  parser.add_argument("--backend", choices=("auto", "numpy", "torch"), default="auto")
  parser.add_argument("--device", default="auto", help="torch device: auto, cpu, cuda, cuda:0")
  parser.add_argument("--val-ratio", type=float, default=0.2)
  parser.add_argument("--sample-stride", type=int, default=5, help="use every Nth controlsState frame")
  parser.add_argument("--min-file-age-sec", type=float, default=0.0, help="skip recently modified rlogs")
  parser.add_argument("--max-sources", type=int, help="limit number of expanded rlog sources")
  parser.add_argument("--offset-horizon", type=float, default=0.5)
  parser.add_argument("--offset-gain", type=float, default=0.35)
  parser.add_argument("--driver-torque-scale", type=float, default=0.25)
  parser.add_argument("--driver-torque-sign", type=float, default=1.0)
  parser.add_argument("--target-clip", type=float, default=0.5)
  parser.add_argument("--alpha-max", type=float, default=0.4)
  parser.add_argument("--seed", type=int, default=0)
  parser.add_argument("--include-manual", action="store_true")
  parser.add_argument("--history-dir", default="~/.cas_train")
  args = parser.parse_args()

  sources = expand_sources(args.rlogs, args.min_file_age_sec)
  if args.max_sources is not None:
    sources = sources[:args.max_sources]
  samples, duration_h, message_counts = collect_samples(sources, max(args.sample_stride, 1))
  x, y, weights, triage_counts, offsets = build_targets(
    samples,
    args.offset_horizon,
    args.offset_gain,
    args.driver_torque_scale,
    args.driver_torque_sign,
    args.target_clip,
    args.include_manual,
  )
  if x.shape[0] < 100:
    raise RuntimeError(f"Not enough CAS training samples: {x.shape[0]} usable / {len(samples)} collected")

  (train_x, train_y, train_w), (val_x, val_y, val_w) = train_val_split(x, y, weights, args.val_ratio)
  train_x_norm, val_x_norm, input_mean, input_std = normalize(train_x, val_x)

  model, train_backend = train_model(train_x_norm, train_y, train_w, train_x.shape[1],
                                     args.backend, args.device, args.epochs,
                                     args.batch_size, args.lr, args.l2, args.seed)

  val_pred = model.predict(val_x_norm).reshape(-1)
  trained_at = datetime.now(UTC).replace(microsecond=0).isoformat()
  validation = {
    "trained_at": trained_at,
    "status": "phase1_candidate",
    "source_count": len(sources),
    "message_counts": format_counts(message_counts),
    "triage_counts": format_counts(triage_counts),
    "offset_metrics": lateral_offset_metrics(offsets),
    "target_metrics": prediction_metrics(val_y, val_pred, val_w),
    "train_backend": train_backend,
  }

  payload = build_json_model(
    args.car,
    args.kind,
    model,
    input_mean,
    input_std,
    validation,
    trained_at,
    duration_h,
    args.alpha_max,
  )
  output = Path(args.output).expanduser() if args.output else default_checkpoint_path(Path(args.history_dir), args.car, args.kind, trained_at)
  write_json_model(output, payload)
  update_history(Path(args.history_dir), args.car, output, validation)

  print(f"CAS trained {args.car} ({args.kind})")
  print(f"sources: {len(sources)}, collected: {len(samples)}, usable: {x.shape[0]}, hours: {duration_h:.2f}")
  print(f"triage: {dict(sorted(triage_counts.items()))}")
  print(f"val: {validation['target_metrics']}")
  print(f"backend: {train_backend}")
  print(f"wrote: {output}")


if __name__ == "__main__":
  main()
