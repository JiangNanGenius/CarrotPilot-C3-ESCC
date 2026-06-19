# 当前代码改动记录

## 2026-06-19: 新架构 alpha 安装入口和说明同步

改动内容：

- 脚本安装器 `--channel alpha` 从旧 `alpha-supercombo` 改为新架构短分支 `alpha-sunnypilot-c3`。
- 移除脚本安装器里的旧 `supercombo` alpha 别名，避免新架构线和旧模型实验线混用。
- `INSTALL_TARGETS.json` 的 alpha 入口改为 `experimental/sunnypilot-011-c3`、`alpha-sunnypilot-c3` 和 Pages `/x`。
- 安装和回滚说明明确 `/x` 只用于新架构停车/开发验证，`/i`、`latest`、稳定 release 和 `install-c3-escc-test` 不随 alpha 移动。
- README 补充新架构 alpha、主要功能状态、安装入口和云服务移除边界。
- 来源和署名补充 SunnyPilot 与 Mr.One C3 兼容参考。

刻意没有改：

- 没有移动 `latest` tag、`install-c3-escc-test` 分支或 release asset。
- 没有把 alpha 设为日常安装目标。
- 没有启用旧 `alpha-supercombo` 或最新模型实验线作为当前 alpha。

## 2026-06-18: 安装器增加 latest-model alpha 通道和代理更新规则

改动内容：

- 脚本安装器新增 `--channel alpha` / `experimental` / `supercombo`，指向短安装分支 `alpha-supercombo`。
- `alpha-supercombo` 作为 `experimental/latest-model-supercombo` 的二进制安装别名，避免安装器模板不支持带 `/` 分支名的问题。
- `alpha` 只用于官方 master 最新 `driving_supercombo` 模型运行栈实验，不作为默认安装目标。
- `docs/personal/LATEST_MODEL_SUPERCOMBO_LINE.md` 记录第三条线开法、C3/C3X/C4 的 `tici` / `tizi` / `mici` 区分和验证门禁。
- 根目录新增 `AGENTS.md`，记录以后按三方来源自动更新的策略、保护项、门禁和 release 规则。

刻意没有改：

- 没有移动 `latest` tag、`install-c3-escc-test` 分支或 release asset。
- 没有把 alpha 设为日常安装目标。
- 没有迁移 modeld/supercombo 代码到主线。

## 2026-06-18: 测速摄像头限速偏移改为可调

改动内容：

- 新增 `AutoNaviSpeedLimitOffset`，默认 `0`，用于测速摄像头/导航限速目标速度的固定 km/h 偏移。
- `AutoNaviSpeedSafetyFactor` 默认从 `105` 改为 `100`，保留为百分比比例：100 不加偏移，105 为 +5%，95 为 -5%。
- `carrot_serv.py` 统一测速摄像头目标速度计算：`限速 × 比例 + 固定偏移`。
- 删除 Waze/外部测速摄像头路径里的硬编码 `+5`。
- 原生 C3 设置页和 Web 设置表都暴露固定偏移和百分比比例。
- 安装器首启安全参数写入 `AutoNaviSpeedLimitOffset=0`、`AutoNaviSpeedSafetyFactor=100`，避免旧版本已持久化的 105% 继续生效。
- `smoke_check.py` 增加守卫，防止默认值或硬编码 `+5` 回退。
- 源码核对：fishop `cp` / `escc-cpv9`、ajouatom `carrot-wip` / `c3-wip`、jixiexiaoge `atune` 都有 `AutoNaviSpeedSafetyFactor=105` 或 Waze/外部测速路径 `offset = 5`；Navipilot APP 侧未发现把下发给 C3 的测速限速主动 `+5`。

刻意没有改：

- 没有改变 ESCC、Seltos 2023、Connect、AlwaysOffroad 或 panda safety 逻辑。
- 没有把道路限速巡航偏移 `AutoRoadSpeedLimitOffset` 当成测速摄像头偏移。

## 2026-06-18: 原生设置页补齐 AlwaysOffroad 入口

改动内容：

- 原生 C3 设置页 `Start` 分组新增 `AlwaysOffroad`，范围固定为 `0/1`。
- 原生 C3 设置页的 `EnableConnect` 范围收紧为 `0/1`，与设置表和后台逻辑一致。
- `smoke_check.py` 和 `escc_offroad_preflight.py` 增加守卫，防止原生设置页缺失 `AlwaysOffroad` 或把 `EnableConnect` 变成非二值状态。

刻意没有改：

- 没有改变 `AlwaysOffroad` 默认值，仍为 `0`。
- 没有把 `AlwaysOffroad` 当成官方 Connect 开关。
- 没有改变驾驶控制或 ESCC 逻辑。

## 2026-06-18: AlwaysOffroad / EnableConnect 语义修正

改动内容：

- `AlwaysOffroad` 默认保持 `0`，只保留为驻车供电更新、继电器调试或故障排查开关。
- `EnableConnect` 默认保持 `0`，并在关闭时跳过在线注册、阻止远程连接/上传相关进程启动。
- 设置页新增/明确“在线连接”开关说明，克隆 C3 默认不连接官方注册/远程连接服务。
- `stable` 证据要求改为 `--require-default-connect-guard`：默认快照需满足 `AlwaysOffroad=0`、`EnableConnect=0`，且不启动远程连接/上传。
- `--require-offroad-update-guard` 保留为手动开启 `AlwaysOffroad=1` 后的驻车更新/调试检查，要求 `IsOnroad=False` 且本地 Web/更新服务可见，不再作为默认 stable 必需项。
- `hardwared` 使用 `AlwaysOffroad` 强制保持 offroad；`pandad` 在该模式下把 panda 安全模式压到 `NO_OUTPUT`。

刻意没有改：

- 没有默认开启在线连接。
- 没有删除 AlwaysOffroad 功能。
- 没有把后台更新作为默认连接守卫的强制失败项；AlwaysOffroad 调试模式反而要求本地更新/Web 仍可见。
- 没有把 `AlwaysOffroad` 当成官方 Connect 开关；官方注册/远程连接只由 `EnableConnect` 控制。

## 2026-06-18: Navipilot 驾驶报告源码契约守卫

改动文件：

- `scripts/personal/cplink_preflight.py`
- `docs/personal/NAVIPILOT_APP_RESEARCH.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/TODO.md`

改动内容：

- `cplink_preflight.py` 新增 Navipilot APP 驾驶评分/报告源码契约检查。
- 守卫 `DrivingDataCollector.kt` 的采集入口、APP 本地存储、每秒更新字段、评分函数调用、今日/本周/全部会话读取。
- 守卫 `DrivingScoreEngine.kt` 的五维评分和总分权重：平稳性 30%、预判力 25%、接管依赖 20%、节能 15%、NOO 稳定度 10%。
- 守卫 `DrivingSession.kt`、`DrivingReportScreen.kt` 和 `DrivingReportShareImage.kt`，确认报告页、历史/成就/分享入口仍在 APP 侧。
- 文档补充：驾驶报告保存在 Android APP 的 `SharedPreferences`，不是 C3 端本地报告数据库；`leadDistance` 当前仍是 TODO/0f。

刻意没有改：

- 没有把 Android 驾驶报告 UI 搬进 C3 Web。
- 没有改变 C3 端驾驶控制、CP搭子协议或自动超车边界。
- 该守卫只证明 APP 参考源码契约未漂移，不替代手机 APP 实测。

## 2026-06-18: 模型选择器只读状态采集

改动文件：

- `scripts/personal/device_snapshot.py`
- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/evidence_readiness_report.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/MODEL_SELECTOR_RESEARCH.md`
- `docs/personal/TODO.md`

改动内容：

- 设备快照新增 `DrivingModelName`、`PendingModelName` 参数记录。
- 设备快照新增 `Model Selector Status` 表，读取 `/data/model_selector_status`，记录 engine、是否自定义 `carrot_modeld`、是否存在 pending 模型安装状态。
- 默认主线没有模型选择器状态文件时显示 `model_selector_engine=default_upstream_assumed`，表示继续使用内置 upstream modeld。
- `road_test_evidence_check.py` 新增可选 `--require-model-selector-status`，要求状态字段存在且没有 pending 模型安装/重启状态。
- `evidence_readiness_report.py` 新增可选阶段 `Model selector status`。
- `smoke_check.py` 检查 C3 静态 dry-run 快照必须包含模型选择器只读字段。

刻意没有改：

- 没有启用模型下载、安装、编译、Web 模型页或 `modeld_runner`。
- 没有把模型选择器作为 stable 必需项。
- 没有改变默认模型；这只是后续实验分支和上车排查用的证据口子。

## 2026-06-18: AlwaysOffroad 更新/调试证据守卫

改动文件：

- `scripts/personal/device_snapshot.py`
- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/evidence_readiness_report.py`
- `scripts/personal/release_gate.py`
- `scripts/personal/collect_real_car_evidence.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/README.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- 设备快照新增 `Process Summary`，机器可读地记录关键进程是否出现。
- 新增 `process_snapshot_available`、`updated_process_seen`、`connect_process_seen`、`uploader_process_seen` 和 `connect_forbidden_processes_seen` 字段。
- `road_test_evidence_check.py` 新增 `--require-offroad-update-guard`，要求 `AlwaysOffroad=1`、`IsOnroad=False`、可读取进程列表，且本地 Web/更新服务可见。
- 后续已修正：`evidence_readiness_report.py` 的 stable 必需阶段改为默认连接守卫，`AlwaysOffroad update/debug guard` 只保留为调试检查。
- 后续已修正：`release_gate.py --kind stable` 自动要求 `--require-default-connect-guard`。
- 证据包和文档更新 stable 校验命令，避免 C3 克隆版 ACC/CAN 断电使用场景漏掉 Connect / AlwaysOffroad 证据。

刻意没有改：

- 没有改 manager 启动逻辑。
- 后续已修正：AlwaysOffroad 默认改为 `0`。
- 没有用进程名判断替代实车 ACC/CAN 断电重启验证；断电重启仍需人工实际确认。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static25`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test17`

含义：

- 包含 AlwaysOffroad 更新/调试证据守卫，静态检查通过，不代表实车断电重启或稳定版本。

## 2026-06-18: AmapNavi 只读状态桥实机采样证据

改动文件：

- `scripts/personal/device_snapshot.py`
- `scripts/personal/c3_static_check.py`
- `scripts/personal/collect_real_car_evidence.py`
- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/evidence_readiness_report.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/README.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `README.md`

改动内容：

- 设备快照新增 `EnableAmapNaviStatus` 安全参数记录。
- `device_snapshot.py --sample-seconds` 现在同时采样 `amapNavi`，记录 `amapNavi_updates`、`amap_navi_updates_seen`、车道线/盲区是否出现和 `last_amapNavi` 摘要。
- `c3_static_check.py` 停车默认参数检查增加 `EnableAmapNaviStatus=0`。
- `road_test_evidence_check.py` 新增可选 `--require-amap-navi-sample`，要求停车采样里 `EnableAmapNaviStatus=1` 且 `amapNavi_updates > 0`。
- `evidence_readiness_report.py` 新增可选阶段 `AmapNavi status bridge sample`，不作为 stable 必需项。
- 证据包 README、设备快照文档、更新检查单和功能矩阵补充 AmapNavi 停车采样流程。

刻意没有改：

- 没有改变 `app_navi_status.py` 的运行逻辑。
- 没有把 `EnableAmapNaviStatus` 默认改成开启。
- 没有把 AmapNavi 样本变成 stable 必需项。
- 没有引入 APP 命令、外接转向灯、自动超车或 desire helper 接入。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static24`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test16`

含义：

- 包含只读 AmapNavi 状态桥的设备端采样和可选证据校验，静态检查通过，不代表实车验证或稳定版本。

## 2026-06-18: 上游更新计划工具

改动文件：

- `scripts/personal/upstream_update_plan.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/BRANCH_STRATEGY.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/README.md`
- `docs/personal/TODO.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `README.md`

