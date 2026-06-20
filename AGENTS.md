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
- Except for explicit curve-speed experiments, active speed/cruise target behavior should stay Carrot/Genius-owned: fresh APN/N/Navipilot/Carrot phone evidence first, then vehicle/cluster speed. Sunny map/GPS speed control is opt-in only through explicit map policies.
- Do not expose or enable SunnyPilot ICBM, SCC-V, or SCC-M in the personal build; they overlap with Carrot button, curve, map, and speed-limit paths.
- Sunny DEC may be retained as an off-by-default advanced longitudinal option. It must not lock out Carrot active speed, turn slowdown/ATC, or traffic-light stop settings.
- Carrot-style settings are preferred: every control behavior should have a visible setting, a clear Chinese/English description, conservative default, owner/source note, and rollback path.
- Onroad visualization is separate from control behavior. `GeniusVisualMode`, `GeniusLaneLineStyle`, `GeniusLeadRadarVisualMode`, `GeniusLaneChangeVisuals`, and `GeniusFishopVisualOverlay` may combine Sunny HUD, Carrot lane/lead/radar drawing, and future Fishop evidence overlays, but they must not emit planner, CAN, lane-change, or overtake control output.
- Prefer comma's offline replay tools for code behavior checks: use `selfdrive/test/process_replay` for process output regressions and `tools/replay` for UI/message replay. C3 parked probes are for real hardware paths such as cameras, IMU, local services, and device integration.
- Do not play device sounds during routine collection. Speaker checks are opt-in only with `--with-sound` or `--with-sound-probe`, and only after the user explicitly asks for an audible test.
- The C3 sidebar temperature card must show numeric Celsius from available `deviceState` temperature sources. If sensors are not ready, show `--C`; do not fall back to translated `GOOD`/`HIGH` status text.
- The C3 sidebar should stay personal-build focused: four cards for temperature, vehicle, phone/Navipilot input freshness, and GPS fix/accuracy. Phone status must use local Carrot/APN/N/Navipilot params, not Sunnylink or comma pairing.
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
   For onroad visualization, keep Sunny, Carrot, and Balanced display modes available, and treat Fishop/lidar overlays as evidence display until a later safety-chain stage exists.
5. Export the user's current Carrot/Fishop/model/visual tuning baseline from the C3 before changing longitudinal, braking, ATC, speed-limit, or Auto-Tuner behavior.
6. Preserve personal defaults: stock model, NNLC on for supported cars, map overlay off, speed offset zero, phone speed policy with timeout, cloud disabled, Carrot advanced controls default off but available while offroad.
7. Bump `sunnypilot/common/version.h` before pushing: keep the SunnyPilot base aligned to upstream, increment the same-day Genius patch, and reset patch to `1` on a new publish date.
8. Run the release gate before pushing.
9. Push `experimental/sunnypilot-011-c3` and `alpha-sunnypilot-c3` together only after the gate passes.
10. Audit the published `/x` installer before telling the user to retry installation.
11. Update `docs/personal/TODO.md`, `docs/personal/CODE_CHANGES.md`, and `docs/personal/VERSIONING.md` in the same change whenever real-device behavior, versioning, or safety assumptions change.
12. If `common/params_keys.h` changes, rebuild the ARM64 `common/params_pyx.so` on the C3 or another aarch64 Linux environment and verify the new key strings are present before publishing.

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

Carrot/Fishop/model/visual tuning baseline before behavior changes:

```bash
python3 scripts/personal/carrot_tuning_baseline.py \
  --output /data/genius_carrot_tuning_baseline.json \
  --pretty
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

Read-only LAN check when SSH is unavailable or the device may still report onroad:

```bash
python3 scripts/personal/navipilot_live_check.py \
  --host 192.168.100.174 \
  --listen-seconds 3 \
  --json-output ~/Desktop/CarrotPilot-C3-ESCC-device-evidence/navipilot_live_readonly_$(date +%Y%m%d_%H%M%S).json \
  --output ~/Desktop/CarrotPilot-C3-ESCC-device-evidence/navipilot_live_readonly_$(date +%Y%m%d_%H%M%S).md
