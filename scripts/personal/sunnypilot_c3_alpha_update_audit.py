#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
AUDIT_REF_PREFIX = "refs/remotes/carrot-audit"


@dataclass(frozen=True)
class Reference:
  name: str
  url: str
  branch: str
  category: str
  required: bool
  note: str

  @property
  def local_ref(self) -> str:
    return f"{AUDIT_REF_PREFIX}/{safe_ref_name(self.name)}"


REFERENCES = (
  Reference(
    "sunnypilot-staging",
    "https://github.com/sunnypilot/sunnypilot.git",
    "staging",
    "base",
    True,
    "alpha base; compare architecture, model manager, UI, speed-limit, and process changes",
  ),
  Reference(
    "sunnypilot-release-tizi",
    "https://github.com/sunnypilot/sunnypilot.git",
    "release-tizi",
    "c3",
    False,
    "TIZI/C3 release reference; compare installer and device compatibility behavior",
  ),
  Reference(
    "ajouatom-carrot-wip",
    "https://github.com/ajouatom/openpilot.git",
    "carrot-wip",
    "carrot",
    True,
    "CarrotPilot main work branch; compare Carrot features, maps, route, speed, and model behavior",
  ),
  Reference(
    "ajouatom-c3-wip",
    "https://github.com/ajouatom/openpilot.git",
    "c3-wip",
    "carrot-c3",
    False,
    "Carrot C3 work branch; reference only for C3 adaptation details",
  ),
  Reference(
    "jixiexiaoge-master",
    "https://github.com/jixiexiaoge/openpilot.git",
    "master",
    "mechanical",
    True,
    "mechanical/Auto-Tuner primary branch; compare Auto-Tuner, APN/N, local Web, fishop hardware",
  ),
  Reference(
    "jixiexiaoge-atune",
    "https://github.com/jixiexiaoge/openpilot.git",
    "atune",
    "mechanical-atune",
    False,
    "Auto-Tuner focused branch; compare learner defaults and apply safety",
  ),
  Reference(
    "jixiexiaoge-cp",
    "https://github.com/jixiexiaoge/openpilot.git",
    "CP",
    "mechanical-carrot",
    False,
    "mechanical Carrot branch; compare CP搭子/Navipilot/APN/N and fishop fields",
  ),
  Reference(
    "jixiexiaoge-release-new",
    "https://github.com/jixiexiaoge/openpilot.git",
    "release-new",
    "mechanical-release",
    False,
    "newer release branch; compare model/speed/UI deltas when planning alpha promotions",
  ),
  Reference(
    "dhvms-carrotpilot-master",
    "https://github.com/dhvms/carrotpilot.git",
    "master",
    "escc",
    False,
    "ESCC reference fork; compare enhanced SCC behavior without importing unrelated changes blindly",
  ),
)


WATCHED_PATHS = (
  "AGENTS.md",
  "launch_openpilot.sh",
  "launch_chffrplus.sh",
  "launch_env.sh",
  "common/params_keys.h",
  "cereal/custom.capnp",
  "cereal/services.py",
  "selfdrive/carrot",
  "selfdrive/modeld",
  "selfdrive/pandad",
  "selfdrive/ui/installer",
  "selfdrive/ui/layouts",
  "selfdrive/ui/mici/layouts",
  "selfdrive/ui/sunnypilot",
  "selfdrive/ui/translations",
  "sunnypilot/modeld_v2",
  "sunnypilot/models",
  "sunnypilot/selfdrive/controls/lib/speed_limit",
  "sunnypilot/selfdrive/controls/lib/longitudinal_planner.py",
  "sunnypilot/system/hardware/c3",
  "system/hardware",
  "system/manager/process_config.py",
  "system/updated",
  "system/version.py",
  "opendbc_repo/opendbc/car/hyundai",
  "opendbc_repo/opendbc/sunnypilot/car/hyundai",
)


RISK_TOKENS = (
  "manage_athenad",
  "uploader",
  "manage_sunnylinkd",
  "sunnylink_registration_manager",
  "statsd_sp",
  "backup_manager",
  "SunnylinkEnabled",
  "OnroadUploads",
  "device_client",
  "private_registration",
  "mr-one.cn",
  "op.mr-one",
  "NeverShutdown",
  "DisableShutdown",
)


def command_env() -> dict[str, str]:
  env = os.environ.copy()
  env.setdefault("GIT_TERMINAL_PROMPT", "0")
  env.setdefault("GIT_OPTIONAL_LOCKS", "0")
  return env


