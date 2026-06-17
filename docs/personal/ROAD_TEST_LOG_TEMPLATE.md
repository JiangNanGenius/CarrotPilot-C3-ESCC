# 上车测试记录模板

本模板用于把 `static` 或 `test` tag 升级为 `stable` tag 前的实车证据。没有完成这些项目时，不要打 `stable` tag。

## 基本信息

- 日期：
- 设备：C3 中国克隆版
- 车辆：Kia Seltos 2023，纯 CAN
- 分支：
- commit：
- tag：
- 设备快照文件：
- 回滚目标：
- 测试地点 / 路况：

## 必填结论行

`release_gate.py --kind stable` 会检查下面这些行。只有实际完成并确认后，才把对应项保留为 `PASS`。

```text
Seltos real-car test: PENDING
AlwaysOffline ACC power-cycle test: PENDING
ESCC 0x2AB observed: PENDING
Low-speed road test: PENDING
Rollback target recorded: PENDING
```

## 0. 安装前

- [ ] 记录当前可用版本。
- [ ] 备份 `/data/params` 关键参数。
- [ ] 运行 `python3 scripts/personal/device_snapshot.py --output /data/media/0/carrotpilot-c3-escc-snapshot.md`。
- [ ] 准备回滚安装地址或回滚 tag。
- [ ] 确认 `AlwaysOffline=1`。
- [ ] 确认 `EnableEscc=0`。

## 1. 静态启动

- [ ] 设备能进入系统。
- [ ] 不因注册或联网流程卡住。
- [ ] 无 manager crash 或循环重启。
- [ ] 设置页能看到“离线使用模式”和“启用 ESCC 硬件”。
- [ ] 可手动选择 `Kia Seltos 2023`。

## 2. 车辆和 CAN 路径

- [ ] 车辆按 Seltos 2023 或等价 Seltos 2021 纯 CAN 路径工作。
- [ ] 没有走 CANFD/HDA2。
- [ ] `CanfdHDA2=0`。
- [ ] 原车 SCC、AEB、FCW 无异常提示。

## 3. Always Offline / ACC 供电

- [ ] 熄火断电后设备不会依赖联网注册恢复。
- [ ] ACC/CAN 重新供电后能正常进入系统。
- [ ] 不启动后台更新。
- [ ] 不启动远程连接和上传流程。
- [ ] 驻车按 Cancel 不主动关机。

## 4. ESCC 静态确认

- [ ] `EnableEscc=0` 时行为接近原 Seltos 2021 可用配置。
- [ ] 开启 `EnableEscc=1` 后能看到 ESCC 0x2AB。
- [ ] 使用 `device_snapshot.py --sample-seconds 20` 记录 0x2AB 计数。
- [ ] ESCC lead / radarState 字段稳定。
- [ ] AEB/FCW/SCC 状态无异常。
- [ ] 刹车、油门、Cancel、人工接管均正常。

## 5. 低速验证

- [ ] 第一轮不开纵控，只观察车道、lead、radarState。
- [ ] 第二轮短时间启用，随时准备接管。
- [ ] 无异常加速。
- [ ] 无异常减速。
- [ ] 无 SCC/AEB 故障。
- [ ] 无车型识别或接线路径错误。

## 6. CP搭子 / Navipilot 可选记录

- [ ] Android APP 能发现 C3。
- [ ] 同 WiFi 7705/7706 通信正常。
- [ ] `nRoadLimitSpeed` 更新正常。
- [ ] TBT / SDI / GPS 更新正常。
- [ ] `LANECHANGE` 仍只走现有安全变道逻辑。

## 7. 问题和回滚

- 问题记录：
- 是否回滚：
- 回滚后状态：
