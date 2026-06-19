#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Reference:
  name: str
  ref: str
  category: str


REFERENCES = (
  Reference("current-alpha", "HEAD", "personal-alpha"),
  Reference("sunnypilot-staging", "refs/remotes/carrot-audit/sunnypilot-staging", "base"),
  Reference("sunnypilot-release-tizi", "refs/remotes/carrot-audit/sunnypilot-release-tizi", "c3"),
  Reference("ajouatom-carrot-wip", "refs/remotes/carrot-audit/ajouatom-carrot-wip", "carrot"),
  Reference("ajouatom-c3-wip", "refs/remotes/carrot-audit/ajouatom-c3-wip", "carrot-c3"),
  Reference("jixiexiaoge-master", "refs/remotes/carrot-audit/jixiexiaoge-master", "mechanical"),
  Reference("jixiexiaoge-atune", "refs/remotes/carrot-audit/jixiexiaoge-atune", "mechanical-atune"),
  Reference("jixiexiaoge-cp", "refs/remotes/carrot-audit/jixiexiaoge-cp", "mechanical-carrot"),
  Reference("jixiexiaoge-release-new", "refs/remotes/carrot-audit/jixiexiaoge-release-new", "mechanical-release"),
  Reference("dhvms-carrotpilot-master", "refs/remotes/carrot-audit/dhvms-carrotpilot-master", "escc"),
)

PARAM_KEYS = (
  "SunnylinkEnabled",
  "EnableSunnylinkUploader",
  "OnroadUploads",
  "EnableConnect",
  "DisableOnroadUploads",
  "OffroadMode",
  "AlwaysOffroad",
  "AlwaysOffline",
  "DynamicExperimentalControl",
  "ExperimentalMode",
  "IntelligentCruiseButtonManagement",
  "SmartCruiseControlVision",
  "SmartCruiseControlMap",
  "SpeedLimitMode",
  "SpeedLimitPolicy",
  "SpeedLimitOffsetType",
  "SpeedLimitValueOffset",
  "CarrotPhoneSpeedLimitEnabled",
  "CarrotMapOverlayEnabled",
  "CarrotActiveSpeedControlEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotTrafficStopEnabled",
  "CarrotLearningActive",
  "CarrotLearningAutoApply",
  "CarrotTunerApplyLat",
  "CarrotTunerApplyLong",
  "FishopLaneCurveEnabled",
  "FishopLidarBlindspotEnabled",
  "FishopLidarLaneDataEnabled",
  "FishopAutoOvertakeEnabled",
  "CruiseMaxVals0",
  "CruiseMaxVals1",
  "CruiseMaxVals2",
  "CruiseMaxVals3",
  "CruiseMaxVals4",
  "CruiseMaxVals5",
  "CruiseMaxVals6",
  "DynamicTFollow",
  "TFollowGap1",
  "TFollowGap2",
  "TFollowGap3",
  "TFollowGap4",
  "StopDistanceCarrot",
  "PathOffset",
  "SteerActuatorDelay",
  "SteerRatioRate",
)

CONFLICT_GROUPS = {
  "cloud_upload": (
    "SunnylinkEnabled",
    "EnableSunnylinkUploader",
    "OnroadUploads",
    "EnableConnect",
    "DisableOnroadUploads",
  ),
  "parked_power": (
    "OffroadMode",
    "AlwaysOffroad",
    "AlwaysOffline",
  ),
  "longitudinal_authority": (
    "DynamicExperimentalControl",
    "ExperimentalMode",
    "SpeedLimitMode",
    "IntelligentCruiseButtonManagement",
    "CarrotActiveSpeedControlEnabled",
    "CarrotAutoTurnControlEnabled",
    "CarrotTrafficStopEnabled",
  ),
  "curve_map_speed": (
    "SmartCruiseControlVision",
    "SmartCruiseControlMap",
    "CarrotAutoTurnControlEnabled",
    "CarrotMapOverlayEnabled",
    "SpeedLimitPolicy",
  ),
  "autotuner_apply": (
    "CarrotLearningAutoApply",
    "CarrotTunerApplyLat",
    "CarrotTunerApplyLong",
  ),
  "fishop_overtake": (
    "FishopLaneCurveEnabled",
    "FishopLidarBlindspotEnabled",
    "FishopLidarLaneDataEnabled",
    "FishopAutoOvertakeEnabled",
  ),
}

