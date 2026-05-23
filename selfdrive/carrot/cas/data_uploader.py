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

try:
  from openpilot.common.params import Params
except ModuleNotFoundError:
  from common.params import Params

try:
  from openpilot.common.swaglog import cloudlog
except ModuleNotFoundError:
  cloudlog = None

try:
  from openpilot.selfdrive.carrot.cas import upload_config, uploader_state
except ModuleNotFoundError:
  from selfdrive.carrot.cas import upload_config, uploader_state


REALDATA = Path("/data/media/0/realdata")
# Comma's segment folder naming has two forms in the wild:
#   - registered devices: "2026-05-21--14-30-00--0"  (date-time + segment)
#   - unregistered:       "00000000--4c043f717d--6"  (bootcount + hash + segment)
# Match anything ending with --<digits>$.
ROUTE_SEG_RE = re.compile(r"^(?P<route>.+)--(?P<seg>\d+)$")

UPLOAD_FILES = ("rlog.zst", "qlog.zst")
META_FILENAME = "route_meta.json"

POLL_OFF_SEC = 30          # sleep when toggle is OFF
POLL_IDLE_SEC = 60         # sleep between scans when nothing to upload
POLL_BUSY_SEC = 2          # short pause between segments while uploading

REQUEST_TIMEOUT_SEC = 60   # HTTP timeout per file
MAX_FILE_BYTES = 50 * 1024 * 1024

# systemd-timesyncd writes this once NTP sync completes. comma3X RTC has no
# battery, so the clock boots at 1970 and only becomes correct after a network
# connection lets NTP (or carrot/browser) set it. We must not upload before
# then — the request timestamp would be wrong and the server rejects it.
NTP_SYNCED_FLAG = Path("/run/systemd/timesync/synchronized")
MIN_VALID_EPOCH = 1704067200   # 2024-01-01; below this the clock isn't set yet


def _log(msg: str) -> None:
  # Use cloudlog so the message lands in swaglog and is traceable after a
  # drive. Falls back to print when cloudlog isn't importable (PC tooling).
  if cloudlog is not None:
    cloudlog.info(f"[cas_upload] {msg}")
  else:
    print(f"[cas_upload] {msg}", flush=True)


def _clock_synced() -> bool:
  """True once the system clock is trustworthy (network time has been set)."""
  try:
    if NTP_SYNCED_FLAG.exists():
      return True
  except OSError:
    pass
  # Covers non-systemd sync paths (carrotMan epochTime, browser time_sync).
  return time.time() > MIN_VALID_EPOCH


# ---------------------------------------------------------------------------
# Device identity — prefer hardware-stable IDs comma already provides.
#
# Priority:
#   1) DongleId        — comma-issued, only present after registration. Most stable.
#   2) HardwareSerial  — hardware-derived (CPU/IMEI), persistent across reflashes.
#   3) CarrotDeviceId  — generated UUID fallback for devices that have neither.
#
# Final id is cached in CarrotDeviceId so the chosen id never changes even if
# DongleId is set later (avoids re-uploading the same data under a new id).

def _read_param_str(params: Params, key: str) -> str:
  try:
    v = params.get(key)
    if isinstance(v, bytes):
      return v.decode("utf-8", "ignore").strip()
    return (v or "").strip()
  except Exception:
    return ""


def _car_key_from_name(name: str) -> str:
  text = re.sub(r"[^A-Za-z0-9]+", "_", str(name).strip()).strip("_").upper()
  return text


def _steer_kind_from_car_params(car_params) -> str:
  value = getattr(car_params, "steerControlType", "")
  text = str(value).lower()
  try:
    numeric = int(value)
  except Exception:
    numeric = None
  if text.endswith(".angle") or text == "angle" or numeric == 1:
    return "angle"
  return "torque"


def _read_car_params(params: Params):
  raw = None
  for key in ("CarParams", "CarParamsPersistent", "CarParamsCache"):
    try:
      raw = params.get(key)
    except Exception:
      raw = None
    if raw:
      break
  if not raw:
    return None
  try:
    import cereal.messaging as messaging
    from cereal import car
    return messaging.log_from_bytes(raw, car.CarParams)
  except Exception:
    return None


