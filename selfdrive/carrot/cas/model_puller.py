#!/usr/bin/env python3
"""
CAS model puller — at boot, fetch the latest trained model from the carrot
upload server and install it to /data/cas_weights/<CAR>.json. CASRuntime
scans this dir at load_model time, preferring it over the git-tracked
selfdrive/carrot/cas/weights/ (factory fallback).

Boot-once semantics:
  - Wait for network/NTP
  - Try the fetch (with short retries for transient failures)
  - Sleep forever once done (managed process restarts on reboot)

Car identity priority (matches build_route_meta):
  CarSelected3 > CarName > CarrotLastCarName
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
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
  from openpilot.selfdrive.carrot.cas import upload_config
  from openpilot.selfdrive.carrot.cas.model import CASModel
except ModuleNotFoundError:
  from selfdrive.carrot.cas import upload_config
  from selfdrive.carrot.cas.model import CASModel


WEIGHTS_DIR = Path("/data/cas_weights")
VERSIONS_PATH = WEIGHTS_DIR / "_versions.json"
KINDS = ("torque", "angle")

# Boot-once cadence
NETWORK_WAIT_SEC      = 300                  # max wait for NTP/online
RETRY_DELAYS_SEC      = (10, 30, 90)         # backoff between retries
SLEEP_AFTER_DONE_SEC  = 24 * 3600            # park until reboot

# Same NTP-synced markers data_uploader uses
NTP_SYNCED_FLAG = Path("/run/systemd/timesync/synchronized")
MIN_VALID_EPOCH = 1704067200                 # 2024-01-01


def _log(msg: str) -> None:
  if cloudlog is not None:
    cloudlog.info(f"[cas_puller] {msg}")
  else:
    print(f"[cas_puller] {msg}", flush=True)


def _read_param_str(params: Params, key: str) -> str:
  try:
    v = params.get(key)
    if isinstance(v, bytes):
      return v.decode("utf-8", "ignore").strip()
    return (v or "").strip()
  except Exception:
    return ""


def _norm_car(name: str) -> str:
  """Server's CAR_RE expects [A-Z0-9_]. Normalize to that alphabet."""
  upper = (name or "").upper()
  safe = re.sub(r"[^A-Z0-9_]+", "_", upper).strip("_")
  return safe


def _wait_for_network(timeout_sec: int) -> bool:
  deadline = time.time() + timeout_sec
  while time.time() < deadline:
    try:
      if NTP_SYNCED_FLAG.exists():
        return True
    except OSError:
      pass
    if time.time() > MIN_VALID_EPOCH:
      return True
    time.sleep(10)
  return False


def _read_versions() -> dict:
  try:
    return json.loads(VERSIONS_PATH.read_text(encoding="utf-8"))
  except Exception:
    return {}


def _write_versions(data: dict) -> None:
  WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
  tmp = VERSIONS_PATH.with_suffix(".tmp")
  tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
  tmp.replace(VERSIONS_PATH)


def _http_get_json(url: str, timeout: float = 15.0) -> dict:
  req = urllib.request.Request(url, headers={"User-Agent": "carrot-cas-puller/1.0"})
  with urllib.request.urlopen(req, timeout=timeout) as resp:
    return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path, timeout: float = 60.0) -> None:
  req = urllib.request.Request(url, headers={"User-Agent": "carrot-cas-puller/1.0"})
  dest.parent.mkdir(parents=True, exist_ok=True)
  tmp = dest.with_suffix(dest.suffix + ".part")
  try:
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
      while True:
        chunk = resp.read(1024 * 1024)
        if not chunk:
          break
        f.write(chunk)
    tmp.replace(dest)
  except Exception:
    try:
      tmp.unlink(missing_ok=True)
    except OSError:
      pass
    raise


def _resolve_car_candidates(params: Params) -> list[str]:
  """Multiple candidate names to try in priority order. Server may have
  published the model under any one of the device's identification fields,
  with or without a trailing year suffix (e.g. CarSelected3 'Hyundai Casper
  EV 2024' vs openpilot's platform name 'HYUNDAI_CASPER_EV')."""
  raw = []
  for key in ("CarSelected3", "CarName", "CarrotLastCarName"):
    v = _read_param_str(params, key)
    if v and v.upper() != "MOCK":
      raw.append(v)

  cands: list[str] = []
  seen: set[str] = set()
  for name in raw:
    n = _norm_car(name)
    if n and n not in seen:
      cands.append(n); seen.add(n)
    # Try year-stripped variant too (HYUNDAI_CASPER_EV_2024 -> HYUNDAI_CASPER_EV).
    stripped = re.sub(r"_\d{4}$", "", n)
    if stripped and stripped != n and stripped not in seen:
      cands.append(stripped); seen.add(stripped)
  return cands


