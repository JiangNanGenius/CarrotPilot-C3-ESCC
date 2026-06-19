"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp, multiple_button_item_sp
from openpilot.system.ui.sunnypilot.lib.styles import style
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import gui_label

import pyray as rl

CHEVRON_INFO_DESCRIPTION = {
  "enabled": tr_noop("Display useful metrics below the chevron that tracks the lead car " +
                     "only applicable to cars with Genius Pilot longitudinal control."),
  "disabled": tr_noop("This feature requires Genius Pilot longitudinal control to be available.")
}


class VisualSectionHeader(Widget):
  def __init__(self, title, description=None):
    super().__init__()
    self._title = title
    self._description = description
    self._rect = rl.Rectangle(0, 0, 0, 112 if description else 72)

  @staticmethod
  def _resolve(value) -> str:
    return value() if callable(value) else str(value)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def _render(self, _) -> None:
    content_x = self._rect.x + style.ITEM_PADDING
    content_w = self._rect.width - style.ITEM_PADDING * 2
    title_rect = rl.Rectangle(content_x, self._rect.y + 8, content_w, 44)
    gui_label(title_rect, self._resolve(self._title), font_size=34, color=rl.Color(150, 205, 255, 255),
              font_weight=FontWeight.SEMI_BOLD, alignment=rl.GuiTextAlignment.TEXT_ALIGN_LEFT)

    if self._description:
      desc_rect = rl.Rectangle(content_x, self._rect.y + 54, content_w, 36)
      gui_label(desc_rect, self._resolve(self._description), font_size=26, color=style.ITEM_TEXT_VALUE_COLOR,
                alignment=rl.GuiTextAlignment.TEXT_ALIGN_LEFT)