改动内容：

- 新增 `upstream_update_plan.py`，用于本地更新前生成可执行计划。
- 默认只读输出每条来源的 local/remote commit、状态、remote ahead 数量、新提交标题、高风险文件和建议命令。
- 支持 `--fetch` 拉取来源远端。
- 支持 `--apply-tracking`，只在本地 tracking ref 严格落后时快进 `upstream/*` / `tracking/*`，不自动合并个人上车分支。
- 支持 `--write-baselines`，审查完成后从本地 tracking ref 重写 `UPSTREAM_BASELINES.json`，给 GitHub Actions `Upstream Watch` 使用。
- 支持 `--self-test` 并纳入 `smoke_check.py`。
- 更新维护文档，把以后更新流程拆成：先审计、再看计划、审查后快进 tracking、跑门禁、最后更新基准。

刻意没有改：

- 没有自动 rebase 或 merge `personal/c3-escc-atune`。
- 没有自动推送到设备安装目标。
- 没有把上游更新直接视为可上车版本。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static23`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test15`

含义：

- 包含上游更新计划工具，静态检查通过，不代表实车验证或稳定版本。

## 2026-06-18: AmapNavi 只读状态桥

改动文件：

- `cereal/custom.capnp`
- `cereal/log.capnp`
- `cereal/services.py`
- `common/params_keys.h`
- `system/manager/process_config.py`
- `selfdrive/carrot/app_navi_status.py`
- `selfdrive/carrot_settings.json`
- `scripts/personal/amap_navi_status_check.py`
- `scripts/personal/feature_boundary_check.py`
- `scripts/personal/app_navi_overtake_audit.py`
- `scripts/personal/feature_status_report.py`
- `scripts/personal/settings_cn_audit.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `README.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`

改动内容：

- 新增 `AmapNavi` custom schema 和 `amapNavi` service，复用 fishop 兼容字段：左右盲区、车道线有效、左右车道线类型。
- 新增 `selfdrive/carrot/app_navi_status.py`，只读取 `carState`，把原车盲区和车道线状态发布为 `amapNavi`。
- 新增 `EnableAmapNaviStatus` 参数和设置项，默认关闭。
- manager 只在 `EnableAmapNaviStatus` 开启时启动 `app_navi_status`。
- 新增 `amap_navi_status_check.py`，确认该桥只读、默认关闭、不接收 APP 命令、不控制外接转向灯、不启用自动超车、不接入 `desire_helper`。
- 更新功能边界守卫：允许只读状态桥，继续禁止 fishop 完整 `amap_navi.py`、`OVERTAKE`、外接转向灯、lidar 盲区和 DEC/longcontrol 进入默认主线。

刻意没有改：

- 没有复制 fishop 完整 `selfdrive/carrot/amap_navi.py`。
- 没有开启 APP 命令控制。
- 没有引入外接转向灯控制。
- 没有把 `amapNavi` 接入 `desire_helper` 或变道逻辑。
- 没有启用 `OVERTAKE`。
- 没有引入 DEC / longcontrol 大改。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static22`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test14`

含义：

- 包含只读 AmapNavi 状态桥，静态检查通过，不代表手机 APP 实测、AmapNavi 完整功能或实车验证完成。

## 2026-06-18: 中文设置说明第三批

改动文件：

- `selfdrive/carrot_settings.json`
- `scripts/personal/settings_cn_audit.py`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- 继续只修改中文显示字段，不修改参数名、范围、默认值或控制逻辑。
- 清理巡航、ATC、纵向增益、巡航按键模拟、动能回收拨片、自动巡航轻点油门、HDP、低速转向、关机时间、驾驶员监控、道路限速调整、路径显示和跟车时间说明。
- 把容易误解的 `胡萝卜巡航`、`HKG 推荐`、`GasTab`、`smdps`、`TimeFollow`、`t_follow` 等中文展示改成更明确的用车描述。
- 扩展 `settings_cn_audit.py`，把第三批关键说明加入审计，防止后续更新退化。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static21`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test13`

含义：

- 包含第三批中文设置说明优化，静态检查通过，不代表实车验证或稳定版本。

## 2026-06-18: AmapNavi / 自动超车 / DEC 来源审计

分支：

- `personal/c3-escc-atune`

主要来源：

- `fishop/openpilot:cp`
- `jixiexiaoge/navipilot:CPdazi`

改动文件：

- `scripts/personal/app_navi_overtake_audit.py`
- `scripts/personal/smoke_check.py`
- `scripts/personal/feature_status_report.py`
- `scripts/personal/feature_boundary_check.py`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `README.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `.github/workflows/personal-smoke.yml`

改动内容：

- 新增 AmapNavi / 自动超车 / DEC 来源审计脚本。
- 审计 fishop 侧 `amap_navi.py`、`amapNavi` schema/service、外接转向灯、lidar 盲区、`OVERTAKE`、DEC/longcontrol 参考源。
- 审计 Navipilot APP 侧 `AutoOvertakeManager.kt`、7705/7706 网络通道和 `LANECHANGE` 命令出口。
- 检查当前默认 C3 主线没有半截引入 `amap_navi.py`、`amapNavi`、外接转向灯参数、lidar 盲区参数、`OVERTAKE` 或 DEC/longcontrol 接入点。
- 将新审计接入总 smoke、功能状态报告和更新检查单。
- GitHub Actions `Personal Smoke` 补抓 `fishop/cp`，避免云端缺少来源参考线时误报失败。
- 明确 P4 决策：ESCC 保留主线默认关闭；CP搭子核心协议保留主线；fishop AmapNavi、外接转向灯、lidar/侧向盲区、APP 自动超车和 DEC/longcontrol 放实验分支或暂缓。

刻意没有改：

- 没有把 fishop `amap_navi.py` 复制进默认主线。
- 没有启用 APP 外接转向灯控制。
- 没有启用 `OVERTAKE`。
- 没有引入 DEC / longcontrol 大改。
- 没有改变 Seltos 2023、ESCC、AlwaysOffroad 或 Auto-Tuner 默认行为。

待后续：

- 如要迁移 AmapNavi，先新开 `experimental/app-navi`。
- 如要迁移自动超车，先新开 `experimental/auto-lanechange`，并补独立开关、停车态检查、低速验证和回滚策略。
- DEC / longcontrol 等 ESCC 和 Seltos 实车表现稳定后再评估。

## 2026-06-17: 新增 Kia Seltos 2023

项目：

- `CarrotPilot-C3-ESCC`

改动文件：

- `opendbc_repo/opendbc/car/hyundai/values.py`

改动内容：

- 新增 `CAR.KIA_SELTOS_2023`。
- 显示名为 `Kia Seltos 2023`。
- 直接复用 `KIA_SELTOS` 的基础配置：
  - `CarHarness.hyundai_a`
  - `mass=1337`
  - `wheelbase=2.63`
  - `steerRatio=14.56`
  - `HyundaiFlags.CHECKSUM_CRC8`
- 将 `CAR.KIA_SELTOS_2023` 加入 ABS 非必要 ECU 列表，保持和 `CAR.KIA_SELTOS` 一致。

刻意没有改：

- 没有改 Seltos 2021。
- 没有改 DBC。
- 没有改转向参数。
- 没有改纵控参数。
- 没有设置 CANFD。
- 没有设置 HDA2。
- 没有复制 FW fingerprint；等拿到 Seltos 2023 实车 dump 后再补。

验证：

- `py_compile` 语法检查通过。
- 已安装最小本地验证依赖：`numpy`、`pycapnp`。
- 完整导入检查通过。
- `CAR.KIA_SELTOS_2023` 可读取。
- `CAR.KIA_SELTOS_2023` 与 `CAR.KIA_SELTOS` 的 specs、flags、DBC 完全一致。
- `CANFD=False`，`HDA2=False`，`CRC8=True`。

