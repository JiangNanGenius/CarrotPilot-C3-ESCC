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

## 新模型是怎么进旧底座的

模型列表来自 `happymaj11r/openpilot-models` 的 `models.json`。2026-06-18 检查时，该 manifest 有 52 个模型，更新时间为 `2026-05-23T05:47:30+09:00`。

如果车机 UI 实际只看到四五个模型，先按“UI 展示、selector 版本过滤、远端清单获取失败或缓存”排查，不要理解成底座只内置了四五个可用模型。参考分支的 `/api/models/list` 是从远端 manifest 拉取列表，按 selector 版本过滤后交给前端排序展示。

按文件结构分三类：

- 25 个旧两文件模型：`driving_vision.onnx` + `driving_policy.onnx`。
- 16 个新三文件模型：`driving_vision.onnx` + `driving_on_policy.onnx` + `driving_off_policy.onnx`。
- 11 个三文件兼容模型：`driving_vision.onnx` + `driving_policy.onnx` + `driving_off_policy.onnx`。

用户提到的 CoolPeople 对应 manifest 里的：

```text
The-Cool-peoples-v3 / TCPv3
```

它仍是旧两文件结构：

```text
driving_vision.onnx
driving_policy.onnx
```

真正更像 1.0 时代/新架构模型的是：

```text
OPv10
OPv11
OPv12
op11 / op11v2 / op11v3
Op model16*
```

这些模型使用 `driving_on_policy.onnx` / `driving_off_policy.onnx` 这类文件，或者依赖 `carrot_modeld` 的更新 parser。

它不是把“1.0 模型”硬塞给旧 upstream modeld 跑。参考分支做的是：

- manager 把 `modeld` 进程入口改成 `carrot.model_selector.modeld_runner`。
- `modeld_runner` 先检查 `/data/models` 是否是有效自定义模型目录。
- 没有有效自定义模型时，继续运行 upstream `selfdrive.modeld.modeld`。
- 有有效自定义模型时，运行 `carrot_modeld`。

下载来的 ONNX 文件会先进入 `/data/models_tmp`，然后在 C3 上执行：

```text
selfdrive/modeld/get_model_metadata.py
tinygrad_repo/examples/openpilot/compile3.py
selfdrive/modeld/compile_warp.py
```

最终安装到 `/data/models` 的不是 ONNX，而是：

```text
*_tinygrad.pkl
*_metadata.pkl
warp_*_tinygrad.pkl
```

`carrot_modeld` 会读取这些 pkl/metadata。它支持旧两模型结构，也支持带 `off_policy` 的三模型结构；并且它的 parser 能处理新模型里的 `action` 输出。如果没有 `action`，再回退到 legacy plan-based 解析。

所以“0.9.9-era 底座能用 1.0 时代模型”的关键不是底座本身升级到了 1.0，而是模型选择器移植了一套兼容新模型输出的自定义 modeld/Parser/编译/回滚流程。

风险也在这里：模型能不能安全使用，不只看文件能不能下载和编译，还要看输出 schema、`ModelConstants`、metadata shape、`modelV2` 消息填充、横纵控取值方式是否匹配。这个链路一旦错，可能影响控制输出。因此它暂不进入默认 C3 / Seltos / ESCC 主线。

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
