#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARAM_NAMES = [
  "ExperimentalMode",
  "AlwaysOffroad",
  "EnableEscc",
  "CarrotLearningActive",
]


class LiveCheckError(Exception):
  pass


def boolish(value: object) -> bool:
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return value != 0
  return str(value).strip().lower() in {"1", "true", "yes", "on"}


def http_json(method: str, url: str, body: Optional[Dict[str, object]] = None, timeout: float = 3.0) -> Tuple[bool, Dict[str, object], str]:
  data = None
  headers = {"Accept": "application/json"}
  if body is not None:
    data = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
  req = Request(url, data=data, method=method, headers=headers)
  try:
    with urlopen(req, timeout=timeout) as resp:
      raw = resp.read().decode("utf-8", errors="replace")
      try:
        parsed = json.loads(raw)
      except json.JSONDecodeError:
        return False, {}, "response was not JSON"
      if not isinstance(parsed, dict):
        return False, {}, "JSON response was not an object"
      return boolish(parsed.get("ok", True)), parsed, ""
  except HTTPError as exc:
    raw = exc.read().decode("utf-8", errors="replace")
    return False, {}, f"HTTP {exc.code}: {raw[:300]}"
  except (OSError, URLError) as exc:
    return False, {}, str(exc)


def read_params(base_url: str, names: List[str], timeout: float) -> Tuple[bool, Dict[str, object], str]:
  joined = ",".join(quote(name) for name in names)
  ok, payload, error = http_json("GET", f"{base_url}/api/params_bulk?names={joined}", timeout=timeout)
  values = payload.get("values") if isinstance(payload, dict) else None
  if not ok:
    return False, {}, error or str(payload.get("error", "unknown error"))
  if not isinstance(values, dict):
    return False, {}, "missing values object"
  missing = [name for name in names if name not in values]
  if missing:
    return False, values, "missing param value(s): " + ", ".join(missing)
  return True, values, ""


def write_param(base_url: str, name: str, value: object, timeout: float) -> Tuple[bool, str]:
  ok, payload, error = http_json("POST", f"{base_url}/api/param_set", {"name": name, "value": value}, timeout=timeout)
  if ok:
    return True, ""
  return False, error or str(payload.get("error", "unknown error"))


def listen_udp_json(port: int, seconds: float) -> Tuple[bool, Dict[str, object], str]:
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except OSError:
      pass
    sock.bind(("", port))
    sock.settimeout(0.25)
    deadline = time.monotonic() + max(seconds, 0.1)
    last_error = ""
    while time.monotonic() < deadline:
      try:
        data, _addr = sock.recvfrom(65535)
      except socket.timeout:
        continue
      try:
        decoded = json.loads(data.decode("utf-8", errors="replace"))
      except Exception as exc:
        last_error = f"non-json UDP packet: {exc}"
        continue
      if isinstance(decoded, dict):
        return True, decoded, ""
    return False, {}, last_error or "timeout waiting for UDP status"
  except OSError as exc:
    return False, {}, str(exc)
  finally:
    sock.close()


def build_test_nav_payload(index: int) -> Dict[str, object]:
  return {
    "carrotIndex": index,
    "carrotCmd": "",
    "carrotArg": "",
    "nRoadLimitSpeed": 50,
    "nSdiType": 1,
    "nSdiSpeedLimit": 50,
    "nSdiDist": 300,
    "nSdiPlusType": 0,
    "nTBTDist": 420,
    "nTBTTurnType": 12,
    "nTBTDistNext": 900,
    "nTBTTurnTypeNext": 13,
    "szTBTMainTextNext": "Navipilot live check",
    "nGoPosDist": 1200,
    "nGoPosTime": 180,
    "vpPosPointLat": 0,
    "vpPosPointLon": 0,
    "latitude": 0,
    "longitude": 0,
  }


