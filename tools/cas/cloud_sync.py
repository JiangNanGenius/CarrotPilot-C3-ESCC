#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


MANIFEST_SCHEMA_VERSION = 1
DEFAULT_LOCAL_RAW_POLICY = "keep"
LOCAL_RAW_POLICIES = ("keep", "delete_after_success")
DEFAULT_SERVER_ENDPOINT = "https://casroute.jominki354.live"


def cas_dir(rlogs: str | Path) -> Path:
  return Path(rlogs).expanduser() / ".cas"


def local_manifest_path(rlogs: str | Path) -> Path:
  return cas_dir(rlogs) / "local_manifest.json"


def cloud_cache_dir(rlogs: str | Path) -> Path:
  return cas_dir(rlogs) / "cloud_cache"


def cloud_route_dir(rlogs: str | Path, car_key: str, route_id: str, segment: str | int) -> Path:
  # Phase 7: local cache organized by car_key (mirrors server car/ layout).
  safe_car = _safe_component(car_key, "unknown_car")
  safe_route = _safe_component(route_id, "unknown_route")
  safe_segment = _safe_component(str(segment), "0")
  return cloud_cache_dir(rlogs) / safe_car / f"{safe_route}--{safe_segment}"


def cloud_route_files(rlogs: str | Path, car_key: str, route_id: str, segment: str | int) -> dict[str, str]:
  root = cloud_route_dir(rlogs, car_key, route_id, segment)
  return {
    "rlog": str(root / "rlog.zst"),
    "qlog": str(root / "qlog.zst"),
    "route_meta": str(root / "route_meta.json"),
  }


def save_manifest(path: str | Path, manifest: dict[str, Any]):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: str | Path) -> dict[str, Any]:
  path = Path(path)
  return json.loads(path.read_text(encoding="utf-8"))


def fetch_server_manifest(endpoint: str = DEFAULT_SERVER_ENDPOINT, car_key: str = "",
                          kind: str = "", device_id: str = "", token: str = "",
                          include_routes: bool = True, timeout: float = 30.0) -> dict[str, Any]:
  query = {
    "include_routes": "true" if include_routes else "false",
  }
  if car_key:
    query["car_key"] = car_key
  if kind:
    query["kind"] = kind
  if device_id:
    query["device_id"] = device_id
  url = _join_url(endpoint, "/api/datasets")
  if query:
    url += "?" + urlencode(query)
  return _fetch_json(url, token=token, timeout=timeout)


def fetch_server_routes(endpoint: str = DEFAULT_SERVER_ENDPOINT, car_key: str = "",
                        kind: str = "", device_id: str = "", token: str = "",
                        limit: int = 500, timeout: float = 30.0) -> dict[str, Any]:
  query: dict[str, str | int] = {"limit": int(limit)}
  if car_key:
    query["car_key"] = car_key
  if kind:
    query["kind"] = kind
  if device_id:
    query["device_id"] = device_id
  return _fetch_json(_join_url(endpoint, "/api/routes") + "?" + urlencode(query), token=token, timeout=timeout)


def post_train_run(endpoint: str, payload: dict[str, Any], token: str = "", timeout: float = 30.0) -> dict[str, Any]:
  body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
  headers = _auth_headers(token)
  headers["Content-Type"] = "application/json"
  req = Request(_join_url(endpoint, "/api/train-runs"), data=body, headers=headers, method="POST")
  with urlopen(req, timeout=timeout) as response:
    return json.loads(response.read().decode("utf-8"))


def resolve_upload_secret() -> bytes:
  """Same HMAC secret the device uses (selfdrive/carrot/cas/upload_config).
  Lets PC tools re-post route_meta.json with a valid signature."""
  try:
    from openpilot.selfdrive.carrot.cas import upload_config
  except ModuleNotFoundError:
    from selfdrive.carrot.cas import upload_config
  return upload_config.resolve_secret()


def post_model(endpoint: str, car: str, kind: str, model_json_path: str | Path,
               secret: bytes, timeout: float = 60.0) -> dict[str, Any]:
  """PC publishes a trained CAS model JSON to the server. Server stores it
  under /srv/carrot_models/<car>/<kind>/<trained_at>.json and updates the
  latest pointer. Devices then pull via fetch_latest_model_info + download_model.

  HMAC signature: same shared secret as uploads, signed message is "model|<ts>".
  """
  ts = int(time.time())
  sig = hmac.new(secret, f"model|{ts}".encode("utf-8"), hashlib.sha256).hexdigest()
  with open(model_json_path, "rb") as f:
    body = f.read()
  url = _join_url(endpoint, f"/api/models/upload/{car}/{kind}")
  req = Request(url, data=body, method="POST")
  req.add_header("User-Agent", "carrot-cas-publish/1.0")
  req.add_header("X-Carrot-TS", str(ts))
  req.add_header("X-Carrot-Sig", sig)
  req.add_header("Content-Type", "application/json")
  with urlopen(req, timeout=timeout) as response:
    return json.loads(response.read().decode("utf-8"))


