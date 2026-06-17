# Model Selector 研究记录

记录日期：2026-06-18

## 来源

- 仓库：`ajouatom/openpilot`
- 分支：`happymaj11r/carrot-wip-model_selector`
- 本地跟踪分支：`tracking/model-selector`
- 当前审查 commit：`d4ed4fa165f019618791b8590f82f4cc115f7c5f`

## 当前结论

模型选择器暂不进入默认 C3 / Seltos / ESCC 主线。

原因：

- 它会改 `modeld` 启动入口。
- 它涉及远程 `models.json`、签名验证、ONNX 下载、SHA256/size 校验、tinygrad 编译、warp pkl、重启和 `/data/models` 原子替换。
- 它需要真实 C3 存储空间、编译耗时、模型资产和回滚验证。
- 当前用户主需求里 ESCC、AlwaysOffline、Seltos 2023、CP搭子基础链路优先级更高。

当前已做的是来源跟踪和安全审计，不是功能启用。

## 参考实现要点

参考分支的 `carrot/model_selector/` 采用分离 engine 思路：

- 默认模型仍由 upstream `selfdrive.modeld.modeld` 负责。
- `/data/models` 中存在有效自定义模型时，`modeld_runner` 才切到 `carrot_modeld`。
- `/data/model_selector_status` 记录当前 engine。
- `DrivingModelName` 表示当前模型。
- `PendingModelName` 表示等待重启后编译安装的模型。

下载和安装链路包含：

- `models.json` canonical JSON + Ed25519 签名校验。
- `ALLOWED_ONNX_FILES` 限定文件名。
- `ALLOWED_URL_PREFIX` 限定模型下载来源。
- 模型 id 正则校验。
- 每个文件 size 和 SHA256 校验。
- `/data/models_tmp` 下载和编译。
- `/data/models` 原子替换。
- 失败后恢复 backup。
- reset 恢复默认模型并清除参数。

## 本项目新增守卫

新增脚本：

```bash
python3 scripts/personal/model_selector_audit.py
```

该脚本检查两件事：

- 参考分支是否仍具备签名、allowlist、hash/size、模型目录 validator、默认 modeld fallback、reset 等关键条件。
- 当前默认 C3 主线是否没有半截模型选择器代码混入。

如果以后真的迁移模型选择器，必须让这个脚本继续通过，并补充更强条件：

- 参数默认关闭。
- Web UI 必须清楚提示需要停车和重启。
- 下载前显示模型来源、文件大小、签名状态和剩余空间。
- 安装失败必须自动恢复默认模型。
- `modeld_runner` 必须在 `/data/models` 无效时回退 upstream modeld。
- C3 上必须保存 `model_selector_status` 和安装日志。
- 证据包必须记录当前 `DrivingModelName`、`PendingModelName` 和 engine。

## 后续迁移顺序

### A. 仅跟踪和审计

- 已建立 `tracking/model-selector`。
- 已把基准写入 `UPSTREAM_BASELINES.json`。
- 已把来源纳入 `update_audit.py` 和 GitHub Actions `Upstream Watch`。
- 已把 `model_selector_audit.py` 纳入 `smoke_check.py`。

### B. 设备端只读状态

后续可先加只读状态采集，不改变模型：

- 读取 `/data/model_selector_status`。
- 读取 `DrivingModelName`、`PendingModelName`。
- 在证据包中显示当前是否为默认模型。

### C. 实验分支迁移

真正的下载、安装、编译、Web UI、重启和 modeld runner 改动必须在单独分支完成，例如：

- `experimental/model-selector`

不应直接进入 `personal/c3-escc-atune` 默认安装线。

### D. 上车前要求

模型选择器进入可测试状态前，至少要完成：

- C3 上默认模型启动验证。
- 自定义模型下载失败回滚验证。
- 自定义模型编译失败回滚验证。
- reset 后回到默认 upstream modeld。
- 低速短程验证无模型输出异常。

## 当前状态

- `Model selector`: `SOURCE_TRACKED`
- 默认 C3 主线未启用模型下载、模型安装或 modeld 切换。
- 该状态是刻意选择，不是遗漏。
