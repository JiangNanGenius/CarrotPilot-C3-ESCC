#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/personal/INSTALL_TARGETS.json"
INSTALLER_SCRIPT = ROOT / "scripts/personal/install_c3_escc.sh"
DEFAULT_REPO = "JiangNanGenius/CarrotPilot-C3-ESCC"
DEFAULT_INSTALL_BRANCH = "install-c3-escc-test"
TAG_RE = re.compile(r"^carrotpilot-c3-escc-(\d{8})-(static|test|stable)(\d*)$")
DEFAULT_REF_RE = re.compile(r'^DEFAULT_REF="([^"]+)"$', re.M)
REQUIRED_TEST_ASSETS = {
  "installer_c3_escc": "application/octet-stream",
  "install_c3_escc.sh": "application/x-sh",
}


class ReleaseIntegrityError(Exception):
  pass


def git(args: Sequence[str], check: bool = False) -> Tuple[int, str]:
  proc = subprocess.run(
    ["git", *args],
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  output = proc.stdout.strip()
  if check and proc.returncode != 0:
    raise ReleaseIntegrityError(f"git {' '.join(args)} failed:\n{output}")
  return proc.returncode, output


def load_manifest() -> Dict[str, Any]:
  try:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
  except Exception as exc:
    raise ReleaseIntegrityError(f"cannot read {MANIFEST.relative_to(ROOT)}: {exc}") from exc
  if not isinstance(data, dict):
    raise ReleaseIntegrityError("install target manifest must be a JSON object")
  return data


def current_test_tag(data: Dict[str, Any]) -> str:
  tag = data.get("current_test_tag")
  if not isinstance(tag, str) or not tag:
    raise ReleaseIntegrityError("current_test_tag must be a non-empty string")
  match = TAG_RE.match(tag)
  if not match or match.group(2) != "test":
    raise ReleaseIntegrityError(f"current_test_tag is not a test tag: {tag}")
  return tag


def require_commit(ref: str, label: str) -> str:
  code, output = git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
  if code != 0 or not output:
    raise ReleaseIntegrityError(f"{label} does not resolve to a commit: {ref}")
  return output


def read_script_default_ref() -> str:
  text = INSTALLER_SCRIPT.read_text(encoding="utf-8")
  match = DEFAULT_REF_RE.search(text)
  if not match:
    raise ReleaseIntegrityError(f"{INSTALLER_SCRIPT.relative_to(ROOT)} is missing DEFAULT_REF")
  return match.group(1)


def remote_target(remote: str, repo: str) -> str:
  code, output = git(["remote", "get-url", remote])
  if code == 0 and output:
    return remote
  return f"https://github.com/{repo}.git"


def ls_remote_commit(remote: str, repo: str, ref: str) -> str:
  target = remote_target(remote, repo)
  code, output = git(["ls-remote", target, ref])
  if code != 0:
    raise ReleaseIntegrityError(f"git ls-remote failed for {target} {ref}:\n{output}")
  lines = [line for line in output.splitlines() if line.strip()]
  if not lines:
    raise ReleaseIntegrityError(f"remote ref is missing: {target} {ref}")
  first = lines[0].split()
  if len(first) < 2:
    raise ReleaseIntegrityError(f"unexpected ls-remote output for {ref}: {output}")
  return first[0]


def github_json(url: str, token: Optional[str]) -> Dict[str, Any]:
  headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "CarrotPilot-C3-ESCC-release-check",
  }
  if token:
    headers["Authorization"] = f"Bearer {token}"
  request = urllib.request.Request(url, headers=headers)
  try:
    with urllib.request.urlopen(request, timeout=20) as response:
      raw = response.read().decode("utf-8")
  except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    raise ReleaseIntegrityError(f"GitHub API returned HTTP {exc.code} for {url}:\n{body}") from exc
  except urllib.error.URLError as exc:
    raise ReleaseIntegrityError(f"GitHub API request failed for {url}: {exc}") from exc
  data = json.loads(raw)
  if not isinstance(data, dict):
    raise ReleaseIntegrityError("GitHub API release response must be an object")
  return data