def check_and_install(params: Params, candidates: list[str]) -> int:
  """Try each kind for each candidate car name. First non-404 response wins
  for that kind. Returns how many ended up newly installed."""
  endpoint = upload_config.resolve_endpoint(params).rstrip("/")
  versions = _read_versions()
  updated = 0

  for kind in KINDS:
    # Walk candidates until one returns a model (or a non-404 error).
    car: str | None = None
    info: dict | None = None
    for cand in candidates:
      try:
        info = _http_get_json(f"{endpoint}/api/models/{cand}/{kind}/latest")
        car = cand
        break
      except urllib.error.HTTPError as e:
        if e.code == 404:
          continue          # try next candidate
        _log(f"{cand}/{kind} HTTP {e.code}")
        info = None
        break
      except Exception as e:
        _log(f"{cand}/{kind} fetch error: {e}")
        info = None
        break
    if info is None or car is None:
      continue              # no model for any candidate (normal first time)
    key = f"{car}/{kind}"
    if len(candidates) > 1 and car != candidates[0]:
      _log(f"{kind}: matched candidate {car} (primary was {candidates[0]})")

    server_version = str(info.get("version", "")).strip()
    if not server_version:
      _log(f"{key} server returned no version")
      continue
    local_version = versions.get(key, "")
    if server_version == local_version:
      _log(f"{key} already at v={server_version}")
      continue

    _log(f"{key} new version {local_version!r} -> {server_version!r}")
    download_url = str(info.get("download_url", "")).strip()
    if not download_url.startswith("/"):
      _log(f"{key} bad download_url: {download_url}")
      continue

    tmp = WEIGHTS_DIR / f"{car}.{kind}.tmp.json"
    try:
      _download(endpoint + download_url, tmp)
    except Exception as e:
      _log(f"{key} download failed: {e}")
      continue

    # Validate by trying to load via the runtime's own parser. A model that
    # CASModel can't load is useless — discard instead of installing a brick.
    try:
      probe = CASModel(tmp)
      del probe
    except Exception as e:
      _log(f"{key} validation failed: {e}")
      try:
        tmp.unlink(missing_ok=True)
      except OSError:
        pass
      continue

    # Install: one weights file per car (CASRuntime matches by car name + kind
    # field inside the JSON). For a user with both torque AND angle published
    # for the same car, latest install wins for that file — but in practice a
    # given car only ever produces one kind anyway.
    dest = WEIGHTS_DIR / f"{car}.json"
    try:
      tmp.replace(dest)
    except Exception as e:
      _log(f"{key} install failed: {e}")
      continue

    versions[key] = server_version
    _write_versions(versions)
    updated += 1
    sha_preview = str(info.get("sha256", ""))[:12]
    _log(f"{key} installed v={server_version} sha={sha_preview} -> {dest}")

  return updated


def run() -> None:
  WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
  params = Params()

  _log(f"start — waiting for network (timeout {NETWORK_WAIT_SEC}s)")
  if not _wait_for_network(NETWORK_WAIT_SEC):
    _log("network/NTP not available — giving up this boot")
  else:
    candidates = _resolve_car_candidates(params)
    if not candidates:
      _log("no CarSelected3 / CarName / CarrotLastCarName — skip")
    else:
      endpoint = upload_config.resolve_endpoint(params)
      _log(f"car candidates={candidates} endpoint={endpoint}")
      done = False
      for attempt, delay in enumerate(RETRY_DELAYS_SEC, 1):
        try:
          n = check_and_install(params, candidates)
          _log(f"boot-once done: {n} update(s)")
          done = True
          break
        except Exception as e:
          _log(f"attempt {attempt} error: {e} — retry in {delay}s")
          time.sleep(delay)
      if not done:
        _log("all attempts exhausted — sleep until next boot")

  # managed process: don't exit (would just be restarted). Park.
  while True:
    time.sleep(SLEEP_AFTER_DONE_SEC)


def main() -> None:
  try:
    run()
  except KeyboardInterrupt:
    return


if __name__ == "__main__":
  main()
