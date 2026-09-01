"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import json
import os
import re
from pathlib import Path

from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.selfdrive.car.sync_car_list_param import CAR_LIST_JSON_OUT

ONROAD_BRIGHTNESS_MIGRATION_VERSION: str = "1.0"
ONROAD_BRIGHTNESS_TIMER_MIGRATION_VERSION: str = "1.0"
LEGACY_CARROT_PARAMS_MIGRATION_MARKER = ".legacy_carrot_params_migrated_v1"
CARROT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "selfdrive" / "carrot_settings.json"
LEGACY_CARROT_EXTRA_KEYS = {"ShareData"}
CARROT_NATIVE_OVERLAP_KEYS = {"CarrotSpeedLimitEnable", "CarrotTrafficStopEnable"}

_SAFE_PARAM_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SENSITIVE_PARAM_NAME_RE = re.compile(
  r"token|password|secret|private|dongle|github|athena|ssh|oauth|credential|email|account|" +
  r"api[_-]?key|mapbox.*key|gmapkey|access[_-]?key",
  re.IGNORECASE,
)

# index → seconds mapping for OnroadScreenOffTimer (SSoT)
ONROAD_BRIGHTNESS_TIMER_VALUES = {0: 3, 1: 5, 2: 7, 3: 10, 4: 15, 5: 30, **{i: (i - 5) * 60 for i in range(6, 16)}}
VALID_TIMER_VALUES = set(ONROAD_BRIGHTNESS_TIMER_VALUES.values())


def _legacy_carrot_param_whitelist(_params, settings_path: Path) -> set[str]:
  with settings_path.open(encoding="utf-8") as f:
    settings = json.load(f)

  native_keys = {
    key.decode("utf-8") if isinstance(key, bytes) else str(key)
    for key in _params.all_keys()
  }
  declared_keys = {
    name
    for item in settings.get("params", [])
    if isinstance(item, dict) and isinstance((name := item.get("name")), str)
  }
  return {
    name for name in declared_keys | LEGACY_CARROT_EXTRA_KEYS
    if _SAFE_PARAM_NAME_RE.fullmatch(name)
    and not _SENSITIVE_PARAM_NAME_RE.search(name)
    and (name not in native_keys or name in CARROT_NATIVE_OVERLAP_KEYS)
  }


def _write_new_raw_param(path: Path, data: bytes) -> bool:
  """Atomically claim and write a new raw param without replacing a target."""
  try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
  except FileExistsError:
    return False

  try:
    with os.fdopen(fd, "wb") as f:
      f.write(data)
      f.flush()
      os.fsync(f.fileno())
  except Exception:
    try:
      path.unlink()
    except OSError:
      pass
    raise
  return True


def migrate_legacy_carrot_params(_params, *, settings_path: Path = CARROT_SETTINGS_PATH) -> int:
  """Copy legacy Carrot-owned raw params before native Params clears unknown keys.

  The old branch stored Carrot values in the native raw params directory. The
  current branch keeps them in a sibling ``*_carrot`` namespace. Only keys
  declared by carrot_settings.json, not sensitive, and not native-owned are
  eligible, apart from the explicit Carrot-runtime overlap keys. Existing
  target values always win.
  """
  copied = 0
  try:
    source_dir = Path(_params.get_param_path())
    carrot_dir = source_dir.with_name(f"{source_dir.name}_carrot")
    marker = carrot_dir / LEGACY_CARROT_PARAMS_MIGRATION_MARKER
    if marker.exists():
      return 0

    whitelist = _legacy_carrot_param_whitelist(_params, Path(settings_path))
    carrot_dir.mkdir(parents=True, exist_ok=True)

    had_errors = False
    for key in sorted(whitelist):
      source = source_dir / key
      target = carrot_dir / key
      if target.exists() or not source.is_file() or source.is_symlink():
        continue

      try:
        if _write_new_raw_param(target, source.read_bytes()):
          copied += 1
      except Exception:
        had_errors = True
        cloudlog.exception(f"params_migration: failed copying legacy Carrot param {key}")

    if not had_errors:
      _write_new_raw_param(marker, b"1\n")
      cloudlog.info(f"params_migration: migrated {copied} legacy Carrot params")
  except Exception:
    # This runs before manager's normal param cleanup and must never block boot.
    cloudlog.exception("params_migration: legacy Carrot param migration failed")

  return copied


def _migrate_car_platform_bundle(_params):
  bundle = _params.get("CarPlatformBundle")
  if bundle is None:
    return

  old_platform = bundle.get("platform")
  if not old_platform:
    return

  from opendbc.car.fingerprints import MIGRATION  # lazy: avoids heavy import at module level
  if old_platform not in MIGRATION:
    return

  new_platform = str(MIGRATION[old_platform])

  with open(CAR_LIST_JSON_OUT) as f:
    car_list = json.load(f)

  candidates = [(k, v) for k, v in car_list.items() if v.get("platform") == new_platform]
  if candidates:
    old_model = bundle.get("model")
    key, data = next(((k, v) for k, v in candidates if v.get("model") == old_model), candidates[0])
    bundle = {**data, "name": key}
  else:
    bundle["platform"] = new_platform

  _params.put("CarPlatformBundle", bundle)
  cloudlog.info(f"params_migration: CarPlatformBundle migrated {old_platform!r} -> {new_platform!r}")


def run_migration(_params):
  # migrate OnroadScreenOffBrightness
  if _params.get("OnroadScreenOffBrightnessMigrated") != ONROAD_BRIGHTNESS_MIGRATION_VERSION:
    try:
      val = _params.get("OnroadScreenOffBrightness", return_default=True)
      if val >= 2:  # old: 5%, new: Screen Off
        new_val = val + 1
        _params.put("OnroadScreenOffBrightness", new_val)
        log_str = f"Successfully migrated OnroadScreenOffBrightness from {val} to {new_val}."
      else:
        log_str = "Migration not required for OnroadScreenOffBrightness."

      _params.put("OnroadScreenOffBrightnessMigrated", ONROAD_BRIGHTNESS_MIGRATION_VERSION)
      cloudlog.info(log_str + f" Setting OnroadScreenOffBrightnessMigrated to {ONROAD_BRIGHTNESS_MIGRATION_VERSION}")
    except Exception as e:
      cloudlog.exception(f"Error migrating OnroadScreenOffBrightness: {e}")

  # migrate OnroadScreenOffTimer
  if _params.get("OnroadScreenOffTimerMigrated") != ONROAD_BRIGHTNESS_TIMER_MIGRATION_VERSION:
    try:
      val = _params.get("OnroadScreenOffTimer", return_default=True)
      if val not in VALID_TIMER_VALUES:
        _params.put("OnroadScreenOffTimer", 15)
        log_str = f"Successfully migrated OnroadScreenOffTimer from {val} to 15 (default)."
      else:
        log_str = "Migration not required for OnroadScreenOffTimer."

      _params.put("OnroadScreenOffTimerMigrated", ONROAD_BRIGHTNESS_TIMER_MIGRATION_VERSION)
      cloudlog.info(log_str + f" Setting OnroadScreenOffTimerMigrated to {ONROAD_BRIGHTNESS_TIMER_MIGRATION_VERSION}")
    except Exception as e:
      cloudlog.exception(f"Error migrating OnroadScreenOffTimer: {e}")

  _migrate_car_platform_bundle(_params)