## 2026-06-17: ESCC 最小补丁

项目：

- `CarrotPilot-C3-ESCC`

主要来源：

- `fishop/openpilot:cp`

改动文件：

- `common/params_keys.h`
- `cereal/car.capnp`
- `opendbc_repo/opendbc/car/car.capnp`
- `opendbc_repo/opendbc/dbc/hyundai_kia_generic.dbc`
- `opendbc_repo/opendbc/car/hyundai/values.py`
- `opendbc_repo/opendbc/car/hyundai/interface.py`
- `opendbc_repo/opendbc/car/hyundai/radar_interface.py`
- `opendbc_repo/opendbc/car/hyundai/carstate.py`
- `opendbc_repo/opendbc/car/hyundai/carcontroller.py`
- `opendbc_repo/opendbc/car/hyundai/hyundaican.py`
- `opendbc_repo/opendbc/safety/safety/safety_hyundai_common.h`
- `selfdrive/carrot_settings.json`

改动内容：

- 新增 `EnableEscc` 参数，默认关闭。
- 新增 `spFlags`，用于保存 ESCC 这类 Carrot/sunnypilot 兼容标志。
- 新增 Hyundai ESCC 标志，避免 ESCC 模式下继续向 SCC ECU 发送禁用消息。
- panda safety 仍保持 0x7D0 诊断消息限制，不为 ESCC 放宽诊断发送边界。
- DBC 中补入 `ESCC` 0x2AB 消息。
- ESCC 开启且实车指纹检测到 0x2AB 时，启用 ESCC lead/AEB 状态读取。
- radar interface 增加 ESCC lead 点。
- carstate 增加 ESCC AEB/FCW 状态缓存。
- 纵控消息保留 ESCC 读取到的 AEB 状态。
- 设置菜单加入“启用 ESCC 硬件”。

刻意没有改：

- 没有默认开启 ESCC。
- 没有把 Seltos 2023 改成 CANFD 或 HDA2。
- 没有整包合并 fishop 分支。
- 没有合并 fishop 的 APP、导航、转向灯板和其它非 ESCC 功能。

待实车验证：

- 开启 `EnableEscc=1` 后，确认 C3 能稳定看到 0x2AB。
- 确认 ESCC lead 距离、相对速度和 AEB 状态显示正常。
- 确认不会触发 SCC/AEB 相关故障。

## 2026-06-17: AlwaysOffroad 模式

改动文件：

- `common/params_keys.h`
- `system/manager/manager.py`
- `system/manager/process_config.py`
- `system/athena/registration.py`
- `selfdrive/car/car_specific.py`
- `selfdrive/carrot_settings.json`

改动内容：

- 新增 `AlwaysOffroad` 参数；后续已修正为默认关闭。
- 设置菜单加入强制 Offroad相关开关。
- 后续已修正：官方在线注册/远程连接由 `EnableConnect` 控制，不由 `AlwaysOffroad` 控制。
- 后续已修正：`AlwaysOffroad=1` 时保持 offroad 和 panda no-output，本地 Web/SSH/更新仍应可用。
- 新增 `EnableConnect` 参数，默认关闭，避免未定义参数被写入。

用途：

- 适配 C3 中国克隆版、ACC/CAN 供电、熄火直接断电、无法注册 openpilot/comma 账号的使用方式。

待实车验证：

- 开机不再卡注册。
- 断电重启后能直接进入系统。
- `AlwaysOffroad=1` 时保持 offroad，本地 Web/更新可用，且不进入驾驶控制/继电器输出路径。

## 2026-06-17: Auto-Tuner 第一批实验接入

分支：

- `personal/c3-escc-atune`

主要来源：

- `jixiexiaoge/openpilot:atune`

改动文件：

- `selfdrive/carrot/carrot_learning.py`
- `selfdrive/carrot/carrot_functions.py`
- `common/params_keys.h`
- `selfdrive/carrot_settings.json`

改动内容：

- 新增轻量 Auto-Tuner 学习器。
- 学习器默认关闭，必须手动开启 `CarrotLearningActive`。
- 开启后记录加速、刹车、跟车距离和转向接管模式。
- 停车后生成 `CarrotLearningRecommend` 推荐数据。
- 推荐值和实际控制参数分开保存。
- 补齐 `CarrotLearningAutoApply`、`CarrotTunerApplyLat`、`CarrotTunerApplyLong`、`CarrotTunerFactoryReset` 等保护参数。
- `CarrotPlanner` 里加入 guarded hook，学习器异常不会让 planner 崩溃。
- 设置菜单新增“自动调参”分组。

刻意没有改：

- 没有整包合并 `jixiexiaoge/openpilot:atune`。
- 没有加入 Web 控制台、地图、cluster HUD、USB 小屏、视觉诊断、Tesla 或 CANFD/HDA2 无关功能。
- 没有默认开启学习。
- 没有默认自动应用推荐。
- 没有改变 Seltos 2023、ESCC、AlwaysOffroad 的默认行为。

验证：

- `git diff --check` 通过。
- `python3 -m json.tool selfdrive/carrot_settings.json` 通过。
- `python3 -m py_compile selfdrive/carrot/carrot_learning.py selfdrive/carrot/carrot_functions.py` 通过。
- mock smoke 通过：默认关闭时不写 `CarrotLearningData`；开启学习后能生成推荐；不会直接修改 `CruiseMaxVals4`。

待后续：

- 上车前先只开启学习，不开启自动应用。

## 2026-06-17: Auto-Tuner 手动确认闭环

分支：

- `personal/c3-escc-atune`

改动文件：

- `selfdrive/carrot/server/services/carrot_learning.py`
- `selfdrive/carrot/server/features/carrot_learning.py`
- `selfdrive/carrot/server/features/params.py`
- `selfdrive/carrot/server/features/__init__.py`
- `selfdrive/carrot/web/js/pages/setting.js`
- `selfdrive/carrot/web/js/shared/api.js`
- `selfdrive/carrot/web/css/pages/settings/base.css`
- `selfdrive/carrot/carrot_learning.py`
- `common/params_keys.h`
- `selfdrive/carrot_settings.json`

改动内容：

- 新增 `/api/carrot_learning`，用于读取待处理推荐。
- 新增 `/api/carrot_learning` POST action：
  - `apply`: 手动应用推荐。
  - `ignore`: 忽略当前推荐。
  - `clear`: 清空学习数据和推荐。
- 应用推荐时检查 `IsOnroad`，行驶中拒绝写入控制参数。
- 设置页“自动调参”分组顶部新增推荐面板。
- 推荐面板显示参数名、当前值、建议值和变化量。
- 推荐面板提供应用、忽略、清空按钮。
- 普通参数写入接口拦截 `CarrotLearningApply`、`CarrotLearningIgnore`、`CarrotLearningClear`，让普通设置页的一次性开关也能真正执行动作。
- 学习器自身也支持 `CarrotLearningApply`、`CarrotLearningIgnore` 一次性开关。

验证：

- `git diff --check` 通过。
- `python3 -m json.tool selfdrive/carrot_settings.json` 通过。
- `py_compile` 通过：
  - `selfdrive/carrot/carrot_learning.py`
  - `selfdrive/carrot/carrot_functions.py`
  - `selfdrive/carrot/server/services/carrot_learning.py`
  - `selfdrive/carrot/server/features/carrot_learning.py`
  - `selfdrive/carrot/server/features/params.py`
  - `selfdrive/carrot/server/features/__init__.py`
- `node --check` 通过：
  - `selfdrive/carrot/web/js/pages/setting.js`
  - `selfdrive/carrot/web/js/shared/api.js`
- mock smoke 通过：
  - 学习器一次性 apply/ignore 开关。
  - Web 服务手动应用推荐。
  - 行驶中拒绝应用推荐。

待实车验证：

- Web 设置页能显示 Auto-Tuner 推荐面板。
- 停车状态下应用推荐能正确写入参数。
- 行驶中应用推荐会被拒绝。

## 2026-06-17: 个人版 smoke 检查脚本

新增文件：

- `scripts/personal/smoke_check.py`
- `scripts/personal/escc_offroad_preflight.py`

用途：

- 更新、合并或上车前一键检查个人版关键保护项。
- 覆盖 Seltos 2023 独立车型、ESCC、AlwaysOffroad、Auto-Tuner 默认安全状态、设置 JSON、Python/JS 语法和 Auto-Tuner mock 回归。
- 单独 preflight 检查 ESCC / AlwaysOffroad 的 capnp、DBC、Params key、设置默认值、Seltos 2023 非 CANFD/HDA2 路径、ESCC 0x2AB 解析链路、EnableConnect 注册守卫和 AlwaysOffroad 本地更新/继电器安全链路。
- preflight 明确保留实车待验证项，不把静态检查当成路测结论。

验证：

- `python3 scripts/personal/escc_offroad_preflight.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-17: GitHub 公开仓库建立

仓库：

- `https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC`

本地远端：

- `github`

已推送分支：

- `personal/c3-escc`
- `personal/c3-escc-atune`

仓库设置：

- 公开仓库。
- 默认分支：`personal/c3-escc-atune`。
- topic：`carrotpilot`, `openpilot`, `c3`, `seltos`, `escc`。

说明：

- GitHub CLI 凭据保存在本机 keyring，不写入代码仓库。
- 推送前已确认项目文件中没有个人 GitHub token。
- 设备安装仍建议使用经过验证的 tag，不直接长期安装日常开发分支。

## 2026-06-17: 同步最新 C3 底座

上游：

- `ajouatom/openpilot:c3-wip`
- 新底座 commit：`244b69b6 Restore AutoGasCancelSpeed param key`

改动内容：

- 将 `upstream/c3-wip` 更新到最新 `origin/c3-wip`。
- 将 `personal/c3-escc` 变基到最新 C3 底座。
- 将 `personal/c3-escc-atune` 继续变基到新的 `personal/c3-escc`。
- 保留 ESCC、AlwaysOffroad、Seltos 2023 和 Auto-Tuner 改动。

验证：

- `python3 scripts/personal/escc_offroad_preflight.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-17: CP搭子 / fishop 功能边界

