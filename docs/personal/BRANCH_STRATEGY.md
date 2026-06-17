# 分支策略

## 原则

主线服务 C3 克隆版和 Seltos 2023。C4 只做旁支，不让它拖慢主线。

ESCC 和 Always Offline 是主线必保留功能。机械小哥和 fishop 的其它功能尽量全整合，但要分阶段、可回滚。

## 远端

当前远端命名：

```bash
git remote add origin https://github.com/ajouatom/openpilot.git
git remote add github https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git
git remote add jixie https://github.com/jixiexiaoge/openpilot.git
git remote add fishop https://jihulab.com/fishop/openpilot.git
git remote add dhvms https://github.com/dhvms/carrotpilot.git
```

## 长期分支

`main`

预留给项目说明和管理文档。当前 GitHub 仓库还没有单独 `main`，默认分支临时使用 `personal/c3-escc-atune`，方便先看到最新整合文档。

`upstream/c3-wip`

只同步 `ajouatom/openpilot:c3-wip`，不手改。

`personal/c3-escc`

主用分支。基于 `upstream/c3-wip`，集成 ESCC 和 Always Offline，并新建 Seltos 2023 纯 CAN 车型条目。Seltos 2023 初期复用 Seltos 2021 配置。

`personal/c3-escc-atune`

在 `personal/c3-escc` 稳定保护线上继续集成机械小哥 atune/在线调参。当前 GitHub 默认分支指向这里，但上车安装仍应优先使用验证过的 tag。

`tracking/fishop-cp`

跟踪 `fishop/openpilot:cp`，用于提取 ESCC 和国内硬件功能。

`tracking/jixie-atune`

跟踪 `jixiexiaoge/openpilot:atune`，用于提取在线/自动调参和 Web 功能。

`tracking/jixie-master`

跟踪 CP搭子 / Navipilot 文档和应用方向，不一定直接合进 openpilot 代码。

`tracking/c4`

C4 旁支。当前本地暂按 `origin/carrot-wip` 跟踪；后续需要再确认这是否就是目标 C4 线。只有在维护成本不高时跟进。

## 合并顺序

1. `upstream/c3-wip` 同步最新版。
2. `personal/c3-escc` rebase 或 merge 上游。
3. 解决 ESCC 冲突。
4. 跑检查单。
5. 打测试 tag。
6. 上车低风险验证。
7. 稳定后再合 atune/CP搭子功能。

## 不建议的做法

- 不建议直接 fork `fishop/cp` 当底子，因为它和最新 C3 CarrotPilot 差距较大。
- 不建议直接把 `fishop/cp` 整个 merge 到 C3 最新版，因为会混入大量非 ESCC 改动。
- 不建议把 C4 和 C3 放在同一个实车主分支里维护。
- 不建议自动把上游更新推到设备安装分支。
