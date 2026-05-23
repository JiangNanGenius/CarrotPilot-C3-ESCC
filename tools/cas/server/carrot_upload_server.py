"""
CAS upload + dataset manifest server.

Deployment target:
  /opt/carrot-upload/server.py

Storage layout:
  /srv/carrot_rlogs/by-device/<device_id>/<route_id>/<segment>/{rlog.zst,qlog.zst}
  /srv/carrot_rlogs/by-device/<device_id>/<route_id>/route_meta.json
  /srv/carrot_rlogs/server_train_runs.json

Upload auth:
  HMAC-SHA256 over "<device_id>|<ts>" with /etc/carrot-upload/secret.

Read API auth:
  If /etc/carrot-upload/read_token exists, /api/* and /download/* require
  Authorization: Bearer <token>. If absent, read API is open for compatibility.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import os
import re
import shutil
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse


SECRET_PATH = Path("/etc/carrot-upload/secret")
READ_TOKEN_PATH = Path("/etc/carrot-upload/read_token")
BASE = Path("/srv/carrot_rlogs")
# Phase 7 folder structure:
#   car/<carname>/<route>/   ← canonical raw storage (organized by car type, ACTIVE)
#   device/<device_id>/      ← reserved for future per-device personalization (EMPTY now)
#   model/<carname>/<kind>/  ← OTA-distributable trained models
# Variable names kept (BY_CAR/BY_DEVICE) for diff continuity, but semantics
# changed: BY_CAR is now canonical (not symlink view), BY_DEVICE is empty.
BY_CAR      = BASE / "car"                                   # ★ canonical raw storage
BY_DEVICE   = BASE / "device"                                # empty placeholder for future
MODELS_BASE = BASE / "model"
TRAIN_RUNS_PATH = BASE / "server_train_runs.json"
MAX_MODEL_BYTES = 4 * 1024 * 1024     # 4 MB — typical CAS JSON is < 200 KB
VERSION_RE = re.compile(r"^[0-9]{8}_[0-9]{6}$")

MAX_BODY_BYTES = 50 * 1024 * 1024
TS_WINDOW = 300
DISK_WARN_PCT = 85
DISK_TARGET_PCT = 75
CLEANUP_EVERY_N = 100

ALLOWED_FILES = {"rlog.zst", "qlog.zst", "route_meta.json"}
DOWNLOAD_FILES = {"rlog.zst", "qlog.zst", "route_meta.json", "car.txt"}
DEVICE_RE = re.compile(r"^[a-zA-Z0-9_-]{4,32}$")
ROUTE_RE = re.compile(r"^[a-zA-Z0-9_:\-]{4,80}$")
SEGMENT_RE = re.compile(r"^(?:\d{1,5}|meta)$")
CAR_RE = re.compile(r"^[A-Z0-9_]{2,64}$")
KIND_RE = re.compile(r"^(?:torque|angle)$")

SECRET = SECRET_PATH.read_text(encoding="utf-8").strip().encode("utf-8")
BY_DEVICE.mkdir(parents=True, exist_ok=True)
BY_CAR.mkdir(parents=True, exist_ok=True)
MODELS_BASE.mkdir(parents=True, exist_ok=True)


def _version_from_trained_at(trained_at: str) -> str:
  """ISO '2026-05-22T15:30:00+00:00' → '20260522_153000'. Falls back to now."""
  if trained_at:
    try:
      ta = trained_at.replace("Z", "+00:00")
      dt = datetime.fromisoformat(ta)
      return dt.strftime("%Y%m%d_%H%M%S")
    except Exception:
      pass
  return datetime.now().strftime("%Y%m%d_%H%M%S")

app = FastAPI(title="carrot-upload", docs_url=None, redoc_url=None)
_upload_counter = 0

# ─── live status (in-memory, lost on restart — fine, it's a monitoring view) ──
# Safe as plain globals because the service runs single-worker (--workers 1) and
# the upload handler is async on one event loop, so there's no true parallelism
# to race these. With multiple workers these counts would be per-worker and wrong.
SERVER_START = time.time()
RECENT_UPLOADS: deque = deque(maxlen=300)   # {ts, device_id, car, ip, bytes, file}
_inflight = 0
_status_cache: dict[str, Any] = {"at": 0.0, "text": ""}
STATUS_CACHE_SEC = 5.0   # disk scan is cheap but pointless to redo every 2s


def _verify_sig(device_id: str, ts: str, sig: str) -> bool:
  try:
    ts_int = int(ts)
  except (TypeError, ValueError):
    return False
  if abs(time.time() - ts_int) > TS_WINDOW:
    return False
  msg = f"{device_id}|{ts}".encode("utf-8")
  expected = _hmac.new(SECRET, msg, hashlib.sha256).hexdigest()
  return _hmac.compare_digest(expected, (sig or "").lower())


def _read_token() -> str:
  try:
    return READ_TOKEN_PATH.read_text(encoding="utf-8").strip()
  except OSError:
    return ""


def _require_read_auth(authorization: str = ""):
  token = _read_token()
  if not token:
    return
  expected = f"Bearer {token}"
  if not _hmac.compare_digest(authorization.strip(), expected):
    raise HTTPException(status_code=401, detail="missing or bad read token")


def _disk_used_pct() -> float:
  usage = shutil.disk_usage(BASE)
  return 100.0 * usage.used / max(usage.total, 1)


def _cleanup_if_needed():
  if _disk_used_pct() < DISK_WARN_PCT:
    return
  routes = []
  for route_dir in _iter_route_dirs():
    try:
      routes.append((route_dir.stat().st_mtime, route_dir))
    except OSError:
      continue
  routes.sort(key=lambda x: x[0])
  for _, route_dir in routes:
    if _disk_used_pct() < DISK_TARGET_PCT:
      break
    try:
      car_links_for(route_dir)
      shutil.rmtree(route_dir, ignore_errors=True)
      print(f"[cleanup] removed {route_dir}", flush=True)
    except Exception as e:
      print(f"[cleanup] failed {route_dir}: {e}", flush=True)


# Phase 7: symlink helpers removed. BY_CAR now holds canonical files directly,
# no by-device shadow. (Previous _ensure_car_symlink / car_links_for were used
# to build the by-car/ view over by-device/ canonical storage.)


def _read_json(path: Path) -> dict[str, Any]:
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return {}


def _write_json_atomic(path: Path, payload: dict[str, Any]):
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_suffix(path.suffix + ".part")
  tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  os.replace(tmp, path)


def _route_meta(route_dir: Path) -> dict[str, Any]:
  # Phase 7: route_dir is car/<carname>/<route_id>/, so route_dir.parent.name
  # is the CAR_KEY (was device_id in Phase 6). device_id now must come from
  # the meta file itself (device always populates it in build_route_meta).
  meta = _read_json(route_dir / "route_meta.json")
  if "route_id" not in meta:
    meta["route_id"] = route_dir.name
  return meta


def _car_key_from_meta(route_dir: Path, meta: dict[str, Any]) -> str:
  # car_key first — device-normalized result. With the Phase 6 priority, the
  # device puts CarSelected3 (CarrotWeb's "Hyundai Casper EV 2024" style) at
  # the top of its chain, so car_key already reflects the user's explicit
  # menu choice with year preserved. car_selected next as direct fallback if
  # an older client didn't promote it to car_key. Other fields after.
  # EPS firmware hash is intentionally NOT in this chain — reference diagnostic
  # only (matches runtime's behavior of treating EPS as a tiebreaker bonus,
  # never a disqualifier).
  for key in ("car_key", "car_selected", "car", "car_name_raw", "last_known_car"):
    value = str(meta.get(key, "")).strip()
    normalized = _norm_car_key(value)
    if normalized:
      return normalized
  try:
    return _norm_car_key((route_dir / "car.txt").read_text(encoding="utf-8").strip())
  except OSError:
    return ""


def _kind_from_meta(meta: dict[str, Any]) -> str:
  kind = str(meta.get("kind", "")).strip().lower()
  if kind in ("torque", "angle"):
    return kind
  steer_type = str(meta.get("steer_control_type", "")).strip().lower()
  if steer_type.endswith(".angle") or steer_type == "angle" or steer_type == "1":
    return "angle"
  return "torque"


def _norm_car_key(value: str) -> str:
  value = value.strip()
  if not value:
    return ""
  safe = "".join(c.upper() if c.isalnum() else "_" for c in value)
  safe = re.sub(r"_+", "_", safe).strip("_")
  return safe if CAR_RE.match(safe) else ""


def _iter_route_dirs():
  # Phase 7: walks BY_CAR/<car_key>/<route_id>/. (Was BY_DEVICE/<device>/<route>.)
  if not BY_CAR.exists():
    return
  for car_dir in sorted(BY_CAR.iterdir(), key=lambda p: p.name):
    if not car_dir.is_dir():
      continue
    for route_dir in sorted(car_dir.iterdir(), key=lambda p: p.name):
      if route_dir.is_dir():
        yield route_dir


def _segment_dirs(route_dir: Path):
  for child in sorted(route_dir.iterdir(), key=lambda p: _segment_sort_key(p.name)):
    if child.is_dir() and SEGMENT_RE.match(child.name):
      yield child


def _segment_sort_key(name: str):
  try:
    return (0, int(name))
  except ValueError:
    return (1, name)


def _file_size(path: Path) -> int:
  try:
    return int(path.stat().st_size)
  except OSError:
    return 0


def _duration_hours(meta: dict[str, Any]) -> float:
  for key, scale in (("duration_sec", 3600.0), ("duration_s", 3600.0), ("duration_hours", 1.0)):
    try:
      value = float(meta.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
      value = 0.0
    if value > 0.0:
      return value / scale
  return 0.0


def _route_record(route_dir: Path) -> dict[str, Any]:
  # Phase 7: route_dir is BY_CAR/<car_key>/<route_id>/.
  meta = _route_meta(route_dir)
  route_id = str(meta.get("route_id", route_dir.name))
  # car_key from path (canonical), falling back to meta lookup chain if needed.
  car_key = _norm_car_key(route_dir.parent.name) or _car_key_from_meta(route_dir, meta)
  # device_id from meta (was: from path). Always populated by device's build_route_meta.
  device_id = str(meta.get("device_id", ""))
  kind = _kind_from_meta(meta)
  eps_hash = str(meta.get("eps_firmware_hash", "")).strip()
  segments = []
  total_bytes = 0

  for seg_dir in _segment_dirs(route_dir):
    files = {}
    for filename in ("rlog.zst", "qlog.zst"):
      path = seg_dir / filename
      if path.exists():
        size = _file_size(path)
        total_bytes += size
        files[filename] = {
          "bytes": size,
          # Phase 7: download URL keyed by car_key (was device_id).
          "download_url": f"/download/{car_key}/{route_id}/{seg_dir.name}/{filename}",
        }
    segments.append({
      "segment": seg_dir.name,
      "files": files,
      "complete": "rlog.zst" in files and "qlog.zst" in files,
    })

  # Duration: openpilot segments are ~60s each, and we hold the actual segment
  # dirs on disk — that's the reliable source. meta.duration_sec is NOT trusted
  # (older/buggy device builds derived it from file mtimes and could inflate it
  # by orders of magnitude). Fall back to meta only for meta-only records that
  # have no segment dirs on disk.
  if segments:
    duration_hours = len(segments) / 60.0
  else:
    duration_hours = _duration_hours(meta)

  return {
    "device_id": device_id,
    "route_id": route_id,
    "car_key": car_key,
    "kind": kind,
    "eps_firmware_hash": eps_hash,
    "uploaded_at": meta.get("uploaded_at"),
    "duration_hours": round(duration_hours, 4),
    "segment_count": len(segments),
    "complete_segment_count": sum(1 for seg in segments if seg.get("complete")),
    "bytes": total_bytes,
    "segments": segments,
    "route_meta": meta,
  }


def _filter_route(record: dict[str, Any], car_key: str = "", kind: str = "", device_id: str = "") -> bool:
  if car_key and record.get("car_key") != _norm_car_key(car_key):
    return False
  if kind and record.get("kind") != kind:
    return False
  if device_id and record.get("device_id") != device_id:
    return False
  return True


def _dataset_key(car_key: str, kind: str) -> str:
  return f"{car_key or 'UNKNOWN_CAR'}/{kind or 'torque'}"


def _load_train_runs() -> dict[str, Any]:
  if not TRAIN_RUNS_PATH.exists():
    return {"version": 1, "runs": []}
  data = _read_json(TRAIN_RUNS_PATH)
  if not isinstance(data.get("runs"), list):
    data["runs"] = []
  return data


def _train_run_summary() -> dict[str, dict[str, Any]]:
  summary = {}
  for run in _load_train_runs().get("runs", []):
    car_key = _norm_car_key(str(run.get("car_key", "")))
    kind = str(run.get("kind", "torque")).strip() or "torque"
    key = _dataset_key(car_key, kind)
    item = summary.setdefault(key, {"trained_hours": 0.0, "run_count": 0, "latest_at": ""})
    item["trained_hours"] = max(float(item["trained_hours"]), float(run.get("trained_on_hours", 0.0) or 0.0))
    item["run_count"] = int(item["run_count"]) + 1
    created_at = str(run.get("created_at", ""))
    if created_at >= item["latest_at"]:
      item["latest_at"] = created_at
  return summary


def _manifest(car_key: str = "", kind: str = "", device_id: str = "", include_routes: bool = True) -> dict[str, Any]:
  datasets: dict[str, dict[str, Any]] = {}
  eps_sets: dict[str, set[str]] = {}
  train_summary = _train_run_summary()

  for route_dir in _iter_route_dirs():
    record = _route_record(route_dir)
    if not _filter_route(record, car_key, kind, device_id):
      continue
    ds_key = _dataset_key(str(record.get("car_key", "")), str(record.get("kind", "torque")))
    dataset = datasets.setdefault(ds_key, {
      "dataset_key": ds_key,
      "car_key": record.get("car_key") or "UNKNOWN_CAR",
      "kind": record.get("kind") or "torque",
      "source": "server",
      "eps_firmware_hashes": [],
      "routes": [],
      "summary": {
        "route_count": 0,
        "segment_count": 0,
        "source_count": 0,
        "total_hours": 0.0,
        "trained_hours": 0.0,
        "train_run_count": 0,
      },
    })
    eps_sets.setdefault(ds_key, set())
    if record.get("eps_firmware_hash"):
      eps_sets[ds_key].add(str(record["eps_firmware_hash"]))
    if include_routes:
      dataset["routes"].append(record)
    dataset["summary"]["route_count"] += 1
    dataset["summary"]["segment_count"] += int(record.get("complete_segment_count", 0))
    dataset["summary"]["source_count"] += int(record.get("complete_segment_count", 0))
    dataset["summary"]["total_hours"] += float(record.get("duration_hours", 0.0))

  for key, dataset in datasets.items():
    hist = train_summary.get(key, {})
    dataset["eps_firmware_hashes"] = sorted(eps_sets.get(key, set()))
    dataset["summary"]["trained_hours"] = float(hist.get("trained_hours", 0.0) or 0.0)
    dataset["summary"]["train_run_count"] = int(hist.get("run_count", 0) or 0)
    dataset["summary"]["new_hours"] = max(0.0, dataset["summary"]["total_hours"] - dataset["summary"]["trained_hours"])
    for hkey in ("total_hours", "trained_hours", "new_hours"):
      dataset["summary"][hkey] = round(float(dataset["summary"][hkey]), 4)

  dataset_list = sorted(datasets.values(), key=lambda item: (item["car_key"], item["kind"]))
  return {
    "version": 1,
    "source": "server",
    "created_at": datetime.now().isoformat(timespec="seconds"),
    "datasets": dataset_list,
    "summary": {
      "dataset_count": len(dataset_list),
      "route_count": sum(int(item["summary"]["route_count"]) for item in dataset_list),
      "segment_count": sum(int(item["summary"]["segment_count"]) for item in dataset_list),
      "source_count": sum(int(item["summary"]["source_count"]) for item in dataset_list),
      "total_hours": round(sum(float(item["summary"]["total_hours"]) for item in dataset_list), 4),
    },
  }


@app.get("/health")
async def health():
  return PlainTextResponse("ok")


@app.get("/api/datasets")
async def api_datasets(
  car_key: str = Query(default=""),
  kind: str = Query(default=""),
  device_id: str = Query(default=""),
  include_routes: bool = Query(default=True),
  authorization: str = Header(default=""),
):
  _require_read_auth(authorization)
  if kind and not KIND_RE.match(kind):
    raise HTTPException(status_code=400, detail="bad kind")
  return JSONResponse(_manifest(car_key, kind, device_id, include_routes=include_routes))


@app.get("/api/datasets/summary")
async def api_dataset_summary(
  car_key: str = Query(default=""),
  kind: str = Query(default=""),
  device_id: str = Query(default=""),
  authorization: str = Header(default=""),
):
  _require_read_auth(authorization)
  manifest = _manifest(car_key, kind, device_id, include_routes=False)
  return JSONResponse(manifest["summary"] | {"datasets": [
    {k: dataset[k] for k in ("dataset_key", "car_key", "kind", "source", "summary")}
    for dataset in manifest["datasets"]
  ]})


@app.get("/api/routes")
async def api_routes(
  car_key: str = Query(default=""),
  kind: str = Query(default=""),
  device_id: str = Query(default=""),
  limit: int = Query(default=500, ge=1, le=5000),
  authorization: str = Header(default=""),
):
  _require_read_auth(authorization)
  routes = []
  for dataset in _manifest(car_key, kind, device_id, include_routes=True)["datasets"]:
    routes.extend(dataset.get("routes", []))
  routes.sort(key=lambda item: (str(item.get("uploaded_at", "")), str(item.get("route_id", ""))), reverse=True)
  return JSONResponse({"routes": routes[:limit], "count": min(len(routes), limit), "total": len(routes)})


@app.get("/api/devices/{device_id}/routes")
async def api_device_routes(device_id: str, authorization: str = Header(default="")):
  _require_read_auth(authorization)
  if not DEVICE_RE.match(device_id):
    raise HTTPException(status_code=400, detail="bad device_id")
  return await api_routes(device_id=device_id, authorization=authorization)


@app.post("/api/train-runs")
async def api_train_runs(request: Request, authorization: str = Header(default="")):
  _require_read_auth(authorization)
  payload = await request.json()
  car_key = _norm_car_key(str(payload.get("car_key") or payload.get("car") or ""))
  kind = str(payload.get("kind") or "torque").strip()
  if not car_key:
    raise HTTPException(status_code=400, detail="missing car_key")
  if not KIND_RE.match(kind):
    raise HTTPException(status_code=400, detail="bad kind")
  run = dict(payload)
  run["car_key"] = car_key
  run["kind"] = kind
  run.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
  data = _load_train_runs()
  data.setdefault("runs", []).append(run)
  data["updated_at"] = datetime.now().isoformat(timespec="seconds")
  _write_json_atomic(TRAIN_RUNS_PATH, data)
  return JSONResponse({"ok": True, "count": len(data["runs"])})


@app.get("/api/train-runs/latest")
async def api_latest_train_run(
  car_key: str = Query(...),
  kind: str = Query(default="torque"),
  authorization: str = Header(default=""),
):
  _require_read_auth(authorization)
  key_car = _norm_car_key(car_key)
  matches = [
    run for run in _load_train_runs().get("runs", [])
    if _norm_car_key(str(run.get("car_key") or run.get("car") or "")) == key_car
    and str(run.get("kind") or "torque") == kind
  ]
  matches.sort(key=lambda run: str(run.get("created_at", "")), reverse=True)
  return JSONResponse({"run": matches[0] if matches else None})


@app.get("/download/{car_key}/{route_id}/{segment}/{filename}")
async def download(
  car_key: str,
  route_id: str,
  segment: str,
  filename: str,
  authorization: str = Header(default=""),
):
  # Phase 7: URL path uses car_key (was device_id). PC builds URL from car_key
  # in route records returned by /api/datasets and /api/routes.
  _require_read_auth(authorization)
  if not CAR_RE.match(car_key):
    raise HTTPException(status_code=400, detail="bad car_key")
  if not ROUTE_RE.match(route_id):
    raise HTTPException(status_code=400, detail="bad route_id")
  if not SEGMENT_RE.match(segment):
    raise HTTPException(status_code=400, detail="bad segment")
  if filename not in DOWNLOAD_FILES:
    raise HTTPException(status_code=400, detail="bad filename")
  root = BY_CAR / car_key / route_id
  path = root / filename if segment == "meta" else root / segment / filename
  try:
    path.resolve().relative_to(root.resolve())
  except ValueError:
    raise HTTPException(status_code=400, detail="bad path")
  if not path.exists() or not path.is_file():
    raise HTTPException(status_code=404, detail="not found")
  return FileResponse(path, filename=filename)


@app.post("/upload/{device_id}/{route_id}/{segment}/{filename}")
async def upload(
  device_id: str,
  route_id: str,
  segment: str,
  filename: str,
  request: Request,
  x_carrot_ts: str = Header(default=""),
  x_carrot_sig: str = Header(default=""),
  x_carrot_version: str = Header(default=""),
  x_carrot_car: str = Header(default=""),
  x_carrot_eps_hash: str = Header(default=""),
  x_carrot_cas_model: str = Header(default=""),
):
  if not DEVICE_RE.match(device_id):
    raise HTTPException(status_code=400, detail="bad device_id")
  if not ROUTE_RE.match(route_id):
    raise HTTPException(status_code=400, detail="bad route_id")
  if not SEGMENT_RE.match(segment):
    raise HTTPException(status_code=400, detail="bad segment")
  if filename not in ALLOWED_FILES:
    raise HTTPException(status_code=400, detail="bad filename")

  if not _verify_sig(device_id, x_carrot_ts, x_carrot_sig):
    raise HTTPException(status_code=401, detail="bad signature")

  global _upload_counter
  _upload_counter += 1
  if _upload_counter % CLEANUP_EVERY_N == 0:
    try:
      _cleanup_if_needed()
    except Exception as e:
      print(f"[cleanup] error: {e}", flush=True)

  # Phase 7: car/<car_key>/<route_id>/... canonical storage.
  # car_key determined from X-Carrot-Car header (device metadata) at first
  # file. If header is empty, file lands under UNKNOWN_CAR. When route_meta
  # arrives later with a different car_key in the JSON body, we DON'T move
  # the dir (would risk mid-route splits) — just log the mismatch.
  car_key = _norm_car_key(x_carrot_car) or "UNKNOWN_CAR"

  route_dir = BY_CAR / car_key / route_id
  seg_dir = route_dir if segment == "meta" else route_dir / segment
  seg_dir.mkdir(parents=True, exist_ok=True)
  dest = seg_dir / filename
  tmp = dest.with_suffix(dest.suffix + ".part")

  # Real client IP behind Cloudflare Tunnel (request.client is the tunnel).
  client_ip = request.headers.get("cf-connecting-ip") or (
    request.client.host if request.client else "")

  global _inflight
  _inflight += 1
  total = 0
  try:
    with tmp.open("wb") as f:
      async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
          tmp.unlink(missing_ok=True)
          raise HTTPException(status_code=413, detail="too large")
        f.write(chunk)
    os.replace(tmp, dest)
  except HTTPException:
    raise
  except Exception as e:
    tmp.unlink(missing_ok=True)
    raise HTTPException(status_code=500, detail=f"write failed: {e}")
  finally:
    _inflight -= 1

  RECENT_UPLOADS.append({
    "ts": time.time(), "device_id": device_id, "car": car_key,
    "ip": client_ip, "bytes": total, "file": filename,
  })

  # When route_meta arrives, sanity-check car_key against meta. Mismatch is
  # informational only — folder stays where it was first placed.
  if filename == "route_meta.json":
    try:
      meta = _read_json(dest)
      meta_car = _car_key_from_meta(route_dir, meta)
      if meta_car and meta_car != car_key:
        print(f"[upload] car_key mismatch route={route_id} header={car_key} meta={meta_car}",
              flush=True)
    except Exception:
      pass

  return JSONResponse({
    "ok": True,
    "stored": str(dest.relative_to(BASE)),
    "bytes": total,
    "disk_pct": round(_disk_used_pct(), 1),
  })


# ─── OTA model distribution endpoints ───────────────────────────────────────
# Flow: PC trains → publishes via POST → devices poll GET /latest → download.

@app.post("/api/models/upload/{car}/{kind}")
async def upload_model(
  car: str,
  kind: str,
  request: Request,
  x_carrot_ts: str = Header(default=""),
  x_carrot_sig: str = Header(default=""),
):
  if not CAR_RE.match(car):
    raise HTTPException(status_code=400, detail="bad car")
  if not KIND_RE.match(kind):
    raise HTTPException(status_code=400, detail="bad kind")
  # Sign message: "model|<ts>" with the same shared secret used for uploads.
  if not _verify_sig("model", x_carrot_ts, x_carrot_sig):
    raise HTTPException(status_code=401, detail="bad signature")

  # Read body with hard size cap (models are tiny).
  body = b""
  async for chunk in request.stream():
    body += chunk
    if len(body) > MAX_MODEL_BYTES:
      raise HTTPException(status_code=413, detail="model too large")
  if not body:
    raise HTTPException(status_code=400, detail="empty body")

  # Parse JSON and validate it looks like a CAS model.
  try:
    meta = json.loads(body.decode("utf-8"))
  except Exception:
    raise HTTPException(status_code=400, detail="not valid JSON")
  if not isinstance(meta, dict):
    raise HTTPException(status_code=400, detail="not a JSON object")
  required = ("input_size", "layers", "feature_schema")
  missing = [k for k in required if k not in meta]
  if missing:
    raise HTTPException(status_code=400, detail=f"not a CAS model (missing: {missing})")

  trained_at = str(meta.get("trained_at", ""))
  version = _version_from_trained_at(trained_at)
  sha = hashlib.sha256(body).hexdigest()

  model_dir = MODELS_BASE / car / kind
  model_dir.mkdir(parents=True, exist_ok=True)
  dest = model_dir / f"{version}.json"
  tmp = dest.with_suffix(dest.suffix + ".part")
  try:
    tmp.write_bytes(body)
    os.replace(tmp, dest)
  except Exception as e:
    tmp.unlink(missing_ok=True)
    raise HTTPException(status_code=500, detail=f"write failed: {e}")

  latest = {
    "version":          version,
    "sha256":           sha,
    "size":             len(body),
    "trained_at":       trained_at,
    "trained_on_hours": float(meta.get("trained_on_hours", 0.0) or 0.0),
    "alpha_max":        float(meta.get("alpha_max", 0.0) or 0.0),
    "car":              str(meta.get("car", "")),
    "model_type":       str(meta.get("model_type", "")),
    "eps_firmware_hash": str(meta.get("eps_firmware_hash", "")),
    "stored_at":        int(time.time()),
    "download_url":     f"/api/models/{car}/{kind}/download/{version}",
  }
  _write_json_atomic(model_dir / "latest.json", latest)
  return JSONResponse({"ok": True, "version": version, "sha256": sha, "size": len(body)})


@app.get("/api/models/{car}/{kind}/latest")
async def model_latest(car: str, kind: str, authorization: str = Header(default="")):
  _require_read_auth(authorization)
  if not CAR_RE.match(car):
    raise HTTPException(status_code=400, detail="bad car")
  if not KIND_RE.match(kind):
    raise HTTPException(status_code=400, detail="bad kind")
  latest_path = MODELS_BASE / car / kind / "latest.json"
  if not latest_path.exists():
    raise HTTPException(status_code=404, detail="no model published")
  return JSONResponse(_read_json(latest_path))


@app.get("/api/models/{car}/{kind}/download/{version}")
async def model_download(car: str, kind: str, version: str,
                         authorization: str = Header(default="")):
  _require_read_auth(authorization)
  if not CAR_RE.match(car):
    raise HTTPException(status_code=400, detail="bad car")
  if not KIND_RE.match(kind):
    raise HTTPException(status_code=400, detail="bad kind")
  if not VERSION_RE.match(version):
    raise HTTPException(status_code=400, detail="bad version")
  p = MODELS_BASE / car / kind / f"{version}.json"
  if not p.exists():
    raise HTTPException(status_code=404, detail="version not found")
  return FileResponse(str(p), media_type="application/json", filename=f"{car}_{kind}_{version}.json")


@app.get("/api/models")
async def list_models(authorization: str = Header(default="")):
  """Catalog: which cars/kinds have published models."""
  _require_read_auth(authorization)
  out = []
  if MODELS_BASE.exists():
    for car_dir in sorted(MODELS_BASE.iterdir()):
      if not car_dir.is_dir():
        continue
      for kind_dir in sorted(car_dir.iterdir()):
        if not kind_dir.is_dir():
          continue
        latest = kind_dir / "latest.json"
        if not latest.exists():
          continue
        meta = _read_json(latest)
        out.append({
          "car":              car_dir.name,
          "kind":             kind_dir.name,
          "version":          meta.get("version", ""),
          "trained_on_hours": meta.get("trained_on_hours", 0.0),
          "stored_at":        meta.get("stored_at", 0),
        })
  return JSONResponse({"models": out, "count": len(out)})


# ─── live status page (htop-style, no DB, no CSS framework) ──────────────────
# /status      → tiny HTML shell that polls /status.txt every 2s in place
# /status.txt  → plain-text dump (LIVE in-memory + disk-scanned TOTAL/CAR/DEVICE)
# Open by design (public). Add _require_read_auth() later if it needs locking.

def _fmt_min(epoch) -> str:
  try:
    if not epoch:
      return "-"
    return datetime.fromtimestamp(int(float(epoch))).strftime("%Y%m%d_%H%M")
  except Exception:
    return "-"


def _fmt_uptime(sec: float) -> str:
  sec = int(sec)
  h, rem = divmod(sec, 3600)
  m = rem // 60
  return f"{h}h{m:02d}m" if h else f"{m}m"


def _age_days(version: str):
  try:
    return (datetime.now() - datetime.strptime(str(version)[:8], "%Y%m%d")).days
  except Exception:
    return None


def _model_for_car(car_key: str):
  """Most recently versioned published model across kinds, or None."""
  best = None
  cdir = MODELS_BASE / car_key
  if cdir.is_dir():
    for kind_dir in sorted(cdir.iterdir()):
      lp = kind_dir / "latest.json"
      if not lp.exists():
        continue
      m = _read_json(lp)
      v = str(m.get("version", ""))
      if best is None or v > str(best.get("version", "")):
        best = {"version": v, "size": int(m.get("size", 0) or 0), "kind": kind_dir.name}
  return best


def _live_data() -> dict:
  now = time.time()
  active: dict = {}     # (device, car) -> latest event in last 60s
  for ev in RECENT_UPLOADS:
    if now - ev["ts"] <= 60:
      active[(ev["device_id"], ev["car"])] = ev
  rows = [{
    "device": dev, "car": car, "ip": ev["ip"],
    "ago": int(now - ev["ts"]), "mb": round(ev["bytes"] / 1e6, 1),
  } for (dev, car), ev in active.items()]
  rows.sort(key=lambda r: r["ago"])
  return {"inflight": _inflight, "rows": rows}


def _disk_data() -> dict:
  """Disk-scanned totals. Cached STATUS_CACHE_SEC so the 2s page poll doesn't
  re-walk every route's meta on every request."""
  now = time.time()
  cached = _status_cache.get("data")
  if cached is not None and now - _status_cache["at"] < STATUS_CACHE_SEC:
    return cached

  cars: dict = {}                 # car_key -> {routes, segs, hours}
  devices: dict = {}              # (device_id, car_key) -> {routes, segs, hours, last}
  car_effect: dict = {}           # car_key -> (ts, cas_runtime_stats) from most recent route
  for route_dir in _iter_route_dirs():
    rec = _route_record(route_dir)
    ck = rec["car_key"] or "UNKNOWN_CAR"
    c = cars.setdefault(ck, {"routes": 0, "segs": 0, "hours": 0.0})
    c["routes"] += 1
    c["segs"] += int(rec["segment_count"])
    c["hours"] += float(rec["duration_hours"])
    did = rec["device_id"] or "?"
    d = devices.setdefault((did, ck), {"routes": 0, "segs": 0, "hours": 0.0, "last": 0})
    d["routes"] += 1
    d["segs"] += int(rec["segment_count"])
    d["hours"] += float(rec["duration_hours"])
    meta = rec.get("route_meta", {})
    try:
      ts = int(float(meta.get("route_start_ts") or meta.get("uploaded_at") or 0))
      d["last"] = max(d["last"], ts)
    except Exception:
      ts = 0
    # #3 keep the newest route's runtime effectiveness snapshot per car.
    crs = meta.get("cas_runtime_stats") or {}
    snap = crs.get("torque") or crs.get("angle") or (next(iter(crs.values()), None) if crs else None)
    if snap and ts >= car_effect.get(ck, (0, None))[0]:
      car_effect[ck] = (ts, snap)

  car_rows = []
  for ck in sorted(cars):
    c = cars[ck]
    m = _model_for_car(ck)
    version = m["version"] if (m and m.get("version")) else ""
    snap = car_effect.get(ck, (0, None))[1] or {}
    car_rows.append({
      "car": ck, "routes": c["routes"], "segs": c["segs"], "hours": round(c["hours"], 1),
      "model": version, "age_days": _age_days(version) if version else None,
      # #3 effectiveness from the most recent drive (None → '-' in UI)
      "gate": snap.get("gate_pass_pct"),
      "acc": snap.get("accuracy_pct"),
      "apply": snap.get("applied_abs_mean"),
    })
  dev_rows = [{
    "device": dev, "car": car, "routes": d["routes"], "segs": d["segs"],
    "hours": round(d["hours"], 1), "last": d["last"],
  } for (dev, car), d in devices.items()]

  data = {
    "total": {
      "cars": len(cars),
      "devices": len({dev for (dev, _c) in devices}),
      "routes": sum(c["routes"] for c in cars.values()),
      "segs": sum(c["segs"] for c in cars.values()),
      "hours": round(sum(c["hours"] for c in cars.values()), 1),
      "disk": round(_disk_used_pct(), 0),
    },
    "cars": car_rows,
    "devices": dev_rows,
  }
  _status_cache["at"] = now
  _status_cache["data"] = data
  return data


