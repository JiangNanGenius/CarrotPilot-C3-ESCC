import pytest

from openpilot.selfdrive.controls.lib.cruise_target_policy import CruiseTargetPolicy


class TestCruiseTargetPolicy:
  def setup_method(self):
    self.policy = CruiseTargetPolicy()
    self.inputs = dict(ceiling=80 / 3.6, road_limit=40 / 3.6,
                       speed=40 / 3.6, gas=False, brake=False,
                       engaged=True, standstill=False)
    self.update()

  def update(self, **kwargs):
    self.inputs.update(kwargs)
    return self.policy.update(**self.inputs) * 3.6

  def override(self):
    self.update(gas=True, speed=70 / 3.6)
    return self.update(gas=False, speed=60 / 3.6)

  def test_ceiling_does_not_raise_road_target(self):
    assert self.update(ceiling=100 / 3.6) == pytest.approx(40)

  def test_release_not_peak_and_repeated_limit(self):
    assert self.override() == pytest.approx(60)
    assert self.update(speed=45 / 3.6) == pytest.approx(60)
    assert self.update(road_limit=40 / 3.6 + 1e-7) == pytest.approx(60)

  def test_new_limit_wins_over_release(self):
    self.update(gas=True, speed=70 / 3.6)
    assert self.update(gas=False, road_limit=50 / 3.6) == pytest.approx(50)
    assert self.policy.override is None

  def test_lower_ceiling_permanently_clips_override(self):
    self.override()
    assert self.update(ceiling=50 / 3.6) == pytest.approx(50)
    assert self.update(ceiling=80 / 3.6) == pytest.approx(50)

  def test_reset_conditions(self):
    for reset in ({"brake": True}, {"engaged": False}, {"standstill": True}):
      self.setup_method()
      self.override()
      assert self.update(**reset) == pytest.approx(40)
      assert self.policy.override is None

  def test_invalid_limit_is_not_new_limit(self):
    self.override()
    for value in (None, 0, float("nan"), float("inf")):
      assert self.update(road_limit=value) == pytest.approx(60)
    assert self.update(road_limit=40 / 3.6) == pytest.approx(60)

  def test_unset_ceiling_cannot_publish_a_target(self):
    for value in (255 / 3.6, float("nan"), 0):
      assert self.update(ceiling=value) == 0

  def test_pedal_held_while_disengaged_does_not_arm(self):
    self.update(engaged=False, gas=True)
    assert self.update(engaged=True, gas=False, speed=60 / 3.6) == pytest.approx(40)

  def test_new_instance_has_no_override(self):
    self.override()
    self.policy = CruiseTargetPolicy()
    assert self.update() == pytest.approx(40)
