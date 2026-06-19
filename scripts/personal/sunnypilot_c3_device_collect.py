#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "192.168.100.174"
DEFAULT_USER = "comma"
DEFAULT_REMOTE_ROOT = "/tmp/carrot_c3_collect"
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "CarrotPilot-C3-ESCC-device-evidence"

SAFE_PARAM_KEYS = (
  "OffroadMode",
  "SunnylinkEnabled",
  "EnableSunnylinkUploader",
  "OnroadUploads",
  "CarrotMapOverlayEnabled",
  "CarrotPhoneSpeedLimitEnabled",
  "CarrotPhoneSpeedLimit",
  "CarrotPhoneSpeedLimitSource",
  "CarrotPhoneSpeedLimitUpdatedAt",
  "CarrotActiveSpeedControlEnabled",
  "CarrotAutoTurnControlEnabled",
  "CarrotTrafficStopEnabled",
  "CarrotLearningActive",
  "CarrotLearningAutoApply",
  "SpeedLimitPolicy",
  "SpeedLimitMode",
  "SpeedLimitOffsetType",
  "SpeedLimitValueOffset",
  "ModelRunnerTypeCache",
  "ModelManager_ActiveBundle",
  "FishopAutoOvertakeEnabled",
  "FishopLaneCurveEnabled",
  "FishopLidarBlindspotEnabled",
  "FishopLidarLaneDataEnabled",
)

CLOUD_PROCESS_NAMES = (
  "athenad",
  "uploader",
  "sunnylinkd",
  "sunnylink_registration_manager",
  "statsd_sp",
  "backup_manager",
)

LOG_PATHS = (
  "/tmp/launch_log",
  "/tmp/installer.log",
  "/tmp/setup.log",
  "/tmp/manager.log",
  "/data/openpilot/launch_log",
  "/data/openpilot/installer.log",
  "/data/params/d/LastUpdateTime",
)


def run(cmd: Sequence[str], timeout_s: int) -> tuple[int, str]:
  env = os.environ.copy()
  env.setdefault("GIT_TERMINAL_PROMPT", "0")
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=ROOT,
      env=env,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      check=False,
      timeout=timeout_s,
    )
    return proc.returncode, proc.stdout.strip()
  except subprocess.TimeoutExpired as exc:
    output = ((exc.stdout or "") + (exc.stderr or "")).strip()
    return 124, f"{cmd[0]} timed out after {timeout_s}s\n{output}".strip()
  except OSError as exc:
    return 127, str(exc)


def ssh_base(args: argparse.Namespace) -> list[str]:
  cmd = [
    "ssh",
    "-p",
    str(args.port),
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    f"ConnectTimeout={args.connect_timeout}",
  ]
  if args.identity:
    cmd.extend(["-i", str(args.identity)])
  for option in args.ssh_option:
    cmd.extend(["-o", option])
  cmd.append(f"{args.user}@{args.host}")
  return cmd


def scp_base(args: argparse.Namespace) -> list[str]:
  cmd = [
    "scp",
    "-P",
    str(args.port),
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    f"ConnectTimeout={args.connect_timeout}",
  ]
  if args.identity:
    cmd.extend(["-i", str(args.identity)])
  for option in args.ssh_option:
    cmd.extend(["-o", option])
  return cmd


def q(value: str) -> str:
  return shlex.quote(value)


