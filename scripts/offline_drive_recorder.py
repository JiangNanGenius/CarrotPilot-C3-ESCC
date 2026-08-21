#!/usr/bin/env python3
"""车端离线行车采集器。

用途：地库/无信号环境，车自己记录关键数据到 /data/offline_log/，回来用 SSH 翻出来分析。
记录：
  1. 车型指纹（每次 card 识别后的 carFingerprint + fingerprintSource + radarUnavailable）
  2. 踩刹车事件 + 当时的 alert（onroadEvents 里的 pedalPressed 等）
  3. 刹车信号抖动（brakePressed 变化时间戳，用于判断是否闪断）
  4. 雷达 lead 数据（leadOne.status/radar/dRel/vLead，用于判断雷达是否真用上）

输出：/data/offline_log/drive_<时间戳>.jsonl  （每行一条 JSON 事件）
      /data/offline_log/fingerprint.txt       （最新指纹信息，覆盖写）
运行：在车端后台跑  python3 scripts/offline_drive_recorder.py
      （或加 & 挂后台；地库熄火 offroad 时自动停记，rlog 持久化不丢）
"""
import os
import sys
import time
import json

sys.path.insert(0, "/data/openpilot")

import cereal.messaging as messaging  # noqa: E402
from cereal import car  # noqa: E402

OUT_DIR = "/data/offline_log"
os.makedirs(OUT_DIR, exist_ok=True)

ts = time.strftime("%Y%m%d_%H%M%S")
LOG_PATH = os.path.join(OUT_DIR, f"drive_{ts}.jsonl")
FP_PATH = os.path.join(OUT_DIR, "fingerprint.txt")


def jwrite(obj):
  with open(LOG_PATH, "a") as f:
    f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
  print(f"[offline_drive_recorder] 开始采集 -> {LOG_PATH}")
  jwrite({"event": "recorder_start", "ts": time.time()})

  sm = messaging.SubMaster([
    "carParams", "carState", "selfdriveState", "onroadEvents", "radarState",
  ], poll=None)  # 非阻塞轮询：offroad 时 carState 不发布也不退出

  prev_brake = False
  prev_fp = None
  brake_toggle_count = 0

  while True:
    sm.update(0)  # 立即返回，offroad 时安全空转
    now = time.time()

    # ---- 指纹（carParams 一更新就记）----
    if sm.updated["carParams"]:
      try:
        cp = sm["carParams"]
        fp = cp.carFingerprint
        src = str(cp.fingerprintSource)
        if fp != prev_fp:
          prev_fp = fp
          info = {
            "event": "fingerprint",
            "ts": now,
            "carFingerprint": fp,
            "fingerprintSource": src,
            "carVin": cp.carVin,
            "radarUnavailable": cp.radarUnavailable,
            "openpilotLongitudinalControl": cp.openpilotLongitudinalControl,
            "pcmCruise": cp.pcmCruise,
          }
          jwrite(info)
          # 覆盖写最新指纹，方便直接看
          with open(FP_PATH, "w") as f:
            f.write(json.dumps(info, ensure_ascii=False, indent=2))
          print(f"[fingerprint] {fp} source={src} radarUnavail={cp.radarUnavailable}")
      except Exception as e:
        jwrite({"event": "fp_error", "ts": now, "err": str(e)})

    # ---- 刹车信号抖动检测 ----
    if sm.updated["carState"]:
      cs = sm["carState"]
      brake = bool(cs.brakePressed)
      if brake != prev_brake:
        brake_toggle_count += 1
        jwrite({
          "event": "brake_toggle",
          "ts": now,
          "brakePressed": brake,
          "brake": round(float(cs.brake), 3),
          "vEgo": round(float(cs.vEgo), 2),
          "standstill": bool(cs.standstill),
          "cruiseEnabled": bool(cs.cruiseState.enabled),
          "toggle_count": brake_toggle_count,
        })
        prev_brake = brake

    # ---- 踩刹车时的 alert 事件（onroadEvents）----
    if sm.updated["onroadEvents"]:
      for ev in sm["onroadEvents"]:
        name = str(ev.name)
        # 只记 pedal/brake/巡航退出相关
        if any(k in name.lower() for k in ["pedal", "brake", "disable", "noentry", "override"]):
          jwrite({
            "event": "onroad_event",
            "ts": now,
            "name": name,
            "brakePressed_now": prev_brake,
            "alertText1": "",  # selfdriveState 里有 alert 文本，这里先记事件名
          })

    # ---- selfdriveState 的 alert 文本（踩刹车时屏幕显示什么）----
    if sm.updated["selfdriveState"]:
      ss = sm["selfdriveState"]
      if ss.alertType and ("brake" in (ss.alertText1 + ss.alertText2).lower() or
                           "pedal" in (ss.alertText1 + ss.alertText2).lower() or
                           "pedal" in str(ss.alertType).lower()):
        jwrite({
          "event": "brake_alert",
          "ts": now,
          "alertType": str(ss.alertType),
          "alertText1": ss.alertText1,
          "alertText2": ss.alertText2,
          "alertSize": str(ss.alertSize),
          "alertStatus": str(ss.alertStatus),
        })

    # ---- 雷达 lead（每秒记一次，判断是否真雷达）----
    if sm.updated["radarState"]:
      rs = sm["radarState"]
      l = rs.leadOne
      # 每 ~1s 记一条（radarState 是 20Hz，用时间戳节流）
      if not hasattr(main, "_last_radar_ts"):
        main._last_radar_ts = 0
      if now - main._last_radar_ts >= 1.0:
        main._last_radar_ts = now
        jwrite({
          "event": "radar_lead",
          "ts": now,
          "status": bool(l.status),
          "radar": bool(l.radar),
          "dRel": round(float(l.dRel), 2),
          "vLead": round(float(l.vLead), 2),
          "modelProb": round(float(l.modelProb), 3),
        })

    # 非阻塞轮询要加 sleep，避免空转占满 CPU
    time.sleep(0.05)  # 20Hz


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("[offline_drive_recorder] 停止")
  except Exception as e:
    import traceback
    with open(os.path.join(OUT_DIR, "recorder_crash.log"), "a") as f:
      f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {traceback.format_exc()}\n")
    raise
