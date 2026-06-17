---
name: 上游更新检查
about: 跟随 ajouatom/c3-wip 更新时使用
title: "上游更新: YYYY-MM-DD"
labels: update
---

## 上游信息

- ajouatom/c3-wip commit:
- fishop/cp commit:
- jixie/atune commit:
- 当前个人分支 commit:

## 高风险改动

- [ ] Hyundai/opendbc
- [ ] panda safety
- [ ] controls / longitudinal
- [ ] radar
- [ ] cereal/capnp
- [ ] Params / settings
- [ ] carrot web/server

## ESCC 检查

- [ ] `EnableEscc` 存在且默认关闭。
- [ ] ESCC 只在预期路径启用。
- [ ] AEB/SCC 消息保留逻辑仍在。
- [ ] Radar lead 解析正常。
- [ ] Seltos 配置未被破坏。

## Always Offline 检查

- [ ] `AlwaysOffline` 存在且个人 C3 克隆版默认开启。
- [ ] 在线注册被跳过。
- [ ] 更新和远程连接流程不在离线模式下启动。
- [ ] 驻车按 Cancel 不主动关机。

## 验证

- [ ] 静态检查完成。
- [ ] 构建/测试完成。
- [ ] 设备静态启动完成。
- [ ] 低速验证完成。
