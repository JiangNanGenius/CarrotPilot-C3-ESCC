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
- High-risk features stay independently gated and default off: traffic-light stop, auto-turn slowdown, active speed control, Auto-Tuner auto-apply, and fishop auto-overtake.
- Fishop lane/lidar/blindspot/overtake work is evidence-only until staged logs, rollback, and real-car review prove the next step.

## Update Workflow

When the user says to update, use this order:

1. Fetch reference branches for SunnyPilot, CarrotPilot, mechanical/Auto-Tuner, and Mr.One C3 references.
2. Keep SunnyPilot `staging` as the alpha base unless the user explicitly changes the base.
3. Pull only necessary C3/TICI compatibility patches from Mr.One. Do not import private registration, upload clients, cloud pairing, never-shutdown logic, or broad safety/opendbc changes.
   In short: do not import private registration or upload/cloud client behavior from reference forks.
4. Compare Carrot changes for Carrot Web, CarrotMan/Navipilot/APN/N input, speed-limit logic, model/map behavior, Auto-Tuner, localization, and fishop hardware fields.
5. Preserve personal defaults: stock model, map overlay off, speed offset zero, phone speed policy with timeout, cloud disabled, high-risk controls off.
6. Run the release gate before pushing.
7. Push `experimental/sunnypilot-011-c3` and `alpha-sunnypilot-c3` together only after the gate passes.
8. Audit the published `/x` installer before telling the user to retry installation.

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

Real Seltos/ESCC evidence check, only after parked checks pass:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_evidence_check.py \
  /data/carrot_alpha_snapshot.json \
  --phase seltos-escc
```

## Installer Rules

- `/x` must be a SunnyPilot Raylib ARM64 installer, not the old Qt installer.
- `/x` must install `https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git` and `alpha-sunnypilot-c3`.
- `/x` must pass `scripts/personal/sunnypilot_c3_installer_audit.py`.
- `/i` remains the rollback stable installer.

## Git Hygiene

The local Mac workspace can be slow because some files are managed by system sync. Prefer targeted file reads and targeted Git commands. Avoid broad `git status` unless necessary. If a status-like check is needed, prefer:

```bash
GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false -c gc.auto=0 status --short --untracked-files=no
```

Do not delete or revert user changes. Do not use destructive Git commands unless the user explicitly asks for them.
