#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "system/hardware/tici/updater"
SOURCE = ROOT / "system/ui/lib/wifi_manager.py"
MEMBER = "openpilot/system/ui/lib/wifi_manager.py"
ZIP_MAGIC = b"PK\x03\x04"


def updater_prefix(data: bytes) -> bytes:
  idx = data.find(ZIP_MAGIC)
  if idx < 0:
    raise RuntimeError(f"{UPDATER} is not a zipapp-like updater")
  return data[:idx]


def embedded_wifi_manager() -> bytes:
  with zipfile.ZipFile(UPDATER) as zf:
    return zf.read(MEMBER)


def patch_updater() -> bool:
  data = UPDATER.read_bytes()
  prefix = updater_prefix(data)
  source = SOURCE.read_bytes()
  current = embedded_wifi_manager()
  if current == source:
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
          payload = source if info.filename == MEMBER else zin.read(info)
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
      embedded = zf.read(MEMBER)
  except Exception as exc:
    return False, f"updater zip payload is invalid: {exc}"
  if embedded != SOURCE.read_bytes():
    return False, f"{MEMBER} does not match system/ui/lib/wifi_manager.py"
  text = embedded.decode("utf-8", errors="replace")
  required = ("JEEPNEY_AVAILABLE = False", "_nmcli_fallback", "_nmcli_active_ssid", "nmcli\", \"device\", \"wifi\", \"rescan", "_update_networks")
  missing = [token for token in required if token not in text]
  if missing:
    return False, f"embedded Wi-Fi manager missing fallback tokens: {missing}"
  return True, ""


def main() -> int:
  parser = argparse.ArgumentParser(description="Patch the packed TICI updater with the main-tree Wi-Fi manager fallback.")
  parser.add_argument("--check", action="store_true", help="only verify the packed updater")
  args = parser.parse_args()

  if args.check:
    ok, detail = check_updater()
    if not ok:
      print(f"FAIL {detail}")
      return 1
    print("PASS packed TICI updater Wi-Fi manager matches main tree")
    return 0

  changed = patch_updater()
  ok, detail = check_updater()
  if not ok:
    print(f"FAIL {detail}")
    return 1
  print("PATCHED packed TICI updater Wi-Fi manager" if changed else "UNCHANGED packed TICI updater Wi-Fi manager")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
