# 机械小哥 atune 整合计划

记录日期：2026-06-17

对比对象：

- 当前底座：`ajouatom/openpilot:c3-wip`，`b12f694fd5aa`
- 当前个人分支：`personal/c3-escc`，`04cb57afba19`
- 机械小哥调参分支：`jixiexiaoge/openpilot:atune`，`c045fcabb8a1`

## 当前结论

`jixiexiaoge/openpilot:atune` 不能整分支合并。

它不只是自动调参，还包含 Web 控制台、地图、cluster HUD、USB 小屏、视觉诊断、终端工具、截图/录像、若干 Hyundai/CANFD 小改动和大量静态资源。仅 `selfdrive/carrot` 范围就超过 5 万行新增。直接合并会让后续跟随最新版 CarrotPilot 的成本急剧上升，也会让 ESCC 和 Seltos 2023 的安全回归变得难查。

因此采用拆分迁移：

- 第一批只迁移 Auto-Tuner 核心。
- 默认关闭，仅收集和推荐，不自动改车。
- Seltos 2023 / C3 / ESCC 行为不被默认改变。
- 每批单独提交，方便回滚。

## 第一批：Auto-Tuner 核心

目标是把自动/在线调参的核心学习器接进来，但不让它默认影响车辆控制。

状态：已在 `personal/c3-escc-atune` 第一批实验接入。当前版本只收集数据和生成推荐，不自动应用。

计划文件：

- `selfdrive/carrot/carrot_learning.py`
  - 已引入轻量核心学习逻辑。
  - 保留参数范围 clamp 和 factory default 表。
  - 初期不接复杂 Web 控制台。
- `common/params_keys.h`
  - 加入 `CarrotLearningActive`，默认 `0`。
  - 加入 `CarrotLearningData`、`CarrotLearningRecommend`、`CarrotLearningPopupReady`、`CarrotLearningHistory`。
  - 加入 `CarrotTunerApplyLat`、`CarrotTunerApplyLong`，但第一批默认建议不自动写入控制参数。
  - `CarrotLearningAutoApply` 必须默认 `0`。
  - `CarrotDSP*` 可以先加入占位，但不启用驾驶风格自动套用。
- `selfdrive/carrot/carrot_functions.py`
  - 使用 guarded import。
  - 只有 `CarrotLearningActive=1` 时才收集学习数据。
  - 学习器异常必须被隔离，不能让 planner 崩。
  - 不改变现有 `tFollow`、加速度、转向默认值。
- `selfdrive/carrot_settings.json`
  - 已加一个小的“自动调参”设置区。
  - 已放核心开关：启用学习、允许横向建议、允许纵向建议、允许自动应用、清空学习数据。
  - 自动应用默认关闭，并在中文说明里写清风险。

第一批不包含：

- `selfdrive/carrot/cluster/`
- cybertruck cluster 模型资源
- `selfdrive/carrot/kmap/`
- 视觉诊断 / raw camera / WebRTC 扩展
- 终端命令扩展
- 远程 Web 控制台大改版
- Tesla 相关文件
- 与 Seltos 2023 无关的 CANFD/HDA2 改动
- 大批量翻译重写

## 第二批：推荐值 UI 和确认流程

第一批稳定后，再做可读的推荐值入口。

状态：已在 `personal/c3-escc-atune` 接入 Web 推荐面板和手动应用 API。实车浏览器验证未完成。

目标：

- 展示推荐参数、当前值、建议值、变化原因。
- 用户停车后手动确认应用。
- 支持“只应用横向”“只应用纵向”“本次忽略”“清空学习数据”。
- 记录应用历史到 `CarrotLearningHistory`。
- 不在行驶中弹出遮挡式交互。

当前实现不合入整套 Web 控制台，只在已有 Carrot 设置页的“自动调参”分组顶部增加一个轻量推荐面板。

## 第三批：驾驶风格画像 DSP

`atune` 里还有 `DrivingStyleProfiler` 方向，用于根据手动驾驶风格给初始参数建议。

这部分暂时放到第三批，原因：

- 它会把手动驾驶习惯转换为默认参数，误判成本比普通推荐更高。
- 用户当前优先级是 ESCC、Seltos 2023、离线模式和可更新维护。
- 需要实车数据确认以后再打开。

第三批原则：

- 默认关闭。
- 只产生建议，不自动应用。
- 必须能一键清空历史。

## 第四批：Web / CP搭子 / 在线控制

`atune` 分支的大量改动在 Web 和在线控制台一侧。这些功能可以很有用，但会显著增加维护负担。

先只记录，不进入主线：

- Web 控制台增强
- 设备设置页面扩展
- 地图和导航 HUD
- vision diagnostic
- terminal commands
- SSH key 管理
- cluster HUD 和 USB 小屏

如果以后要做，建议单独开 `personal/c3-escc-web` 或 `experimental/web-console`，不要和 ESCC 主线混在一起。

## 安全约束

迁移 Auto-Tuner 时必须满足：

- `EnableEscc` 默认仍为 `0`。
- `AlwaysOffline` 默认仍为 `1`。
- Seltos 2023 仍复用 Seltos 2021 配置。
- 不默认开启 CANFD、HDA2、camera SCC 或其它非纯 CAN 路径。
- 不改 panda safety 的诊断限制。
- 不改当前 ESCC DBC 和 radar parser 行为。
- 不改现有用户参数默认值，除非单独说明并经过上车确认。
- `CarrotLearningAutoApply=0` 时，学习器不能写入实际控制参数。

## 测试清单

本地检查：

- [ ] `git diff --check`
- [ ] `python -m json.tool selfdrive/carrot_settings.json`
- [ ] Python 语法检查：
  - `selfdrive/carrot/carrot_learning.py`
  - `selfdrive/carrot/carrot_functions.py`
- [ ] 默认关闭时，`CarrotPlanner` 初始化不要求学习器运行。
- [ ] 默认关闭时，不写入 `CarrotLearningData`。
- [ ] 开启学习后，模拟输入能写入推荐数据，但不自动改 `CruiseMaxVals*`、`TFollowGap*`、`PathOffset` 等实际控制参数。
- [ ] `CarrotLearningAutoApply=0` 时，推荐值只进入推荐区。
- [ ] `CarrotLearningClear` 能清空学习数据。
- [ ] Web API 行驶中拒绝应用推荐。
- [ ] Web 设置页能显示并手动应用推荐。

上车前检查：

- [ ] 先在停车状态启动，确认无 manager crash。
- [ ] 先保持 Auto-Tuner 关闭，确认 ESCC 和离线模式无回归。
- [ ] 再只开启学习，不开启自动应用。
- [ ] 第一次路测只观察推荐值，不应用。
- [ ] 手动应用前保存 `/data/params` 快照。

## 分支和提交顺序

建议新开分支：

`personal/c3-escc-atune`

提交顺序：

1. `Add atune params disabled by default`
2. `Import CarrotLearner without auto apply`
3. `Add guarded Auto-Tuner collection hook`
4. `Add Auto-Tuner settings entries`
5. `Add recommendation review UI`

如果任何一步出问题，可以回滚单个提交，不影响当前已经完成的 ESCC / Seltos / Always Offline 主线。
