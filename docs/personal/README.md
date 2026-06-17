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
- [Seltos 2023 车辆档案](VEHICLE_PROFILE_SELTOS_2023.md)
- [车型配置说明](CAR_CONFIG_EXPLAINER.md)
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
python3 scripts/personal/smoke_check.py
```

上车前也可以单独跑更详细的 ESCC / 离线模式预检：

```bash
python3 scripts/personal/escc_offline_preflight.py
```

这些检查覆盖 Seltos 2023、ESCC、Always Offline、Auto-Tuner 默认安全状态、设置 JSON、关键 Python/JS 语法、Auto-Tuner mock 回归、capnp/DBC/Params 关键依赖，以及仍需实车确认的项目。
