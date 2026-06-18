# 最新模型 supercombo 实验线计划

本文件只定义第三条实验线怎么开，不代表当前可安装版本已经迁移到官方 master 最新模型栈。

更新：2026-06-19 的 SunnyPilot / Mr.One 研究显示，新版目标应优先拆成两个层级：

- 0.11+ 架构和 C3 兼容：见 `SUNNYPILOT_C3_LATEST_ARCHITECTURE_PLAN.md`。
- 最新模型 / `modeld_v2` / 模型管理器：仍按本文作为 alpha 线推进。

不要直接把 Mr.One 当基座。Mr.One `devc3` 和 `res` 只作为 C3/TICI 兼容补丁参考。

## 目标

第三条线命名建议：

```text
experimental/latest-model-supercombo
```

目标是研究并最小化移植官方 master 的最新 `driving_supercombo.onnx` / `big_driving_supercombo.onnx` 运行栈。它和 `experimental/op-011-c3` 分开维护；0.11/C3 稳态迁移先保证设备可启动和车辆安全，supercombo 线只做模型运行栈实验。

安装器可以暴露这条线为 `--channel alpha`，但 `alpha` 不是默认安装目标，也不是日常驾驶目标。由于当前二进制安装器模板只支持不带 `/` 的短分支，alpha 安装入口使用短分支 `alpha-supercombo`，并让它镜像开发分支 `experimental/latest-model-supercombo`。

## 当前事实

当前个人版模型栈：

- `selfdrive/modeld/modeld.py` 分别加载 `driving_vision_tinygrad.pkl` 和 `driving_policy_tinygrad.pkl`。
- `SConscript` 分别编译 `driving_vision.onnx`、`driving_policy.onnx`、`dmonitoring_model.onnx`。
- `Parser` 仍分 `parse_vision_outputs` 和 `parse_policy_outputs`。

官方 master 最新模型栈：

- `selfdrive/modeld/models/` 里是 `driving_supercombo.onnx`、`big_driving_supercombo.onnx`、`dmonitoring_model.onnx`。
- `SConscript` 通过 `compile_modeld.py --onnx ...driving_supercombo.onnx` 生成 `driving_tinygrad.pkl`。
- `modeld.py` 通过 `compile_modeld.make_input_queues()` 建立输入队列，一次运行 `run_policy()` 得到完整输出。
- `parse_model_outputs.py` 使用单一 `parse_outputs()`，不再拆成 vision/policy 两段。
- `fill_model_msg.py` 新增/使用 `fill_driving_model_data()`，同时发布 `modelV2` 和 `drivingModelData`。

Mr.one `devc3` 参考线：

- 基座接近 sunnypilot / openpilot 0.11.1。
- 仍是 `driving_vision + driving_policy` 两段模型结构，并不是官方 master 的 supercombo 结构。
- 适合参考 C3/C3X/0.11 启动和硬件适配，不适合作为 supercombo 线的直接基座。

## C3 / C3X / C4 基座判断

官方当前 README 把 release 分支分成：

- comma four: `release-mici`
- comma 3X: `release-tizi`

源码硬件层仍以 `/TICI` 进入 tici 类硬件路径，但 `system/hardware/tici/hardware.h` 里会进一步区分设备树 model：

- `tici`: comma 3 / C3 类路径
- `tizi`: comma 3X / C3X 类路径
- `mici`: comma four / C4 类路径

Mr.one 安装器里有 `release3 -> release-tizi` 的迁移映射，说明它更像在把三代设备入口映射到 C3X/TIZI 预编译线。对 C3 中国克隆版不能直接假设等同 C3X 或 C4；必须先在真机上读取：

```bash
cat /sys/firmware/devicetree/base/model
test -f /TICI && echo TICI
test -f /AGNOS && echo AGNOS
```

如果克隆 C3 报告为 `tici`，应优先从 tici 路径向新模型栈移植；如果它被系统伪装为 `tizi`，再参考 Mr.one 的 `devc3` / `release-tizi` 经验。C4 的 `mici` 线可以参考，但不能直接作为本车机安装基座。

## 开线方式

