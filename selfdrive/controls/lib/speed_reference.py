"""Convert cruise targets to the driver's selected vehicle-speed reference."""

from openpilot.selfdrive.carrot.carrot_params import CarrotParams


WHEEL_SPEED = 0
INSTRUMENT_SPEED = 1

MIN_CALIBRATION_SPEED = 8.33  # 30 km/h
MAX_CALIBRATION_ACCEL = 0.3
MIN_SAFE_RATIO = 0.85
MAX_PLAUSIBLE_RATIO = 1.15
RATIO_FILTER_ALPHA = 0.05
PARAM_REFRESH_FRAMES = 100


class SpeedReference:
  """Keep a stable wheel-speed loop while targeting the selected display speed.

  Instrument mode learns the steady-state ratio between wheel speed (vEgo)
  and the vehicle cluster's current-speed display (vEgoCluster). It scales
  cruise targets down by that ratio. The ratio is capped at 1.0, so this
  feature can never raise a target above the ordinary wheel-speed target.
  """

  def __init__(self, params: CarrotParams | None = None):
    self.params = params or CarrotParams()
    self.reference = self.params.get_int("LongitudinalSpeedReference", WHEEL_SPEED)
    self.ratio = 1.0
    self.ratio_initialized = False
    self.frame = 0

  def _update_params(self) -> None:
    if self.frame % PARAM_REFRESH_FRAMES == 0:
      self.reference = self.params.get_int("LongitudinalSpeedReference", WHEEL_SPEED)

  def _update_ratio(self, v_ego: float, v_ego_cluster: float, a_ego: float) -> None:
    if v_ego < MIN_CALIBRATION_SPEED or v_ego_cluster < MIN_CALIBRATION_SPEED or abs(a_ego) > MAX_CALIBRATION_ACCEL:
      return

    raw_ratio = v_ego / v_ego_cluster
    if not MIN_SAFE_RATIO <= raw_ratio <= MAX_PLAUSIBLE_RATIO:
      return

    # A speedometer that reads low must never cause this feature to speed up.
    safe_ratio = min(1.0, raw_ratio)
    if not self.ratio_initialized:
      self.ratio = safe_ratio
      self.ratio_initialized = True
    else:
      self.ratio += RATIO_FILTER_ALPHA * (safe_ratio - self.ratio)

  def update(self, target_speed: float, v_ego: float, v_ego_cluster: float, a_ego: float) -> float:
    self._update_params()
    self._update_ratio(v_ego, v_ego_cluster, a_ego)
    self.frame += 1

    if self.reference != INSTRUMENT_SPEED or target_speed <= 0:
      return target_speed
    return min(target_speed, target_speed * self.ratio)

