# 研究快照：2026-06-17

本文件记录本轮调查时看到的远端状态。后续更新时以实时远端为准。

## 用户约束

- 设备：C3 中国克隆版，不是 C3X。
- 车辆：Kia Seltos 2023。
- 实际可用配置：直接选择 Kia Seltos 2021 可以使用。
- 项目目标：新建 Seltos 2023 独立车型条目，初期复用 Seltos 2021 配置。
- 车辆总线：纯 CAN，不是 CANFD。
- 必迁：fishop / 飞扬线里的 ESCC 硬件支持。
- 必备：Always Offline 模式，适配 ACC/CAN 供电、熄火断电、无法在线注册的 C3 克隆版。
- 目标：尽量整合机械小哥和 fishop 的全部实用功能。
- C4：可旁支维护，但不影响 C3 主线。
- 低优先级：清理 Korean/机翻式中文菜单和抽象参数说明。

## 上游分支快照

`ajouatom/openpilot`

- `c3-wip`: `b12f694`，2026-06-17，`hotfix: enable cweb_push process`
- `carrot-wip`: `0211a1c`，2026-06-17，`Remove cluster libyuv H264 dependency (#402)`
- `c3`: `fe21f2d`，2026-05-20，`carrot_v260520`

判断：用户主线应跟 `c3-wip`。

`jixiexiaoge/openpilot`

- `CP`: `d988b77`，2026-06-15，`Gate gas resume on accelerator disengage setting`
- `atune`: `c045fca`，2026-06-16，`Gate gas resume on accelerator disengage setting`
- `master`: `3b039d2`，2026-06-14，`Update sync-branches.yml`

判断：

- `CP` 当前已经是 `ajouatom/c3-wip` 的祖先，只比上游少 3 个提交。
- `atune` 是后续在线/自动调参重点来源。
- `master` 更像 CP搭子 / Navipilot 应用和文档入口。

`fishop/openpilot`

- 仓库：`https://jihulab.com/fishop/openpilot.git`
- `cp`: `aad1330`，2026-06-14，`longcontrol.py:删除测试功能代码`
- `escc-cpv9`: `f8eaf06`，2026-01-30，`carrot_v260130`
- `cpv9`: `2165c35`，2026-02-08，`carrot_v260208`
- `cpv9-dev`: `34b3303`，2026-06-14，`amap_navi.py:增加APP可通过CP控制外挂的转向灯板`

判断：

- `gitop.vip/cp` 安装器硬编码拉取 `fishop/openpilot.git` 的 `cp` 分支。
- ESCC 不应只从旧 `escc-cpv9` 拿，当前 `cp` 分支里已经包含更多相关改动和后续修复。

`dhvms/carrotpilot`

- `master`: `be766a9`，2024-02-03，`Update README.md`

判断：

- 这是旧 CarrotPilot 线，不适合作为当前底座。
- 可参考 Radar Tracks、SCC 改线 BUS2、APM/APN 的历史说明。

## 发现的关键事实

`gitop.vip/cp` 返回的是 ARM64 Linux ELF 安装器，不是 Git 仓库。

静态 `strings` 检查发现：

- 仓库：`https://jihulab.com/fishop/openpilot.git`
- 分支：`cp`
- 安装路径逻辑包含 `/data/openpilot`、`/data/tmppilot`、`git remote set-branches --add origin cp`

## ESCC 重点路径

在 `fishop/cp` 中看到的关键参数和路径：

- `EnableEscc`
- `EnableRadarTracks`
- `EnableRadarTracksResult`
- `RadarLatFactor`
- `EnableCornerRadar`
- `HyundaiCameraSCC`
- `CanfdHDA2`
- `opendbc_repo/opendbc/car/hyundai/interface.py`
- `opendbc_repo/opendbc/car/hyundai/radar_interface.py`
- `opendbc_repo/opendbc/car/hyundai/carcontroller.py`
- `opendbc_repo/opendbc/car/hyundai/carstate.py`
- `opendbc_repo/opendbc/car/hyundai/hyundaican.py`
- `opendbc_repo/opendbc/car/hyundai/hyundaicanfd.py`
- `opendbc_repo/opendbc/car/hyundai/values.py`

## 初步执行顺序

1. 建 GitHub 仓库和 `ajouatom/c3-wip` 底座。
2. 建 Seltos 2023 独立车型条目，初期复用 Seltos 2021 配置。
3. 从 `fishop/cp` 拆 ESCC 最小补丁。
4. 验证 ESCC 默认关闭时行为等同上游。
5. 开启 ESCC 做 Seltos 专项验证。
6. 再拆机械小哥 `atune`。
7. 再拆 CP搭子 / Navipilot / Web / 自动超车等扩展功能。
