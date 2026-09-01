"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of GeniusPilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets.list_view import ListItem, ItemAction


class ProgressBarAction(ItemAction):
  def __init__(self, width=600):
    super().__init__(width=width)
    self.progress = 0.0
    self.text = ""
    self.show_progress = False
    self.text_color = rl.GRAY
    self._font = gui_app.font(FontWeight.NORMAL)

  def update(self, progress, text, show_progress=False, text_color=rl.GRAY):
    self.progress = progress
    self.text = text
    self.show_progress = show_progress
    self.text_color = text_color

  def _render(self, rect: rl.Rectangle):
    font_size = 40
    padding = 30
    # The old renderer only reserved room for a "100%" prefix. Bundle progress
    # also contains file counts and ETA, which made the bar narrower than its
    # text and pushed the useful percentage outside the action area.
    bar_width = max(1.0, rect.width)

    display_text = self.text
    max_text_width = max(1.0, bar_width - 2 * padding)
    text_size = measure_text_cached(self._font, display_text, font_size)
    if text_size.x > max_text_width:
      ellipsis = "..."
      left, right = 0, len(display_text)
      while left < right:
        mid = (left + right) // 2
        candidate = display_text[:mid] + ellipsis
        if measure_text_cached(self._font, candidate, font_size).x <= max_text_width:
          left = mid + 1
        else:
          right = mid
      display_text = display_text[:max(0, left - 1)] + ellipsis
      text_size = measure_text_cached(self._font, display_text, font_size)
    text_x = (bar_width - text_size.x) / 2

    bar_height = 60
    bar_rect = rl.Rectangle(rect.x + rect.width - bar_width, rect.y + (rect.height - bar_height) / 2, bar_width, bar_height)

    if self.show_progress:
      inner_rect = rl.Rectangle(bar_rect.x + 4, bar_rect.y + 4, bar_rect.width - 8, bar_rect.height - 8)
      if inner_rect.width > 0:
        rl.draw_rectangle_rounded(inner_rect, 0.2, 10, rl.Color(43, 43, 43, 220))
        if self.progress > 0:
          fill_width = max(0, min(inner_rect.width, inner_rect.width * (self.progress / 100.0)))
          rl.draw_rectangle_rounded(rl.Rectangle(inner_rect.x, inner_rect.y, fill_width, inner_rect.height), 0.2, 10, rl.Color(30, 121, 232, 255))
        else:
          # DNS/TLS and servers without Content-Length have no honest percent.
          # Show an indeterminate moving segment so 0% is visibly active rather
          # than looking like the model-selection tap was ignored.
          segment_width = max(48.0, inner_rect.width * 0.22)
          phase = (rl.get_time() % 1.6) / 1.6
          segment_x = inner_rect.x - segment_width + phase * (inner_rect.width + segment_width)
          visible_x = max(inner_rect.x, segment_x)
          visible_right = min(inner_rect.x + inner_rect.width, segment_x + segment_width)
          if visible_right > visible_x:
            rl.draw_rectangle_rounded(rl.Rectangle(visible_x, inner_rect.y, visible_right - visible_x, inner_rect.height),
                                      0.2, 10, rl.Color(30, 121, 232, 255))

    rl.draw_text_ex(self._font, display_text, rl.Vector2(bar_rect.x + text_x, bar_rect.y + (bar_height - text_size.y) / 2), font_size, 0, self.text_color)


def progress_item(title):
  action = ProgressBarAction()
  return ListItem(title=title, action_item=action)
