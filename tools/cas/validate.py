import numpy as np


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