def fetch_latest_model_info(endpoint: str, car: str, kind: str,
                            token: str = "", timeout: float = 15.0) -> dict[str, Any]:
  """Returns {version, sha256, size, trained_at, trained_on_hours, alpha_max,
  download_url, ...} for the latest published model. Raises HTTPError(404) if
  no model published yet for this (car, kind)."""
  url = _join_url(endpoint, f"/api/models/{car}/{kind}/latest")
  req = Request(url, headers=_auth_headers(token))
  with urlopen(req, timeout=timeout) as response:
    return json.loads(response.read().decode("utf-8"))


def download_model(endpoint: str, car: str, kind: str, version: str,
                   dest_path: str | Path, token: str = "",
                   timeout: float = 60.0) -> Path:
  """Download a specific model version to dest_path (atomic via .part rename)."""
  url = _join_url(endpoint, f"/api/models/{car}/{kind}/download/{version}")
  req = Request(url, headers=_auth_headers(token))
  dest = Path(dest_path)
  dest.parent.mkdir(parents=True, exist_ok=True)
  tmp = dest.with_suffix(dest.suffix + ".part")
  try:
    with urlopen(req, timeout=timeout) as response, open(tmp, "wb") as f:
      while True:
        chunk = response.read(1024 * 1024)
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
  return dest


def post_route_meta(endpoint: str, device_id: str, route_id: str, meta: dict[str, Any],
                    secret: bytes, timeout: float = 30.0) -> dict[str, Any]:
  """Overwrite a route's route_meta.json on the server. The upload handler
  recomputes car_key from the new meta and re-bins the route (UNKNOWN → real
  car). rlog/qlog files are NOT touched — only the small JSON is sent.

  This is the PC-side backfill path for routes the device uploaded before it
  had identified the car (empty CarName/CarParams → UNKNOWN bucket)."""
  ts = int(time.time())
  sig = hmac.new(secret, f"{device_id}|{ts}".encode("utf-8"), hashlib.sha256).hexdigest()
  body = json.dumps(meta, ensure_ascii=False).encode("utf-8")
  url = _join_url(endpoint, f"/upload/{device_id}/{route_id}/meta/route_meta.json")
  req = Request(url, data=body, method="POST")
  req.add_header("User-Agent", "carrot-cas-backfill/1.0")
  req.add_header("X-Carrot-TS", str(ts))
  req.add_header("X-Carrot-Sig", sig)
  car_hdr = str(meta.get("car_key") or meta.get("car_name_raw") or "").strip()
  if car_hdr:
    req.add_header("X-Carrot-Car", car_hdr)
  req.add_header("Content-Type", "application/octet-stream")
  with urlopen(req, timeout=timeout) as response:
    raw = response.read().decode("utf-8", "ignore")
    return json.loads(raw) if raw else {}


def download_cloud_file(endpoint: str, download_url: str, dest: str | Path,
                        token: str = "", timeout: float = 120.0) -> Path:
  dest_path = Path(dest)
  dest_path.parent.mkdir(parents=True, exist_ok=True)
  tmp = dest_path.with_suffix(dest_path.suffix + ".part")
  req = Request(_join_url(endpoint, download_url), headers=_auth_headers(token))
  try:
    with urlopen(req, timeout=timeout) as response, open(tmp, "wb") as f:
      while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
          break
        f.write(chunk)
    tmp.replace(dest_path)
  except (HTTPError, URLError, OSError):
    try:
      tmp.unlink(missing_ok=True)
    except OSError:
      pass
    raise
  return dest_path


def download_segment(endpoint: str, rlogs: str | Path, car_key: str, route_id: str,
                     segment: str | int, filenames: tuple[str, ...] = ("rlog.zst", "qlog.zst"),
                     token: str = "") -> dict[str, str]:
  # Phase 7: download URL + local cache keyed by car_key (was device_id).
  files = cloud_route_files(rlogs, car_key, route_id, segment)
  written = {}
  for filename in filenames:
    key = filename.split(".", 1)[0]
    dest = files.get(key)
    if not dest:
      continue
    url = f"/download/{car_key}/{route_id}/{segment}/{filename}"
    written[filename] = str(download_cloud_file(endpoint, url, dest, token=token))
  return written


