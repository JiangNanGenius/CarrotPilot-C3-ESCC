import os

from openpilot.common.basedir import BASEDIR

PINNED_TINYGRAD_REF = "66ee3cfb4f3a3908a6a20ddfbec7774ba7c09b4e"


def get_tinygrad_ref():
  repo_path = os.path.join(BASEDIR, "tinygrad_repo")
  ref_path = os.path.join(repo_path, "TINYGRAD_REF")
  if os.path.isfile(ref_path):
    with open(ref_path) as f:
      return f.read().strip()
  git_path = os.path.join(repo_path, ".git")
  try:
    if os.path.isdir(git_path):
      git_dir = git_path
    else:
      with open(git_path) as f:
        line = f.read().strip()
      git_dir = os.path.join(repo_path, line[8:])
    with open(os.path.join(git_dir, "HEAD")) as f:
      ref = f.read().strip()
    if ref.startswith("ref:"):
      with open(os.path.join(git_dir, ref.split(" ", 1)[1])) as f:
        return f.read().strip()
    return ref
  except Exception as e:
    print(f"Using vendored tinygrad ref after git metadata lookup failed: {e}")
    return PINNED_TINYGRAD_REF


def main():
  current_ref = get_tinygrad_ref()
  if current_ref:
    print(current_ref)
  else:
    print("")


if __name__ == "__main__":
  main()