def _status_text() -> str:
  """Plain-text dump for `curl /status.txt` (default sort, no interactivity)."""
  d = _disk_data()
  last_activity = max((ev["ts"] for ev in RECENT_UPLOADS), default=0)
  live = _live_data()
  lines = [
    f"CAS upload server   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}   "
    f"(auto 2s)   uptime {_fmt_uptime(time.time() - SERVER_START)}   "
    f"last activity {_fmt_min(last_activity)}",
    "",
    f"[ LIVE ]  in-flight {live['inflight']}",
  ]
  if live["rows"]:
    lines.append(f"{'DEVICE':<12}  {'CAR':<24}  {'IP':<15}  {'AGO':>5}  {'MB':>6}")
    for r in live["rows"]:
      lines.append(f"{r['device'][:12]:<12}  {r['car'][:24]:<24}  {r['ip'][:15]:<15}  "
                   f"{str(r['ago'])+'s':>5}  {r['mb']:>6.1f}")
  else:
    lines.append("(no uploads in last 60s)")
  t = d["total"]
  lines += [
    "",
    f"[ TOTAL ]  cars {t['cars']}  devices {t['devices']}  routes {t['routes']}  "
    f"segs {t['segs']}  {t['hours']}h  disk {t['disk']:.0f}%",
    "",
    "[ BY CAR ]",
    f"{'CAR':<24}  {'ROUTES':>6}  {'SEGS':>5}  {'HOURS':>6}  {'MODEL':<14}  {'AGE':>5}  "
    f"{'GATE%':>5}  {'ACC%':>4}  {'APPLY':>6}",
  ]
  for r in sorted(d["cars"], key=lambda x: x["hours"], reverse=True):
    model = r["model"] or "(none)"
    age = "-" if r["age_days"] is None else (f"{r['age_days']}d*" if r["age_days"] > 14 else f"{r['age_days']}d")
    gate = "-" if r.get("gate") is None else f"{r['gate']:.0f}"
    acc  = "-" if r.get("acc") is None else f"{r['acc']:.0f}"
    appl = "-" if r.get("apply") is None else f"{r['apply']:.3f}"
    lines.append(f"{r['car'][:24]:<24}  {r['routes']:>6}  {r['segs']:>5}  "
                 f"{r['hours']:>6.1f}  {model[:14]:<14}  {age:>5}  "
                 f"{gate:>5}  {acc:>4}  {appl:>6}")
  lines += [
    "",
    "[ BY DEVICE ]",
    f"{'DEVICE':<12}  {'CAR':<24}  {'ROUTES':>6}  {'SEGS':>5}  {'HOURS':>6}  {'LAST UPLOAD':<13}",
  ]
  for r in sorted(d["devices"], key=lambda x: x["hours"], reverse=True):
    lines.append(f"{r['device'][:12]:<12}  {r['car'][:24]:<24}  {r['routes']:>6}  {r['segs']:>5}  "
                 f"{r['hours']:>6.1f}  {_fmt_min(r['last']):<13}")
  return "\n".join(lines) + "\n"