def remote_collect_script(args: argparse.Namespace) -> str:
  safe_params = " ".join(q(key) for key in SAFE_PARAM_KEYS)
  cloud_names = " ".join(q(name) for name in CLOUD_PROCESS_NAMES)
  log_paths = " ".join(q(path) for path in LOG_PATHS)
  sample_seconds = max(0, int(args.sample_seconds))
  hardware_probe_seconds = max(1, int(args.hardware_probe_seconds))
  imu_probe_seconds = max(1, int(args.imu_probe_seconds))
  camera_snapshot_timeout = max(1, int(args.camera_snapshot_timeout))
  navipilot_flag = "--navipilot-live-check" if args.navipilot_live_check else ""
  require_cloud_flag = "--require-no-cloud-processes" if args.require_no_cloud_processes else ""
  sound_probe_flag = "--skip-sound" if args.skip_sound_probe else ""
  snapshot_block = "true"
  if not args.skip_snapshot:
    snapshot_block = f"""
if [ -d /data/openpilot ]; then
  cd /data/openpilot
  OPENPILOT_PYTHON="/usr/local/venv/bin/python"
  if [ ! -x "$OPENPILOT_PYTHON" ]; then
    OPENPILOT_PYTHON="$(command -v python3 || command -v python)"
  fi
  {{
    git rev-parse HEAD || true
    git branch --show-current || true
    git remote -v | sed -E 's#(https://)[^/@]+@#\\1<redacted>@#g' || true
  }} > "$OUT/openpilot_git.txt" 2>&1
  echo "$OPENPILOT_PYTHON" > "$OUT/python_runtime.txt"
  if [ -f scripts/personal/sunnypilot_c3_alpha_snapshot.py ]; then
    PYTHONPATH=/data/openpilot "$OPENPILOT_PYTHON" scripts/personal/sunnypilot_c3_alpha_snapshot.py \\
      --sample-seconds {sample_seconds} \\
      {navipilot_flag} \\
      {require_cloud_flag} \\
      --output "$OUT/carrot_alpha_snapshot.json" \\
      --pretty > "$OUT/snapshot_stdout.txt" 2> "$OUT/snapshot_stderr.txt" || echo "$?" > "$OUT/snapshot_exit_code.txt"
    if [ -f "$OUT/carrot_alpha_snapshot.json" ] && [ -f scripts/personal/sunnypilot_c3_alpha_evidence_check.py ]; then
      PYTHONPATH=/data/openpilot "$OPENPILOT_PYTHON" scripts/personal/sunnypilot_c3_alpha_evidence_check.py "$OUT/carrot_alpha_snapshot.json" \\
        --phase static --phase parked --phase model > "$OUT/evidence_check_static_parked_model.txt" 2>&1 || echo "$?" > "$OUT/evidence_check_exit_code.txt"
    fi
  else
    echo "snapshot script missing; install may not have completed" > "$OUT/snapshot_missing.txt"
  fi
else
  echo "/data/openpilot missing; install likely did not complete" > "$OUT/openpilot_missing.txt"
fi
"""
  hardware_probe_block = "true"
  if args.parked_hardware_probe:
    hardware_probe_block = f"""
if [ -d /data/openpilot ]; then
  cd /data/openpilot
  OPENPILOT_PYTHON="/usr/local/venv/bin/python"
  if [ ! -x "$OPENPILOT_PYTHON" ]; then
    OPENPILOT_PYTHON="$(command -v python3 || command -v python)"
  fi
  echo "$OPENPILOT_PYTHON" > "$OUT/python_runtime.txt"
  if [ -f scripts/personal/sunnypilot_c3_parked_hardware_probe.py ]; then
    PYTHONPATH=/data/openpilot "$OPENPILOT_PYTHON" scripts/personal/sunnypilot_c3_parked_hardware_probe.py \\
      --sample-seconds {hardware_probe_seconds} \\
      --sound-seconds 1.2 \\
      {sound_probe_flag} \\
      --output "$OUT/parked_hardware_probe.json" \\
      --pretty > "$OUT/parked_hardware_probe_stdout.txt" 2> "$OUT/parked_hardware_probe_stderr.txt" || echo "$?" > "$OUT/parked_hardware_probe_exit_code.txt"
  else
    echo "parked hardware probe script missing" > "$OUT/parked_hardware_probe_missing.txt"
  fi
fi
"""
  imu_probe_block = "true"
  if args.imu_probe:
    imu_probe_block = f"""
if [ -d /data/openpilot ]; then
  cd /data/openpilot
  OPENPILOT_PYTHON="/usr/local/venv/bin/python"
  if [ ! -x "$OPENPILOT_PYTHON" ]; then
    OPENPILOT_PYTHON="$(command -v python3 || command -v python)"
  fi
  echo "$OPENPILOT_PYTHON" > "$OUT/python_runtime.txt"
  if [ -f scripts/personal/sunnypilot_c3_imu_probe.py ]; then
    PYTHONPATH=/data/openpilot "$OPENPILOT_PYTHON" scripts/personal/sunnypilot_c3_imu_probe.py \\
      --sample-seconds {imu_probe_seconds} \\
      --output "$OUT/c3_imu_probe.json" \\
      --pretty > "$OUT/c3_imu_probe_stdout.txt" 2> "$OUT/c3_imu_probe_stderr.txt" || echo "$?" > "$OUT/c3_imu_probe_exit_code.txt"
  else
    echo "C3 IMU probe script missing" > "$OUT/c3_imu_probe_missing.txt"
  fi
fi
"""
  camera_snapshot_block = "true"
  if args.camera_snapshot:
    camera_snapshot_block = f"""
if [ -d /data/openpilot ]; then
  cd /data/openpilot
  OPENPILOT_PYTHON="/usr/local/venv/bin/python"
  if [ ! -x "$OPENPILOT_PYTHON" ]; then
    OPENPILOT_PYTHON="$(command -v python3 || command -v python)"
  fi
  echo "$OPENPILOT_PYTHON" > "$OUT/python_runtime.txt"
  mkdir -p "$OUT/camera_snapshot"
  if [ -f scripts/personal/sunnypilot_c3_camera_snapshot_probe.py ]; then
    PYTHONPATH=/data/openpilot "$OPENPILOT_PYTHON" scripts/personal/sunnypilot_c3_camera_snapshot_probe.py \\
      --output-dir "$OUT/camera_snapshot" \\
      --timeout {camera_snapshot_timeout} \\
      --pretty > "$OUT/camera_snapshot_stdout.txt" 2> "$OUT/camera_snapshot_stderr.txt" || echo "$?" > "$OUT/camera_snapshot_exit_code.txt"
    test -f "$OUT/camera_snapshot/camera_snapshot_probe.json" || true
  elif [ -f system/camerad/snapshot.py ]; then
    echo "personal camera snapshot probe missing; upstream snapshot.py is present" > "$OUT/camera_snapshot_missing.txt"
  else
    echo "camera snapshot scripts missing" > "$OUT/camera_snapshot_missing.txt"
  fi
fi
"""
  ui_capture_block = "true"
  if args.ui_capture:
    ui_capture_block = """
mkdir -p "$OUT/ui"
{
  date -u || true
  echo "UI capture is passive: it does not tap the screen and does not play sound."
  if command -v screencap >/dev/null 2>&1; then
    echo "method=screencap"
    screencap -p "$OUT/ui/screencap.png" || true
  elif command -v fbgrab >/dev/null 2>&1; then
    echo "method=fbgrab"
    fbgrab "$OUT/ui/fbgrab.png" || true
  elif [ -r /dev/graphics/fb0 ]; then
    echo "method=/dev/graphics/fb0 raw"
    dd if=/dev/graphics/fb0 of="$OUT/ui/fb0.raw" bs=4096 count=4096 2>"$OUT/ui/fb0_dd.txt" || true
  elif [ -r /dev/fb0 ]; then
    echo "method=/dev/fb0 raw"
    dd if=/dev/fb0 of="$OUT/ui/fb0.raw" bs=4096 count=4096 2>"$OUT/ui/fb0_dd.txt" || true
  else
    echo "method=unavailable"
  fi
  if command -v fbset >/dev/null 2>&1; then
    fbset -i || true
  fi
  ls -l "$OUT/ui" || true
} > "$OUT/ui/ui_capture.txt" 2>&1
"""

  return f"""#!/usr/bin/env bash
set +e
STAMP="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || date +%Y%m%dT%H%M%S)"
REMOTE_ROOT={q(args.remote_root)}
OUT="$REMOTE_ROOT/$STAMP"
mkdir -p "$OUT"/logs "$OUT"/params "$OUT"/proc "$OUT"/network

{{
  echo "timestamp_utc=$STAMP"
  uname -a 2>/dev/null || true
  cat /VERSION 2>/dev/null || true
  cat /etc/os-release 2>/dev/null || true
  cat /sys/firmware/devicetree/base/model 2>/dev/null | tr -d '\\000' || true
  echo
}} > "$OUT/device_info.txt" 2>&1

date -u > "$OUT/date_utc.txt" 2>&1 || true
uptime > "$OUT/uptime.txt" 2>&1 || true
df -h > "$OUT/df_h.txt" 2>&1 || true
mount > "$OUT/mount.txt" 2>&1 || true
ps -A -o pid,ppid,args > "$OUT/proc/ps.txt" 2>&1 || ps aux > "$OUT/proc/ps.txt" 2>&1 || true

for name in {cloud_names}; do
  if grep -E "(^|[ /])$name([ ./$]|$)" "$OUT/proc/ps.txt" >/dev/null 2>&1; then
    echo "$name" >> "$OUT/proc/cloud_processes_seen.txt"
  fi
done
touch "$OUT/proc/cloud_processes_seen.txt"

ip addr > "$OUT/network/ip_addr.txt" 2>&1 || ifconfig -a > "$OUT/network/ifconfig.txt" 2>&1 || true
ss -lntup > "$OUT/network/listeners.txt" 2>&1 || netstat -lntup > "$OUT/network/listeners.txt" 2>&1 || true

for path in {log_paths}; do
  if [ -e "$path" ]; then
    safe="$(echo "$path" | sed 's#^/##; s#[^A-Za-z0-9._-]#_#g')"
    cp -a "$path" "$OUT/logs/$safe" 2>/dev/null || cat "$path" > "$OUT/logs/$safe" 2>/dev/null || true
  fi
done
journalctl -b --no-pager -n 700 > "$OUT/logs/journalctl_boot_tail.txt" 2>&1 || true
dmesg | tail -n 700 > "$OUT/logs/dmesg_tail.txt" 2>&1 || true

for key in {safe_params}; do
  for root in /data/params/d /data/params /persist/comma/params/d; do
    if [ -f "$root/$key" ]; then
      cp "$root/$key" "$OUT/params/$key.txt" 2>/dev/null || cat "$root/$key" > "$OUT/params/$key.txt" 2>/dev/null || true
      break
    fi
  done
done

{snapshot_block}

{hardware_probe_block}

{imu_probe_block}

{camera_snapshot_block}

{ui_capture_block}

tarball="$OUT.tar.gz"
tar -czf "$tarball" -C "$(dirname "$OUT")" "$(basename "$OUT")" 2> "$OUT/tar_stderr.txt"
echo "CARROT_COLLECT_DIR=$OUT"
echo "CARROT_COLLECT_TARBALL=$tarball"
"""


