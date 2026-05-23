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
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse


SECRET_PATH = Path("/etc/carrot-upload/secret")
READ_TOKEN_PATH = Path("/etc/carrot-upload/read_token")
BASE = Path("/srv/carrot_rlogs")
# Phase 6 folder structure: device/ (canonical raw), car/ (per-platform view),
# model/ (OTA-distributable trained models). Names match the cas_server_
# operations.md doc. BY_DEVICE/BY_CAR variable names kept for diff continuity.
BY_DEVICE   = BASE / "device"                                # was "by-device"
BY_CAR      = BASE / "car"                                   # was "by-car"
MODELS_BASE = BASE / "model"                                 # was Path("/srv/carrot_models")
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


def car_links_for(route_dir: Path):
  if not BY_CAR.exists():
    return
  device_id = route_dir.parent.name
  route_id = route_dir.name
  link_name = f"{device_id}__{route_id}"
  for car_dir in BY_CAR.iterdir():
    if not car_dir.is_dir():
      continue
    link = car_dir / link_name
    if link.is_symlink() or link.exists():
      try:
        link.unlink()
      except OSError:
        pass


def _ensure_car_symlink(route_dir: Path, car: str):
  if not car or not CAR_RE.match(car):
    return
  car_dir = BY_CAR / car
  car_dir.mkdir(parents=True, exist_ok=True)
  link_name = f"{route_dir.parent.name}__{route_dir.name}"
  link = car_dir / link_name
  if link.is_symlink() or link.exists():
    return
  try:
    rel = os.path.relpath(route_dir, car_dir)
    link.symlink_to(rel)
  except OSError as e:
    print(f"[symlink] failed {link} -> {route_dir}: {e}", flush=True)


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
  meta = _read_json(route_dir / "route_meta.json")
  if "device_id" not in meta:
    meta["device_id"] = route_dir.parent.name
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
  if not BY_DEVICE.exists():
    return
  for device_dir in sorted(BY_DEVICE.iterdir(), key=lambda p: p.name):
    if not device_dir.is_dir():
      continue
    for route_dir in sorted(device_dir.iterdir(), key=lambda p: p.name):
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
  meta = _route_meta(route_dir)
  device_id = str(meta.get("device_id", route_dir.parent.name))
  route_id = str(meta.get("route_id", route_dir.name))
  car_key = _car_key_from_meta(route_dir, meta)
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
          "download_url": f"/download/{device_id}/{route_id}/{seg_dir.name}/{filename}",
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


@app.get("/download/{device_id}/{route_id}/{segment}/{filename}")
async def download(
  device_id: str,
  route_id: str,
  segment: str,
  filename: str,
  authorization: str = Header(default=""),
):
  _require_read_auth(authorization)
  if not DEVICE_RE.match(device_id):
    raise HTTPException(status_code=400, detail="bad device_id")
  if not ROUTE_RE.match(route_id):
    raise HTTPException(status_code=400, detail="bad route_id")
  if not SEGMENT_RE.match(segment):
    raise HTTPException(status_code=400, detail="bad segment")
  if filename not in DOWNLOAD_FILES:
    raise HTTPException(status_code=400, detail="bad filename")
  root = BY_DEVICE / device_id / route_id
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

  route_dir = BY_DEVICE / device_id / route_id
  seg_dir = route_dir if segment == "meta" else route_dir / segment
  seg_dir.mkdir(parents=True, exist_ok=True)
  dest = seg_dir / filename
  tmp = dest.with_suffix(dest.suffix + ".part")

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

  car_file = route_dir / "car.txt"
  car_for_link = _norm_car_key(x_carrot_car)
  if filename == "route_meta.json":
    meta = _read_json(dest)
    car_for_link = _car_key_from_meta(route_dir, meta) or car_for_link
  if car_for_link and not car_file.exists():
    try:
      car_file.write_text(car_for_link, encoding="utf-8")
    except OSError:
      pass
  if not car_for_link and car_file.exists():
    try:
      car_for_link = _norm_car_key(car_file.read_text(encoding="utf-8").strip())
    except OSError:
      car_for_link = ""
  _ensure_car_symlink(route_dir, car_for_link)

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

