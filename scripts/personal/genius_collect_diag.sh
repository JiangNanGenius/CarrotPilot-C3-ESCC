#!/usr/bin/env bash
# Genius Pilot — Seltos 2023 车辆诊断采集（克隆 C3，离线可用）
# 发动机运转、车静止（P挡）、dp 未激活时运行。
# 一次采全：ECU 指纹 / VIN / CAN 报文快照 / ESCC 检测 / 车型识别 / 状态
# 输出 /data/genius_diag/diag_时间戳/，便于上车一次带走。

TS=$(date +%Y%m%d_%H%M%S 2>/dev/null || echo boot)
OUT_DIR="/data/genius_diag/diag_${TS}"
mkdir -p "$OUT_DIR" 2>/dev/null

# 仓库根（设备上 /data/openpilot）
BASEDIR="${BASEDIR:-/data/openpilot}"
cd "$BASEDIR" 2>/dev/null || { echo "cannot cd $BASEDIR"; exit 1; }

log() { echo "[$(date +%H:%M:%S 2>/dev/null)] $*" | tee -a "$OUT_DIR/_progress.log"; }

log "=== Genius 诊断采集开始 ==="

# 0) 环境信息
{
  echo "MODEL: $(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null)"
  echo "AGNOS: $(cat /VERSION 2>/dev/null)"
  echo "KERNEL: $(uname -a 2>/dev/null)"
  echo "GENIUS: $(git log --oneline -1 2>/dev/null)"
  echo "BRANCH: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo "DATE: $(date 2>/dev/null)"
} > "$OUT_DIR/00_device.txt"
log "0 环境信息完成"

# 1) VIN
log "1 读取 VIN..."
timeout 60 python3 selfdrive/debug/car/vin.py > "$OUT_DIR/01_vin.txt" 2>&1 || echo "(vin failed)" >> "$OUT_DIR/01_vin.txt"

# 2) ECU 固件指纹（hyundai）
log "2 读取 ECU 固件指纹(hyundai)..."
timeout 180 python3 selfdrive/debug/car/fw_versions.py --brand hyundai > "$OUT_DIR/02_fw_hyundai.txt" 2>&1

# 3) ECU 全扫描
log "3 ECU 全扫描..."
timeout 240 python3 selfdrive/debug/car/fw_versions.py --scan > "$OUT_DIR/03_fw_scan.txt" 2>&1

# 4) CAN 指纹（车辆 CAN 消息指纹）
log "4 CAN 指纹采集(35s)..."
timeout 45 python3 selfdrive/debug/get_fingerprint.py > "$OUT_DIR/04_can_fingerprint.txt" 2>&1

# 5) ESCC 关键报文采样（0x2AB / SCC / 雷达）
log "5 ESCC/CAN 报文采样(30s)..."
timeout 40 python3 - <<'PY' > "$OUT_DIR/05_escc_can.txt" 2>&1
import time
try:
  import cereal.messaging as messaging
  logcan = messaging.sub_sock('can')
  seen = {}
  interesting = {0x2AB, 0x371, 0x38D, 0x389, 0x386, 0x35E, 0x2F0, 0x2A0}
  start = time.monotonic()
  while time.monotonic() - start < 30:
    lc = messaging.recv_sock(logcan, True)
    if lc is None:
      break
    for m in lc.can:
      a = m.address
      dat = m.dat.hex() if hasattr(m, 'dat') else ''
      if a not in seen:
        seen[a] = dat
      if a in interesting:
        seen[a] = dat + " <== ESCC候选"
  print("总报文地址数:", len(seen))
  for a in sorted(seen):
    print(hex(a), seen[a][:40])
except Exception as e:
  print("can sample error:", e)
PY

# 6) ESCC 检测证据（启动日志里的 $$$ESCC）
log "6 ESCC 检测证据..."
{
  echo "--- launch_log 里的 ESCC ---"
  grep -iE 'ESCC|enhanced|0x2AB|\$\$\$' /tmp/launch_log 2>/dev/null | head -20
  echo "--- params ---"
  for p in CarParams FingerprintedCar FuzzyFingerprint CarModel; do
    echo "$p: $(cat /data/params/d/$p 2>/dev/null | head -c 200)"
  done
} > "$OUT_DIR/06_escc_state.txt"

log "=== 采集完成: $OUT_DIR ==="
echo "DONE $OUT_DIR"
