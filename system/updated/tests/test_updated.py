import pytest

from openpilot.common.params import Params
from openpilot.system.updated import updated
from openpilot.system.updated.updated import Updater


def test_stale_overlay_is_not_an_update_when_running_checkout_matches_remote(mocker):
  params = Params()
  params.put("UpdaterTargetBranch", "genius/c3")

  updater = Updater()
  updater.branches["genius/c3"] = "new-commit"

  mocker.patch.object(updated.os.path, "isdir", return_value=True)
  mocker.patch.object(
    updater,
    "get_branch",
    side_effect=lambda path: "genius/c3",
  )
  mocker.patch.object(
    updater,
    "get_commit_hash",
    side_effect=lambda path=updated.OVERLAY_MERGED: "new-commit" if path == updated.BASEDIR else "old-overlay",
  )

  try:
    assert not updater.update_available
  finally:
    params.remove("UpdaterTargetBranch")


@pytest.mark.parametrize("branch", ["release3", "release3-staging", "master", "genius/c3"])
def test_target_branch_is_owned(branch):
  params = Params()
  params.remove("UpdaterTargetBranch")
  params.put("UpdaterTargetBranch", branch)
  try:
    assert Updater().target_branch == updated.OWNED_BRANCH
  finally:
    params.remove("UpdaterTargetBranch")


def test_known_sunnypilot_origin_is_migrated(mocker):
  commands = []
  mocker.patch.object(updated, "run", side_effect=lambda cmd, cwd=None: (
    commands.append((cmd, cwd)) or "https://github.com/sunnypilot/sunnypilot.git\n"
  ) if cmd[:4] == ["git", "remote", "get-url", "origin"] else commands.append((cmd, cwd)) or "")

  assert updated.ensure_owned_remote("/tmp/repo") == updated.OWNED_REMOTE_URL
  assert (["git", "remote", "set-url", "origin", updated.OWNED_REMOTE_URL], "/tmp/repo") in commands


def test_unknown_origin_fails_closed(mocker):
  mocker.patch.object(updated, "run", return_value="https://example.com/other/repo.git\n")
  with pytest.raises(RuntimeError, match="unowned origin"):
    updated.ensure_owned_remote("/tmp/repo")
