#!/usr/bin/env python3
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
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
  from openpilot.selfdrive.carrot.cas.metadata import eps_firmware_hash
  from openpilot.tools.cas.export_json import build_json_model, write_json_model
  from openpilot.tools.cas.triage import TRIAGE_WEIGHTS, TriageType, classify_sample, coerce_triage
  from openpilot.tools.cas.validate import format_counts, lateral_offset_metrics, prediction_metrics
  from openpilot.tools.cas import cache as feature_cache
except ModuleNotFoundError:
  from selfdrive.carrot.cas.features import CASFeatureState, build_feature_vector, lane_center_offset
  from selfdrive.carrot.cas.metadata import eps_firmware_hash
  from tools.cas.export_json import build_json_model, write_json_model
  from tools.cas.triage import TRIAGE_WEIGHTS, TriageType, classify_sample, coerce_triage
  from tools.cas import cache as feature_cache
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


class AuditLogger:
  def __init__(self, audit_dir: Path | None, dump_samples: bool = False):
    self.audit_dir = audit_dir
    self.dump_samples = dump_samples
    if self.audit_dir is not None:
      self.audit_dir.mkdir(parents=True, exist_ok=True)

  def enabled(self) -> bool:
    return self.audit_dir is not None

  def write_json(self, name: str, data):
    if self.audit_dir is None:
      return
    with open(self.audit_dir / name, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
      f.write("\n")

  def write_jsonl(self, name: str, data):
    if self.audit_dir is None:
      return
    with open(self.audit_dir / name, "a", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, sort_keys=True)
      f.write("\n")

  def source_start(self, index: int, total: int, source: str):
    print(f"[collect] {index}/{total} reading {source}", flush=True)
    self.write_jsonl("source_events.jsonl", {
      "event": "source_start",
      "index": index,
      "total": total,
      "source": source,
      "wall_time": datetime.now().isoformat(timespec="seconds"),
    })

  def source_end(self, index: int, total: int, source: str, elapsed_s: float,
                 message_counts: Counter, sample_count: int, triage_counts: Counter,
                 first_t: float | None, last_t: float | None):
    duration_s = 0.0 if first_t is None or last_t is None else max(0.0, last_t - first_t)
    print(f"[collect] {index}/{total} done messages={sum(message_counts.values())} "
          f"samples={sample_count} dt={duration_s:.1f}s elapsed={elapsed_s:.1f}s", flush=True)
    self.write_jsonl("source_events.jsonl", {
      "event": "source_end",
      "index": index,
      "total": total,
      "source": source,
      "elapsed_s": elapsed_s,
      "log_duration_s": duration_s,
      "message_counts": dict(sorted(message_counts.items())),
      "sample_count": sample_count,
      "triage_counts": dict(sorted(triage_counts.items())),
      "wall_time": datetime.now().isoformat(timespec="seconds"),
    })

  def source_error(self, index: int, total: int, source: str, error: Exception):
    print(f"[collect] {index}/{total} error {source}: {error}", flush=True)
    self.write_jsonl("source_events.jsonl", {
      "event": "source_error",
      "index": index,
      "total": total,
      "source": source,
      "error": repr(error),
      "wall_time": datetime.now().isoformat(timespec="seconds"),
    })

  def sample(self, source: str, frame: int, sample: Sample):
    if not self.dump_samples:
      return
    self.write_jsonl("samples.jsonl", {
      "source": source,
      "frame": frame,
      "t": sample.t,
      "flag": sample.flag.name,
      "offset": sample.offset,
      "driver_torque": sample.driver_torque,
      "features": sample.features,
    })


@dataclass
class SourceCollectResult:
  source: str
  samples: list[Sample]
  message_counts: Counter
  triage_counts: Counter
  detected_car_names: Counter
  eps_firmware_hashes: Counter
  steer_control_types: Counter
  first_t: float | None
  last_t: float | None
  elapsed_s: float
  # Sum / count of per-sample lateralDelay (s) so the final model JSON can
  # record the average actuator delay seen during training.
  lateral_delay_sum: float = 0.0
  lateral_delay_count: int = 0


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


def steer_kind_from_car_params(car_params) -> str:
  value = getattr(car_params, "steerControlType", "")
  text = str(value).lower()
  try:
    numeric = int(value)
  except Exception:
    numeric = None
  if text.endswith(".angle") or text == "angle" or numeric == 1:
    return "angle"
  return "torque"


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


def read_rlog_list_files(paths: list[str]) -> list[str]:
  sources = []
  for list_path in paths:
    path = Path(list_path).expanduser()
    with open(path, "r", encoding="utf-8") as f:
      for line in f:
        source = line.strip()
        if source and not source.startswith("#"):
          sources.append(source)
  return sources


def resolve_rlog_inputs(rlogs: list[str], rlog_lists: list[str]) -> list[str]:
  sources = list(rlogs or [])
  sources.extend(read_rlog_list_files(rlog_lists or []))
  if not sources:
    raise RuntimeError("No rlog inputs. Use --rlogs or --rlog-list.")
  return sources


def source_inventory(sources: list[str]) -> list[dict]:
  inventory = []
  for source in sources:
    path = Path(source)
    item = {"source": source}
    try:
      stat = path.stat()
      item.update({
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
      })
    except OSError:
      item["exists"] = False
    inventory.append(item)
  return inventory


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


def _collect_source(source: str, sample_stride: int,
                    cache_dir: Path | None = None) -> SourceCollectResult:
  # Cache hit fast-path: return reconstructed result without touching the rlog.
  if cache_dir is not None:
    cached = feature_cache.load(cache_dir, source, sample_stride)
    if cached is not None:
      m = feature_cache.materialize(cached, Sample, coerce_triage)
      return SourceCollectResult(
        source, m["samples"], m["message_counts"], m["triage_counts"],
        m["detected_car_names"], m["eps_firmware_hashes"],
        m["steer_control_types"],
        m["first_t"], m["last_t"], m["elapsed_s"],
        lateral_delay_sum=m["lateral_delay_sum"],
        lateral_delay_count=m["lateral_delay_count"],
      )

  install_openpilot_aliases()
  try:
    from openpilot.tools.lib.logreader import LogReader
  except ModuleNotFoundError:
    from tools.lib.logreader import LogReader

  samples: list[Sample] = []
  counts = Counter()
  triage = Counter()
  detected_car_names = Counter()
  eps_hashes = Counter()
  steer_control_types = Counter()
  lateral_delay_sum = 0.0
  lateral_delay_count = 0
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
  started = time.monotonic()

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
    elif which == "carParams":
      car_name = str(getattr(msg.carParams, "carFingerprint", "")).strip()
      if car_name:
        detected_car_names[car_name] += 1
      steer_control_types[steer_kind_from_car_params(msg.carParams)] += 1
      eps_hash = eps_firmware_hash(msg.carParams.carFw)
      if eps_hash:
        eps_hashes[eps_hash] += 1
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

      sample_lateral_delay = _latest_lateral_delay(latest.liveDelay)
      features = build_feature_vector(
        feature_state,
        latest.carState,
        latest.liveParameters,
        _to_float(getattr(controls_state, "desiredCurvature", getattr(controls_state, "curvature", 0.0))),
        _measured_lateral_accel(controls_state, latest.carState),
        model_data=latest.modelV2,
        CC=car_control,
        lateral_plan=latest.lateralPlan,
        lateral_delay=sample_lateral_delay,
        t=t,
      )
      sample = Sample(t, features, flag, offset, _to_float(latest.carState.steeringTorque))
      samples.append(sample)
      triage[flag.name] += 1
      lateral_delay_sum += float(sample_lateral_delay)
      lateral_delay_count += 1

  elapsed = time.monotonic() - started
  if cache_dir is not None:
    try:
      feature_cache.save(
        cache_dir, source, sample_stride,
        samples, counts, triage, detected_car_names, eps_hashes, steer_control_types,
        first_t, last_t, elapsed,
        lateral_delay_sum, lateral_delay_count,
      )
    except Exception as e:
      # Cache write failure is non-fatal — training still completes.
      print(f"[cache] save failed for {source}: {e}", flush=True)
  return SourceCollectResult(
    source, samples, counts, triage, detected_car_names, eps_hashes, steer_control_types,
    first_t, last_t, elapsed,
    lateral_delay_sum=lateral_delay_sum,
    lateral_delay_count=lateral_delay_count,
  )


def _merge_source_result(result: SourceCollectResult, samples: list[Sample], counts: Counter,
                         detected_car_names: Counter, eps_hashes: Counter,
                         steer_control_types: Counter,
                         first_t: float | None, last_t: float | None,
                         delay_acc: dict | None = None) -> tuple[float | None, float | None]:
  samples.extend(result.samples)
  counts.update(result.message_counts)
  detected_car_names.update(result.detected_car_names)
  eps_hashes.update(result.eps_firmware_hashes)
  steer_control_types.update(result.steer_control_types)
  if result.first_t is not None:
    first_t = result.first_t if first_t is None else min(first_t, result.first_t)
  if result.last_t is not None:
    last_t = result.last_t if last_t is None else max(last_t, result.last_t)
  if delay_acc is not None:
    delay_acc["sum"] += float(result.lateral_delay_sum)
    delay_acc["count"] += int(result.lateral_delay_count)
  return first_t, last_t


def collect_samples(sources: list[str], sample_stride: int,
                    audit: AuditLogger | None = None,
                    workers: int = 1,
                    cache_dir: Path | None = None) -> tuple[list[Sample], float, Counter, Counter, Counter, Counter, dict]:
  samples: list[Sample] = []
  counts = Counter()
  detected_car_names = Counter()
  eps_hashes = Counter()
  steer_control_types = Counter()
  delay_acc = {"sum": 0.0, "count": 0}
  first_t = None
  last_t = None
  total_sources = len(sources)
  workers = max(1, int(workers))

  if workers > 1 and total_sources > 1:
    print(f"[collect] parallel workers={workers} sources={total_sources}", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as executor:
      futures = {}
      for source_index, source in enumerate(sources, 1):
        if audit is not None:
          audit.source_start(source_index, total_sources, source)
        futures[executor.submit(_collect_source, source, sample_stride, cache_dir)] = (source_index, source)

      for future in as_completed(futures):
        source_index, source = futures[future]
        try:
          result = future.result()
          first_t, last_t = _merge_source_result(result, samples, counts, detected_car_names, eps_hashes,
                                                 steer_control_types,
                                                 first_t, last_t, delay_acc)
          if audit is not None:
            audit.source_end(source_index, total_sources, source, result.elapsed_s,
                             result.message_counts, len(result.samples), result.triage_counts,
                             result.first_t, result.last_t)
            for frame, sample in enumerate(result.samples, 1):
              audit.sample(source, frame, sample)
        except Exception as e:
          if audit is not None:
            audit.source_error(source_index, total_sources, source, e)
          else:
            raise
    samples.sort(key=lambda sample: sample.t)
    duration_h = 0.0 if first_t is None or last_t is None else max(0.0, (last_t - first_t) / 3600.0)
    return samples, duration_h, counts, eps_hashes, detected_car_names, steer_control_types, delay_acc

  for source_index, source in enumerate(sources, 1):
    if audit is not None:
      audit.source_start(source_index, total_sources, source)
    try:
      result = _collect_source(source, sample_stride, cache_dir)
      first_t, last_t = _merge_source_result(result, samples, counts, detected_car_names, eps_hashes,
                                             steer_control_types,
                                             first_t, last_t, delay_acc)
    except Exception as e:
      if audit is not None:
        audit.source_error(source_index, total_sources, source, e)
      else:
        raise
    finally:
      if audit is not None and "result" in locals():
        audit.source_end(source_index, total_sources, source, result.elapsed_s,
                         result.message_counts, len(result.samples), result.triage_counts,
                         result.first_t, result.last_t)
        for frame, sample in enumerate(result.samples, 1):
          audit.sample(source, frame, sample)
        del result

  duration_h = 0.0 if first_t is None or last_t is None else max(0.0, (last_t - first_t) / 3600.0)
  return samples, duration_h, counts, eps_hashes, detected_car_names, steer_control_types, delay_acc


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
  parser.add_argument("--rlogs", nargs="*", default=[], help="rlog files, route URLs, or directories")
  parser.add_argument("--rlog-list", action="append", default=[],
                      help="text file containing one rlog file, route URL, or directory per line")
  parser.add_argument("--car", default="", help="primary car name for the exported model; auto-detected from carParams when omitted")
  parser.add_argument("--car-name", action="append", default=[], help="additional CarName/CarSelected3 alias for runtime matching")
  parser.add_argument("--eps-firmware-hash", default="", help="override auto-detected EPS firmware hash")
  parser.add_argument("--output", help="candidate JSON path; defaults to ~/.cas_train/<car>/checkpoints/")
  parser.add_argument("--kind", choices=("auto", "torque", "angle"), default="torque")
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
  parser.add_argument("--workers", type=int, default=1, help="parallel rlog parser workers")
  parser.add_argument("--cache-dir", default="~/.cas_train/feature_cache",
                      help="directory for per-rlog feature cache; empty string disables cache")
  parser.add_argument("--no-cache", action="store_true",
                      help="disable feature cache (always re-parse rlogs)")
  parser.add_argument("--offset-horizon", type=float, default=0.5)
  parser.add_argument("--offset-gain", type=float, default=0.35)
  parser.add_argument("--driver-torque-scale", type=float, default=0.25)
  parser.add_argument("--driver-torque-sign", type=float, default=1.0)
  parser.add_argument("--target-clip", type=float, default=0.5)
  parser.add_argument("--alpha-max", type=float, default=0.5)
  parser.add_argument("--seed", type=int, default=0)
  parser.add_argument("--include-manual", action="store_true")
  parser.add_argument("--history-dir", default="~/.cas_train")
  parser.add_argument("--audit-dir", help="write detailed raw/audit logs to this directory")
  parser.add_argument("--audit-samples", action="store_true", help="write collected sample records to samples.jsonl")
  args = parser.parse_args()

  audit = AuditLogger(Path(args.audit_dir).expanduser() if args.audit_dir else None, args.audit_samples)
  source_inputs = resolve_rlog_inputs(args.rlogs, args.rlog_list)
  sources = expand_sources(source_inputs, args.min_file_age_sec)
  if args.max_sources is not None:
    sources = sources[:args.max_sources]
  audit.write_json("source_inventory.json", source_inventory(sources))
  audit.write_json("train_args.json", vars(args))

  cache_dir = None
  if not args.no_cache and args.cache_dir:
    cache_dir = Path(args.cache_dir).expanduser()
    print(f"[cache] feature cache enabled at {cache_dir}", flush=True)
  else:
    print("[cache] feature cache disabled", flush=True)

  samples, duration_h, message_counts, eps_hashes, detected_car_names, steer_control_types, delay_acc = collect_samples(
    sources, max(args.sample_stride, 1), audit, args.workers, cache_dir=cache_dir)
  lateral_delay_at_train = (delay_acc["sum"] / delay_acc["count"]) if delay_acc["count"] > 0 else 0.0
  model_car = args.car.strip()
  if not model_car and detected_car_names:
    model_car = detected_car_names.most_common(1)[0][0]
  if not model_car:
    raise RuntimeError("Could not auto-detect car name from rlogs. Use --car in advanced/manual mode.")
  detected_kind = steer_control_types.most_common(1)[0][0] if steer_control_types else ""
  model_kind = detected_kind if args.kind == "auto" and detected_kind else args.kind
  if model_kind == "auto":
    model_kind = "torque"
  if detected_kind and model_kind != detected_kind:
    raise RuntimeError(f"CAS kind mismatch: --kind {model_kind} but rlogs look like {detected_kind}")

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
    "car": model_car,
    "source_count": len(sources),
    "message_counts": format_counts(message_counts),
    "detected_car_name_counts": format_counts(detected_car_names),
    "eps_firmware_hash_counts": format_counts(eps_hashes),
    "steer_control_type_counts": format_counts(steer_control_types),
    "kind": model_kind,
    "triage_counts": format_counts(triage_counts),
    "offset_metrics": lateral_offset_metrics(offsets),
    "target_metrics": prediction_metrics(val_y, val_pred, val_w),
    "train_backend": train_backend,
  }
  audit.write_json("train_validation.json", validation)

  # Auto-derive deployment metadata from the training distribution.
  vego_col = x[:, 0]
  vego_min_train = float(np.percentile(vego_col, 5)) if vego_col.size else 5.0
  vego_max_train = float(np.percentile(vego_col, 95)) if vego_col.size else 35.0
  if y.size:
    y_p99 = float(np.percentile(np.abs(y), 99))
  else:
    y_p99 = float(args.target_clip)
  output_clip_val = min(float(args.target_clip), max(0.05, y_p99 * 1.5))

  # friction_override auto-detect (§23.2): probe the trained model with a small
  # error-only input (no lat_accel signal). If the model barely reacts, the
  # downstream runtime should add classical friction back on top.
  # We use the (already normalized) value of the lateralJerkLookahead feature
  # (index 10) plus all zeros as a synthetic "tiny friction" probe and look
  # at the absolute response in normalized output units.
  try:
    probe = np.zeros(input_mean.shape[0], dtype=np.float32)
    if probe.size > 10:
      # 0.2 m/s^3 jerk in raw units; normalize using the same mean/std.
      probe[10] = (0.2 - float(input_mean[10])) / max(float(input_std[10]), 1e-3)
    probe_out = model.predict(probe.reshape(1, -1))[0, 0]
    friction_override = bool(abs(float(probe_out)) < 0.1)
  except Exception:
    friction_override = False
  validation["friction_override_probe"] = float(probe_out) if "probe_out" in locals() else None
  detected_eps_hash = args.eps_firmware_hash.strip()
  if not detected_eps_hash and eps_hashes:
    detected_eps_hash = eps_hashes.most_common(1)[0][0]
  car_names = []
  for name in [model_car, *args.car_name]:
    name = name.strip()
    if name and name not in car_names:
      car_names.append(name)

  payload = build_json_model(
    model_car,
    model_kind,
    model,
    input_mean,
    input_std,
    validation,
    trained_at,
    duration_h,
    args.alpha_max,
    output_clip=(-output_clip_val, output_clip_val),
    vego_min=vego_min_train,
    vego_max=vego_max_train,
    trained_rlog_count=len(sources),
    eps_firmware_hash=detected_eps_hash,
    car_names=car_names,
    lateral_delay_at_train=lateral_delay_at_train,
    friction_override=friction_override,
  )
  output = Path(args.output).expanduser() if args.output else default_checkpoint_path(Path(args.history_dir), model_car, model_kind, trained_at)
  write_json_model(output, payload)
  update_history(Path(args.history_dir), model_car, output, validation)

  print(f"CAS trained {model_car} ({model_kind})")
  print(f"detected_car_names: {dict(sorted(detected_car_names.items()))}")
  print(f"steer_control_types: {dict(sorted(steer_control_types.items()))}")
  print(f"sources: {len(sources)}, collected: {len(samples)}, usable: {x.shape[0]}, hours: {duration_h:.2f}")
  print(f"triage: {dict(sorted(triage_counts.items()))}")
  print(f"val: {validation['target_metrics']}")
  print(f"backend: {train_backend}")
  print(f"eps_firmware_hash: {detected_eps_hash or '<none>'}")
  print(f"wrote: {output}")
  if audit.enabled():
    print(f"audit: {audit.audit_dir}")


if __name__ == "__main__":
  main()
