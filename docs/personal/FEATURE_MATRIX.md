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
| 自动实验模式切换完整闭环 | 机械小哥 | P1 | 独立开关，后续单批迁移 |
| 模型选择切换器 | 机械小哥 | P1 | 独立开关 |
| 自动超车 | 机械小哥 / fishop | P2 | 后置验证 |
| LED / cluster HUD | 机械小哥 | P2 | 实验功能 |
| 驾驶报告 | `jixiexiaoge/navipilot:CPdazi` | P2 | APP 端功能；C3 端保持 WebSocket/CarrotMan 数据兼容，待 APP 实测 |
| 中文翻译和参数说明优化 | 本项目维护 | P2 | 不改默认值，只改菜单显示文字 |

## 当前主线已有但必须守住边界

| 功能 | 当前状态 | 守卫 |
| --- | --- | --- |
| 7000 Web 本地控制台 | `carrot_server.py` 默认 7000 端口，已有 dashcam、screenrecord、tools、Auto-Tuner 面板 | `scripts/personal/feature_boundary_check.py` 确认入口和关键文件仍存在 |
| cluster HUD / USB 小屏代码 | 当前代码树已有，manager 只在 `ClusterHud` 为 1 或 2 时启动 | `feature_boundary_check.py` 确认 `carrot_cluster` 仍由 `enable_cluster_hud` 控制 |
| 机械小哥数据广播 | 当前代码树已有 `xiaoge_data`，manager 只在 `ShareData` 开启时启动 | `feature_boundary_check.py` 确认不默认常驻 |

机器可重复盘点：

```bash
python3 scripts/personal/feature_status_report.py --strict
```

这个脚本把已静态具备、已有但需要实机验证、故意隔离和仍待迁移的功能分开列出。

## 单独实验分支评估

| 功能 | 来源 | 风险 | 计划 |
| --- | --- | --- | --- |
| fishop `amap_navi.py` | `fishop/openpilot:cp` | 中 | 与 CP搭子协议重叠，先放 `experimental/app-navi` |
| APP 外接转向灯控制 | `fishop/openpilot:cp` | 中/高 | 需要硬件和上车验证，不进默认分支 |
| `OVERTAKE` 命令 | `fishop/openpilot:cp` / `jixiexiaoge/navipilot:CPdazi` | 高 | 需要独立开关、速度/盲区/车道条件保护 |
| 哨兵 Web 服务 | `jixiexiaoge/openpilot:master` | 高 | 含固定 secret 和外部资源，只做隔离参考 |
| DEC / longcontrol 大改 | `fishop/openpilot:cp` | 高 | 不影响 ESCC 前暂不碰 |

## 先放旁边

| 功能 | 来源 | 原因 |
| --- | --- | --- |
| C4 支持 | 上游/机械小哥相关分支 | 用户硬件不是 C4，维护成本可能高 |
| 非 Seltos 的车型特调 | fishop / jixie | 不影响用户主车时再处理 |
| dhvms 旧版整包代码 | `dhvms/carrotpilot` | 旧 CarrotPilot 参考线，只做历史参考 |
