#!/usr/bin/env python3
import argparse
import re
import subprocess
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[2]


class Report:
  def __init__(self) -> None:
    self.passed: List[str] = []
    self.warned: List[str] = []
    self.failed: List[str] = []

  def pass_(self, label: str) -> None:
    self.passed.append(label)

  def warn(self, label: str, detail: str = "") -> None:
    self.warned.append(label if not detail else f"{label}: {detail}")

  def fail(self, label: str, detail: str = "") -> None:
    self.failed.append(label if not detail else f"{label}: {detail}")

  def require(self, label: str, condition: bool, detail: str = "") -> None:
    if condition:
      self.pass_(label)
    else:
      self.fail(label, detail)

  def contains(self, label: str, path: str, needle: str) -> None:
    text = read_text(path)
    self.require(label, needle in text, f"missing {needle!r} in {path}")

  def regex(self, label: str, path: str, pattern: str) -> None:
    text = read_text(path)
    self.require(label, re.search(pattern, text, re.S) is not None, f"missing pattern {pattern!r} in {path}")


def read_text(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8")


def git(args: List[str]) -> Tuple[int, str]:
  proc = subprocess.run(
    ["git"] + args,
    cwd=str(ROOT),
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  return proc.returncode, proc.stdout.strip()


def ref_exists(ref: str) -> bool:
  code, _ = git(["rev-parse", "--verify", "--quiet", ref])
  return code == 0


def check_tracking_refs(report: Report) -> None:
  if ref_exists("jixie/master"):
    report.pass_("jixie/master fetched")
  else:
    report.warn("jixie/master not fetched", "run git fetch jixie before reviewing CPlink/Navipilot updates")

  if ref_exists("tracking/jixie-master"):
    report.pass_("tracking branch exists: tracking/jixie-master")
  else:
    report.warn("tracking/jixie-master missing", "create it before the next source review")

  if ref_exists("jixie-navipilot/CPdazi"):
    report.pass_("jixie-navipilot/CPdazi fetched")
  else:
    report.warn("jixie-navipilot/CPdazi not fetched", "run git fetch jixie-navipilot before reviewing the Android CP搭子 app")

  if ref_exists("tracking/jixie-navipilot"):
    report.pass_("tracking branch exists: tracking/jixie-navipilot")
  else:
    report.warn("tracking/jixie-navipilot missing", "create it before the next Navipilot app source review")


def check_cereal_protocol(report: Report) -> None:
  report.contains("custom.capnp has CarrotMan struct", "cereal/custom.capnp", "struct CarrotMan")
  for field in [
    "activeCarrot",
    "nRoadLimitSpeed",
    "xSpdType",
    "xSpdLimit",
    "xSpdDist",
    "xTurnInfo",
    "xDistToTurn",
    "atcType",
    "vTurnSpeed",
    "szTBTMainText",
    "carrotCmdIndex",
    "carrotCmd",
    "carrotArg",
    "xPosLat",
    "xPosLon",
    "trafficState",
    "naviPaths",
  ]:
    report.contains(f"CarrotMan field: {field}", "cereal/custom.capnp", field)

  report.contains("log.capnp includes carrotMan service", "cereal/log.capnp", "carrotMan @107 :Custom.CarrotMan")
  report.contains("log.capnp includes navInstructionCarrot", "cereal/log.capnp", "navInstructionCarrot @126 :NavInstruction")
  report.contains("services.py includes carrotMan", "cereal/services.py", '"carrotMan"')
  report.contains("services.py includes navInstructionCarrot", "cereal/services.py", '"navInstructionCarrot"')


def check_carrotman_runtime(report: Report) -> None:
  report.contains("CarrotMan class exists", "selfdrive/carrot/carrot_man.py", "class CarrotMan")
  report.contains("CarrotMan publishes carrotMan", "selfdrive/carrot/carrot_man.py", "'carrotMan'")
  report.contains("CarrotMan publishes navInstructionCarrot", "selfdrive/carrot/carrot_man.py", "navInstructionCarrot")
  report.regex("CarrotMan broadcasts on 7705", "selfdrive/carrot/carrot_man.py", r"broadcast_port\s*=\s*7705")
  report.regex("CarrotMan listens on 7706", "selfdrive/carrot/carrot_man.py", r"carrot_man_port\s*=\s*7706")
  report.contains("manager runs carrot_man", "system/manager/process_config.py", 'PythonProcess("carrot_man"')
  report.contains("manager runs carrot_server", "system/manager/process_config.py", 'PythonProcess("carrot_server"')


def check_status_broadcast(report: Report) -> None:
  report.contains("CarrotMan broadcasts discovery/status on 7705", "selfdrive/carrot/carrot_man.py", "self.broadcast_port = 7705")
  report.contains("CarrotMan status message builder exists", "selfdrive/carrot/carrot_man.py", "def make_send_message")
  for key in [
    "Carrot2",
    "IsOnroad",
    "CarrotRouteActive",
    "ip",
    "port",
    "navi_http_port",
    "log_carrot",
    "v_cruise_kph",
    "carcruiseSpeed",
    "v_ego_kph",
    "tbt_dist",
    "sdi_dist",
    "active",
    "xState",
    "trafficState",
  ]:
    report.contains(f"7705 status key for Navipilot app: {key}", "selfdrive/carrot/carrot_man.py", f"'{key}'")


def check_cplink_payload(report: Report) -> None:
  for key in [
    "carrotIndex",
    "carrotCmd",
    "carrotArg",
    "goalPosX",
    "goalPosY",
    "nRoadLimitSpeed",
    "nSdiType",
    "nSdiSpeedLimit",
    "nSdiDist",
    "nSdiPlusType",
    "nTBTDist",
    "nTBTTurnType",
    "nTBTDistNext",
    "nTBTTurnTypeNext",
    "szTBTMainTextNext",
    "nGoPosDist",
    "nGoPosTime",
    "vpPosPointLat",
    "vpPosPointLon",
    "latitude",
    "longitude",
  ]:
    report.contains(f"CPlink payload key parsed: {key}", "selfdrive/carrot/carrot_serv.py", f'"{key}"')

  for field in [
    "msg.carrotMan.nRoadLimitSpeed",
    "msg.carrotMan.xSpdType",
    "msg.carrotMan.xTurnInfo",
    "msg.carrotMan.carrotCmdIndex",
    "msg.carrotMan.carrotCmd",
    "msg.carrotMan.carrotArg",
    "msg.carrotMan.xPosLat",
    "msg.carrotMan.xPosLon",
    "pm.send('carrotMan'",
    "pm.send('navInstructionCarrot'",
  ]:
    report.contains(f"CarrotMan output field: {field}", "selfdrive/carrot/carrot_serv.py", field)

  report.regex(
    "TBT next text reads the correct app key",
    "selfdrive/carrot/carrot_serv.py",
    r"szTBTMainTextNext\s*=\s*_s\(json\.get\(\"szTBTMainTextNext\"\)\)",
  )


def check_navipilot_websocket(report: Report) -> None:
  report.contains("WebSocket raw multiplex endpoint exists", "selfdrive/carrot/server/features/ws.py", '"/ws/raw_multiplex"')
  report.contains("WebSocket raw service endpoint exists", "selfdrive/carrot/server/features/ws.py", '"/ws/raw/{service}"')
  report.contains("WebSocket camera endpoint exists", "selfdrive/carrot/server/features/ws.py", '"/ws/camera/{camera}"')
  for service in [
    "carState",
    "modelV2",
    "controlsState",
    "selfdriveState",
    "deviceState",
    "carrotMan",
    "gpsLocationExternal",
  ]:
    report.contains(f"Navipilot default WS service allowed: {service}", "selfdrive/carrot/server/live_runtime/services.py", f'"{service}"')


def check_navipilot_param_api(report: Report) -> None:
  report.contains("Params REST bulk endpoint handler exists", "selfdrive/carrot/server/features/params.py", "async def api_params_bulk")
  report.contains("Params REST set endpoint handler exists", "selfdrive/carrot/server/features/params.py", "async def api_param_set")
  report.contains("Params REST bulk route exists", "selfdrive/carrot/server/features/params.py", 'app.router.add_get("/api/params_bulk"')
  report.contains("Params REST set route exists", "selfdrive/carrot/server/features/params.py", 'app.router.add_post("/api/param_set"')
  report.contains("Params REST returns values object", "selfdrive/carrot/server/features/params.py", '"values": values')
  report.contains("Params REST writes named param", "selfdrive/carrot/server/features/params.py", "set_param_value(name, value)")
  report.contains("Params service supports bulk reads", "selfdrive/carrot/server/services/params.py", "def get_param_values")
  report.contains("Params service supports typed writes", "selfdrive/carrot/server/services/params.py", "def set_param_value")
  report.contains("Params service uses typed put", "selfdrive/carrot/server/services/params.py", "put_typed(params, name, value)")
  report.contains("ExperimentalMode is a Web device control param", "selfdrive/carrot/server/features/system.py", '"ExperimentalMode"')
  report.contains("ExperimentalMode confirmation param exists", "selfdrive/carrot/server/features/system.py", '"ExperimentalModeConfirmed"')


def check_navipilot_app_source_contract(report: Report) -> None:
  if not ref_exists("tracking/jixie-navipilot"):
    report.warn("Navipilot app source contract not checked", "tracking/jixie-navipilot is not available")
    return

  files = {
    "app/src/main/java/com/example/navipilot/data/CarrotWsClient.kt": [
      'private const val WS_RAW_PATH = "/ws/raw_multiplex"',
      'private const val WS_CAMERA_PATH = "/ws/camera/road"',
      "object MultiplexFrame",
      "readUnsignedByte()",
      "object CameraWsFrame",
      "dis.readInt()",
      '"carState"',
      '"modelV2"',
      '"controlsState"',
      '"selfdriveState"',
      '"deviceState"',
      '"carrotMan"',
      '"gpsLocationExternal"',
    ],
    "app/src/main/java/com/example/navipilot/NetworkManager.kt": [
      'optBoolean("IsOnroad", false)',
      'optDouble("v_cruise_kph", 0.0)',
      'optDouble("carcruiseSpeed", 0.0)',
      'optInt("v_ego_kph", 0)',
      'optInt("tbt_dist", 0)',
      'optInt("sdi_dist", 0)',
      'optBoolean("active", false)',
      'optInt("xState", 0)',
      'optInt("trafficState", 0)',
      "setOnDeviceIPUpdated",
    ],
    "app/src/main/java/com/example/navipilot/MainActivityLifecycle.kt": [
      "startOnroadMonitoring",
      "shouldCollect = isConnected && isOnroad",
      "drivingDataCollector?.startCollecting()",
      "drivingDataCollector?.stopCollecting()",
      "drivingDataCollector?.updateData(",
    ],
    "app/src/main/java/com/example/navipilot/CarrotParamClient.kt": [
      'private const val PORT = 7000',
      'url("$baseUrl/api/param_set")',
      'url("$baseUrl/api/params_bulk?names=$namesStr")',
      'put("name", name)',
      'put("value", value)',
      'resp.getJSONObject("values")',
      'setParam("ExperimentalMode"',
    ],
  }

  for relpath, needles in files.items():
    code, text = git(["show", f"tracking/jixie-navipilot:{relpath}"])
    if code != 0:
      report.warn(f"Navipilot app source missing: {relpath}", "update tracking/jixie-navipilot before reviewing app compatibility")
      continue
    for needle in needles:
      report.require(f"Navipilot app expects: {needle}", needle in text, f"missing {needle!r} in tracking/jixie-navipilot:{relpath}")

  code, text = git(["show", "tracking/jixie-navipilot:app/src/main/java/com/example/navipilot/data/CarrotWsClient.kt"])
  if code == 0 and "private fun decodeCarrotMan" in text and "return null" in text:
    report.warn("Navipilot app carrotMan raw decoder is incomplete", "7705 status broadcast remains the reliable source for onroad/active/speed in the current app")


def check_controls_consumers(report: Report) -> None:
  report.contains("controlsd subscribes carrotMan", "selfdrive/controls/controlsd.py", "'carrotMan'")
  report.contains("plannerd subscribes carrotMan", "selfdrive/controls/plannerd.py", "'carrotMan'")
  report.contains("lateral planner reads carrotMan speed", "selfdrive/controls/lib/lateral_planner.py", "sm['carrotMan'].vTurnSpeed")
  report.contains("desire helper handles LANECHANGE command", "selfdrive/controls/lib/desire_helper.py", 'carrotMan.carrotCmd == "LANECHANGE"')
  if "OVERTAKE" not in read_text("selfdrive/controls/lib/desire_helper.py"):
    report.warn("OVERTAKE command not integrated", "keep fishop/jixie overtake logic as a later, separately-gated batch")


def manual_items() -> List[str]:
  return [
    "Install CP搭子 on Android and confirm the phone and C3 are on the same WiFi.",
    "Confirm CP搭子 discovers the C3 broadcast on UDP 7705 and receives IsOnroad, active, v_ego_kph, and v_cruise_kph.",
    "Confirm CP搭子 sends navigation data to UDP 7706.",
    "During navigation, confirm nRoadLimitSpeed, TBT, SDI, and GPS fields change in carrotMan.",
    "For Navipilot driving report, confirm the Android app starts collection only after connected + IsOnroad and saves a score after stopping.",
    "Send a LANECHANGE command from the app and confirm the command is accepted only under safe lane-change conditions.",
    "Do not treat OVERTAKE, external blinker control, fishop full AmapNavi command service, or sentry mode as integrated until they get separate guarded commits.",
  ]


def print_report(report: Report, show_manual: bool) -> None:
  print("CPlink / Navipilot protocol preflight")
  print("repo:", ROOT)
  for label in report.passed:
    print("[PASS]", label)
  for label in report.warned:
    print("[WARN]", label)
  for label in report.failed:
    print("[FAIL]", label)
  if show_manual:
    print("Manual checks still required:")
    for item in manual_items():
      print("[TODO]", item)
  if report.failed:
    print("FAILED: %d check(s)" % len(report.failed))
  else:
    print("OK: CPlink static protocol preflight passed")


def main() -> int:
  parser = argparse.ArgumentParser(description="Static CPlink/Navipilot compatibility preflight.")
  parser.add_argument("--no-manual", action="store_true", help="Do not print manual device/app checks.")
  args = parser.parse_args()

  report = Report()
  check_tracking_refs(report)
  check_cereal_protocol(report)
  check_carrotman_runtime(report)
  check_status_broadcast(report)
  check_cplink_payload(report)
  check_navipilot_websocket(report)
  check_navipilot_param_api(report)
  check_navipilot_app_source_contract(report)
  check_controls_consumers(report)

  print_report(report, show_manual=not args.no_manual)
  return 1 if report.failed else 0


if __name__ == "__main__":
  raise SystemExit(main())