_STATUS_HTML = """<!doctype html>
<meta charset="utf-8">
<title>CAS status</title>
<style>
body{background:#161616;color:#c8c8c8;font-family:Consolas,'DejaVu Sans Mono',monospace;font-size:13px;margin:12px}
.hd{color:#888;margin-bottom:12px}
.cap{display:inline-block;color:#161616;font-weight:bold;padding:1px 10px;margin:8px 0 3px;border-radius:2px}
.c-live{background:#7fbf7f}.c-total{background:#6fb0ff}.c-car{background:#e0c050}.c-dev{background:#d28fd2}
.totline{margin:2px 0 14px}
table{border-collapse:collapse;margin:2px 0 18px}
th,td{border:1px solid #333;padding:2px 10px;white-space:nowrap;text-align:left}
th{background:#202020;color:#ddd;user-select:none}
th.h{cursor:pointer}
th.h:hover{color:#ffd54a}
.num{text-align:right}
tbody tr:nth-child(even){background:#1c1c1c}
tbody tr:hover{background:#2b2b2b}
.muted{color:#6e6e6e}
.stale{color:#ff6b6b}
</style>
<div id="app">loading…</div>
<script>
const SORT = {cars:{k:'hours',d:-1}, devices:{k:'hours',d:-1}};
const LIVE_COLS = [
  {k:'device',label:'DEVICE'}, {k:'car',label:'CAR'}, {k:'ip',label:'IP'},
  {k:'ago',label:'AGO',num:1,fmt:r=>r.ago+'s'}, {k:'mb',label:'MB',num:1,fmt:r=>r.mb.toFixed(1)},
];
const TOTAL_COLS = [
  {k:'cars',label:'CARS',num:1}, {k:'devices',label:'DEVICES',num:1},
  {k:'routes',label:'ROUTES',num:1}, {k:'segs',label:'SEGS',num:1},
  {k:'hours',label:'HOURS',num:1}, {k:'disk',label:'DISK',num:1,fmt:r=>r.disk+'%'},
];
const CAR_COLS = [
  {k:'car',label:'CAR',cls:r=>r.car==='UNKNOWN_CAR'?'stale':''},
  {k:'routes',label:'ROUTES',num:1}, {k:'segs',label:'SEGS',num:1},
  {k:'hours',label:'HOURS',num:1,fmt:r=>r.hours.toFixed(1)},
  {k:'model',label:'MODEL',fmt:r=>r.model||'(none)',cls:r=>r.model?'':'muted'},
  {k:'age',label:'AGE',num:1,get:r=>r.age_days==null?-1:r.age_days,
   fmt:r=>r.age_days==null?'\\u2013':(r.age_days+'d'+(r.age_days>14?'*':'')),
   cls:r=>(r.age_days!=null&&r.age_days>14)?'stale':(r.model?'':'muted')},
  // #3 on-road effectiveness (most recent drive): GATE%=engaged fraction,
  // ACC%=correction-direction accuracy, APPLY=mean |applied correction|.
  {k:'gate',label:'GATE%',num:1,get:r=>r.gate==null?-1:r.gate,
   fmt:r=>r.gate==null?'\\u2013':r.gate.toFixed(0),cls:r=>r.gate==null?'muted':''},
  {k:'acc',label:'ACC%',num:1,get:r=>r.acc==null?-1:r.acc,
   fmt:r=>r.acc==null?'\\u2013':r.acc.toFixed(0),cls:r=>r.acc==null?'muted':(r.acc<50?'stale':'')},
  {k:'apply',label:'APPLY',num:1,get:r=>r.apply==null?-1:r.apply,
   fmt:r=>r.apply==null?'\\u2013':r.apply.toFixed(3),cls:r=>r.apply==null?'muted':''},
];
const DEV_COLS = [
  {k:'device',label:'DEVICE',fmt:r=>(r.device&&r.device!=='?')?r.device:'(unknown)',
   cls:r=>(r.device&&r.device!=='?')?'':'muted'},
  {k:'car',label:'CAR',cls:r=>r.car==='UNKNOWN_CAR'?'stale':''},
  {k:'routes',label:'ROUTES',num:1}, {k:'segs',label:'SEGS',num:1},
  {k:'hours',label:'HOURS',num:1,fmt:r=>r.hours.toFixed(1)},
  {k:'last',label:'LAST UPLOAD',get:r=>r.last||0,fmt:r=>fmtLast(r.last),cls:r=>r.last?'':'muted'},
];
let DATA = null;

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmtLast(e){if(!e)return '\\u2013'; const d=new Date(e*1000); const p=n=>String(n).padStart(2,'0');
  return `${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;}

function buildTable(tbl, cols, rows, sortable){
  let sorted;
  if(sortable){
    const st=SORT[tbl], c=cols.find(x=>x.k===st.k)||cols[0];
    sorted=rows.slice().sort((a,b)=>{
      let va=c.get?c.get(a):a[c.k], vb=c.get?c.get(b):b[c.k];
      if(typeof va==='number'&&typeof vb==='number') return (va-vb)*st.d;
      return String(va).localeCompare(String(vb))*st.d;
    });
  } else { sorted=rows.slice().sort((a,b)=>a.ago-b.ago); }
  const st=SORT[tbl];
  const thead=cols.map(c=>{
    const arrow=(sortable && st.k===c.k)?(st.d<0?' \\u25be':' \\u25b4'):'';
    const klass=(c.num?'num ':'')+(sortable?'h':'');
    const attr=sortable?` data-tbl="${tbl}" data-k="${c.k}"`:'';
    return `<th class="${klass.trim()}"${attr}>${esc(c.label)}${arrow}</th>`;
  }).join('');
  const body=sorted.map(r=>'<tr>'+cols.map(c=>{
    const v=c.fmt?c.fmt(r):r[c.k];
    const klass=((c.num?'num ':'')+(c.cls?c.cls(r):'')).trim();
    return `<td class="${klass}">${esc(v)}</td>`;
  }).join('')+'</tr>').join('');
  return `<table><thead><tr>${thead}</tr></thead><tbody>${body}</tbody></table>`;
}

function render(){
  if(!DATA)return;
  let html=`<div class=hd>CAS upload server &nbsp; ${esc(DATA.server_time)} &nbsp; uptime ${esc(DATA.uptime)} &nbsp; (auto 2s) &nbsp; last activity ${esc(DATA.last_activity)}</div>`;
  html+=`<div class="cap c-live">LIVE &nbsp; in-flight ${DATA.live.inflight}</div>`;
  html+= DATA.live.rows.length ? buildTable('live',LIVE_COLS,DATA.live.rows,false)
       : '<div class=muted style="margin:4px 0 16px">(no uploads in last 60s)</div>';
  html+=`<div class="cap c-total">TOTAL</div>`+buildTable('total',TOTAL_COLS,[DATA.total],false);
  html+=`<div class="cap c-car">BY CAR</div>`+buildTable('cars',CAR_COLS,DATA.cars,true);
  html+=`<div class="cap c-dev">BY DEVICE</div>`+buildTable('devices',DEV_COLS,DATA.devices,true);
  document.getElementById('app').innerHTML=html;
  document.querySelectorAll('th.h').forEach(th=>th.onclick=()=>{
    const tb=th.dataset.tbl,k=th.dataset.k,st=SORT[tb];
    if(st.k===k)st.d*=-1; else {st.k=k; st.d=-1;}
    render();
  });
}
async function tick(){
  try{ const r=await fetch('/status.json',{cache:'no-store'}); DATA=await r.json(); render(); }
  catch(e){ document.getElementById('app').textContent='fetch error: '+e; }
}
tick(); setInterval(tick,2000);
</script>
"""


@app.get("/status.json")
async def status_json():
  d = _disk_data()
  last_activity = max((ev["ts"] for ev in RECENT_UPLOADS), default=0)
  return JSONResponse({
    "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "uptime": _fmt_uptime(time.time() - SERVER_START),
    "last_activity": _fmt_min(last_activity),
    "live": _live_data(),
    "total": d["total"],
    "cars": d["cars"],
    "devices": d["devices"],
  })


@app.get("/status.txt", response_class=PlainTextResponse)
async def status_txt():
  return PlainTextResponse(_status_text())


@app.get("/status", response_class=HTMLResponse)
async def status_page():
  return HTMLResponse(_STATUS_HTML)


@app.get("/")
async def root(request: Request):
  # The status page lives at the dedicated casstatus host's root. casroute /
  # casrouter (upload/API/alist) keep a bare root so they don't masquerade as
  # the dashboard. cloudflared forwards the original Host header by hostname.
  host = (request.headers.get("host") or "").split(":")[0].lower()
  if host.startswith("casstatus."):
    return HTMLResponse(_STATUS_HTML)
  return PlainTextResponse("carrot-upload\n")

