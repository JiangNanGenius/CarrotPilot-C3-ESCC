#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 7000
DEFAULT_STATUS_PORT = 7705
DEFAULT_NAV_PORT = 7706
DEFAULT_NAVI_TCP_PORT = 7712
DEFAULT_NAVI_HTTP_PORT = 7713

DEFAULT_PARAM_NAMES = [
  "ExperimentalMode",
  "ExperimentalModeConfirmed",
  "SpeedFromPCM",
  "OffroadMode",
  "CarrotMapOverlayEnabled",
  "CarrotPhoneSpeedLimitEnabled",
  "CarrotActiveSpeedControlEnabled",
  "CarrotTrafficStopEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotLearningActive",
  "CarrotLearningAutoApply",
  "FishopAutoOvertakeEnabled",
]

READ_ONLY_PARAM_NAMES = {
  "OffroadMode",
  "SpeedFromPCM",
}

WRITABLE_SAME_VALUE_PARAM_NAMES = {
  "ExperimentalMode",
  "ExperimentalModeConfirmed",
  "CarrotMapOverlayEnabled",
  "CarrotPhoneSpeedLimitEnabled",
  "CarrotActiveSpeedControlEnabled",
  "CarrotTrafficStopEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotLearningActive",
  "CarrotLearningAutoApply",
  "FishopAutoOvertakeEnabled",
}

REQUIRED_HEALTH_ENDPOINTS = {
  "/api/health",
  "/api/params_bulk",
  "/api/param_set",
  "/api/status_broadcast",
  "/api/navigation_event",
  "/api/navi",
  "/api/navi/tcp_health",
  "/api/phone_speed_limit",
}

REQUIRED_STATUS_KEYS = [
  "Carrot2",
  "IsOnroad",
  "CarrotRouteActive",
  "ip",
  "port",
  "navi_http_port",
  "navi_tcp_port",
  "log_carrot",
  "active",
  "v_ego_kph",
  "v_cruise_kph",
  "carcruiseSpeed",
  "tbt_dist",
  "sdi_dist",
  "sdi_type",
  "speedBumpDist",
  "modelSpeedKph",
  "carrotControlPreview",
  "navigationHazards",
  "xState",
  "trafficState",
  "controlOutput",
]

class LiveCheckError(Exception):
  pass


def now_text() -> str:
  return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def compact(value: Any, limit: int = 500) -> str:
  if isinstance(value, (dict, list)):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
  else:
    text = str(value)
  text = text.replace("\n", " ")
  return text if len(text) <= limit else text[:limit - 3] + "..."


def check(name: str, status: str, detail: str = "", evidence: Any = None) -> dict[str, Any]:
  return {
    "name": name,
    "status": status,
    "detail": detail,
    "evidence": evidence if evidence is not None else {},
  }


def boolish(value: Any) -> bool:
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return value != 0
  return str(value).strip().lower() in {"1", "true", "yes", "on"}


