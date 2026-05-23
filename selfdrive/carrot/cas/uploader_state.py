"""
Persistent state for the CAS uploader.

Tracks which route segments have been uploaded successfully, plus retry
attempts. Lives under /data/cas_upload_state.json so it survives reboots.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path


STATE_PATH = Path("/data/cas_upload_state.json")
_LOCK = threading.Lock()

# Permanent errors (bad signature, file too large, 4xx) won't fix themselves —
# cap retries so they don't spin forever.
MAX_ATTEMPTS = 5

# Transient errors (server busy/down, network blip) WILL fix themselves once the
# server is healthy again. We must never permanently give up on these, otherwise
# a busy day would silently abandon segments forever. Instead back off so we
# don't hammer a struggling server; once it recovers the next scan uploads the
# file right away. Index by attempt count; the last value repeats (cap at 1h).
TRANSIENT_BACKOFF_SEC = [60, 300, 900, 1800, 3600]   # 1m, 5m, 15m, 30m, 1h, 1h…
# HTTP codes that mean "try later": 408 timeout, 429 rate-limited, 5xx server.
# (uvicorn returns 503 when --limit-concurrency is exceeded.)
_TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}


def is_transient_error(error: str) -> bool:
  """Transient = worth retrying indefinitely (server busy/down, network blip).
  Permanent = retrying won't help (bad signature, 'too large', other 4xx)."""
  e = (error or "").lower()
  m = re.search(r"http\s+(\d+)", e)
  if m:
    return int(m.group(1)) in _TRANSIENT_HTTP
  if "network" in e or "timeout" in e or "connection" in e or "temporarily" in e:
    return True
  return False   # "too large", "error: ...", unknown → permanent (capped)


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
    entry = state.setdefault("failed", {}).setdefault(
      k, {"attempts": 0, "last_error": "", "last_at": 0, "transient": True})
    entry["attempts"] = int(entry.get("attempts", 0)) + 1
    entry["last_error"] = str(error)[:200]
    entry["last_at"] = int(time.time())
    entry["transient"] = is_transient_error(error)
    return entry["attempts"]


def should_retry(state: dict, route_id: str, segment: str, filename: str) -> bool:
  k = _key(route_id, segment, filename)
  entry = state.get("failed", {}).get(k)
  if entry is None:
    return True
  attempts = int(entry.get("attempts", 0))
  # Permanent failure: give up after a few tries — retrying won't help.
  if not bool(entry.get("transient", True)):
    return attempts < MAX_ATTEMPTS
  # Transient failure: never give up. Wait out a growing backoff so a busy/down
  # server gets breathing room; once it's healthy the next scan picks the file
  # right up (so "today it failed, tomorrow it uploads" holds true).
  idx = min(max(attempts - 1, 0), len(TRANSIENT_BACKOFF_SEC) - 1)
  return (time.time() - int(entry.get("last_at", 0))) >= TRANSIENT_BACKOFF_SEC[idx]
