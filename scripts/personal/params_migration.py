#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = ROOT / "selfdrive/carrot_settings.json"
DEFAULT_PARAM_ROOTS = [
  Path("/data/params/d"),
  Path("/data/params"),
  Path("/persist/comma/params/d"),
]

SAFE_EXTRA_KEYS = {
  "EnableConnect",
}

SENSITIVE_RE = re.compile(
  r"(token|password|secret|private|dongle|github|athena|ssh|api[_-]?key|oauth|credential|email|account)",
  re.I,
)


class MigrationError(Exception):
  pass


def run(cmd: Sequence[str]) -> str:
  proc = subprocess.run(
    list(cmd),
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def git_meta() -> Dict[str, str]:
  return {
    "branch": run(["git", "branch", "--show-current"]),
    "commit": run(["git", "rev-parse", "HEAD"]),
    "commit_short": run(["git", "rev-parse", "--short=10", "HEAD"]),
  }


def load_setting_specs(settings_file: Path) -> Dict[str, Dict[str, object]]:
  try:
    data = json.loads(settings_file.read_text(encoding="utf-8"))
  except Exception as exc:
    raise MigrationError(f"cannot read settings file {settings_file}: {exc}") from exc
  params = data.get("params", [])
  if not isinstance(params, list):
    raise MigrationError("settings file must contain a params list")
  specs: Dict[str, Dict[str, object]] = {}
  for item in params:
    if not isinstance(item, dict):
      continue
    name = str(item.get("name", "")).strip()
    if name:
      specs[name] = item
  return specs


def safe_key_names(specs: Dict[str, Dict[str, object]], extra_keys: Iterable[str]) -> List[str]:
  names = set(specs.keys()) | set(extra_keys)
  return sorted(name for name in names if name and not SENSITIVE_RE.search(name))


def normalize_value(data: bytes) -> str:
  try:
    text = data.decode("utf-8", errors="strict")
  except UnicodeDecodeError:
    digest = hashlib.sha256(data).hexdigest()[:16]
    raise MigrationError(f"binary value is not safe to migrate automatically: sha256:{digest}")
  return text.replace("\x00", "").strip()


def param_roots_from_args(args: argparse.Namespace) -> List[Path]:
  if args.param_root:
    return [Path(path) for path in args.param_root]
  return DEFAULT_PARAM_ROOTS


class ParamStore:
  def __init__(self, roots: Sequence[Path], *, use_params_api: bool = True) -> None:
    self.roots = list(roots)
    self.params = None
    if use_params_api:
      try:
        from openpilot.common.params import Params  # type: ignore
        self.params = Params()
      except Exception:
        self.params = None

  def _path_for_read(self, key: str) -> Optional[Path]:
    for root in self.roots:
      path = root / key
      if path.exists() and path.is_file():
        return path
    return None

  def _path_for_write(self, key: str) -> Path:
    root = self.roots[0]
    root.mkdir(parents=True, exist_ok=True)
    return root / key

  def get(self, key: str) -> Optional[str]:
    if self.params is not None:
      try:
        value = self.params.get(key, block=False, return_default=False)
      except TypeError:
        try:
          value = self.params.get(key)
        except Exception:
          value = None
      except Exception:
        value = None
      if value is not None:
        if isinstance(value, str):
          return value.strip()
        if isinstance(value, (bytes, bytearray, memoryview)):
          return normalize_value(bytes(value))
        return str(value).strip()

    path = self._path_for_read(key)
    if path is None:
      return None
    return normalize_value(path.read_bytes())

  def put(self, key: str, value: str) -> None:
    if self.params is not None:
      try:
        self.params.put(key, value)
        return
      except Exception:
        pass
    self._path_for_write(key).write_text(value, encoding="utf-8")


def validate_export_value(name: str, value: str, spec: Dict[str, object]) -> Optional[str]:
  if value == "":
    return None
  if "min" not in spec and "max" not in spec:
    return None
  try:
    number = float(value)
  except ValueError:
    return f"{name}: non-numeric value {value!r} for ranged setting"
  min_value = spec.get("min")
  max_value = spec.get("max")
  try:
    if min_value is not None and number < float(min_value):
      return f"{name}: {value} is below min {min_value}"
    if max_value is not None and number > float(max_value):
      return f"{name}: {value} is above max {max_value}"
  except Exception:
    return None
  return None


def build_export(args: argparse.Namespace) -> Dict[str, object]:
  settings_file = Path(args.settings_file)
  specs = load_setting_specs(settings_file)
  keys = safe_key_names(specs, SAFE_EXTRA_KEYS)
  if args.key:
    requested = set(args.key)
    keys = [key for key in keys if key in requested]

  store = ParamStore(param_roots_from_args(args), use_params_api=not bool(args.param_root))
  params: Dict[str, Dict[str, object]] = {}
  warnings: List[str] = []
  skipped: List[str] = []

  for key in keys:
    value = store.get(key)
    spec = specs.get(key, {})
    if value is None:
      if args.include_missing:
        params[key] = {
          "value": None,
          "default": spec.get("default"),
          "title": spec.get("ctitle") or spec.get("etitle") or spec.get("title"),
        }
      else:
        skipped.append(key)
      continue
    warning = validate_export_value(key, value, spec)
    if warning:
      warnings.append(warning)
    params[key] = {
      "value": value,
      "default": spec.get("default"),
      "min": spec.get("min"),
      "max": spec.get("max"),
      "unit": spec.get("unit"),
      "title": spec.get("ctitle") or spec.get("etitle") or spec.get("title"),
    }

  return {
    "schema": "carrotpilot-personal-params-migration-v1",
    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "source": {
      "settings_file": str(settings_file),
      "git": git_meta(),
    },
    "privacy": {
      "policy": "Only setting whitelist keys are exported. Token/account/device identity keys are filtered.",
      "sensitive_filter": SENSITIVE_RE.pattern,
    },
    "params": params,
    "warnings": warnings,
    "skipped_missing": skipped,
  }


def print_export_summary(data: Dict[str, object], output: Path) -> None:
  params = data.get("params", {})
  warnings = data.get("warnings", [])
  skipped = data.get("skipped_missing", [])
  print("Personal params migration export")
  print("output:", output)
  print("exported keys:", len(params) if isinstance(params, dict) else 0)
  print("missing skipped:", len(skipped) if isinstance(skipped, list) else 0)
  if isinstance(warnings, list) and warnings:
    print("warnings:")
    for warning in warnings:
      print("-", warning)
  print("OK: export written")


def load_export(path: Path) -> Dict[str, object]:
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except Exception as exc:
    raise MigrationError(f"cannot read export {path}: {exc}") from exc
  if data.get("schema") != "carrotpilot-personal-params-migration-v1":
    raise MigrationError("unsupported migration export schema")
  params = data.get("params")
  if not isinstance(params, dict):
    raise MigrationError("migration export must contain a params object")
  return data


def import_params(args: argparse.Namespace) -> int:
  settings_file = Path(args.settings_file)
  specs = load_setting_specs(settings_file)
  allowed = set(safe_key_names(specs, SAFE_EXTRA_KEYS))
  data = load_export(Path(args.input))
  exported = data["params"]
  assert isinstance(exported, dict)

  store = ParamStore(param_roots_from_args(args), use_params_api=not bool(args.param_root))
  changes: List[Tuple[str, Optional[str], str]] = []
  skipped: List[str] = []
  warnings: List[str] = []

  for key, item in exported.items():
    if not isinstance(item, dict):
      skipped.append(f"{key}: malformed item")
      continue
    if key not in allowed and not args.allow_unknown:
      skipped.append(f"{key}: not in current safe whitelist")
      continue
    value = item.get("value")
    if value is None:
      skipped.append(f"{key}: missing value in export")
      continue
    value_text = str(value).strip()
    spec = specs.get(key, {})
    warning = validate_export_value(key, value_text, spec)
    if warning:
      warnings.append(warning)
      if not args.ignore_range_warnings:
        skipped.append(f"{key}: range validation failed")
        continue
    current = store.get(key)
    if current != value_text:
      changes.append((key, current, value_text))

  print("Personal params migration import")
  print("input:", args.input)
  print("settings:", settings_file)
  print("mode:", "apply" if args.apply else "dry-run")
  print("changes:", len(changes))
  for key, current, value in changes:
    current_display = "<missing>" if current is None else current
    print(f"- {key}: {current_display!r} -> {value!r}")
  if skipped:
    print("skipped:")
    for item in skipped:
      print("-", item)
  if warnings:
    print("warnings:")
    for item in warnings:
      print("-", item)

  if args.apply:
    for key, _current, value in changes:
      store.put(key, value)
    print("OK: applied", len(changes), "change(s)")
  else:
    print("OK: dry-run only; rerun with --apply to write params")
  return 0


def self_test() -> int:
  with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    settings = tmp_path / "carrot_settings.json"
    settings.write_text(json.dumps({
      "params": [
        {"name": "EnableEscc", "default": 0, "min": 0, "max": 1, "ctitle": "ESCC"},
        {"name": "CruiseMaxVals1", "default": 60, "min": 10, "max": 200, "ctitle": "speed"},
        {"name": "GithubToken", "default": "", "ctitle": "secret"},
      ]
    }), encoding="utf-8")
    root = tmp_path / "params"
    root.mkdir()
    (root / "EnableEscc").write_text("1", encoding="utf-8")
    (root / "CruiseMaxVals1").write_text("88", encoding="utf-8")
    (root / "GithubToken").write_text("should-not-export", encoding="utf-8")
    export = tmp_path / "export.json"

    ns = argparse.Namespace(
      settings_file=str(settings),
      param_root=[str(root)],
      key=None,
      include_missing=False,
    )
    data = build_export(ns)
    params = data["params"]
    assert isinstance(params, dict)
    if "EnableEscc" not in params or "CruiseMaxVals1" not in params:
      raise MigrationError("self-test export missed safe keys")
    if "GithubToken" in params:
      raise MigrationError("self-test exported a sensitive key")
    export.write_text(json.dumps(data), encoding="utf-8")

    apply_root = tmp_path / "apply_params"
    apply_root.mkdir()
    code = import_params(argparse.Namespace(
      input=str(export),
      settings_file=str(settings),
      param_root=[str(apply_root)],
      allow_unknown=False,
      ignore_range_warnings=False,
      apply=False,
    ))
    if code != 0:
      return code
  print("OK: params migration self-test passed")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Export/import a safe personal CarrotPilot params whitelist.")
  parser.add_argument("--settings-file", default=str(DEFAULT_SETTINGS), help="carrot_settings.json used to build the safe settings whitelist")
  parser.add_argument("--param-root", action="append", help="params directory to read/write; may be repeated")
  sub = parser.add_subparsers(dest="cmd", required=True)

  export_parser = sub.add_parser("export", help="export safe setting params to JSON")
  export_parser.add_argument("--output", required=True, help="output JSON path")
  export_parser.add_argument("--key", action="append", help="limit export to a specific key; may be repeated")
  export_parser.add_argument("--include-missing", action="store_true", help="include whitelist keys that have no stored value")

  import_parser = sub.add_parser("import", help="import safe setting params from JSON")
  import_parser.add_argument("--input", required=True, help="export JSON path")
  import_parser.add_argument("--allow-unknown", action="store_true", help="allow keys not present in the current settings whitelist")
  import_parser.add_argument("--ignore-range-warnings", action="store_true", help="apply values even if range validation warns")
  import_parser.add_argument("--apply", action="store_true", help="write params; omitted means dry-run only")

  sub.add_parser("self-test", help="run local self-test without touching device params")
  args = parser.parse_args()

  try:
    if args.cmd == "export":
      data = build_export(args)
      output = Path(args.output)
      output.parent.mkdir(parents=True, exist_ok=True)
      output.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
      print_export_summary(data, output)
      return 0
    if args.cmd == "import":
      return import_params(args)
    if args.cmd == "self-test":
      return self_test()
    raise MigrationError("unknown command")
  except MigrationError as exc:
    print("params migration failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
