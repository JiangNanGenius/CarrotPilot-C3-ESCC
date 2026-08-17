from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout, FormData

from .params import HAS_PARAMS, Params
from .vision_test import LOG_PATH as VISION_TEST_LOG_PATH
from .vision_test import get_status as get_vision_test_status

try:
  from openpilot.system.hardware import HARDWARE
except Exception:
  HARDWARE = None


STREAM_PROXY_HISTORY_LIMIT = 120
TEXT_LINE_LIMIT = 800
JOURNAL_LINE_LIMIT = 240
PROC_NET_LINE_LIMIT = 320
VISION_TEST_LOG_LINE_LIMIT = 240
DISCORD_FILE_MAX_BYTES = 8 * 1024 * 1024

_STREAM_PROXY_HISTORY: deque[dict[str, Any]] = deque(maxlen=STREAM_PROXY_HISTORY_LIMIT)
_STREAM_PROXY_HISTORY_LOCK = threading.Lock()
_PROCESS_MATCHES = {
  "camerad": "system/camerad/camerad",
  "stream_encoderd": "system/loggerd/encoderd\x00--stream",
  "encoderd": "system/loggerd/encoderd",
  "webrtcd": "system.webrtc.webrtcd",
  "carrot_web": "selfdrive.carrot.server",
}
_JOURNAL_TERMS = (
  "camerad",
  "camera",
  "encoderd",
  "loggerd",
  "webrtcd",
  "visionipc",
  "v4l_encoder",
  "spectra.cc",
  "h264",
  "multi-slice",
  "checked_ioctl",
  "carrot",
)


def _trim_text(value: Any, limit: int = TEXT_LINE_LIMIT) -> str:
  text = str(value or "").replace("\x00", " ")
  return text if len(text) <= limit else f"{text[:limit]}..."


def _decode_obfuscated(value: str, key: str) -> str:
  try:
    token = str(value or "").strip()
    key_bytes = str(key or "").encode("utf-8")
    if not token or not key_bytes:
      return ""
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    decoded = bytes(raw[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(raw)))
    return decoded.decode("utf-8", errors="ignore").strip()
  except Exception:
    return ""


def _param_text(params: Any, key: str, default: str = "") -> str:
  try:
    if not params:
      return default
    value = params.get(key)
    if isinstance(value, bytes):
      value = value.decode("utf-8", errors="replace")
    value = str(value or "").strip()
    return value or default
  except Exception:
    return default


def _repo_dir() -> str:
  return os.environ.get("CARROT_REPO_DIR", "/data/openpilot")


def _git_text(args: list[str], default: str = "unknown") -> str:
  try:
    result = subprocess.run(
      ["git", *args],
      cwd=_repo_dir(),
      capture_output=True,
      text=True,
      timeout=4,
    )
    if result.returncode == 0:
      value = (result.stdout or "").strip()
      return value or default
  except Exception:
    pass
  return default


def _device_serial(params: Any) -> str:
  for key in ("HardwareSerial", "DeviceSerial", "Serial", "CarrotSerial"):
    value = _param_text(params, key, "")
    if value:
      return value
  for key in ("CARROT_DEVICE_SERIAL", "DEVICE_SERIAL", "SERIAL"):
    value = os.environ.get(key, "").strip()
    if value:
      return value
  try:
    getter = getattr(HARDWARE, "get_serial", None) if HARDWARE is not None else None
    if callable(getter):
      value = str(getter() or "").strip()
      if value:
        return value
  except Exception:
    pass
  return "unknown"


def _diagnostic_metadata(params: Any | None = None) -> dict[str, str]:
  return {
    "carName": _param_text(params, "CarName", "none"),
    "dongleId": _param_text(params, "DongleId", "unknown"),
    "serial": _device_serial(params),
    "branch": _git_text(["branch", "--show-current"]),
    "commit": _git_text(["rev-parse", "--short", "HEAD"]),
    "commitDate": _git_text(["show", "-s", "--date=format:%Y-%m-%d %H:%M:%S", "--format=%cd", "HEAD"]),
  }


