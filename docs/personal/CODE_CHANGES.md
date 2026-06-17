# 当前代码改动记录

## 2026-06-17: 新增 Kia Seltos 2023

代码目录：

- `openpilot-c3-seltos-escc`

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

代码目录：

- `openpilot-c3-seltos-escc`

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

## 2026-06-17: Always Offline 模式

改动文件：

- `common/params_keys.h`
- `system/manager/manager.py`
- `system/manager/process_config.py`
- `system/athena/registration.py`
- `selfdrive/car/car_specific.py`
- `selfdrive/carrot_settings.json`

改动内容：

- 新增 `AlwaysOffline` 参数，个人 C3 克隆版默认开启。
- 设置菜单加入“离线使用模式”。
- 开启后跳过在线注册，使用本地 `UnregisteredDevice`。
- 开启后关闭后台更新和远程连接相关流程。
- 开启后驻车按 Cancel 不再触发主动关机。
- 新增 `EnableConnect` 参数，默认关闭，避免未定义参数被写入。

用途：

- 适配 C3 中国克隆版、ACC/CAN 供电、熄火直接断电、无法注册 openpilot/comma 账号的使用方式。

待实车验证：

- 开机不再卡注册。
- 断电重启后能直接进入系统。
- 离线模式开启时不启动更新和远程连接。

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
- 没有改变 Seltos 2023、ESCC、Always Offline 的默认行为。

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
- `scripts/personal/escc_offline_preflight.py`

用途：

- 更新、合并或上车前一键检查个人版关键保护项。
- 覆盖 Seltos 2023 独立车型、ESCC、Always Offline、Auto-Tuner 默认安全状态、设置 JSON、Python/JS 语法和 Auto-Tuner mock 回归。
- 单独 preflight 检查 ESCC / Always Offline 的 capnp、DBC、Params key、设置默认值、Seltos 2023 非 CANFD/HDA2 路径、ESCC 0x2AB 解析链路和离线注册/更新/连接禁用链路。
- preflight 明确保留实车待验证项，不把静态检查当成路测结论。

验证：

- `python3 scripts/personal/escc_offline_preflight.py` 通过。
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
- 保留 ESCC、Always Offline、Seltos 2023 和 Auto-Tuner 改动。

验证：

- `python3 scripts/personal/escc_offline_preflight.py` 通过。
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
- 给 ESCC、CANFD/HDA2、Camera SCC、雷达轨迹、角雷达、Always Offline、车门/安全带屏蔽等高风险项补充适用车型、默认建议和风险提示。
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
- 明确当前功能状态：ESCC 默认关闭、Always Offline 默认开启、Auto-Tuner 默认关闭、CP搭子核心协议静态兼容但 APP 未实测。
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
- 运行 `scripts/personal/smoke_check.py`、`scripts/personal/escc_offline_preflight.py --no-manual` 和 `scripts/personal/cplink_preflight.py --no-manual`。
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
  - `AlwaysOffline=1`
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
- 运行安装目标、Seltos 车型复用、ESCC / Always Offline、CP搭子静态预检。
- 读取安全参数并提示是否符合停车上车前建议：
  - `AlwaysOffline=1`
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
