# GitHub 建仓计划

## 建议仓库名

首选：

- `CarrotPilot-C3-Seltos-ESCC`

备选：

- `carrotpilot-c3-escc`
- `carrotpilot-seltos-escc`
- `CarrotPilot-ESCC-AutoAdjust`

## 建议可见性

先建私有仓库，等署名、许可证、安装说明、免责声明都整理好后，再决定是否公开。

原因：

- 还没有完成 ESCC 实车验证。
- 会涉及车辆安全相关修改。
- 需要保留并核对多个上游来源的署名。

## 初始仓库内容

初始仓库直接放可安装的 openpilot 代码分支，并保留个人维护文档：

- `personal/c3-escc`：当前主用代码分支。
- `docs/personal/`：整合计划、更新检查单、来源署名、安装和回滚说明。
- `.github/ISSUE_TEMPLATE/`：上游更新和功能整合模板。
- `.github/workflows/upstream-snapshot.yml`：上游分支快照工作流。
- `scripts/personal/upstream_snapshot.sh`：上游分支检查脚本。

后续再建立：

- `upstream/c3-wip`
- `personal/c3-escc-atune`
- `tracking/fishop-cp`
- `tracking/jixie-atune`

## 创建后需要设置

- [ ] 默认分支使用 `main`。
- [ ] 打开 Issues。
- [ ] 打开 Actions。
- [ ] 添加 topic：`carrotpilot`, `openpilot`, `c3`, `seltos`, `escc`。
- [ ] README 保留上游来源。
- [ ] 不把安装 URL 指到开发分支。
- [ ] 稳定版使用 tag 或 release。

## 推荐保护规则

如果仓库公开或多人协作：

- `main` 禁止直接 push。
- `personal/c3-escc` 禁止未检查直接 push。
- 上游更新通过 PR。
- ESCC 相关改动必须跑 `docs/UPDATE_CHECKLIST.md`。
