# 安装和回滚说明

本说明面向当前个人分支：

- 设备：C3 中国克隆版，不是 C3X。
- 车辆：Kia Seltos 2023，纯 CAN，不是 CANFD。
- 车型配置：新建 `Kia Seltos 2023`，初期复用 `Kia Seltos 2021`。
- ESCC：有硬件才开启，默认关闭。
- 离线模式：`AlwaysOffline` 默认开启。

## GitHub 仓库

- 仓库：`https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC`
- 主用保护分支：`personal/c3-escc`
- 当前整合分支：`personal/c3-escc-atune`

日常开发和功能整合可以在分支上推进，但设备长期安装目标建议使用经过静态检查和实车验证后的 tag。

当前静态检查 tag：

- `carrotpilot-c3-escc-20260618-static28`
- 只代表静态检查通过，不代表实车验证。

当前受控上车测试 tag：

- `carrotpilot-c3-escc-20260618-test22`
- 用于停车静态检查、证据采集和低速短程验证。
- 不作为日常稳定安装目标。

- 目前还没有 `stable` tag。

机器可检查的安装目标记录在 [INSTALL_TARGETS.json](INSTALL_TARGETS.json)。当前 `daily_install_target` 必须为空，因为还没有完成 Seltos 实车验证和 `stable` 发布。

## 本地预检

更新、合并或上车前先跑：

```bash
python3 scripts/personal/smoke_check.py
python3 scripts/personal/escc_offline_preflight.py
```

`escc_offline_preflight.py` 只能证明代码里的 capnp、DBC、Params key、设置默认值和 ESCC/离线路径引用完整；它不能替代实车确认 0x2AB、ACC 断电重启、SCC/AEB 状态。

## Release 和安装器

GitHub Release 只负责记录“这次可安装的版本、检查状态和注意事项”。Release 自动带的 zip/tar.gz 是源码快照，不是车机安装包；车机真正安装时仍然应该拉取一个 git tag 或运行安装器。

`installer.comma.ai` 的公开入口提示格式是 `用户名或组织/分支`，例如 `commaai/master-ci`。这说明官方安装入口偏向固定仓库/分支格式；本项目仓库名是 `CarrotPilot-C3-ESCC`，所以不要假设官方入口能直接安装这个仓库名。

鱼店/马上飞扬的 `gitop.vip/cp` 是一个 AArch64 ELF 安装器二进制，它内置了 `https://jihulab.com/fishop/openpilot.git` 和 `cp` 分支，并会把代码放到 `/data/openpilot`。本项目先提供一个更透明的脚本安装器，后续如果需要一键输入短链接，再单独做同款 C3 GUI 二进制安装器。

当前主安装入口是 C3 二进制安装器。它的形态和 `gitop.vip/cp` 同类，适合在 C3 初装/Custom Software 流程里使用：

```bash
https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC/releases/download/carrotpilot-c3-escc-20260618-test22/installer_c3_escc
```

二进制安装器实际拉取的是安装分支：

```text
install-c3-escc-test
```

该分支会指向当前受控测试 tag `carrotpilot-c3-escc-20260618-test22` 对应提交。二进制安装器使用分支而不是 tag，是因为旧 Qt installer 内部会执行 `git reset --hard origin/<branch>`。

SSH 维护或救援时仍可使用脚本安装器：

```bash
curl -fsSL https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC/releases/download/carrotpilot-c3-escc-20260618-test22/install_c3_escc.sh | sh
```

脚本默认安装 `carrotpilot-c3-escc-20260618-test22`，备份旧 `/data/openpilot` 到 `/data/carrotpilot-backups/`，更新 `/data/continue.sh`，并写入首次启动安全参数：`AlwaysOffline=1`、`EnableConnect=0`、`EnableEscc=0`、`CanfdHDA2=0`、`HyundaiCameraSCC=0`、`EnableRadarTracks=0`。

如果要先看脚本会做什么：

```bash
curl -fsSL https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC/releases/download/carrotpilot-c3-escc-20260618-test22/install_c3_escc.sh | sh -s -- --dry-run
```

