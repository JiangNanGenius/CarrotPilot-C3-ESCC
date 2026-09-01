import json
from pathlib import Path

from openpilot.sunnypilot.system.params_migration import (
  LEGACY_CARROT_PARAMS_MIGRATION_MARKER,
  migrate_legacy_carrot_params,
)


class RawParams:
  def __init__(self, source_dir: Path, native_keys=()):
    self.source_dir = source_dir
    self.native_keys = list(native_keys)

  def get_param_path(self):
    return str(self.source_dir)

  def all_keys(self):
    return self.native_keys


def write_settings(path: Path, *names: str) -> None:
  path.write_text(json.dumps({"params": [{"name": name} for name in names]}), encoding="utf-8")


def test_legacy_carrot_migration_copies_only_carrot_whitelist(tmp_path):
  source = tmp_path / "d"
  target = tmp_path / "d_carrot"
  settings = tmp_path / "carrot_settings.json"
  source.mkdir()
  (source / "CarrotOwned").write_bytes(b"42")
  (source / "OpenpilotEnabledToggle").write_bytes(b"0")
  (source / "OutsideWhitelist").write_bytes(b"keep-out")
  (source / "MapboxSecretKey").write_bytes(b"secret")
  (source / "EnableAmapNaviStatus").write_bytes(b"1")
  (source / "ShareData").write_bytes(b"1")
  (source / "CarrotSpeedLimitEnable").write_bytes(b"0")
  (source / "CarrotTrafficStopEnable").write_bytes(b"1")
  write_settings(
    settings,
    "CarrotOwned",
    "OpenpilotEnabledToggle",
    "MapboxSecretKey",
    "EnableAmapNaviStatus",
    "CarrotSpeedLimitEnable",
    "CarrotTrafficStopEnable",
  )

  copied = migrate_legacy_carrot_params(
    RawParams(
      source,
      native_keys=("OpenpilotEnabledToggle", "CarrotSpeedLimitEnable", "CarrotTrafficStopEnable"),
    ),
    settings_path=settings,
  )

  assert copied == 5
  assert (target / "CarrotOwned").read_bytes() == b"42"
  assert (target / "EnableAmapNaviStatus").read_bytes() == b"1"
  assert (target / "ShareData").read_bytes() == b"1"
  assert (target / "CarrotSpeedLimitEnable").read_bytes() == b"0"
  assert (target / "CarrotTrafficStopEnable").read_bytes() == b"1"
  assert not (target / "OpenpilotEnabledToggle").exists()
  assert not (target / "OutsideWhitelist").exists()
  assert not (target / "MapboxSecretKey").exists()


def test_legacy_carrot_migration_never_overwrites_existing_target(tmp_path):
  source = tmp_path / "d"
  target = tmp_path / "d_carrot"
  settings = tmp_path / "carrot_settings.json"
  source.mkdir()
  target.mkdir()
  (source / "CarrotOwned").write_bytes(b"legacy")
  (target / "CarrotOwned").write_bytes(b"current")
  write_settings(settings, "CarrotOwned")

  copied = migrate_legacy_carrot_params(RawParams(source), settings_path=settings)

  assert copied == 0
  assert (target / "CarrotOwned").read_bytes() == b"current"


def test_legacy_carrot_migration_marker_makes_second_run_noop(tmp_path):
  source = tmp_path / "d"
  target = tmp_path / "d_carrot"
  settings = tmp_path / "carrot_settings.json"
  source.mkdir()
  (source / "First").write_bytes(b"one")
  write_settings(settings, "First", "AppearedLater")

  assert migrate_legacy_carrot_params(RawParams(source), settings_path=settings) == 1
  assert (target / LEGACY_CARROT_PARAMS_MIGRATION_MARKER).exists()

  (source / "AppearedLater").write_bytes(b"two")
  assert migrate_legacy_carrot_params(RawParams(source), settings_path=settings) == 0
  assert not (target / "AppearedLater").exists()
