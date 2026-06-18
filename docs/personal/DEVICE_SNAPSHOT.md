# 设备端快照采集

这个快照用于上车前后把 C3 设备上的关键状态记录下来，方便判断 ESCC、离线模式、车型路径、CP搭子协议和只读 AmapNavi 状态桥是否正常。

快照也会记录模型选择器的只读状态，包括 `DrivingModelName`、`PendingModelName` 和 `/data/model_selector_status` 中的 engine。默认主线未启用模型选择器时，状态会显示为 `default_upstream_assumed`，这表示继续使用内置 upstream modeld。

脚本默认不采集 VIN、dongle id、token、路线 id，也不读取完整 `CarParams` 内容，只记录安全参数和二进制参数的大小/hash。

## 在 C3 上运行

进入 openpilot 目录：

```bash
cd /data/openpilot
```

只采集静态状态：

```bash
python3 scripts/personal/device_snapshot.py --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

如果已经停车接好车，可以短时间采样 CAN / CarrotMan 消息：

```bash
python3 scripts/personal/device_snapshot.py --sample-seconds 20 --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

安装后也可以运行更完整的静态检查向导，它会调用本快照脚本并生成一份检查报告：

```bash
python3 scripts/personal/c3_static_check.py --output /data/media/0/carrotpilot-c3-escc-static-check.md
```

实车验证时更推荐一键采集证据包。它会把静态检查、设备快照、路测记录草稿、清单和可选压缩包放在同一个目录：

```bash
python3 scripts/personal/collect_real_car_evidence.py --archive
```

停车并准备采样 ESCC 0x2AB 时：

```bash
python3 scripts/personal/collect_real_car_evidence.py --sample-seconds 20 --archive
```

如果同时准备验证 CP搭子 / Navipilot，可在停车状态下加入 C3 侧 APP 端点检查：

```bash
python3 scripts/personal/collect_real_car_evidence.py \
  --sample-seconds 20 \
  --navipilot-check \
  --navipilot-param-write-probe \
  --archive
```

需要确认 7706 导航输入链路时，再加 `--navipilot-send-test-nav`。该测试不会发送 `LANECHANGE` 或 `OVERTAKE`。

如果要验证只读 AmapNavi 状态桥，停车状态下先开启 `EnableAmapNaviStatus=1`，再采样：

```bash
python3 scripts/personal/collect_real_car_evidence.py --sample-seconds 20 --archive
```

拷回电脑后，证据校验命令额外加 `--require-amap-navi-sample`。

准备升 `stable` 时，把这个 markdown 文件保存到电脑本地，后续传给：

```bash
python3 scripts/personal/road_test_evidence_check.py \
  --road-test-log docs/personal/road_tests/你的记录.md \
  --device-snapshot /path/to/carrotpilot-c3-escc-snapshot.md \
  --require-device-snapshot \
  --require-escc-sample
```

如果使用 `collect_real_car_evidence.py` 生成的完整证据包，解压后可以直接传整个目录：

```bash
python3 scripts/personal/evidence_readiness_report.py \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS
```

这个报告不会创建 tag，只会告诉你当前证据包已经满足哪些阶段、还缺哪些 stable 必需项。

```bash
python3 scripts/personal/road_test_evidence_check.py \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS \
  --require-device-snapshot \
  --require-offline-process-guard \
  --require-escc-sample
```

## 什么时候采集

建议至少采三次：

- 安装 `static` tag 后、第一次上车前，`EnableEscc=0`。
- 停车静态检查时，`EnableEscc=0`。
- 停车静态检查时，手动开启 `EnableEscc=1` 后，确认是否看到 ESCC 0x2AB。

每次都可以优先使用 `collect_real_car_evidence.py`，这样后续升 `stable` 时不用再手动拼文件。

如果测试 CP搭子 / Navipilot，再额外采一次：

- C3 和手机在同一 WiFi。
- CP搭子 APP 正在发送导航数据。
- `--sample-seconds 20` 期间观察 `carrotMan_updates`、`navInstructionCarrot_updates` 和导航字段。
- 需要机器检查 CP搭子实连时，可在电脑端证据检查命令里加 `--require-cplink-sample`。
- 需要机器检查 C3 侧 APP 端点时，可运行证据包时加 `--navipilot-check`，电脑端校验时加 `--require-navipilot-live-check`。

如果测试只读 AmapNavi 状态桥，再额外采一次：

- 停车状态。
- 手动开启 `EnableAmapNaviStatus=1`。
- `--sample-seconds 20` 期间观察 `amapNavi_updates` 和 `last_amapNavi`。
- 需要机器检查时，可在电脑端证据检查命令里加 `--require-amap-navi-sample`。

