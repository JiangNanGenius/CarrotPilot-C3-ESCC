# GitHub 建仓记录

## 当前状态

- 仓库：`JiangNanGenius/CarrotPilot-C3-ESCC`
- 地址：`https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC`
- 可见性：公开。
- 本地远端名：`github`
- 默认分支：`personal/c3-escc-atune`
- 已推送分支：
  - `personal/c3-escc`：Seltos 2023 + ESCC + AlwaysOffroad 主用保护线。
  - `personal/c3-escc-atune`：在主用保护线上继续集成 Auto-Tuner。
- GitHub CLI 已登录 `JiangNanGenius`，凭据保存在本机 GitHub CLI/keyring，不写入仓库。
- 仓库先从 `ajouatom/openpilot` 种入上游历史，再转为独立公开仓库；GitHub 页面不再显示 fork 关系，但远端仍保留上游分支历史，方便后续只推个人改动。

## 建议仓库名

首选：

- `CarrotPilot-C3-ESCC`

备选：

- `carrotpilot-c3-escc`
- `CarrotPilot-ESCC-AutoAdjust`

## 公开后注意事项

当前仓库已公开。后续每次推送前都要先做来源署名、安装说明、免责声明和敏感信息检查。

公开状态下尤其注意：

- ESCC 还没有完成实车验证，不能把静态检查写成实车结论。
- 车辆安全相关修改必须保留默认关闭或明确的回滚路径。
- 继续核对多个上游来源的署名和许可证边界。
- 不把个人令牌、设备信息、车辆 VIN 或其它隐私内容写入仓库。

## 初始仓库内容

初始仓库直接放可安装的 openpilot 代码分支，并保留个人维护文档：

- `personal/c3-escc`：主用保护分支，适合做后续测试 tag 的来源。
- `personal/c3-escc-atune`：当前整合分支，包含 Auto-Tuner 实验功能。
- `docs/personal/`：整合计划、更新检查单、来源署名、安装和回滚说明。
- `.github/ISSUE_TEMPLATE/`：上游更新和功能整合模板。
- `.github/workflows/upstream-snapshot.yml`：上游更新审计工作流，显示名为 `Upstream Watch`。
- `scripts/personal/upstream_snapshot.sh`：上游分支检查脚本。
- `docs/personal/UPSTREAM_BASELINES.json`：GitHub Actions 使用的已审查上游基准 commit。

本地仍保留这些基准分支，方便人工 rebase 和对比：

- `upstream/c3-wip`
- `tracking/c4`
- `tracking/fishop-cp`
- `tracking/jixie-atune`
- `tracking/jixie-master`

`Upstream Watch` 不需要把这些 tracking 分支推到 GitHub；它使用 [UPSTREAM_BASELINES.json](UPSTREAM_BASELINES.json) 比较三方远端是否有新提交。不要把 tracking 分支或基准 commit 当作设备安装目标。

## 创建后需要设置

- [x] 默认分支使用 `personal/c3-escc-atune`，方便先看到当前整合文档。
- [x] 添加 topic：`carrotpilot`, `openpilot`, `c3`, `seltos`, `escc`。
- [x] README 保留上游来源。
- [x] 不把安装 URL 指到未验证开发分支。
- [x] Issues 已开启。
- [x] Actions 已开启。
- [x] Wiki 已关闭。
- [x] `Personal Smoke` 已接入。
- [x] `Upstream Watch` 已接入。
- [ ] 稳定版使用 tag 或 release。

## 推荐保护规则

如果仓库公开或多人协作：

- `main` 禁止直接 push。
- `personal/c3-escc` 禁止未检查直接 push。
- 上游更新通过 PR。
- ESCC 相关改动必须跑 `docs/UPDATE_CHECKLIST.md`。
