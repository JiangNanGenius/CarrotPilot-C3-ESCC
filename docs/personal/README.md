# Personal Project Notes

本目录记录个人 C3 / Kia Seltos 2023 / ESCC 整合计划。

## 先看

- [安装和回滚说明](INSTALL_AND_ROLLBACK.md)
- [从旧版本迁移安全参数](CONFIG_MIGRATION.md)
- [当前代码改动记录](CODE_CHANGES.md)
- [以后更新检查单](UPDATE_CHECKLIST.md)
- [TODO 主计划](TODO.md)
- [机械小哥 atune 整合计划](ATUNE_INTEGRATION_PLAN.md)

## 背景

- [研究快照](RESEARCH_SNAPSHOT_2026-06-17.md)
- [分支策略](BRANCH_STRATEGY.md)
- [功能整合矩阵](FEATURE_MATRIX.md)
- [机械小哥 / fishop 功能边界](JIXIE_FISHOP_BOUNDARY.md)
- [Navipilot APP 研究记录](NAVIPILOT_APP_RESEARCH.md)
- [Model Selector 研究记录](MODEL_SELECTOR_RESEARCH.md)
- [Seltos 2023 车辆档案](VEHICLE_PROFILE_SELTOS_2023.md)
- [车型配置说明](CAR_CONFIG_EXPLAINER.md)
- [设备端快照采集](DEVICE_SNAPSHOT.md)
- [安装目标清单](INSTALL_TARGETS.json)
- [上车测试记录模板](ROAD_TEST_LOG_TEMPLATE.md)
- [来源和署名](SOURCES_AND_CREDITS.md)
- [GitHub 建仓计划](GITHUB_SETUP.md)

## 当前原则

- 底座跟随 `ajouatom/openpilot:c3-wip`，当前按 CarrotPilot / CarPad 韩国主源处理。
- 用户主车优先：C3 克隆版、Kia Seltos 2023、纯 CAN。
- Seltos 2023 初期复用 Seltos 2021，不额外调转向或纵控默认值。
- ESCC 默认关闭，必须手动开启。
- Always Offline 默认开启，适配 ACC/CAN 供电和无法在线注册的使用方式。
- 机械小哥/fishop 其它功能分批迁移，每批可单独回滚。

## 本地检查

更新、合并或上车前先跑：

```bash
python3 scripts/personal/update_audit.py
python3 scripts/personal/upstream_update_plan.py
python3 scripts/personal/smoke_check.py
```

上车前也可以单独跑更详细的 ESCC / 离线模式预检：

```bash
python3 scripts/personal/escc_offline_preflight.py
python3 scripts/personal/cplink_preflight.py
python3 scripts/personal/feature_boundary_check.py
python3 scripts/personal/feature_status_report.py --strict
python3 scripts/personal/settings_cn_audit.py
python3 scripts/personal/localization_audit.py
python3 scripts/personal/install_target_check.py
python3 scripts/personal/release_integrity_check.py --self-test
python3 scripts/personal/seltos_profile_check.py
python3 scripts/personal/road_test_evidence_check.py --self-test
python3 scripts/personal/evidence_readiness_report.py --self-test
python3 scripts/personal/navipilot_live_check.py --self-test
python3 scripts/personal/model_selector_audit.py
python3 scripts/personal/upstream_update_plan.py --self-test
python3 scripts/personal/c3_static_check.py --output /tmp/carrotpilot-c3-escc-static-check.md --snapshot-output /tmp/carrotpilot-c3-escc-snapshot.md --allow-branch --skip-preflight
python3 scripts/personal/collect_real_car_evidence.py --output-dir /tmp/carrotpilot-c3-escc-evidence --allow-branch --skip-preflight --force
python3 scripts/personal/c3_commissioning.py --output-dir /tmp/carrotpilot-c3-escc-commissioning --allow-branch --skip-preflight --force
```

`update_audit.py --fetch` 用于更新前检查三方来源是否有新提交、是否碰到高风险目录，以及本地 tracking 分支是否需要重新审查。
`upstream_update_plan.py --fetch` 用于把这些更新转成可执行计划：哪些 tracking 分支可以快进、哪些来源触碰高风险目录、后续该跑哪些门禁。它默认只读，只有显式加 `--apply-tracking` 或 `--write-baselines` 才会改本地 tracking 分支或基准文件。

其它检查覆盖 Seltos 2023、ESCC、Always Offline、Auto-Tuner 默认安全状态、上游更新计划工具、功能边界守卫、功能状态报告、证据就绪度报告、模型选择器参考线审计、中文设置说明、设置 JSON、关键 Python/JS 语法、Auto-Tuner mock 回归、capnp/DBC/Params 关键依赖、CP搭子核心协议链路，以及仍需实车确认的项目。

