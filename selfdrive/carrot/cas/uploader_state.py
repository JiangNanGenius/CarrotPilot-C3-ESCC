"""
Persistent state for the CAS uploader.

Tracks which route segments have been uploaded successfully, plus retry
attempts. Lives under /data/cas_upload_state.json so it survives reboots.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path


STATE_PATH = Path("/data/cas_upload_state.json")
_LOCK = threading.Lock()

# Cap retries so a permanently bad file doesn't spin forever.
MAX_ATTEMPTS = 5


def _empty_state() -> dict:
  return {
    "version": 1,
    "uploaded": {},      # key "route/segment/filename" -> {at, bytes}
    "failed": {},        # key -> {attempts, last_error, last_at}
    "device_id": "",     # cached CarrotDeviceId
  }


def load() -> dict:
  if not STATE_PATH.exists():
    return _empty_state()
  try:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))
  except Exception:
    return _empty_state()


def save(state: dict) -> None:
  STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
  fd, tmp = tempfile.mkstemp(dir=str(STATE_PATH.parent), prefix=".cas_upload_state.", suffix=".tmp")
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
      json.dump(state, f, sort_keys=True)
    os.replace(tmp, STATE_PATH)
  except Exception:
    try:
      os.unlink(tmp)
    except OSError:
      pass
    raise


def _key(route_id: str, segment: str, filename: str) -> str:
  return f"{route_id}/{segment}/{filename}"


def is_uploaded(state: dict, route_id: str, segment: str, filename: str) -> bool:
  return _key(route_id, segment, filename) in state.get("uploaded", {})


def mark_uploaded(state: dict, route_id: str, segment: str, filename: str, byte_count: int) -> None:
  with _LOCK:
    state.setdefault("uploaded", {})[_key(route_id, segment, filename)] = {
      "at": int(time.time()),
      "bytes": int(byte_count),
    }
    # Clear any failure record.
    state.get("failed", {}).pop(_key(route_id, segment, filename), None)


def record_failure(state: dict, route_id: str, segment: str, filename: str, error: str) -> int:
  """Returns updated attempt count."""
  with _LOCK:
    k = _key(route_id, segment, filename)
    entry = state.setdefault("failed", {}).setdefault(k, {"attempts": 0, "last_error": "", "last_at": 0})
    entry["attempts"] = int(entry.get("attempts", 0)) + 1
    entry["last_error"] = str(error)[:200]
    entry["last_at"] = int(time.time())
    return entry["attempts"]


def should_retry(state: dict, route_id: str, segment: str, filename: str) -> bool:
  k = _key(route_id, segment, filename)
  entry = state.get("failed", {}).get(k)
  if entry is None:
    return True
  return int(entry.get("attempts", 0)) < MAX_ATTEMPTS
