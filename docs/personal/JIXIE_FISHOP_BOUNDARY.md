# 机械小哥 / fishop 功能边界

记录日期：2026-06-17

分析基线：

- `personal/c3-escc-atune`
- commit: `9ab8fee6e208`

对比来源：

- `jixie/master`: `3b039d270ff5`
- `jixie/atune`: `c045fcabb8a1`
- `jixie-navipilot/CPdazi`: `c2a1028f22e`
- `fishop/cp`: `aad13305f41c`
- 底座：`origin/c3-wip` `244b69b61b17`

## 当前结论

不能整包合并 `jixie/atune`、`jixie/master`、`jixie-navipilot/CPdazi` 或 `fishop/cp`。

原因：

- `jixie/master` 包含 CP搭子 / Navipilot 的设备端、网页、脚本和实验服务参考。
- `jixie-navipilot/CPdazi` 是 Android APP 主线，包含 CP搭子 APP、驾驶评分、摄像头预览、模型/参数管理和自动超车 UI，不应直接混入 openpilot 车机代码。
- `jixie/atune` 与当前分支相比仍包含大批 cluster HUD、USB 小屏、Qt 设置页、loggerd、Web 控制台和翻译改动。
- `fishop/cp` 与当前 C3 底座差距更大，夹带 AmapNavi、外接转向灯控制、盲区/雷达、自动变道、DEC、longcontrol、模型资产、UI 和大量非 Seltos 改动。
- fishop 分支还基于较旧代码线，直接合并会破坏当前 `selfdrive/carrot/server`、Web、cluster 和 Auto-Tuner 手动确认闭环。

## 已经具备的 CP搭子核心兼容

当前分支已经保留 CarrotMan / CPlink 核心协议链路：

- `cereal/custom.capnp` 有 `CarrotMan` 自定义消息。
- `cereal/log.capnp` 和 `cereal/services.py` 有 `carrotMan`、`navInstructionCarrot`。
- `selfdrive/carrot/carrot_man.py` 使用 UDP 7705 广播、UDP 7706 接收。
- `selfdrive/carrot/carrot_serv.py` 能解析 CP搭子常用导航数据：
  - 限速：`nRoadLimitSpeed`
  - 摄像头/限速提醒：`nSdiType`, `nSdiSpeedLimit`, `nSdiDist`
  - 导航转向：`nTBTDist`, `nTBTTurnType`, `nTBTDistNext`, `nTBTTurnTypeNext`
  - GPS：`vpPosPointLat`, `vpPosPointLon`, `latitude`, `longitude`
  - 命令：`carrotCmd`, `carrotArg`
- 已修复 APP 字段兼容：`szTBTMainTextNext` 现在读取 APP 的 `szTBTMainTextNext` 键。
- `selfdrive/carrot/carrot_man.py` 的 UDP 7705 状态广播提供 Navipilot 驾驶评分启动需要的 `IsOnroad`、`active`、`v_ego_kph`、`v_cruise_kph`、`carcruiseSpeed`、`tbt_dist`、`sdi_dist`。
- `selfdrive/carrot/server/features/ws.py` 提供 `/ws/raw_multiplex`、`/ws/raw/{service}`、`/ws/camera/{camera}`，满足 Navipilot APP 读取车辆数据和摄像头的基础入口。
- `selfdrive/carrot/server/features/params.py` 提供 `/api/params_bulk` 和 `/api/param_set`，满足 Navipilot APP `CarrotParamClient` 读取/切换 `ExperimentalMode` 等参数的基础入口。
- `scripts/personal/navipilot_live_check.py` 可在 C3 上实际检查 7000 参数接口、7705 状态广播和可选 7706 测试导航输入。
- `selfdrive/controls/lib/desire_helper.py` 已处理 CP搭子 `LANECHANGE` 命令。
- `selfdrive/carrot/web` 和 cluster/realtime 侧已经读取 `carrotMan` / `navInstructionCarrot`，用于 Web HUD 和导航显示。

新增静态检查：

```bash
python3 scripts/personal/cplink_preflight.py
```

这个检查证明当前代码仍保留 CP搭子核心协议接口，但不能替代手机 APP 实测。

## 当前主线功能边界守卫

新增静态检查：

```bash
python3 scripts/personal/feature_boundary_check.py
python3 scripts/personal/app_navi_overtake_audit.py
```

这些检查做三件事：

- 确认当前 C3 底座已有的 7000 Web、dashcam/screenrecord/tools、Auto-Tuner Web 面板仍存在。
- 确认 cluster HUD 和 `xiaoge_data` 仍由 `ClusterHud` / `ShareData` 参数控制，同时自动超车 `OVERTAKE`、fishop `amap_navi.py`、独立 `xiaoge_web.py` / `xiaoge_sentryd.py` 不会无保护进入默认主线。
- 确认 fishop `amap_navi.py`、外接转向灯、lidar 盲区、`OVERTAKE`、DEC/longcontrol 和 Navipilot APP `AutoOvertakeManager.kt` 的参考源仍可追踪，但默认主线没有半截启用。

如果后续要迁移这些被拦截的功能，必须在同一个提交里补独立开关、文档、实车/设备验证计划，并同步更新这个脚本。

## 尚未具备或不应默认启用

这些功能后续必须单独提交、单独开关、单独验证：