如果要从当前可工作的 fishop / 飞扬版本迁移设置，使用：

```bash
python3 scripts/personal/params_migration.py export --output /data/media/0/carrotpilot-fishop-working-params.json
python3 scripts/personal/params_migration.py import --input /data/media/0/carrotpilot-fishop-working-params.json
```

第二条默认只是 dry-run，确认无误后才加 `--apply`。

刚安装到 C3 后，可以用首装向导一次性跑迁移 dry-run、静态检查、设备快照、证据包和 readiness 报告：

```bash
python3 scripts/personal/c3_commissioning.py \
  --migration-input /data/media/0/carrotpilot-fishop-working-params.json \
  --archive
```

`seltos_profile_check.py` 专门守住 Seltos 2023 当前策略：经典 CAN、复用 Seltos 2021 harness/specs/flags、不引入 CANFD/HDA2 特判、不复制未验证 FW fingerprint。

安装目标以 [INSTALL_TARGETS.json](INSTALL_TARGETS.json) 为准：当前有 `static` 预检 tag 和 `test` 受控上车测试 tag，没有 `stable` tag，所以日常稳定安装目标必须保持为空。

发布 GitHub release 后，可额外运行在线完整性检查，确认 manifest、安装脚本、远端安装分支、GitHub release 和两个安装资产一致：

```bash
python3 scripts/personal/release_integrity_check.py --online
```

打安装 tag 前先跑：

```bash
python3 scripts/personal/release_gate.py --tag carrotpilot-c3-escc-YYYYMMDD-static1 --kind static --run-checks
```

`stable` tag 必须先填写上车测试记录，不能只靠静态检查。

升 `stable` 前还必须把 C3 设备快照传给证据检查器：

```bash
python3 scripts/personal/road_test_evidence_check.py \
  --road-test-log docs/personal/road_tests/你的记录.md \
  --device-snapshot /path/to/carrotpilot-c3-escc-snapshot.md \
  --require-device-snapshot \
  --require-offline-process-guard \
  --require-power-cycle-boot \
  --require-escc-sample
```

如果使用一键证据采集器，可以直接传整个证据目录：

```bash
python3 scripts/personal/evidence_readiness_report.py \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS
```

```bash
python3 scripts/personal/road_test_evidence_check.py \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS \
  --require-device-snapshot \
  --require-carparams-summary \
  --require-offline-process-guard \
  --require-power-cycle-boot \
  --require-escc-sample
```

如果这次测 CP搭子 / Navipilot，可把 `--require-escc-sample` 换成或另加 `--require-cplink-sample`。如果证据包里也运行了 `--navipilot-check`，再加 `--require-navipilot-live-check`。
如果这次测只读 AmapNavi 状态桥，停车开启 `EnableAmapNaviStatus=1` 后采样，再额外加 `--require-amap-navi-sample`。

在 C3 设备上采集当前参数和静态状态：

```bash
python3 scripts/personal/device_snapshot.py --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

C3 安装后推荐直接跑：

```bash
python3 scripts/personal/c3_static_check.py --output /data/media/0/carrotpilot-c3-escc-static-check.md
```

如果准备实车验证，推荐用一键证据采集器生成同一个文件夹：

```bash
python3 scripts/personal/collect_real_car_evidence.py --archive
```

## GitHub Actions

公开仓库有一个轻量工作流：

- `.github/workflows/personal-smoke.yml`
- 触发：推送到 `personal/c3-escc`、`personal/c3-escc-atune`，PR 到这些分支，或手动触发。
- 内容：运行 `smoke_check.py`、ESCC / Always Offline preflight、CP搭子 preflight 和功能边界守卫。
- `smoke_check.py` 里也会运行功能状态报告，确认 7000 Web、实验模式开关、Auto-Tuner、CP搭子核心、cluster HUD gate、ShareData gate 和高风险隔离状态没有漂移。

公开仓库还有一个上游监控工作流：

- `.github/workflows/upstream-snapshot.yml`
- 名称：`Upstream Watch`
- 触发：每周自动运行，或手动触发。
- 内容：比较 [UPSTREAM_BASELINES.json](UPSTREAM_BASELINES.json) 中记录的已审查 commit 和对应三方远端最新分支。
- 如果工作流变红，通常表示上游有新提交或高风险目录变化，需要按 [以后更新检查单](UPDATE_CHECKLIST.md) 人工审查；这不是自动合并。

Actions 通过只证明静态检查通过，不代表实车验证通过。