PARAM_RE = re.compile(r'^\s*\{"(?P<key>[^"]+)",\s*\{(?P<body>.*)\}\s*\},?\s*$')


def run_git(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
  return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=check)


def ref_exists(ref: str) -> bool:
  return run_git(["rev-parse", "--verify", ref]).returncode == 0


def git_show(ref: str, path: str) -> str:
  proc = run_git(["show", f"{ref}:{path}"])
  return proc.stdout if proc.returncode == 0 else ""


def git_grep_keys(ref: str, keys: tuple[str, ...]) -> dict[str, list[str]]:
  args = ["grep", "-n", "-I"]
  for key in keys:
    args.extend(["-e", key])
  proc = run_git([
    *args, ref, "--",
    "common/params_keys.h",
    "selfdrive",
    "sunnypilot",
    "system",
  ])
  if proc.returncode not in (0, 1):
    return {key: [] for key in keys}

  hits = {key: [] for key in keys}
  for line in proc.stdout.splitlines():
    for key in keys:
      if key in line:
        hits[key].append(line)
  return hits


def parse_params(text: str) -> dict[str, dict[str, str]]:
  params: dict[str, dict[str, str]] = {}
  for line in text.splitlines():
    match = PARAM_RE.match(line)
    if not match:
      continue
    key = match.group("key")
    body = match.group("body")
    quoted = re.findall(r'"([^"]*)"', body)
    flags = body.split(",")
    default = quoted[-1] if quoted else None
    value_type = ""
    for part in flags:
      candidate = part.strip().strip("{}")
      if candidate in {"BOOL", "INT", "FLOAT", "STRING", "BYTES", "JSON"}:
        value_type = candidate
        break
    params[key] = {
      "type": value_type,
      "default": default if default is not None else "<none>",
      "raw": body.strip(),
    }
  return params


def truthy_default(value: str | None) -> bool:
  return value not in (None, "", "0", "false", "False", "<none>")


def summarize_refs() -> tuple[dict[str, Any], list[dict[str, Any]]]:
  refs: dict[str, Any] = {}
  findings: list[dict[str, Any]] = []

  for reference in REFERENCES:
    if not ref_exists(reference.ref):
      refs[reference.name] = {"available": False, "ref": reference.ref, "category": reference.category}
      continue

    params = parse_params(git_show(reference.ref, "common/params_keys.h"))
    hits = git_grep_keys(reference.ref, PARAM_KEYS)
    selected = {key: params[key] for key in PARAM_KEYS if key in params}
    refs[reference.name] = {
      "available": True,
      "ref": reference.ref,
      "category": reference.category,
      "params": selected,
      "hits": hits,
    }

    for key in ("SunnylinkEnabled", "OnroadUploads", "EnableSunnylinkUploader"):
      default = selected.get(key, {}).get("default")
      if truthy_default(default):
        findings.append({
          "severity": "block" if reference.name == "current-alpha" else "import_block",
          "group": "cloud_upload",
          "reference": reference.name,
          "key": key,
          "message": f"{key} defaults to {default}; personal alpha must keep cloud/upload services inert.",
        })

    if "EnableConnect" in selected or hits.get("EnableConnect"):
      findings.append({
        "severity": "review",
        "group": "cloud_upload",
        "reference": reference.name,
        "key": "EnableConnect",
        "message": "EnableConnect appears in this reference; do not expose it as a cloud-connect control in the personal alpha.",
      })

  return refs, findings


def diff_defaults(refs: dict[str, Any]) -> list[dict[str, Any]]:
  diffs: list[dict[str, Any]] = []
  for key in PARAM_KEYS:
    values: dict[str, list[str]] = {}
    for name, info in refs.items():
      if not info.get("available"):
        continue
      value = info.get("params", {}).get(key, {}).get("default", "<missing>")
      if key not in info.get("params", {}):
        value = "<missing>"
      values.setdefault(value, []).append(name)
    if len(values) > 1:
      diffs.append({"key": key, "defaults": values})
  return diffs