新增文件：

- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `scripts/personal/cplink_preflight.py`

改动内容：

- 建立 `tracking/jixie-master`，跟踪 `jixiexiaoge/openpilot:master`。
- 记录机械小哥 `master` 是 CP搭子 / Navipilot 应用和说明方向，不是 openpilot 整包代码线。
- 记录当前分支已具备 CarrotMan / CPlink 核心协议静态兼容：
  - `carrotMan`
  - `navInstructionCarrot`
  - UDP 7705 / 7706
  - 限速、TBT、SDI、GPS、`LANECHANGE`。
- 记录 fishop `amap_navi.py`、APP 外接转向灯、`OVERTAKE`、盲区/雷达、DEC/longcontrol 等功能必须单独分支迁移。
- 将 `cplink_preflight.py` 接入 `scripts/personal/smoke_check.py`。

验证：

- `python3 scripts/personal/cplink_preflight.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-17: 上游更新审计工具

新增文件：

- `scripts/personal/update_audit.py`

改动内容：

- 增加本地维护审计脚本，用于更新前检查：
  - 当前分支是否仍包含 `origin/c3-wip` 和 `personal/c3-escc`。
  - `upstream/c3-wip`、`tracking/c4`、`tracking/jixie-atune`、`tracking/jixie-master`、`tracking/fishop-cp` 是否落后对应远端。
  - 新提交是否触碰 Hyundai、DBC、panda safety、params、cereal、controls、carrot、manager 等高风险目录。
- 支持 `--fetch`，需要联网时先拉取各来源再审计。
- 将脚本加入 `smoke_check.py` 的 Python 语法检查。
- 在 README、分支策略和更新检查单中加入使用入口。

验证：

- `python3 scripts/personal/update_audit.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-17: 发布 gate 和上车记录模板

新增文件：

- `scripts/personal/release_gate.py`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`

改动内容：

- 增加发布前 gate，统一检查 tag 命名、干净工作区、上游底座包含关系、ESCC/离线保护线、个人 token 扫描、旧仓库名扫描。
- 支持 `static`、`test`、`stable` 三类 tag。
- `static` / `test` 明确不代表实车验证。
- `stable` 必须提供上车测试记录，并包含 Seltos 实车、ACC 断电启动、ESCC 0x2AB、低速路测和回滚目标的 `PASS` 结论行。
- 将 release gate 加入 smoke 的 Python 语法检查。
- 更新安装说明、更新检查单和 TODO。

验证：

- `python3 scripts/personal/release_gate.py --tag carrotpilot-c3-escc-20260617-static1 --kind static --run-checks` 通过后，才能创建当前静态测试 tag。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260617-static1`
- `carrotpilot-c3-escc-20260617-static2`
- 含义：静态检查通过，不代表实车验证或稳定版本。

## 2026-06-17: 中文设置说明第一批

新增文件：

- `scripts/personal/settings_cn_audit.py`

改动内容：

- 只修改 `selfdrive/carrot_settings.json` 的中文显示字段 `cgroup` / `ctitle` / `cdescr`，不修改参数名、范围、默认值或控制逻辑。
- 第一批补充启动、现代/起亚、雷达、纵控、转向和外部 HUD 中容易误解的说明。
- 给 ESCC、CANFD/HDA2、Camera SCC、雷达轨迹、角雷达、AlwaysOffroad、车门/安全带屏蔽等高风险项补充适用车型、默认建议和风险提示。
- 补齐中文字段中的空说明，并将部分英文残留改为中文。
- 将中文设置审计接入 `scripts/personal/smoke_check.py`。

验证：

- `python3 scripts/personal/settings_cn_audit.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260617-static2`
- 含义：包含第一批中文设置说明优化，静态检查通过，不代表实车验证或稳定版本。

## 2026-06-17: 公开仓库首页整理

改动内容：

- 将根 README 开头改为 `CarrotPilot-C3-ESCC` 项目说明。
- 明确当前目标硬件和车型：C3 中国克隆版、Kia Seltos 2023、纯 CAN。
- 明确当前功能状态：ESCC 默认关闭、AlwaysOffroad 后续修正为默认关闭、EnableConnect 默认关闭、Auto-Tuner 默认关闭、CP搭子核心协议静态兼容但 APP 未实测。
- 标出当前可参考 `static` tag：`carrotpilot-c3-escc-20260617-static2`，并说明它不是稳定版。
- 在首页保留 ajouatom、fishop / 飞扬（码上飞扬，名称待确认）、机械小哥 / JixieXiaoGe、dhvms 的来源署名。
- 标明上游 README 中的 `openpilot.comma.ai` 是官方 openpilot 安装入口，不是本个人分支安装目标。
- 在安装说明中加入当前 `static2` tag 和“没有 stable tag”的状态。

验证：

- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-17: GitHub Actions 个人静态检查

新增文件：

- `.github/workflows/personal-smoke.yml`

改动内容：

- 新增轻量 GitHub Actions 工作流 `Personal Smoke`。
- 触发范围限制在 `personal/c3-escc`、`personal/c3-escc-atune`、对应 PR 和手动触发。
- 使用 `actions/checkout@v6`、`actions/setup-python@v6`、`actions/setup-node@v6` 和 Node.js 24，避免 Node 20 退役警告。
- 工作流会补齐个人脚本需要的 `personal/c3-escc`、`origin/c3-wip`、`jixie/master` / `tracking/jixie-master` 参考 ref。
- 运行 `scripts/personal/smoke_check.py`、`scripts/personal/escc_offroad_preflight.py --no-manual` 和 `scripts/personal/cplink_preflight.py --no-manual`。
- README 和更新检查单增加 Actions 说明。

验证：

- `python3 scripts/personal/smoke_check.py` 本地通过。
- 推送后需要确认 GitHub Actions `Personal Smoke` 通过。

## 2026-06-17: C3 设备端快照采集

新增文件：

- `scripts/personal/device_snapshot.py`
- `docs/personal/DEVICE_SNAPSHOT.md`

改动内容：

- 增加设备端只读快照脚本，用于在 C3 上记录当前分支、commit、tag、安全参数、关键二进制参数 hash、相关进程状态。
- 默认不采集 VIN、dongle id、token、路线 id 或完整 `/data/params`。
- 支持 `--sample-seconds`，停车时可短时间统计 CAN 里的 ESCC `0x2AB` 和 CP搭子 / Navipilot 的 `carrotMan`、`navInstructionCarrot` 更新次数。
- 将脚本加入 `smoke_check.py` 的 Python 语法检查。
- 在 README、安装说明、更新检查单和上车测试模板里加入设备快照步骤。

验证：

- `python3 scripts/personal/device_snapshot.py` 本地可运行。
- `python3 scripts/personal/smoke_check.py` 通过。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260617-static3`
- 含义：包含设备端快照采集脚本，静态检查通过，不代表实车验证或稳定版本。

## 2026-06-17: 安装目标清单和回滚护栏

新增文件：

- `docs/personal/INSTALL_TARGETS.json`
- `scripts/personal/install_target_check.py`

改动内容：

- 增加机器可检查的安装目标清单，记录当前 `static` tag、未来 `stable` tag、上一稳定 tag 和回滚底座。
- 当前还没有完成实车验证，所以 `daily_install_target` 必须保持为空。
- `stable` 发布后必须把 `daily_install_target` 指向 `current_stable_tag`，不能指向开发分支。
- 没有首个 `stable` 前，回滚底座先保留为 `origin/c3-wip`。
- 检查脚本会验证 tag 命名、tag 是否存在、tag 是否在当前分支历史里、回滚 ref 是否存在，以及 stable 路测记录是否齐全。
- 将安装目标检查接入 `scripts/personal/smoke_check.py`。
- 在安装说明、更新检查单和 TODO 中加入安装目标清单维护步骤。

验证：

- `python3 scripts/personal/install_target_check.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: CI tag refresh for release manifests

改动文件：

- `.github/workflows/personal-smoke.yml`
- `scripts/personal/install_target_check.py`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/CODE_CHANGES.md`

改动内容：

- `Personal Smoke` 在运行个人 smoke 前显式刷新 GitHub release tags，减少发布 commit 先触发、release tag 后到达导致的无意义红灯。
- `install_target_check.py` 在本地 tag 缺失时自动从 `origin` 补 fetch 一次 tags，再严格解析 `current_static_tag`、`current_test_tag`、`current_stable_tag`。
- 保留 `CARROTPILOT_PENDING_RELEASE_TAG` 给本地 release gate 使用；stable tag 仍必须真实存在，并且 stable 证据门槛不放松。
- 更新发布检查单，说明 CI 会主动刷新 tags，极端竞态下再复跑失败 job。

验证：

- `python3 scripts/personal/install_target_check.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: Release integrity checker

改动文件：

- `scripts/personal/release_integrity_check.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/README.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/CODE_CHANGES.md`

改动内容：

- 新增 release 完整性检查脚本，默认检查 `INSTALL_TARGETS.json`、当前 test tag 和安装脚本 `DEFAULT_REF` 是否一致。
- `--online` 模式会额外检查远端 `install-c3-escc-test` 分支是否指向当前 test tag commit、GitHub release 是否存在且为 prerelease、`installer_c3_escc` 和 `install_c3_escc.sh` 两个资产是否存在且大小/类型有效。
- 将脚本 self-test 纳入 `smoke_check.py`，避免普通 CI 依赖 GitHub API。
- 更新发布检查单，要求 release 发布后运行 `release_integrity_check.py --online`。

