import pyray as rl

from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller import NavRawScrollPanel

TITLE = tr_noop("Data Uploads Disabled")
DESCRIPTION = tr_noop(
  "Genius Pilot keeps cloud training uploads disabled in this personal C3 build.\n\n"
  + "Local Wi-Fi, SSH, Web, GitHub updates, and model downloads remain available. "
  + "Driving data is not uploaded from this page."
)
INSTRUCTIONS_INTRO = tr_noop(
  "For updates, bring your device inside and connect to a good USB-C adapter and Wi-Fi.\n\n"
  + "Use the Software, Models, and Super Advanced pages for local maintenance. "
  + "This page does not pair with comma, Sunnylink, or any cloud upload service."
)
FAQ_HEADER = tr_noop("Frequently Asked Questions")
FAQ_ITEMS = [
  (tr_noop("Does this upload my drives?"), tr_noop("No. Cloud upload paths are disabled in Genius Pilot.")),
  (tr_noop("Can I still update over Wi-Fi?"), tr_noop("Yes. GitHub updates and model downloads are local maintenance features.")),
  (tr_noop("What should I use this page for?"), tr_noop("It is a reminder that cloud training upload mode is intentionally unavailable.")),
]


class FirehoseLayoutBase(Widget):
  GREEN = rl.Color(46, 204, 113, 255)
  GRAY = rl.Color(68, 68, 68, 255)
  LIGHT_GRAY = rl.Color(228, 228, 228, 255)

  def __init__(self):
    super().__init__()

    self._scroll_panel = GuiScrollPanel2(horizontal=False)
    self._content_height = 0

  def __del__(self):
    pass

  def show_event(self):
    super().show_event()
    self._scroll_panel.set_offset(0)

  def _render(self, rect: rl.Rectangle):
    # compute total content height for scrolling
    content_height = self._measure_content_height(rect)
    scroll_offset = self._scroll_panel.update(rect, content_height)

    # start drawing with offset
    x = rect.x + 40
    y = rect.y + 40 + scroll_offset
    w = rect.width - 80

    # Title
    title_text = tr(TITLE)
    title_font = gui_app.font(FontWeight.BOLD)
    title_size = 64
    rl.draw_text_ex(title_font, title_text, rl.Vector2(x, y), title_size, 0, rl.WHITE)
    y += int(title_size * FONT_SCALE) + 20

    # Description
    y = self._draw_wrapped_text(x, y, w, tr(DESCRIPTION), gui_app.font(FontWeight.ROMAN), 36, rl.WHITE)
    y += 20

    # Separator
    rl.draw_rectangle_rec(rl.Rectangle(x, y, w, 2), self.GRAY)
    y += 20

    # Status
    status_text, status_color = self._get_status()
    y = self._draw_wrapped_text(x, y, w, status_text, gui_app.font(FontWeight.BOLD), 48, status_color)
    y += 20

    # Separator
    rl.draw_rectangle_rec(rl.Rectangle(x, y, w, 2), self.GRAY)
    y += 20

    # Instructions intro
    y = self._draw_wrapped_text(x, y, w, tr(INSTRUCTIONS_INTRO), gui_app.font(FontWeight.ROMAN), 32, self.LIGHT_GRAY)
    y += 20

    # FAQ Header
    y = self._draw_wrapped_text(x, y, w, tr(FAQ_HEADER), gui_app.font(FontWeight.BOLD), 44, rl.WHITE)
    y += 20

    # FAQ Items
    for question, answer in FAQ_ITEMS:
      y = self._draw_wrapped_text(x, y, w, tr(question), gui_app.font(FontWeight.BOLD), 32, self.LIGHT_GRAY)
      y = self._draw_wrapped_text(x, y, w, tr(answer), gui_app.font(FontWeight.ROMAN), 32, self.LIGHT_GRAY)
      y += 20

  def _draw_wrapped_text(self, x, y, width, text, font, font_size, color):
    wrapped = wrap_text(font, text, font_size, width)
    for line in wrapped:
      rl.draw_text_ex(font, line, rl.Vector2(x, y), font_size, 0, color)
      y += int(font_size * FONT_SCALE)
    return y

  def _measure_content_height(self, rect: rl.Rectangle) -> int:
    # Rough measurement using the same wrapping as rendering
    w = int(rect.width - 80)
    y = 40

    # Title
    title_size = 72
    y += int(title_size * FONT_SCALE) + 20

    # Description
    desc_lines = wrap_text(gui_app.font(FontWeight.ROMAN), tr(DESCRIPTION), 36, w)
    y += int(len(desc_lines) * 36 * FONT_SCALE) + 20

    # Separator + Status
    y += 2 + 20
    status_text, _ = self._get_status()
    status_lines = wrap_text(gui_app.font(FontWeight.BOLD), status_text, 48, w)
    y += int(len(status_lines) * 48 * FONT_SCALE) + 20

    # Separator + Instructions
    y += 2 + 20

    # Instructions intro
    intro_lines = wrap_text(gui_app.font(FontWeight.ROMAN), tr(INSTRUCTIONS_INTRO), 32, w)
    y += int(len(intro_lines) * 32 * FONT_SCALE) + 20

    # FAQ Header
    faq_header_lines = wrap_text(gui_app.font(FontWeight.BOLD), tr(FAQ_HEADER), 44, w)
    y += int(len(faq_header_lines) * 44 * FONT_SCALE) + 20

    # FAQ Items
    for question, answer in FAQ_ITEMS:
      q_lines = wrap_text(gui_app.font(FontWeight.BOLD), tr(question), 32, w)
      y += int(len(q_lines) * 32 * FONT_SCALE)
      a_lines = wrap_text(gui_app.font(FontWeight.ROMAN), tr(answer), 32, w)
      y += int(len(a_lines) * 32 * FONT_SCALE) + 20

    # bottom padding
    y += 40
    return y

  def _get_status(self) -> tuple[str, rl.Color]:
    return tr("DISABLED: cloud uploads are off in this personal build"), self.GREEN


class FirehoseLayout(NavRawScrollPanel, FirehoseLayoutBase):
  pass
