#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "system/hardware/tici/updater"
MEMBER = "openpilot/system/ui/lib/wifi_manager.py"
SYNC_MEMBERS = {
  MEMBER: ROOT / "system/ui/lib/wifi_manager.py",
  "openpilot/system/ui/tici_updater.py": ROOT / "system/ui/tici_updater.py",
  "openpilot/system/ui/widgets/__init__.py": ROOT / "system/ui/widgets/__init__.py",
  "openpilot/system/ui/widgets/button.py": ROOT / "system/ui/widgets/button.py",
  "openpilot/system/ui/lib/application.py": ROOT / "system/ui/lib/application.py",
}
ZIP_MAGIC = b"PK\x03\x04"


def updater_prefix(data: bytes) -> bytes:
  idx = data.find(ZIP_MAGIC)
  if idx < 0:
    raise RuntimeError(f"{UPDATER} is not a zipapp-like updater")
  return data[:idx]


def embedded_member(member: str) -> bytes:
  with zipfile.ZipFile(UPDATER) as zf:
    return zf.read(member)


def patch_updater() -> bool:
  data = UPDATER.read_bytes()
  prefix = updater_prefix(data)
  sources = {member: source.read_bytes() for member, source in SYNC_MEMBERS.items()}
  if all(embedded_member(member) == payload for member, payload in sources.items()):
    return False

  mode = UPDATER.stat().st_mode & 0o777
  fd, tmp_name = tempfile.mkstemp(prefix="updater.", suffix=".tmp", dir=str(UPDATER.parent))
  os.close(fd)
  tmp_path = Path(tmp_name)
  try:
    with zipfile.ZipFile(UPDATER) as zin, tmp_path.open("wb") as raw_out:
      raw_out.write(prefix)
      with zipfile.ZipFile(raw_out, "w") as zout:
        for info in zin.infolist():
          payload = sources.get(info.filename, zin.read(info))
          zout.writestr(info, payload)
    os.chmod(tmp_path, mode)
    tmp_path.replace(UPDATER)
  except Exception:
    tmp_path.unlink(missing_ok=True)
    raise
  return True


def check_updater() -> tuple[bool, str]:
  data = UPDATER.read_bytes()
  prefix = updater_prefix(data)
  if not prefix.startswith(b"#!/usr/bin/env python3"):
    return False, "updater prefix is not the expected python3 shebang"
  try:
    with zipfile.ZipFile(UPDATER) as zf:
      zf.testzip()
      embedded = {member: zf.read(member) for member in SYNC_MEMBERS}
  except Exception as exc:
    return False, f"updater zip payload is invalid: {exc}"
  for member, source in SYNC_MEMBERS.items():
    if embedded[member] != source.read_bytes():
      return False, f"{member} does not match {source.relative_to(ROOT)}"
  text = embedded[MEMBER].decode("utf-8", errors="replace")
  required = (
    "JEEPNEY_AVAILABLE = False",
    "_nmcli_fallback",
    "_run_nmcli",
    "_nmcli_active_ssid",
    "\"device\", \"wifi\", \"rescan\"",
    "nmcli command unavailable",
    "_update_networks",
  )
  missing = [token for token in required if token not in text]
  if missing:
    return False, f"embedded Wi-Fi manager missing fallback tokens: {missing}"
  updater_text = embedded["openpilot/system/ui/tici_updater.py"].decode("utf-8", errors="replace")
  updater_required = (
    "CRITICAL_TAP_EXPAND_PX",
    "button.set_tap_release_move_px(140)",
    "def _activate_at",
    "self._install_button_rect",
    "self._ignore_release_after_press",
  )
  missing = [token for token in updater_required if token not in updater_text]
  if missing:
    return False, f"embedded TICI updater missing touch fallback tokens: {missing}"
  widget_text = embedded["openpilot/system/ui/widgets/__init__.py"].decode("utf-8", errors="replace")
  widget_required = (
    "TAP_RELEASE_MOVE_PX = 24",
    "def set_tap_release_move_px",
    "__touch_cancelled",
    "short_tap_release and not touch_cancelled and touch_valid",
  )
  missing = [token for token in widget_required if token not in widget_text]
  if missing:
    return False, f"embedded widget core missing tap filtering tokens: {missing}"
  application_text = embedded["openpilot/system/ui/lib/application.py"].decode("utf-8", errors="replace")
  application_required = (
    "MAIN_THREAD_INPUT",
    "_last_touch_pos",
    "C3/TICI touch releases can report an empty/cleared position",
    "self._mouse._handle_mouse_event()",
  )
  missing = [token for token in application_required if token not in application_text]
  if missing:
    return False, f"embedded application input loop missing C3 touch tokens: {missing}"
  return True, ""


def main() -> int:
  parser = argparse.ArgumentParser(description="Patch the packed TICI updater with main-tree Wi-Fi and C3 touch fallbacks.")
  parser.add_argument("--check", action="store_true", help="only verify the packed updater")
  args = parser.parse_args()

  if args.check:
    ok, detail = check_updater()
    if not ok:
      print(f"FAIL {detail}")
      return 1
    print("PASS packed TICI updater UI payload matches main tree")
    return 0

  changed = patch_updater()
  ok, detail = check_updater()
  if not ok:
    print(f"FAIL {detail}")
    return 1
  print("PATCHED packed TICI updater UI payload" if changed else "UNCHANGED packed TICI updater UI payload")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
