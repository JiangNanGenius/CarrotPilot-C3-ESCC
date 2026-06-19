# CarrotPilot-C3-ESCC Alpha Code Changes

## 2026-06-19 Installer Fix

The first `/x` alpha installer on GitHub Pages was a SunnyPilot Raylib ARM64 installer patched for this repository. On the user's clone C3 it showed the setup download progress and then exited before the installer UI appeared.

The likely compatibility problem is that the Raylib installer binary requires newer runtime symbols such as `GLIBC_2.38`, while the C3 setup environment can be older. The published `/x` file has therefore been replaced with a Qt-compatible ARM64 installer derived from the known-working `gitop.vip/cp` binary and patched for this repository and branch:

- URL: `https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x`
- repo: `https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git`
- branch: `alpha-sunnypilot-c3`
- sha256: `e284ab3c54c671f6409e966765f04ef9f1b90a1ea0bafa6dfd9a71c7d4189c8d`
- expected traits: ARM64 ELF, size about 217 KB, contains `QProgressBar` and `GLIBC_2.17`
- forbidden traits: `GLIBC_2.38`, `Initializing raylib`, old `jihulab.com/fishop/openpilot.git`, SunnyPilot upstream repo/branch strings, and old `cp` checkout/reset strings

`scripts/personal/build_c3_qt_compat_installer.py` rebuilds this installer from the pinned source binary:

```bash
python3 scripts/personal/build_c3_qt_compat_installer.py --output /tmp/carrot_x_qt_compat
```

`scripts/personal/sunnypilot_c3_installer_audit.py` checks the published contract. Use it before republishing `/x`:

```bash
python3 scripts/personal/sunnypilot_c3_installer_audit.py --json
```

For a pinned release, pass the expected hash:

```bash
python3 scripts/personal/sunnypilot_c3_installer_audit.py \
  --expected-sha256 e284ab3c54c671f6409e966765f04ef9f1b90a1ea0bafa6dfd9a71c7d4189c8d
```

Do not switch `/x` back to a Raylib installer until the exact binary has been run on the user's C3 setup environment or the device runtime is confirmed to satisfy the required GLIBC symbols.

## Safety Boundary

This installer fix only changes the GitHub Pages `/x` binary and alpha verification tooling. It does not change vehicle control, model selection, ESCC, speed-limit resolution, or fishop hardware behavior.

## 2026-06-19 Update Gate

The alpha line now includes a repeatable future-agent workflow:

- `AGENTS.md` records branch rules, user hardware, Seltos 2023 SCC assumptions, cloud-removal boundaries, installer rules, and update order.
- `scripts/personal/sunnypilot_c3_alpha_release_gate.py` runs the fast local gate and can run the full pre-publish gate with `--full`.
- `scripts/personal/sunnypilot_c3_alpha_static_check.py` verifies the guide and release gate exist, and self-tests the gate.

Use the fast gate while developing:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py
```

Use the full gate before pushing an alpha installer change:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --full
```

## 2026-06-19 Upstream Update Audit

The alpha line now has a repeatable reference fetch/compare tool:

- `scripts/personal/sunnypilot_c3_alpha_update_audit.py` knows the SunnyPilot, ajouatom CarrotPilot, jixiexiaoge mechanical/Auto-Tuner, and dhvms ESCC reference branches.
- It can fetch those branches into `refs/remotes/carrot-audit/*` without changing normal Git remotes.
- It compares watched paths for C3, Carrot, speed limit, model manager, UI/localization, fishop hardware, Hyundai opendbc, and process/installer behavior.
- It can scan reference branches for cloud/private/power-risk tokens so those changes are reviewed instead of accidentally imported.
- `scripts/personal/sunnypilot_c3_alpha_release_gate.py --fetch-references` can run this audit as part of the release gate.

Use this before future upstream merges:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_update_audit.py --fetch --strict --scan-risk-tokens --json
```

Initial reference baseline fetched on 2026-06-19:

- `sunnypilot-staging`: `0a6503e5039c`, watched changes `34`, risk hits capped at `40`
- `sunnypilot-release-tizi`: `fba34f341fa7`, watched changes `134`, risk hits capped at `40`
- `ajouatom-carrot-wip`: `825182c39dbc`, watched changes `446`, risk hits `3`
- `ajouatom-c3-wip`: `ccfcabd7d3ae`, watched changes `492`, risk hits `3`
- `jixiexiaoge-master`: `3b039d270ff5`, watched changes `306`, risk hits `0`
- `jixiexiaoge-atune`: `8e2edc9666ce`, watched changes `492`, risk hits `3`
- `jixiexiaoge-cp`: `ccfcabd7d3ae`, watched changes `492`, risk hits `3`
- `jixiexiaoge-release-new`: `4c2778214235`, watched changes `306`, risk hits `6`
- `dhvms-carrotpilot-master`: `be766a9dad2b`, watched changes `403`, risk hits `2`

Risk-token hits in reference branches do not fail the audit by themselves. They are review evidence so cloud/private/power behavior is not copied into this personal alpha by accident.

## 2026-06-19 C3 Device Evidence Collector

`scripts/personal/sunnypilot_c3_device_collect.py` can SSH to the clone C3, collect install/launch logs, process lists, safe params, network listeners, and a Carrot alpha snapshot, then fetch a tarball back to the Mac desktop.

Normal parked evidence after `/x` installs:

```bash
python3 scripts/personal/sunnypilot_c3_device_collect.py \
  --host 192.168.100.174 \
  --navipilot-live-check \
  --require-no-cloud-processes
```

Installer crash/download-screen exit evidence:

```bash
python3 scripts/personal/sunnypilot_c3_device_collect.py \
  --host 192.168.100.174 \
  --skip-snapshot
```

The collector intentionally reads only safe params and logs. It does not collect SSH private keys and does not write vehicle-control params.
