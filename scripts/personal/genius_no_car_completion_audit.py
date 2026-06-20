#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TITLE = "Genius Pilot No-Car Completion Audit"


PENDING_CLASSIFIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
  ("release_policy_recurring", (
    "Keep `/x` as the single short alpha entry",
    "Bump the Genius Pilot suffix before every pushed alpha build",
    "Keep `/i` stable until C3 parking and road evidence are clean",
  )),
  ("device_install_required", (
    "After the next clean `/x` install",
    "Pull a C3 evidence bundle",
    "Restore C3 SSH access",
    "Verify model list download and active bundle evidence on C3",
    "Sync or reinstall on the user's C3",
    "Run C3 parked checks",
    "Run the silent C3 IMU probe on the clone C3",
    "Re-run writable same-value and safe navigation probes",
    "Verify model manager live list/download availability on C3",
    "Verify the same Super Advanced page on the physical C3",
    "Verify C3 UI/touch without car",
    "User visual confirmation",
    "Run real device parking test on clone C3",
    "Run `sunnypilot_c3_device_collect.py --parked-hardware-probe`",
    "Re-run IMU as a separate C3 hardware check",
  )),
  ("real_car_required", (
    "Validate on the user's Kia Seltos 2023",
    "Validate speed source switching",
  )),
  ("future_fixture_or_baseline", (
    "Add model replay with camera frame inputs when a suitable FrameReader/log fixture is available",
    "Generate and review fork-owned process replay references",
  )),
  ("docs_after_feedback", (
    "Keep docs current after every real-device hotfix",
    "Continue polishing Chinese descriptions after real-device feedback",
  )),
  ("current_release_archive_recurring", (
    "Run `genius_no_car_evidence_bundle.py --full-gate --json` after each pushed alpha build",
  )),
  ("not_required_for_code_phase", (
    "Road testing is not required for this code/local phase",
  )),
)


REQUIRED_LOCAL_EVIDENCE: tuple[tuple[str, str, str], ...] = (
  ("release gate includes completion audit", "scripts/personal/sunnypilot_c3_alpha_release_gate.py", "genius_no_car_completion_audit.py"),
  ("static gate includes completion audit", "scripts/personal/sunnypilot_c3_alpha_static_check.py", "Genius no-car completion audit"),
  ("AGENTS lists completion audit", "AGENTS.md", "genius_no_car_completion_audit.py --json"),
  ("TODO records completion audit", "docs/personal/TODO.md", "Verify no-car/code completion boundaries through `genius_no_car_completion_audit.py`"),
  ("CODE_CHANGES records completion audit", "docs/personal/CODE_CHANGES.md", "No-Car Completion Audit"),
  ("evidence bundle command is documented", "AGENTS.md", "genius_no_car_evidence_bundle.py --full-gate --json"),
  ("touch contract is release-gated", "scripts/personal/sunnypilot_c3_alpha_release_gate.py", "Genius C3 touch fallback contract"),
  ("super advanced contract is release-gated", "scripts/personal/sunnypilot_c3_alpha_release_gate.py", "Genius Super Advanced contract"),
  ("model manager contract is release-gated", "scripts/personal/sunnypilot_c3_alpha_release_gate.py", "Genius model manager contract"),
)


def read(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
  return {"name": name, "ok": bool(ok), "detail": "" if ok else detail}


def pending_todo_items(todo_text: str) -> list[dict[str, Any]]:
  items: list[dict[str, Any]] = []
  for idx, line in enumerate(todo_text.splitlines(), start=1):
    match = re.match(r"\s*-\s+\[ \]\s+(.*)", line)
    if not match:
      continue
    text = match.group(1).strip()
    category = ""
    for candidate, needles in PENDING_CLASSIFIERS:
      if any(needle in text for needle in needles):
        category = candidate
        break
    items.append({"line": idx, "text": text, "category": category})
  return items


def build_report() -> dict[str, Any]:
  todo = read("docs/personal/TODO.md")
  items = pending_todo_items(todo)
  unclassified = [item for item in items if not item["category"]]
  categories: dict[str, int] = {}
  for item in items:
    categories[item["category"] or "unclassified"] = categories.get(item["category"] or "unclassified", 0) + 1

  checks: list[dict[str, Any]] = [
    check("all unchecked TODO items are classified", not unclassified, json.dumps(unclassified, ensure_ascii=False)),
    check("no unchecked TODO is classified as local no-car/code work", all(item["category"] != "local_no_car_required" for item in items)),
  ]

  for name, path, token in REQUIRED_LOCAL_EVIDENCE:
    checks.append(check(name, token in read(path), f"{token} missing from {path}"))

  checks.append(check(
    "future fixture items are explicitly not release blockers",
    "Model replay that needs camera frames should follow" in read("AGENTS.md")
    and "Current HYUNDAI no-car replay is crash-free and native-unblocked" in read("AGENTS.md")
    and "reports fork reference diffs until Genius/Carrot-owned baselines are generated" in read("AGENTS.md"),
  ))
  checks.append(check(
    "physical C3 items remain visibly separate",
    "Verify the same Super Advanced page on the physical C3" in todo
    and "Verify C3 UI/touch without car" in todo
    and "Run the silent C3 IMU probe on the clone C3" in todo,
  ))

  return {
    "title": TITLE,
    "ok": all(item["ok"] for item in checks),
    "pendingCount": len(items),
    "pendingCategories": categories,
    "unclassified": unclassified,
    "checks": checks,
  }


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    TITLE,
    "PENDING_CLASSIFIERS",
    "REQUIRED_LOCAL_EVIDENCE",
    "future_fixture_or_baseline",
    "device_install_required",
    "real_car_required",
    "docs_after_feedback",
    "all unchecked TODO items are classified",
    "physical C3 items remain visibly separate",
  )
  if not all(token in text for token in required):
    print(f"FAIL {TITLE} self-test: missing token")
    return 1
  report = build_report()
  if not report["ok"]:
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 1
  print(f"PASS {TITLE} self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description=TITLE)
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report = build_report()
  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
  else:
    print(f"{'PASS' if report['ok'] else 'FAIL'} {TITLE}")
    for item in report["checks"]:
      print(f"{'PASS' if item['ok'] else 'FAIL'} {item['name']}")
      if not item["ok"] and item.get("detail"):
        print(item["detail"])
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
