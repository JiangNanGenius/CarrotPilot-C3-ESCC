#!/usr/bin/env python3
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path
from typing import Optional


TEMPLATE_URL = (
  "https://raw.githubusercontent.com/sshane/openpilot-installer-generator/"
  "b397447deb4b18115c6ac9c2e967822d557da95d/fork/installer_openpilot_agnos"
)
TEMPLATE_SHA256 = "94aa793a33dee223abd127a3c1b1e4eb42f4d2834b6a16adab931cf2442cd6ba"

REPO_PLACEHOLDER = b"27182818284590452353602874713526624977572470936999595"
BRANCH_PLACEHOLDER = (
  b"161803398874989484820458683436563811772030917980576286213544862270526046281890244970720720418939113748475408807538689175212663386222353693179318006076672635443338908659593958290563832266131992829026788067520876689250171169620703222104321626954862629631361"
)
LOADING_PLACEHOLDER = b"314159265358979323846264338327950288419"

DEFAULT_REPO_PATH = "JiangNanGenius/CarrotPilot-C3-ESCC.git"
DEFAULT_BRANCH = "install-c3-escc-test"
DEFAULT_LOADING = "CarrotPilot-C3-ESCC"


class InstallerBuildError(Exception):
  pass


def fill_placeholder(binary: bytes, placeholder: bytes, value: str, padding: bytes, label: str) -> bytes:
  encoded = value.encode("utf-8")
  if len(encoded) > len(placeholder):
    raise InstallerBuildError(
      f"{label} is too long for the binary template: {len(encoded)} > {len(placeholder)}"
    )
  replacement = encoded + padding * (len(placeholder) - len(encoded))
  if placeholder not in binary:
    raise InstallerBuildError(f"{label} placeholder is missing from the template")
  return binary.replace(placeholder, replacement)


def download_template() -> bytes:
  with urllib.request.urlopen(TEMPLATE_URL, timeout=30) as resp:
    return resp.read()


def read_template(path: Optional[Path]) -> bytes:
  data = path.read_bytes() if path else download_template()
  digest = hashlib.sha256(data).hexdigest()
  if digest != TEMPLATE_SHA256:
    raise InstallerBuildError(
      f"unexpected AGNOS installer template sha256: {digest}; expected {TEMPLATE_SHA256}"
    )
  return data


def build_installer(template: bytes, repo_path: str, branch: str, loading: str) -> bytes:
  if repo_path.startswith("https://github.com/"):
    repo_path = repo_path.removeprefix("https://github.com/")
  if not repo_path.endswith(".git"):
    repo_path += ".git"
  if "/" not in repo_path:
    raise InstallerBuildError("repo path must look like owner/repo.git")
  if not branch:
    raise InstallerBuildError("branch must be non-empty")
  if "/" in branch:
    raise InstallerBuildError("use a short branch without slashes for the setup installer")
  if not loading:
    raise InstallerBuildError("loading message must be non-empty")

  binary = fill_placeholder(template, REPO_PLACEHOLDER, repo_path, b"\0", "repo path")
  binary = fill_placeholder(binary, BRANCH_PLACEHOLDER, branch, b"\0", "branch")
  binary = fill_placeholder(binary, LOADING_PLACEHOLDER, loading, b" ", "loading message")
  return binary


def assert_no_placeholder(binary: bytes) -> None:
  for label, placeholder in {
    "repo": REPO_PLACEHOLDER,
    "branch": BRANCH_PLACEHOLDER,
    "loading": LOADING_PLACEHOLDER,
  }.items():
    if placeholder in binary:
      raise InstallerBuildError(f"{label} placeholder still present in output")


def self_test() -> None:
  fake = b"|".join([REPO_PLACEHOLDER, BRANCH_PLACEHOLDER, BRANCH_PLACEHOLDER, LOADING_PLACEHOLDER])
  built = build_installer(fake, DEFAULT_REPO_PATH, DEFAULT_BRANCH, DEFAULT_LOADING)
  assert_no_placeholder(built)
  if DEFAULT_REPO_PATH.encode("utf-8") not in built:
    raise InstallerBuildError("self-test output missing repo path")
  if built.count(DEFAULT_BRANCH.encode("utf-8")) != 2:
    raise InstallerBuildError("self-test output missing branch replacements")
  if DEFAULT_LOADING.encode("utf-8") not in built:
    raise InstallerBuildError("self-test output missing loading message")


def main() -> int:
  parser = argparse.ArgumentParser(description="Build a C3 AGNOS binary installer from the Qt setup template.")
  parser.add_argument("--repo-path", default=DEFAULT_REPO_PATH, help="GitHub repo path, e.g. owner/repo.git")
  parser.add_argument("--branch", default=DEFAULT_BRANCH, help="Install branch. Tags are not recommended.")
  parser.add_argument("--loading", default=DEFAULT_LOADING, help="Installer loading message")
  parser.add_argument("--template", type=Path, help="Local installer_openpilot_agnos template")
  parser.add_argument("--output", type=Path, help="Output binary path")
  parser.add_argument("--self-test", action="store_true", help="Run placeholder replacement self-test")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("binary installer builder self-test: OK")
      return 0

    if args.output is None:
      raise InstallerBuildError("--output is required unless --self-test is used")

    template = read_template(args.template)
    binary = build_installer(template, args.repo_path, args.branch, args.loading)
    assert_no_placeholder(binary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(binary)
    args.output.chmod(0o755)
    print(f"wrote {args.output}")
    print(f"repo path: {args.repo_path}")
    print(f"branch: {args.branch}")
    print(f"loading: {args.loading}")
    print(f"sha256: {hashlib.sha256(binary).hexdigest()}")
    return 0
  except InstallerBuildError as exc:
    print(f"binary installer build failed: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
