import datetime

from openpilot.system import timed


class FakeParams:
  def __init__(self, values=None):
    self.values = values or {}
    self.writes = []

  def get(self, key):
    return self.values.get(key)

  def put(self, key, value):
    self.values[key] = value
    self.writes.append((key, value))


def dt(day=1, hour=0):
  return datetime.datetime(2026, 9, day, hour)


def test_restore_prefers_dedicated_checkpoint(mocker):
  params = FakeParams({
    timed.TIME_CHECKPOINT_PARAM: dt(1, 8),
    "LastUpdateTime": dt(1, 6),
    "UpdaterLastFetchTime": dt(1, 7),
  })
  mocker.patch.object(timed, "utc_now", return_value=dt(1, 5))
  set_time = mocker.patch.object(timed, "set_time", return_value=True)

  assert timed.restore_time_from_durable_state(params) == dt(1, 8)
  set_time.assert_called_once_with(dt(1, 8))


def test_checkpoint_is_rate_limited_and_never_moves_backwards():
  params = FakeParams()
  last = dt(1, 8)

  assert timed.update_time_checkpoint(params, last, dt(1, 8)) == last
  assert timed.update_time_checkpoint(params, last, dt(1, 8) + datetime.timedelta(minutes=59)) == last
  assert timed.update_time_checkpoint(params, last, dt(1, 7)) == last
  assert params.writes == []

  now = dt(1, 9)
  assert timed.update_time_checkpoint(params, last, now) == now
  assert params.writes == [(timed.TIME_CHECKPOINT_PARAM, now)]


def test_checkpoint_is_forced_at_drive_boundary():
  params = FakeParams()
  last = dt(1, 8)
  now = dt(1, 8) + datetime.timedelta(minutes=5)

  assert timed.update_time_checkpoint(params, last, now, force=True) == now
  assert params.values[timed.TIME_CHECKPOINT_PARAM] == now


def test_trusted_gps_can_replace_future_checkpoint():
  params = FakeParams()
  wrong_future = dt(2, 8)
  gps_time = dt(1, 8)

  assert timed.update_time_checkpoint(params, wrong_future, gps_time, force=True, trusted=True) == gps_time
  assert params.values[timed.TIME_CHECKPOINT_PARAM] == gps_time


def test_invalid_wall_time_is_not_persisted():
  params = FakeParams()
  invalid = datetime.datetime(1970, 1, 1)

  assert timed.update_time_checkpoint(params, None, invalid, force=True) is None
  assert params.writes == []
