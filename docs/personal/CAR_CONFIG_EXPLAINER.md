# 车型配置文件里预设了什么

openpilot / CarrotPilot 里的“车型文件”不是只写车名。它们决定这台车如何被识别、怎么读 CAN、怎么发控制、用什么安全限制，以及初始转向和纵控参数。

## 1. 车型身份

这部分决定系统把车识别成什么。

常见内容：

- 车型枚举，例如 Kia Seltos 某年款。
- 显示名称，例如 `Kia Seltos 2023`。
- 车型分组，例如 Hyundai / Kia。
- 是否属于 CAN、CANFD、HDA2、Camera SCC、EV、Hybrid 等类别。

对本项目的意义：

- Seltos 2023 要新建独立车型条目。
- 初期可以复用 Seltos 2021 的配置。
- 必须明确它是纯 CAN，不是 CANFD。

## 2. Fingerprint 和固件识别

这部分决定系统怎么“认车”。

常见内容：

- CAN fingerprint：车上哪些 CAN ID 存在、每条消息多长。
- FW versions：摄像头、雷达、EPS、ABS、SCC 等 ECU 的固件版本。
- fuzzy fingerprint：固件或 CAN 消息不完全一致时的模糊匹配规则。

对本项目的意义：

- 如果 Seltos 2023 和 2021 CAN/FW 很像，初期可以让 2023 复用 2021。
- 后续最好采集你的车的 fingerprint/FW dump，给 2023 独立补全。

## 3. DBC 和 CAN 消息定义

DBC 是 CAN 消息字典。

常见内容：

- 车速、方向盘角度、油门、刹车、转向灯、档位等信号在哪条 CAN 消息里。
- SCC/ACC、AEB、LKAS、LFA 等消息格式。
- 每个信号的 bit 位置、缩放、偏移、单位。

对本项目的意义：

- 如果 Seltos 2023 和 2021 DBC 一致，就可以直接复用。
- ESCC 移植会重点碰 SCC/雷达/AEB 相关消息。

## 4. 总线布局

这部分决定不同消息在哪条 CAN bus 上。

常见内容：

- camera bus。
- powertrain bus。
- SCC/radar bus。
- ADAS module bus。
- 是否 CANFD。
- 是否 HDA2。

对本项目的意义：

- 你的 Seltos 2023 是纯 CAN，不走 CANFD。
- 所以新车型条目不能默认带 CANFD/HDA2 flag。
- ESCC 接线在哪条 bus 上需要单独确认。

## 5. Safety 配置

这是最敏感的一部分。

常见内容：

- 使用哪套 Hyundai safety model。
- 是否允许 openpilot 控制纵向。
- 是否允许 camera SCC。
- 是否允许 ESCC。
- 转向扭矩上限、转向变化率限制。
- 加速度、减速度、jerk 限制。
- 哪些原车消息要拦截、转发或保留。

对本项目的意义：

- ESCC 不能只改 UI 开关，必须和 safety 参数一致。
- Seltos 2023 默认应保持保守：ESCC 默认关闭。
- 任何 CANFD/HDA2 safety flag 都不能误加到你的纯 CAN 车上。

## 6. 车辆物理参数

这部分影响控制模型。

常见内容：

- 质量 `mass`。
- 轴距 `wheelbase`。
- 转向比 `steerRatio`。
- 轮胎刚度因子。
- 最小转弯半径相关参数。
- 车身尺寸和重心相关估计。

对本项目的意义：

- 这些会影响横向控制手感。
- Seltos 2023 如果机械结构和 2021 接近，先复用 2021 是合理的。
- 后续如果感觉过弯、居中、回正不对，再单独调。

## 7. 转向预设

你问的“转向预设”主要在这里。

常见内容：

- 使用 torque control、angle control，还是 PID/INDI/LQR 等控制方式。
- lateral tuning 参数。
- 最大转向扭矩。
- 转向扭矩变化速度限制。
- 低速/高速转向限制。
- driver torque allowance：人手打方向时如何让权。
- angle rate limit：角度控制时方向角变化速度。

对本项目的意义：

- 如果 2021 配置现在开起来正常，2023 第一版不要乱改转向参数。
- 新建车型先复制 2021 转向 tuning，等实车反馈再调。

## 8. 纵向控制预设

这部分决定跟车、加减速、停车起步。

常见内容：

- 是否启用 openpilot longitudinal control。
- 加速度上限、减速度下限。
- jerk 限制。
- stop-and-go 参数。
- 跟车距离策略。
- 原厂 SCC 和 openpilot 纵控如何切换。
- AEB/SCC 消息如何保留。

对本项目的意义：

- ESCC 主要影响这里。
- 迁移时要确认 ESCC lead/radar 数据能进入 longitudinal planner。
- 默认不开 ESCC 纵控，避免上车第一版就改变加减速行为。

## 9. Radar / lead 预设

这部分决定前车信息从哪里来。

常见内容：

- camera lead。
- SCC/radar tracks。
- ESCC lead。
- corner radar。
- radar delay。
- radar time step。
- lead 选择和 fallback。

对本项目的意义：

- fishop 的 ESCC 支持重点就在这里。
- Seltos 2023 要确认 ESCC 数据、原车 SCC 数据、camera lead 的优先级。

## 10. UI 和参数开关

这部分决定设置页能不能看到功能。

常见内容：

- `EnableEscc`
- `EnableRadarTracks`
- `HyundaiCameraSCC`
- `CanfdHDA2`
- 其它 CarrotPilot/国内导航/调参开关。

对本项目的意义：

- Seltos 2023 可以显示 ESCC 开关。
- ESCC 默认关闭。
- `CanfdHDA2` 这类开关即使保留给其它车型，也不能误作用于 Seltos 2023。

## Seltos 2023 新建车型的第一版策略

第一版不要大改控制参数。

建议：

- 新增 Seltos 2023 名字和枚举。
- 复用 Seltos 2021 DBC。
- 复用 Seltos 2021 转向 tuning。
- 复用 Seltos 2021 纵控基础参数。
- 明确设置为纯 CAN。
- 不设置 CANFD/HDA2。
- ESCC 默认关闭。
- 后续用你的车的 fingerprint/FW dump 补全独立识别。
