"""
CAS data uploader daemon.

When CarrotDataUpload is enabled, scans /data/media/0/realdata/ for completed
route segments and uploads rlog.zst / qlog.zst plus a per-route route_meta.json
to the CAS upload server via HTTPS with HMAC headers.

Design:
  - One file per HTTP POST. No batching (keeps memory low, easy retries).
  - State persisted in /data/cas_upload_state.json so reboots don't repeat work.
  - Conditions: WiFi-only / battery / offroad-only guarded by params.
  - Idle when toggle is off — process stays alive but sleeps.

Runs as a managed process from selfdrive/manager/process_config.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from openpilot.common.params import Params

try:
  from openpilot.selfdrive.carrot.cas import upload_config, uploader_state
except ModuleNotFoundError:
  from selfdrive.carrot.cas import upload_config, uploader_state


REALDATA = Path("/data/media/0/realdata")
ROUTE_SEG_RE = re.compile(r"^(?P<route>\d{4}-\d{2}-\d{2}--\d{2}-\d{2}-\d{2})--(?P<seg>\d+)$")

UPLOAD_FILES = ("rlog.zst", "qlog.zst")
META_FILENAME = "route_meta.json"

POLL_OFF_SEC = 30          # sleep when toggle is OFF
POLL_IDLE_SEC = 60         # sleep between scans when nothing to upload
POLL_BUSY_SEC = 2          # short pause between segments while uploading

REQUEST_TIMEOUT_SEC = 60   # HTTP timeout per file
MAX_FILE_BYTES = 50 * 1024 * 1024


def _log(msg: str) -> None:
  print(f"[cas_upload] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Device identity

def get_device_id(params: Params) -> str:
  try:
    cur = (params.get("CarrotDeviceId") or b"").decode("utf-8").strip()
  except Exception:
    cur = ""
  if cur:
    return cur
  new_id = uuid.uuid4().hex[:16]
  params.put("CarrotDeviceId", new_id)
  _log(f"generated CarrotDeviceId={new_id}")
  return new_id


# ---------------------------------------------------------------------------
# Conditions

def _on_wifi() -> bool:
  # Best-effort: check if wlan0 has a non-empty inet that isn't link-local.
  try:
    with open("/proc/net/route", "r") as f:
      for line in f.readlines()[1:]:
        cols = line.split()
        if cols and cols[0].startswith("wlan"):
          return True
  except OSError:
    pass
  return False


def _battery_pct() -> int:
  for path in ("/sys/class/power_supply/battery/capacity",
               "/sys/class/power_supply/BAT0/capacity"):
    try:
      return int(Path(path).read_text().strip())
    except (OSError, ValueError):
      continue
  return 100   # if we can't read, assume fine


def _is_offroad(params: Params) -> bool:
  try:
    return not bool(params.get_bool("IsOnroad"))
  except Exception:
    return True


def upload_allowed(params: Params) -> tuple[bool, str]:
  if not params.get_bool("CarrotDataUpload"):
    return False, "toggle off"
  if params.get_bool("CarrotUploadWifiOnly") and not _on_wifi():
    return False, "not on wifi"
  min_batt = params.get_int("CarrotUploadMinBattery") or 0
  if _battery_pct() < min_batt:
    return False, f"battery<{min_batt}"
  if params.get_bool("CarrotUploadOnlyOffroad") and not _is_offroad(params):
    return False, "onroad"
  return True, ""


# ---------------------------------------------------------------------------
# Filesystem scanning

def list_segments() -> list[tuple[str, str, Path]]:
  """Returns list of (route_id, segment, path) sorted oldest-first."""
  out = []
  if not REALDATA.exists():
    return out
  for entry in REALDATA.iterdir():
    m = ROUTE_SEG_RE.match(entry.name)
    if not m:
      continue
    out.append((m.group("route"), m.group("seg"), entry))
  # Sort by route then segment numerically.
  out.sort(key=lambda x: (x[0], int(x[1])))
  return out


def is_segment_complete(seg_dir: Path) -> bool:
  """Heuristic: rlog.zst exists and hasn't been touched in 60s."""
  rlog = seg_dir / "rlog.zst"
  if not rlog.exists():
    return False
  try:
    mtime = rlog.stat().st_mtime
  except OSError:
    return False
  return (time.time() - mtime) > 60


# ---------------------------------------------------------------------------
# HTTP upload

def _sign(device_id: str, ts: int, secret: bytes) -> str:
  msg = f"{device_id}|{ts}".encode("utf-8")
  return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _build_url(endpoint: str, device_id: str, route_id: str, segment: str, filename: str) -> str:
  return f"{endpoint.rstrip('/')}/upload/{device_id}/{route_id}/{segment}/{filename}"


def upload_file(endpoint: str, secret: bytes, device_id: str, route_id: str,
                segment: str, filename: str, file_path: Path,
                car: str, eps_hash: str, cas_model: str, carrot_version: str) -> tuple[bool, str, int]:
  size = file_path.stat().st_size
  if size > MAX_FILE_BYTES:
    return False, f"too large ({size} bytes)", 0

  ts = int(time.time())
  sig = _sign(device_id, ts, secret)
  url = _build_url(endpoint, device_id, route_id, segment, filename)

  with file_path.open("rb") as f:
    body = f.read()

  req = urllib.request.Request(url, data=body, method="POST")
  req.add_header("X-Carrot-TS", str(ts))
  req.add_header("X-Carrot-Sig", sig)
  req.add_header("X-Carrot-Version", carrot_version)
  if car:        req.add_header("X-Carrot-Car", car)
  if eps_hash:   req.add_header("X-Carrot-EpsHash", eps_hash)
  if cas_model:  req.add_header("X-Carrot-CasModel", cas_model)
  req.add_header("Content-Type", "application/octet-stream")

  try:
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
      body = resp.read(4096)
      return True, body.decode("utf-8", "ignore"), size
  except urllib.error.HTTPError as e:
    return False, f"HTTP {e.code}", size
  except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
    return False, f"network: {e}", size
  except Exception as e:
    return False, f"error: {e}", size


