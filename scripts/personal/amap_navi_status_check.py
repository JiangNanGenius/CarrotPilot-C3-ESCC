#!/usr/bin/env python3
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import List


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class CheckError(Exception):
  pass


def read(relpath: str) -> str:
  return (ROOT / relpath).read_text(encoding="utf-8", errors="replace")


def exists(relpath: str) -> bool:
  return (ROOT / relpath).exists()


def require(label: str, condition: bool, failures: List[str]) -> None:
  if not condition:
    failures.append(label)


def main() -> int:
  failures: List[str] = []
  custom = read("cereal/custom.capnp")
  log = read("cereal/log.capnp")
  services = read("cereal/services.py")
  params = read("common/params_keys.h")
  settings = read("selfdrive/carrot_settings.json")
  manager = read("system/manager/process_config.py")
  module = read("selfdrive/carrot/app_navi_status.py") if exists("selfdrive/carrot/app_navi_status.py") else ""
  desire = read("selfdrive/controls/lib/desire_helper.py")
  carrot_man = read("selfdrive/carrot/carrot_man.py")

  require("AmapNavi struct exists", "struct AmapNavi @0xaedffd8f31e7b55d" in custom, failures)
  for field in ("leftBlind @0", "rightBlind @1", "lineValid @2", "leftLine @3", "rightLine @4"):
    require(f"AmapNavi field exists: {field}", field in custom, failures)
  require("log event maps custom slot 108 to amapNavi", "amapNavi @108 :Custom.AmapNavi" in log, failures)
  require("amapNavi service registered", '"amapNavi": (True, 20., 5)' in services, failures)
  require("EnableAmapNaviStatus param default off", '{"EnableAmapNaviStatus", {PERSISTENT, INT, "0"}}' in params, failures)
  require("EnableAmapNaviStatus setting default off", '"name": "EnableAmapNaviStatus"' in settings and '"default": 0' in settings, failures)
  require("setting says no app commands", "不接收 APP 命令" in settings, failures)
  require("setting says no external blinker", "不控制外接转向灯" in settings, failures)
  require("setting says no overtake", "不启用自动超车" in settings, failures)

  require("app_navi_status module exists", bool(module), failures)
  require("module publishes amapNavi", 'PubMaster(["amapNavi"])' in module, failures)
  require("module only subscribes carState", 'SubMaster(["carState"])' in module, failures)
  require("module maps stock left blindspot", "leftBlindspot" in module and "OEM_BLIND_BIT" in module, failures)
  require("module maps lane lines", "leftLaneLine" in module and "rightLaneLine" in module, failures)
  for forbidden in ("socket", "carrotCmd", "OVERTAKE", "blinker_ctrl", "4210", "4211", "4212", "4213", "7706"):
    require(f"module omits high-risk marker: {forbidden}", forbidden not in module, failures)

  require("manager gate exists", "def enable_app_navi_status" in manager, failures)
  require("manager gate reads EnableAmapNaviStatus", "EnableAmapNaviStatus" in manager, failures)
  require(
    "manager starts app_navi_status through gate",
    'PythonProcess("app_navi_status", "selfdrive.carrot.app_navi_status", enable_app_navi_status)' in manager,
    failures,
  )

  require("desire helper does not consume amapNavi", "amapNavi" not in desire, failures)
  require("desire helper does not accept OVERTAKE", "OVERTAKE" not in desire, failures)
  require("carrot_man does not import fishop AmapNaviServ", "AmapNaviServ" not in carrot_man, failures)

  try:
    from selfdrive.carrot.app_navi_status import build_payload
    payload = build_payload(SimpleNamespace(
      leftLaneLine=10,
      rightLaneLine=21,
      leftBlindspot=True,
      rightBlindspot=False,
    ))
    require("payload maps stock left blindspot to OEM bit", payload.get("leftBlind") == 2, failures)
    require("payload keeps right blindspot clear", payload.get("rightBlind") == 0, failures)
    require("payload preserves lane line codes", payload.get("leftLine") == 10 and payload.get("rightLine") == 21, failures)
    require("payload marks line data valid", payload.get("lineValid") is True, failures)
  except Exception as exc:
    failures.append(f"payload builder import/mock failed: {exc}")

  print("AmapNavi status compatibility check")
  print("repo:", ROOT)
  if failures:
    for failure in failures:
      print("[FAIL]", failure)
    return 2
  print("OK: read-only AmapNavi status bridge is present, default-off, and not wired into control paths")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
