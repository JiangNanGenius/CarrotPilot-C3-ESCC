"""Low-speed stopped-lead latch.

The MPC still owns normal following. This small state machine only prevents a
stopped lead from being released at crawl speed because of a short radar
dropout or an almost-zero acceleration solution.
"""

import math

from openpilot.common.realtime import DT_MDL


class LeadStopHold:
  def __init__(self):
    self.active = False
    self.remaining_distance = 0.0
    self.dropout_frames = 0
    self.moving_frames = 0

  def reset(self):
    self.active = False
    self.remaining_distance = 0.0
    self.dropout_frames = 0
    self.moving_frames = 0

  def update(self, *, lead_status: bool, lead_distance: float, lead_speed: float,
             ego_speed: float, desired_gap: float, engaged: bool, gas: bool) -> bool:
    if not engaged or gas or not all(math.isfinite(x) for x in (ego_speed, desired_gap)):
      self.reset()
      return False

    desired_gap = max(2.5, min(6.0, desired_gap))
    ego_speed = max(0.0, ego_speed)
    valid_lead = bool(lead_status and math.isfinite(lead_distance) and lead_distance > 0 and
                      math.isfinite(lead_speed))

    if valid_lead:
      self.dropout_frames = 0
      # Reserve reaction plus comfortable braking distance. This state only
      # arms below 2.5 m/s, so it cannot replace normal-speed lead planning.
      approach_distance = desired_gap + ego_speed * 0.6 + ego_speed**2 / 2.0
      stopped_lead = lead_speed <= 0.35
      if stopped_lead and ego_speed <= 2.5 and lead_distance <= approach_distance:
        self.active = True
        self.remaining_distance = lead_distance

      if self.active:
        self.remaining_distance = lead_distance
        if lead_speed >= 0.8 and lead_distance >= desired_gap + 0.75:
          self.moving_frames += 1
          if self.moving_frames * DT_MDL >= 0.5:
            self.reset()
        else:
          self.moving_frames = 0
    elif self.active:
      self.dropout_frames += 1
      self.remaining_distance = max(0.0, self.remaining_distance - ego_speed * DT_MDL)
      if self.dropout_frames * DT_MDL > 1.0:
        self.reset()

    return self.active
