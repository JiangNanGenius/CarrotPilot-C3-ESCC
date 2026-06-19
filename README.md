# Genius Pilot C3 ESCC

Genius Pilot is a personal C3/TICI alpha build for a clone comma C3 and a Kia
Seltos 2023 SCC pure-CAN car. It uses SunnyPilot 0.11 architecture as the base,
but the product direction is CarrotPilot-first: granular Carrot controls,
ESCC detection, APN/N/Navipilot inputs, Auto-Tuner evidence, and Fishop hardware
evidence are explicit instead of hidden behind cloud services or black-box
settings.

This repository is for personal research and testing. It is not a product and
does not replace driver responsibility.

## 中文快速说明

这是给克隆版 C3/TICI 和 Kia Seltos 2023 SCC 纯 CAN 车使用的个人 alpha
版本。日常稳定回滚线用 `/i`，新架构测试线用 `/x`。

- 稳定回滚：`https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/i`
- 当前 alpha：`https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x`
- 车型：`KIA_SELTOS_2023`
- ESCC：通过 `0x2AB` 自动识别，不提供普通手动开关
- 云服务：Sunnylink、comma connect、上传、远程配对、云备份都禁用或无效
- 本地服务：Wi-Fi、SSH、本地 Carrot Web/API、GitHub 更新、模型下载保留
- 默认模型：stock model
- 默认地图覆盖：关闭，不让 Mapbox/Kakao 盖住 HUD
- 高风险功能：主动控速、自动转弯减速、红绿灯停车、Auto-Tuner 自动应用、
  Fishop 自动超车都要停车/offroad 分开测试

先做停车测试，再做只显示/只读证据测试，最后才逐项测试控制相关功能。出现不确定行为时，先关闭对应功能；必要时刷回 `/i`。

## Install

Stable daily rollback line:

```text
https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/i
```

SunnyPilot 0.11 C3 alpha line:

```text
https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x
```

Use `/i` as the known stable rollback path. Use `/x` only for the current
Genius Pilot alpha. The `/x` installer is intentionally short and points to the
`alpha-sunnypilot-c3` branch.

## Hardware And Vehicle Target

- Device: clone comma C3/TICI, not C3X and not C4.
- Primary vehicle: Kia Seltos 2023 SCC pure CAN.
- Vehicle profile: `KIA_SELTOS_2023`, based on the known-working Seltos 2021
  SCC path.
- ESCC: automatic enhanced SCC detection through `0x2AB`; there is no broad
  manual ESCC toggle.
- NNLC/NLC: default on for supported cars.

Other cars are not the target of this personal build.

## Cloud Policy

Cloud services are intentionally disabled or inert:

- Sunnylink
- comma connect / athenad pairing
- uploader and Onroad Uploads
- cloud backups
- remote pairing
- cloud training upload flows

Local networking remains enabled for maintenance:

- local Wi-Fi and LAN access
- SSH when enabled locally
- local Carrot Web/API
- GitHub update/install flow
- model list and model downloads requested by the user

## Main Features

- C3/TICI compatibility patches for the SunnyPilot 0.11 architecture.
- Genius Pilot versioning that follows the SunnyPilot base and adds a date plus
  same-day patch suffix.
- Seltos 2023 SCC profile and ESCC auto-detection.
- Sunny native model manager and `modeld_tinygrad`, with stock model as the
  default.
- Phone-first speed-limit input from APN/N/Navipilot/Carrot, then vehicle speed
  limit, then OSM/mapd.
- Fixed and percentage speed-limit offset; default offset is zero.
- `CarrotMapOverlayEnabled=0` by default so external map overlays do not cover
  the HUD.
- Super Advanced Carrot/Genius settings for active speed, auto-turn, red-light
  stop, curve speed, following, longitudinal tuning, Auto-Tuner, and Fishop
  hardware.
- Local Carrot Web/API on LAN for status, params, navigation evidence, Fishop
  evidence, and Auto-Tuner evidence.
- Visualization modes: Sunny, Carrot, and Fusion base presets, with independent
  Carrot World and Fishop evidence overlays (`GeniusCarrotWorldOverlay` and
  `GeniusFishopVisualOverlay`).

## Local Web And Evidence

The local Web/API is a local maintenance surface, not a cloud pairing service.
Important endpoints include:

- `/api/health`
- `/api/params_bulk`
- `/api/param_set`
- `/api/status_broadcast`
- `/api/navigation_event`
- `/api/phone_speed_limit`
- `/api/fishop_hardware`
- `/api/carrot_learning`

Changed parameter writes are blocked while onroad. High-risk Carrot/Fishop
features expose evidence and state, but the local Web/API does not publish CAN,
planner, lane-change, or lateral control output.

## Testing Order

Use a staged test flow:

1. Parked/offroad install and boot check from `/x`.
2. Confirm no cloud/upload processes are running.
3. Confirm local Wi-Fi, SSH, local Web/API, updater, and model manager work.
4. Confirm stock model starts before trying a custom model.
5. Confirm Seltos 2023 and ESCC evidence.
6. Test speed-limit sources in information/display mode first.
7. Test one higher-risk feature at a time.

Keep `/i` ready as rollback until parked checks and later road evidence are
clean.

## Docs

Personal alpha docs live under `docs/personal/`:

- `TODO.md`: current development checklist.
- `VERSIONING.md`: Genius Pilot version format.
- `SETTINGS_MATRIX.md`: owner matrix for Carrot, Sunny, Fishop, ESCC, model,
  local-network, visualization, and removed cloud settings.
- `SETTINGS_CONFLICTS.md`: conflict policy across imported branches.
- `HIGH_RISK_SETTING_GUIDE.md`: practical guide for risky toggles.
- `RELEASE_TEMPLATE.md`: release/evidence note template.

## Attribution

This personal build includes work derived from or inspired by:

- comma.ai openpilot
- SunnyPilot
- ajouatom CarrotPilot / CarrotPilot-style functions
- jixiexiaoge mechanical / Auto-Tuner / local Web work
- masang-feiyang ESCC-oriented work
- dhvms and other related CarrotPilot forks

The code remains subject to the licenses in this repository, including
`LICENSE` and `LICENSE.md`.

## Safety And License

This is alpha-quality research software. You are responsible for complying with
local laws and regulations and for supervising the vehicle at all times. No
warranty is expressed or implied.
