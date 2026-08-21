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


@pytest.mark.parametrize(("device_type", "branch", "expected"), [
  ("tizi", "release3", "release-tizi"),
  ("tizi", "release3-staging", "release-tizi-staging"),
  ("mici", "release3", "release-mici"),
  ("mici", "release3-staging", "release-mici-staging"),
])
def test_target_branch_migration_from_current_branch(mocker, device_type, branch, expected):
  params = Params()
  params.remove("UpdaterTargetBranch")

  mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)
  mocker.patch.object(Updater, "get_branch", return_value=branch)

  assert Updater().target_branch == expected


@pytest.mark.parametrize(("device_type", "branch", "expected"), [
  ("tizi", "release3", "release-tizi"),
  ("tizi", "release3-staging", "release-tizi-staging"),
  ("mici", "release3", "release-mici"),
  ("mici", "release3-staging", "release-mici-staging"),
])
def test_target_branch_migration_from_param(mocker, device_type, branch, expected):
  params = Params()
  params.put("UpdaterTargetBranch", branch)

  mocker.patch("openpilot.system.updated.updated.HARDWARE.get_device_type", return_value=device_type)

  try:
    assert Updater().target_branch == expected
  finally:
    params.remove("UpdaterTargetBranch")
