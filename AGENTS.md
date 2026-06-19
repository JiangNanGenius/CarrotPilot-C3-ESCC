# CarrotPilot-C3-ESCC Agent Guide

This repository has two active user-facing lines:

- Stable daily line: `personal/c3-escc-atune`, installed from `/i`.
- SunnyPilot 0.11 C3 alpha line: `experimental/sunnypilot-011-c3` and short install branch `alpha-sunnypilot-c3`, installed from `/x`.

Do not move `/i` or stable/latest to the alpha line until the C3 parked checks and real Seltos 2023 road evidence pass.

## User Hardware And Vehicle

- Device: clone comma C3, not C3X and not comma four.
- Vehicle: Kia Seltos 2023 SCC, pure CAN, currently known to work with the Seltos 2021 SCC path.
- ESCC hardware is present and must be supported through automatic enhanced SCC detection. Do not add a broad manual ESCC toggle.

## Non-Negotiable Safety Boundaries

- Cloud services stay removed or inert: `manage_athenad`, `uploader`, `manage_sunnylinkd`, `sunnylink_registration_manager`, `statsd_sp`, and `backup_manager` must not be manager processes.
- `SunnylinkEnabled`, `EnableSunnylinkUploader`, and `OnroadUploads` are not user features in this personal build. Old values must not start cloud processes.
- Keep local networking, SSH, Carrot Web, GitHub update, and model downloads. These are local or user-triggered maintenance paths, not cloud pairing services.
- Always-offroad semantics use `OffroadMode`. Do not add `AlwaysOffline`, `AlwaysOffroad`, or other confusing aliases.
- `OffroadMode` must keep the device parked and panda in no-output mode. Do not import Mr.One never-shutdown behavior.
- `CarrotMapOverlayEnabled` defaults off. When off, do not load Mapbox/Kakao iframe or external SDKs.
- Carrot advanced features default off but must remain visible and user-toggleable while offroad: traffic-light stop, auto-turn slowdown/ATC, active speed control, Auto-Tuner auto-apply, and Fishop auto-overtake.
- Fishop lane/lidar/blindspot/overtake inputs must remain tied to the existing safety-chain review; do not hide the settings, and do not publish direct planner/CAN outputs from the local Web bridge.
- NNLC/NLC defaults on for supported cars through `NeuralNetworkLateralControl=1`; unsupported cars must be cleaned up by the existing Sunny support checks.
- Product direction is CarrotPilot-first. SunnyPilot is the 0.11 architecture base, not the feature owner for cruise behavior.
- Do not expose or enable SunnyPilot ICBM, SCC-V, or SCC-M in the personal build; they overlap with Carrot button, curve, map, and speed-limit paths.
- Sunny DEC may be retained as an off-by-default advanced longitudinal option. It must not lock out Carrot active speed, turn slowdown/ATC, or traffic-light stop settings.
- Carrot-style settings are preferred: every control behavior should have a visible setting, a clear Chinese/English description, conservative default, owner/source note, and rollback path.
- When three reference lines disagree, build a setting matrix first: ajouatom CarrotPilot, jixiexiaoge/mechanical, and masang-feiyang/ESCC. Decide one owner per behavior and avoid unexplained compatibility aliases.
- User-facing alpha branding should move toward Genius Pilot. Keep upstream package/module names only where renaming would create code risk.
- Genius Pilot version numbers follow the SunnyPilot base and append the personal build suffix: `<SunnyPilot base>-gp.<YYYYMMDD>.<patch>`.
- Do not rely on cloud registration for local recovery. Local Wi-Fi, SSH, and web access must work on the user's clone C3 without Sunnylink or comma connect.
- Do not add a public default password to a release build. If bench recovery needs a password path, make it explicitly local, documented, and removable before release.

## Update Workflow

When the user says to update, use this order:

1. Fetch reference branches for SunnyPilot, CarrotPilot, mechanical/Auto-Tuner, and Mr.One C3 references.
2. Keep SunnyPilot `staging` as the alpha base unless the user explicitly changes the base.
3. Pull only necessary C3/TICI compatibility patches from Mr.One. Do not import private registration, upload clients, cloud pairing, never-shutdown logic, or broad safety/opendbc changes.
   In short: do not import private registration or upload/cloud client behavior from reference forks.