def send_test_nav(host: str, port: int, count: int, interval: float) -> Tuple[bool, int, str]:
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sent = 0
  try:
    for idx in range(1, max(count, 1) + 1):
      payload = json.dumps(build_test_nav_payload(idx), separators=(",", ":")).encode("utf-8")
      sock.sendto(payload, (host, port))
      sent += 1
      time.sleep(max(interval, 0.0))
    return True, sent, ""
  except OSError as exc:
    return False, sent, str(exc)
  finally:
    sock.close()


def status_has_required_keys(payload: Dict[str, object]) -> Tuple[bool, List[str]]:
  required = [
    "Carrot2",
    "IsOnroad",
    "active",
    "v_ego_kph",
    "v_cruise_kph",
    "carcruiseSpeed",
    "tbt_dist",
    "sdi_dist",
    "trafficState",
  ]
  missing = [key for key in required if key not in payload]
  return not missing, missing


def run_live_check(args: argparse.Namespace) -> Dict[str, object]:
  host = args.host
  base_url = f"http://{host}:{args.http_port}"
  names = args.params or DEFAULT_PARAM_NAMES
  result: Dict[str, object] = {
    "version": 1,
    "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "host": host,
    "http_port": args.http_port,
    "udp_status_port": args.status_port,
    "udp_nav_port": args.nav_port,
    "param_names": names,
    "param_bulk_ok": False,
    "param_values": {},
    "param_bulk_error": "",
    "param_write_probe_requested": bool(args.param_write_probe),
    "param_write_probe_ok": False,
    "param_write_probe_error": "",
    "udp_7705_listen_requested": args.listen_seconds > 0,
    "udp_7705_seen": False,
    "udp_7705_required_keys_ok": False,
    "udp_7705_missing_keys": [],
    "udp_7705_last_status": {},
    "udp_7705_error": "",
    "udp_7706_send_requested": bool(args.send_test_nav),
    "udp_7706_sent_ok": False,
    "udp_7706_sent_count": 0,
    "udp_7706_error": "",
    "overall_ok": False,
    "notes": [
      "This check validates C3-side Navipilot endpoints; it does not prove the Android app UI has connected.",
      "The test nav packet never sends LANECHANGE or OVERTAKE.",
    ],
  }

  params_ok, values, params_error = read_params(base_url, names, args.timeout)
  result["param_bulk_ok"] = params_ok
  result["param_values"] = values
  result["param_bulk_error"] = params_error

  if args.param_write_probe:
    if params_ok:
      probe_name = args.param_write_name
      probe_value = values.get(probe_name, 0)
      write_ok, write_error = write_param(base_url, probe_name, probe_value, args.timeout)
      result["param_write_probe_ok"] = write_ok
      result["param_write_probe_error"] = write_error
    else:
      result["param_write_probe_error"] = "skipped because param bulk read failed"

  if args.listen_seconds > 0:
    seen, status, listen_error = listen_udp_json(args.status_port, args.listen_seconds)
    result["udp_7705_seen"] = seen
    result["udp_7705_last_status"] = status
    result["udp_7705_error"] = listen_error
    if seen:
      keys_ok, missing = status_has_required_keys(status)
      result["udp_7705_required_keys_ok"] = keys_ok
      result["udp_7705_missing_keys"] = missing

  if args.send_test_nav:
    send_ok, sent, send_error = send_test_nav(host, args.nav_port, args.nav_count, args.nav_interval)
    result["udp_7706_sent_ok"] = send_ok
    result["udp_7706_sent_count"] = sent
    result["udp_7706_error"] = send_error

  required = [bool(result["param_bulk_ok"])]
  if args.param_write_probe:
    required.append(bool(result["param_write_probe_ok"]))
  if args.listen_seconds > 0:
    required.append(bool(result["udp_7705_seen"]))
    required.append(bool(result["udp_7705_required_keys_ok"]))
  if args.send_test_nav:
    required.append(bool(result["udp_7706_sent_ok"]))
  result["overall_ok"] = all(required)
  return result


def flatten_value(value: object) -> str:
  if isinstance(value, (dict, list)):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
  else:
    text = str(value)
  return text.replace("\n", "<br>")


