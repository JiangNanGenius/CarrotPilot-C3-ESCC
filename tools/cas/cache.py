"""
Feature cache for CAS training.

Caches the per-rlog output of `_collect_source` so repeated training runs
(different alpha/epochs/etc.) skip the expensive rlog parse + feature build
step. Cache invalidates automatically when:
  - the rlog file changes (size/mtime),
  - the sample_stride changes,
  - the features.py / triage.py code changes,
  - the cache schema version bumps.

Layout:
  <cache_dir>/<sha1[:16]>.npz   <- numpy arrays (features, triages, ...)
  <cache_dir>/<sha1[:16]>.json  <- metadata sidecar (key, counts, source path, ...)
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np


# Bump when the on-disk array layout changes in a non-backward-compatible way.
CACHE_SCHEMA_VERSION = 1


def _file_hash(path: Path) -> str:
  try:
    return hashlib.sha1(path.read_bytes()).hexdigest()
  except Exception:
    return "missing"


def _code_fingerprint() -> str:
  """Hash the feature/triage source files so code changes invalidate cache."""
  here = Path(__file__).resolve().parent.parent.parent  # repo root-ish
  candidates = [
    here / "selfdrive" / "carrot" / "cas" / "features.py",
    here / "tools" / "cas" / "triage.py",
  ]
  h = hashlib.sha1()
  for p in candidates:
    h.update(str(p).encode("utf-8"))
    h.update(b"\0")
    h.update(_file_hash(p).encode("utf-8"))
  return h.hexdigest()[:16]


def _rlog_signature(source: str) -> tuple[int, int]:
  """(size, mtime_ns). Changes if the rlog is rewritten."""
  try:
    st = os.stat(source)
    return int(st.st_size), int(st.st_mtime_ns)
  except OSError:
    return -1, -1


def cache_key(source: str, sample_stride: int) -> str:
  size, mtime = _rlog_signature(source)
  payload = json.dumps({
    "schema": CACHE_SCHEMA_VERSION,
    "source": source,
    "size": size,
    "mtime": mtime,
    "stride": sample_stride,
    "code": _code_fingerprint(),
  }, sort_keys=True).encode("utf-8")
  return hashlib.sha1(payload).hexdigest()[:16]


def _paths(cache_dir: Path, key: str) -> tuple[Path, Path]:
  return cache_dir / f"{key}.npz", cache_dir / f"{key}.json"


def load(cache_dir: Path, source: str, sample_stride: int):
  """Return SourceCollectResult-like dict on hit, None on miss."""
  if not cache_dir or not cache_dir.exists():
    return None
  key = cache_key(source, sample_stride)
  npz_path, meta_path = _paths(cache_dir, key)
  if not npz_path.exists() or not meta_path.exists():
    return None
  try:
    arrays = np.load(npz_path, allow_pickle=False)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
  except Exception:
    return None
  if meta.get("schema") != CACHE_SCHEMA_VERSION:
    return None
  if meta.get("source") != source:
    return None
  # Defense: signature inside meta must match current rlog stat.
  size, mtime = _rlog_signature(source)
  if meta.get("size") != size or meta.get("mtime") != mtime:
    return None
  return {
    "samples": {
      "t":              arrays["t"],
      "features":       arrays["features"],
      "triage":         arrays["triage"],
      "offset":         arrays["offset"],
      "driver_torque":  arrays["driver_torque"],
    },
    "meta": meta,
  }


def save(cache_dir: Path, source: str, sample_stride: int,
         samples: list, message_counts: Counter, triage_counts: Counter,
         detected_car_names: Counter, eps_firmware_hashes: Counter,
         first_t: float | None, last_t: float | None, elapsed_s: float,
         lateral_delay_sum: float, lateral_delay_count: int):
  if not cache_dir:
    return
  cache_dir.mkdir(parents=True, exist_ok=True)
  key = cache_key(source, sample_stride)
  npz_path, meta_path = _paths(cache_dir, key)

  if samples:
    t = np.asarray([s.t for s in samples], dtype=np.float64)
    features = np.asarray([s.features for s in samples], dtype=np.float32)
    # triage flag may be Enum-like; store its integer value, plus name in meta.
    triage = np.asarray([int(getattr(s.flag, "value", s.flag)) for s in samples], dtype=np.int16)
    offset = np.asarray([s.offset for s in samples], dtype=np.float32)
    driver_torque = np.asarray([s.driver_torque for s in samples], dtype=np.float32)
  else:
    t = np.zeros(0, dtype=np.float64)
    features = np.zeros((0, 0), dtype=np.float32)
    triage = np.zeros(0, dtype=np.int16)
    offset = np.zeros(0, dtype=np.float32)
    driver_torque = np.zeros(0, dtype=np.float32)

  size, mtime = _rlog_signature(source)
  meta = {
    "schema": CACHE_SCHEMA_VERSION,
    "source": source,
    "size": size,
    "mtime": mtime,
    "stride": sample_stride,
    "code": _code_fingerprint(),
    "message_counts": dict(message_counts),
    "triage_counts": dict(triage_counts),
    "detected_car_names": dict(detected_car_names),
    "eps_firmware_hashes": dict(eps_firmware_hashes),
    "first_t": first_t,
    "last_t": last_t,
    "elapsed_s": elapsed_s,
    "lateral_delay_sum": lateral_delay_sum,
    "lateral_delay_count": lateral_delay_count,
    "n_samples": int(triage.size),
  }

  # Write atomically: tmp then rename, so a crash mid-write can't corrupt cache.
  npz_tmp = npz_path.with_suffix(".npz.tmp")
  meta_tmp = meta_path.with_suffix(".json.tmp")
  np.savez_compressed(npz_tmp, t=t, features=features, triage=triage,
                      offset=offset, driver_torque=driver_torque)
  meta_tmp.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
  os.replace(npz_tmp, npz_path)
  os.replace(meta_tmp, meta_path)


def materialize(cached, Sample, coerce_triage):
  """Turn a cached dict back into a list[Sample] + counters tuple."""
  arrays = cached["samples"]
  meta = cached["meta"]
  n = int(arrays["triage"].size)
  samples = []
  for i in range(n):
    samples.append(Sample(
      float(arrays["t"][i]),
      arrays["features"][i].tolist() if arrays["features"].ndim == 2 else [],
      coerce_triage(int(arrays["triage"][i])),
      float(arrays["offset"][i]),
      float(arrays["driver_torque"][i]),
    ))
  return {
    "samples": samples,
    "message_counts": Counter(meta.get("message_counts", {})),
    "triage_counts": Counter(meta.get("triage_counts", {})),
    "detected_car_names": Counter(meta.get("detected_car_names", {})),
    "eps_firmware_hashes": Counter(meta.get("eps_firmware_hashes", {})),
    "first_t": meta.get("first_t"),
    "last_t": meta.get("last_t"),
    "elapsed_s": float(meta.get("elapsed_s", 0.0)),
    "lateral_delay_sum": float(meta.get("lateral_delay_sum", 0.0)),
    "lateral_delay_count": int(meta.get("lateral_delay_count", 0)),
  }