4. Compare Carrot changes for Carrot Web, CarrotMan/Navipilot/APN/N input, speed-limit logic, model/map behavior, Auto-Tuner, localization, and fishop hardware fields.
   Treat CarrotPilot behavior and setting granularity as the target; use SunnyPilot implementation only when it is the safer/newer base primitive.
5. Preserve personal defaults: stock model, NNLC on for supported cars, map overlay off, speed offset zero, phone speed policy with timeout, cloud disabled, Carrot advanced controls default off but available while offroad.
6. Bump `sunnypilot/common/version.h` before pushing: keep the SunnyPilot base aligned to upstream, increment the same-day Genius patch, and reset patch to `1` on a new publish date.
7. Run the release gate before pushing.
8. Push `experimental/sunnypilot-011-c3` and `alpha-sunnypilot-c3` together only after the gate passes.
9. Audit the published `/x` installer before telling the user to retry installation.
10. Update `docs/personal/TODO.md`, `docs/personal/CODE_CHANGES.md`, and `docs/personal/VERSIONING.md` in the same change whenever real-device behavior, versioning, or safety assumptions change.
11. If `common/params_keys.h` changes, rebuild the ARM64 `common/params_pyx.so` on the C3 or another aarch64 Linux environment and verify the new key strings are present before publishing.

## Required Commands

Fast local gate during development:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py
```

Full pre-publish gate:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --full
```

Reference fetch/compare audit before upstream updates:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_update_audit.py --fetch --strict --scan-risk-tokens --json
```

Settings conflict audit after refreshing references:

```bash
python3 scripts/personal/sunnypilot_c3_settings_conflict_audit.py --strict
```

Full gate with reference fetch:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --fetch-references --full
```

Published installer audit:

```bash
python3 scripts/personal/sunnypilot_c3_installer_audit.py
```

Device snapshot after install:

```bash
python3 scripts/personal/sunnypilot_c3_device_collect.py \
  --host 192.168.100.174 \
  --navipilot-live-check \
  --require-no-cloud-processes
```

On-device snapshot command, if already SSH'd into the C3:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_snapshot.py \
  --sample-seconds 10 \
  --navipilot-live-check \
  --require-no-cloud-processes \
  --output /data/carrot_alpha_snapshot.json \
  --pretty
python3 scripts/personal/sunnypilot_c3_alpha_evidence_check.py \
  /data/carrot_alpha_snapshot.json \
  --phase parked \
  --phase model
```

Installer crash / download-screen exit evidence:

```bash
python3 scripts/personal/sunnypilot_c3_device_collect.py \
  --host 192.168.100.174 \
  --skip-snapshot
```

Real Seltos/ESCC evidence check, only after parked checks pass:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_evidence_check.py \
  /data/carrot_alpha_snapshot.json \
  --phase seltos-escc
```

## Installer Rules

- `/x` currently must be the Qt-compatible ARM64 installer generated by `scripts/personal/build_c3_qt_compat_installer.py`.
- Do not switch `/x` back to a Raylib installer until that exact binary has been tested on the user's clone C3 setup environment, or the device runtime is confirmed to satisfy the required GLIBC symbols.
- `/x` must install `https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git` and `alpha-sunnypilot-c3`.
- `/x` must pass `scripts/personal/sunnypilot_c3_installer_audit.py`.
- `/i` remains the rollback stable installer.
- The packed TICI updater is not the same file as `system/ui/lib/wifi_manager.py`. If Wi-Fi or dependency handling changes, audit the embedded updater payload too.
- Fresh `/x` installs must have `jeepney` available or the packed updater must carry the `nmcli` fallback; otherwise C3 update/setup paths can crash before the normal UI Wi-Fi fallback helps.

## Git Hygiene

The local Mac workspace can be slow because some files are managed by system sync. Prefer targeted file reads and targeted Git commands. Avoid broad `git status` unless necessary. If a status-like check is needed, prefer:

```bash
GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false -c gc.auto=0 status --short --untracked-files=no
```

Do not delete or revert user changes. Do not use destructive Git commands unless the user explicitly asks for them.