验证：

- `python3 scripts/personal/release_integrity_check.py --self-test` 通过。
- `python3 scripts/personal/release_integrity_check.py` 通过。
- `python3 scripts/personal/release_integrity_check.py --online` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: Installer first-boot note

改动文件：

- `scripts/personal/install_c3_escc.sh`
- `scripts/personal/smoke_check.py`
- `README.md`
- `docs/personal/BINARY_INSTALLER_RESEARCH.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/TODO.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/CODE_CHANGES.md`

改动内容：

- 安装脚本默认写入 `/data/media/0/carrotpilot-c3-escc-first-boot.txt`。
- 将当前受控上车测试目标更新为 `carrotpilot-c3-escc-20260618-test23`，让新安装包直接包含首启说明文件。
- 首启说明记录安装 ref、仓库、安全默认参数、首装向导命令、旧版本参数迁移命令和 ESCC 0x2AB 证据采集命令。
- 新增 `--first-boot-note PATH` 和 `--no-first-boot-note`，便于调试或关闭提示文件。
- `smoke_check.py` 增加安装脚本首启说明守卫，防止以后删掉上车提示。

验证：

- `sh -n scripts/personal/install_c3_escc.sh` 通过。
- `scripts/personal/install_c3_escc.sh --dry-run --force ...` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-17: Seltos 2023 车型复用护栏

新增文件：

- `scripts/personal/seltos_profile_check.py`

改动内容：

- 增加 Seltos 2023 专项静态检查，防止后续更新合并时把用户主车路径改歪。
- 检查 `CAR.KIA_SELTOS_2023` 仍使用经典 CAN `HyundaiPlatformConfig`，不能变成 `HyundaiCanFDPlatformConfig`。
- 检查 Seltos 2023 的 harness、物理参数和 flags 仍与 `CAR.KIA_SELTOS` 完全一致。
- 检查 Seltos 2023 不默认设置 CANFD、HDA2、Camera SCC、Radar SCC 相关 flag。
- 检查当前没有复制未经实车 FW dump 证明的 Seltos 2023 fingerprint。
- 检查 Hyundai 目录里没有新增未审查的 `KIA_SELTOS_2023` 特判引用。
- 将脚本接入 `scripts/personal/smoke_check.py`。
- 更新车辆档案、更新检查单和 TODO。

验证：

- `python3 scripts/personal/seltos_profile_check.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-17: 路测证据检查器

新增文件：

- `scripts/personal/road_test_evidence_check.py`

改动文件：

- `scripts/personal/release_gate.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`

改动内容：

- 增加路测证据检查脚本，用于把 `static` / `test` 推进到 `stable` 前检查实车证据。
- 检查上车测试记录中必填字段和必填 `PASS` 结论行。
- 支持读取一个或多个 C3 设备快照 markdown。
- `stable` 证据要求至少一个快照满足：
  - `AlwaysOffroad=0`
  - `EnableConnect=0`
  - `CanfdHDA2=0`
  - `HyundaiCameraSCC=0`
  - `EnableEscc=1`
  - `enabled=True`
  - `ok=True`
  - `escc_0x2ab_bus0 > 0`
- `release_gate.py --kind stable` 现在必须传入 `--road-test-log` 和至少一个 `--device-snapshot`。
- 将证据检查器自检接入 `smoke_check.py`。
- 更新安装说明、设备快照说明、路测模板和更新检查单。

验证：

- `python3 scripts/personal/road_test_evidence_check.py --self-test` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: Upstream Watch 定期审计

改动文件：

- `.github/workflows/upstream-snapshot.yml`
- `docs/personal/README.md`
- `docs/personal/GITHUB_SETUP.md`
- `docs/personal/BRANCH_STRATEGY.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- 将旧的 `Upstream Snapshot` 工作流升级为 `Upstream Watch`。
- 使用 `actions/checkout@v6` 和 `actions/setup-python@v6`。
- 增加 `docs/personal/UPSTREAM_BASELINES.json`，记录已审查的上游基准 commit：
  - `upstream/c3-wip`
  - `tracking/c4`
  - `tracking/jixie-atune`
  - `tracking/jixie-master`
  - `tracking/fishop-cp`
- 再拉取三方来源的最新远端分支：
  - `ajouatom/openpilot:c3-wip`
  - `ajouatom/openpilot:carrot-wip`
  - `jixiexiaoge/openpilot:atune`
  - `jixiexiaoge/openpilot:master`
  - `fishop/openpilot:cp`
- 运行 `python3 scripts/personal/update_audit.py --baseline-file docs/personal/UPSTREAM_BASELINES.json --strict`。
- 如果上游有新提交、基准 commit 落后或高风险目录有变化，工作流会变红，作为人工更新审计提醒。
- 明确该工作流只提醒，不自动合并，也不改变设备安装目标。

验证：

- 本地 `python3 scripts/personal/update_audit.py --fetch` 通过，当前三方来源均对齐。
- 推送后需要手动触发或等待 `Upstream Watch` 确认 GitHub 侧基准清单可用。

## 2026-06-18: 当前静态检查 tag

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static1`

包含范围：

- `carrotpilot-c3-escc-20260617-static3` 之后的维护护栏：
  - 安装目标清单和检查脚本。
  - Seltos 2023 纯 CAN / Seltos 2021 复用护栏。
  - 路测证据检查器和 `stable` gate 加严。
  - `Upstream Watch` 定期上游审计。

含义：

- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。
- `daily_install_target` 仍为空。

验证：

- `python3 scripts/personal/update_audit.py --baseline-file docs/personal/UPSTREAM_BASELINES.json --strict` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: C3 静态检查向导

新增文件：

- `scripts/personal/c3_static_check.py`

改动内容：

- 增加 C3 设备端静态检查向导，默认只读，不修改参数。
- 检查当前安装是否匹配 `INSTALL_TARGETS.json` 的 `current_static_tag`。
- 运行安装目标、Seltos 车型复用、ESCC / AlwaysOffroad、CP搭子静态预检。
- 读取安全参数并提示是否符合停车上车前建议：
  - `AlwaysOffroad=0`
  - `EnableConnect=0`
  - `EnableEscc=0`
  - `HyundaiCameraSCC=0`
  - `CanfdHDA2=0`
  - `EnableRadarTracks=0`
- 调用 `device_snapshot.py` 生成隐私安全快照。
- 生成 `/data/media/0/carrotpilot-c3-escc-static-check.md` 检查报告。
- 将脚本加入 `smoke_check.py` 的 Python 语法检查。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static2`

含义：

- 包含 C3 静态检查向导。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/c3_static_check.py --output /tmp/carrotpilot-c3-escc-static-check.md --snapshot-output /tmp/carrotpilot-c3-escc-snapshot.md --allow-branch --skip-preflight` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: C3 静态检查向导 smoke 覆盖

改动文件：

- `scripts/personal/c3_static_check.py`
- `scripts/personal/smoke_check.py`

改动内容：

- `c3_static_check.py --allow-branch` 现在可用于开发分支和 CI dry-run，即使下一版 `static` tag 尚未创建也能验证脚本流程。
- `smoke_check.py` 新增 C3 静态检查向导 dry-run。
- dry-run 会写入 `/tmp/carrotpilot-c3-escc-static-check-smoke.md` 和 `/tmp/carrotpilot-c3-escc-snapshot-smoke.md`，并确认二者是有效报告。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static3`

含义：

- 包含 C3 静态检查向导的 CI 运行覆盖。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/smoke_check.py` 通过，包含 `C3 static check dry-run`。

## 2026-06-18: 一键实车证据采集器

新增文件：

- `scripts/personal/collect_real_car_evidence.py`

改动文件：

- `scripts/personal/smoke_check.py`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`
- `docs/personal/README.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- 增加 C3 设备端一键证据采集器，默认只读，不修改参数。
- 自动调用 `c3_static_check.py` 生成 `static-check.md` 和 `device-snapshot.md`。
- 自动生成 `road-test-log-draft.md`、`README.md`、`manifest.json` 和 `static-check-output.txt`。
- 支持 `--sample-seconds 20`，停车时采集 ESCC 0x2AB / CP搭子消息计数。
- 支持 `--archive`，把证据目录打成 tar.gz，方便从 C3 拷出。
- 将证据包 dry-run 加入 `smoke_check.py`，确认每次推送都能生成完整证据目录。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static4`

含义：

- 包含实车证据采集器。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/collect_real_car_evidence.py --output-dir /tmp/carrotpilot-c3-escc-evidence --allow-branch --skip-preflight --force` 通过。
- `python3 scripts/personal/smoke_check.py` 通过，包含 `Real-car evidence bundle dry-run`。

## 2026-06-18: Stable 证据包目录校验

改动文件：

- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/release_gate.py`
- `scripts/personal/collect_real_car_evidence.py`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`
- `docs/personal/README.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- `road_test_evidence_check.py` 新增 `--evidence-dir`，可直接读取一键证据采集器生成的目录。
- 证据目录中如果有 `manifest.json`，会确认 `static_check_exit_code=0`。
- 自动从证据目录中读取 `road-test-log-draft.md` 和 `device-snapshot.md`。
- `release_gate.py --kind stable` 新增 `--evidence-dir`，可直接用同一个证据包创建 stable tag。
- 证据包 README 改为推荐 `--evidence-dir` 命令，减少手工拼路径出错。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static5`

含义：

- 包含证据包目录校验和 stable 发布闸门目录输入。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/road_test_evidence_check.py --self-test` 通过，包含证据包目录自测。
- 未填写的证据包会被拒绝，并列出缺少的 `PASS` 结论行。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: CP搭子 / Navipilot 实连证据增强

改动文件：