class VisualsLayout(Widget):
  def __init__(self):
    super().__init__()

    self._params = Params()
    items = self._initialize_items()
    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _initialize_items(self):
    self._toggle_defs = {
      "GeniusLaneChangeVisuals": (
        lambda: tr("Genius Lane Change Visuals"),
        tr("Show lane-change intent cues on the driving screen using the model lane-change events. This is display-only."),
        None,
      ),
      "GeniusFishopVisualOverlay": (
        lambda: tr("Fishop Visual Overlay"),
        tr("Draw Fishop lane, lidar lane, blindspot, and overtake suggestion evidence on top of any visual preset only while the local hardware data is fresh. This does not enable automatic overtake control."),
        None,
      ),
      "GeniusCarrotWorldOverlay": (
        lambda: tr("Carrot World Overlay"),
        tr("Draw Carrot-style side-lane, blindspot, lane-change, lead, and radar evidence on top of the selected visual preset. This is display-only and does not change lane-change or control decisions."),
        None,
      ),
      "BlindSpot": (
        lambda: tr("Show Blind Spot Warnings"),
        tr("Enabling this will display warnings when a vehicle is detected in your " +
           "blind spot as long as your car has BSM supported."),
        None,
      ),
      "TorqueBar": (
        lambda: tr("Steering Arc"),
        tr("Display steering arc on the driving screen when lateral control is enabled."),
        None,
      ),
      "RainbowMode": (
        lambda: tr("Enable Tesla Rainbow Mode"),
        tr("A beautiful rainbow effect on the path the model wants to take. " +
           "It does not affect driving in any way."),
        None,
      ),
      "StandstillTimer": (
        lambda: tr("Enable Standstill Timer"),
        tr("Show a timer on the HUD when the car is at a standstill."),
        None,
      ),
      "RoadNameToggle": (
        lambda: tr("Display Road Name"),
        tr("Displays the name of the road the car is traveling on." +
           "<br>The OpenStreetMap database of the location must be downloaded from " +
           "the OSM panel to fetch the road name."),
        None,
      ),
      "GreenLightAlert": (
        lambda: tr("Green Traffic Light Alert (Beta)"),
        tr("A chime and on-screen alert will play when the traffic light you are waiting for " +
           "turns green and you have no vehicle in front of you." +
           "<br>Note: This chime is only designed as a notification. " +
           "It is the driver's responsibility to observe their environment and make decisions accordingly."),
        None,
      ),
      "LeadDepartAlert": (
        lambda: tr("Lead Departure Alert (Beta)"),
        tr("A chime and on-screen alert will play when you are stopped, and the vehicle in front of you start moving." +
           "<br>Note: This chime is only designed as a notification. " +
           "It is the driver's responsibility to observe their environment and make decisions accordingly."),
        None,
      ),
      "TrueVEgoUI": (
        lambda: tr("Speedometer: Always Display True Speed"),
        tr("For applicable vehicles, always display the true vehicle current speed from wheel speed sensors."),
        None,
      ),
      "HideVEgoUI": (
        lambda: tr("Speedometer: Hide from Onroad Screen"),
        tr("When enabled, the speedometer on the onroad screen is not displayed."),
        None,
      ),
      "ShowTurnSignals": (
        lambda: tr("Display Turn Signals"),
        tr("When enabled, visual turn indicators are drawn on the HUD."),
        None,
      ),
      "RocketFuel": (
        lambda: tr("Real-time Acceleration Bar"),
        tr("Show an indicator on the left side of the screen to display real-time vehicle acceleration and deceleration. " +
           "This displays what the car is currently doing, not what the planner is requesting."),
        None,
      ),
    }
    self._toggles = {}
    for param, (title, desc, callback) in self._toggle_defs.items():
      toggle = toggle_item_sp(
        title=title,
        description=desc,
        param=param,
        initial_state=ui_state.params.get_bool(param),
        callback=callback,
      )
      self._toggles[param] = toggle

    self._genius_visual_mode = multiple_button_item_sp(
      title=lambda: tr("Genius Visualization Preset"),
      description=lambda: tr("Choose one base display preset. Sunny is minimal, Carrot emphasizes lane, path, lead, and radar information, and Balanced keeps the Sunny HUD with Carrot-style lane and path cues. Fishop and Carrot World overlays are independent top layers."),
      buttons=[lambda: tr("Sunny"), lambda: tr("Carrot"), lambda: tr("Balanced")],
      param="GeniusVisualMode",
      callback=self._apply_visual_preset,
      button_width=300,
      inline=False,
    )
    self._genius_lane_line_style = multiple_button_item_sp(
      title=lambda: tr("Lane-Line Style"),
      description=lambda: tr("Simple uses white lanes and red road edges. Colored highlights active lane confidence. Carrot adds stronger adjacent-lane emphasis and torque color cues."),
      buttons=[lambda: tr("Simple"), lambda: tr("Colored"), lambda: tr("Carrot")],
      param="GeniusLaneLineStyle",
      button_width=300,
      inline=False,
    )
    self._genius_lead_radar_visual_mode = multiple_button_item_sp(
      title=lambda: tr("Lead And Radar Display"),
      description=lambda: tr("Chevron uses Sunny's lead marker. Box draws a Carrot-style lead-car frame. Radar also shows speed labels for tracked leads."),
      buttons=[lambda: tr("Chevron"), lambda: tr("Box"), lambda: tr("Radar")],
      param="GeniusLeadRadarVisualMode",
      button_width=300,
      inline=False,
    )

    self._chevron_info = multiple_button_item_sp(
      title=lambda: tr("Display Metrics Below Chevron"),
      description="",
      buttons=[lambda: tr("Off"), lambda: tr("Distance"), lambda: tr("Speed"), lambda: tr("Time"), lambda: tr("All")],
      param="ChevronInfo",
      inline=False
    )
    self._dev_ui_info = multiple_button_item_sp(
      title=lambda: tr("Developer UI"),
      description=lambda: tr("Display real-time parameters and metrics from various sources."),
      buttons=[lambda: tr("Off"), lambda: tr("Bottom"), lambda: tr("Right"), lambda: tr("Right & Bottom")],
      param="DevUIInfo",
      button_width=350,
      inline=False
    )

    overlay_params = ("GeniusCarrotWorldOverlay", "GeniusFishopVisualOverlay")
    genius_toggle_params = ("GeniusLaneChangeVisuals", *overlay_params)
    hud_toggles = [
      toggle for param, toggle in self._toggles.items()
      if param not in genius_toggle_params
    ]

    items = [
      VisualSectionHeader(lambda: tr("Base Display Layer"), lambda: tr("Only one base road renderer is active at a time.")),
      self._genius_visual_mode,
      VisualSectionHeader(lambda: tr("Visual Detail Controls"), lambda: tr("These refine the selected preset without changing planner or lane-change behavior.")),
      self._genius_lane_line_style,
      self._genius_lead_radar_visual_mode,
      self._toggles["GeniusLaneChangeVisuals"],
      VisualSectionHeader(lambda: tr("Evidence Overlays"), lambda: tr("Carrot World and Fishop are independent display-only overlays. They may be enabled together on top of any base preset when you need lane-change or hardware evidence.")),
      self._toggles["GeniusCarrotWorldOverlay"],
      self._toggles["GeniusFishopVisualOverlay"],
      VisualSectionHeader(lambda: tr("General HUD Widgets"), lambda: tr("These are normal Sunny/Genius HUD widgets and do not select the base road renderer.")),
    ] + hud_toggles + [
      self._chevron_info,
      self._dev_ui_info,
    ]
    return items

  def _apply_visual_preset(self, preset: int):
    self._params.put("GeniusVisualMode", preset)
    if preset == 0:
      self._params.put("GeniusLaneLineStyle", 0)
      self._params.put("GeniusLeadRadarVisualMode", 0)
    elif preset == 1:
      self._params.put("GeniusLaneLineStyle", 2)
      self._params.put("GeniusLeadRadarVisualMode", 2)
      self._params.put_bool("GeniusLaneChangeVisuals", True)
    else:
      self._params.put("GeniusLaneLineStyle", 1)
      self._params.put("GeniusLeadRadarVisualMode", 1)
      self._params.put_bool("GeniusLaneChangeVisuals", True)

  def _update_state(self):
    super()._update_state()

    for param in self._toggle_defs:
      self._toggles[param].action_item.set_state(self._params.get_bool(param))

    self._genius_visual_mode.action_item.set_selected_button(self._params.get("GeniusVisualMode", return_default=True))
    self._genius_lane_line_style.action_item.set_selected_button(self._params.get("GeniusLaneLineStyle", return_default=True))
    self._genius_lead_radar_visual_mode.action_item.set_selected_button(self._params.get("GeniusLeadRadarVisualMode", return_default=True))
    self._dev_ui_info.action_item.set_selected_button(ui_state.params.get("DevUIInfo", return_default=True))

    if ui_state.has_longitudinal_control:
      self._chevron_info.set_description(tr(CHEVRON_INFO_DESCRIPTION["enabled"]))
      self._chevron_info.action_item.set_selected_button(ui_state.params.get("ChevronInfo", return_default=True))
      self._chevron_info.action_item.set_enabled(True)
    else:
      self._chevron_info.set_description(tr(CHEVRON_INFO_DESCRIPTION["disabled"]))
      self._chevron_info.action_item.set_enabled(False)
      ui_state.params.put("ChevronInfo", 0)

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
    if not ui_state.has_longitudinal_control:
      self._chevron_info.set_description(tr(CHEVRON_INFO_DESCRIPTION["disabled"]))
      self._chevron_info.show_description(True)