def run_git(args: Sequence[str], timeout_s: int = 60) -> tuple[int, str]:
  try:
    proc = subprocess.run(
      ["git", "-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
      cwd=ROOT,
      env=command_env(),
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      check=False,
      timeout=timeout_s,
    )
    return proc.returncode, proc.stdout.strip()
  except subprocess.TimeoutExpired as exc:
    output = ((exc.stdout or "") + (exc.stderr or "")).strip()
    return 124, f"git {' '.join(args)} timed out after {timeout_s}s\n{output}".strip()
  except OSError as exc:
    return 127, str(exc)


def safe_ref_name(name: str) -> str:
  return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def ls_remote(ref: Reference) -> dict[str, Any]:
  code, output = run_git(["ls-remote", ref.url, f"refs/heads/{ref.branch}"], timeout_s=45)
  commit = ""
  if code == 0 and output:
    first = output.splitlines()[0].split()
    if len(first) >= 2:
      commit = first[0]
  return {
    "ok": code == 0 and bool(commit),
    "commit": commit,
    "error": "" if code == 0 and commit else output[-400:],
  }


def fetch_reference(ref: Reference) -> dict[str, Any]:
  refspec = f"+refs/heads/{ref.branch}:{ref.local_ref}"
  code, output = run_git(["fetch", "--no-tags", "--depth=1", ref.url, refspec], timeout_s=180)
  return {
    "ok": code == 0,
    "localRef": ref.local_ref,
    "error": "" if code == 0 else output[-800:],
  }


def local_ref_commit(local_ref: str) -> dict[str, Any]:
  code, output = run_git(["rev-parse", "--verify", f"{local_ref}^{{commit}}"], timeout_s=30)
  return {
    "ok": code == 0,
    "commit": output.splitlines()[0] if code == 0 and output else "",
    "error": "" if code == 0 else output[-400:],
  }


def diff_watched(local_ref: str, max_lines: int) -> dict[str, Any]:
  code, _ = run_git(["merge-base", "--is-ancestor", local_ref, "HEAD"], timeout_s=30)
  range_expr = f"{local_ref}..HEAD" if code == 0 else f"{local_ref}...HEAD"
  diff_code, output = run_git(["diff", "--name-status", range_expr, "--", *WATCHED_PATHS], timeout_s=90)
  if diff_code != 0:
    range_expr = f"{local_ref}..HEAD"
    diff_code, output = run_git(["diff", "--name-status", range_expr, "--", *WATCHED_PATHS], timeout_s=90)
  lines = [line for line in output.splitlines() if line.strip()] if diff_code == 0 else []
  return {
    "ok": diff_code == 0,
    "range": range_expr,
    "changeCount": len(lines),
    "changedFiles": lines[:max_lines],
    "truncated": len(lines) > max_lines,
    "error": "" if diff_code == 0 else output[-800:],
  }


def grep_risk_tokens(local_ref: str, max_hits: int) -> dict[str, Any]:
  hits: list[str] = []
  for token in RISK_TOKENS:
    code, output = run_git(
      ["grep", "-n", "-I", "--fixed-strings", token, local_ref, "--", *WATCHED_PATHS],
      timeout_s=45,
    )
    if code == 0:
      for line in output.splitlines():
        hits.append(line[:240])
        if len(hits) >= max_hits:
          return {"ok": True, "hitCount": len(hits), "hits": hits, "truncated": True}
    elif code not in (1,):
      return {"ok": False, "hitCount": len(hits), "hits": hits, "truncated": False, "error": output[-400:]}
  return {"ok": True, "hitCount": len(hits), "hits": hits, "truncated": False}


def audit_reference(ref: Reference, args: argparse.Namespace) -> dict[str, Any]:
  remote = ls_remote(ref) if not args.skip_network else {"ok": False, "commit": "", "error": "network skipped"}
  fetch = {"ok": False, "localRef": ref.local_ref, "error": "fetch skipped"}
  if args.fetch:
    fetch = fetch_reference(ref)

  local = local_ref_commit(ref.local_ref)
  diff = diff_watched(ref.local_ref, args.max_diff_lines) if local["ok"] else {
    "ok": False,
    "range": "",
    "changeCount": 0,
    "changedFiles": [],
    "truncated": False,
    "error": "local reference missing; run with --fetch",
  }
  risk = grep_risk_tokens(ref.local_ref, args.max_risk_hits) if local["ok"] and args.scan_risk_tokens else {
    "ok": True,
    "hitCount": 0,
    "hits": [],
    "truncated": False,
    "skipped": not args.scan_risk_tokens,
  }

  ok = (remote["ok"] or args.skip_network) and (fetch["ok"] if args.fetch else True) and (local["ok"] or not args.require_local_refs)
  if ref.required and args.strict:
    ok = ok and (local["ok"] or fetch["ok"])

  return {
    "name": ref.name,
    "category": ref.category,
    "url": ref.url,
    "branch": ref.branch,
    "required": ref.required,
    "note": ref.note,
    "localRef": ref.local_ref,
    "ok": ok,
    "remote": remote,
    "fetch": fetch,
    "local": local,
    "diff": diff,
    "riskTokens": risk,
  }


def selected_references(names: Iterable[str]) -> tuple[Reference, ...]:
  requested = set(names)
  if not requested:
    return REFERENCES
  known = {ref.name: ref for ref in REFERENCES}
  missing = sorted(requested - set(known))
  if missing:
    raise SystemExit(f"unknown reference name(s): {', '.join(missing)}")
  return tuple(known[name] for name in names)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
  refs = [audit_reference(ref, args) for ref in selected_references(args.reference)]
  required_refs = [ref for ref in refs if ref["required"]]
  failed_required = [ref["name"] for ref in required_refs if not ref["ok"]]
  risk_hits = {ref["name"]: ref["riskTokens"]["hitCount"] for ref in refs if ref["riskTokens"].get("hitCount", 0)}
  return {
    "title": "CarrotPilot-C3-ESCC Alpha Update Audit",
    "ok": not failed_required,
    "strict": args.strict,
    "fetch": args.fetch,
    "watchPathCount": len(WATCHED_PATHS),
    "riskTokenCount": len(RISK_TOKENS),
    "failedRequired": failed_required,
    "riskHitsByReference": risk_hits,
    "references": refs,
    "policy": {
      "base": "SunnyPilot staging remains the alpha base unless explicitly changed",
      "mrone": "Mr.One is C3/TICI reference-only; do not import private registration, upload, cloud, never-shutdown, or broad safety/opendbc changes",
      "cloud": "Sunnylink/comma cloud/upload services stay removed or inert",
      "car": "Kia Seltos 2023 SCC pure CAN stays the first real-car target",
    },
  }


def print_report(report: dict[str, Any], as_json: bool) -> None:
  if as_json:
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return
  print(f"{'PASS' if report['ok'] else 'FAIL'} {report['title']}")
  for ref in report["references"]:
    status = "PASS" if ref["ok"] else "FAIL"
    local = ref["local"]["commit"][:12] if ref["local"].get("commit") else "missing"
    remote = ref["remote"]["commit"][:12] if ref["remote"].get("commit") else "unknown"
    print(f"{status} {ref['name']} branch={ref['branch']} local={local} remote={remote} changes={ref['diff']['changeCount']}")
    if not ref["ok"]:
      detail = ref["fetch"].get("error") or ref["local"].get("error") or ref["remote"].get("error")
      if detail:
        print(detail)


def self_test() -> int:
  refs = {ref.name: ref for ref in REFERENCES}
  for required in ("sunnypilot-staging", "ajouatom-carrot-wip", "jixiexiaoge-master"):
    if required not in refs or not refs[required].required:
      return 1
  for optional in ("jixiexiaoge-atune", "jixiexiaoge-cp", "dhvms-carrotpilot-master"):
    if optional not in refs:
      return 1
  if selected_references(["sunnypilot-staging"])[0].branch != "staging":
    return 1
  if "system/manager/process_config.py" not in WATCHED_PATHS:
    return 1
  if "manage_athenad" not in RISK_TOKENS or "NeverShutdown" not in RISK_TOKENS:
    return 1
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Fetch and compare upstream references for CarrotPilot-C3-ESCC alpha updates.")
  parser.add_argument("--fetch", action="store_true", help="fetch configured reference branches into refs/remotes/carrot-audit/*")
  parser.add_argument("--strict", action="store_true", help="fail when required references cannot be audited")
  parser.add_argument("--require-local-refs", action="store_true", help="fail when local audit refs are missing")
  parser.add_argument("--skip-network", action="store_true", help="skip ls-remote checks")
  parser.add_argument("--scan-risk-tokens", action="store_true", help="scan reference branches for cloud/private/power-risk tokens")
  parser.add_argument("--reference", action="append", default=[], help="limit audit to one configured reference name")
  parser.add_argument("--max-diff-lines", type=int, default=80, help="maximum watched diff lines per reference")
  parser.add_argument("--max-risk-hits", type=int, default=40, help="maximum risk-token hits per reference")
  parser.add_argument("--json", action="store_true", help="print JSON report")
  parser.add_argument("--self-test", action="store_true", help="run an offline self-test")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report = build_report(args)
  print_report(report, args.json)
  return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
  raise SystemExit(main())