# ---------------------------------------------------------------------------
# Per-route metadata

def build_route_meta(params: Params, route_id: str, segments: list[Path],
                     device_id: str) -> dict:
  car_name = ""
  try:
    car_name = (params.get("CarName") or b"").decode("utf-8", "ignore").strip()
  except Exception:
    pass
  carrot_version = ""
  try:
    carrot_version = (params.get("GitCommit") or b"")[:12].decode("utf-8", "ignore").strip()
  except Exception:
    pass
  cas_model = ""
  try:
    cas_model = (params.get("CASModelName") or b"").decode("utf-8", "ignore").strip()
  except Exception:
    pass

  return {
    "device_id": device_id,
    "route_id": route_id,
    "car": car_name,
    "carrot_version": carrot_version,
    "cas_model_used": cas_model,
    "segments": len(segments),
    "uploaded_at": int(time.time()),
  }


def _eps_hash_from_params(params: Params) -> str:
  # Best-effort: not all carrot builds expose this on params.
  try:
    return (params.get("CASEpsHash") or b"").decode("utf-8", "ignore").strip()
  except Exception:
    return ""


# ---------------------------------------------------------------------------
# Main loop

def run() -> None:
  params = Params()
  state = uploader_state.load()
  secret = upload_config.resolve_secret()
  device_id = get_device_id(params)
  state["device_id"] = device_id
  uploader_state.save(state)

  _log(f"device_id={device_id} endpoint={upload_config.resolve_endpoint(params)}")

  while True:
    ok, reason = upload_allowed(params)
    if not ok:
      time.sleep(POLL_OFF_SEC)
      continue

    endpoint = upload_config.resolve_endpoint(params)
    carrot_version = ""
    try:
      carrot_version = (params.get("GitCommit") or b"")[:12].decode("utf-8", "ignore").strip()
    except Exception:
      pass
    car_name = ""
    try:
      car_name = (params.get("CarName") or b"").decode("utf-8", "ignore").strip()
    except Exception:
      pass
    eps_hash = _eps_hash_from_params(params)
    cas_model = ""
    try:
      cas_model = (params.get("CASModelName") or b"").decode("utf-8", "ignore").strip()
    except Exception:
      pass

    segments = list_segments()
    # Group by route to know which routes have meta to send.
    routes: dict[str, list[tuple[str, Path]]] = {}
    for route_id, seg, path in segments:
      routes.setdefault(route_id, []).append((seg, path))

    uploaded_anything = False
    for route_id, segs in routes.items():
      # Re-check toggle between segments — user can flip mid-loop.
      ok, _ = upload_allowed(params)
      if not ok:
        break

      for seg, seg_dir in segs:
        if not is_segment_complete(seg_dir):
          continue
        for fname in UPLOAD_FILES:
          fpath = seg_dir / fname
          if not fpath.exists():
            continue
          if uploader_state.is_uploaded(state, route_id, seg, fname):
            continue
          if not uploader_state.should_retry(state, route_id, seg, fname):
            continue
          ok, msg, size = upload_file(endpoint, secret, device_id, route_id, seg, fname,
                                      fpath, car_name, eps_hash, cas_model, carrot_version)
          if ok:
            uploader_state.mark_uploaded(state, route_id, seg, fname, size)
            uploaded_anything = True
            _log(f"OK {route_id}/{seg}/{fname} ({size} bytes)")
          else:
            attempts = uploader_state.record_failure(state, route_id, seg, fname, msg)
            _log(f"FAIL {route_id}/{seg}/{fname}: {msg} (attempt {attempts})")
          uploader_state.save(state)
          # Short pause so we don't peg the network or our own loop.
          time.sleep(POLL_BUSY_SEC)

      # After segments uploaded, send route_meta for this route once.
      meta_key = (route_id, "meta", META_FILENAME)
      if any(uploader_state.is_uploaded(state, route_id, seg, fname)
             for seg, _ in segs
             for fname in UPLOAD_FILES):
        if not uploader_state.is_uploaded(state, *meta_key):
          meta = build_route_meta(params, route_id, [p for _, p in segs], device_id)
          # Write meta to a temp file so we can re-use upload_file.
          tmp = Path("/data") / f".cas_meta_{route_id}.json"
          try:
            tmp.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
            ok, msg, size = upload_file(endpoint, secret, device_id, route_id, "meta",
                                        META_FILENAME, tmp, car_name, eps_hash, cas_model, carrot_version)
            if ok:
              uploader_state.mark_uploaded(state, route_id, "meta", META_FILENAME, size)
              _log(f"META {route_id} uploaded")
            else:
              uploader_state.record_failure(state, route_id, "meta", META_FILENAME, msg)
            uploader_state.save(state)
          finally:
            try:
              tmp.unlink()
            except OSError:
              pass

    time.sleep(POLL_BUSY_SEC if uploaded_anything else POLL_IDLE_SEC)


def main():
  try:
    run()
  except KeyboardInterrupt:
    return


if __name__ == "__main__":
  main()
