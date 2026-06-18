#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SRC_COMMIT = "ce355250be726f9bc8f0ac165a6cde41586a983d"
EXPECTED_SRC_DATE = "1741413843 2025-03-07 22:04:03 -0800"


class BaseVersionError(Exception):
  pass


def read(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8")


def expect(text: str, needle: str, label: str) -> None:
  if needle not in text:
    raise BaseVersionError(f"missing {label}: {needle}")


def main() -> int:
  try:
    src_commit = read("git_src_commit").strip()
    src_date = read("git_src_commit_date").strip()
    readme = read("README.md")
    releases = read("RELEASES.md")
    doc = read("docs/personal/BASE_VERSION_AND_UPGRADE.md")

    if src_commit != EXPECTED_SRC_COMMIT:
      raise BaseVersionError(f"unexpected git_src_commit: {src_commit}")
    if src_date != EXPECTED_SRC_DATE:
      raise BaseVersionError(f"unexpected git_src_commit_date: {src_date}")

    expect(readme, "ajouatom/openpilot:c3-wip", "README base branch")
    expect(readme, "BASE_VERSION_AND_UPGRADE.md", "README base version doc link")
    expect(releases, "Version 0.9.9 (2025-04-30)", "0.9.9 release marker")
    expect(doc, "openpilot 0.9.9-era CarrotPilot C3-WIP", "version label")
    expect(doc, EXPECTED_SRC_COMMIT, "source commit")
    expect(doc, EXPECTED_SRC_DATE, "source commit date")
    expect(doc, "不是官方 openpilot 1.0", "not 1.0 warning")
    expect(doc, "不是 0.10.x", "not 0.10.x warning")
    expect(doc, "C3 中国克隆版", "C3 clone scope")
    expect(doc, "ESCC", "ESCC scope")

    print("Base version check")
    print(f"source commit: {src_commit}")
    print(f"source date: {src_date}")
    print("base label: openpilot 0.9.9-era CarrotPilot C3-WIP")
    print("OK: base version documentation matches repository evidence")
    return 0
  except BaseVersionError as exc:
    print(f"base version check failed: {exc}")
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