二进制安装器研究记录见 [C3 二进制安装器研究](BINARY_INSTALLER_RESEARCH.md)。如果以后已经有 `stable` tag，安装分支会改为指向 stable；在此之前，它只能作为受控测试安装入口。

## 安装前

先记录当前设备可用版本和关键参数：

- 当前安装 URL 或分支。
- 当前能正常使用的车型选择。
- `/data/params` 中和车辆、ESCC、离线模式相关的参数。
- 上一个稳定 tag 或可回滚安装地址。

如果当前设备上正在跑 fishop / 飞扬版本且状态正常，优先按 [从旧版本迁移安全参数](CONFIG_MIGRATION.md) 导出一份设置白名单。这样安装本项目版本后，可以先 dry-run 对比，再只导入 ESCC、Camera SCC、雷达、离线模式和调参相关设置。

安装本项目版本后，可以先跑一次首装向导。它默认不会写参数，只会把迁移 dry-run、静态检查、设备快照、证据包和 readiness 报告放进同一个目录：

```bash
cd /data/openpilot
python3 scripts/personal/c3_commissioning.py \
  --migration-input /data/media/0/carrotpilot-fishop-working-params.json \
  --archive
```

确认 `migration-import-output.txt` 没有异常后，才考虑加 `--apply-migration` 重新运行。

可在 C3 上运行设备快照脚本，生成不含 VIN / dongle id / token 的状态记录：

```bash
python3 scripts/personal/device_snapshot.py --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

不要把日常开发分支直接作为长期安装目标。建议只安装已经打过 tag 的测试版或稳定版。

如果为了准备上车静态检查而安装 `static` tag，先把它当作“受控测试版本”，不要把它当作日常稳定版本。

安装前可在本地仓库先确认安装目标清单没有误写成开发分支：

```bash
python3 scripts/personal/install_target_check.py
```

安装到 C3 后，可以在设备上运行静态检查向导。它会确认当前 tag、跑预检、检查建议参数，并生成设备快照：

```bash
cd /data/openpilot
python3 scripts/personal/c3_static_check.py \
  --output /data/media/0/carrotpilot-c3-escc-static-check.md \
  --snapshot-output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

停车并准备采样 ESCC 0x2AB 时，再加 `--sample-seconds 20`。

如果想把静态检查、设备快照、路测模板和清单放到同一个文件夹，推荐直接运行证据采集器：

```bash
cd /data/openpilot
python3 scripts/personal/collect_real_car_evidence.py --archive
```

如果是刚安装完本项目版本，更推荐先用首装向导：

```bash
python3 scripts/personal/c3_commissioning.py --archive
```

停车并准备采样 ESCC 0x2AB 时：

```bash
python3 scripts/personal/collect_real_car_evidence.py --sample-seconds 20 --archive
```

如果这次同时准备验证 CP搭子 / Navipilot，停车状态下可让证据包额外检查 C3 侧 APP 端点：

```bash
python3 scripts/personal/collect_real_car_evidence.py \
  --sample-seconds 20 \
  --navipilot-check \
  --navipilot-param-write-probe \
  --archive
```

如需同时验证 7706 导航输入链路，再加 `--navipilot-send-test-nav`。该测试包不会发送 `LANECHANGE` 或 `OVERTAKE`，但仍建议只在停车状态下使用。

把证据包拷回电脑并解压后，可以直接让校验器读取整个目录：

```bash
python3 scripts/personal/evidence_readiness_report.py \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS
```

这个报告会分阶段告诉你设备快照、CarParams、ESCC 0x2AB、路测记录和 stable gate 还缺哪一项。准备正式升 `stable` 时，再跑严格校验：

```bash
python3 scripts/personal/road_test_evidence_check.py \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS \
  --require-device-snapshot \
  --require-carparams-summary \
  --require-offline-process-guard \
  --require-escc-sample
```

验证 CP搭子 / Navipilot 端点时，可额外要求 live check 通过：

```bash
python3 scripts/personal/road_test_evidence_check.py \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS \
  --require-device-snapshot \
  --require-carparams-summary \
  --require-cplink-sample \
  --require-navipilot-live-check
```

## 建议参数

Seltos 2023 初期建议：

- `AlwaysOffline=1`
- `EnableEscc=0`
- `HyundaiCameraSCC=0`
- `CanfdHDA2=0`
- `EnableRadarTracks=0`