def get_device_id(params: Params) -> str:
  cached = _read_param_str(params, "CarrotDeviceId")
  if cached:
    return cached

  # DongleId may be present but set to "UnregisteredDevice" before comma
  # registration. Treat any value containing "unregistered" as missing.
  for source in ("DongleId", "HardwareSerial"):
    v = _read_param_str(params, source)
    if not v:
      continue
    if "unregistered" in v.lower() or v.lower() in ("none", "n/a", "0", "default"):
      continue
    params.put("CarrotDeviceId", v)
    _log(f"using {source}={v} as CarrotDeviceId")
    return v

  new_id = uuid.uuid4().hex[:16]
  params.put("CarrotDeviceId", new_id)
  _log(f"generated CarrotDeviceId={new_id} (no DongleId/HardwareSerial)")
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


def _is_offroad(params: Params) -> bool:
  try:
    return not bool(params.get_bool("IsOnroad"))
  except Exception:
    return True


def upload_allowed(params: Params) -> tuple[bool, str]:
  # Battery check intentionally removed — comma C3/C3X is car-powered, the
  # tiny internal battery reading isn't meaningful, and a battery gate just
  # blocks uploads on bench testing. Keep CarrotUploadMinBattery param around
  # for backward compatibility but ignore its value.
  if not params.get_bool("CarrotDataUpload"):
    return False, "toggle off"
  if not _clock_synced():
    return False, "clock not synced (waiting for network time)"
  if params.get_bool("CarrotUploadWifiOnly") and not _on_wifi():
    return False, "not on wifi"
  if params.get_bool("CarrotUploadOnlyOffroad") and not _is_offroad(params):
    return False, "onroad"
  return True, ""


# ---------------------------------------------------------------------------
# Filesystem scanning

def list_segments() -> list[tuple[str, str, Path]]:
  """Returns list of (route_id, segment, path) sorted oldest-first.

  Registered comma devices name routes "YYYY-MM-DD--HH-MM-SS--N" so name
  sorting is already chronological. Unregistered devices use
  "00000000--<hash>--N" — the bootcount stays zero so name-sorting falls back
  to hash alphabetical, which has nothing to do with real time. Use directory
  mtime as the primary key so oldest-first holds in both cases; fall back to
  (route, seg) for stability when mtimes tie.
  """
  out = []
  if not REALDATA.exists():
    return out
  for entry in REALDATA.iterdir():
    m = ROUTE_SEG_RE.match(entry.name)
    if not m:
      continue
    try:
      mtime = entry.stat().st_mtime
    except OSError:
      mtime = 0.0
    out.append((mtime, m.group("route"), m.group("seg"), entry))
  out.sort(key=lambda x: (x[0], x[1], int(x[2])))
  return [(route, seg, path) for _, route, seg, path in out]


