# CarrotPilot-C3-ESCC Agent Rules

This repository is a personal C3 Chinese-clone build for a Kia Seltos 2023 pure-CAN car. Treat driving, safety, install, and hardware changes as high risk.

## Default Goal

When the user asks to "update", "continue updating", "sync the three versions", or similar, update this project against these reference lines:

- `origin` / `ajouatom/openpilot`: main CarrotPilot base. Prefer `c3-wip` and `carrot-wip` for current CarrotPilot direction.
- `fishop` / `jihulab.com/fishop/openpilot`: fishop / Masha Feiyang reference. ESCC support is mandatory to preserve.
- `jixie` / `jixiexiaoge/openpilot`: mechanical-xiaoge / atune reference. Auto-Tuner and related UI/server ideas are reference sources.
- `jixie-navipilot` / `jixiexiaoge/navipilot`: CPdazi / Navipilot Android app reference for local network, navigation, driving reports, and UDP field compatibility.
- `mrone` / `jihulab.com/mr-one/onepilot` when available: C3/C3X 0.11-style reference, especially `devc3`.
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
- `experimental/latest-model-supercombo`: alpha model-runtime experiment development branch.
- `alpha-supercombo`: short install alias for `experimental/latest-model-supercombo`, required because the binary installer template cannot use branch names with `/`.
- Installer may expose `alpha-supercombo` as `--channel alpha`, but it is not a daily driving target.
- Do not promote `experimental/latest-model-supercombo` to `latest`, `stable`, or default install without explicit road-test evidence.

## Latest Model / Supercombo Rule

Treat official master supercombo work as a separate alpha line:

- Do not mix supercombo migration with ESCC, Seltos, AlwaysOffroad, Connect, or Navipilot feature changes.
- Start from the plan in `docs/personal/LATEST_MODEL_SUPERCOMBO_LINE.md`.
- First prove `modeld`, `modelV2`, `drivingModelData`, and `cameraOdometry` run on a parked C3.
- If C3 reports `tici`, `tizi`, or another model string differently than expected, document it before changing hardware logic.

## Release Rules

Only update public install targets after checks pass:

```bash
git push github personal/c3-escc-atune
git push github HEAD:refs/heads/install-c3-escc-test
git tag -f latest HEAD
git push -f github refs/tags/latest
```

When `scripts/personal/install_c3_escc.sh` changes, update the release script asset and GitHub Pages `/s` short script as part of the same release task.

If exposing alpha through Custom Software, build/upload a separate `installer_c3_escc_alpha` binary pointing at `alpha-supercombo`; do not repoint the default `installer_c3_escc`.

## Safety Notes

- Never assume a clone C3 behaves like C3X or C4 just because the CPU family is similar.
- Compare `tici`, `tizi`, and `mici` paths explicitly before copying hardware code.
- Avoid compatibility aliases or dead settings unless a real installed version requires migration.
- Prefer a blocked/experimental branch over a risky "mostly works" install target.
