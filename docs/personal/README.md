# Personal Project Notes

本目录记录个人 C3 / Kia Seltos 2023 / ESCC 整合计划。

## 先看

- [安装和回滚说明](INSTALL_AND_ROLLBACK.md)
- [当前代码改动记录](CODE_CHANGES.md)
- [以后更新检查单](UPDATE_CHECKLIST.md)
- [TODO 主计划](TODO.md)
- [机械小哥 atune 整合计划](ATUNE_INTEGRATION_PLAN.md)

## 背景

- [研究快照](RESEARCH_SNAPSHOT_2026-06-17.md)
- [分支策略](BRANCH_STRATEGY.md)
- [功能整合矩阵](FEATURE_MATRIX.md)
- [机械小哥 / fishop 功能边界](JIXIE_FISHOP_BOUNDARY.md)
- [Seltos 2023 车辆档案](VEHICLE_PROFILE_SELTOS_2023.md)
- [车型配置说明](CAR_CONFIG_EXPLAINER.md)
- [设备端快照采集](DEVICE_SNAPSHOT.md)
- [安装目标清单](INSTALL_TARGETS.json)
- [上车测试记录模板](ROAD_TEST_LOG_TEMPLATE.md)
- [来源和署名](SOURCES_AND_CREDITS.md)
- [GitHub 建仓计划](GITHUB_SETUP.md)

## 当前原则

- 底座跟随 `ajouatom/openpilot:c3-wip`。
- 用户主车优先：C3 克隆版、Kia Seltos 2023、纯 CAN。
- Seltos 2023 初期复用 Seltos 2021，不额外调转向或纵控默认值。
- ESCC 默认关闭，必须手动开启。
- Always Offline 默认开启，适配 ACC/CAN 供电和无法在线注册的使用方式。
- 机械小哥/fishop 其它功能分批迁移，每批可单独回滚。

## 本地检查

更新、合并或上车前先跑：

```bash
python3 scripts/personal/update_audit.py
python3 scripts/personal/smoke_check.py
```

上车前也可以单独跑更详细的 ESCC / 离线模式预检：

```bash
python3 scripts/personal/escc_offline_preflight.py
python3 scripts/personal/cplink_preflight.py
python3 scripts/personal/settings_cn_audit.py
python3 scripts/personal/install_target_check.py
```

`update_audit.py --fetch` 用于更新前检查三方来源是否有新提交、是否碰到高风险目录，以及本地 tracking 分支是否需要重新审查。

其它检查覆盖 Seltos 2023、ESCC、Always Offline、Auto-Tuner 默认安全状态、中文设置说明、设置 JSON、关键 Python/JS 语法、Auto-Tuner mock 回归、capnp/DBC/Params 关键依赖、CP搭子核心协议链路，以及仍需实车确认的项目。

安装目标以 [INSTALL_TARGETS.json](INSTALL_TARGETS.json) 为准：当前只有 `static` 预检 tag，没有 `stable` tag，所以日常稳定安装目标必须保持为空。

打安装 tag 前先跑：

```bash
python3 scripts/personal/release_gate.py --tag carrotpilot-c3-escc-YYYYMMDD-static1 --kind static --run-checks
```

`stable` tag 必须先填写上车测试记录，不能只靠静态检查。

在 C3 设备上采集当前参数和静态状态：

```bash
python3 scripts/personal/device_snapshot.py --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

## GitHub Actions

公开仓库有一个轻量工作流：

- `.github/workflows/personal-smoke.yml`
- 触发：推送到 `personal/c3-escc`、`personal/c3-escc-atune`，PR 到这些分支，或手动触发。
- 内容：运行 `smoke_check.py`、ESCC / Always Offline preflight、CP搭子 preflight。

Actions 通过只证明静态检查通过，不代表实车验证通过。
