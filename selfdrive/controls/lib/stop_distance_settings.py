"""Validated, cached distance settings; persistent values are centimetres."""

import math


def bounded_distance(value, default, minimum, maximum):
  try:
    distance = float(value) / 100
  except (TypeError, ValueError, OverflowError):
    return default
  return min(maximum, max(minimum, distance)) if math.isfinite(distance) else default


class StopDistanceSettings:
  def __init__(self, params):
    self.params = params
    self.frame = 0
    self.follow = 6.0
    self.traffic = 2.0

  def update(self):
    if self.frame % 100 == 0:
      self.follow = bounded_distance(self.params.get('StopDistanceCarrot'), 6.0, 3.0, 12.0)
      # The old signed TrafficStopDistanceAdjust was not connected and had
      # different semantics. Do not silently reinterpret it as a buffer.
      self.traffic = bounded_distance(self.params.get('TrafficStopBufferCm'), 2.0, 1.0, 10.0)
    self.frame += 1
