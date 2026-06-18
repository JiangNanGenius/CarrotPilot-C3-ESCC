# 分支策略

## 原则

主线服务 C3 克隆版和 Seltos 2023。C4 只做旁支，不让它拖慢主线。

ESCC 和 AlwaysOffroad 是主线必保留功能。机械小哥和 fishop 的其它功能尽量全整合，但要分阶段、可回滚。

## 远端

当前远端命名：

```bash
git remote add origin https://github.com/ajouatom/openpilot.git
git remote add github https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git
git remote add jixie https://github.com/jixiexiaoge/openpilot.git
git remote add jixie-navipilot https://github.com/jixiexiaoge/navipilot.git
git remote add fishop https://jihulab.com/fishop/openpilot.git
git remote add dhvms https://github.com/dhvms/carrotpilot.git
```

## 长期分支

`main`

预留给项目说明和管理文档。当前 GitHub 仓库还没有单独 `main`，默认分支临时使用 `personal/c3-escc-atune`，方便先看到最新整合文档。

`upstream/c3-wip`

只同步 `ajouatom/openpilot:c3-wip`，不手改。当前按 CarrotPilot / CarPad 韩国主源处理。

`personal/c3-escc`

主用分支。基于 `upstream/c3-wip`，集成 ESCC 和 AlwaysOffroad，并新建 Seltos 2023 纯 CAN 车型条目。Seltos 2023 初期复用 Seltos 2021 配置。

`personal/c3-escc-atune`

在 `personal/c3-escc` 稳定保护线上继续集成机械小哥 atune/在线调参。当前 GitHub 默认分支指向这里，但上车安装仍应优先使用验证过的 tag。

`tracking/fishop-cp`

跟踪 `fishop/openpilot:cp`，用于提取 ESCC 和国内硬件功能。`gitop.vip/cp` 静态检查显示实际安装器拉取的就是这条线。

`tracking/jixie-atune`

跟踪 `jixiexiaoge/openpilot:atune`，用于提取在线/自动调参和 Web 功能。

`tracking/jixie-master`

跟踪 CP搭子 / Navipilot 文档和应用方向，不一定直接合进 openpilot 代码。

`tracking/jixie-navipilot`

跟踪 `jixiexiaoge/navipilot:CPdazi`，用于检查 Android CP搭子 APP、驾驶报告、WebSocket 需求、模型/参数管理和自动超车 UI 的变动。不把 Android 项目直接合进 openpilot 主分支。

`tracking/model-selector`

跟踪 `ajouatom/openpilot:happymaj11r/carrot-wip-model_selector`，用于研究 modeld 模型选择器、模型下载/签名校验、编译和回滚策略。当前只作为参考线和静态审计来源，不进入默认 C3/Seltos/ESCC 主线。

`tracking/c4`

C4 旁支。当前本地暂按 `origin/carrot-wip` 跟踪；后续需要再确认这是否就是目标 C4 线。只有在维护成本不高时跟进。

## GitHub 上游基准

本地保留 `upstream/c3-wip` 和 `tracking/*` 分支，方便人工维护和 rebase。GitHub Actions 不直接依赖这些本地分支，而是读取 [UPSTREAM_BASELINES.json](UPSTREAM_BASELINES.json) 里的已审查 commit。

`Upstream Watch` 每周自动拉取 ajouatom、jixiexiaoge、fishop 的最新分支，并用 `scripts/personal/update_audit.py --baseline-file docs/personal/UPSTREAM_BASELINES.json --strict` 和这些基准 commit 比较。工作流变红时，不代表当前车机分支坏了，而是提醒需要人工审查上游更新、高风险目录和是否更新基准清单。

本地维护时先跑 `python3 scripts/personal/upstream_update_plan.py --fetch`。它不会默认改代码，只把每条来源的 remote/local 状态、高风险文件和建议命令列出来。审查后如果只是 tracking 分支严格落后，可以运行 `python3 scripts/personal/upstream_update_plan.py --fetch --apply-tracking` 快进本地 `upstream/*` / `tracking/*`；确认后再用 `--write-baselines` 更新 GitHub Actions 使用的基准文件。

## 合并顺序

1. 运行 `python3 scripts/personal/update_audit.py --fetch` 和 `python3 scripts/personal/upstream_update_plan.py --fetch`，确认哪些来源有新提交、高风险目录变化，以及哪些 tracking 分支可快进。
2. `upstream/c3-wip` 同步最新版。
3. `personal/c3-escc` rebase 或 merge 上游。
4. 解决 ESCC 冲突。
5. 跑检查单。
6. 打测试 tag。
7. 上车低风险验证。
8. 稳定后再合 atune/CP搭子功能。

## 不建议的做法

- 不建议直接 fork `fishop/cp` 当底子，因为它和最新 C3 CarrotPilot 差距较大。
- 不建议直接把 `fishop/cp` 整个 merge 到 C3 最新版，因为会混入大量非 ESCC 改动。
- 不建议把 `dhvms/carrotpilot` 当作当前官方底座；它只保留旧版说明和历史实现参考价值。
- 不建议把 C4 和 C3 放在同一个实车主分支里维护。
- 不建议自动把上游更新推到设备安装分支。