def markdown_report(result: Dict[str, object]) -> str:
  lines: List[str] = []
  lines.append("# Navipilot APP Live Endpoint Check")
  lines.append("")
  lines.append("This report checks C3-side endpoints used by the Navipilot Android app.")
  lines.append("It does not replace a real phone APP connection test.")
  lines.append("")
  lines.append("| Check | Result | Detail |")
  lines.append("| --- | --- | --- |")
  rows = [
    ("7000 params bulk", result.get("param_bulk_ok"), result.get("param_bulk_error") or result.get("param_values")),
    ("7000 param write probe", result.get("param_write_probe_ok") if result.get("param_write_probe_requested") else "SKIPPED", result.get("param_write_probe_error")),
    ("7705 status broadcast", result.get("udp_7705_seen") if result.get("udp_7705_listen_requested") else "SKIPPED", result.get("udp_7705_error") or result.get("udp_7705_last_status")),
    ("7705 required app keys", result.get("udp_7705_required_keys_ok") if result.get("udp_7705_listen_requested") else "SKIPPED", result.get("udp_7705_missing_keys")),
    ("7706 test nav packet", result.get("udp_7706_sent_ok") if result.get("udp_7706_send_requested") else "SKIPPED", result.get("udp_7706_error") or f"sent {result.get('udp_7706_sent_count')} packet(s)"),
  ]
  for name, ok, detail in rows:
    if ok == "SKIPPED":
      state = "SKIPPED"
    else:
      state = "PASS" if bool(ok) else "FAIL"
    lines.append(f"| {name} | {state} | {flatten_value(detail)} |")
  lines.append("")
  lines.append("## Summary")
  lines.append("")
  lines.append(f"- Overall: {'PASS' if result.get('overall_ok') else 'FAIL'}")
  lines.append(f"- Host: `{result.get('host')}`")
  lines.append(f"- HTTP port: `{result.get('http_port')}`")
  lines.append(f"- UDP status port: `{result.get('udp_status_port')}`")
  lines.append(f"- UDP nav port: `{result.get('udp_nav_port')}`")
  lines.append("")
  lines.append("## Safety Notes")
  lines.append("")
  for note in result.get("notes", []):
    lines.append(f"- {note}")
  lines.append("")
  return "\n".join(lines)


def write_outputs(result: Dict[str, object], output: Optional[str], json_output: Optional[str]) -> None:
  if output:
    path = Path(output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_report(result), encoding="utf-8")
    print(f"wrote {path}")
  if json_output:
    path = Path(json_output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path}")


