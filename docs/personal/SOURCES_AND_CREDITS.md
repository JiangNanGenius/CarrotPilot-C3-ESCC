# 来源和署名

本项目应保留所有上游项目的许可证、免责声明和贡献来源。

## 主要底座

ajouatom CarrotPilot / CarPad 主源

- 来源：`ajouatom/openpilot`
- URL: `https://github.com/ajouatom/openpilot`
- 计划使用分支：`c3-wip`
- 用途：C3 主底座。
- 当前判断：按用户核对和公开仓库信息，`ajouatom/openpilot` 作为 CarrotPilot / CarPad 的韩国主源处理。
- 验证记录：
  - GitHub 元数据显示该仓库不是 GitHub fork，默认分支为 `carrot-wip`，2026-06-17 仍有推送。
  - README 里保留 Korean legal notice、HKG harness 说明和 `# carrotpilot` 标题。
  - `dhvms/carrotpilot` README 明确写到 CarrotPilot 地址从 `ajouatom/carrotpilot.git` 改到 `ajouatom/openpilot.git`。

## ESCC 和国内硬件支持

fishop / 码上飞扬 / 飞扬

- 来源：`fishop/openpilot`
- URL: `https://jihulab.com/fishop/openpilot.git`
- 计划参考分支：`cp`
- 历史参考分支：`escc-cpv9`
- 发现方式：`gitop.vip/cp` 下载到的是 ARM64 Linux ELF 安装器；静态 `strings` 检查显示实际仓库为 `https://jihulab.com/fishop/openpilot.git`，安装时添加 `cp` 分支。
- 用途：ESCC、Hyundai Camera SCC、CanfdHDA2、Radar Tracks、国内 APP/导航/硬件功能。
- 名称待确认：用户提到可能叫“码上飞扬”。在正式 README 里可写作“fishop / 飞扬（码上飞扬，待确认）”。

## 机械小哥功能

机械小哥 / JixieXiaoGe

- 来源：`jixiexiaoge/openpilot`
- URL: `https://github.com/jixiexiaoge/openpilot`
- 计划参考分支：
  - `CP`: C3 CarrotPilot 线，当前基本已被 `ajouatom/c3-wip` 包含。
  - `atune`: 自动/在线调参。
    - `master`: CP搭子 / Navipilot 设备端和 Web 参考。
- 来源：`jixiexiaoge/navipilot`
- URL: `https://github.com/jixiexiaoge/navipilot`
- 计划参考分支：
  - `CPdazi`: Android CP搭子 APP、驾驶报告、摄像头预览、APP 侧参数/模型/超车 UI 和协议说明。
- 用途：CP搭子、Navipilot、在线调参、7000 Web、自动实验模式、模型切换、自动超车、驾驶报告、LED/cluster HUD 等。

## 历史参考

dhvms

- 来源：`dhvms/carrotpilot`
- URL: `https://github.com/dhvms/carrotpilot`
- 当前判断：旧 CarrotPilot 参考线，不作为官方主源或当前底座。
- 依据：GitHub 元数据显示该仓库不是 GitHub fork，但最新推送停在 2024-03-02；README 自己说明 CarrotPilot 直接安装地址已迁到 `ajouatom/openpilot.git`。
- 用途：旧版 CarrotPilot 的 Radar Tracks、SCC 改线 BUS2、APM/APN 说明和历史实现参考。
- 不建议用途：不作为当前底座，不直接合并整包。

## 正式 README 署名建议

建议在最终项目 README 中写：

```text
Based on the ajouatom CarrotPilot / CarPad C3 source and contributors.
ESCC and related Hyundai/Kia hardware support references fishop / 飞扬（码上飞扬，名称待确认）.
Navipilot / CPlink / atune related ideas and code reference JixieXiaoGe / 机械小哥, including jixiexiaoge/openpilot and jixiexiaoge/navipilot.
Historical CarrotPilot references include dhvms/carrotpilot, but it is not used as the base.
All original licenses and notices are preserved.
```

中文建议：

```text
本项目基于 ajouatom 维护的 CarrotPilot / CarPad C3 主源分支。
ESCC 及部分 Hyundai/Kia 国内硬件支持参考 fishop / 飞扬（码上飞扬，名称待确认）的实现。
CP搭子、Navipilot、在线调参、7000 Web 等功能参考机械小哥 / JixieXiaoGe 的实现，包括 `jixiexiaoge/openpilot` 和 `jixiexiaoge/navipilot`。
同时参考 dhvms/carrotpilot 的历史实现说明，但不把它作为当前底座。
所有上游许可证、免责声明和贡献署名均会保留。
```
