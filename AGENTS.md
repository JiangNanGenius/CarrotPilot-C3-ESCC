# CarrotPilot-C3-ESCC Agent Rules

This repository is a personal C3 Chinese-clone build for a Kia Seltos 2023 pure-CAN car. Treat driving, safety, install, and hardware changes as high risk.

## Default Goal

When the user asks to "update", "continue updating", "sync the three versions", or similar, update this project against these reference lines:

- `origin` / `ajouatom/openpilot`: main CarrotPilot base. Prefer `c3-wip` and `carrot-wip` for current CarrotPilot direction.
- `fishop` / `jihulab.com/fishop/openpilot`: fishop / Masha Feiyang reference. ESCC support is mandatory to preserve. Also track its domestic navigation, lane-curve/lane-data, external lidar/side blindspot hardware, and auto-overtake features as optional hardware modules.
- `jixie` / `jixiexiaoge/openpilot`: mechanical-xiaoge / atune reference. Auto-Tuner and related UI/server ideas are reference sources.
- `jixie-navipilot` / `jixiexiaoge/navipilot`: CPdazi / Navipilot Android app reference for local network, navigation, driving reports, and UDP field compatibility.
- `mrone` / `jihulab.com/mr-one/onepilot` when available: C3/C3X 0.11-style reference, especially `devc3`.
- `mrone-openpilot` / `jihulab.com/mr-one/openpilot` when available: Mr.One `op.mr-one.cn` installer target. Use `devc3` and `res` only as C3/TICI compatibility patch references; do not use them as the main upstream base.
- `sunnypilot` / `sunnypilot/sunnypilot`: official SunnyPilot upstream for 0.11+ architecture, model manager, `modeld_v2`, and current `staging`/`master`/`dev` baselines.
- `commaai/openpilot`: official upstream reference for modeld, cereal, device branches, and release architecture.

## Protected Local Requirements

Always preserve these unless the user explicitly changes the target:

- Device: C3 Chinese clone, not C3X.
- Car: Kia Seltos 2023, pure CAN, initially equivalent to Seltos 2021.
- ESCC hardware support must remain available but default off.
- `EnableConnect=0` by default.
- `AlwaysOffroad=0` by default and separate from Connect/offline behavior.
- `CanfdHDA2=0` for Seltos 2023.
- Speed-camera default target must stay neutral: `AutoNaviSpeedLimitOffset=0`, `AutoNaviSpeedSafetyFactor=100`.
- Do not move `latest`, `install-c3-escc-test`, or release assets after experimental work unless explicitly asked and checks pass.
- For the SunnyPilot 0.11+ alpha line, do not expose Sunnylink, comma connect, onroad uploads, remote pairing, or cloud backup as user features.
- For the SunnyPilot 0.11+ alpha line, use SunnyPilot `OffroadMode` for the always-offroad behavior; do not add `AlwaysOffline` or another compatibility alias.

## Update Procedure

1. Fetch references:

```bash
python3 scripts/personal/update_audit.py --fetch
python3 scripts/personal/upstream_update_plan.py --fetch
```

2. Review high-risk paths before merging:

```text
opendbc_repo/opendbc/car/hyundai/
opendbc_repo/opendbc/dbc/
panda/board/safety/
common/params_keys.h
cereal/*.capnp
selfdrive/controls/
selfdrive/modeld/
selfdrive/carrot/
selfdrive/carrot_settings.json
system/manager/
system/hardware/
scripts/personal/install_c3_escc.sh
```

3. Merge conservatively. Prefer small commits by subsystem:

- base CarrotPilot sync
- ESCC/Seltos safety preservation
- Auto-Tuner / mechanical-xiaoge features
- Navipilot / local network compatibility
- installer/docs/checklist updates
- model architecture experiments

4. Run gates before pushing:

```bash
python3 scripts/personal/smoke_check.py
python3 scripts/personal/escc_offroad_preflight.py --no-manual
python3 scripts/personal/cplink_preflight.py --no-manual
python3 scripts/personal/feature_boundary_check.py --no-manual
python3 scripts/personal/release_integrity_check.py
```

5. If changing settings, installer defaults, release channels, or install assets, also run:

```bash
python3 -m json.tool selfdrive/carrot_settings.json >/tmp/carrot_settings.json.check
python3 -m json.tool docs/personal/INSTALL_TARGETS.json >/tmp/install_targets.json.check
sh -n scripts/personal/install_c3_escc.sh
scripts/personal/install_c3_escc.sh --list-channels
```

## Branch Policy

- `personal/c3-escc-atune`: main integration branch.
- `install-c3-escc-test`: current controlled-test install branch.
- `latest` tag/release: points to the current controlled-test install target.
- `experimental/latest-model-supercombo`: legacy alpha model-runtime experiment branch. Keep it separate from the SunnyPilot 0.11+ architecture line.
- `alpha-supercombo`: legacy short install alias for `experimental/latest-model-supercombo`; do not use it as the current `/x` alpha target.
- `experimental/sunnypilot-011-c3`: full SunnyPilot 0.11+ C3 alpha architecture branch based on official SunnyPilot `staging`.
- `alpha-sunnypilot-c3`: short install alias for `experimental/sunnypilot-011-c3`.
- `/x`: GitHub Pages short installer entry for `alpha-sunnypilot-c3`; `/i`, `latest`, and controlled-test release assets must keep pointing at the stable C3 line unless the user explicitly promotes a verified build.
- Installer `--channel alpha` and Pages `/x` should point to `alpha-sunnypilot-c3`. The older `alpha-supercombo` line is not the current alpha target and is not a daily driving target.
- Do not promote `experimental/latest-model-supercombo` to `latest`, `stable`, or default install without explicit road-test evidence.

