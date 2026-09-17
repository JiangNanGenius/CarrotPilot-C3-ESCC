from openpilot.selfdrive.controls.lib.stop_distance_settings import StopDistanceSettings, bounded_distance


class TestStopDistanceSettings:
  def test_bounds_and_invalid_values(self):
    for value in (None, 'invalid', float('nan'), float('inf')):
      assert bounded_distance(value, 3.5, 2.5, 6) == 3.5
    assert bounded_distance(100, 3.5, 2.5, 6) == 2.5
    assert bounded_distance(1500, 3.5, 2.5, 6) == 6
    assert bounded_distance(350, 3.5, 2.5, 6) == 3.5

  def test_defaults_and_refresh_preserve_store(self):
    params = {'TrafficStopDistanceAdjust': -150}
    settings = StopDistanceSettings(params)
    settings.update()
    assert (settings.follow, settings.traffic) == (3.5, 2)
    params.update(StopDistanceCarrot=500, TrafficStopBufferCm=400)
    for _ in range(100):
      settings.update()
    assert (settings.follow, settings.traffic) == (5, 4)
    assert params['TrafficStopDistanceAdjust'] == -150

    params['TrafficStopBufferCm'] = 5000
    for _ in range(100):
      settings.update()
    assert settings.traffic == 10