class _SelfTestHandler(BaseHTTPRequestHandler):
  values = {"ExperimentalMode": 0, "AlwaysOffroad": 0, "EnableConnect": 0, "EnableEscc": 0, "CarrotLearningActive": 0}

  def log_message(self, _fmt: str, *_args: object) -> None:
    return

  def _send_json(self, payload: Dict[str, object], status: int = 200) -> None:
    data = json.dumps(payload).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

  def do_GET(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path != "/api/params_bulk":
      self._send_json({"ok": False, "error": "not found"}, 404)
      return
    names = parse_qs(parsed.query).get("names", [""])[0].split(",")
    self._send_json({"ok": True, "values": {name: self.values.get(name, 0) for name in names if name}})

  def do_POST(self) -> None:
    if urlparse(self.path).path != "/api/param_set":
      self._send_json({"ok": False, "error": "not found"}, 404)
      return
    length = int(self.headers.get("Content-Length", "0"))
    body = json.loads(self.rfile.read(length).decode("utf-8"))
    name = body.get("name")
    value = body.get("value")
    if not name:
      self._send_json({"ok": False, "error": "missing name"}, 400)
      return
    self.values[str(name)] = value
    self._send_json({"ok": True, "name": name, "value": value})


def send_selftest_status(port: int) -> None:
  payload = {
    "Carrot2": "SELFTEST",
    "IsOnroad": False,
    "active": False,
    "v_ego_kph": 0,
    "v_cruise_kph": 0,
    "carcruiseSpeed": 0,
    "tbt_dist": 0,
    "sdi_dist": 0,
    "trafficState": 0,
  }
  deadline = time.monotonic() + 1.5
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    data = json.dumps(payload).encode("utf-8")
    while time.monotonic() < deadline:
      sock.sendto(data, ("127.0.0.1", port))
      time.sleep(0.05)
  finally:
    sock.close()


def self_test() -> None:
  server = HTTPServer(("127.0.0.1", 0), _SelfTestHandler)
  http_port = int(server.server_address[1])
  server_thread = threading.Thread(target=server.serve_forever, daemon=True)
  server_thread.start()

  status_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  status_socket.bind(("127.0.0.1", 0))
  status_port = int(status_socket.getsockname()[1])
  status_socket.close()

  nav_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  nav_socket.bind(("127.0.0.1", 0))
  nav_port = int(nav_socket.getsockname()[1])
  nav_socket.close()

  sender = threading.Thread(target=send_selftest_status, args=(status_port,), daemon=True)
  sender.start()
  args = argparse.Namespace(
    host="127.0.0.1",
    http_port=http_port,
    status_port=status_port,
    nav_port=nav_port,
    timeout=2.0,
    listen_seconds=1.0,
    send_test_nav=True,
    nav_count=2,
    nav_interval=0.01,
    param_write_probe=True,
    param_write_name="ExperimentalMode",
    params=DEFAULT_PARAM_NAMES,
  )
  try:
    result = run_live_check(args)
  finally:
    server.shutdown()
    server.server_close()
  if not result.get("overall_ok"):
    raise LiveCheckError("self-test live check failed: " + json.dumps(result, ensure_ascii=False, sort_keys=True))
  report = markdown_report(result)
  if "Navipilot APP Live Endpoint Check" not in report or "7000 params bulk" not in report:
    raise LiveCheckError("self-test report did not include expected sections")


def main() -> int:
  parser = argparse.ArgumentParser(description="Check C3-side Navipilot Android app endpoints.")
  parser.add_argument("--host", default="127.0.0.1", help="C3 host or IP; use 127.0.0.1 when running on the C3")
  parser.add_argument("--http-port", type=int, default=7000, help="C3 carrot_server HTTP port")
  parser.add_argument("--status-port", type=int, default=7705, help="UDP status broadcast port")
  parser.add_argument("--nav-port", type=int, default=7706, help="UDP navigation input port")
  parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout seconds")
  parser.add_argument("--listen-seconds", type=float, default=3.0, help="listen for 7705 status broadcast; 0 disables")
  parser.add_argument("--param-write-probe", action="store_true", help="write ExperimentalMode back to its current value to prove /api/param_set")
  parser.add_argument("--param-write-name", default="ExperimentalMode", help="param used for the same-value write probe")
  parser.add_argument("--send-test-nav", action="store_true", help="send a parked test nav packet to UDP 7706; no lanechange/overtake command is sent")
  parser.add_argument("--nav-count", type=int, default=6, help="number of test nav packets when --send-test-nav is used")
  parser.add_argument("--nav-interval", type=float, default=0.05, help="seconds between test nav packets")
  parser.add_argument("--param", dest="params", action="append", help="param name to read; may be repeated")
  parser.add_argument("--output", help="write markdown report")
  parser.add_argument("--json-output", help="write machine-readable JSON report")
  parser.add_argument("--self-test", action="store_true", help="run local HTTP/UDP parser self-test")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("OK: Navipilot live check self-test passed")
      return 0
    result = run_live_check(args)
    write_outputs(result, args.output, args.json_output)
    if not args.output and not args.json_output:
      print(markdown_report(result))
    return 0 if result.get("overall_ok") else 2
  except Exception as exc:
    print("Navipilot live check failed:", exc)
    return 2


if __name__ == "__main__":
  sys.exit(main())
