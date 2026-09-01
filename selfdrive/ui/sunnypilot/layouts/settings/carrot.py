"""Carrot settings panel — focused, only exposes EFFECTIVE parameters.

After wiring carrot speed limit (stage 2) and traffic-light stop (stage 3),
these are the parameters that actually take effect:
  * CarrotSpeedLimitEnable / CarrotTrafficStopEnable — consumed by
    CarrotSpeedLimit / CarrotTrafficStop in the longitudinal planner.
  * AutoRoadSpeedLimitOffset / AutoNaviSpeedLimitOffset / AutoNaviSpeedSafetyFactor
    / AutoNaviSpeedDecelRate / TurnSpeedControlMode / MapTurnSpeedFactor —
    consumed by carrot_serv to compute carrotMan.desiredSpeed (which is now
    consumed by CarrotSpeedLimit).

Orphan params (MyDrivingMode / TFollowGap* / TrafficLightDetectMode / ...) that
belong to the still-unwired CarrotPlanner are intentionally NOT exposed, so
users don't get a false sense that they have an effect.

All values are read/written via CarrotParams (file-backed, bypasses the C++
check_key registry) so they work without rebuilding params_pyx.so.
"""

from openpilot.selfdrive.carrot.carrot_params import CarrotParams
from openpilot.system.ui.sunnypilot.widgets.list_view import (
  LineSeparatorSP,
  multiple_button_item_sp,
  toggle_item_sp,
)
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller


class CarrotLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = CarrotParams()
    self._controls = []

    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=False, spacing=0)

  def _selected_index(self, key, values):
    current = self._params.get_int(key)
    if current in values:
      return values.index(current)
    if values:
      return min(range(len(values)), key=lambda i: abs(values[i] - current))
    return 0

  def _toggle(self, key, title, description=""):
    item = toggle_item_sp(
      title=title,
      description=description,
      initial_state=self._params.get_bool(key),
      callback=lambda state: self._params.put_bool(key, state),
    )
    self._controls.append((item, key, None))
    return item

  def _selector(self, key, title, labels, values, description="", button_width=160):
    item = multiple_button_item_sp(
      title=title,
      description=description,
      buttons=labels,
      selected_index=self._selected_index(key, values),
      button_width=button_width,
      callback=lambda index: self._params.put_int(key, values[index]),
    )
    self._controls.append((item, key, values))
    return item

  def _initialize_items(self):
    items = [
      # -- Speed limit (wired in stage 2) ---------------------------
      self._selector(
        "LongitudinalSpeedReference", "实际速度基准",
        ["轮速", "仪表"], [0, 1],
        description="仪表模式会校正实际纵向目标，使车辆仪表显示贴合设定速度；不使用 GPS。",
        button_width=260,
      ),
      self._toggle(
        "CarrotSpeedLimitEnable", "Carrot 规划速度源",
        "使用 Carrot 规划的道路限速、导航测速/减速带、车辆转发限速和弯道速度；Sunny Speed Limit 仍独立管理车辆与原生地图源。",
      ),
      self._selector(
        "AutoRoadSpeedLimitOffset", "道路限速偏移",
        ["-1", "0", "+5", "+10", "+20"], [-1, 0, 5, 10, 20],
        description="道路限速的固定偏移（-1 表示不启用）。",
      ),
      self._selector(
        "AutoNaviSpeedLimitOffset", "导航限速偏移",
        ["-20", "-10", "0", "+10", "+20"], [-20, -10, 0, 10, 20],
        description="导航测速限速的固定偏移（km/h）。",
      ),
      self._selector(
        "AutoNaviSpeedSafetyFactor", "限速安全系数",
        ["80%", "90%", "100%", "110%", "120%"], [80, 90, 100, 110, 120],
        description="限速值的百分比系数（低于 100% 更保守）。",
      ),
      self._selector(
        "AutoNaviSpeedDecelRate", "导航减速效率",
        ["100", "150", "200", "250", "300"], [100, 150, 200, 250, 300],
        description="导航减速的效率（0.01 m/s² × 该值）。",
      ),
      self._selector(
        "TurnSpeedControlMode", "转向速度控制",
        ["关闭", "模式1", "模式2", "模式3"], [0, 1, 2, 3],
        description="根据转向自动减速的控制模式。",
      ),
      self._selector(
        "MapTurnSpeedFactor", "地图转向速度因子",
        ["50", "100", "150", "200", "300"], [50, 100, 150, 200, 300],
        description="地图弯道减速的强度因子。",
      ),
      LineSeparatorSP(),
      # -- Traffic-light stop (wired in stage 3, default off) --------
      self._toggle(
        "CarrotTrafficStopEnable",
        "红绿灯停车",
        "模型预测前方红灯时提前减速（视觉版，默认关闭，高风险）。",
      ),
    ]
    return items

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    # 每次进入页面时刷新 toggle 状态
    self._refresh_toggle_states()
    self._scroller.show_event()

  def _refresh_toggle_states(self):
    """Re-read durable values so the legacy panel cannot show stale state."""
    for item, key, values in self._controls:
      if values is None:
        item.action_item.set_state(self._params.get_bool(key))
      else:
        value = self._params.get_int(key)
        item.action_item.set_selected_button(values.index(value) if value in values else 0)
