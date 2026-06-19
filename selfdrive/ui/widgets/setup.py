import pyray as rl
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.system.ui.widgets.label import Label


class SetupWidget(Widget):
  def __init__(self):
    super().__init__()
    self._open_settings_callback = None
    self._open_settings_btn = Button(lambda: tr("Open settings"), lambda: self._open_settings_callback() if self._open_settings_callback else None,
                                     button_style=ButtonStyle.PRIMARY)
    self._local_label = Label(lambda: tr("Local Maintenance"), font_weight=FontWeight.MEDIUM, font_size=64)

  def set_open_settings_callback(self, callback):
    self._open_settings_callback = callback

  def _render(self, rect: rl.Rectangle):
    self._render_local_maintenance_prompt(rect)

  def _render_local_maintenance_prompt(self, rect: rl.Rectangle):
    """Render local maintenance prompt without cloud upload or pairing."""

    rl.draw_rectangle_rounded(rl.Rectangle(rect.x, rect.y, rect.width, 500), 0.04, 20, rl.Color(51, 51, 51, 255))

    # Content margins (56, 40, 56, 40)
    x = rect.x + 56
    y = rect.y + 40
    w = rect.width - 112
    spacing = 42

    # Title
    self._local_label.render(rl.Rectangle(rect.x, y, rect.width, 64))
    y += 64 + spacing

    # Description
    desc_font = gui_app.font(FontWeight.NORMAL)
    desc_text = tr("Use local settings for Wi-Fi, SSH, GitHub updates, and model downloads. Cloud pairing and uploads are disabled.")
    wrapped_desc = wrap_text(desc_font, desc_text, 40, int(w))

    for line in wrapped_desc:
      rl.draw_text_ex(desc_font, line, rl.Vector2(x, y), 40, 0, rl.WHITE)
      y += 40 * FONT_SCALE

    y += spacing

    # Open button
    button_height = 48 + 64  # font size + padding
    button_rect = rl.Rectangle(x, y, w, button_height)
    self._open_settings_btn.render(button_rect)
