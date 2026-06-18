# CarrotPilot-C3-ESCC 使用说明

本文面向实际装车和日常使用，不是开发笔记。当前目标设备是 C3 中国克隆版，目标车辆是 Kia Seltos 2023 纯 CAN。其它车、C3X、C4 或 CANFD/HDA2 车型不要按本文直接套用。

## 资料来源

本说明参考并改写了这些上游资料和代码：

- `jixiexiaoge/navipilot:CPdazi` 的 APP README：用于理解 CP搭子 / Navipilot APP 的导航、参数、驾驶报告和扩展能力。
- `jixiexiaoge/openpilot:atune` 的 `selfdrive/carrot/README.md`：用于理解机械小哥 Web / 7000 控制台 / Auto-Tuner 所在模块。
- `jixiexiaoge/openpilot:atune` 的 `apps/carrotman.txt`：CarrotMan APP 下载入口参考。
- `fishop/openpilot:cp`：用于 ESCC、EnableConnect 默认关闭、AmapNavi / 自动超车相关来源审计。

本文只描述本项目当前实际支持或明确隔离的功能。机械小哥和 fishop 源码里存在但本项目没有启用的功能，会标为“未启用”或“实验/隔离”。

## 最安全的默认状态

第一次安装和第一次上车，建议保持：

| 参数 | 建议 | 说明 |
| --- | --- | --- |
| `EnableEscc` | `0` | ESCC 硬件支持默认关闭。先确认车辆、摄像头 CAN、SCC/AEB/FCW 都正常，再手动开启。 |
| `AlwaysOffroad` | `0` | 默认关闭。只在车辆仍有 ACC/CAN 供电、但需要保持 offroad 做本地更新或调试时手动开启。 |
| `EnableConnect` | `0` | 默认关闭。避免克隆 C3 连接 comma/openpilot 官方注册和远程连接服务。 |
| `CanfdHDA2` | `0` | Seltos 2023 纯 CAN 车不要开。 |
| `HyundaiCameraSCC` | `0` | 未确认接线和车型前保持关闭。 |
| `EnableRadarTracks` | `0` | ESCC 没验证前不启用原车 radar tracks 变体。 |
| `CarrotLearningActive` | `0` | Auto-Tuner 学习默认关闭。 |
| `CarrotLearningAutoApply` | `0` | 不自动应用调参建议。 |
| `EnableAmapNaviStatus` | `0` | AmapNavi 只读状态桥默认关闭。 |

默认设计和马上飞扬 / fishop 的思路一致：不连接官方 Connect，但不断开本地网络。这样更新、Git 拉代码、Web 本地管理仍然可以按需要工作。

## 安装入口

C3 初装 / Custom Software 输入：

```text
https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/i
```

SSH 救援或切换通道：

```bash
curl -fsSL https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/s | sh
curl -fsSL https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/s | sh -s -- --channel test
curl -fsSL https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/s | sh -s -- --channel dev
```

当前默认通道是 `install-c3-escc-test`。编号 test tag 只用于追溯，不建议手动输入。

## 首次上车流程

1. 安装后先不要开 ESCC。
2. 进入系统，确认没有 manager crash、循环重启、注册卡死。
3. 车型选择使用 `Kia Seltos 2023`。如果自动识别不到，可手动选；当前配置复用 Seltos 2021。
4. 确认 `CanfdHDA2=0`、`HyundaiCameraSCC=0`。
5. 停车状态运行一次设备快照或 commissioning：

```bash
python3 scripts/personal/c3_commissioning.py --archive
```

6. 熄火断电，再重新 ACC/CAN 供电，确认能正常进系统。
7. 断电重启确认后记录：

```bash
python3 scripts/personal/record_power_cycle_boot.py
python3 scripts/personal/collect_real_car_evidence.py --archive
```

8. 确认基础路径正常后，再考虑手动开启 `EnableEscc=1`，并低速/停车观察 ESCC 0x2AB、lead、SCC、AEB、FCW 状态。

## ESCC 硬件支持

ESCC 是本项目必须保留的功能，但默认关闭。

作用：

- 支持马上飞扬 / fishop 版本里用于增强 SCC lead 的 ESCC 0x2AB 路径。
- 在 Hyundai/Kia safety 参数里加入 ESCC flag。
- radar parser 读取 ESCC 目标状态和距离/横向位置/相对速度。

怎么用：

- 设置里开启 `EnableEscc=1`。
- 必须确认车上 bus 0 能稳定看到 0x2AB。
- 如果出现 SCC/AEB/FCW 报错、异常 lead、异常加减速，立刻关 `EnableEscc`。

不建议同时乱开：

- `CanfdHDA2`
- `HyundaiCameraSCC`
- 未确认含义的 radar tracks 变体

## EnableConnect 和 AlwaysOffroad

这两个容易混，单独说明。

`EnableConnect`：