def record_stream_proxy_event(event: dict[str, Any]) -> None:
  entry = {
    "ts": time.time(),
    **event,
  }
  with _STREAM_PROXY_HISTORY_LOCK:
    _STREAM_PROXY_HISTORY.append(entry)


def get_stream_proxy_history() -> list[dict[str, Any]]:
  with _STREAM_PROXY_HISTORY_LOCK:
    return list(_STREAM_PROXY_HISTORY)


def _read_text(path: Path, limit: int = 256_000) -> str:
  try:
    return path.read_text(encoding="utf-8", errors="replace")[:limit]
  except Exception:
    return ""


def _tail_file(path: Path, lines: int) -> list[str]:
  text = _read_text(path)
  return [_trim_text(line) for line in text.splitlines()[-lines:]]


def _run(args: list[str], timeout: float = 3.0) -> dict[str, Any]:
  try:
    proc = subprocess.run(
      args,
      check=False,
      capture_output=True,
      encoding="utf-8",
      errors="replace",
      timeout=timeout,
    )
    return {
      "argv": args,
      "returncode": proc.returncode,
      "stdout": _trim_text(proc.stdout, 96_000),
      "stderr": _trim_text(proc.stderr, 24_000),
    }
  except Exception as exc:
    return {
      "argv": args,
      "error": _trim_text(exc),
    }


def _pid_cmdline(pid: int) -> str:
  try:
    return Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
  except Exception:
    return ""


def _find_processes() -> dict[str, list[dict[str, Any]]]:
  result: dict[str, list[dict[str, Any]]] = {name: [] for name in _PROCESS_MATCHES}
  proc_root = Path("/proc")
  if not proc_root.exists():
    return result

  for proc_path in proc_root.glob("[0-9]*"):
    try:
      pid = int(proc_path.name)
    except ValueError:
      continue
    raw_cmdline = _pid_cmdline(pid)
    if not raw_cmdline:
      continue
    for name, match in _PROCESS_MATCHES.items():
      if match in raw_cmdline:
        result[name].append(_process_snapshot(pid, raw_cmdline))
  return result


def _process_snapshot(pid: int, raw_cmdline: str) -> dict[str, Any]:
  status: dict[str, str] = {}
  for line in _read_text(Path(f"/proc/{pid}/status"), limit=32_000).splitlines():
    if ":" not in line:
      continue
    key, value = line.split(":", 1)
    if key in {"Name", "State", "Pid", "PPid", "Tgid", "Threads", "VmRSS", "VmSize"}:
      status[key] = value.strip()

  stat = _read_text(Path(f"/proc/{pid}/stat"), limit=8_000).split()
  fd_count = None
  try:
    fd_count = sum(1 for _ in Path(f"/proc/{pid}/fd").iterdir())
  except Exception:
    pass
  return {
    "pid": pid,
    "cmdline": _trim_text(raw_cmdline.replace("\x00", " ").strip()),
    "status": status,
    "cpu_user_ticks": stat[13] if len(stat) > 14 else None,
    "cpu_system_ticks": stat[14] if len(stat) > 15 else None,
    "fd_count": fd_count,
  }


def _params_snapshot() -> dict[str, Any]:
  if not HAS_PARAMS:
    return {"available": False}
  params = Params()
  result: dict[str, Any] = {"available": True}
  for name in ("IsOffroad", "IsTakingSnapshot", "CarParamsPersistent"):
    try:
      if name == "CarParamsPersistent":
        raw = params.get(name)
        result[name] = {"present": bool(raw), "bytes": len(raw or b"")}
      else:
        result[name] = params.get_bool(name)
    except Exception as exc:
      result[name] = {"error": _trim_text(exc)}
  return result


def _vipc_snapshot() -> dict[str, Any]:
  try:
    from msgq.visionipc import VisionIpcClient
    streams = sorted(int(stream) for stream in VisionIpcClient.available_streams("camerad", block=False))
    return {"available": True, "camerad_streams": streams}
  except Exception as exc:
    return {"available": False, "error": _trim_text(exc)}


def _port_open(port: int) -> bool:
  try:
    with socket.create_connection(("127.0.0.1", port), timeout=0.25):
      return True
  except OSError:
    return False


