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

## 2026-06-19 Alpha Verification Refresh

After replacing `/x` with the Qt-compatible C3 installer, the alpha line was verified from a clean workspace at commit `31d58e626f4a99c573dd51d9771edf637e1bca51`.

Passed gates:

```bash
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --full
python3 scripts/personal/sunnypilot_c3_installer_audit.py \
  --expected-sha256 e284ab3c54c671f6409e966765f04ef9f1b90a1ea0bafa6dfd9a71c7d4189c8d
python3 scripts/personal/build_c3_qt_compat_installer.py \
  --source-file /tmp/gitop_cp \
  --output /tmp/carrot_x_qt_compat_from_published_source
python3 scripts/personal/sunnypilot_c3_alpha_update_audit.py \
  --fetch --strict --scan-risk-tokens --json
```

Update audit result: `ok=True`, `watchPathCount=26`, `riskTokenCount=14`. Reference branches were refreshed and reviewed at the same commits listed in the initial baseline above. The highest-risk reviewed deltas remain SunnyPilot cloud/Sunnylink/uploader code in reference branches and are intentionally not imported into this personal alpha.

Open evidence still required before promoting alpha to stable/latest:

- `/x` install retry on the clone C3.
- Parked C3 snapshot showing no cloud/upload processes and working local Web/SSH/update/model manager.
- Seltos 2023 SCC/ESCC road evidence with stock model and Carrot high-risk controls off.

## 2026-06-19 Carrot-First Product Direction

The alpha line is now documented as CarrotPilot-first:

- SunnyPilot 0.11 remains the architecture base for C3 compatibility, model manager, and newer runtime structure.
- User-facing cruise and speed-control behavior should converge toward CarrotPilot's granular settings and evidence-first workflow.
- SunnyPilot ICBM, SCC-V, SCC-M, and Dynamic Experimental Control are not personal-build features; they are hidden from the Cruise panel and old params are removed during interface setup.
- Carrot, Auto-Tuner, APN/N/Navipilot, Fishop hardware, and ESCC features should be migrated as explicit controls with Chinese/English descriptions, safe defaults, and per-feature validation gates.
- High-risk output paths remain off until parked evidence, road logs, and rollback paths are proven.

This direction is captured in `AGENTS.md` and `docs/personal/TODO.md` so future updates do not drift back to SunnyPilot black-box cruise behavior.

## 2026-06-19 C3 UI Hotfix Direction

Real-device feedback on the clone C3 found four UI issues after the settings tap fix:

- Network page stayed at "Scanning Wi-Fi networks..." although NetworkManager was already connected. The C3 runtime lacked the Python `jeepney` DBus package, so the Wi-Fi manager never started. The fix keeps the DBus path when available and adds an `nmcli` fallback for scan, active SSID, saved connections, IP address, connect, forget, activate, and metered state.
- Opening settings from the left sidebar gear could immediately close the page. The root cause is the opening touch being reused by the settings page. The fix adds a one-touch guard when settings is opened.
- The sidebar temperature card showed only `GOOD`/`HIGH`. It now displays `deviceState.maxTempC` as a number when available, while preserving warning coloring.
- Simplified Chinese localization needs continuous cleanup. The immediate target is the high-use alpha pages: Device, Network, Cruise, Speed Limit, Models, Carrot, Visuals, and Developer.

Implementation notes added after the first device sync:

- The main source-tree Wi-Fi manager now keeps the `jeepney` DBus path when available and falls back to `nmcli` when that Python package is missing.
- The user's C3 proved that the runtime virtualenv had `zmq` but did not have `jeepney`; the fallback successfully reported the connected SSID, IP address, and nearby networks.
- A direct `pip install jeepney` into `/usr/local/venv` failed because that filesystem is read-only on the C3, so dependency repair must be part of the installer/update package rather than a manual device mutation.
- The packed TICI updater is a separate embedded Python payload and still contained the old direct `jeepney` import. Fresh release work must either install `jeepney` before that updater runs or rebuild/patch the packed updater so it has the same fallback.
- Settings page touch handling now ignores the touch that opened the page, so the sidebar gear cannot immediately close settings.
- SunnyPilot ICBM, SCC-V, SCC-M, and DEC are hidden and forced inert in the personal alpha. Any future speed-control work should be implemented as Carrot/Genius Pilot granular controls, not by re-enabling those SunnyPilot black-box toggles.
- The sidebar temperature label now prefers numeric `maxTempC` and only uses the color state as a warning hint.
- A Simplified Chinese overlay was added for the high-use alpha pages, but this is the first pass; real-device wording feedback should continue to update the `.po` file and the setting descriptions.

Open follow-up from the same bench test:

- Replace user-facing SunnyPilot branding with Genius Pilot where it is accurate and does not conflict with upstream package names.
- Keep the welcome/training flow, but replace the long SunnyPilot consent copy with short personal-build copy and verify that Agree advances on C3.
- Build a real Carrot-style settings surface. The alpha must not feel like SunnyPilot with a few hidden toggles; CarrotPilot, mechanical/Auto-Tuner, ESCC, APN/N, and Fishop controls need explicit settings, descriptions, defaults, and evidence gates.

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
