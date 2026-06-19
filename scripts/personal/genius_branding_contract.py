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
  mici_device = read("selfdrive/ui/mici/layouts/settings/device.py")
  mici_toggles = read("selfdrive/ui/mici/layouts/settings/toggles.py")
  updater = read("system/updated/updated.py")
  readme = read("README.md")
  high_risk_guide = read("docs/personal/HIGH_RISK_SETTING_GUIDE.md")
  release_template = read("docs/personal/RELEASE_TEMPLATE.md")

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
    "enable sunnypilot",
    "update sunnypilot",
  )
  required_firehose_tokens = (
    "Data Uploads Disabled",
    "Genius Pilot keeps cloud training uploads disabled",
    "Driving data is not uploaded from this page.",
    "DISABLED: cloud uploads are off in this personal build",
  )
  forbidden_readme_tokens = (
    "By default, sunnypilot uploads the driving data to comma servers",
    "Firehose Mode allows you to maximize your training data uploads",
    "Join the official sunnypilot community forum",
    "Become a sponsor",
    "PayPal this",
    "sunnylink client-side implementation",
  )
  required_readme_tokens = (
    "Genius Pilot C3 ESCC",
    "Stable daily rollback line",
    "https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/i",
    "SunnyPilot 0.11 C3 alpha line",
    "https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x",
    "Cloud services are intentionally disabled or inert",
    "Local networking remains enabled for maintenance",
    "KIA_SELTOS_2023",
    "ESCC: automatic enhanced SCC detection through `0x2AB`",
    "Super Advanced Carrot/Genius settings",
    "GeniusCarrotWorldOverlay",
    "GeniusFishopVisualOverlay",
    "HIGH_RISK_SETTING_GUIDE.md",
    "RELEASE_TEMPLATE.md",
  )
  required_high_risk_tokens = (
    "Genius Pilot High-Risk Setting Guide",
    "`OffroadMode`",
    "`CarrotActiveSpeedControlEnabled`",
    "`CarrotAutoTurnControlEnabled`",
    "`CarrotTrafficStopEnabled`",
    "`CarrotLearningAutoApply`",
    "`FishopAutoOvertakeEnabled`",
    "`GeniusVisualMode`",
    "controlOutput=false",
    "Install `/i` if the alpha branch itself is suspect",
  )
  required_release_tokens = (
    "Genius Pilot Alpha Release Template",
    "Installer SHA256",
    "Stable rollback URL",
    "No-Cloud Evidence",
    "`athenad`",
    "`uploader`",
    "`sunnylinkd`",
    "Enhanced SCC `0x2AB` detected",
    "`modelV2` sampled",
    "Control output remains false",
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
      not any(token in firehose + firehose_mici + cruise + snapshot + evidence + software + mici_device + mici_toggles + updater for token in forbidden_brand_tokens),
      "selected user-facing alpha surfaces must not show old SunnyPilot branding",
    ),
    CheckResult(
      "visible updater/software branding remains Genius Pilot",
      "Genius Pilot {version}" in updater
      and "Genius Pilot {get_version()}" in software
      and "update Genius Pilot" in mici_device
      and "enable Genius Pilot" in mici_toggles,
      "software, updater, and MICI settings surfaces must show Genius Pilot",
    ),
    CheckResult(
      "README is Genius Pilot personal alpha copy",
      all(token in readme for token in required_readme_tokens),
      "README must describe /i, /x, C3/Seltos/ESCC, no-cloud policy, local Web/API, and personal docs",
    ),
    CheckResult(
      "README has no upstream cloud/sponsor copy",
      not any(token in readme for token in forbidden_readme_tokens),
      "README must not keep upstream cloud-upload, Sunnylink, or sponsor marketing copy",
    ),
    CheckResult(
      "high-risk setting guide exists",
      all(token in high_risk_guide for token in required_high_risk_tokens),
      "docs/personal/HIGH_RISK_SETTING_GUIDE.md must explain risky Carrot/Fishop/model/visual settings and rollback",
    ),
    CheckResult(
      "release evidence template exists",
      all(token in release_template for token in required_release_tokens),
      "docs/personal/RELEASE_TEMPLATE.md must capture installer, device, no-cloud, ESCC, model, Carrot, and Fishop evidence",
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