从当前个人整合分支开实验线：

```bash
git switch personal/c3-escc-atune
git pull --ff-only github personal/c3-escc-atune
git switch -c experimental/latest-model-supercombo
git push -u github experimental/latest-model-supercombo
```

这条线可通过脚本安装器 `--channel alpha` 指向短安装分支 `alpha-supercombo`，但初期不要接入默认 `latest`，不要移动 `install-c3-escc-test`，不要上传为默认 release asset。

同步 alpha 安装别名：

```bash
git branch -f alpha-supercombo experimental/latest-model-supercombo
git push github refs/heads/alpha-supercombo:refs/heads/alpha-supercombo
```

如需 C3 Custom Software 直接安装 alpha，需要用 `build_binary_installer.py --branch alpha-supercombo` 生成单独二进制，不要复用默认 `installer_c3_escc`。

## 第一阶段：只迁模型栈，不碰车辆控制

候选文件组：

```text
selfdrive/modeld/modeld.py
selfdrive/modeld/SConscript
selfdrive/modeld/compile_modeld.py
selfdrive/modeld/compile_dm_warp.py
selfdrive/modeld/helpers.py
selfdrive/modeld/parse_model_outputs.py
selfdrive/modeld/fill_model_msg.py
selfdrive/modeld/constants.py
selfdrive/modeld/models/README.md
selfdrive/modeld/models/driving_supercombo.onnx
selfdrive/modeld/models/big_driving_supercombo.onnx
selfdrive/modeld/models/dmonitoring_model.onnx
cereal/log.capnp
cereal/services.py
common/file_chunker.py
common/transformations/model.py
common/transformations/camera.py
```

实际迁移时不能整目录盲拷，必须逐个 diff。尤其注意：

- `cereal/log.capnp` 字段号不能和 Carrot / ESCC / Navipilot 现有字段冲突。
- `drivingModelData` service 已在当前代码使用，字段结构必须保持兼容。
- `modelV2.action`、`hidden_state`、`raw_pred` 输出 shape 需要和 parser 对齐。
- tinygrad 版本、`compile3.py`、chunk manifest、prebuilt pkl 文件必须一起核对。

## 第二阶段：只做 PC/编译验证

先在电脑上验证：

```bash
python3 -m py_compile selfdrive/modeld/modeld.py selfdrive/modeld/compile_modeld.py selfdrive/modeld/parse_model_outputs.py selfdrive/modeld/fill_model_msg.py
python3 scripts/personal/smoke_check.py
python3 scripts/personal/feature_boundary_check.py
```

如果可以拿到模型 pkl，再做 replay / process 启动级验证。不能只看语法通过。

## 第三阶段：C3 停车启动验证

只在单独实验安装入口上测试：

- 不启用 ESCC。
- 不启用自动调参自动写入。
- 不改 Seltos 2023 车型参数。
- 先确认 `modeld` 不崩、`modelV2` 和 `drivingModelData` 正常发布。
- 确认温度、CPU/GPU 占用、帧率和掉帧。

最低证据：

```bash
python3 scripts/personal/device_snapshot.py --output /data/media/0/supercombo-snapshot.md
python3 scripts/personal/collect_real_car_evidence.py --sample-seconds 30 --archive
```

## 禁止事项

- 不把第三线设为 `latest`。
- 不让二进制安装器默认安装第三线。
- 不把 `alpha` 当作日常驾驶目标。
- 不在第三线未跑通前合回 `personal/c3-escc-atune`。
- 不同时迁 ESCC、车型、AlwaysOffroad、Connect、Navipilot 和 supercombo。

## 判定标准

可以继续推进的条件：

- PC 静态检查通过。
- C3 停车状态 `modeld` 连续运行，不循环崩溃。
- `modelV2`、`drivingModelData`、`cameraOdometry` 发布正常。
- 设备温度和帧率没有明显异常。

必须暂停的条件：

- `modeld` crash loop。
- capnp schema 编译或服务字段冲突。
- C3 上 tinygrad 编译/加载超时或内存不足。
- 摄像头流、driver monitoring 或 manager 启动受影响。
