from cereal import car

from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.selfdrived.events import ET, Events


ButtonType = car.CarState.ButtonEvent.Type
GearShifter = car.CarState.GearShifter

RELEASE_DELAY_FRAMES = int(1.0 / DT_CTRL)
ARM_TIMEOUT_FRAMES = int(30.0 / DT_CTRL)
MIN_RESUME_SPEED = 5.0  # m/s; stopped/parking maneuvers always require the driver
AUTO_RESUME_GEARS = (GearShifter.drive, GearShifter.sport)


class BrakeAutoResume:
  """One-shot, explicitly enabled brake-takeover resume guard."""

  def __init__(self) -> None:
    self.armed = False
    self.age_frames = 0
    self.release_frames = 0

  def disarm(self) -> None:
    self.armed = False
    self.age_frames = 0
    self.release_frames = 0

  def update(self, feature_enabled: bool, controls_enabled: bool, CS: car.CarState,
             CS_prev: car.CarState, events: Events) -> bool:
    cancel_pressed = any(be.type == ButtonType.cancel and be.pressed for be in CS.buttonEvents)
    brake_rising = CS.brakePressed and not CS_prev.brakePressed

    if not feature_enabled:
      self.disarm()
      return False

    if brake_rising and controls_enabled and CS.cruiseState.available and CS.canValid:
      self.armed = True
      self.age_frames = 0
      self.release_frames = 0

    if not self.armed:
      return False

    self.age_frames += 1
    unsafe = (cancel_pressed or CS.gasPressed or CS.regenBraking or not CS.canValid or
              not CS.cruiseState.available or CS.gearShifter not in AUTO_RESUME_GEARS or
              self.age_frames > ARM_TIMEOUT_FRAMES)
    if unsafe:
      self.disarm()
      return False

    if CS.brakePressed:
      self.release_frames = 0
      return False

    self.release_frames += 1
    if self.release_frames < RELEASE_DELAY_FRAMES or CS.vEgo < MIN_RESUME_SPEED:
      return False

    # A stale brake session must never bypass current no-entry/safety gates.
    if events.contains(ET.NO_ENTRY) or events.contains(ET.IMMEDIATE_DISABLE) or events.contains(ET.SOFT_DISABLE):
      self.disarm()
      return False

    self.disarm()
    return True
