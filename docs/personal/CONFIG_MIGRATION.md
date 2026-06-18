# 从旧版本迁移安全参数

这份说明用于把当前能正常跑的 fishop / 飞扬版本设置导出，再导入本项目版本。

目标不是复制整个 `/data/params`，而是只迁移设置白名单。脚本会从 `selfdrive/carrot_settings.json` 生成可迁移 key，并额外允许少量安全隐藏项。包含 token、password、dongle、github、athena、ssh、email、account 等字样的 key 会被过滤。

## 适用场景

- 当前车机上 fishop / 飞扬版本能正常使用。
- ESCC 当前默认或手动开启后工作正常。
- 想把这些参数迁到本项目版本，减少重新手动调参。

## 旧版本上导出

在当前能正常使用的版本上运行：

```bash
cd /data/openpilot
python3 scripts/personal/params_migration.py export \
  --output /data/media/0/carrotpilot-fishop-working-params.json
```

如果旧版本没有这个脚本，先把本项目的 `scripts/personal/params_migration.py` 临时放到旧版本的 `/data/openpilot/scripts/personal/params_migration.py`，再运行同一条命令。脚本默认读取当前目录下的 `selfdrive/carrot_settings.json`，所以它会按旧版本自己的设置表导出。

导出后建议同时保留一份设备快照：

```bash
python3 scripts/personal/device_snapshot.py \
  --output /data/media/0/carrotpilot-before-migration-snapshot.md
```

如果旧版本没有 `device_snapshot.py`，跳过快照也可以，参数导出文件才是迁移用的主文件。

## 新版本上 dry-run

安装本项目版本后，先不要直接写入参数。先看 dry-run：

```bash
cd /data/openpilot
python3 scripts/personal/params_migration.py import \
  --input /data/media/0/carrotpilot-fishop-working-params.json
```

重点核对这些项：

- `EnableEscc`
- `HyundaiCameraSCC`
- `EnableRadarTracks`
- `CanfdHDA2`
- `AlwaysOffroad`
- 巡航、跟车、转向、导航减速和 Auto-Tuner 相关参数

Seltos 2023 是纯 CAN，`CanfdHDA2` 应保持 `0`。如果 dry-run 准备把它改成 `1`，不要 apply。

也可以用首装向导把 dry-run、静态检查和证据包一次跑完：

```bash
cd /data/openpilot
python3 scripts/personal/c3_commissioning.py \
  --migration-input /data/media/0/carrotpilot-fishop-working-params.json \
  --archive
```

向导会生成 `migration-import-output.txt`、`evidence/` 和 `evidence-readiness.txt`。

## 确认后写入

确认 dry-run 没有异常后，再写入：

```bash
python3 scripts/personal/params_migration.py import \
  --input /data/media/0/carrotpilot-fishop-working-params.json \
  --apply
```

写入后重启一次系统，再跑静态检查：

```bash
python3 scripts/personal/c3_static_check.py \
  --output /data/media/0/carrotpilot-c3-escc-static-check.md \
  --snapshot-output /data/media/0/carrotpilot-c3-escc-snapshot.md
```

或者用首装向导直接做写入后检查：

```bash
python3 scripts/personal/c3_commissioning.py \
  --migration-input /data/media/0/carrotpilot-fishop-working-params.json \
  --apply-migration \
  --archive
```

## 不会自动迁移的内容

- GitHub token、SSH key、账号、邮箱、dongle id、Athena / comma 注册相关信息。
- `IsOnroad` 这类运行状态。
- `EnableRadarTracksResult` 这类启动后会重新生成的检测结果。
- 不在新版本安全白名单里的旧版本私有参数。

## 建议策略

如果你现在的 fishop / 飞扬版本 ESCC 已经能正常用，可以先用迁移文件把它的工作参数带过来；但本项目公开默认仍保持 `EnableEscc=0`。第一次上车时先停车确认参数和 0x2AB，再逐步开启。