```

This covers Carrot Web health, safe params bulk, UDP 7705 status, 7712/7713 Navipilot health, phone speed state, and Fishop read-only evidence. Do not add `--write-same-value` or `--send-navigation-probe` unless the C3 clearly reports parked/offroad.

Parked hardware probe after install or model/camera/sensor/sound changes:

```bash
python3 scripts/personal/sunnypilot_c3_device_collect.py \
  --host 192.168.100.174 \
  --navipilot-live-check \
  --require-no-cloud-processes \
  --parked-hardware-probe \
  --imu-probe \
  --ui-capture
```

This probe is silent by default. Only add `--with-sound-probe` when the user explicitly wants an audible speaker test.

Explicit C3 camera snapshot evidence, separate from modeld/camera stream checks:

```bash
python3 scripts/personal/sunnypilot_c3_device_collect.py \
  --host 192.168.100.174 \
  --require-no-cloud-processes \
  --camera-snapshot \
  --ui-capture
```

The camera snapshot path uses `scripts/personal/sunnypilot_c3_camera_snapshot_probe.py`, which wraps upstream `system/camerad/snapshot.py`. It is opt-in and silent.

Offline replay checks before or alongside C3 testing:

```bash
python3 scripts/personal/genius_ui_replay_check.py --json
python3 scripts/personal/genius_ui_replay_check.py --run-ui-replay
python3 scripts/personal/genius_offline_replay_check.py --json
/tmp/gp-replay-py312/bin/python scripts/personal/build_mac_replay_shadow.py --json
PYTHONPATH=/tmp/gp-replay-shadow:/path/to/repo /tmp/gp-replay-py312/bin/python \
  scripts/personal/genius_offline_replay_check.py \
  --run-process-replay --procs controlsd,plannerd,radard,locationd,paramsd --cars HYUNDAI --jobs 1 --timeout 420
/tmp/gp-replay-py312/bin/python scripts/personal/genius_model_manager_contract.py --json
python3 scripts/personal/genius_super_advanced_contract.py --json
python3 scripts/personal/genius_c3_touch_contract.py --json
python3 scripts/personal/genius_no_car_evidence_bundle.py --full-gate --json
python3 scripts/personal/genius_no_car_completion_audit.py --json
tools/replay/replay --demo
```

Use process replay for logic regressions and C3 probes for physical hardware evidence. Model replay that needs camera frames should follow `selfdrive/test/process_replay/model_replay.py` or provide `FrameReader` inputs.
When calling upstream `test_processes.py` directly, pass process and car whitelists as repeated arguments, not comma-separated strings. On macOS, run `scripts/personal/build_mac_replay_shadow.py` first with the replay Python 3.12 environment. It builds ignored local-only `rednose` and `acados` native extensions, preserving the checked-in C3/Linux `.so` files while letting `plannerd`, `locationd`, and `paramsd` import on Mac. Current HYUNDAI no-car replay is crash-free and native-unblocked, but still reports fork reference diffs until Genius/Carrot-owned baselines are generated.
For macOS UI diff replay, keep caller-provided `PYTHONPATH` entries ahead of the repo path so temporary native extension shadows can override C3/Linux extension files, and keep a temporary `PARAMS_ROOT` so replay does not depend on the user's home params directory.

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
- The packed TICI updater is not the same file as the main source tree. If Wi-Fi, dependency handling, touch handling, or updater buttons change, audit the embedded updater payload too.
- Fresh `/x` installs must have `jeepney` available or the packed updater must carry the `nmcli` fallback; otherwise C3 update/setup paths can crash before the normal UI Wi-Fi fallback helps.
- Clone C3 setup/update screens are more touch-jitter sensitive than normal settings pages. Keep the strict default tap threshold for ordinary widgets, but preserve the wider per-widget tolerance and parent-level fallback actions on TICI/MICI setup and updater install buttons so dependency/install prompts can advance reliably.

## Git Hygiene

The local Mac workspace can be slow because some files are managed by system sync. Prefer targeted file reads and targeted Git commands. Avoid broad `git status` unless necessary. If a status-like check is needed, prefer:

```bash
GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false -c gc.auto=0 status --short --untracked-files=no
```

Do not delete or revert user changes. Do not use destructive Git commands unless the user explicitly asks for them.
