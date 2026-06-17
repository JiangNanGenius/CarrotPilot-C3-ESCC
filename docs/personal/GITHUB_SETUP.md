# GitHub 建仓记录

## 当前状态

- 仓库：`JiangNanGenius/CarrotPilot-C3-Seltos-ESCC`
- 地址：`https://github.com/JiangNanGenius/CarrotPilot-C3-Seltos-ESCC`
- 可见性：私有。
- 本地远端名：`github`
- 默认分支：`personal/c3-escc-atune`
- 已推送分支：
  - `personal/c3-escc`：Seltos 2023 + ESCC + Always Offline 主用保护线。
  - `personal/c3-escc-atune`：在主用保护线上继续集成 Auto-Tuner。
- GitHub CLI 已登录 `JiangNanGenius`，凭据保存在本机 GitHub CLI/keyring，不写入仓库。
- 仓库先从 `ajouatom/openpilot` 种入上游历史，再转为私有仓库；GitHub 页面不再显示 fork 关系，但远端仍保留上游分支历史，方便后续只推个人改动。

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

- `personal/c3-escc`：主用保护分支，适合做后续测试 tag 的来源。
- `personal/c3-escc-atune`：当前整合分支，包含 Auto-Tuner 实验功能。
- `docs/personal/`：整合计划、更新检查单、来源署名、安装和回滚说明。
- `.github/ISSUE_TEMPLATE/`：上游更新和功能整合模板。
- `.github/workflows/upstream-snapshot.yml`：上游分支快照工作流。
- `scripts/personal/upstream_snapshot.sh`：上游分支检查脚本。

后续再建立：

- `upstream/c3-wip`
- `tracking/fishop-cp`
- `tracking/jixie-atune`

## 创建后需要设置

- [x] 默认分支使用 `personal/c3-escc-atune`，方便先看到当前整合文档。
- [x] 添加 topic：`carrotpilot`, `openpilot`, `c3`, `seltos`, `escc`。
- [x] README 保留上游来源。
- [x] 不把安装 URL 指到未验证开发分支。
- [x] Issues 已开启。
- [x] Actions 已开启。
- [x] Wiki 已关闭。
- [ ] 稳定版使用 tag 或 release。

## 推荐保护规则

如果仓库公开或多人协作：

- `main` 禁止直接 push。
- `personal/c3-escc` 禁止未检查直接 push。
- 上游更新通过 PR。
- ESCC 相关改动必须跑 `docs/UPDATE_CHECKLIST.md`。
