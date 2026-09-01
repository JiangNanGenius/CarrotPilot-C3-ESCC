import os
import pytest
import signal
import time

from cereal import car
from openpilot.common.params import Params
import openpilot.system.manager.manager as manager
from openpilot.system.manager.process import ensure_running
from openpilot.system.manager.process_config import managed_processes, procs
from openpilot.system.hardware import HARDWARE

os.environ['FAKEUPLOAD'] = "1"

MAX_STARTUP_TIME = 3
BLACKLIST_PROCS = ['manage_athenad', 'pandad', 'pigeond']


class TestManager:
  def setup_method(self):
    HARDWARE.set_power_save(False)

    # ensure clean CarParams
    params = Params()
    params.clear_all()

  def teardown_method(self):
    manager.manager_cleanup()

  def test_manager_prepare(self):
    os.environ['PREPAREONLY'] = '1'
    manager.main()

  def test_duplicate_procs(self):
    assert len(procs) == len(managed_processes), "Duplicate process names"

  def test_legacy_carrot_migration_runs_before_param_clear(self, monkeypatch):
    calls = []

    class FakeParams:
      def clear_all(self, flag):
        calls.append(("clear", flag))

    monkeypatch.setattr(manager, "PC", False)
    monkeypatch.setattr(manager, "migrate_legacy_carrot_params", lambda params: calls.append(("migrate", params)))
    params = FakeParams()

    manager.migrate_and_clear_params(params)

    assert calls[0] == ("migrate", params)
    assert [call[0] for call in calls[1:]] == ["clear"] * 4

  def test_legacy_carrot_migration_failure_does_not_block_param_clear(self, monkeypatch):
    calls = []

    class FakeParams:
      def clear_all(self, flag):
        calls.append(flag)

    def fail_migration(_params):
      raise OSError("migration failed")

    monkeypatch.setattr(manager, "PC", False)
    monkeypatch.setattr(manager, "migrate_legacy_carrot_params", fail_migration)
    monkeypatch.setattr(manager.cloudlog, "exception", lambda message: None)

    manager.migrate_and_clear_params(FakeParams())

    assert len(calls) == 4

  def test_time_restore_precedes_bootlog(self, monkeypatch):
    calls = []
    params = object()

    class StopAfterBootlog(Exception):
      pass

    monkeypatch.setattr(manager, "PC", False)
    monkeypatch.setattr(manager, "Params", lambda: params)
    monkeypatch.setattr(manager, "restore_time_from_durable_state",
                        lambda actual: calls.append(("restore_time", actual)))

    def stop_after_bootlog():
      calls.append(("bootlog", None))
      raise StopAfterBootlog

    monkeypatch.setattr(manager, "save_bootlog", stop_after_bootlog)

    with pytest.raises(StopAfterBootlog):
      manager.manager_init()

    assert calls == [("restore_time", params), ("bootlog", None)]

  def test_early_time_restore_is_best_effort_and_device_only(self, monkeypatch):
    params = object()
    calls = []

    monkeypatch.setattr(manager, "PC", True)
    monkeypatch.setattr(manager, "restore_time_from_durable_state", lambda actual: calls.append(actual))
    manager.restore_time_before_process_start(params)
    assert calls == []

    def fail_restore(_params):
      raise OSError("bad checkpoint")

    monkeypatch.setattr(manager, "PC", False)
    monkeypatch.setattr(manager, "restore_time_from_durable_state", fail_restore)
    monkeypatch.setattr(manager.cloudlog, "exception", lambda message: calls.append(message))
    manager.restore_time_before_process_start(params)

    assert calls == ["manager failed to restore system time before process start"]

  def test_blacklisted_procs(self):
    # TODO: ensure there are blacklisted procs until we have a dedicated test
    assert len(BLACKLIST_PROCS), "No blacklisted procs to test not_run"

  def test_set_params_with_default_value(self):
    params = Params()
    params.clear_all()

    os.environ['PREPAREONLY'] = '1'
    manager.main()
    for k in params.all_keys():
      default_value = params.get_default_value(k)
      if default_value is not None:
        assert params.get(k) == default_value
    assert params.get("OpenpilotEnabledToggle")
    assert params.get("RouteCount") == 0

  @pytest.mark.skip("this test is flaky the way it's currently written, should be moved to test_onroad")
  def test_clean_exit(self, subtests):
    """
      Ensure all processes exit cleanly when stopped.
    """
    HARDWARE.set_power_save(False)
    manager.manager_init()

    CP = car.CarParams.new_message()
    procs = ensure_running(managed_processes.values(), True, Params(), CP, not_run=BLACKLIST_PROCS)

    time.sleep(10)

    for p in procs:
      with subtests.test(proc=p.name):
        state = p.get_process_state_msg()
        assert state.running, f"{p.name} not running"
        exit_code = p.stop(retry=False)

        assert p.name not in BLACKLIST_PROCS, f"{p.name} was started"

        assert exit_code is not None, f"{p.name} failed to exit"

        # TODO: interrupted blocking read exits with 1 in cereal. use a more unique return code
        exit_codes = [0, 1]
        if p.sigkill:
          exit_codes = [-signal.SIGKILL]
        assert exit_code in exit_codes, f"{p.name} died with {exit_code}"