- 默认 `0`。
- 控制 comma/openpilot 远程连接 / athena / 上传相关流程。
- 当前版本 `EnableConnect=0` 时会跳过在线注册，使用本地 `UnregisteredDevice`。
- 这接近马上飞扬 / fishop 的行为：不连接官方注册服务。
- 关闭它不等于完全断网；Git 更新、局域网 Web、SSH 仍可按实际网络使用。

`AlwaysOffroad`：

- 默认 `0`。
- 只作为强制 Offroad/驻车供电更新/故障排查开关。
- 开启后设备会保持 `IsOnroad=False`，pandad 会把 panda 安全模式压到 `NO_OUTPUT`，避免进入驾驶控制或接管 harness 继电器。
- 它不负责官方注册；官方注册/远程连接仍由 `EnableConnect` 控制。
- 它不应该切断本地网络；局域网 Web、SSH、Git 拉取和本地更新服务仍应可用。
- 如果只是日常使用克隆 C3，不建议默认开它。
- 典型用途是车辆点火供电但不能开车时，先开它让设备保持 offroad，再做更新或调试。

推荐日常状态：

```text
AlwaysOffroad=0
EnableConnect=0
```

## Auto-Tuner / 自动调参

来源是机械小哥 `jixiexiaoge/openpilot:atune`，但本项目没有整包合并 atune，只迁移了安全边界更清楚的核心学习和手动确认闭环。

当前支持：

- `CarrotLearningActive`：开启后记录驾驶和接管习惯，生成建议值。
- `CarrotTunerApplyLat`：允许生成横向建议，例如车道偏移、转向延迟。
- `CarrotTunerApplyLong`：允许生成纵向建议，例如加速、跟车距离、前车制动反应。
- `CarrotLearningAutoApply`：自动应用建议，默认关闭，不推荐开。
- `CarrotLearningApply`：停车后手动应用当前建议。
- `CarrotLearningIgnore`：忽略当前建议，但保留学习数据。
- `CarrotLearningClear`：清空学习数据和当前建议。
- Web 设置页有一个轻量推荐面板，通过 `/api/carrot_learning` 读取和执行动作。

推荐用法：

1. 先保持 `CarrotLearningActive=0` 跑几次，确认 ESCC 和基础驾驶正常。
2. 再开 `CarrotLearningActive=1`，只观察推荐，不开自动应用。
3. 路测结束、停车后再看推荐值。
4. 如果建议看起来合理，停车状态手动应用。
5. 每次应用前先保存 `/data/params` 或跑一次设备快照。

不要做：

- 不要在第一次装车就开启 `CarrotLearningAutoApply`。
- 不要在还没确认 ESCC、SCC、AEB 正常时应用纵向建议。
- 不要把 Auto-Tuner 当成自动修车工具。它只根据有限样本给建议，最终仍要人工判断。

## 7000 Web 本地控制台

当前 C3 端默认有 `carrot_server.py`，本地 Web 服务在 7000 端口。

常见用途：

- 查看和修改设置参数。
- 备份/恢复部分参数。
- 查看 dashcam / screenrecord。
- 使用 tools 页面执行受控工具。
- 查看 Auto-Tuner 推荐面板。
- 给 Navipilot APP 提供参数读写接口。

访问方式：

```text
http://<C3_IP>:7000
```

注意：

- 这是局域网管理入口，不等于官方 Connect。
- 修改驾驶相关参数前先确认车停稳。
- 终端和工具功能有风险，不确定命令含义时不要乱点。

## CP搭子 / Navipilot APP

来源是机械小哥 `jixiexiaoge/navipilot:CPdazi`。APP README 里描述了很多能力：高德/Google/腾讯导航、摄像头预览、参数管理、驾驶评分、自动超车、LED 彩屏等。本项目只保证 C3 端基础协议兼容，不默认启用所有 APP 高风险功能。

当前 C3 端已守住的接口：

| 接口 | 用途 |
| --- | --- |
| UDP 7705 | C3 向 APP 广播车速、onroad、巡航、导航状态等。 |
| UDP 7706 | APP 向 C3 发送导航数据。 |
| TCP 7709 | 路线点数据。 |
| HTTP 7000 | 参数读取和写入，例如 `ExperimentalMode`。 |
| WebSocket 7000 | raw multiplex 和 camera road 预览。 |

停车状态可跑：

```bash
python3 scripts/personal/navipilot_live_check.py --param-write-probe
```

如果要采证据包：

```bash
python3 scripts/personal/collect_real_car_evidence.py \
  --sample-seconds 20 \
  --navipilot-check \
  --navipilot-param-write-probe \
  --archive
```

当前状态：

- APP 发现 C3、导航数据、驾驶报告都还需要手机实测。
- C3 端已静态检查 APP 所需字段，但这不能替代真实 Android APP 测试。

## 驾驶报告

驾驶报告是 Navipilot Android APP 端功能，不是 C3 Web 里的本地报告页面。

APP 侧设计：

- 每秒采集车速、加速度、NOO/巡航状态、限速、TBT、道路类型等。
- 五维评分：平稳性、预判力、接管依赖、节能、NOO 稳定度。
- 报告保存在 Android APP 本地，最多保留约 50 条会话。

C3 端需要做的是：