def is_segment_complete(seg_dir: Path) -> bool:
  """Heuristic: rlog.zst exists and hasn't been touched in 30s.

  Short window so uploads start soon after a segment closes, even mid-drive.
  """
  rlog = seg_dir / "rlog.zst"
  if not rlog.exists():
    return False
  try:
    mtime = rlog.stat().st_mtime
  except OSError:
    return False
  return (time.time() - mtime) > 30


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
  # Cloudflare blocks the default Python-urllib User-Agent as a bot. Use a
  # distinct identifier so it passes Bot Fight Mode / Browser Integrity Check.
  req.add_header("User-Agent", "carrot-cas-uploader/0.1")
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
  car_name = _read_param_str(params, "CarName")
  car_selected = _read_param_str(params, "CarSelected3")

  # Persist most-recent good CarName. Lets a future upload that happens before
  # CarParams becomes available (e.g. just after boot) still carry a hint:
  # 디바이스가 "지난 번엔 이 차였다"고 알려줌. Server side adds last_known_car to
  # its car_key resolution chain so even pre-identification uploads bin correctly.
  if car_name and car_name.upper() != "MOCK":
    try:
      params.put("CarrotLastCarName", car_name)
    except Exception:
      pass
  last_known_car = _read_param_str(params, "CarrotLastCarName")

  car_params = _read_car_params(params)
  car_fingerprint = ""
  car_make = ""
  car_model_year = ""
  kind = ""
  if car_params is not None:
    car_fingerprint = str(getattr(car_params, "carFingerprint", "")).strip()
    kind = _steer_kind_from_car_params(car_params)
    car_make = str(getattr(car_params, "make", "") or getattr(car_params, "brand", "")).strip()
    year_attr = getattr(car_params, "year", "")
    car_model_year = str(year_attr).strip() if year_attr else ""

  # Phase 6: CarSelected3 is the source of truth. It's what the user picked in
  # CarrotWeb ("Hyundai Casper EV 2024"), so it captures generation/year info
  # exactly the way the user (and the CarrotWeb car list) thinks of the car.
  # carFingerprint/CarName are openpilot's internal platform keys — used as
  # fallback when no CarSelected3 (uncommon, only pre-setup devices).
  # last_known_car catches the very early-boot case where neither is populated.
  car_key = car_selected or car_fingerprint or car_name or last_known_car

  carrot_version  = _read_param_str(params, "GitCommit")[:12]
  carrot_branch   = _read_param_str(params, "GitBranch")
  hardware_serial = _read_param_str(params, "HardwareSerial")
  dongle_id       = _read_param_str(params, "DongleId")
  cas_model       = _read_param_str(params, "CASModelName")

  # EPS firmware hash — **reference only**, NEVER a primary matching key.
  # Same SHA1-12 the runtime computes; surfaced here so the PC GUI can show
  # "this car has EPS XYZ" for debug/diagnostic context. Server's car_key
  # resolution chain intentionally ignores this field (matches the runtime
  # behavior where EPS hash mismatch no longer disqualifies a model).
  eps_hash = ""
  try:
    try:
      from openpilot.selfdrive.carrot.cas.metadata import eps_firmware_hash
    except ModuleNotFoundError:
      from selfdrive.carrot.cas.metadata import eps_firmware_hash
    if car_params is not None and hasattr(car_params, "carFw"):
      eps_hash = eps_firmware_hash(list(car_params.carFw))
  except Exception:
    pass

  # Duration: openpilot segments are ~60s each — that's the reliable estimate.
  # Do NOT derive duration from segment mtimes: mtime reflects file write/copy/
  # sync time and can span boots, inflating the value by orders of magnitude.
  duration_sec = int(len(segments) * 60)
  duration_estimated = True
  # route_start/end timestamps kept as *informational* metadata only (when the
  # files were last written) — never used for duration.
  route_start_ts = 0
  route_end_ts = 0
  if segments:
    try:
      mtimes = sorted(int(s.stat().st_mtime) for s in segments if s.exists())
      if mtimes:
        route_start_ts = mtimes[0]
        route_end_ts   = mtimes[-1]
    except OSError:
      pass

  file_bytes = {}
  for fname in UPLOAD_FILES:
    total = 0
    for seg_dir in segments:
      try:
        total += int((seg_dir / fname).stat().st_size)
      except OSError:
        pass
    file_bytes[fname] = total

  return {
    "meta_schema_version": 2,
    "device_id":         device_id,
    "route_id":          route_id,
    # Car identity (most-specific first; server.lookup walks down this chain)
    "car":               car_fingerprint or car_name,
    "car_key":           _car_key_from_name(car_key),
    "car_name_raw":      car_name,
    "car_selected":      car_selected,
    "last_known_car":    last_known_car,
    "car_make":          car_make,
    "car_model_year":    car_model_year,
    "eps_firmware_hash": eps_hash,
    "kind":              kind,
    "steer_control_type": kind,
    # Device traceability
    "dongle_id":         dongle_id,
    "hardware_serial":   hardware_serial,
    "carrot_version":    carrot_version,
    "carrot_branch":     carrot_branch,
    "cas_model_used":    cas_model,
    # Route stats
    "segments":          len(segments),
    "duration_sec":      duration_sec,
    "duration_estimated": duration_estimated,
    "route_start_ts":    route_start_ts,
    "route_end_ts":      route_end_ts,
    "file_bytes":        file_bytes,
    "uploaded_at":       int(time.time()),
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

  last_reason = None       # avoid spamming the same gate-block message
  last_scan_summary = None # avoid spamming the same scan result

  while True:
    ok, reason = upload_allowed(params)
    if not ok:
      if reason != last_reason:
        _log(f"idle: {reason}")
        last_reason = reason
      time.sleep(POLL_OFF_SEC)
      continue
    if last_reason is not None:
      _log("gates OK, scanning")
      last_reason = None

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
