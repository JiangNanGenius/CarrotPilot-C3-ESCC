"""Persistent, fail-visible SCC badges. Pulsing means selected curve limiting."""
import math
import pyray as rl

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.sunnypilot.onroad.curve_status import curve_status
from openpilot.selfdrive.ui.sunnypilot.onroad.hud_layout import CRUISE_PANEL_WIDTH, LEFT_MARGIN, TOP_MARGIN
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.sunnypilot.lib.utils import AlertFadeAnimator
from openpilot.system.ui.widgets import Widget


class SmartCruiseControlRenderer(Widget):
  def __init__(self):
    super().__init__()
    self.font = gui_app.font(FontWeight.BOLD)
    self._fades = [AlertFadeAnimator(gui_app.target_fps, duration_on=0.15) for _ in range(2)]
    self._states = [('数据失效', 'unknown', False)] * 2

  def update(self):
    sm = ui_state.sm
    fresh = all(sm.alive[k] and sm.valid[k] for k in ('longitudinalPlanSP', 'longitudinalPlan', 'carControl'))
    plan = sm['longitudinalPlanSP']
    control = sm['carControl']
    source = str(sm['longitudinalPlan'].cruiseTargetSource)
    speed_conv = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    for i, (curve, source_name) in enumerate(((plan.smartCruiseControl.vision, 'visionCurve'),
                                             (plan.smartCruiseControl.map, 'mapCurve'))):
      predicted = curve.maxPredictedLateralAccel if i == 0 else 0.0
      self._states[i] = curve_status(
        fresh=fresh, enabled=curve.enabled, active=curve.active,
        approaching=math.isfinite(predicted) and predicted >= 1.0,
        override=control.cruiseControl.override, selected=source == source_name,
        target=curve.vTarget * speed_conv,
      )
      self._fades[i].update(self._states[i][2])

  def _render(self, rect: rl.Rectangle):
    # Beside the left rail; leave current speed, alerts and ESCC clear.
    x = rect.x + LEFT_MARGIN + CRUISE_PANEL_WIDTH + 16
    colors = {'idle': rl.Color(55, 62, 70, 235), 'unknown': rl.Color(65, 65, 65, 235),
              'preview': rl.Color(235, 179, 45, 245), 'active': rl.Color(60, 210, 120, 245)}
    for i, name in enumerate(('SCC-V  视觉', 'SCC-M  地图')):
      label, kind, pulse = self._states[i]
      y = rect.y + TOP_MARGIN + i * 88
      color = colors[kind]
      # Never blink completely out: status remains readable during the pulse.
      alpha = 0.55 + 0.45 * self._fades[i].alpha if pulse else 1.0
      bg = rl.Color(color.r, color.g, color.b, int(color.a * alpha))
      fg = rl.BLACK if kind in ('preview', 'active') else rl.WHITE
      rl.draw_rectangle_rounded(rl.Rectangle(x, y, 270, 78), 0.15, 8, bg)
      for text, size, dy in ((name, 30, 6), (label, 28, 42)):
        width = measure_text_cached(self.font, text, size).x
        rl.draw_text_ex(self.font, text, rl.Vector2(x + (270-width)/2, y+dy), size, 0, fg)
