#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import urllib.request


DEFAULT_INSTALL_URL = "https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x"
DEFAULT_MIN_SIZE_BYTES = 180_000

REQUIRED_TOKENS = (
  b"Installing Genius Pilot alpha",
  b"https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git",
  b"git checkout alpha-sunnypilot-c3",
  b"git reset --hard origin/alpha-sunnypilot-c3",
  b"QProgressBar",
  b"GLIBC_2.17",
)

FORBIDDEN_TOKENS = (
  b"GLIBC_2.38",
  b"Initializing raylib",
  b"sshane/openpilot-installer-generator",
  b"Installing sp/staging-tici",
  b"https://github.com/sunnypilot/sunnypilot.git",
  b"https://jihulab.com/fishop/openpilot.git",
  b"git checkout staging-tici",
  b"git reset --hard origin/staging-tici",
  b"git checkout cp",
  b"git reset --hard origin/cp",
)


def check(name: str, ok: bool, detail: str) -> dict[str, object]:
  return {
    "name": name,
    "ok": bool(ok),
    "detail": detail,
  }


def is_arm64_elf(data: bytes) -> bool:
  if len(data) < 64:
    return False
  if data[:4] != b"\x7fELF":
    return False
  if data[4] != 2 or data[5] != 1:
    return False
  return int.from_bytes(data[18:20], "little") == 183


def audit_bytes(data: bytes, source: str, min_size: int, expected_sha256: str | None = None) -> dict[str, object]:
  sha256 = hashlib.sha256(data).hexdigest()
  checks: list[dict[str, object]] = [
    check("arm64_elf", is_arm64_elf(data), "installer must be an ARM64 ELF binary"),
    check("qt_compat_size", len(data) >= min_size, f"installer size {len(data)} must be at least {min_size} bytes"),
  ]

  for token in REQUIRED_TOKENS:
    checks.append(check(f"required:{token.decode('utf-8', errors='replace')}", token in data, "required installer token missing"))

  for token in FORBIDDEN_TOKENS:
    checks.append(check(f"forbidden:{token.decode('utf-8', errors='replace')}", token not in data, "forbidden old/upstream installer token present"))

  if expected_sha256:
    checks.append(check("expected_sha256", sha256 == expected_sha256, f"actual sha256 is {sha256}"))

  ok = all(item["ok"] for item in checks)
  return {
    "title": "Genius Pilot Installer Audit",
    "source": source,
    "ok": ok,
    "size": len(data),
    "sha256": sha256,
    "checks": checks,
  }


def download(url: str) -> bytes:
  request = urllib.request.Request(
    url,
    headers={
      "User-Agent": "CarrotPilot-C3-ESCC-installer-audit/1.0",
      "Accept": "application/octet-stream,*/*",
    },
  )
  with urllib.request.urlopen(request, timeout=30) as response:
    return response.read()


def sample_installer(*, old_or_incompatible: bool = False) -> bytes:
  header = bytearray(64)
  header[:4] = b"\x7fELF"
  header[4] = 2
  header[5] = 1
  header[16:18] = (3).to_bytes(2, "little")
  header[18:20] = (183).to_bytes(2, "little")
  tokens = FORBIDDEN_TOKENS if old_or_incompatible else REQUIRED_TOKENS
  data = bytes(header) + (b"\0" * 256) + b"\0".join(tokens)
  return data + (b"\0" * 4096)


def self_test() -> int:
  good = audit_bytes(sample_installer(), "self-test-good", min_size=1000)
  bad = audit_bytes(sample_installer(old_or_incompatible=True), "self-test-old-or-incompatible", min_size=1000)
  if not good["ok"]:
    print(json.dumps(good, indent=2, sort_keys=True))
    return 1
  if bad["ok"]:
    print(json.dumps(bad, indent=2, sort_keys=True))
    return 1
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit the published Genius Pilot C3 installer binary.")
  parser.add_argument("--url", default=DEFAULT_INSTALL_URL, help="Installer URL to download when --file is not supplied.")
  parser.add_argument("--file", type=Path, help="Already downloaded installer binary to audit.")
  parser.add_argument("--expected-sha256", help="Optional exact SHA256 expected for a pinned release asset.")
  parser.add_argument("--min-size", type=int, default=DEFAULT_MIN_SIZE_BYTES, help="Minimum expected Qt-compatible installer size.")
  parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
  parser.add_argument("--self-test", action="store_true", help="Run offline positive and negative tests.")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  if args.file:
    source = str(args.file)
    data = args.file.read_bytes()
  else:
    source = args.url
    with tempfile.NamedTemporaryFile(prefix="carrot-installer-", suffix=".bin") as tmp:
      data = download(args.url)
      tmp.write(data)
      tmp.flush()

  report = audit_bytes(data, source, args.min_size, args.expected_sha256)
  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"{status} {report['title']}: {report['source']}")
    print(f"sha256={report['sha256']} size={report['size']}")
    for item in report["checks"]:
      if not item["ok"]:
        print(f"FAIL {item['name']}: {item['detail']}")
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