def parse_tarball(output: str) -> str:
  for line in output.splitlines():
    if line.startswith("CARROT_COLLECT_TARBALL="):
      return line.split("=", 1)[1].strip()
  return ""


def collect(args: argparse.Namespace) -> dict[str, object]:
  script = remote_collect_script(args)
  ssh_cmd = [*ssh_base(args), "bash -s"]
  code, output = run_with_input(ssh_cmd, script, args.remote_timeout)
  tarball = parse_tarball(output)
  result: dict[str, object] = {
    "ok": code == 0 and bool(tarball),
    "host": args.host,
    "sshExitCode": code,
    "remoteTarball": tarball,
    "remoteOutput": output[-2000:],
    "localTarball": "",
  }
  if code != 0 or not tarball or args.no_fetch:
    return result

  args.output_dir.mkdir(parents=True, exist_ok=True)
  local_name = f"carrot_c3_collect_{args.host.replace('.', '_')}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
  local_path = args.output_dir / local_name
  scp_cmd = [*scp_base(args), f"{args.user}@{args.host}:{tarball}", str(local_path)]
  scp_code, scp_output = run(scp_cmd, args.remote_timeout)
  result.update({
    "ok": scp_code == 0,
    "scpExitCode": scp_code,
    "scpOutput": scp_output[-1000:],
    "localTarball": str(local_path) if scp_code == 0 else "",
  })
  return result