def _proc_net_snapshot() -> dict[str, list[str]]:
  result: dict[str, list[str]] = {}
  for name in ("tcp", "tcp6", "udp", "udp6"):
    lines = _read_text(Path(f"/proc/net/{name}"), limit=256_000).splitlines()
    result[name] = [_trim_text(line) for line in lines[:PROC_NET_LINE_LIMIT]]
  return result


def _journal_snapshot() -> dict[str, Any]:
  raw = _run(["journalctl", "-b", "--no-pager", "-n", "900", "-o", "short-iso"], timeout=4.0)
  lines = str(raw.get("stdout") or "").splitlines()
  filtered = [
    _trim_text(line)
    for line in lines
    if any(term in line.lower() for term in _JOURNAL_TERMS)
  ]
  return {
    "command": raw.get("argv"),
    "returncode": raw.get("returncode"),
    "error": raw.get("error", ""),
    "lines": filtered[-JOURNAL_LINE_LIMIT:],
  }


def _upload_filename(filename: str | None = None) -> str:
  name = str(filename or "").strip().replace("\\", "_").replace("/", "_")
  if name and name.endswith(".txt"):
    return name[:180]
  stamp = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
  return f"carrot_vision_diag_{stamp}.txt"


def _limit_upload_text(text: str) -> str:
  raw = text.encode("utf-8", errors="replace")
  if len(raw) <= DISCORD_FILE_MAX_BYTES:
    return text
  keep_each = max(256_000, (DISCORD_FILE_MAX_BYTES // 2) - 128_000)
  head = raw[:keep_each].decode("utf-8", errors="replace")
  tail = raw[-keep_each:].decode("utf-8", errors="replace")
  return "\n".join([
    head,
    "",
    f"# ===== DISCORD UPLOAD TRUNCATED original_bytes={len(raw)} limit={DISCORD_FILE_MAX_BYTES} =====",
    "",
    tail,
  ])


def _console_upload_filename(filename: str | None, diag_filename: str) -> str:
  name = str(filename or "").strip().replace("\\", "_").replace("/", "_")
  if name and name.endswith(".txt"):
    return name[:180]
  if diag_filename.endswith(".txt"):
    return f"{diag_filename[:-4]}_console.txt"
  return f"{diag_filename}_console.txt"


def _socket_snapshot(processes: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
  relevant_pids = {
    str(proc["pid"])
    for entries in processes.values()
    for proc in entries
    if proc.get("pid")
  }
  raw = _run(["ss", "-tunap"], timeout=3.0)
  lines = str(raw.get("stdout") or "").splitlines()
  filtered = [
    _trim_text(line)
    for line in lines
    if ":5001" in line or any(f"pid={pid}," in line for pid in relevant_pids)
  ]
  return {
    "command": raw.get("argv"),
    "returncode": raw.get("returncode"),
    "error": raw.get("error", ""),
    "lines": filtered[-PROC_NET_LINE_LIMIT:],
  }


def get_server_diagnostic_snapshot() -> dict[str, Any]:
  processes = _find_processes()
  try:
    vision_test_status: dict[str, Any] = get_vision_test_status()
  except Exception as exc:
    vision_test_status = {"error": _trim_text(exc)}

  return {
    "captured_at": time.time(),
    "captured_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "system": {
      "hostname": platform.node(),
      "platform": platform.platform(),
      "python": platform.python_version(),
      "uptime_seconds": _trim_text(_read_text(Path("/proc/uptime"), limit=128)),
      "loadavg": _trim_text(_read_text(Path("/proc/loadavg"), limit=128)),
    },
    "params": _params_snapshot(),
    "vipc": _vipc_snapshot(),
    "ports": {
      "webrtcd_5001_open": _port_open(5001),
    },
    "processes": processes,
    "stream_proxy_history": get_stream_proxy_history(),
    "vision_test": {
      "status": vision_test_status,
      "log_path": str(VISION_TEST_LOG_PATH),
      "log_tail": _tail_file(VISION_TEST_LOG_PATH, VISION_TEST_LOG_LINE_LIMIT),
    },
    "sockets": _socket_snapshot(processes),
    "proc_net": _proc_net_snapshot(),
    "journal_tail": _journal_snapshot(),
  }