def build_local_manifest(index: dict[str, Any], train_runs: dict[str, Any] | None = None,
                         raw_policy: str = DEFAULT_LOCAL_RAW_POLICY) -> dict[str, Any]:
  if raw_policy not in LOCAL_RAW_POLICIES:
    raw_policy = DEFAULT_LOCAL_RAW_POLICY

  train_summary = _summarize_train_runs(train_runs or {})
  datasets: dict[tuple[str, str], dict[str, Any]] = {}
  routes_by_dataset: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
  eps_by_dataset: dict[tuple[str, str], set[str]] = defaultdict(set)

  for source, meta in (index.get("logs", {}) or {}).items():
    car_key = str(meta.get("car", "")).strip()
    if not car_key:
      continue
    kind = str(meta.get("kind", "")).strip() or "torque"
    eps_hash = str(meta.get("eps_firmware_hash", "")).strip()
    route_id, segment = route_segment_from_source(source)
    duration_hours = float(meta.get("duration_hours", 0.0) or 0.0)
    dataset_key = (car_key, kind)

    dataset = datasets.setdefault(dataset_key, {
      "dataset_key": dataset_id(car_key, kind),
      "car_key": car_key,
      "kind": kind,
      "source": "local",
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
    if eps_hash:
      eps_by_dataset[dataset_key].add(eps_hash)

    route_key = route_id or f"source:{source}"
    route = routes_by_dataset[dataset_key].setdefault(route_key, {
      "route_id": route_id,
      "segments": [],
      "summary": {
        "segment_count": 0,
        "source_count": 0,
        "total_hours": 0.0,
      },
    })
    route["segments"].append({
      "segment": segment,
      "source": source,
      "duration_hours": duration_hours,
      "complete": not bool(meta.get("error")),
      "eps_firmware_hash": eps_hash,
    })
    route["summary"]["segment_count"] += 1 if segment != "" else 0
    route["summary"]["source_count"] += 1
    route["summary"]["total_hours"] += duration_hours

    summary = dataset["summary"]
    summary["segment_count"] += 1 if segment != "" else 0
    summary["source_count"] += 1
    summary["total_hours"] += duration_hours

  for key, dataset in datasets.items():
    car_key, kind = key
    routes = list(routes_by_dataset[key].values())
    routes.sort(key=lambda item: str(item.get("route_id", "")))
    dataset["routes"] = routes
    dataset["eps_firmware_hashes"] = sorted(eps_by_dataset[key])
    dataset["summary"]["route_count"] = len({str(route.get("route_id", "")) for route in routes if route.get("route_id")})
    history = train_summary.get(dataset_id(car_key, kind), {})
    dataset["summary"]["trained_hours"] = float(history.get("trained_hours", 0.0) or 0.0)
    dataset["summary"]["train_run_count"] = int(history.get("run_count", 0) or 0)
    dataset["summary"]["new_hours"] = max(0.0, float(dataset["summary"]["total_hours"]) - float(dataset["summary"]["trained_hours"]))
    dataset["summary"]["total_hours"] = round(float(dataset["summary"]["total_hours"]), 4)
    dataset["summary"]["trained_hours"] = round(float(dataset["summary"]["trained_hours"]), 4)
    dataset["summary"]["new_hours"] = round(float(dataset["summary"]["new_hours"]), 4)

  dataset_list = sorted(datasets.values(), key=lambda item: (item["car_key"], item["kind"]))
  total_hours = sum(float(item["summary"]["total_hours"]) for item in dataset_list)
  return {
    "version": MANIFEST_SCHEMA_VERSION,
    "source": "local",
    "created_at": datetime.now().isoformat(timespec="seconds"),
    "raw_policy": raw_policy,
    "datasets": dataset_list,
    "summary": {
      "dataset_count": len(dataset_list),
      "route_count": sum(int(item["summary"]["route_count"]) for item in dataset_list),
      "segment_count": sum(int(item["summary"]["segment_count"]) for item in dataset_list),
      "source_count": sum(int(item["summary"]["source_count"]) for item in dataset_list),
      "total_hours": round(total_hours, 4),
    },
  }


def route_segment_from_source(source: str) -> tuple[str, str]:
  segment_name = Path(source).parent.name
  if "--" not in segment_name:
    return "", ""
  route_id, segment = segment_name.rsplit("--", 1)
  return route_id, segment


def dataset_id(car_key: str, kind: str) -> str:
  return f"{car_key}/{kind}"


def _safe_component(value: str, fallback: str) -> str:
  safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in value.strip())
  return safe.strip("_") or fallback


def _summarize_train_runs(train_runs: dict[str, Any]) -> dict[str, dict[str, Any]]:
  summary = {}
  for run in train_runs.get("runs", []) or []:
    car_key = str(run.get("car_key") or run.get("car") or "").strip()
    kind = str(run.get("kind") or "torque").strip() or "torque"
    if not car_key:
      continue
    key = dataset_id(car_key, kind)
    item = summary.setdefault(key, {"trained_hours": 0.0, "run_count": 0, "latest_at": ""})
    item["trained_hours"] = max(float(item["trained_hours"]), float(run.get("trained_on_hours", 0.0) or 0.0))
    item["run_count"] = int(item["run_count"]) + 1
    created_at = str(run.get("created_at", ""))
    if created_at >= str(item.get("latest_at", "")):
      item["latest_at"] = created_at
  return summary


def _fetch_json(url: str, token: str = "", timeout: float = 30.0) -> dict[str, Any]:
  req = Request(url, headers=_auth_headers(token))
  with urlopen(req, timeout=timeout) as response:
    return json.loads(response.read().decode("utf-8"))


def _auth_headers(token: str) -> dict[str, str]:
  headers = {"User-Agent": "cas-training-tools/1"}
  if token:
    headers["Authorization"] = f"Bearer {token}"
  return headers


def _join_url(endpoint: str, path: str) -> str:
  return urljoin(endpoint.rstrip("/") + "/", path.lstrip("/"))
