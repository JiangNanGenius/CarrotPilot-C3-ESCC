from cereal import car

from openpilot.selfdrive.selfdrived.brake_auto_resume import BrakeAutoResume, RELEASE_DELAY_FRAMES
from openpilot.selfdrive.selfdrived.events import Events


GearShifter = car.CarState.GearShifter
ButtonType = car.CarState.ButtonEvent.Type


def _state(*, brake=False, gas=False, speed=12.0, available=True, can_valid=True, gear=GearShifter.drive, buttons=()):
  cs = car.CarState.new_message()
  cs.brakePressed = brake
  cs.gasPressed = gas
  cs.vEgo = speed
  cs.canValid = can_valid
  cs.gearShifter = gear
  cs.cruiseState.available = available
  cs.buttonEvents = [car.CarState.ButtonEvent.new_message(type=button, pressed=True) for button in buttons]
  return cs


def test_resumes_once_after_stable_brake_release():
  guard = BrakeAutoResume()
  events = Events()
  released = _state()
  assert not guard.update(True, True, _state(brake=True), released, events)

  should_resume = False
  for _ in range(RELEASE_DELAY_FRAMES):
    should_resume = guard.update(True, False, released, _state(brake=True), events)
  assert should_resume
  assert not guard.update(True, False, released, released, events)


def test_never_resumes_when_disabled_stopped_or_driver_cancels():
  events = Events()
  for feature_enabled, release in (
      (False, _state()),
      (True, _state(speed=0.0)),
      (True, _state(buttons=(ButtonType.cancel,))),
      (True, _state(can_valid=False)),
  ):
    guard = BrakeAutoResume()
    assert not guard.update(feature_enabled, True, _state(brake=True), _state(), events)
    assert not any(guard.update(feature_enabled, False, release, _state(brake=True), events)
                   for _ in range(RELEASE_DELAY_FRAMES + 2))
