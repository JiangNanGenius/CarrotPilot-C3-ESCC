from openpilot.selfdrive.controls.lib.stop_distance_settings import StopDistanceSettings, bounded_distance


class TestStopDistanceSettings:
  def test_bounds_and_invalid_values(self):
    for value in (None, 'invalid', float('nan'), float('inf')):
      assert bounded_distance(value, 6, 3, 12) == 6
    assert bounded_distance(100, 6, 3, 12) == 3
    assert bounded_distance(1500, 6, 3, 12) == 12
    assert bounded_distance(650, 6, 3, 12) == 6.5

  def test_defaults_and_refresh_preserve_store(self):
    params = {'TrafficStopDistanceAdjust': -150}
    settings = StopDistanceSettings(params)
    settings.update()
    assert (settings.follow, settings.traffic) == (6, 2)
    params.update(StopDistanceCarrot=800, TrafficStopBufferCm=400)
    for _ in range(100):
      settings.update()
    assert (settings.follow, settings.traffic) == (8, 4)
    assert params['TrafficStopDistanceAdjust'] == -150

    params['TrafficStopBufferCm'] = 5000
    for _ in range(100):
      settings.update()
    assert settings.traffic == 10
