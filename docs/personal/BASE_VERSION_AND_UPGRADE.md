# 底座版本和升级路线

## 当前结论

本项目当前底座是：

```text
ajouatom/openpilot:c3-wip
```

它不是官方 openpilot 1.0 级代码，也不是 0.10.x 级代码。按仓库内证据判断，它更接近 openpilot 0.9.9 前后的 C3/CarrotPilot 代码底子，再叠加 ajouatom/CarrotPilot 自己长期维护的功能。

## 证据

仓库根目录记录的官方来源提交：

```text
git_src_commit: ce355250be726f9bc8f0ac165a6cde41586a983d
git_src_commit_date: 1741413843 2025-03-07 22:04:03 -0800
```

该提交标题：

```text
[bot] Update Python packages (#34819)
```

仓库内 `RELEASES.md` 的最新官方版本记录停在：

```text
Version 0.9.9 (2025-04-30)
```

本仓库当前没有 0.10.x 或 1.0 的官方 release 记录。机械小哥远端里可以看到 `xnor-c3` 分支标题写过 `openpilot v0.10.1`，也能看到 `Dragonpilot-0.11.0` 分支，但那不是本项目当前底座。当前没有确认到明确的 CarrotPilot `1.0` 分支。

因此更准确的叫法是：

```text
openpilot 0.9.9-era CarrotPilot C3-WIP
```

不要把它称为：

```text
openpilot 1.0
openpilot 0.10.x
官方 release3 原版
```

## 对本项目的影响

### C3 克隆版优先

用户硬件是 C3 中国克隆版，不是 C3X。当前 0.9.9-era C3-WIP 底座更贴近 C3 旧安装器、Qt setup installer、旧 AGNOS/C3 使用习惯。短期内不应为了追版本号而切换到 0.10.x 或 1.0 级底座。

### ESCC 优先

马上飞扬/鱼店 ESCC 支持是必移植项。ESCC、Always Offline、Seltos 2023 纯 CAN、C3 二进制安装器这些主目标完成并实车稳定前，不做大版本 rebase。

### 机械小哥功能采用移植策略

CP搭子/Navipilot、在线调参、模型切换、AmapNavi、自动超车、驾驶报告等功能优先按模块审查后移植，不直接把主底座切到机械小哥较新的分支。这样可以避免把 C3 克隆版、ESCC、旧安装流程一起带进未知状态。

模型选择器尤其要谨慎。它可以通过 `carrot_modeld`、`/data/models`、ONNX 下载、tinygrad 编译和自定义 parser 支持 OPv10/OPv11/OPv12、op11、Op model16 等更新模型，但这不等于当前底座升级到了 1.0。详细记录见 [Model Selector 研究记录](MODEL_SELECTOR_RESEARCH.md)。

### C4 线低优先级

C4/新架构线可以保留研究价值，但不要影响 C3/Seltos/ESCC 主线。只有当 C3 主线稳定后，再评估是否开一个单独分支研究 0.10.x/1.0 级迁移。

## 升级策略

短期策略：

- 主线继续基于 `ajouatom/openpilot:c3-wip`。
- 上游更新先通过 `scripts/personal/upstream_update_plan.py` 比较。
- 只 cherry-pick 明确需要的 C3、ESCC、Seltos、Always Offline、CP搭子功能。
- 不把 daily install target 指向开发分支。

中期策略：

- 第一版 `stable` 必须先完成 C3 实车证据包。
- stable 之前，只发布 `staticN` 和 `testN`。
- 安装入口使用二进制安装器和 `install-c3-escc-test` 分支。

长期策略：

- 另开迁移研究分支，例如 `research/openpilot-0.10-c3-escc`。
- 先比对 opendbc、panda safety、manager/registration、installer、modeld、CarrotPilot UI/Web 参数体系。
- 不在主线直接 rebase 到 0.10.x/1.0，除非 C3 克隆版启动、ESCC 0x2AB、Always Offline、Seltos 2023 全部重新验证通过。

## 复查命令

```bash
python3 scripts/personal/base_version_check.py
```

该检查只证明文档和仓库内版本证据一致，不证明实车稳定。
