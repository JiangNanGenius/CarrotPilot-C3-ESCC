#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CheckResult:
  name: str
  ok: bool
  detail: str = ""


def read(rel: str) -> str:
  return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def check_sources() -> list[CheckResult]:
  firehose = read("selfdrive/ui/layouts/settings/firehose.py")
  firehose_mici = read("selfdrive/ui/mici/layouts/settings/firehose.py")
  cruise = read("selfdrive/ui/sunnypilot/layouts/settings/cruise.py")
  snapshot = read("scripts/personal/sunnypilot_c3_alpha_snapshot.py")
  evidence = read("scripts/personal/sunnypilot_c3_alpha_evidence_check.py")
  software = read("selfdrive/ui/layouts/settings/software.py")
  updater = read("system/updated/updated.py")

  combined_firehose = firehose + "\n" + firehose_mici
  forbidden_firehose_tokens = (
    "sunnypilot learns to drive",
    "Firehose Mode allows you to maximize your training data uploads",
    "Firehose Mode can also work while you're driving",
    "ApiCache_FirehoseStats",
    "api_get",
    "get_token",
    "UNREGISTERED_DONGLE_ID",
    "v1/devices/",
    "firehose_stats",
  )
  forbidden_brand_tokens = (
    "Welcome to sunnypilot",
    "sunnypilot longitudinal control may come",
    "Enable the sunnypilot longitudinal control",
    "CarrotPilot-C3-ESCC SunnyPilot Alpha Snapshot",
    "privacy-safe SunnyPilot C3 alpha",
    "SunnyPilot ICBM",
  )
  required_firehose_tokens = (
    "Data Uploads Disabled",
    "Genius Pilot keeps cloud training uploads disabled",
    "Driving data is not uploaded from this page.",
    "DISABLED: cloud uploads are off in this personal build",
  )

  return [
    CheckResult(
      "Firehose page is local/no-cloud copy",
      all(token in combined_firehose for token in required_firehose_tokens),
      "Firehose page must explain that cloud uploads are disabled in Genius Pilot",
    ),
    CheckResult(
      "Firehose page has no upload client path",
      not any(token in combined_firehose for token in forbidden_firehose_tokens),
      "Firehose page must not mention training uploads or call cloud firehose APIs",
    ),
    CheckResult(
      "snapshot branding is Genius Pilot",
      "Genius Pilot C3 Alpha Snapshot" in snapshot and "Genius Pilot C3 Alpha Snapshot" in evidence,
      "snapshot tools must use Genius Pilot title metadata",
    ),
    CheckResult(
      "user-facing branding avoids old SunnyPilot copy",
      not any(token in firehose + firehose_mici + cruise + snapshot + evidence + software + updater for token in forbidden_brand_tokens),
      "selected user-facing alpha surfaces must not show old SunnyPilot branding",
    ),
    CheckResult(
      "visible updater/software branding remains Genius Pilot",
      "Genius Pilot {version}" in updater and "Genius Pilot {get_version()}" in software,
      "software and updater surfaces must show Genius Pilot",
    ),
  ]


def print_results(results: list[CheckResult]) -> None:
  for result in results:
    if result.ok:
      print(f"PASS {result.name}")
    else:
      print(f"FAIL {result.name}: {result.detail}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Check Genius Pilot user-facing branding and local/no-cloud Firehose copy.")
  parser.add_argument("--self-test", action="store_true", help="run the same offline branding checks used by the release gate")
  parser.parse_args()

  results = check_sources()
  print_results(results)
  return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
  raise SystemExit(main())
