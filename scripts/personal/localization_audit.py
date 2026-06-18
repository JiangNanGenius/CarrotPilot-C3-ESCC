#!/usr/bin/env python3
import re
import sys
from pathlib import Path
from typing import Iterable, List


ROOT = Path(__file__).resolve().parents[2]
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

SCAN_PATHS = [
  "README.md",
  "docs/personal",
  "scripts/personal",
  "selfdrive/carrot_settings.json",
  "selfdrive/carrot/carrot_serv.py",
  "selfdrive/carrot/kmap/kmap.js",
  "selfdrive/carrot/kmap/index.html",
  "selfdrive/carrot/recovery/server.py",
  "selfdrive/carrot/server/features",
  "selfdrive/carrot/server/services",
  "selfdrive/carrot/web/css",
  "selfdrive/carrot/web/index.html",
  "selfdrive/carrot/web/js/pages",
  "selfdrive/carrot/web/js/realtime",
  "selfdrive/carrot/web/js/shared",
  "selfdrive/carrot/web/js/translations",
]

SKIP_PARTS = {
  "__pycache__",
  ".pytest_cache",
  "vendor",
}


def iter_files(paths: Iterable[str]) -> Iterable[Path]:
  for rel in paths:
    path = ROOT / rel
    if not path.exists():
      continue
    if path.is_file():
      yield path
      continue
    for child in path.rglob("*"):
      if not child.is_file():
        continue
      if any(part in SKIP_PARTS for part in child.relative_to(ROOT).parts):
        continue
      if child.suffix.lower() not in {".css", ".html", ".js", ".json", ".md", ".py", ".txt", ".yml", ".yaml"}:
        continue
      yield child


def rel(path: Path) -> str:
  return str(path.relative_to(ROOT))


def main() -> int:
  failures: List[str] = []
  for path in iter_files(SCAN_PATHS):
    try:
      text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
      continue
    for lineno, line in enumerate(text.splitlines(), start=1):
      if HANGUL_RE.search(line):
        failures.append(f"{rel(path)}:{lineno}: Korean text remains")

  ko_pack = ROOT / "selfdrive/carrot/web/js/translations/ko.js"
  if ko_pack.exists():
    failures.append(f"{rel(ko_pack)}: Korean translation pack should not be shipped in this personal fork")

  index = (ROOT / "selfdrive/carrot/web/index.html").read_text(encoding="utf-8")
  if "/js/translations/ko.js" in index:
    failures.append("selfdrive/carrot/web/index.html: Korean translation pack is still loaded")

  print("Localization audit")
  print("repo:", ROOT)
  print("checked roots:", ", ".join(SCAN_PATHS))
  if failures:
    for failure in failures:
      print("[FAIL]", failure)
    return 1
  print("OK: Chinese/English localization has no direct Korean UI text")
  return 0


if __name__ == "__main__":
  sys.exit(main())