- `scripts/personal/device_snapshot.py`
- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/smoke_check.py`
- `scripts/personal/collect_real_car_evidence.py`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/README.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `README.md`

改动内容：

- 设备快照新增 CP搭子 / Navipilot 采样诊断：
  - `cplink_updates_seen`
  - `cplink_speed_limit_seen`
  - `cplink_sdi_seen`
  - `cplink_tbt_seen`
  - `cplink_gps_seen`
  - `cplink_lanechange_cmd_seen`
  - `last_carrotMan`
  - `last_navInstructionCarrot`
- 快照只记录导航字段是否出现和非敏感摘要，不记录 GPS 坐标、路线点或街道名。
- `road_test_evidence_check.py` 新增 `--require-cplink-sample`，用于 CP搭子实测时检查证据包里是否有实际导航数据流。
- `smoke_check.py` 新增对 CP搭子诊断字段的 dry-run 覆盖。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static6`

含义：

- 包含 CP搭子 / Navipilot 实连证据增强。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/road_test_evidence_check.py --self-test` 通过，包含 `--require-cplink-sample` 自测。
- `python3 scripts/personal/smoke_check.py` 通过，确认快照包含 CP搭子诊断字段。

## 2026-06-18: CarParams 车型证据摘要

改动文件：

- `scripts/personal/device_snapshot.py`
- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/release_gate.py`
- `scripts/personal/smoke_check.py`
- `scripts/personal/collect_real_car_evidence.py`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`
- `docs/personal/README.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `docs/personal/INSTALL_TARGETS.json`
- `README.md`

改动内容：

- 设备快照新增隐私安全 CarParams 摘要：
  - `CarParamsDecoded`
  - `carName`
  - `carFingerprint`
  - `fingerprintSource`
  - `networkLocation`
  - `openpilotLongitudinalControl`
  - `pcmCruise`
  - `dashcamOnly`
  - `flags`
  - `spFlags`
  - `safetyConfigs`
  - `carFwCount`
- 不记录 VIN、完整 firmware、路线或完整参数内容。
- `road_test_evidence_check.py` 新增 `--require-carparams-summary`，要求快照能解码 Seltos 相关 CarParams 并包含 safety 配置摘要。
- `release_gate.py --kind stable` 默认要求 `--require-carparams-summary`。
- `smoke_check.py` 确认新快照包含 `CarParamsDecoded` 字段。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static7`

含义：

- 包含 Seltos / safety 车型证据摘要和 stable gate 加严。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/road_test_evidence_check.py --self-test` 通过，包含 `--require-carparams-summary` 自测。
- `python3 scripts/personal/smoke_check.py` 通过，确认快照包含 `CarParamsDecoded`。

## 2026-06-18: 功能边界守卫

新增文件：

- `scripts/personal/feature_boundary_check.py`

改动文件：

- `scripts/personal/smoke_check.py`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `docs/personal/README.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `README.md`

改动内容：

- 新增主线功能边界静态检查，确认未验证的 `OVERTAKE`、fishop `amap_navi.py`、独立 `xiaoge_web.py` / `xiaoge_sentryd.py` 没有进入默认主线。
- 确认当前 C3 底座已有的 7000 Web、dashcam、screenrecord、tools 和 Auto-Tuner Web 面板仍存在。
- 确认 cluster HUD 仍由 `ClusterHud` 参数控制，`xiaoge_data` 仍由 `ShareData` 参数控制，不默认常驻。
- 将功能边界守卫加入 `smoke_check.py` 和更新检查单。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static8`

含义：

- 包含功能边界守卫。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/feature_boundary_check.py --no-manual` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: 实车证据就绪度报告

新增文件：

- `scripts/personal/evidence_readiness_report.py`

改动文件：

- `scripts/personal/smoke_check.py`
- `scripts/personal/collect_real_car_evidence.py`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`
- `docs/personal/README.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `docs/personal/INSTALL_TARGETS.json`
- `README.md`

改动内容：

- 新增证据就绪度报告脚本，可读取单个快照、路测记录或一键证据包目录。
- 分阶段显示：
  - 证据输入是否存在。
  - C3 设备快照是否可解析。
  - Seltos CarParams 摘要是否存在。
  - ESCC 0x2AB 采样是否满足 stable 要求。
  - 路测记录 PASS 结论是否完整。
  - stable gate 是否已准备好。
  - CP搭子 / Navipilot 采样是否存在。
- 证据采集器生成的 README 中新增就绪度报告命令。
- 将就绪度报告自检接入 `smoke_check.py`。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static9`

含义：

- 包含实车证据就绪度报告。
- 静态检查通过，不代表实车验证。
- 还没有 `stable` tag。

验证：

- `python3 scripts/personal/evidence_readiness_report.py --self-test` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: 受控上车测试 tag

改动文件：

- `scripts/personal/install_target_check.py`
- `scripts/personal/release_gate.py`
- `scripts/personal/device_snapshot.py`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/README.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- 在安装目标清单中记录当前受控上车测试 tag：
  - `carrotpilot-c3-escc-20260618-test1`
- `install_target_check.py` 输出当前 `test` tag，方便区分静态预检、受控测试和稳定版本。
- `release_gate.py --kind test` 的 tag message 改为受控测试说明，不再复用 static 文案。
- `device_snapshot.py` 在系统命令不可用时继续生成快照，避免受限环境里 `ps` 被拒绝导致 dry-run 失败。
- 文档明确 `test1` 只用于停车静态检查、证据采集和低速短程验证，不是日常稳定安装目标。

当前测试 tag：

- `carrotpilot-c3-escc-20260618-test1`

含义：

- 已通过当前个人静态检查链。
- 准备给 C3 / Seltos 2023 做受控上车测试和证据采集。
- 不代表 stable，不应作为日常稳定安装目标。

验证：

- `CARROTPILOT_PENDING_RELEASE_TAG=carrotpilot-c3-escc-20260618-test1 python3 scripts/personal/install_target_check.py` 通过。
- `CARROTPILOT_PENDING_RELEASE_TAG=carrotpilot-c3-escc-20260618-test1 python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: 功能状态报告

新增文件：

- `scripts/personal/feature_status_report.py`

改动文件：

- `scripts/personal/smoke_check.py`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/README.md`
- `docs/personal/TODO.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `README.md`

改动内容：

- 新增个人功能状态报告，输出当前功能分组状态：
  - 7000 Web console：`READY_STATIC`
  - 实验模式 Web 开关：`READY_STATIC`
  - Auto-Tuner 手动确认闭环：`READY_STATIC`
  - CP搭子 / Navipilot 核心协议：`READY_STATIC`
  - cluster HUD / USB display：`GATED`
  - `xiaoge_data`：`GATED`
  - 驾驶报告：`PENDING`
  - 模型选择器：`PENDING`
  - 自动超车、fishop AmapNavi、独立 Xiaoge web/sentry：`ISOLATED`
- 将功能状态报告接入 `smoke_check.py` 和更新检查单。
- 更新 TODO，把已有 Web/实验模式/cluster 静态能力和仍待实测/迁移的项目分开。
- `install_target_check.py` 支持 `CARROTPILOT_PENDING_RELEASE_TAGS`，用于同一次提交里同时验证待创建的 static/test tag。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static10`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test2`

验证：

- `python3 scripts/personal/feature_status_report.py --strict` 通过。
- `CARROTPILOT_PENDING_RELEASE_TAGS=carrotpilot-c3-escc-20260618-static10,carrotpilot-c3-escc-20260618-test2 python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-18: 中文设置说明第二批

改动文件：

- `selfdrive/carrot_settings.json`
- `scripts/personal/settings_cn_audit.py`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- 继续只修改中文显示字段，不修改参数名、范围、默认值或控制逻辑。
- 补清导航减速、转弯减速、路径颜色、雷达显示、限速摄像头提醒和外部 HUD 相关说明。
- 对没有外接 HUD/小屏硬件时应保持关闭的项目增加说明。
- 对 C3/C3 克隆版容易误调的外部 HUD FPS、实时优先级、编码器选项增加提示。
- 扩展 `settings_cn_audit.py`，把第二批关键说明加入审计，防止后续更新退化。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static11`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test3`

含义：

- 包含第二批中文设置说明优化，静态检查通过，不代表实车验证或稳定版本。

## 2026-06-18: Navipilot APP 来源跟踪和 TBT 字段修复

新增文件：

- `docs/personal/NAVIPILOT_APP_RESEARCH.md`

改动文件：

- `.github/workflows/personal-smoke.yml`
- `.github/workflows/upstream-snapshot.yml`
- `selfdrive/carrot/carrot_serv.py`
- `scripts/personal/cplink_preflight.py`
- `scripts/personal/feature_status_report.py`
- `scripts/personal/update_audit.py`
- `scripts/personal/upstream_snapshot.sh`
- `docs/personal/UPSTREAM_BASELINES.json`
- `docs/personal/BRANCH_STRATEGY.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/README.md`
- `docs/personal/SOURCES_AND_CREDITS.md`
- `docs/personal/TODO.md`
- `docs/personal/UPDATE_CHECKLIST.md`

改动内容：

- 新增 `jixie-navipilot` 来源，跟踪 `jixiexiaoge/navipilot:CPdazi`。
- `UPSTREAM_BASELINES.json` 记录 Navipilot APP 当前已审查 commit：`c2a1028f22e47b3c4838b9e2a320966a0529cc03`。
- `Upstream Watch` 和 `Personal Smoke` 会抓取 Navipilot APP 分支，防止驾驶报告、WebSocket、APP 协议、模型/参数管理和自动超车 UI 更新漏审。
- 明确驾驶报告属于 Navipilot Android APP 侧功能；C3 端保持 `carrotMan`、`/ws/raw_multiplex`、`/ws/camera/road` 和导航字段兼容。
- 修复 `szTBTMainTextNext`：车机端现在读取 APP 发来的 `szTBTMainTextNext` 键，不再误读 `szTBTMainText`。
- `cplink_preflight.py` 增加 raw multiplex、camera WebSocket、Navipilot 默认服务和 TBT 下一路口字段守卫。
- 功能状态报告把“驾驶报告”改为“Navipilot APP 驾驶报告支持”，避免误判为 C3 本体缺少本地报告网页。

