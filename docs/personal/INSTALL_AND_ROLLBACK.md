# 安装和回滚说明

本说明面向当前个人分支：

- 设备：C3 中国克隆版，不是 C3X。
- 车辆：Kia Seltos 2023，纯 CAN，不是 CANFD。
- 车型配置：新建 `Kia Seltos 2023`，初期复用 `Kia Seltos 2021`。
- ESCC：有硬件才开启，默认关闭。
- 离线模式：`AlwaysOffline` 默认开启。

## GitHub 仓库

- 仓库：`https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC`
- 主用保护分支：`personal/c3-escc`
- 当前整合分支：`personal/c3-escc-atune`

日常开发和功能整合可以在分支上推进，但设备长期安装目标建议使用经过静态检查和实车验证后的 tag。

当前静态检查 tag：

- `carrotpilot-c3-escc-20260618-static1`
- 只代表静态检查通过，不代表实车验证。
- 目前还没有 `stable` tag。

机器可检查的安装目标记录在 [INSTALL_TARGETS.json](INSTALL_TARGETS.json)。当前 `daily_install_target` 必须为空，因为还没有完成 Seltos 实车验证和 `stable` 发布。

## 本地预检

更新、合并或上车前先跑：

```bash
python3 scripts/personal/smoke_check.py
python3 scripts/personal/escc_offline_preflight.py
```

`escc_offline_preflight.py` 只能证明代码里的 capnp、DBC、Params key、设置默认值和 ESCC/离线路径引用完整；它不能替代实车确认 0x2AB、ACC 断电重启、SCC/AEB 状态。

## 安装前

先记录当前设备可用版本和关键参数：

- 当前安装 URL 或分支。
- 当前能正常使用的车型选择。
- `/data/params` 中和车辆、ESCC、离线模式相关的参数。
- 上一个稳定 tag 或可回滚安装地址。

可在 C3 上运行设备快照脚本，生成不含 VIN / dongle id / token 的状态记录：

```bash
python3 scripts/personal/device_snapshot.py --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

不要把日常开发分支直接作为长期安装目标。建议只安装已经打过 tag 的测试版或稳定版。

如果为了准备上车静态检查而安装 `static` tag，先把它当作“受控测试版本”，不要把它当作日常稳定版本。

安装前可在本地仓库先确认安装目标清单没有误写成开发分支：

```bash
python3 scripts/personal/install_target_check.py
```

## 建议参数

Seltos 2023 初期建议：

- `AlwaysOffline=1`
- `EnableEscc=0`
- `HyundaiCameraSCC=0`
- `CanfdHDA2=0`
- `EnableRadarTracks=0`

第一次上车静态验证通过后，再手动开启：

- `EnableEscc=1`

如果开启 ESCC 后没有看到 0x2AB 或出现 SCC/AEB 相关异常，立即关闭 `EnableEscc` 并回滚到上一个稳定 tag。

## 第一次启动

第一级检查只看设备状态，不开车：

- 能进入系统，不反复重启。
- 不因为在线注册卡住。
- 不启动后台更新和远程连接。
- 设置菜单能看到“离线使用模式”和“启用 ESCC 硬件”。
- 车型可以手动选择 `Kia Seltos 2023`。

## 静态上车检查

停车状态下检查：

- 车辆识别为 Seltos 2023 或手动选择 Seltos 2023。
- 确认不是 CANFD/HDA2 路径。
- `EnableEscc=0` 时，行为应接近原 Seltos 2021 可用配置。
- `EnableEscc=1` 后，确认 CAN 中能稳定看到 ESCC 0x2AB。
- 没有 manager crash、CAN error、SCC/AEB 故障提示。

如需记录 0x2AB 和 CP搭子消息计数，可停车后运行：

```bash
python3 scripts/personal/device_snapshot.py --sample-seconds 20 --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

## 低速验证

只在安全条件下做短时间验证：

- 先不开纵控，只看车道、速度、lead/radarState 是否异常。
- 确认刹车、油门、取消按钮、接管都正常。
- 短时间启用后观察前车距离、相对速度、AEB/FCW 状态。
- 有异常加减速、SCC 故障、AEB 故障或车型路径错误时立即回滚。

## 回滚

保留两个回滚目标：

- 上一个已验证稳定 tag。
- 纯 `ajouatom/openpilot:c3-wip` 底座。

回滚后重新确认：

- 设备能正常启动。
- 车型选择仍可用。
- `EnableEscc` 已关闭或不存在。
- `AlwaysOffline` 状态符合当前设备供电方式。

## 发布 tag 建议

命名格式：

```text
carrotpilot-c3-escc-YYYYMMDD-staticN
carrotpilot-c3-escc-YYYYMMDD-testN
carrotpilot-c3-escc-YYYYMMDD-stable
```

含义：

- `staticN`：只代表静态检查通过，不代表实车验证。
- `testN`：代表准备用于受控上车测试。
- `stable`：只有完成静态启动、低速验证和多次短程验证后才使用。

打 tag 前先运行：

```bash
python3 scripts/personal/release_gate.py --tag carrotpilot-c3-escc-YYYYMMDD-static1 --kind static --run-checks
```

升级到 `stable` 前，先复制并填写 [上车测试记录模板](ROAD_TEST_LOG_TEMPLATE.md)，并把 C3 生成的设备快照文件保存到电脑本地。`stable` gate 会要求设备快照里有 `AlwaysOffline=1`、`CanfdHDA2=0`、`EnableConnect=0`，并且至少有一次 `EnableEscc=1`、`enabled=True`、`ok=True` 且 `escc_0x2ab_bus0 > 0` 的采样。

```bash
python3 scripts/personal/release_gate.py \
  --tag carrotpilot-c3-escc-YYYYMMDD-stable \
  --kind stable \
  --road-test-log docs/personal/road_tests/你的记录.md \
  --device-snapshot /path/to/carrotpilot-c3-escc-snapshot.md \
  --run-checks
```

发布 `stable` 后再更新 [INSTALL_TARGETS.json](INSTALL_TARGETS.json)：把 `current_stable_tag` 和 `daily_install_target` 指向新的稳定 tag，并把旧稳定 tag 写入 `previous_stable_tag`。没有旧稳定 tag 时，回滚目标至少保留 `rollback_base_ref`。
