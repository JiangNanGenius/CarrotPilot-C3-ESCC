from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pyray as rl

from openpilot.selfdrive.carrot.fishop_hardware import normalize_fishop_payloads
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.widgets import Widget

FISHOP_JSONL = Path("/data/fishop_hardware.jsonl")
MAX_FISHOP_LINES = 240
MAX_SOURCE_AGE_S = 2.5
REFRESH_INTERVAL_S = 0.5

PANEL_W = 250
PANEL_H = 106
PANEL_MARGIN_X = 38
PANEL_Y_FRAC = 0.54
PILL_H = 48

COLOR_BG = rl.Color(0, 0, 0, 150)
COLOR_MUTED = rl.Color(160, 166, 166, 220)
COLOR_OK = rl.Color(34, 188, 112, 230)
COLOR_WARN = rl.Color(244, 172, 54, 235)
COLOR_BLOCK = rl.Color(222, 72, 64, 235)
COLOR_LINE = rl.Color(255, 255, 255, 60)
COLOR_TEXT = rl.Color(255, 255, 255, 235)


def _tail_lines(path: Path, max_lines: int) -> list[str]:
  try:
    with path.open("rb") as f:
      f.seek(0, 2)
      pos = f.tell()
      data = b""
      block_size = 4096
      while pos > 0 and data.count(b"\n") <= max_lines:
        read_size = min(block_size, pos)
        pos -= read_size
        f.seek(pos)
        data = f.read(read_size) + data
  except OSError:
    return []

  return data.decode("utf-8", "replace").splitlines()[-max_lines:]


def _payloads_from_lines(lines: list[str]) -> list[dict[str, Any]]:
  payloads: list[dict[str, Any]] = []
  for line in lines:
    try:
      parsed = json.loads(line)
    except json.JSONDecodeError:
      continue

    if isinstance(parsed, dict):
      payloads.append(parsed)
    elif isinstance(parsed, list):
      payloads.extend(item for item in parsed if isinstance(item, dict))
  return payloads


def _bool(value: Any) -> bool:
  return bool(value)


