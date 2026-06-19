#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import urllib.request


DEFAULT_SOURCE_URL = "https://gitop.vip/cp"
DEFAULT_SOURCE_SHA256 = "01b7d45c35ef262abded54bfb8f39e46b754917a9a5de890b15fa4ef4634da5e"
DEFAULT_OUTPUT = Path("/tmp/carrot_x_qt_compat")

TARGET_REPO = b"https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git"
TARGET_BRANCH = b"alpha-sunnypilot-c3"
TARGET_TITLE = b"Installing Genius Pilot alpha"
DISABLED_CACHE_PATH = b"/data/cp_no_cache"


def sha256(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
  request = urllib.request.Request(
    url,
    headers={
      "User-Agent": "CarrotPilot-C3-ESCC-qt-installer-builder/1.0",
      "Accept": "application/octet-stream,*/*",
    },
  )
  with urllib.request.urlopen(request, timeout=30) as response:
    return response.read()


class BinaryPatcher:
  def __init__(self, data: bytes):
    self.data = bytearray(data)
    self.changes: list[str] = []

  def replace_exact(self, old: bytes, new: bytes, label: str) -> None:
    offset = self.data.find(old)
    if offset < 0:
      raise RuntimeError(f"missing {label}: {old!r}")
    if len(new) > len(old):
      raise RuntimeError(f"{label} replacement too long: {len(new)} > {len(old)}")
    self.data[offset:offset + len(old)] = new + (b"\0" * (len(old) - len(new)))
    self.changes.append(f"{label}: offset={offset} old_len={len(old)} new_len={len(new)}")

  def replace_in_slot(self, old: bytes, new: bytes, label: str) -> None:
    offset = self.data.find(old)
    if offset < 0:
      raise RuntimeError(f"missing {label}: {old!r}")

    end = offset
    while end < len(self.data) and self.data[end] != 0:
      end += 1

    slot_end = end
    while slot_end < len(self.data) and self.data[slot_end] == 0:
      slot_end += 1

    slot_len = slot_end - offset
    if len(new) + 1 > slot_len:
      raise RuntimeError(f"{label} replacement too long for slot: {len(new) + 1} > {slot_len}")
    self.data[offset:offset + slot_len] = new + (b"\0" * (slot_len - len(new)))
    self.changes.append(f"{label}: offset={offset} slot={slot_len} new_len={len(new)}")


def build_installer(source: bytes, *, expected_source_sha256: str) -> tuple[bytes, list[str]]:
  actual_source_sha256 = sha256(source)
  if expected_source_sha256 and actual_source_sha256 != expected_source_sha256:
    raise RuntimeError(f"source sha256 mismatch: expected {expected_source_sha256}, got {actual_source_sha256}")

  patcher = BinaryPatcher(source)
  patcher.replace_in_slot(b"https://jihulab.com/fishop/openpilot.git", TARGET_REPO, "repo url")
  patcher.replace_exact(b"/usr/comma/openpilot", DISABLED_CACHE_PATH, "cache path 1")
  patcher.replace_exact(b"/usr/comma/openpilot", DISABLED_CACHE_PATH, "cache path 2")
  patcher.replace_in_slot(b"Installing CarrotPilot                            ", TARGET_TITLE, "title")
  patcher.replace_in_slot(
    b"git remote set-branches --add origin cp",
    b"git remote set-branches --add origin " + TARGET_BRANCH,
    "set branches",
  )
  patcher.replace_in_slot(b"git checkout cp", b"git checkout " + TARGET_BRANCH, "checkout")
  patcher.replace_in_slot(b"git reset --hard origin/cp", b"git reset --hard origin/" + TARGET_BRANCH, "reset")
  return bytes(patcher.data), patcher.changes


def main() -> int:
  parser = argparse.ArgumentParser(description="Build the C3-compatible /x Qt installer from the known gitop.vip/cp binary.")
  parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
  parser.add_argument("--source-file", type=Path)
  parser.add_argument("--source-sha256", default=DEFAULT_SOURCE_SHA256)
  parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
  args = parser.parse_args()

  source = args.source_file.read_bytes() if args.source_file else download(args.source_url)
  output, changes = build_installer(source, expected_source_sha256=args.source_sha256)
  args.output.write_bytes(output)
  args.output.chmod(0o755)

  for change in changes:
    print(change)
  print(f"source_sha256={sha256(source)}")
  print(f"output_sha256={sha256(output)}")
  print(f"output={args.output}")
  print(f"size={len(output)}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
