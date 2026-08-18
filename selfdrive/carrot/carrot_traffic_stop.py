"""Carrot traffic-light stop (nav-app source) — lightweight, feature-flagged.

Consumes ``carrotMan.trafficState`` (from carrot's nav-app integration, e.g.
Amap red-light data: 0=none, 1=red, 2=green, 3=left-turn) and requests an
EARLY deceleration by lowering ``v_cruise`` to 0 when the nav app reports a
red light ahead.

Design rules (same as CarrotSpeedLimit):
  * It only lowers ``v_cruise`` — it NEVER outputs brakes/acceleration and
    NEVER drives ``shouldStop``. Final stopping stays solely with sunny's
    e2e ``modelV2.shouldStop``, so there is no double-trigger.
  * The vision-based stop (check_model_stopping) is NOT wired here: sunny's
    e2e already handles visual stop signs / red lights. This module only
    adds the nav-app red-light signal as an early-deceleration hint.
  * Disabled by default (high risk); gray-rollout via CarrotTrafficStopEnable.
"""

from openpilot.selfdrive.carrot.carrot_params import CarrotParams


class CarrotTrafficStop:
  def __init__(self):
    self.params = CarrotParams()
    self.enabled = self.params.get_bool("CarrotTrafficStopEnable")

  def update(self, sm, v_cruise_ms: float) -> float:
    if not self.enabled:
      return v_cruise_ms

    try:
      if sm.alive['carrotMan']:
        traffic_state = sm['carrotMan'].trafficState
        # 1 == red light -> request early deceleration.
        if traffic_state == 1:
          return 0.0
    except Exception:
      pass

    return v_cruise_ms