待实测：

- Android Navipilot APP 连接 C3 7000 端口。
- APP 通过 `/ws/raw_multiplex` 读取车辆数据，通过 `/ws/camera/road` 读取摄像头。
- 开车结束后 APP 端生成驾驶评分报告。
- 不启用自动超车时，确认 `OVERTAKE` / ZMQ 7710 不进入默认主线。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static12`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test4`

含义：

- 包含 Navipilot APP 来源跟踪和 TBT 下一路口字段修复。
- 静态检查通过后才可用于停车检查或低速受控测试。
- 不代表 stable，不应作为日常稳定安装目标。

## 2026-06-18: Navipilot 驾驶报告实测前守卫补强

改动文件：

- `scripts/personal/cplink_preflight.py`
- `scripts/personal/feature_status_report.py`
- `docs/personal/NAVIPILOT_APP_RESEARCH.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/TODO.md`
- `README.md`

改动内容：

- `cplink_preflight.py` 新增 UDP 7705 状态广播字段检查：
  - `IsOnroad`
  - `active`
  - `v_ego_kph`
  - `v_cruise_kph`
  - `carcruiseSpeed`
  - `tbt_dist`
  - `sdi_dist`
  - `xState`
  - `trafficState`
- `cplink_preflight.py` 新增对 `tracking/jixie-navipilot` APP 源码的契约检查，确认 APP 仍使用 `/ws/raw_multiplex`、`/ws/camera/road`、7705 状态字段和 `startOnroadMonitoring()`。
- 文档明确当前 Navipilot APP 的 raw `carrotMan` 解码仍不完整，驾驶评分启动应优先核对 7705 状态广播，而不是只看 WebSocket 是否连接。
- 功能状态报告把 Navipilot 驾驶报告支持条件扩展为 7705 状态广播 + WebSocket raw/camera。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static13`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test5`

含义：

- 包含 Navipilot 驾驶报告实测前的 7705 状态广播守卫。
- 不代表 stable，不应作为日常稳定安装目标。

## 2026-06-18: 来源关系修正和安全参数迁移

新增文件：

- `scripts/personal/params_migration.py`
- `docs/personal/CONFIG_MIGRATION.md`

改动文件：

- `scripts/personal/smoke_check.py`
- `scripts/personal/update_audit.py`
- `docs/personal/SOURCES_AND_CREDITS.md`
- `docs/personal/RESEARCH_SNAPSHOT_2026-06-17.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/BRANCH_STRATEGY.md`
- `docs/personal/UPSTREAM_BASELINES.json`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/TODO.md`
- `docs/personal/README.md`
- `README.md`

改动内容：

- 将 `ajouatom/openpilot` 明确记录为当前按 CarrotPilot / CarPad 韩国主源处理的 C3 底座。
- 将 `dhvms/carrotpilot` 降级为旧 CarrotPilot 参考线，不作为官方主源或当前底座。
- 记录 `gitop.vip/cp` 实际下载的是 ARM64 ELF 安装器，静态字符串显示它拉取 `https://jihulab.com/fishop/openpilot.git` 的 `cp` 分支。
- 增加安全参数迁移脚本：
  - `export` 从当前版本导出设置白名单。
  - `import` 默认 dry-run，必须加 `--apply` 才写入。
  - `self-test` 确认安全 key 可导出、敏感 key 会被过滤。
- 迁移脚本过滤 token、password、private、dongle、github、athena、ssh、api key、oauth、credential、email、account 等敏感 key。
- 不迁移 `IsOnroad`、`EnableRadarTracksResult` 这类运行状态或启动后检测结果。
- 将迁移脚本接入 `smoke_check.py`。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static14`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test6`

含义：

- 包含来源关系修正和从 fishop / 飞扬工作版本迁移安全设置的工具。
- 不代表 stable，不应作为日常稳定安装目标。

## 2026-06-18: C3 首次安装/迁移向导

新增文件：

- `scripts/personal/c3_commissioning.py`

改动文件：

- `scripts/personal/smoke_check.py`
- `docs/personal/CONFIG_MIGRATION.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/TODO.md`
- `docs/personal/README.md`
- `README.md`

改动内容：

- 增加 C3 设备端首装向导，用于安装本项目版本后的第一轮停车准备。
- 默认流程：
  - 可选读取旧 fishop / 飞扬版本导出的安全参数 JSON。
  - 未加 `--apply-migration` 时只做参数导入 dry-run。
  - 调用 `collect_real_car_evidence.py` 生成 `evidence/` 证据包。
  - 调用 `evidence_readiness_report.py` 生成 `evidence-readiness.txt`。
  - 生成 `README.md` 和 `manifest.json`，记录迁移模式、命令、退出码、commit、tag 和证据目录。
- 支持 `--archive` 打包整个首装向导目录，方便从 C3 拷回电脑。
- 将首装向导 dry-run 接入 `smoke_check.py`。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static15`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test7`

含义：

- 包含首装/迁移/证据采集一体化设备端向导。
- 不代表 stable，不应作为日常稳定安装目标。

## 2026-06-18: Navipilot APP 参数接口守卫

改动文件：

- `scripts/personal/cplink_preflight.py`
- `scripts/personal/feature_status_report.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/NAVIPILOT_APP_RESEARCH.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/TODO.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `README.md`

改动内容：

- `cplink_preflight.py` 新增 C3 端 7000 参数 REST API 检查：
  - `/api/params_bulk`
  - `/api/param_set`
  - `get_param_values`
  - `set_param_value`
  - `ExperimentalMode`
  - `ExperimentalModeConfirmed`
- `cplink_preflight.py` 新增对 Navipilot APP `CarrotParamClient.kt` 的源码契约检查，确认 APP 仍使用 7000 端口和上述参数接口。
- `feature_status_report.py` 新增 `Navipilot app param API` 状态。
- `smoke_check.py` 将空白检查改为个人维护路径的工作区扫描，避免 partial clone 下全仓 `git diff --check` 等待旧 blob。
- 文档明确：APP 侧实验模式/参数控制接口已静态兼容；模型选择器仍是高风险独立批次，不随本次进入主线。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static16`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test8`

含义：

- 包含 Navipilot APP 参数接口静态契约守卫。
- 不代表 stable，不应作为日常稳定安装目标。

## 2026-06-18: Navipilot APP 端点 live check

改动文件：

- `scripts/personal/navipilot_live_check.py`
- `scripts/personal/collect_real_car_evidence.py`
- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/evidence_readiness_report.py`
- `scripts/personal/feature_status_report.py`
- `scripts/personal/smoke_check.py`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/DEVICE_SNAPSHOT.md`
- `docs/personal/ROAD_TEST_LOG_TEMPLATE.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/NAVIPILOT_APP_RESEARCH.md`
- `docs/personal/JIXIE_FISHOP_BOUNDARY.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/TODO.md`
- `docs/personal/README.md`
- `README.md`

改动内容：

- 新增 `navipilot_live_check.py`，用于在 C3 上检查 Navipilot APP 依赖的车机端点：
  - 7000 `/api/params_bulk`
  - 7000 `/api/param_set` 同值写回探针
  - UDP 7705 状态广播及 APP 评分关键字段
  - 可选 UDP 7706 测试导航输入
- 7706 测试包不发送 `LANECHANGE` 或 `OVERTAKE`，仍建议只在停车状态下使用。
- `collect_real_car_evidence.py` 新增 `--navipilot-check`、`--navipilot-param-write-probe` 和 `--navipilot-send-test-nav`，可把 `navipilot-live-check.md/json` 放入证据包。
- `road_test_evidence_check.py` 新增 `--navipilot-live-check` 和 `--require-navipilot-live-check`，可检查证据包内 live check 是否通过。
- `evidence_readiness_report.py` 新增可选阶段 `Navipilot live endpoint check`。
- `feature_status_report.py` 新增 `Navipilot live endpoint check` 状态。
- `smoke_check.py` 纳入 `navipilot_live_check.py --self-test`。
- 文档明确：该检查只证明 C3 侧端点可用，不代表 Android APP UI、导航发送、摄像头预览或驾驶报告已经实测通过。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static17`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test9`

含义：

- 包含 Navipilot APP 端点 live check 和证据包校验。
- 不代表 stable，不应作为日常稳定安装目标。

## 2026-06-18: Model selector 参考线跟踪和审计

改动文件：

- `scripts/personal/model_selector_audit.py`
- `scripts/personal/smoke_check.py`
- `scripts/personal/feature_status_report.py`
- `scripts/personal/update_audit.py`
- `.github/workflows/personal-smoke.yml`
- `.github/workflows/upstream-snapshot.yml`
- `docs/personal/MODEL_SELECTOR_RESEARCH.md`
- `docs/personal/UPSTREAM_BASELINES.json`
- `docs/personal/BRANCH_STRATEGY.md`
- `docs/personal/SOURCES_AND_CREDITS.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/INSTALL_TARGETS.json`
- `docs/personal/TODO.md`
- `docs/personal/README.md`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `README.md`

改动内容：

- 新建 `tracking/model-selector`，跟踪 `ajouatom/openpilot:happymaj11r/carrot-wip-model_selector`。
- `UPSTREAM_BASELINES.json` 新增已审查基准 `d4ed4fa165f019618791b8590f82f4cc115f7c5f`。
- `update_audit.py` 和 GitHub Actions `Upstream Watch` 纳入模型选择器参考线。
- 新增 `model_selector_audit.py`，检查参考分支是否仍具备：
  - canonical JSON + Ed25519 manifest 校验。
  - ONNX 文件 allowlist。
  - 下载 URL prefix allowlist。
  - size / SHA256 校验。
  - `/data/models` validator。
  - tinygrad 编译、warp pkl、atomic swap 和 backup 恢复。
  - 无有效自定义模型时回退 upstream `modeld`。
  - reset 恢复默认模型。
- `model_selector_audit.py` 同时检查当前默认 C3 主线没有半截启用模型下载、模型安装、Web 模型页或 `modeld_runner`。
- `smoke_check.py` 纳入模型选择器审计。
- `feature_status_report.py` 将模型选择器状态标为 `SOURCE_TRACKED`。
- 新增 `MODEL_SELECTOR_RESEARCH.md`，明确真正迁移必须放到 `experimental/model-selector` 这类独立分支。

当前静态测试 tag：

- `carrotpilot-c3-escc-20260618-static18`

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test10`

