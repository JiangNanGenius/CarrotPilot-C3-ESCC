# 功能整合矩阵

## 必须进入主分支

| 功能 | 来源 | 优先级 | 计划 |
| --- | --- | --- | --- |
| C3 最新 CarrotPilot / CarPad 底座 | `ajouatom/openpilot:c3-wip` | P0 | 当前按韩国主源处理，作为主线底座 |
| Seltos 2023 独立车型条目 | 用户车辆 | P0 | 新建车型，初期复用 Seltos 2021 配置 |
| Seltos 2023 纯 CAN 路径 | 用户车辆 | P0 | 不走 CANFD/HDA2 |
| ESCC 硬件支持 | `fishop/openpilot:cp` | P0 | 拆成独立补丁 |
| ESCC 参数开关 | `fishop/openpilot:cp` | P0 | 默认关闭 |
| Hyundai Camera SCC 相关兼容 | `fishop/openpilot:cp` | P0 | 按 Seltos 纯 CAN 接线验证 |
| Radar tracks / ESCC lead 解析 | `fishop/openpilot:cp` | P0 | 优先迁移 |
| Always Offline 离线使用模式 | 用户硬件约束 / fishop 思路 | P0 | C3 克隆版、ACC/CAN 供电、无法注册时使用 |

## 计划进入扩展分支

| 功能 | 来源 | 优先级 | 计划 |
| --- | --- | --- | --- |
| Auto-Tuner / 在线调参 | `jixiexiaoge/openpilot:atune` | P1 | 已迁移核心学习器和 Web 手动确认，默认关闭 |
| 7000 Web 控制台增强 | `jixiexiaoge/openpilot:atune` / `master` | P1 | 当前 C3 底座已有 7000 Web、录像/截屏/工具/Auto-Tuner 面板；剩余增强分批迁移 |
| CP搭子 / Navipilot 核心协议 | `jixiexiaoge/openpilot:master` / `jixiexiaoge/navipilot:CPdazi` | P1 | 已做静态预检，待 APP 实测 |
| 实验模式 Web 开关 | 当前 C3 底座 | P1 | 已静态确认，可在 Web 设备页操作 `ExperimentalMode` |
| Navipilot APP 参数接口 | `jixiexiaoge/navipilot:CPdazi` / 当前 C3 Web API | P1 | 已静态确认 `/api/params_bulk`、`/api/param_set` 和 APP `CarrotParamClient` 契约 |
| Navipilot APP 端点 live check | 本项目维护 | P1 | 已新增 C3 侧检查器，可验证 7000 参数接口、7705 状态广播和可选 7706 测试导航输入；不替代手机 APP 实测 |
| 自动实验模式切换完整闭环 | 机械小哥 / Navipilot APP | P1 | C3 端参数接口已具备；APP 侧实测和策略闭环待验证 |
| 模型选择切换器 | `ajouatom/openpilot:happymaj11r/carrot-wip-model_selector` / Navipilot APP | P1 | 已跟踪参考线并增加源码审计；下载/编译/切 modeld 仍保持高风险独立批次 |
| AmapNavi 只读状态桥 | `fishop/openpilot:cp` / 本项目维护 | P1 | 已接入默认关闭的 `EnableAmapNaviStatus`，只发布车道线和原车盲区状态，不接收 APP 命令 |
| AmapNavi / 自动超车来源审计 | `fishop/openpilot:cp` / `jixiexiaoge/navipilot:CPdazi` | P1 | 已新增源码审计，确认完整 AmapNavi、外设控制、自动超车和 DEC 仍隔离 |
| 自动超车 | 机械小哥 / fishop | P2 | 后置验证；APP 可发 `LANECHANGE`，`OVERTAKE` 不进默认主线 |
| LED / cluster HUD | 机械小哥 | P2 | 实验功能 |
| 驾驶报告 | `jixiexiaoge/navipilot:CPdazi` | P2 | APP 端功能；C3 端保持 WebSocket/CarrotMan 数据兼容，待 APP 实测 |
| 中文翻译和参数说明优化 | 本项目维护 | P2 | 不改默认值，只改菜单显示文字 |

## 当前主线已有但必须守住边界

| 功能 | 当前状态 | 守卫 |
| --- | --- | --- |
| 7000 Web 本地控制台 | `carrot_server.py` 默认 7000 端口，已有 dashcam、screenrecord、tools、Auto-Tuner 面板 | `scripts/personal/feature_boundary_check.py` 确认入口和关键文件仍存在 |
| AmapNavi 只读状态桥 | `app_navi_status.py` 默认关闭，只镜像 `carState` 车道线和原车盲区到 `amapNavi` | `scripts/personal/amap_navi_status_check.py` 和 `feature_boundary_check.py` 确认不接收命令、不接外设、不进变道逻辑 |
| cluster HUD / USB 小屏代码 | 当前代码树已有，manager 只在 `ClusterHud` 为 1 或 2 时启动 | `feature_boundary_check.py` 确认 `carrot_cluster` 仍由 `enable_cluster_hud` 控制 |
| 机械小哥数据广播 | 当前代码树已有 `xiaoge_data`，manager 只在 `ShareData` 开启时启动 | `feature_boundary_check.py` 确认不默认常驻 |

机器可重复盘点：

```bash
python3 scripts/personal/feature_status_report.py --strict
python3 scripts/personal/app_navi_overtake_audit.py
```

这个脚本把已静态具备、已有但需要实机验证、故意隔离和仍待迁移的功能分开列出。

## 单独实验分支评估

| 功能 | 来源 | 风险 | 计划 |
| --- | --- | --- | --- |
| fishop 完整 `amap_navi.py` | `fishop/openpilot:cp` | 中/高 | 与 CP搭子协议重叠，且耦合 4210-4213、7705/7706、盲区、外设和 APP 命令；只读状态桥已进主线，完整服务先放 `experimental/app-navi` |
| APP 外接转向灯控制 | `fishop/openpilot:cp` | 高 | 需要外置硬件和上车验证，不进默认分支 |
| `OVERTAKE` 命令 | `fishop/openpilot:cp` / `jixiexiaoge/navipilot:CPdazi` | 高 | APP 端已有状态机和 `LANECHANGE` 命令出口；设备端 `OVERTAKE` 需要独立开关、速度/盲区/车道条件保护 |
| modeld 模型选择器 | `ajouatom/openpilot:happymaj11r/carrot-wip-model_selector` | 高 | 已来源跟踪和静态审计；真正迁移放 `experimental/model-selector` |
| 哨兵 Web 服务 | `jixiexiaoge/openpilot:master` | 高 | 含固定 secret 和外部资源，只做隔离参考 |
| DEC / longcontrol 大改 | `fishop/openpilot:cp` | 高 | 已纳入来源审计和边界守卫；不影响 ESCC 前暂不碰 |

## 先放旁边

| 功能 | 来源 | 原因 |
| --- | --- | --- |
| C4 支持 | 上游/机械小哥相关分支 | 用户硬件不是 C4，维护成本可能高 |
| 非 Seltos 的车型特调 | fishop / jixie | 不影响用户主车时再处理 |
| dhvms 旧版整包代码 | `dhvms/carrotpilot` | 旧 CarrotPilot 参考线，只做历史参考 |
