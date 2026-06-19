#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = ROOT / "docs/personal/settings_matrix.json"
DEFAULT_PARAM_ROOTS = (
  Path("/data/params/d"),
  Path("/data/params"),
  Path("/persist/comma/params/d"),
)
BASELINE_OWNERS = {
  "carrot",
  "fishop",
  "visualization",
  "model_manager",
  "local_network_update",
  "sunny_primitive",
}
EXTRA_KEYS = (
  "CarParams",
  "CarParamsSP",
  "CarParamsPersistent",
  "CarParamsSPPersistent",
  "CarrotLearningData",
  "CarrotLearningRecommend",
  "CarrotLearningHistory",
)


def utc_now() -> str:
  return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run_git(args: list[str]) -> str:
  import subprocess
  try:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=False, timeout=5)
  except Exception:
    return ""
  return proc.stdout.strip() if proc.returncode == 0 else ""


def load_matrix(path: Path) -> list[dict[str, Any]]:
  data = json.loads(path.read_text(encoding="utf-8"))
  rows = data.get("rows") if isinstance(data, dict) else data
  if not isinstance(rows, list):
    raise ValueError(f"invalid settings matrix: {path}")
  return [row for row in rows if isinstance(row, dict)]


def baseline_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
  selected: list[dict[str, Any]] = []
  seen: set[str] = set()
  for row in rows:
    key = row.get("current_key")
    if not isinstance(key, str) or not key:
      continue
    owner = str(row.get("owner", ""))
    if owner not in BASELINE_OWNERS:
      continue
    if key in seen:
      continue
    seen.add(key)
    selected.append(row)

  for key in EXTRA_KEYS:
    if key not in seen:
      selected.append({
        "key": key,
        "current_key": key,
        "owner": "runtime_baseline",
        "category": "runtime",
        "default": None,
        "current": {},
        "notes": "Runtime evidence included with the user's known-good tuning baseline.",
      })
      seen.add(key)

  return sorted(selected, key=lambda row: (str(row.get("owner", "")), str(row.get("category", "")), str(row.get("current_key", ""))))


def read_param_bytes(key: str, roots: list[Path]) -> tuple[Path | None, bytes | None]:
  for root in roots:
    path = root / key
    if path.is_file():
      return path, path.read_bytes()
  return None, None


def decode_value(raw: bytes | None, value_type: str) -> Any:
  if raw is None:
    return None
  if len(raw) > 2048:
    return {
      "binary": True,
      "size": len(raw),
      "sha256": hashlib.sha256(raw).hexdigest(),
    }
  text = raw.decode("utf-8", errors="replace").replace("\x00", "").strip()
  try:
    if value_type == "BOOL":
      return text.lower() in {"1", "true", "on", "yes"}
    if value_type == "INT":
      return int(float(text)) if text else 0
    if value_type == "FLOAT":
      return float(text) if text else 0.0
    if value_type == "JSON":
      return json.loads(text) if text else None
  except Exception:
    pass
  return text


def row_value_type(row: dict[str, Any]) -> str:
  current = row.get("current") if isinstance(row.get("current"), dict) else {}
  value_type = str(current.get("type", ""))
  return value_type or "STRING"


def build_baseline(matrix: Path, param_roots: list[Path]) -> dict[str, Any]:
  rows = baseline_rows(load_matrix(matrix))
  params: dict[str, Any] = {}
  for row in rows:
    key = str(row["current_key"])
    value_type = row_value_type(row)
    path, raw = read_param_bytes(key, param_roots)
    params[key] = {
      "present": raw is not None,
      "path": str(path) if path else "",
      "owner": row.get("owner", ""),
      "category": row.get("category", ""),
      "type": value_type,
      "default": row.get("default"),
      "value": decode_value(raw, value_type),
      "rawText": "" if raw is None or len(raw) > 2048 else raw.decode("utf-8", errors="replace").replace("\x00", "").strip(),
      "notes": row.get("notes", ""),
    }

  return {
    "title": "Genius Pilot Carrot tuning baseline",
    "schemaVersion": 1,
    "generatedAt": utc_now(),
    "repo": {
      "branch": run_git(["branch", "--show-current"]),
      "commit": run_git(["rev-parse", "HEAD"]),
    },
    "matrix": str(matrix),
    "paramRoots": [str(root) for root in param_roots],
    "paramCount": len(params),
    "missingCount": sum(1 for item in params.values() if not item["present"]),
    "owners": sorted(BASELINE_OWNERS),
    "params": params,
  }


def write_json(path: Path, payload: dict[str, Any], pretty: bool) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2 if pretty else None)
  tmp = path.with_suffix(path.suffix + ".tmp")
  tmp.write_text(text + "\n", encoding="utf-8")
  os.replace(tmp, path)


def self_test() -> int:
  with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    matrix = root / "settings_matrix.json"
    params_dir = root / "params"
    params_dir.mkdir()
    matrix.write_text(json.dumps({
      "rows": [
        {"key": "SpeedLimitPolicy", "current_key": "SpeedLimitPolicy", "owner": "carrot",
         "category": "speed_limit", "default": "5", "current": {"type": "INT"}},
        {"key": "SunnylinkEnabled", "current_key": "SunnylinkEnabled", "owner": "removed_cloud",
         "category": "cloud", "default": "0", "current": {"type": "BOOL"}},
      ],
    }), encoding="utf-8")
    (params_dir / "SpeedLimitPolicy").write_text("5", encoding="utf-8")
    baseline = build_baseline(matrix, [params_dir])
    params = baseline["params"]
    if params["SpeedLimitPolicy"]["value"] != 5:
      return 1
    if "SunnylinkEnabled" in params:
      return 1
    if "CarrotLearningData" not in params:
      return 1
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Export a Genius Pilot Carrot/Fishop/model/visual tuning baseline from params.")
  parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX, help="settings matrix JSON")
  parser.add_argument("--params-root", type=Path, action="append", default=[], help="param directory; may be repeated")
  parser.add_argument("--output", type=Path, help="write JSON baseline to this path")
  parser.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
  parser.add_argument("--self-test", action="store_true", help="run offline self-test")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  roots = args.params_root or list(DEFAULT_PARAM_ROOTS)
  payload = build_baseline(args.matrix, roots)
  if args.output:
    write_json(args.output, payload, args.pretty)
  print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