- 稳定输出 7705 状态字段。
- 确保 APP 能看到 `IsOnroad`、`active`、`v_ego_kph`、`v_cruise_kph` 等字段。
- 不需要把 APP 报告 UI 搬到 C3 Web。

## AmapNavi 只读状态桥

当前只启用了安全边界较清楚的只读状态桥：

- 参数：`EnableAmapNaviStatus`
- 默认：`0`
- 作用：把 C3 已有的车道线、原车盲区等状态镜像到 `amapNavi` 消息。
- 不接收 APP 命令。
- 不启用自动超车。
- 不接外设控制。

什么时候开：

- 只在停车调试或验证 APP 状态读取时开启。
- 正常日常使用可以保持关闭。

## 显示和导航相关开关

这些主要影响 UI 显示，不应改变底层控制逻辑：

- `ShowRouteInfo`：显示 CP搭子/APN 导航路线提示。
- `ShowRadarInfo`：显示雷达目标信息。
- `ShowPathMode` / `ShowPathColor`：改变路径线样式和颜色。
- `ShowModelView`：模型视图显示模式。

原则：

- 显示项可以按个人习惯调。
- 如果文字、图标遮挡驾驶信息，先关掉。
- 不要把显示项和控制项混为一谈。

## 模型选择器

当前只做状态跟踪和源码审计，没有启用真正的模型下载、安装、编译或 modeld 切换。

快照里会记录：

- `DrivingModelName`
- `PendingModelName`
- `/data/model_selector_status` 如果存在，会记录 engine 和 pending 状态。

当前不要做：

- 不要把未知模型直接放上车跑。
- 不要把模型切换和 ESCC 首次路测混在一起。

## cluster HUD / USB 小屏 / LED

当前代码树里有 cluster HUD / USB 小屏相关代码，也有来源跟踪，但不作为默认功能。

状态：

- `ClusterHud` 为 0 时不启动。
- `carrot_cluster` 只在 `ClusterHud` 为 1 或 2 时启动。
- 外接 LED / 蓝牙彩屏主要在 Navipilot APP 或机械小哥来源中，当前本项目默认不启用。

建议：

- 没有对应硬件就不要开。
- 不要和 ESCC 首次验证同一天一起测。

## 机械小哥数据广播 / ShareData

当前有 `xiaoge_data` 相关代码，但默认不开。

- 参数：`ShareData`
- 作用：给机械小哥相关数据链路广播数据。
- 风险：会增加额外进程和网络/数据流。

没有明确 APP 或调试需求时保持关闭。

## 自动超车 / OVERTAKE / LANECHANGE

Navipilot APP 和 fishop 来源里都有自动超车、变道命令相关代码，但本项目默认主线不启用完整自动超车。

当前边界：

- APP 侧可能发送 `LANECHANGE`。
- 本项目不让 `OVERTAKE` / ZMQ 7710 进入默认驾驶控制主线。
- 完整自动超车需要独立分支、独立开关、盲区/车道线/速度/导航多条件保护。

日常使用建议：不要开。

## DEC / full AmapNavi / 外设控制

这些属于高风险或未验证整合项：

- fishop 完整 `amap_navi.py`
- DEC / longcontrol 大改
- APP 外接转向灯控制
- 自动超车命令闭环

当前都不进入默认主线。以后如果要做，应该开独立实验分支，不和 Seltos 2023 / ESCC 稳定线混在一起。

## 参数迁移

如果你当前 C3 上有马上飞扬 / fishop 版本且能正常用，可以先导出白名单参数：

```bash
python3 scripts/personal/params_migration.py export --output /data/media/0/carrotpilot-fishop-working-params.json
```

安装本项目后先 dry-run：

```bash
python3 scripts/personal/params_migration.py import --input /data/media/0/carrotpilot-fishop-working-params.json
```

确认输出合理后再加：

```bash
python3 scripts/personal/params_migration.py import --input /data/media/0/carrotpilot-fishop-working-params.json --apply
```

优先迁移：

- `EnableEscc`
- `HyundaiCameraSCC`
- `EnableRadarTracks`
- Seltos / 转向 / 纵向相关手动调参项
- Auto-Tuner 相关项，如果你确实已经在用

不要盲目迁移：

- CANFD/HDA2
- 未知外设
- 自动超车
- 模型切换

## 遇到问题先关什么

如果出现异常，按这个顺序降级：

1. 关 `EnableEscc`。
2. 关 `CarrotLearningActive` 和 `CarrotLearningAutoApply`。
3. 关 `EnableAmapNaviStatus`。
4. 关显示增强项，例如 `ShowRouteInfo`、`ShowRadarInfo`。
5. 确认 `CanfdHDA2=0`、`HyundaiCameraSCC=0`。
6. 如需要在 ACC/CAN 供电时保持 offroad 做本地更新或继电器调试，临时开 `AlwaysOffroad=1`。
7. 仍异常则回滚到上一个可用 tag 或原版本。

任何时候只要出现异常加减速、SCC/AEB/FCW 报错、车型路径错误，都先停止路测。
