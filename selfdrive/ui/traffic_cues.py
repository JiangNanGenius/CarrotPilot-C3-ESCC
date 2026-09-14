"""Read-only notification edges. Never issues engagement or actuator commands."""

import math


class TrafficCues:
  def __init__(self):
    self.reset()

  def reset(self):
    self.last_time = None
    self.red_since = None
    self.clear_since = None
    self.red_notified = False
    self.stopped_since = None
    self.move_since = None
    self.start_armed = False

  def update(self, now, *, healthy, enabled, traffic_state, speed, long_active, brake, gas):
    if not healthy or not enabled or not math.isfinite(speed) or speed < -0.1:
      self.reset()
      return None
    if self.last_time is not None and not 0 <= now - self.last_time <= 0.3:
      self.reset()
    self.last_time = now
    speed = max(0.0, speed)  # filtered wheel speed can be slightly negative at rest
    cue = None
    if traffic_state == 1:
      self.clear_since = None
      if self.red_since is None:
        self.red_since = now
      if not self.red_notified and now - self.red_since >= 0.5:
        self.red_notified = True
        cue = "detected"
    else:
      self.red_since = None
      if self.clear_since is None:
        self.clear_since = now
      if now - self.clear_since >= 1.0:
        self.red_notified = False

    # Require a real stationary dwell, then fresh, autonomous forward motion.
    # Driver override/disengagement cancels the arm, not just the sound.
    if brake or gas or not long_active:
      self.stopped_since = self.move_since = None
      self.start_armed = False
    elif speed < 0.1:
      self.move_since = None
      if self.stopped_since is None:
        self.stopped_since = now
      if now - self.stopped_since >= 1.0:
        self.start_armed = True
    elif self.start_armed and speed >= 0.3:
      if self.move_since is None:
        self.move_since = now
      if now - self.move_since >= 0.15:
        self.start_armed = False
        self.stopped_since = self.move_since = None
        cue = "starting"
    else:
      self.move_since = None
      if not self.start_armed:
        self.stopped_since = None
    return cue
