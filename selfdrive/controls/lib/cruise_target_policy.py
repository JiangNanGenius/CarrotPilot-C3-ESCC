"""Driver ceiling and temporary road-speed override, before safety constraints.

All inputs and outputs use the selected display reference, in m/s. This policy
never owns acceleration, engagement, curve, lead or traffic-stop decisions.
"""

import math


class CruiseTargetPolicy:
  def __init__(self):
    self.override = None
    self.last_limit = None
    self.gas_previous = False
    self.source = "ceiling"

  def update(self, *, ceiling, road_limit, speed, gas, brake, engaged, standstill, enforce_limit=False):
    valid_ceiling = math.isfinite(ceiling) and 0 < ceiling <= 150 / 3.6
    valid_limit = road_limit is not None and math.isfinite(road_limit) and 0 < road_limit <= 150 / 3.6
    # Integer road signs are normalized before comparison, not floating-point
    # transport noise or changes to the identity of the supplying service.
    limit = round(road_limit * 3.6) if valid_limit else None
    changed = limit is not None and limit != self.last_limit
    if limit is not None:
      self.last_limit = limit

    reset = not valid_ceiling or not engaged or brake or standstill or changed or enforce_limit
    if reset:
      self.override = None
    elif self.gas_previous and not gas and math.isfinite(speed) and speed > 0:
      # Accelerator release below the road limit is a launch/curve override,
      # not a request to freeze cruise at that lower release speed.
      release_target = max(speed, road_limit) if valid_limit else speed
      self.override = min(release_target, ceiling)

    # Never re-arm an override with a pedal press that began while disengaged,
    # braking or stationary. A new limit during the press also cancels it.
    self.gas_previous = bool(gas and not reset)
    if self.override is not None:
      self.override = min(self.override, ceiling)

    target = ceiling if valid_ceiling else 0.0
    self.source = "ceiling"
    if valid_ceiling and valid_limit:
      target = min(ceiling, road_limit)
      self.source = "road" if road_limit <= ceiling else "ceiling"
    if valid_ceiling and self.override is not None and not enforce_limit:
      target = min(ceiling, self.override)
      self.source = "driver"
    return target