- `OVERTAKE` 命令。
- APP 直接控制外接转向灯。
- fishop `amap_navi.py` 设备端 AmapNavi 服务。
- fishop 盲区 / lidar / side radar 逻辑。
- fishop DEC / longcontrol 大改。
- 机械小哥哨兵模式 Web 服务。
- 机械小哥 cluster HUD / USB 小屏大改。
- 机械小哥模型切换器和自动实验模式完整闭环。
- Navipilot APP 驾驶报告实测。

其中 `jixie/master:xiaoge_web.py` 是独立 Flask Web 服务，含固定 secret key 和外部 CDN 页面资源，只能作为隔离实验参考，不能直接进默认车机主线。

驾驶报告目前按 APP 侧功能处理：C3 端负责提供 7705 状态广播、`carrotMan`、raw multiplex、摄像头和导航字段；评分计算、报告 UI 和历史记录留在 `jixiexiaoge/navipilot` Android APP 里。当前 APP 的 raw `carrotMan` 解码仍不完整，所以驾驶评分启动要优先看 7705 状态广播是否进入 APP。

## 推荐迁移顺序

### A. 当前已完成

- Seltos 2023 独立车型。
- ESCC 最小补丁。
- AlwaysOffroad。
- Auto-Tuner 第一批核心学习器。
- Auto-Tuner 第二批 Web 推荐面板和手动确认。
- CP搭子核心协议静态预检。
- Navipilot APP 来源跟踪和驾驶报告边界确认。
- Navipilot APP 参数读写接口静态守卫。
- Navipilot APP 端点 live check 和证据包集成。
- Model selector 参考线跟踪和源码审计。
- AmapNavi 只读状态桥：默认关闭，只把 `carState` 车道线和原车盲区状态发布为 `amapNavi`，不接收 APP 命令、不控制外接转向灯、不启用自动超车；设备快照和证据检查器已支持可选采样。

### B. 下一批，低风险

- CP搭子 Android APP 实测连接：
  - 手机和 C3 在同一 WiFi。
  - APP 能发现 7705 广播。
  - APP 能通过 7000 端口读取/切换 `ExperimentalMode`。
  - APP 能向 7706 发送导航数据。
  - `carrotMan` 中限速、TBT、SDI、GPS 字段随导航变化。
  - C3 上运行 `navipilot_live_check.py --param-write-probe` 通过，证据包可用 `--require-navipilot-live-check` 校验。
- `LANECHANGE` 命令实测：
  - 只在安全变道条件下响应。
  - 不响应 `OVERTAKE`，直到单独迁移该逻辑。
- 设备证据包实测：
  - 用 `collect_real_car_evidence.py --sample-seconds 20 --archive` 采集。
  - 电脑端运行 `road_test_evidence_check.py --evidence-dir <证据包目录> --require-device-snapshot --require-cplink-sample`。
  - 快照只记录导航字段是否出现，不记录 GPS 坐标、路线点或街道名。
- Navipilot APP 驾驶报告实测：
  - APP 能收到 7705 中的 `IsOnroad`、`active`、`v_ego_kph`、`v_cruise_kph`。
  - onroad 后 APP 开始采集。
  - 停车后 APP 保存一次驾驶报告。
  - C3 侧不新增本地驾驶报告网页，除非以后明确要做独立设备端报告。
- 中文说明补全：
  - CP搭子需要手机 APP 和同一 WiFi。
  - 7000 Web 只是设备端控制台，不等于手机导航桥。
- AmapNavi 只读状态桥实测：
  - 停车状态开启 `EnableAmapNaviStatus=1`。
  - 用 `collect_real_car_evidence.py --sample-seconds 20 --archive` 采集。
  - 电脑端运行 `road_test_evidence_check.py --evidence-dir <证据包目录> --require-device-snapshot --require-amap-navi-sample`。
  - 确认 `amapNavi` 服务发布车道线和原车盲区状态。
  - 确认 `carrotCmd`、`OVERTAKE`、外接转向灯和变道逻辑没有被触发。

### C. 中风险，单独分支

- fishop 完整 `amap_navi.py`。
- 外接转向灯控制。
- APP 命令变道增强。
- 自动超车 / `OVERTAKE`。当前 Navipilot APP 端已有 `AutoOvertakeManager`，会通过 7706 发送 `LANECHANGE`；设备端 fishop 参考还支持 `OVERTAKE`，必须等独立安全门控后再碰。
- 盲区、雷达、路沿概率回传。

建议分支：

- `experimental/app-navi`
- `experimental/auto-lanechange`

### D. 高风险，暂不进主用线

- DEC / longcontrol 大改。
- modeld 模型选择器和多模型资产。当前只跟踪 `tracking/model-selector` 并运行 `model_selector_audit.py`，不启用下载、编译或 modeld 切换。
- cluster HUD / USB 小屏重构。
- 哨兵模式 Web 服务。
- C4 专项线。

## CP搭子实测记录模板

每次测试记录：

```text
日期：
设备：
车：
分支 / commit：
手机系统：
CP搭子版本：
导航源：
同 WiFi：是/否
7705 广播发现：是/否
7706 数据接收：是/否
7000 参数读写：是/否
Navipilot live check：通过/失败/未测
nRoadLimitSpeed 更新：是/否
TBT 更新：是/否
SDI 更新：是/否
GPS 更新：是/否
证据包 `--require-cplink-sample`：通过/失败
LANECHANGE 命令：未测/通过/失败
异常：
回滚目标：
```
