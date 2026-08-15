#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
TITLE = "Genius Pilot C3 Touch Fallback Contract"
EXPAND_PX = 55


@dataclass(frozen=True)
class Rect:
  x: float
  y: float
  width: float
  height: float

  def expanded(self, px: float) -> "Rect":
    return Rect(self.x - px, self.y - px, self.width + px * 2, self.height + px * 2)

  def contains(self, point: tuple[float, float]) -> bool:
    px, py = point
    return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


class FallbackHarness:
  def __init__(self):
    self.actions: list[tuple[Rect, Callable[[], None], Callable[[], bool]]] = []
    self.ignore_release_after_press = False

  def set_actions(self, actions: list[tuple[Rect, Callable[[], None], Callable[[], bool] | bool]]) -> None:
    self.actions = []
    for rect, callback, enabled in actions:
      enabled_cb = enabled if callable(enabled) else (lambda value=bool(enabled): value)
      self.actions.append((rect.expanded(EXPAND_PX), callback, enabled_cb))

  def activate_at(self, point: tuple[float, float]) -> bool:
    for rect, callback, enabled_cb in reversed(self.actions):
      if enabled_cb() and rect.contains(point):
        callback()
        return True
    return False

  def press(self, point: tuple[float, float]) -> None:
    self.ignore_release_after_press = self.activate_at(point)

  def release(self, point: tuple[float, float]) -> None:
    if self.ignore_release_after_press:
      self.ignore_release_after_press = False
      return
    self.activate_at(point)


def read(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
  return {"name": name, "ok": bool(ok), "detail": detail}


def source_checks() -> list[dict[str, Any]]:
  setup = read("system/ui/tici_setup.py")
  updater = read("system/ui/tici_updater.py")
  settings = read("openpilot/selfdrive/ui/layouts/settings/settings.py")
  settings_sp = read("openpilot/selfdrive/ui/sunnypilot/layouts/settings/settings.py")

  checks: list[dict[str, Any]] = []
  checks.append(check(
    "TICI setup has parent-level fallback actions",
    "CRITICAL_TAP_EXPAND_PX = 55" in setup
    and "self._fallback_actions" in setup
    and "def _set_fallback_actions" in setup
    and "def _activate_at" in setup
    and "for rect, callback, enabled_cb in reversed(self._fallback_actions)" in setup
    and "enabled_cb() and rl.check_collision_point_rec(mouse_pos, rect)" in setup
    and "self._ignore_release_after_press = self._activate_at(mouse_pos)" in setup,
  ))
  checks.append(check(
    "TICI setup critical screens are wired",
    all(token in setup for token in (
      "render_low_voltage",
      "render_getting_started",
      "render_network_setup",
      "render_software_selection",
      "render_download_failed",
      "render_custom_software_warning",
      "_select_openpilot",
      "_select_custom_software",
      "_network_setup_continue_button_callback",
    ))
    and "lambda: self.network_connected.is_set()" in setup
    and "lambda: self._software_selection_continue_button.enabled" in setup
    and "lambda: self._custom_software_warning_continue_button.enabled" in setup
    and "button.set_tap_release_move_px(140)" in setup,
  ))
  checks.append(check(
    "TICI updater has expanded prompt fallback",
    "CRITICAL_TAP_EXPAND_PX = 55" in updater
    and "button.set_tap_release_move_px(140)" in updater
    and "def _critical_tap_rect" in updater
    and "def _tap_in" in updater
    and "def _activate_at" in updater
    and "self._tap_in(mouse_pos, self._install_button_rect)" in updater
    and "self._tap_in(mouse_pos, self._wifi_button_rect)" in updater
    and "self._tap_in(mouse_pos, self._back_button_rect)" in updater
    and "self._tap_in(mouse_pos, self._reboot_button_rect)" in updater
    and "self.current_screen == Screen.PROGRESS" in updater
    and "self.update_thread is not None and self.update_thread.is_alive()" in updater,
  ))
  checks.append(check(
    "settings entry guard and sidebar relaxed tap remain present",
    "OPEN_TOUCH_GUARD_S = 1.2" in settings
    and "not mouse_down and rl.get_time() >= self._ignore_touch_guard_until" in settings
    and "SIDEBAR_NAV_TAP_MAX_MOVE = 96" in settings_sp
    and "CLOSE_TAP_MAX_MOVE = 44" in settings_sp
    and "SIDEBAR_RELEASE_EXPAND_PX = 40" in settings_sp
    and "def _panel_at_relaxed" in settings_sp
    and "_tap_moved_too_far" in settings_sp
    and "self._press_panel_pos" in settings_sp,
  ))
  return checks


def behavior_checks() -> list[dict[str, Any]]:
  checks: list[dict[str, Any]] = []

  base_rect = Rect(100, 100, 200, 100)
  expanded = base_rect.expanded(EXPAND_PX)
  checks.append(check(
    "expanded critical hit region accepts clone-C3 edge drift",
    expanded.contains((50, 105))
    and expanded.contains((355, 255))
    and not expanded.contains((44, 105))
    and not expanded.contains((356, 256)),
  ))

  events: list[str] = []
  harness = FallbackHarness()
  harness.set_actions([(base_rect, lambda: events.append("install"), True)])
  harness.press((50, 105))
  harness.release((50, 105))
  checks.append(check(
    "press fallback triggers once and release is suppressed",
    events == ["install"],
    repr(events),
  ))

  events.clear()
  harness.press((10, 10))
  harness.release((50, 105))
  checks.append(check(
    "release fallback still works when press event is lost",
    events == ["install"],
    repr(events),
  ))

  events.clear()
  harness.set_actions([(base_rect, lambda: events.append("disabled"), False)])
  harness.press((150, 150))
  harness.release((150, 150))
  checks.append(check(
    "disabled fallback action cannot fire",
    events == [],
    repr(events),
  ))

  events.clear()
  harness.set_actions([
    (Rect(0, 0, 200, 200), lambda: events.append("older"), True),
    (Rect(0, 0, 200, 200), lambda: events.append("newer"), True),
  ])
  harness.press((100, 100))
  checks.append(check(
    "later rendered fallback action wins overlapping hit regions",
    events == ["newer"],
    repr(events),
  ))

  return checks


def build_report() -> dict[str, Any]:
  checks = source_checks() + behavior_checks()
  return {"title": TITLE, "ok": all(item["ok"] for item in checks), "checks": checks}


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    TITLE,
    "FallbackHarness",
    "CRITICAL_TAP_EXPAND_PX = 55",
    "button.set_tap_release_move_px(140)",
    "OPEN_TOUCH_GUARD_S = 1.2",
    "press fallback triggers once",
    "release fallback still works",
    "disabled fallback action cannot fire",
  )
  if not all(token in text for token in required):
    print(f"FAIL {TITLE} self-test: missing token")
    return 1
  report = build_report()
  if not report["ok"]:
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1
  print(f"PASS {TITLE} self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description=TITLE)
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report = build_report()
  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    print(f"{'PASS' if report['ok'] else 'FAIL'} {TITLE}")
    for item in report["checks"]:
      print(f"{'PASS' if item['ok'] else 'FAIL'} {item['name']}")
      if not item["ok"] and item.get("detail"):
        print(item["detail"])
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
