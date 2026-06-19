# Genius Pilot Alpha Release Template

Use this template for every `/x` alpha release or device-side hotfix.

## Release Identity

- Date:
- Genius Pilot version:
- SunnyPilot base version:
- Code branch: `experimental/sunnypilot-011-c3`
- Install branch: `alpha-sunnypilot-c3`
- Commit:
- Commit date:
- Installer URL: `https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x`
- Stable rollback URL: `https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/i`
- Installer SHA256:
- Installer size:

## Scope

- Summary:
- Changed files:
- User-facing changes:
- Control-output changes:
- Cloud/upload changes:
- Known rollback:

## Required Local Gates

- `python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --full --skip-online-installer`
- `python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py`
- `python3 scripts/personal/sunnypilot_c3_installer_audit.py --json`

Paste results or attach logs:

```text

```

## Device Evidence

- Device IP:
- Installed branch:
- Installed commit:
- UI opens:
- Settings open:
- Super Advanced opens:
- Visuals page opens:
- Network page connected state:
- Temperature display:
- Local Web/API:
- SSH:
- GitHub updater:
- Model manager:
- Stock model runner:
- `/tmp/launch_log` clean:

Evidence bundle path:

```text

```

## No-Cloud Evidence

Required absent processes:

- `athenad`
- `uploader`
- `sunnylinkd`
- `sunnylink_registration_manager`
- `statsd_sp`
- `backup_manager`

Evidence:

```text

```

## Vehicle And ESCC Evidence

- Vehicle: Kia Seltos 2023 SCC pure CAN
- Selected profile: `KIA_SELTOS_2023`
- Dashcam-only: false
- Non-SCC Seltos path absent:
- Enhanced SCC `0x2AB` detected:
- ESCC safety param set:
- NNLC/NLC default:

Evidence:

```text

```

## Model Evidence

- Active model bundle:
- Model runner:
- `modeld` status:
- `modelV2` sampled:
- `drivingModelData` sampled:
- `cameraOdometry` sampled:
- Fallback/rollback status:

Evidence:

```text

```

## Carrot And Speed Evidence

- Phone/APN/N/Navipilot input:
- Vehicle speed-limit input:
- OSM/mapd input:
- Offset type/value:
- Active speed control:
- Auto-turn:
- Traffic-light stop:
- Auto-Tuner:
- Known-good tuning values preserved:

Evidence:

```text

```

## Fishop Evidence

- Lane curve:
- Left/right lane data:
- Lidar blindspot:
- Camera blindspot:
- Dynamic blindspot risk:
- Navigation gate:
- Overtake request:
- Overtake suggestion preview:
- Control output remains false:

Evidence:

```text

```

## Test Phase

- Parked/offroad:
- First road test:
- Speed-limit display only:
- Speed-limit assist:
- Model manager:
- Carrot advanced features:
- Fishop/overtake stages:

## Decision

- Release status:
- Blockers:
- Follow-up TODO:
- Rollback needed:
