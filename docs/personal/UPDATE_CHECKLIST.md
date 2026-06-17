# 以后更新检查单

每次跟随最新版 CarrotPilot 更新时，按这个清单走。

## 0. 更新前记录

- [ ] 记录当前稳定 tag。
- [ ] 查看 `docs/personal/INSTALL_TARGETS.json`，确认 `daily_install_target` 不是日常开发分支。
- [ ] 记录当前上车分支和 commit。
- [ ] 备份设备 `/data/params` 关键参数。
- [ ] 运行 `python3 scripts/personal/collect_real_car_evidence.py --archive` 采集设备端安全证据包。
- [ ] 如只需要单份快照，可运行 `python3 scripts/personal/device_snapshot.py`。
- [ ] 证据包拷回电脑后，运行 `python3 scripts/personal/evidence_readiness_report.py --evidence-dir <证据包目录>` 看阶段缺口。
- [ ] 记录当前车款识别结果：Seltos 2023 独立车型，初期复用 Seltos 2021 配置。
- [ ] 确认车辆仍按纯 CAN 路径运行，不是 CANFD。
- [ ] 记录 ESCC 相关参数当前值。
- [ ] 记录 `AlwaysOffline`、`DisableUpdates`、`EnableConnect` 当前值。
- [ ] 如果当前设备版本能正常跑，先运行 `python3 scripts/personal/params_migration.py export --output /data/media/0/carrotpilot-working-params.json` 导出安全设置白名单。
- [ ] 如果使用 atune 分支，记录 `CarrotLearningActive`、`CarrotLearningAutoApply` 和当前推荐值快照。
- [ ] 如果使用 CP搭子，记录手机 APP 版本、导航源、同 WiFi 状态和 7705/7706 连接结果。

## 1. 拉取上游

- [ ] 运行 `python3 scripts/personal/update_audit.py --fetch`。
- [ ] 拉取 `ajouatom/openpilot:c3-wip`。
- [ ] 拉取 `fishop/openpilot:cp`。
- [ ] 拉取 `jixiexiaoge/openpilot:atune`。
- [ ] 拉取 `jixiexiaoge/navipilot:CPdazi`。
- [ ] 检查 `update_audit.py` 输出的 remote ahead、新提交标题和高风险目录。
- [ ] 查看 GitHub Actions `Upstream Watch` 最近一次结果；如果变红，把输出当作更新审计入口。
- [ ] 查看三方最近提交标题。
- [ ] 判断这次是否涉及高风险目录。
- [ ] 确认个人远端 `github` 可推送。

高风险目录：

- `opendbc_repo/opendbc/car/hyundai/`
- `opendbc_repo/opendbc/dbc/`
- `panda/board/safety/`
- `common/params_keys.h`
- `cereal/*.capnp`
- `selfdrive/controls/`
- `selfdrive/carrot/`
- `selfdrive/carrot_settings.json`
- `selfdrive/apilot.json`
- `system/manager/process_config.py`

## 2. 合并前 diff 检查

- [ ] 检查 Hyundai 安全 flag 是否变动。
- [ ] 检查 Seltos 2023 新车型枚举是否仍存在。
- [ ] 检查 Seltos 2021 原车型枚举是否未被破坏。
- [ ] 检查 Seltos 2021/2023 fingerprint 是否变动。
- [ ] 检查 SCC、Camera SCC 逻辑是否变动。
- [ ] 检查 CANFD/HDA2 改动是否误影响 Seltos 2023 纯 CAN 路径。
- [ ] 检查 radar parser、radar track、lead selection 是否变动。
- [ ] 检查 longitudinal planner / longcontrol 是否变动。
- [ ] 检查 Carrot settings schema 是否变动。
- [ ] 检查 capnp schema 是否新增字段或字段编号冲突。

## 3. ESCC 回归检查

- [ ] 运行 `python3 scripts/personal/escc_offline_preflight.py`。
- [ ] `EnableEscc` 仍存在。
- [ ] ESCC 默认关闭，必须显式开启。
- [ ] ESCC 只在预期 Hyundai/Kia 路径启用。
- [ ] ESCC AEB/SCC 消息保留逻辑没有被上游覆盖。
- [ ] `HyundaiCameraSCC` 行为符合接线方式。
- [ ] `CanfdHDA2` 行为没有误影响 Seltos 2023 纯 CAN 车型。
- [ ] `EnableRadarTracks` 与 ESCC 的优先级明确。
- [ ] radar interface 对 ESCC、原车 radar tracks、camera lead 都有清楚 fallback。

## 3.5. 离线模式回归检查

- [ ] 运行 `python3 scripts/personal/escc_offline_preflight.py`。
- [ ] `AlwaysOffline` 仍存在，个人 C3 克隆版默认开启。
- [ ] 设置菜单仍显示“离线使用模式”。
- [ ] 开启后跳过在线注册。
- [ ] 开启后不启动后台更新。
- [ ] 开启后不启动远程连接和上传流程。
- [ ] 驻车按 Cancel 不触发主动关机。
- [ ] manager process 没有引用当前代码树不存在的模块。

## 3.6. Auto-Tuner / atune 回归检查

- [ ] `CarrotLearningActive` 默认关闭。
- [ ] `CarrotLearningAutoApply` 默认关闭。
- [ ] 默认关闭时不收集学习数据，不写入推荐参数。
- [ ] 开启学习时，学习器异常不会导致 planner 或 manager 崩溃。
- [ ] 推荐值和实际控制参数分开保存。
- [ ] 未经手动确认，不写入 `CruiseMaxVals*`、`TFollowGap*`、`PathOffset`、`SteerActuatorDelay`、`SteerRatioRate`。
- [ ] 本地 smoke 覆盖：默认关闭不写数据，开启学习可生成推荐，推荐不会直接改控制参数。
- [ ] Web 推荐面板能读取 `/api/carrot_learning`。
- [ ] 手动应用推荐时，`IsOnroad=True` 会拒绝写入。
- [ ] `CarrotLearningApply`、`CarrotLearningIgnore`、`CarrotLearningClear` 都是一触发即复位的一次性动作。
- [ ] Auto-Tuner 改动没有夹带 Web、cluster HUD、地图、Tesla、CANFD/HDA2 等无关功能。
- [ ] Seltos 2023、ESCC、Always Offline 的默认行为没有变化。

## 3.7. CP搭子 / Navipilot 回归检查

- [ ] 运行 `python3 scripts/personal/cplink_preflight.py`。
- [ ] `carrotMan` 和 `navInstructionCarrot` 服务仍存在。
- [ ] 7705 广播和 7706 接收逻辑仍存在。
- [ ] 7705 广播仍包含 Navipilot APP 驾驶评分需要的 `IsOnroad`、`active`、`v_ego_kph`、`v_cruise_kph`、`carcruiseSpeed`、`tbt_dist`、`sdi_dist`。
- [ ] 7000 WebSocket `/ws/raw_multiplex` 和 `/ws/camera/road` 仍存在，满足 Navipilot APP 车辆数据和摄像头预览。
- [ ] 设备端可运行 `python3 scripts/personal/navipilot_live_check.py --param-write-probe`，验证 7000 参数读写和 7705 状态广播。
- [ ] `nRoadLimitSpeed`、TBT、SDI、GPS 字段仍被解析。
- [ ] `szTBTMainTextNext` 仍从 APP 的 `szTBTMainTextNext` 键读取，不退回误读 `szTBTMainText`。
- [ ] `LANECHANGE` 命令仍只走现有安全变道逻辑。
- [ ] `OVERTAKE`、外接转向灯、AmapNavi、哨兵模式没有被无保护夹带进主线。
- [ ] 如 Navipilot APP 更新了 `CarrotWsClient.kt`、`DrivingDataCollector.kt`、`DrivingScoreEngine.kt` 或字段清单，重新核对 C3 端数据字段。

## 3.8. 功能边界守卫

- [ ] 运行 `python3 scripts/personal/feature_boundary_check.py`。
- [ ] 运行 `python3 scripts/personal/feature_status_report.py --strict`。
- [ ] 7000 Web 当前入口仍为 `carrot_server.py` 默认 7000 端口。
- [ ] dashcam、screenrecord、tools、Auto-Tuner Web 面板关键路由仍存在。
- [ ] `carrot_cluster` 仍由 `ClusterHud` 参数控制，不默认常驻。
- [ ] `xiaoge_data` 仍由 `ShareData` 参数控制，不默认常驻。
- [ ] `OVERTAKE`、fishop `amap_navi.py`、外接转向灯、lidar 盲区、DEC/longcontrol、独立 `xiaoge_web.py` / `xiaoge_sentryd.py` 没有进入默认主线。

## 3.9. 模型选择器参考线

- [ ] 运行 `python3 scripts/personal/model_selector_audit.py`。
- [ ] `tracking/model-selector` 仍指向已审查的 `ajouatom/openpilot:happymaj11r/carrot-wip-model_selector`。
- [ ] 默认 C3 主线没有半截启用模型下载、模型安装、Web 模型页或 `modeld_runner`。
- [ ] 如果准备迁移，必须新开 `experimental/model-selector`，并先验证签名、hash/size、allowlist、剩余空间、编译失败恢复和 reset 回默认模型。

## 3.10. AmapNavi / 自动超车 / DEC 来源参考线

- [ ] 运行 `python3 scripts/personal/app_navi_overtake_audit.py`。
- [ ] `fishop/cp` 仍包含 `selfdrive/carrot/amap_navi.py`、`amapNavi` schema/service、外接转向灯、lidar 盲区、`OVERTAKE` 和 DEC/longcontrol 参考源。
- [ ] `tracking/jixie-navipilot` 仍包含 `AutoOvertakeManager.kt`、7705/7706 网络通道和 `LANECHANGE` 命令出口。
- [ ] 默认 C3 主线仍没有 `amap_navi.py`、`amapNavi` service、外接转向灯参数、`OVERTAKE`、lidar 盲区参数或 DEC 接入点。
- [ ] 如准备迁移，必须新开 `experimental/app-navi` 或 `experimental/auto-lanechange`，并先补独立开关、停车态验证、低速验证和回滚策略。

## 4. Seltos 专项检查

- [ ] Seltos 2023 独立车型仍能识别。
- [ ] 运行 `python3 scripts/personal/seltos_profile_check.py`，确认 Seltos 2023 仍严格复用 Seltos 2021 经典 CAN 配置。
- [ ] Seltos 2023 默认配置仍等同已验证的 Seltos 2021 路径。
- [ ] 不引入只适合其它 Hyundai/Kia 车型的默认值。
- [ ] 不默认开启 HDA2/CANFD 路径。
- [ ] 不设置 CANFD/HDA2 safety flag。
- [ ] 不默认开启 ESCC 纵控，必须由参数控制。
- [ ] 保留可回滚到纯 `c3-wip` 的方式。

## 5. 构建和静态检查

- [ ] 运行 `python3 scripts/personal/update_audit.py` 并确认当前分支仍包含 `origin/c3-wip` 和 `personal/c3-escc`。
- [ ] 运行 `python3 scripts/personal/smoke_check.py` 并确认全部通过。
- [ ] 单独运行 `python3 scripts/personal/escc_offline_preflight.py` 并确认没有失败项。
- [ ] 单独运行 `python3 scripts/personal/cplink_preflight.py` 并确认没有失败项。
- [ ] 单独运行 `python3 scripts/personal/feature_boundary_check.py` 并确认没有失败项。
- [ ] 单独运行 `python3 scripts/personal/feature_status_report.py --strict` 并确认没有失败项。
- [ ] 运行 `python3 scripts/personal/settings_cn_audit.py` 并确认高风险中文说明没有缺失。
- [ ] 运行 `python3 scripts/personal/install_target_check.py` 并确认安装目标、稳定 tag 和回滚基线一致。
- [ ] 运行 `python3 scripts/personal/seltos_profile_check.py` 并确认车型配置没有被更新合并改成 CANFD/HDA2 或其它车型特判。
- [ ] 运行 `python3 scripts/personal/navipilot_live_check.py --self-test` 并确认 C3 侧 APP 端点检查器正常。
- [ ] 运行 `python3 scripts/personal/model_selector_audit.py` 并确认模型选择器参考线和默认主线边界正常。
- [ ] 运行 `python3 scripts/personal/app_navi_overtake_audit.py` 并确认 AmapNavi / 自动超车 / DEC 来源参考和默认主线边界正常。
- [ ] 运行 `python3 scripts/personal/evidence_readiness_report.py --self-test` 并确认证据就绪度报告正常。
- [ ] 检查 Python 语法。
- [ ] 检查 JSON 配置格式。
- [ ] 检查 capnp 是否需要重新生成。
- [ ] 检查新增 Params key 是否在 UI 和默认配置中一致。
- [ ] 检查 manager process 是否引用了存在的文件。
- [ ] 检查中文设置说明是否仍和参数含义一致，不能改默认值或参数范围。
- [ ] 推送后确认 GitHub Actions `Personal Smoke` 通过。
- [ ] 同步 `upstream/c3-wip` 或 `tracking/*` 后，更新 `docs/personal/UPSTREAM_BASELINES.json` 并手动触发一次 GitHub Actions `Upstream Watch`。
- [ ] 如环境允许，跑 Hyundai/opendbc 相关测试。
- [ ] 如环境允许，跑 controls 相关测试。

## 6. 上车前检查