含义：

- 包含模型选择器参考线跟踪和源码审计。
- 不启用模型下载、模型安装或 `modeld` 切换。
- 不代表 stable，不应作为日常稳定安装目标。

## 2026-06-18: 中文/英文本地化清理

改动文件：

- `selfdrive/carrot_settings.json`
- `selfdrive/carrot/web/index.html`
- `selfdrive/carrot/web/js/translations/registry.js`
- `selfdrive/carrot/web/js/translations/ko.js`
- `selfdrive/carrot/web/js/shared/i18n.js`
- `selfdrive/carrot/web/js/shared/constants.js`
- `selfdrive/carrot/web/js/shared/utils.js`
- `selfdrive/carrot/web/js/pages/setting.js`
- `selfdrive/carrot/web/js/pages/tools.js`
- `selfdrive/carrot/web/js/pages/tools_web_settings.js`
- `selfdrive/carrot/web/js/pages/setting_device_config.js`
- `selfdrive/carrot/web/js/pages/logs/shared.js`
- `selfdrive/carrot/web/js/realtime/nav_hud.js`
- `selfdrive/carrot/web/js/realtime/carrot_map.js`
- `selfdrive/carrot/web/js/realtime/hud_card.js`
- `selfdrive/carrot/web/js/realtime/vision_diag.js`
- `selfdrive/carrot/kmap/kmap.js`
- `selfdrive/carrot/kmap/index.html`
- `selfdrive/carrot/carrot_serv.py`
- `selfdrive/carrot/recovery/server.py`
- `selfdrive/carrot/server/features/static.py`
- `selfdrive/carrot/server/features/dashcam/paths.py`
- `selfdrive/carrot/server/features/system.py`
- `selfdrive/carrot/server/services/settings.py`
- `selfdrive/carrot/server/services/web_settings.py`
- `selfdrive/carrot/server/services/heartbeat.py`
- `selfdrive/carrot/server/services/time_sync.py`
- `selfdrive/carrot/server/services/params.py`
- `scripts/personal/localization_audit.py`
- `scripts/personal/smoke_check.py`
- `scripts/personal/settings_cn_audit.py`
- `scripts/personal/model_selector_audit.py`
- `README.md`
- `docs/personal/TODO.md`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/CODE_CHANGES.md`

改动内容：

- 将 `carrot_settings.json` 的主 `group/title/descr` 从韩文切换为英文，继续保留 `cgroup/ctitle/cdescr` 中文字段；参数名、范围、默认值不变。
- 给 11 个原本缺失英文说明的设置补英文描述，避免英文 fallback 为空。
- Web 语言入口收敛为英文/中文，删除韩语语言包加载；旧 `ko` 或 `main_ko` 缓存会回落到英文。
- 清理 Web 初始 HTML、设置页、日志页、Auto-Tuner 面板、Carrot Vision 诊断、地图缩放、导航 HUD 和 KMap 浮层中的直接韩文文案。
- 过滤服务端注入的设备语言列表，只保留 English、简体中文、繁體中文；旧 `main_ko` 配置按英文处理。
- 清理 Carrot 服务端 SDI 描述、dashcam 相对时间、系统重置消息、恢复页和 KMap HTML 的直接韩文。
- README 上游法律/线束说明改为中英文可读版本，同时保留免责声明含义和上游署名。
- 新增 `localization_audit.py`，并纳入 `smoke_check.py`，防止后续上游合并重新带入直接韩文 UI 文案。

验证：

- `python3 scripts/personal/localization_audit.py` 通过。
- `python3 scripts/personal/settings_cn_audit.py` 通过。
- `python3 -m json.tool selfdrive/carrot_settings.json` 通过。
- Python 语法检查通过。

## 2026-06-18: test21 受控测试安装目标

改动文件：

- `docs/personal/INSTALL_TARGETS.json`
- `scripts/personal/install_c3_escc.sh`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/BINARY_INSTALLER_RESEARCH.md`
- `README.md`
- `docs/personal/CODE_CHANGES.md`

改动内容：

- 将当前受控上车测试目标更新为 `carrotpilot-c3-escc-20260618-test21`。
- 脚本安装器默认 ref 同步改为 test21。
- 安装说明里的 release asset URL、二进制安装器说明和 dry-run 命令同步改为 test21。
- `current_static_tag` 仍保持 `carrotpilot-c3-escc-20260618-static28`；当前仍没有 stable tag，`daily_install_target` 继续为空。

## 2026-06-18: test22 本地化说明和发布清单

改动文件：

- `selfdrive/carrot_settings.json`
- `scripts/personal/settings_cn_audit.py`
- `docs/personal/UPDATE_CHECKLIST.md`
- `docs/personal/TODO.md`
- `docs/personal/FEATURE_MATRIX.md`
- `docs/personal/README.md`
- `docs/personal/INSTALL_TARGETS.json`
- `scripts/personal/install_c3_escc.sh`
- `docs/personal/INSTALL_AND_ROLLBACK.md`
- `docs/personal/BINARY_INSTALLER_RESEARCH.md`
- `README.md`
- `docs/personal/CODE_CHANGES.md`

改动内容：

- 将当前受控上车测试目标更新为 `carrotpilot-c3-escc-20260618-test22`。
- 改善一批容易误解的设置说明，覆盖转向摩擦补偿、巡航触发距离、节能巡航、目标停车距离、起步加速代价、巡航按键步进、LDWS-only、雷达轨迹、软件菜单、弯道减速下限、驾驶模式、红绿灯处理和外部 HUD 主题。
- 扩展 `settings_cn_audit.py`，把这批说明加入自动守卫，防止以后上游合并退回抽象机翻。
- 更新 `UPDATE_CHECKLIST.md`，补齐 test release 的二进制安装器发布步骤、tag 先后顺序和 GitHub Actions 复跑注意事项。
- 更新安装说明、脚本默认 ref 和二进制安装器研究记录到 test22。

验证：

- `jq empty selfdrive/carrot_settings.json` 通过。
- `python3 scripts/personal/settings_cn_audit.py` 通过。
- `python3 scripts/personal/localization_audit.py` 通过。
- `python3 scripts/personal/install_target_check.py` 通过。
- `python3 scripts/personal/smoke_check.py` 通过。

## 2026-06-19: alpha CP搭子 / Navipilot live check

改动文件：

- `openpilot-sunnypilot-011-c3/scripts/personal/navipilot_live_check.py`
- `openpilot-sunnypilot-011-c3/scripts/personal/sunnypilot_c3_alpha_snapshot.py`
- `openpilot-sunnypilot-011-c3/scripts/personal/sunnypilot_c3_alpha_static_check.py`
- `scripts/personal/road_test_evidence_check.py`
- `scripts/personal/evidence_readiness_report.py`
- `docs/personal/TODO.md`
- `docs/personal/CODE_CHANGES.md`

改动内容：

- 新架构 alpha 新增 CP搭子 / Navipilot 本地端点检查器。
- 覆盖 7000 `/api/health`、`/api/params_bulk`、`/api/param_set`、`/api/status_broadcast`、7705 UDP 状态广播、7713 HTTP 导航健康、7712 TCP 导航健康和 `/api/navigation_event`。
- 默认只读；同值参数写回需要显式 `--write-same-value`，安全导航探针需要显式 `--send-navigation-probe`。
- 安全导航探针只发送空命令字段的证据包，继续要求 `xState=0`、`trafficState=0`、`controlOutput=false`。
- alpha 静态守门新增 live check 自测，并检查工具不保留旧 `AlwaysOffroad` / `EnableEscc` 别名、不引用云连接/上传客户端依赖。
- alpha 设备快照新增可选 `navipilotLiveCheck` 证据块；默认不运行，停车测试时加 `--navipilot-live-check`，需要作为证据门槛时加 `--require-navipilot-live-check`。
- 稳定线证据校验器可直接读取 alpha 快照里的 `navipilotLiveCheck.report`，并要求 local-only、无云服务、无控制输出，以及 7000/7705/7712/7713 关键检查通过；旧 `navipilot-live-check.json` 格式继续兼容。

验证：

- `python3 -m py_compile scripts/personal/navipilot_live_check.py scripts/personal/sunnypilot_c3_alpha_static_check.py` 通过。
- `python3 scripts/personal/navipilot_live_check.py --self-test` 通过。
- `python3 scripts/personal/navipilot_live_check.py --host 127.0.0.1 --web-port 9 --navi-http-port 9 --listen-seconds 0 --allow-unavailable --json` 通过。
- `python3 scripts/personal/sunnypilot_c3_alpha_snapshot.py --output /tmp/sunnypilot_c3_alpha_snapshot_check.json --pretty` 通过，默认 `navipilotLiveCheck.requested=false`。
- `python3 -u scripts/personal/sunnypilot_c3_alpha_static_check.py` 通过。
- `python3 scripts/personal/road_test_evidence_check.py --self-test` 通过。
- `python3 scripts/personal/evidence_readiness_report.py --self-test` 通过。
- 临时 alpha 快照 JSON 作为 `--navipilot-live-check` 输入并配合 `--require-navipilot-live-check` 通过。
