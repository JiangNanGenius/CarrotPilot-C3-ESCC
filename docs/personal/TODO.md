# TODO 主计划

## P0: 项目底座

- [ ] 确认 GitHub 仓库名称、公开或私有状态。
- [ ] 正式创建 GitHub 仓库。
- [x] 以 `ajouatom/openpilot:c3-wip` 建立本地主底座。
- [x] 添加本地远端：
  - `origin`: `https://github.com/ajouatom/openpilot.git`
  - `jixie`: `https://github.com/jixiexiaoge/openpilot.git`
  - `fishop`: `https://jihulab.com/fishop/openpilot.git`
  - `dhvms`: `https://github.com/dhvms/carrotpilot.git`
- [x] 建立当前开发分支：
  - `personal/c3-escc`
- [ ] 建立完整长期分支：
  - `upstream/c3-wip`
  - `personal/c3-escc`
  - `personal/c3-escc-atune`
  - `tracking/fishop-cp`
  - `tracking/jixie-atune`
  - `tracking/c4`

## P1: 用户车辆优先支持

- [x] 建立 Seltos 2023 车辆档案。
- [x] 新建 Kia Seltos 2023 独立车型条目。
- [x] 初期复用 Kia Seltos 2021 的 harness、物理参数、转向配置和 checksum flag。
- [x] 确认当前实际可用路径为 Seltos 2021 配置。
- [x] 记录车辆为纯 CAN，不是 CANFD。
- [ ] 确认 fingerprint、FW 查询、SCC/ESCC 硬件接线方式。
- [x] 确认代码改动没有覆盖原有 Seltos 2021 条目。
- [ ] 确认当前设备上可工作的 CarrotPilot 版本和参数快照。
- [ ] 列出并修改 Seltos 2021/2023 相关 Hyundai 文件：
  - `opendbc_repo/opendbc/car/hyundai/values.py`
  - `opendbc_repo/opendbc/car/hyundai/interface.py`
  - `opendbc_repo/opendbc/car/hyundai/carstate.py`
  - `opendbc_repo/opendbc/car/hyundai/carcontroller.py`
  - `opendbc_repo/opendbc/car/hyundai/hyundaican.py`
  - `opendbc_repo/opendbc/car/hyundai/hyundaicanfd.py`
  - `opendbc_repo/opendbc/car/hyundai/radar_interface.py`

## P2: ESCC 必迁

- [x] 从 `fishop/openpilot:cp` 提取 ESCC 相关改动。
- [x] 不直接整包合并 fishop 分支，先拆成最小功能补丁。
- [x] 迁移参数：
  - `EnableEscc`
  - `EnableRadarTracks`
  - `EnableRadarTracksResult`
  - `HyundaiCameraSCC`
  - `CanfdHDA2`，只保留为其它车兼容项，Seltos 2023 不走 CANFD/HDA2 路径。
  - `RadarLatFactor`
  - `EnableCornerRadar`
- [x] 迁移 Hyundai 安全标志和 ESCC 标志。
- [x] 迁移 ESCC 雷达解析逻辑。
- [x] 迁移 ESCC AEB/SCC 消息保留逻辑。
- [x] 迁移 ESCC 与 openpilot longitudinal control 的启用条件。
- [x] 给 Seltos 2023 优先加默认保护：默认关闭 ESCC，必须显式参数开启。
- [x] Seltos 2023 不默认开启 CANFD、HDA2、CanfdHDA2 相关 flag。
- [x] 做一次静态检查：所有 ESCC 路径都必须有参数开关保护。
- [ ] 做一次上车前 dry-run：确认无缺失 capnp、DBC、Params key。

## P2.5: C3 克隆版离线模式

- [x] 新增 `AlwaysOffline` 参数，个人 C3 克隆版默认开启。
- [x] 设置菜单加入“离线使用模式”。
- [x] 开启后跳过在线注册。
- [x] 开启后禁用后台更新。
- [x] 开启后禁用远程连接和上传相关流程。
- [x] 开启后驻车按 Cancel 不主动关机。
- [ ] 上车确认 ACC/CAN 供电断电重启后能直接进入系统。

## P3: 机械小哥功能整合

- [x] `jixiexiaoge/openpilot:CP` 已基本进入 `ajouatom/c3-wip`，先不重复合并。
- [x] 从 `jixiexiaoge/openpilot:atune` 完成初步拆分评估。
- [x] 写入 [机械小哥 atune 整合计划](ATUNE_INTEGRATION_PLAN.md)。
- [x] 新开 `personal/c3-escc-atune` 分支。
- [x] 第一批只迁移 Auto-Tuner 核心，默认关闭，禁止自动应用。
- [ ] 第二批再做推荐值 UI 和手动确认流程。
- [ ] 从 `jixiexiaoge/openpilot:master` 记录 CP搭子 / Navipilot 功能边界。
- [ ] 机械小哥功能分批迁移：
  - [ ] CP搭子导航桥接兼容。
  - [ ] 7000 Web 控制台增强。
  - [ ] 自动实验模式切换。
  - [ ] 模型选择切换器。
  - [ ] 自动超车。
  - [ ] 驾驶报告。
  - [ ] LED / cluster HUD。
  - [x] Auto-Tuner / atune 第一批核心学习器。
- [ ] 每批迁移都单独提交，避免以后更新冲突时无法回滚。

## P4: fishop 非 ESCC 功能整合

- [ ] 从 `fishop/openpilot:cp` 拆出国内导航/APP 控制功能。
- [ ] 评估 `amap_navi.py` 与机械小哥 CP搭子的功能重叠。
- [ ] 评估转向灯板控制、雷达/激光雷达盲区、APP 控制变道、纵控平顺停车等功能。
- [ ] 决定哪些进入主分支，哪些放到实验分支。

## P5: C4 旁支

- [ ] 不作为主线目标。
- [ ] 建立 `tracking/c4` 或 `experimental/c4` 分支。
- [ ] 只在低成本时跟踪，不影响 C3/Seltos/ESCC 主线。

## P6: 发布和安装

- [ ] 给每个可上车版本打 tag，例如 `seltos-c3-escc-YYYYMMDD`.
- [ ] 写安装说明。
- [ ] 写回滚说明。
- [ ] 保留上一个稳定版本。
- [ ] 只把稳定 tag 作为设备安装目标，不直接安装日常开发分支。

## P7: 中文翻译和参数说明优化

低优先级，等 ESCC 和离线模式先稳定。

- [ ] 梳理 `selfdrive/carrot_settings.json` 中明显机翻、韩文残留和含糊描述。
- [ ] 优先改启动、现代/起亚、雷达、纵控、转向相关参数说明。
- [ ] 给危险或容易误解的参数补“适用车型/默认建议/风险提示”。
- [ ] 不改参数含义和默认值，只改显示文字。
- [ ] 每批翻译单独提交，方便回滚。
