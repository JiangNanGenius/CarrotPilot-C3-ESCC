# Navipilot APP 研究记录

记录日期：2026-06-18

## 来源

- 仓库：`jixiexiaoge/navipilot`
- URL: `https://github.com/jixiexiaoge/navipilot`
- 分支：`CPdazi`
- 当前审查 commit：`c2a1028f22e47b3c4838b9e2a320966a0529cc03`

机械小哥相关来源不能只看一个库：

- `jixiexiaoge/openpilot`：openpilot 端、atune、部分 Web/cluster/工具代码来源。
- `jixiexiaoge/navipilot`：Android CP搭子 APP、导航桥、驾驶评分、摄像头预览、模型/参数管理、自动超车 UI 和协议说明来源。

## 对本项目的结论

驾驶报告不是当前 C3 车机主线里缺一个独立网页模块，而是 Navipilot Android APP 端的功能。

本项目主线应做的是：

- 保持 C3 端 `carrotMan` / `navInstructionCarrot` 数据完整。
- 保持 UDP 7705 状态广播、UDP 7706 导航输入、TCP 7709 路线、HTTP 7000 参数接口兼容。
- 保持 `/ws/raw_multiplex` 和 `/ws/camera/road` 给 APP 读取车辆数据和摄像头。
- 用实机测试确认 APP 连接、导航数据、驾驶评分采集能正常工作。

暂不应做的是：

- 把 APP 的驾驶评分 UI 整体搬进 C3 Web。
- 默认启用自动超车、ZMQ 7710 命令、外接灯板或模型切换器。
- 把 Navipilot 仓库中的 Android/Gradle 代码混入 openpilot 主分支。

## Navipilot APP 关键能力

APP README 和代码显示的核心能力：

- 多源导航：高德车机版、高德手机 SDK、Google Navigation SDK、腾讯导航 SDK。
- 导航数据发送：UDP 7706，约 5 Hz。
- 路线点发送：TCP 7709。
- 车辆与摄像头读取：WebSocket 7000，主要使用 `/ws/raw_multiplex` 和 `/ws/camera/road`。
- 参数读写：HTTP 7000。
- 自动超车命令：ZMQ 7710，当前本项目主线不启用。
- 驾驶评分：APP 端五维评分，包含平稳性、预判力、接管依赖、节能、NOO 稳定度。

## 驾驶评分数据来源

APP 侧 `DrivingDataCollector` 每秒更新一次，主要输入包括：

- 速度、加速度、急加速、急刹车、急转弯。
- NOO / cruise 激活状态。
- 行驶里程增量。
- 限速、TBT 距离、道路类型、道路名。
- 前车距离目前在 APP 中仍是 TODO。

APP 启动驾驶评分采集的直接条件：

- 网络状态显示已连接。
- `CarrotManFields.isOnroad` 为 true。

当前 APP 的 `CarrotManFields.isOnroad`、`active`、`vEgoKph`、`vCruiseKph` 等主要来自 C3 端 UDP 7705 状态广播，而不是 `/ws/raw_multiplex` 中的 `carrotMan`。`CarrotWsClient.kt` 目前订阅了 `carrotMan` 和 `gpsLocationExternal`，但 `decodeCarrotMan()` 仍返回 `null`，`gpsLocationExternal` 也未进入 `updateVehicleData()` 分支。

因此驾驶报告实测时不要只看 WebSocket 是否连接，还要确认 APP 已收到 7705 状态字段：

- `IsOnroad`
- `active`
- `v_ego_kph`
- `v_cruise_kph`
- `carcruiseSpeed`
- `tbt_dist`
- `sdi_dist`
- `xState`
- `trafficState`

APP 侧 `DrivingScoreEngine` 的总分权重：

- 平稳性 30%。
- 预判力 25%。
- 接管依赖 20%。
- 节能 15%。
- NOO 稳定度 10%。

所以 C3 端最需要保证的是实时数据和导航字段能被 APP 稳定读取，不是复制评分公式。

## 已修复的兼容问题

Navipilot 的 `carrotcode/App发往Comma3数据字段清单.md` 标出车机端一个字段 bug：

- APP 发送 `szTBTMainTextNext`。
- 旧车机代码误读成 `szTBTMainText`。
- 本项目已改为读取 `szTBTMainTextNext`。

对应守卫：

```bash
python3 scripts/personal/cplink_preflight.py
```

该守卫现在同时检查：

- C3 端 UDP 7705 状态广播字段。
- C3 端 UDP 7706 导航 JSON 字段。
- C3 端 `/ws/raw_multiplex` 和 `/ws/camera/road`。
- Navipilot APP 当前源码对 7705、raw multiplex、camera WebSocket 和驾驶评分启动条件的字段需求。

## 更新维护

本项目已新增来源跟踪：

- 远端：`jixie-navipilot`
- 本地分支：`tracking/jixie-navipilot`
- 基准文件：[UPSTREAM_BASELINES.json](UPSTREAM_BASELINES.json)
- 周期检查：GitHub Actions `Upstream Watch`

以后每次更新，除 `jixiexiaoge/openpilot` 外，也要看 `jixiexiaoge/navipilot:CPdazi` 是否有新提交，尤其是：

- `CarrotManNetworkClient.kt`
- `CarrotWsClient.kt`
- `DrivingDataCollector.kt`
- `DrivingScoreEngine.kt`
- `DrivingReportScreen.kt`
- `carrotcode/App发往Comma3数据字段清单.md`

## 实测清单

- Android 设备和 C3 在同一 WiFi。
- APP 能连接 C3 的 7000 端口。
- APP 能收到 C3 的 7705 状态广播，且 `IsOnroad`、`active`、`v_ego_kph`、`v_cruise_kph` 有正确值。
- `/ws/raw_multiplex` 有 `carState`、`controlsState`、`selfdriveState`、`deviceState`、`carrotMan`、`gpsLocationExternal`。
- `/ws/camera/road` 能显示摄像头画面。
- UDP 7706 导航字段进入 C3，`nRoadLimitSpeed`、TBT、SDI、GPS 字段变化。
- 开车结束后 APP 端生成驾驶评分报告。
- 不测试自动超车时，确认 `OVERTAKE` / ZMQ 7710 不进入本项目默认主线。