def assets_by_name(release: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
  assets = release.get("assets")
  if not isinstance(assets, list):
    raise ReleaseIntegrityError("GitHub release response missing assets list")
  result: Dict[str, Dict[str, Any]] = {}
  for asset in assets:
    if not isinstance(asset, dict):
      continue
    name = asset.get("name")
    if isinstance(name, str):
      result[name] = asset
  return result


def require_release_assets(release: Dict[str, Any], required: Dict[str, str]) -> List[str]:
  assets = assets_by_name(release)
  digests: List[str] = []
  for name, content_type in required.items():
    asset = assets.get(name)
    if not asset:
      raise ReleaseIntegrityError(f"release asset is missing: {name}")
    size = asset.get("size")
    if not isinstance(size, int) or size <= 0:
      raise ReleaseIntegrityError(f"release asset has invalid size: {name}")
    actual_type = asset.get("content_type") or asset.get("contentType")
    if actual_type and actual_type != content_type:
      raise ReleaseIntegrityError(f"release asset {name} content type is {actual_type}, expected {content_type}")
    digest = asset.get("digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
      digests.append(f"{name} {digest}")
  return digests


def require_no_extra_daily_target(data: Dict[str, Any]) -> None:
  if data.get("current_stable_tag") is None and data.get("daily_install_target") is not None:
    raise ReleaseIntegrityError("daily_install_target must stay null until stable exists")


def check_local(tag: str, data: Dict[str, Any]) -> str:
  require_no_extra_daily_target(data)
  tag_commit = require_commit(f"refs/tags/{tag}", "current_test_tag")
  script_ref = read_script_default_ref()
  if script_ref != tag:
    raise ReleaseIntegrityError(f"installer script DEFAULT_REF is {script_ref}, expected {tag}")
  return tag_commit


def check_online(tag: str, tag_commit: str, repo: str, remote: str, install_branch: str) -> List[str]:
  branch_commit = ls_remote_commit(remote, repo, f"refs/heads/{install_branch}")
  if branch_commit != tag_commit:
    raise ReleaseIntegrityError(
      f"{install_branch} points to {branch_commit}, expected release tag commit {tag_commit}"
    )

  tag_ref = ls_remote_commit(remote, repo, f"refs/tags/{tag}^{{}}")
  if tag_ref != tag_commit:
    raise ReleaseIntegrityError(f"remote tag {tag} resolves to {tag_ref}, expected {tag_commit}")

  token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
  release = github_json(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", token)
  if release.get("draft") is True:
    raise ReleaseIntegrityError("GitHub release is still a draft")
  if release.get("prerelease") is not True:
    raise ReleaseIntegrityError("test release should be marked as prerelease")
  return require_release_assets(release, REQUIRED_TEST_ASSETS)


def self_test() -> None:
  fake_release = {
    "draft": False,
    "prerelease": True,
    "assets": [
      {
        "name": "installer_c3_escc",
        "size": 217288,
        "content_type": "application/octet-stream",
        "digest": "sha256:" + "0" * 64,
      },
      {
        "name": "install_c3_escc.sh",
        "size": 6321,
        "content_type": "application/x-sh",
        "digest": "sha256:" + "1" * 64,
      },
    ],
  }
  digests = require_release_assets(fake_release, REQUIRED_TEST_ASSETS)
  if len(digests) != 2:
    raise ReleaseIntegrityError("self-test did not collect both asset digests")
  bad_release = {"draft": False, "prerelease": True, "assets": []}
  try:
    require_release_assets(bad_release, REQUIRED_TEST_ASSETS)
  except ReleaseIntegrityError:
    pass
  else:
    raise ReleaseIntegrityError("self-test failed to reject missing assets")


def main() -> int:
  parser = argparse.ArgumentParser(description="Verify personal C3 ESCC release/install integrity.")
  parser.add_argument("--tag", help="release tag to check; defaults to current_test_tag")
  parser.add_argument("--online", action="store_true", help="also check remote install branch and GitHub release assets")
  parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repo")
  parser.add_argument("--remote", default="github", help="git remote name, or fallback to https://github.com/<repo>.git")
  parser.add_argument("--install-branch", default=DEFAULT_INSTALL_BRANCH, help="binary installer branch")
  parser.add_argument("--self-test", action="store_true", help="run internal parser checks without network")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("OK: release integrity self-test passed")
      return 0

    data = load_manifest()
    tag = args.tag or current_test_tag(data)
    tag_commit = check_local(tag, data)
    print("Release integrity check")
    print(f"repo: {ROOT}")
    print(f"tag: {tag}")
    print(f"tag commit: {tag_commit}")
    print(f"installer script ref: {read_script_default_ref()}")
    if args.online:
      digests = check_online(tag, tag_commit, args.repo, args.remote, args.install_branch)
      print(f"install branch: {args.install_branch}")
      for digest in digests:
        print(f"asset digest: {digest}")
    else:
      print("online checks: skipped")
    print("OK: release/install targets are aligned")
    return 0
  except ReleaseIntegrityError as exc:
    print("release integrity check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
