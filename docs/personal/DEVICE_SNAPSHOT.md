# 设备端快照采集

这个快照用于上车前后把 C3 设备上的关键状态记录下来，方便判断 ESCC、离线模式、车型路径和 CP搭子协议是否正常。

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

准备升 `stable` 时，把这个 markdown 文件保存到电脑本地，后续传给：

```bash
python3 scripts/personal/road_test_evidence_check.py \
  --road-test-log docs/personal/road_tests/你的记录.md \
  --device-snapshot /path/to/carrotpilot-c3-escc-snapshot.md \
  --require-device-snapshot \
  --require-escc-sample
```

## 什么时候采集

建议至少采三次：

- 安装 `static` tag 后、第一次上车前，`EnableEscc=0`。
- 停车静态检查时，`EnableEscc=0`。
- 停车静态检查时，手动开启 `EnableEscc=1` 后，确认是否看到 ESCC 0x2AB。

如果测试 CP搭子 / Navipilot，再额外采一次：

- C3 和手机在同一 WiFi。
- CP搭子 APP 正在发送导航数据。
- `--sample-seconds 20` 期间观察 `carrotMan_updates`、`navInstructionCarrot_updates` 和导航字段。

## 快照里重点看什么

- `branch` / `commit` / `tags`：确认安装的是预期 tag 或分支。
- `AlwaysOffline`：个人 C3 克隆版建议为 `1`。
- `EnableEscc`：第一次上车前应为 `0`。
- `HyundaiCameraSCC`、`CanfdHDA2`：Seltos 2023 纯 CAN 初期应为 `0`。
- `EnableRadarTracks`：初期建议为 `0`。
- `DisableUpdates`、`EnableConnect`：离线模式下应符合预期。
- `escc_0x2ab_bus0`：开启 ESCC 后用于确认 0x2AB 是否真的出现在 bus 0。
- `carrotMan_updates` / `navInstructionCarrot_updates`：用于确认 CP搭子 / Navipilot 数据是否进入系统。

`stable` 发布要求至少有一个快照满足：

- `AlwaysOffline=1`
- `EnableConnect=0`
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
