# CarrotPilot-C3-ESCC Alpha Code Changes

## 2026-06-19 Installer Fix

The first `/x` alpha installer on GitHub Pages was the old Qt-style installer. On C3 this can show the device setup download progress and then exit before the SunnyPilot installer UI appears.

The published `/x` file has been replaced with a SunnyPilot Raylib ARM64 installer patched for this repository and branch:

- URL: `https://jiangnangenius.github.io/CarrotPilot-C3-ESCC/x`
- repo: `https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git`
- branch: `alpha-sunnypilot-c3`
- sha256: `fa75f760437bb6cfab97c0830d6be426206dc5a9deb62b37921349c63a355343`
- expected traits: ARM64 ELF, size about 1.3 MB, contains `Initializing raylib`
- forbidden traits: `QProgressBar`, `sshane/openpilot-installer-generator`, SunnyPilot upstream repo/branch strings

`scripts/personal/sunnypilot_c3_installer_audit.py` now checks this contract. Use it before republishing `/x`:

```bash
python3 scripts/personal/sunnypilot_c3_installer_audit.py --json
```

For a pinned release, pass the expected hash:

```bash
python3 scripts/personal/sunnypilot_c3_installer_audit.py \
  --expected-sha256 fa75f760437bb6cfab97c0830d6be426206dc5a9deb62b37921349c63a355343
```

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