def http_json(host: str, port: int, method: str, path: str, body: dict[str, Any] | None, timeout: float) -> tuple[int, dict[str, Any]]:
  payload = b""
  headers = {"Accept": "application/json"}
  if body is not None:
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers["Content-Type"] = "application/json"
  conn = http.client.HTTPConnection(host, port, timeout=timeout)
  try:
    conn.request(method, path, body=payload if body is not None else None, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
  finally:
    conn.close()
  try:
    parsed = json.loads(raw or "{}")
  except json.JSONDecodeError as exc:
    raise LiveCheckError(f"{method} {host}:{port}{path} returned non-json response: {exc}") from exc
  if not isinstance(parsed, dict):
    raise LiveCheckError(f"{method} {host}:{port}{path} returned non-object JSON")
  return resp.status, parsed


def unavailable_check(name: str, exc: Exception, allow_unavailable: bool) -> dict[str, Any]:
  status = "warn" if allow_unavailable else "fail"
  return check(name, status, "endpoint unavailable", {"error": str(exc)})


def query_json_check(host: str, port: int, path: str, timeout: float,
                     allow_unavailable: bool, name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
  try:
    status, payload = http_json(host, port, "GET", path, None, timeout)
  except Exception as exc:
    return None, unavailable_check(name, exc, allow_unavailable)
  if status >= 400 or not boolish(payload.get("ok", True)):
    return payload, check(name, "fail", f"HTTP {status}", payload)
  return payload, check(name, "pass", "", payload)


def validate_health(payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
  endpoints = set(payload.get("endpoints", [])) if isinstance(payload.get("endpoints"), list) else set()
  missing_endpoints = sorted(REQUIRED_HEALTH_ENDPOINTS - endpoints)
  evidence = {
    "service": payload.get("service"),
    "mode": payload.get("mode"),
    "cloudServices": payload.get("cloudServices"),
    "controlOutput": payload.get("controlOutput"),
    "statusBroadcastPort": payload.get("statusBroadcastPort"),
    "navigationUdpPort": payload.get("navigationUdpPort"),
    "naviHttpPort": payload.get("naviHttpPort"),
    "naviTcpPort": payload.get("naviTcpPort"),
    "missingEndpoints": missing_endpoints,
  }
  failures: list[str] = []
  if payload.get("mode") != "local":
    failures.append("mode is not local")
  if payload.get("cloudServices") is not False:
    failures.append("cloudServices is not false")
  if payload.get("controlOutput") is not False:
    failures.append("controlOutput is not false")
  if int(payload.get("statusBroadcastPort", 0)) != DEFAULT_STATUS_PORT:
    failures.append("status port is not 7705")
  if int(payload.get("navigationUdpPort", 0)) != DEFAULT_NAV_PORT:
    failures.append("navigation UDP port is not 7706")
  if int(payload.get("naviHttpPort", 0)) != DEFAULT_NAVI_HTTP_PORT:
    failures.append("navigation HTTP port is not 7713")
  if int(payload.get("naviTcpPort", 0)) != DEFAULT_NAVI_TCP_PORT:
    failures.append("navigation TCP port is not 7712")
  if missing_endpoints:
    failures.append("missing health endpoints")
  return not failures, "; ".join(failures), evidence


def validate_params(payload: dict[str, Any], names: list[str]) -> tuple[bool, str, dict[str, Any]]:
  values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
  writable = payload.get("writable") if isinstance(payload.get("writable"), dict) else {}
  read_only = payload.get("readOnly") if isinstance(payload.get("readOnly"), dict) else {}
  missing = [name for name in names if name not in values]
  bad_read_only = [name for name in READ_ONLY_PARAM_NAMES if name in values and not bool(read_only.get(name, False))]
  bad_writable = [name for name in WRITABLE_SAME_VALUE_PARAM_NAMES if name in values and not bool(writable.get(name, False))]
  failures: list[str] = []
  if payload.get("source") != "local_safe_whitelist":
    failures.append("param source is not local_safe_whitelist")
  if payload.get("has_params") is not True and payload.get("hasParams") is not True:
    failures.append("Params unavailable")
  if missing:
    failures.append("missing requested params")
  if bad_read_only:
    failures.append("high-risk params are writable")
  if bad_writable:
    failures.append("expected same-value params are not writable")
  evidence = {
    "source": payload.get("source"),
    "has_params": payload.get("has_params", payload.get("hasParams")),
    "missing": missing,
    "readOnly": {name: read_only.get(name) for name in sorted(READ_ONLY_PARAM_NAMES) if name in values},
    "writable": {name: writable.get(name) for name in sorted(WRITABLE_SAME_VALUE_PARAM_NAMES) if name in values},
  }
  return not failures, "; ".join(failures), evidence


def validate_status_payload(payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
  missing = [key for key in REQUIRED_STATUS_KEYS if key not in payload]
  preview = payload.get("carrotControlPreview") if isinstance(payload.get("carrotControlPreview"), dict) else {}
  preview_control_output = preview.get("controlOutput", False)
  evidence = {
    "missing": missing,
    "Carrot2": payload.get("Carrot2"),
    "IsOnroad": payload.get("IsOnroad"),
    "xState": payload.get("xState"),
    "trafficState": payload.get("trafficState"),
    "controlOutput": payload.get("controlOutput"),
    "previewControlOutput": preview_control_output,
    "carrotManCompatible": payload.get("carrotManCompatible"),
    "naviHttpAvailable": payload.get("naviHttpAvailable"),
    "naviTcpAvailable": payload.get("naviTcpAvailable"),
  }
  failures: list[str] = []
  if missing:
    failures.append("missing status keys")
  if payload.get("xState") != 0:
    failures.append("xState must stay 0 before Carrot control migration")
  if payload.get("trafficState") != 0:
    failures.append("trafficState must stay 0 before Carrot control migration")
  if payload.get("controlOutput") is not False:
    failures.append("controlOutput must be false")
  if preview_control_output is not False:
    failures.append("carrotControlPreview.controlOutput must be false")
  if payload.get("carrotManCompatible") is not True:
    failures.append("carrotManCompatible must be true")
  return not failures, "; ".join(failures), evidence


def safe_navigation_payload() -> dict[str, Any]:
  return {
    "carrotIndex": 1,
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
    "speedBumpDistance": 0,
    "modelSpeedKph": 0,
    "latitude": 0,
    "longitude": 0,
    "source": "navipilot_live_check",
  }


def listen_udp_status(port: int, seconds: float) -> tuple[dict[str, Any] | None, str]:
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
        last_error = str(exc)
        continue
      if isinstance(decoded, dict):
        return decoded, ""
    return None, last_error or "timeout waiting for UDP status"
  except OSError as exc:
    return None, str(exc)
  finally:
    sock.close()


def send_udp_navigation(host: str, port: int) -> tuple[bool, str]:
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    data = json.dumps(safe_navigation_payload(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sock.sendto(data, (host, port))
    return True, ""
  except OSError as exc:
    return False, str(exc)
  finally:
    sock.close()


def send_tcp_navigation(host: str, port: int, timeout: float) -> tuple[bool, str]:
  try:
    with socket.create_connection((host, port), timeout=timeout) as sock:
      payload = {"rgdata": safe_navigation_payload()}
      sock.sendall(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")
    return True, ""
  except OSError as exc:
    return False, str(exc)


def poll_navigation_source(host: str, port: int, timeout: float, source_prefix: str, deadline_s: float = 2.0) -> tuple[bool, dict[str, Any]]:
  deadline = time.monotonic() + deadline_s
  last_payload: dict[str, Any] = {}
  while time.monotonic() < deadline:
    try:
      status, payload = http_json(host, port, "GET", "/api/navigation_event", None, timeout)
    except Exception:
      time.sleep(0.1)
      continue
    last_payload = payload
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    source = str(event.get("source", ""))
    if status < 400 and source.startswith(source_prefix) and event.get("controlOutput") is False:
      return True, payload
    time.sleep(0.1)
  return False, last_payload


def run_live_check(args: argparse.Namespace) -> dict[str, Any]:
  checks: list[dict[str, Any]] = []
  params = args.param or DEFAULT_PARAM_NAMES

  health_payload, health_check = query_json_check(args.host, args.web_port, "/api/health", args.timeout, args.allow_unavailable, "7000 health")
  if health_payload:
    ok, detail, evidence = validate_health(health_payload)
    health_check = check("7000 health", "pass" if ok else "fail", detail, evidence)
  checks.append(health_check)

  joined = ",".join(params)
  params_payload, params_check = query_json_check(
    args.host, args.web_port, f"/api/params_bulk?names={joined}", args.timeout, args.allow_unavailable, "7000 params bulk",
  )
  if params_payload:
    ok, detail, evidence = validate_params(params_payload, params)
    params_check = check("7000 params bulk", "pass" if ok else "fail", detail, evidence)
  checks.append(params_check)

  if args.write_same_value:
    if not params_payload or not isinstance(params_payload.get("values"), dict):
      checks.append(check("7000 same-value param write", "fail", "params were not readable"))
    else:
      values = params_payload["values"]
      name = args.write_param
      if name not in WRITABLE_SAME_VALUE_PARAM_NAMES:
        checks.append(check("7000 same-value param write", "fail", "write param is not in the safe same-value allowlist", {"name": name}))
      else:
        try:
          status, payload = http_json(args.host, args.web_port, "POST", "/api/param_set", {"name": name, "value": values.get(name)}, args.timeout)
          ok = status < 400 and boolish(payload.get("ok", False)) and payload.get("changed") is False
          checks.append(check("7000 same-value param write", "pass" if ok else "fail", "" if ok else f"HTTP {status}", payload))
        except Exception as exc:
          checks.append(unavailable_check("7000 same-value param write", exc, args.allow_unavailable))
  else:
    checks.append(check("7000 same-value param write", "skip", "use --write-same-value to test without changing the value"))

  status_payload, status_check = query_json_check(args.host, args.web_port, "/api/status_broadcast", args.timeout, args.allow_unavailable, "7000 status broadcast snapshot")
  if status_payload:
    payload = status_payload.get("payload") if isinstance(status_payload.get("payload"), dict) else {}
    ok, detail, evidence = validate_status_payload(payload)
    evidence["lastTargets"] = status_payload.get("lastTargets", [])
    evidence["activeTargets"] = status_payload.get("activeTargets", [])
    status_check = check("7000 status broadcast snapshot", "pass" if ok else "fail", detail, evidence)
  checks.append(status_check)

  if args.listen_seconds > 0:
    payload, error = listen_udp_status(args.status_port, args.listen_seconds)
    if payload is None:
      checks.append(check("7705 UDP status broadcast", "warn" if args.allow_unavailable else "fail", error))
    else:
      ok, detail, evidence = validate_status_payload(payload)
      checks.append(check("7705 UDP status broadcast", "pass" if ok else "fail", detail, evidence))
  else:
    checks.append(check("7705 UDP status broadcast", "skip", "disabled by --listen-seconds=0"))

  navi_http_payload, navi_http_check = query_json_check(args.host, args.navi_http_port, "/health", args.timeout, args.allow_unavailable, "7713 navigation HTTP health")
  if navi_http_payload:
    ok = navi_http_payload.get("controlOutput") is False and int(navi_http_payload.get("port", 0)) == DEFAULT_NAVI_HTTP_PORT
    navi_http_check = check("7713 navigation HTTP health", "pass" if ok else "fail", "" if ok else "unexpected 7713 health payload", navi_http_payload)
  checks.append(navi_http_check)

  navi_tcp_payload, navi_tcp_check = query_json_check(args.host, args.web_port, "/api/navi/tcp_health", args.timeout, args.allow_unavailable, "7712 navigation TCP health")
  if navi_tcp_payload:
    ok = navi_tcp_payload.get("controlOutput") is False and int(navi_tcp_payload.get("port", 0)) == DEFAULT_NAVI_TCP_PORT
    navi_tcp_check = check("7712 navigation TCP health", "pass" if ok else "fail", "" if ok else "unexpected 7712 health payload", navi_tcp_payload)
  checks.append(navi_tcp_check)

  navigation_payload, navigation_check = query_json_check(args.host, args.web_port, "/api/navigation_event", args.timeout, args.allow_unavailable, "7000 navigation event snapshot")
  if navigation_payload:
    event = navigation_payload.get("event") if isinstance(navigation_payload.get("event"), dict) else {}
    ok = navigation_payload.get("hasParams") is True and (not event or event.get("controlOutput") is False)
    navigation_check = check("7000 navigation event snapshot", "pass" if ok else "fail", "" if ok else "unexpected navigation event state", {
      "hasParams": navigation_payload.get("hasParams"),
      "source": event.get("source"),
      "controlOutput": event.get("controlOutput"),
    })
  checks.append(navigation_check)

  if args.send_navigation_probe:
    ok, error = send_udp_navigation(args.host, args.nav_port)
    if not ok:
      checks.append(check("7706 safe navigation probe", "warn" if args.allow_unavailable else "fail", error))
    else:
      seen, payload = poll_navigation_source(args.host, args.web_port, args.timeout, "udp-7706")
      checks.append(check("7706 safe navigation probe", "pass" if seen else "fail", "" if seen else "navigation event did not update from udp-7706", payload))

    try:
      status, payload = http_json(args.host, args.navi_http_port, "POST", "/api/navi", {"rgdata": safe_navigation_payload()}, args.timeout)
      ok = status < 400 and boolish(payload.get("ok", False)) and payload.get("controlOutput") is False
      checks.append(check("7713 safe navigation probe", "pass" if ok else "fail", "" if ok else f"HTTP {status}", payload))
    except Exception as exc:
      checks.append(unavailable_check("7713 safe navigation probe", exc, args.allow_unavailable))

    ok, error = send_tcp_navigation(args.host, args.navi_tcp_port, args.timeout)
    if not ok:
      checks.append(check("7712 safe navigation probe", "warn" if args.allow_unavailable else "fail", error))
    else:
      time.sleep(0.2)
      tcp_payload, _tcp_check = query_json_check(args.host, args.web_port, "/api/navi/tcp_health", args.timeout, args.allow_unavailable, "7712 safe navigation probe")
      last_event = tcp_payload.get("lastEvent") if isinstance(tcp_payload, dict) and isinstance(tcp_payload.get("lastEvent"), dict) else {}
      ok = bool(last_event) and last_event.get("controlOutput") is False and str(last_event.get("source", "")).startswith("tcp-7712")
      checks.append(check("7712 safe navigation probe", "pass" if ok else "fail", "" if ok else "tcp health did not record the safe rgdata event", tcp_payload or {}))
  else:
    checks.append(check("7706/7712/7713 safe navigation probe", "skip", "use --send-navigation-probe while parked to inject a safe evidence-only packet"))

  failed = [item for item in checks if item["status"] == "fail"]
  return {
    "version": 1,
    "generatedAt": now_text(),
    "host": args.host,
    "ports": {
      "web": args.web_port,
      "status": args.status_port,
      "navigationUdp": args.nav_port,
      "navigationTcp": args.navi_tcp_port,
      "navigationHttp": args.navi_http_port,
    },
    "allowUnavailable": bool(args.allow_unavailable),
    "sendNavigationProbe": bool(args.send_navigation_probe),
    "writeSameValue": bool(args.write_same_value),
    "checks": checks,
    "overallOk": not failed,
    "safetyBoundary": {
      "localOnly": True,
      "cloudServices": False,
      "controlOutput": False,
      "safeProbeCommandFieldsEmpty": True,
    },
  }


def markdown_report(result: dict[str, Any]) -> str:
  lines = [
    "# Navipilot / CPdazi Alpha Live Check",
    "",
    "This checks the local C3 endpoints used by the Android app. It does not replace a real phone connection test.",
    "",
    "| Check | Result | Detail |",
    "| --- | --- | --- |",
  ]
  for item in result["checks"]:
    lines.append(f"| {item['name']} | {item['status'].upper()} | {compact(item.get('detail') or item.get('evidence') or '')} |")
  lines.extend([
    "",
    "## Summary",
    "",
    f"- Overall: {'PASS' if result.get('overallOk') else 'FAIL'}",
    f"- Host: `{result.get('host')}`",
    f"- Ports: `{compact(result.get('ports'))}`",
    f"- Safe navigation probe: `{result.get('sendNavigationProbe')}`",
    f"- Same-value param write: `{result.get('writeSameValue')}`",
    "",
    "## Boundary",
    "",
    "- Local/LAN endpoints only.",
    "- Cloud connection, uploads, remote pairing, and backups are not checked or used.",
    "- Control output must remain false.",
    "- The optional navigation probe leaves command fields empty and records evidence only.",
    "",
  ])
  return "\n".join(lines)


class _SelfTestWebHandler(BaseHTTPRequestHandler):
  values = {
    "ExperimentalMode": 0,
    "ExperimentalModeConfirmed": 0,
    "SpeedFromPCM": 1,
    "OffroadMode": 0,
    "CarrotMapOverlayEnabled": 0,
    "CarrotPhoneSpeedLimitEnabled": 1,
    "CarrotTrafficStopEnabled": 0,
    "CarrotAutoTurnControlEnabled": 0,
    "CarrotLearningActive": 0,
    "CarrotLearningAutoApply": 0,
    "FishopAutoOvertakeEnabled": 0,
  }
  navi_http_port = DEFAULT_NAVI_HTTP_PORT
  navi_tcp_port = DEFAULT_NAVI_TCP_PORT

  def log_message(self, _fmt: str, *_args: Any) -> None:
    return

  def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

  def do_GET(self) -> None:
    path, _, query = self.path.partition("?")
    if path == "/api/health":
      self.send_json({
        "ok": True,
        "service": "carrot_server",
        "mode": "local",
        "cloudServices": False,
        "controlOutput": False,
        "statusBroadcastPort": DEFAULT_STATUS_PORT,
        "navigationUdpPort": DEFAULT_NAV_PORT,
        "naviHttpPort": DEFAULT_NAVI_HTTP_PORT,
        "naviTcpPort": DEFAULT_NAVI_TCP_PORT,
        "endpoints": sorted(REQUIRED_HEALTH_ENDPOINTS),
      })
      return
    if path == "/api/params_bulk":
      names = []
      if query.startswith("names="):
        names = [name for name in query.removeprefix("names=").split(",") if name]
      writable = {name: name in WRITABLE_SAME_VALUE_PARAM_NAMES for name in names}
      self.send_json({
        "ok": True,
        "hasParams": True,
        "has_params": True,
        "source": "local_safe_whitelist",
        "values": {name: self.values.get(name, 0) for name in names},
        "writable": writable,
        "readOnly": {name: not writable[name] for name in names},
        "types": {name: "bool" for name in names},
        "unknown": [],
      })
      return
    if path == "/api/status_broadcast":
      self.send_json({
        "ok": True,
        "lastTargets": ["255.255.255.255:7705"],
        "activeTargets": ["255.255.255.255:7705"],
        "payload": selftest_status_payload(),
      })
      return
    if path == "/api/navigation_event":
      self.send_json({"ok": True, "hasParams": True, "event": {"source": "self-test", "controlOutput": False}})
      return
    if path == "/api/navi/tcp_health":
      self.send_json({"ok": True, "service": "carrot_navi_tcp", "port": DEFAULT_NAVI_TCP_PORT, "available": True, "controlOutput": False})
      return
    self.send_json({"ok": False, "error": "not found"}, 404)

  def do_POST(self) -> None:
    if self.path != "/api/param_set":
      self.send_json({"ok": False, "error": "not found"}, 404)
      return
    length = int(self.headers.get("Content-Length", "0"))
    body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
    self.send_json({"ok": True, "name": body.get("name"), "value": body.get("value"), "changed": False, "hasParams": True, "has_params": True, "writable": True})


class _SelfTestNaviHttpHandler(BaseHTTPRequestHandler):
  def log_message(self, _fmt: str, *_args: Any) -> None:
    return

  def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

  def do_GET(self) -> None:
    if self.path == "/health":
      self.send_json({"ok": True, "service": "carrot_navi_http", "port": DEFAULT_NAVI_HTTP_PORT, "available": True, "controlOutput": False})
      return
    self.send_json({"ok": False, "error": "not found"}, 404)


def selftest_status_payload() -> dict[str, Any]:
  payload = {key: 0 for key in REQUIRED_STATUS_KEYS}
  payload.update({
    "Carrot2": "GeniusPilot-alpha",
    "IsOnroad": False,
    "CarrotRouteActive": False,
    "ip": DEFAULT_HOST,
    "port": DEFAULT_NAV_PORT,
    "navi_http_port": DEFAULT_NAVI_HTTP_PORT,
    "navi_tcp_port": DEFAULT_NAVI_TCP_PORT,
    "log_carrot": "",
    "active": False,
    "v_ego_kph": 0.0,
    "v_cruise_kph": 0.0,
    "carcruiseSpeed": 0.0,
    "tbt_dist": 0,
    "sdi_dist": 0,
    "sdi_type": 0,
    "speedBumpDist": 0,
    "modelSpeedKph": 0,
    "carrotControlPreview": {"controlOutput": False},
    "navigationHazards": {"controlOutput": False},
    "xState": 0,
    "trafficState": 0,
    "controlOutput": False,
    "carrotManCompatible": True,
    "naviHttpAvailable": True,
    "naviTcpAvailable": True,
  })
  return payload


def start_server(handler: type[BaseHTTPRequestHandler]) -> tuple[HTTPServer, int]:
  server = HTTPServer(("127.0.0.1", 0), handler)
  port = int(server.server_address[1])
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  return server, port


def send_selftest_udp_status(port: int) -> None:
  data = json.dumps(selftest_status_payload(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
  deadline = time.monotonic() + 1.5
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    while time.monotonic() < deadline:
      sock.sendto(data, ("127.0.0.1", port))
      time.sleep(0.05)
  finally:
    sock.close()


def self_test() -> None:
  web_server, web_port = start_server(_SelfTestWebHandler)
  navi_server, navi_http_port = start_server(_SelfTestNaviHttpHandler)
  status_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  status_probe.bind(("127.0.0.1", 0))
  status_port = int(status_probe.getsockname()[1])
  status_probe.close()
  sender = threading.Thread(target=send_selftest_udp_status, args=(status_port,), daemon=True)
  sender.start()
  args = argparse.Namespace(
    host="127.0.0.1",
    web_port=web_port,
    status_port=status_port,
    nav_port=DEFAULT_NAV_PORT,
    navi_tcp_port=DEFAULT_NAVI_TCP_PORT,
    navi_http_port=navi_http_port,
    timeout=2.0,
    allow_unavailable=False,
    listen_seconds=1.0,
    send_navigation_probe=False,
    write_same_value=True,
    write_param="ExperimentalMode",
    param=None,
  )
  try:
    result = run_live_check(args)
  finally:
    web_server.shutdown()
    web_server.server_close()
    navi_server.shutdown()
    navi_server.server_close()
  if not result.get("overallOk"):
    raise LiveCheckError(json.dumps(result, ensure_ascii=False, sort_keys=True))
  report = markdown_report(result)
  for token in ("7000 health", "7705 UDP status broadcast", "7713 navigation HTTP health"):
    if token not in report:
      raise LiveCheckError(f"missing self-test report token: {token}")


def write_optional_outputs(result: dict[str, Any], output: str | None, json_output: str | None) -> None:
  if output:
    with open(output, "w", encoding="utf-8") as f:
      f.write(markdown_report(result))
      f.write("\n")
  if json_output:
    with open(json_output, "w", encoding="utf-8") as f:
      json.dump(result, f, indent=2, ensure_ascii=False, sort_keys=True)
      f.write("\n")


def main() -> int:
  parser = argparse.ArgumentParser(description="Check alpha C3 Navipilot / CPdazi local endpoints.")
  parser.add_argument("--host", default=DEFAULT_HOST, help="C3 host or IP")
  parser.add_argument("--web-port", type=int, default=DEFAULT_WEB_PORT, help="Carrot Web port")
  parser.add_argument("--status-port", type=int, default=DEFAULT_STATUS_PORT, help="UDP status broadcast port")
  parser.add_argument("--nav-port", type=int, default=DEFAULT_NAV_PORT, help="UDP navigation input port")
  parser.add_argument("--navi-tcp-port", type=int, default=DEFAULT_NAVI_TCP_PORT, help="TCP navigation input port")
  parser.add_argument("--navi-http-port", type=int, default=DEFAULT_NAVI_HTTP_PORT, help="HTTP navigation compatibility port")
  parser.add_argument("--timeout", type=float, default=3.0, help="HTTP/socket timeout seconds")
  parser.add_argument("--allow-unavailable", action="store_true", help="return success when local endpoints are unavailable on a development machine")
  parser.add_argument("--listen-seconds", type=float, default=3.0, help="listen for UDP 7705 status broadcast; 0 disables")
  parser.add_argument("--send-navigation-probe", action="store_true", help="while parked, send one safe evidence-only navigation packet to 7706/7712/7713")
  parser.add_argument("--write-same-value", action="store_true", help="write a safe param back to its current value to test /api/param_set")
  parser.add_argument("--write-param", default="ExperimentalMode", help="safe writable param for --write-same-value")
  parser.add_argument("--param", action="append", help="extra or replacement param names to read; may be repeated")
  parser.add_argument("--json", action="store_true", help="print JSON instead of markdown")
  parser.add_argument("--output", help="write markdown report to a path")
  parser.add_argument("--json-output", help="write JSON report to a path")
  parser.add_argument("--self-test", action="store_true", help="run local parser self-test")
  args = parser.parse_args()

  try:
    if args.self_test:
      self_test()
      print("OK: Navipilot / CPdazi alpha live check self-test passed")
      return 0

    result = run_live_check(args)
    write_optional_outputs(result, args.output, args.json_output)
    if args.json:
      print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    elif not args.output:
      print(markdown_report(result))
    return 0 if result.get("overallOk") else 2
  except Exception as exc:
    print(f"Navipilot / CPdazi alpha live check failed: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