第一次上车静态验证通过后，再手动开启：

- `EnableEscc=1`

如果开启 ESCC 后没有看到 0x2AB 或出现 SCC/AEB 相关异常，立即关闭 `EnableEscc` 并回滚到上一个稳定 tag。

## 第一次启动

第一级检查只看设备状态，不开车：

- 能进入系统，不反复重启。
- 不因为在线注册卡住。
- 不启动后台更新和远程连接。
- 设置菜单能看到“离线使用模式”和“启用 ESCC 硬件”。
- 车型可以手动选择 `Kia Seltos 2023`。

## 静态上车检查

停车状态下检查：

- 车辆识别为 Seltos 2023 或手动选择 Seltos 2023。
- 确认不是 CANFD/HDA2 路径。
- `EnableEscc=0` 时，行为应接近原 Seltos 2021 可用配置。
- `EnableEscc=1` 后，确认 CAN 中能稳定看到 ESCC 0x2AB。
- 没有 manager crash、CAN error、SCC/AEB 故障提示。

如需记录 0x2AB 和 CP搭子消息计数，可停车后运行：

```bash
python3 scripts/personal/device_snapshot.py --sample-seconds 20 --output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

## 低速验证

只在安全条件下做短时间验证：

- 先不开纵控，只看车道、速度、lead/radarState 是否异常。
- 确认刹车、油门、取消按钮、接管都正常。
- 短时间启用后观察前车距离、相对速度、AEB/FCW 状态。
- 有异常加减速、SCC 故障、AEB 故障或车型路径错误时立即回滚。

## 回滚

保留两个回滚目标：

- 上一个已验证稳定 tag。
- 纯 `ajouatom/openpilot:c3-wip` 底座。

回滚后重新确认：

- 设备能正常启动。
- 车型选择仍可用。
- `EnableEscc` 已关闭或不存在。
- `AlwaysOffline` 状态符合当前设备供电方式。

## 发布 tag 建议

命名格式：

```text
carrotpilot-c3-escc-YYYYMMDD-staticN
carrotpilot-c3-escc-YYYYMMDD-testN
carrotpilot-c3-escc-YYYYMMDD-stable
```

含义：

- `staticN`：只代表静态检查通过，不代表实车验证。
- `testN`：代表准备用于受控上车测试。
- `stable`：只有完成静态启动、低速验证和多次短程验证后才使用。

打 tag 前先运行：

```bash
python3 scripts/personal/release_gate.py --tag carrotpilot-c3-escc-YYYYMMDD-static1 --kind static --run-checks
```

创建 `stable` tag 时可以直接使用同一个证据包目录：

```bash
python3 scripts/personal/release_gate.py \
  --tag carrotpilot-c3-escc-YYYYMMDD-stable \
  --kind stable \
  --evidence-dir /path/to/carrotpilot-c3-escc-evidence-YYYYMMDD-HHMMSS \
  --run-checks
```

升级到 `stable` 前，先复制并填写 [上车测试记录模板](ROAD_TEST_LOG_TEMPLATE.md)，并把 C3 生成的设备快照文件保存到电脑本地。`stable` gate 会要求设备快照里有 `AlwaysOffline=1`、`CanfdHDA2=0`、`EnableConnect=0`、`offline_forbidden_processes_seen=False`，并且至少有一次 `EnableEscc=1`、`enabled=True`、`ok=True` 且 `escc_0x2ab_bus0 > 0` 的采样。

```bash
python3 scripts/personal/release_gate.py \
  --tag carrotpilot-c3-escc-YYYYMMDD-stable \
  --kind stable \
  --road-test-log docs/personal/road_tests/你的记录.md \
  --device-snapshot /path/to/carrotpilot-c3-escc-snapshot.md \
  --run-checks
```

发布 `stable` 后再更新 [INSTALL_TARGETS.json](INSTALL_TARGETS.json)：把 `current_stable_tag` 和 `daily_install_target` 指向新的稳定 tag，并把旧稳定 tag 写入 `previous_stable_tag`。没有旧稳定 tag 时，回滚目标至少保留 `rollback_base_ref`。