def group_presence(refs: dict[str, Any]) -> dict[str, Any]:
  groups: dict[str, Any] = {}
  for group, keys in CONFLICT_GROUPS.items():
    groups[group] = {}
    for name, info in refs.items():
      if not info.get("available"):
        continue
      hits = info.get("hits", {})
      present = [key for key in keys if key in info.get("params", {}) or hits.get(key)]
      groups[group][name] = present
  return groups


def current_policy_findings(refs: dict[str, Any]) -> list[dict[str, Any]]:
  findings: list[dict[str, Any]] = []
  current = refs.get("current-alpha", {})
  params = current.get("params", {})

  if params.get("DynamicExperimentalControl", {}).get("default") == "0":
    findings.append({
      "severity": "info",
      "group": "longitudinal_authority",
      "reference": "current-alpha",
      "key": "DynamicExperimentalControl",
      "message": "DEC is present and defaults off; it may be kept as a candidate advanced longitudinal mode if SCC-V/SCC-M/ICBM remain hidden or inert.",
    })
  else:
    findings.append({
      "severity": "block",
      "group": "longitudinal_authority",
      "reference": "current-alpha",
      "key": "DynamicExperimentalControl",
      "message": "DEC must exist with default 0 if retained.",
    })

  for key in ("SmartCruiseControlVision", "SmartCruiseControlMap", "IntelligentCruiseButtonManagement"):
    default = params.get(key, {}).get("default")
    if truthy_default(default):
      findings.append({
        "severity": "block",
        "group": "curve_map_speed",
        "reference": "current-alpha",
        "key": key,
        "message": f"{key} must not default on because it overlaps with Carrot cruise/speed behavior.",
      })

  for key in ("CarrotActiveSpeedControlEnabled", "CarrotAutoTurnControlEnabled", "CarrotTrafficStopEnabled", "FishopAutoOvertakeEnabled", "CarrotLearningAutoApply"):
    default = params.get(key, {}).get("default")
    if truthy_default(default):
      findings.append({
        "severity": "block",
        "group": "longitudinal_authority",
        "reference": "current-alpha",
        "key": key,
        "message": f"{key} must default off until staged vehicle evidence exists.",
      })

  return findings


def build_report() -> dict[str, Any]:
  refs, findings = summarize_refs()
  findings.extend(current_policy_findings(refs))
  report = {
    "title": "Genius Pilot C3 Settings Conflict Audit",
    "ok": not any(f["severity"] == "block" and f.get("reference") == "current-alpha" for f in findings),
    "references": refs,
    "defaultDifferences": diff_defaults(refs),
    "groups": group_presence(refs),
    "findings": findings,
    "policy": {
      "dec": "retain as off-by-default candidate; do not combine with unvalidated Carrot active speed/turn/traffic-stop outputs",
      "sccVisionMap": "keep hidden or inert; overlaps with Carrot curve/map/navigation speed control",
      "cloud": "cloud connect/upload params may exist as compatibility keys but must not start cloud processes or be user-facing",
      "offroad": "OffroadMode is the only supported parked maintenance semantics; avoid AlwaysOffline/AlwaysOffroad aliases",
    },
  }
  return report


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit setting conflicts across Genius Pilot, SunnyPilot, CarrotPilot, mechanical, and ESCC references.")
  parser.add_argument("--json", action="store_true", help="Print full JSON report")
  parser.add_argument("--strict", action="store_true", help="Exit non-zero if the current alpha violates blocking policy")
  args = parser.parse_args()

  report = build_report()
  if args.json:
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
  else:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"{status} {report['title']}")
    for finding in report["findings"]:
      print(f"{finding['severity'].upper()} {finding['group']} {finding['reference']} {finding['key']}: {finding['message']}")
    print(f"default differences: {len(report['defaultDifferences'])}")

  return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
  sys.exit(main())