class FishopVisualOverlay(Widget):
  def __init__(self):
    super().__init__()
    self._last_refresh_s = 0.0
    self._state: dict[str, Any] | None = None
    self._source_age_s: float | None = None

  def _load_state(self) -> dict[str, Any] | None:
    now = time.monotonic()
    if now - self._last_refresh_s < REFRESH_INTERVAL_S:
      return self._state

    self._last_refresh_s = now
    self._state = None
    self._source_age_s = None

    try:
      stat = FISHOP_JSONL.stat()
    except OSError:
      return None

    self._source_age_s = max(0.0, time.time() - stat.st_mtime)
    if self._source_age_s > MAX_SOURCE_AGE_S:
      return None

    payloads = _payloads_from_lines(_tail_lines(FISHOP_JSONL, MAX_FISHOP_LINES))
    if not payloads:
      return None

    self._state = normalize_fishop_payloads(payloads, now_s=now)
    return self._state

  def _render(self, rect: rl.Rectangle) -> None:
    if not ui_state.genius_fishop_visual_overlay:
      return

    state = self._load_state()
    if not state or not state.get("sensorOnline"):
      return

    lane = state.get("lane", {}) if isinstance(state.get("lane"), dict) else {}
    blindspot = state.get("blindspot", {}) if isinstance(state.get("blindspot"), dict) else {}
    overtake = state.get("overtake", {}) if isinstance(state.get("overtake"), dict) else {}

    y = rect.y + rect.height * PANEL_Y_FRAC
    left_rect = rl.Rectangle(rect.x + PANEL_MARGIN_X, y, PANEL_W, PANEL_H)
    right_rect = rl.Rectangle(rect.x + rect.width - PANEL_MARGIN_X - PANEL_W, y, PANEL_W, PANEL_H)
    self._draw_side_panel(left_rect, "L", lane, blindspot)
    self._draw_side_panel(right_rect, "R", lane, blindspot)
    self._draw_overtake_pill(rect, overtake)

  def _draw_side_panel(self, rect: rl.Rectangle, side: str, lane: dict[str, Any], blindspot: dict[str, Any]) -> None:
    left = side == "L"
    prefix = "left" if left else "right"
    line_key = "leftLine" if left else "rightLine"
    lane_block_key = "leftLaneBlind" if left else "rightLaneBlind"
    lidar_online_key = "leftLidarOnline" if left else "rightLidarOnline"
    camera_online_key = "leftCameraOnline" if left else "rightCameraOnline"
    lidar_blind_key = "leftLidarBlind" if left else "rightLidarBlind"
    lidar_car_blind_key = "leftLidarCarBlind" if left else "rightLidarCarBlind"
    camera_blind_key = "leftCameraBlind" if left else "rightCameraBlind"

    dynamic = blindspot.get("dynamicBlind", {}) if isinstance(blindspot.get("dynamicBlind"), dict) else {}
    active_dynamic = tuple(str(item) for item in dynamic.get("activeRiskPreview", []))
    dynamic_block = any(item.startswith(prefix[0]) for item in active_dynamic)
    line_block = _bool(lane.get(lane_block_key))
    blind_block = any(_bool(blindspot.get(key)) for key in (lidar_blind_key, lidar_car_blind_key, camera_blind_key))
    online = _bool(lane.get("fresh")) or _bool(blindspot.get(lidar_online_key)) or _bool(blindspot.get(camera_online_key))

    if line_block or blind_block or dynamic_block:
      color = COLOR_BLOCK
      status = "BLOCK"
    elif online:
      color = COLOR_OK
      status = "CLEAR"
    else:
      color = COLOR_MUTED
      status = "WAIT"

    rl.draw_rectangle_rounded(rect, 0.18, 8, COLOR_BG)
    rl.draw_rectangle_rounded_lines_ex(rect, 0.18, 8, 3, color)
    rl.draw_text(f"FISHOP {side}", int(rect.x + 14), int(rect.y + 10), 24, COLOR_TEXT)
    rl.draw_text(status, int(rect.x + rect.width - 92), int(rect.y + 10), 24, color)
    rl.draw_line_ex((rect.x + 14, rect.y + 44), (rect.x + rect.width - 14, rect.y + 44), 1.0, COLOR_LINE)

    line_text = f"line {int(lane.get(line_key, 0) or 0)}"
    lidar_text = "lidar" if _bool(blindspot.get(lidar_online_key)) else "lidar --"
    camera_text = "cam" if _bool(blindspot.get(camera_online_key)) else "cam --"
    dyn_text = "dyn" if dynamic_block else "dyn --"
    rl.draw_text(line_text, int(rect.x + 14), int(rect.y + 56), 20, COLOR_TEXT if line_block else COLOR_MUTED)
    rl.draw_text(lidar_text, int(rect.x + 104), int(rect.y + 56), 20, COLOR_TEXT if _bool(blindspot.get(lidar_online_key)) else COLOR_MUTED)
    rl.draw_text(camera_text, int(rect.x + 14), int(rect.y + 80), 20, COLOR_TEXT if _bool(blindspot.get(camera_online_key)) else COLOR_MUTED)
    rl.draw_text(dyn_text, int(rect.x + 104), int(rect.y + 80), 20, COLOR_TEXT if dynamic_block else COLOR_MUTED)

  def _draw_overtake_pill(self, rect: rl.Rectangle, overtake: dict[str, Any]) -> None:
    preview = overtake.get("suggestionPreview", {}) if isinstance(overtake.get("suggestionPreview"), dict) else {}
    hint = preview.get("overtakeHint", {}) if isinstance(preview.get("overtakeHint"), dict) else {}
    direction = str(preview.get("direction") or hint.get("direction") or overtake.get("direction") or "").upper()
    if direction not in ("LEFT", "RIGHT"):
      return

    if preview.get("readyForSuggestion"):
      label = f"OVERTAKE {direction} READY"
      color = COLOR_OK
    elif hint.get("available"):
      label = f"OVERTAKE {direction} HINT"
      color = COLOR_WARN
    elif overtake.get("requested") or overtake.get("commandSeen"):
      label = f"OVERTAKE {direction} BLOCKED"
      color = COLOR_BLOCK
    else:
      return

    font_size = 24
    text_w = rl.measure_text(label, font_size)
    w = min(max(text_w + 36, 300), 520)
    x = rect.x + (rect.width - w) / 2
    y = rect.y + rect.height - PILL_H - 38
    pill_rect = rl.Rectangle(x, y, w, PILL_H)
    rl.draw_rectangle_rounded(pill_rect, 0.36, 12, COLOR_BG)
    rl.draw_rectangle_rounded_lines_ex(pill_rect, 0.36, 12, 3, color)
    rl.draw_text(label, int(x + (w - text_w) / 2), int(y + 12), font_size, color)
