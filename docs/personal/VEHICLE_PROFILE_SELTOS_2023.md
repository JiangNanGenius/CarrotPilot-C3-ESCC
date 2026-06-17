# 车辆档案：Kia Seltos 2023

## 基本信息

- 车辆：Kia Seltos 2023。
- 当前可用配置：直接选择 Kia Seltos 2021 可以使用。
- 项目目标：新建 Kia Seltos 2023 独立车型条目，初期复用 Seltos 2021 配置。
- 设备：C3 中国克隆版。
- 车辆总线：纯 CAN，不是 CANFD。
- 主线目标：C3 CarrotPilot。
- 最高优先级：用户自己的车稳定可用。

## 设计判断

Seltos 2023 应该新建独立车型条目，而不是长期让用户手动选择 Seltos 2021。

第一版实现可以复制或复用 Seltos 2021 的配置，因为用户反馈当前直接选择 Seltos 2021 基本可用，差异很小。

新建车型的目的：

- 以后日志、设置、安装说明里能明确显示 Seltos 2023。
- 后续如果 2023 和 2021 出现 fingerprint、FW、tuning 或 ESCC 差异，可以单独调整。
- 不把用户自己的车长期藏在 2021 车型配置下面。

ESCC 必须作为可开关功能迁入，默认关闭，避免影响其它车型和未验证状态。

## 待确认

- [x] 车辆为纯 CAN。
- [x] 车辆不是 CANFD。
- [x] Seltos 2023 初期不走 HDA2/CANFD 路径。
- [ ] ESCC 硬件接在哪条 bus。
- [ ] 是否需要 `HyundaiCameraSCC`。
- [x] Seltos 2023 不需要 `CanfdHDA2` 强制识别。
- [ ] 原车 SCC 消息是否在 camera、ADAS module 或其它 ECU。
- [ ] 当前可用版本的 Params 快照。
- [ ] 当前可用版本的 CarParams dump。
- [ ] 当前可用版本的 fingerprint / FW dump。

## 新建车型实现计划

- [x] 查清上游当前 Seltos 2021 的车型枚举命名：`CAR.KIA_SELTOS`。
- [x] 新增 Seltos 2023 车型枚举：`CAR.KIA_SELTOS_2023`。
- [x] 新增 Seltos 2023 CarInfo 显示名：`Kia Seltos 2023`。
- [x] 复用 Seltos 2021 DBC 映射。
- [x] 复用 Seltos 2021 lateral/longitudinal 基础参数。
- [x] 复用 Seltos 2021 safety 基础配置，但明确不设置 CANFD/HDA2 flag。
- [ ] 加入 Seltos 2023 fingerprint/FW；如果暂时没有完整 dump，先用 2021 兼容路径并记录 TODO。
- [ ] 保证 Seltos 2021 原车型不受影响。
- [ ] 在 ESCC 参数开启前，Seltos 2023 行为应等同原上游 CAN Seltos 路径。

## 当前代码改动

已在 `openpilot-c3-seltos-escc/opendbc_repo/opendbc/car/hyundai/values.py` 新增：

- `CAR.KIA_SELTOS_2023`
- 显示名：`Kia Seltos 2023`
- harness：复用 `CarHarness.hyundai_a`
- 参数：复用 Seltos 2021 的 `mass=1337`、`wheelbase=2.63`、`steerRatio=14.56`
- flag：复用 `HyundaiFlags.CHECKSUM_CRC8`
- 非必要 ABS ECU 列表中加入 `CAR.KIA_SELTOS_2023`

未改动：

- 未改 Seltos 2021。
- 未改转向 tuning。
- 未改纵控 tuning。
- 未改 DBC。
- 未加 CANFD/HDA2。
- 未复制 FW fingerprint，避免没有实车 dump 时制造 2021/2023 自动识别歧义。

## 优先测试路径

1. 纯上游 `c3-wip` 能否识别并启动。
2. 当前手动选择 Seltos 2021 时行为是否稳定。
3. 新建 Seltos 2023 后，默认行为是否等同 Seltos 2021。
4. ESCC 参数默认关闭时，行为是否等同上游。
5. ESCC 开启后，是否能稳定解析 ESCC lead/radar。
6. 纵控启用前，先验证所有取消和人工接管路径。

## 重点文件

- `opendbc_repo/opendbc/car/hyundai/values.py`
- `opendbc_repo/opendbc/car/hyundai/interface.py`
- `opendbc_repo/opendbc/car/hyundai/carstate.py`
- `opendbc_repo/opendbc/car/hyundai/carcontroller.py`
- `opendbc_repo/opendbc/car/hyundai/hyundaican.py`
- `opendbc_repo/opendbc/car/hyundai/hyundaicanfd.py`
- `opendbc_repo/opendbc/car/hyundai/radar_interface.py`
- `opendbc_repo/opendbc/car/hyundai/fingerprints.py`
- `opendbc_repo/opendbc/dbc/`
- `panda/board/safety/safety_hyundai*.h`

## 明确不适用

- Seltos 2023 不走 CANFD 路径。
- Seltos 2023 不默认设置 HDA2。
- Seltos 2023 不默认设置 `CanfdHDA2`。
