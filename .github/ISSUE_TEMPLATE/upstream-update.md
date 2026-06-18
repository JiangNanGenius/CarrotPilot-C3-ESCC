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

## Connect / AlwaysOffroad 检查

- [ ] `AlwaysOffroad` 存在且默认关闭。
- [ ] `EnableConnect` 存在且默认关闭，在线注册被跳过。
- [ ] `EnableConnect=0` 时远程连接和上传流程不启动。
- [ ] `AlwaysOffroad=1` 时设备保持 offroad，本地 Web/SSH/更新仍可用，pandad 保持 no-output。

## 验证

- [ ] 静态检查完成。
- [ ] 构建/测试完成。
- [ ] 设备静态启动完成。
- [ ] 低速验证完成。