如果测试模型选择器参考线或实验分支，再额外看一次：

- `DrivingModelName`：当前模型名；默认主线通常为 `<missing>`。
- `PendingModelName`：等待重启编译/安装的模型；正常路测前不应有 pending。
- `model_selector_status_available`：是否读到了 `/data/model_selector_status`。
- `model_selector_engine`：`default_upstream_assumed`、`upstream_modeld` 或 `carrot_modeld`。
- `model_selector_custom_active`：是否正在使用自定义 `carrot_modeld`。
- 需要机器检查时，可在电脑端证据检查命令里加 `--require-model-selector-status`。该检查只要求状态字段存在且没有 pending 模型安装，不证明自定义模型安全。

## 快照里重点看什么

- `branch` / `commit` / `tags`：确认安装的是预期 tag 或分支。
- `CarParamsDecoded`：是否成功解码当前设备上的 `CarParams`。
- `carFingerprint`：确认当前车型路径，应为 Seltos 相关车型。
- `carName`、`networkLocation`、`safetyConfigs`、`spFlags`：确认 Hyundai/Kia safety、接线位置和 ESCC safety 参数摘要。
- `AlwaysOffline`：个人 C3 克隆版建议为 `1`。
- `EnableEscc`：第一次上车前应为 `0`。
- `HyundaiCameraSCC`、`CanfdHDA2`：Seltos 2023 纯 CAN 初期应为 `0`。
- `EnableRadarTracks`：初期建议为 `0`。
- `DisableUpdates`、`EnableConnect`：离线模式下应符合预期。
- `process_snapshot_available`：是否成功读取进程列表。
- `offline_forbidden_processes_seen`：离线模式下不应看到更新、远程连接或上传进程。
- `updated_process_seen` / `connect_process_seen` / `uploader_process_seen`：离线模式下应为 `False`。
- `escc_0x2ab_bus0`：开启 ESCC 后用于确认 0x2AB 是否真的出现在 bus 0。
- `carrotMan_updates` / `navInstructionCarrot_updates`：用于确认 CP搭子 / Navipilot 数据是否进入系统。
- `EnableAmapNaviStatus`：只读 AmapNavi 状态桥开关，默认应为 `0`。
- `cplink_updates_seen`：采样期间是否收到 CP搭子 / Navipilot 消息。
- `cplink_speed_limit_seen`：是否看到限速字段。
- `cplink_sdi_seen`：是否看到摄像头 / 限速提醒字段。
- `cplink_tbt_seen`：是否看到转向 / 诱导字段。
- `cplink_gps_seen`：是否看到 GPS 字段。快照只记录是否出现，不记录坐标。
- `cplink_lanechange_cmd_seen`：是否看到 `LANECHANGE` 命令。
- `amapNavi_updates`：采样期间是否收到只读 AmapNavi 状态桥消息。
- `amap_navi_updates_seen`：是否至少收到一次 AmapNavi 状态。
- `amap_navi_lane_seen`：是否看到车道线状态。
- `amap_navi_left_blind_seen` / `amap_navi_right_blind_seen`：是否看到原车盲区状态为触发。
- `last_carrotMan` / `last_navInstructionCarrot`：最后一帧非敏感字段摘要，不包含 GPS 坐标、路线点或街道名。
- `last_amapNavi`：最后一帧只读 AmapNavi 状态摘要，只含左右盲区和车道线状态，不含 APP 命令。
- `DrivingModelName` / `PendingModelName`：模型选择器参数，只读记录。
- `model_selector_engine`：当前模型 engine。默认主线没有模型选择器状态文件时显示 `default_upstream_assumed`。
- `model_selector_pending_active`：是否存在等待重启处理的模型安装状态；上车前应为 `False`。

`stable` 发布要求至少有一个快照满足：

- `CarParamsDecoded=ok`
- `carFingerprint` 包含 `SELTOS`
- `safetyConfigs` 有有效摘要
- `AlwaysOffline=1`
- `EnableConnect=0`
- `process_snapshot_available=True`
- `offline_forbidden_processes_seen=False`
- `updated_process_seen=False`
- `connect_process_seen=False`
- `uploader_process_seen=False`
- `CanfdHDA2=0`
- `HyundaiCameraSCC=0`
- `EnableEscc=1`
- `enabled=True`
- `ok=True`
- `escc_0x2ab_bus0 > 0`

## 不要公开的内容

脚本会避开常见敏感项，但如果你手动补充内容，不要贴：

- VIN
- dongle id
- GitHub token
- WiFi 密码
- 个人定位路线
- 完整 `/data/params` 打包文件

需要发给维护者时，优先发脚本生成的 markdown 内容，不要直接发整个设备日志目录。