- [ ] 先跑 `python3 scripts/personal/release_gate.py --tag carrotpilot-c3-escc-YYYYMMDD-static1 --kind static --run-checks`。
- [ ] 先打 `static` 或 `test` tag，不直接装开发分支。
- [ ] 运行 `python3 scripts/personal/escc_offline_preflight.py`，逐条处理脚本输出的 Manual checks。
- [ ] 安装前记录当前可用版本。
- [ ] 安装前保存设备证据包或设备快照文件。
- [ ] 如有旧版本设置导出文件，安装后先运行 `python3 scripts/personal/params_migration.py import --input /data/media/0/carrotpilot-working-params.json` dry-run。
- [ ] dry-run 输出里重点核对 `EnableEscc`、`HyundaiCameraSCC`、`EnableRadarTracks`、`AlwaysOffline`、Seltos/转向/纵控/导航调参项，再决定是否加 `--apply`。
- [ ] 更推荐安装后先运行 `python3 scripts/personal/c3_commissioning.py --migration-input /data/media/0/carrotpilot-working-params.json --archive`，把 dry-run、静态检查、证据包和 readiness 报告放到一个目录。
- [ ] 准备回滚 URL 或回滚分支。
- [ ] 第一次启动只静态检查，不开车。
- [ ] 确认无 manager crash、无循环重启、无缺失模块。
- [ ] 确认车辆识别正确。
- [ ] 确认 ESCC 参数默认状态符合预期。
- [ ] 确认离线模式开启时不会卡注册，也不会尝试联网更新。
- [ ] 如测试 CP搭子，先在停车状态运行 `python3 scripts/personal/collect_real_car_evidence.py --sample-seconds 20 --navipilot-check --navipilot-param-write-probe --archive`。
- [ ] 如测试 CP搭子，确认 Android APP 能发现 C3 并发送导航数据。
- [ ] 如测试 Navipilot 驾驶报告，确认 APP 端先收到 7705 的 `IsOnroad=True` 和车速字段，再在 onroad 后开始采集，并在停车后生成评分。
- [ ] 如测试 CP搭子，运行 `python3 scripts/personal/road_test_evidence_check.py --evidence-dir <证据包目录> --require-device-snapshot --require-cplink-sample --require-navipilot-live-check`。
- [ ] 如证据包还没满足 stable，先看 `evidence_readiness_report.py` 输出的缺口，不要直接打 stable tag。

## 7. 路测分级

第一级：停车或低速静态

- [ ] 设备启动稳定。
- [ ] CAN 无明显错误。
- [ ] UI 设置可读写。
- [ ] ESCC 开关可读写。

第二级：低速人工接管

- [ ] 不启用纵控，只确认车道/识别/雷达信息。
- [ ] 确认刹车、油门、取消按钮均正常。

第三级：有限启用

- [ ] 在安全条件下短时间启用。
- [ ] 观察 lead、SCC、AEB、radarState 是否异常。
- [ ] 有异常立即回滚。

第四级：日常使用前

- [ ] 至少经过多次短程验证。
- [ ] 没有 manager crash。
- [ ] 没有异常加减速。
- [ ] 没有错误识别车型或接线方式。

## 8. 发布

- [ ] 更新 changelog。
- [ ] 标注来源：CarrotPilot、机械小哥、fishop/码上飞扬。
- [ ] 标注是否经过 Seltos 实车验证。
- [ ] 标注是否经过 Always Offline 启动验证。
- [ ] 推送 `personal/c3-escc` 或 `personal/c3-escc-atune` 到 `github`。
- [ ] 发布前再次确认没有个人 token、私钥或设备隐私参数进入仓库。
- [ ] `stable` 前填写上车测试记录，并把 C3 快照文件保存到电脑本地。
- [ ] 如使用证据包，把 `road-test-log-draft.md` 和 `device-snapshot.md` 一起保存到电脑本地。
- [ ] 先运行 `python3 scripts/personal/evidence_readiness_report.py --evidence-dir <证据包目录>`，确认 stable 必需阶段都通过。
- [ ] 运行 `python3 scripts/personal/road_test_evidence_check.py --evidence-dir <证据包目录> --require-device-snapshot --require-carparams-summary --require-escc-sample`。
- [ ] 通过 `release_gate.py --kind stable --evidence-dir <证据包目录>`。
- [ ] 打稳定 tag。
- [ ] 更新 `docs/personal/INSTALL_TARGETS.json`，把新稳定 tag 设为 `current_stable_tag` 和 `daily_install_target`。
- [ ] 保留上一稳定 tag，并写入 `previous_stable_tag`。
