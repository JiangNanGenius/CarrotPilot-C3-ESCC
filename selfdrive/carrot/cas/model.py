import json
from pathlib import Path

import numpy as np


class CASModel:
  activation_function_names = {"σ": "sigmoid"}

  def __init__(self, params_file: str | Path):
    self.params_file = Path(params_file)
    with open(self.params_file, "r", encoding="utf-8") as f:
      params = json.load(f)

    self.meta = params
    self.model_type = params.get("model_type", "")
    self.car = params.get("car", "")
    self.car_fingerprints = list(params.get("car_fingerprints", [self.car])) if self.car else list(params.get("car_fingerprints", []))
    self.eps_firmware_hash = params.get("eps_firmware_hash", "")
    self.alpha_max = float(params.get("alpha_max", 0.0))
    self.input_size = int(params["input_size"])
    self.output_size = int(params.get("output_size", 1))
    self.input_mean = np.asarray(params["input_mean"], dtype=np.float32)
    self.input_std = np.asarray(params["input_std"], dtype=np.float32)
    self.input_std = np.where(np.abs(self.input_std) < 1e-6, 1.0, self.input_std)
    self.feature_spec = list(params.get("feature_spec", []))
    output_clip = params.get("output_clip", [-3.0, 3.0])
    self.output_clip_low = float(output_clip[0])
    self.output_clip_high = float(output_clip[1])
    self.vego_min = float(params.get("vego_min", 5.0))
    self.vego_max = float(params.get("vego_max", 35.0))
    self.use_steering_angle = bool(params.get("use_steering_angle", True))
    self.layers = []

    prev_size = self.input_size
    for layer_params in params["layers"]:
      layer_type = layer_params.get("type", "linear")
      if layer_type != "linear":
        raise ValueError(f"Unsupported CAS layer type: {layer_type}")

      w_key = next(key for key in layer_params if key.endswith("_W") or key.startswith("W_"))
      b_key = next(key for key in layer_params if key.endswith("_b") or key.startswith("b_"))
      raw_W = np.asarray(layer_params[w_key], dtype=np.float32)
      if raw_W.ndim != 2:
        raise ValueError("CAS layer weight must be 2D")
      if raw_W.shape[0] == prev_size:
        W = raw_W
      elif raw_W.shape[1] == prev_size:
        W = raw_W.T
      else:
        raise ValueError(f"CAS layer shape {raw_W.shape} does not match input {prev_size}")
      b = np.asarray(layer_params[b_key], dtype=np.float32)
      activation = layer_params.get("activation", "identity")
      for src, dst in self.activation_function_names.items():
        activation = activation.replace(src, dst)
      self.layers.append((W, b, activation))
      prev_size = W.shape[1]

    self.validate_layers()

  @staticmethod
  def identity(x):
    return x

  @staticmethod
  def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

  @staticmethod
  def tanh(x):
    return np.tanh(x)

  @staticmethod
  def relu(x):
    return np.maximum(x, 0.0)

  def validate_layers(self):
    if self.input_mean.shape[0] != self.input_size or self.input_std.shape[0] != self.input_size:
      raise ValueError("CAS input_mean/input_std size mismatch")
    for _, _, activation in self.layers:
      if not hasattr(self, activation):
        raise ValueError(f"Unknown CAS activation: {activation}")

  def normalize(self, input_array):
    x = np.asarray(input_array, dtype=np.float32)
    if x.shape[0] != self.input_size:
      raise ValueError(f"CAS input length {x.shape[0]} != {self.input_size}")
    return (x - self.input_mean) / self.input_std

  def forward(self, x):
    for W, b, activation in self.layers:
      x = getattr(self, activation)(x.dot(W) + b)
    return x

  def evaluate(self, input_array) -> tuple[float, float]:
    x = self.normalize(input_array)
    max_abs_z = float(np.max(np.abs(x))) if x.size else 0.0
    y = self.forward(x.reshape(1, -1))
    raw = float(y[0, 0])
    clipped = max(self.output_clip_low, min(self.output_clip_high, raw))
    return clipped, max_abs_z