def run_with_input(cmd: Sequence[str], stdin: str, timeout_s: int) -> tuple[int, str]:
  try:
    proc = subprocess.run(
      list(cmd),
      cwd=ROOT,
      text=True,
      input=stdin,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      check=False,
      timeout=timeout_s,
    )
    return proc.returncode, proc.stdout.strip()
  except subprocess.TimeoutExpired as exc:
    output = ((exc.stdout or "") + (exc.stderr or "")).strip()
    return 124, f"{cmd[0]} timed out after {timeout_s}s\n{output}".strip()
  except OSError as exc:
    return 127, str(exc)


def print_report(report: dict[str, object], as_json: bool) -> None:
  if as_json:
    print(json.dumps(report, indent=2, sort_keys=True))
    return
  print(f"{'PASS' if report.get('ok') else 'FAIL'} CarrotPilot-C3-ESCC C3 Device Collect")
  for key in ("host", "remoteTarball", "localTarball", "sshExitCode", "scpExitCode"):
    if key in report:
      print(f"{key}: {report[key]}")
  if not report.get("ok") and report.get("remoteOutput"):
    print(report["remoteOutput"])


def self_test() -> int:
  class Args:
    remote_root = DEFAULT_REMOTE_ROOT
    sample_seconds = 2
    hardware_probe_seconds = 2
    imu_probe_seconds = 2
    camera_snapshot_timeout = 2
    navipilot_live_check = True
    require_no_cloud_processes = True
    skip_snapshot = False
    parked_hardware_probe = True
    skip_sound_probe = True
    imu_probe = True
    camera_snapshot = True
    ui_capture = True

  script = remote_collect_script(Args())
  required = (
    "sunnypilot_c3_alpha_snapshot.py",
    "sunnypilot_c3_alpha_evidence_check.py",
    "sunnypilot_c3_parked_hardware_probe.py",
    "parked_hardware_probe.json",
    "--skip-sound",
    "sunnypilot_c3_imu_probe.py",
    "c3_imu_probe.json",
    "sunnypilot_c3_camera_snapshot_probe.py",
    "camera_snapshot_probe.json",
    "camera_snapshot_stdout.txt",
    "system/camerad/snapshot.py",
    "UI capture is passive",
    "screencap",
    "fb0.raw",
    "/usr/local/venv/bin/python",
    "PYTHONPATH=/data/openpilot",
    "python_runtime.txt",
    "cloud_processes_seen.txt",
    "CarrotMapOverlayEnabled",
    "ModelManager_ActiveBundle",
    "CARROT_COLLECT_TARBALL=",
    "/data/openpilot missing; install likely did not complete",
  )
  if not all(token in script for token in required):
    return 1
  forbidden_public_key_param = "Github" + "SshKeys"
  if forbidden_public_key_param in script or "PrivateKey" in script:
    return 1
  if not parse_tarball("x\nCARROT_COLLECT_TARBALL=/tmp/a.tar.gz\n"):
    return 1
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description="Collect C3 install, parked, model, and no-cloud evidence over SSH.")
  parser.add_argument("--host", default=DEFAULT_HOST, help="C3 IP address or hostname")
  parser.add_argument("--user", default=DEFAULT_USER, help="SSH user")
  parser.add_argument("--port", type=int, default=22, help="SSH port")
  parser.add_argument("--identity", type=Path, help="SSH private key path")
  parser.add_argument("--ssh-option", action="append", default=[], help="extra ssh -o option")
  parser.add_argument("--connect-timeout", type=int, default=8, help="SSH connect timeout seconds")
  parser.add_argument("--remote-timeout", type=int, default=180, help="remote command/scp timeout seconds")
  parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT, help="remote collection root")
  parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="local directory for fetched evidence bundle")
  parser.add_argument("--sample-seconds", type=int, default=10, help="messaging sample seconds for snapshot")
  parser.add_argument("--parked-hardware-probe", action="store_true", help="run parked camera/modeld probe and include the JSON result")
  parser.add_argument("--hardware-probe-seconds", type=int, default=12, help="seconds to sample camera/modeld during parked hardware probe")
  parser.add_argument("--imu-probe", action="store_true", help="run the silent C3 IMU accelerometer/gyroscope probe")
  parser.add_argument("--imu-probe-seconds", type=int, default=5, help="seconds to sample IMU services")
  parser.add_argument("--camera-snapshot", action="store_true", help="run the upstream camerad snapshot path and collect back/front JPEG evidence")
  parser.add_argument("--camera-snapshot-timeout", type=int, default=25, help="seconds to allow for C3 camera snapshot capture")
  parser.add_argument("--ui-capture", action="store_true", help="passively collect a C3 UI screenshot/framebuffer artifact when available")
  parser.add_argument("--skip-sound-probe", action="store_true", default=True, help="keep parked hardware probe silent; this is the default")
  parser.add_argument("--with-sound-probe", action="store_true", help="explicitly allow the parked hardware probe to play a short speaker test sound")
  parser.add_argument("--navipilot-live-check", action="store_true", help="run evidence-only local Navipilot live check")
  parser.add_argument("--require-no-cloud-processes", action="store_true", help="make snapshot fail if disabled cloud/upload processes are visible")
  parser.add_argument("--skip-snapshot", action="store_true", help="collect logs/processes only, useful when install did not complete")
  parser.add_argument("--no-fetch", action="store_true", help="leave the tarball on the C3 instead of scp back")
  parser.add_argument("--json", action="store_true", help="print JSON report")
  parser.add_argument("--self-test", action="store_true", help="run an offline self-test")
  args = parser.parse_args()

  if args.self_test:
    return self_test()
  if args.with_sound_probe:
    args.skip_sound_probe = False

  report = collect(args)
  print_report(report, args.json)
  return 0 if report.get("ok") else 1


if __name__ == "__main__":
  raise SystemExit(main())