## Latest Model / Supercombo Rule

Treat official master supercombo work as a separate alpha line:

- Do not mix supercombo migration with ESCC, Seltos, AlwaysOffroad, Connect, or Navipilot feature changes.
- Start from the plan in `docs/personal/LATEST_MODEL_SUPERCOMBO_LINE.md`.
- For the broader 0.11+ migration, start from `docs/personal/SUNNYPILOT_C3_LATEST_ARCHITECTURE_PLAN.md`.
- Prefer official SunnyPilot `staging` or `master` as the new-architecture base. Treat Mr.One `devc3`/`res` as compatibility patch samples only.
- Never copy Mr.One C3 patches wholesale. In particular, review and justify power shutdown changes, TICI branch-gate bypasses, registration/cloud changes, extra clients, and process changes before porting.
- First prove `modeld`, `modelV2`, `drivingModelData`, and `cameraOdometry` run on a parked C3.
- If C3 reports `tici`, `tizi`, or another model string differently than expected, document it before changing hardware logic.

## SunnyPilot 0.11+ Full Architecture Rule

When the user asks to continue the new SunnyPilot architecture work, follow `docs/personal/TODO.md` P8 before making code changes.

- Start from official SunnyPilot `staging` 0.11.2 for `experimental/sunnypilot-011-c3`.
- Treat Mr.One `devc3` and `res` only as C3/TICI compatibility patch references.
- Do not import Mr.One private registration, upload, extra clients, shutdown bypasses, or broad safety/opendbc changes.
- Hard-disable cloud processes in the alpha branch: `manage_athenad`, `uploader`, `manage_sunnylinkd`, `sunnylink_registration_manager`, `statsd_sp`, and `backup_manager`.
- Keep local Wi-Fi, SSH, local Web, GitHub update, model list download, and model download paths.
- Add `KIA_SELTOS_2023` by reusing the known-good Seltos 2021 SCC pure-CAN path; exclude `KIA_SELTOS_2023_NON_SCC` from the personal build.
- Use SunnyPilot native ESCC auto-detection from message `0x2AB`; do not add a normal user-facing ESCC manual switch in this branch.
- Use SunnyPilot native model manager and `modeld_tinygrad`; old Carrot model selector code is only a validation and rollback reference.
- Add phone/APN/N/Navipilot speed-limit data as a fresh, timeout-protected source above car speed limit and mapd; keep Mapbox/Kakao/Carrot route display optional and default off through `CarrotMapOverlayEnabled=0`.
- Migrate Carrot, CP搭子/Navipilot, fishop hardware-enhanced sensing, Auto-Tuner, and high-risk controls behind independent safe defaults. Red-light stop, auto-turn decel, active speed control, fishop auto-overtake, and Auto-Tuner auto-apply must be off by default.
- For fishop hardware features, first preserve read-only data paths for lane curves, left/right lane data, external lidar blindspots, side targets, sensor health, and freshness timestamps. Only after parked and road evidence may these inputs feed warnings, suggested lane changes, or controlled auto-overtake.
- fishop auto-overtake must use the existing safe lane-change chain. It must not bypass turn signals, stock/external blindspot checks, driver confirmation, speed gates, road-type gates, sensor freshness gates, or the Seltos 2023 vehicle gate.
- For fishop hardware updates, start by re-auditing `fishop/cp:selfdrive/carrot/amap_navi.py`, `fishop/cp:cereal/custom.capnp`, `fishop/cp:cereal/log.capnp`, and `fishop/cp:selfdrive/apilot.json`. Treat `lane`, `blindspot`, `cam_blind`, `overtake`, `navi`, and `lidar` as protocol inputs to prove, not as trusted control commands.
- Keep the fishop hardware flow in this order: protocol audit, read-only state bridge, evidence/UI display, warning or suggestion, existing lane-change safety chain, then controlled experiment. Do not skip stages even if the hardware is installed.

## Release Rules

Only update public install targets after checks pass:

```bash
git push github personal/c3-escc-atune
git push github HEAD:refs/heads/install-c3-escc-test
git tag -f latest HEAD
git push -f github refs/tags/latest
```

When `scripts/personal/install_c3_escc.sh` changes, update the release script asset and GitHub Pages `/s` short script as part of the same release task.

If exposing alpha through Custom Software, build/upload a separate `installer_c3_escc_alpha` binary pointing at `alpha-sunnypilot-c3`; do not repoint the default `installer_c3_escc`.

## Safety Notes

- Never assume a clone C3 behaves like C3X or C4 just because the CPU family is similar.
- Compare `tici`, `tizi`, and `mici` paths explicitly before copying hardware code.
- Avoid compatibility aliases or dead settings unless a real installed version requires migration.
- Prefer a blocked/experimental branch over a risky "mostly works" install target.
