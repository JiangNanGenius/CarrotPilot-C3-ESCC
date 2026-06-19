# CarrotPilot-C3-ESCC Alpha Code Changes

## 2026-06-20 Navipilot/APN/N Replay Contract

Added a dedicated local replay contract for the Navipilot/APN/N navigation bridge:

- Added `scripts/personal/genius_navipilot_replay_contract.py`.
- The contract replays flat UDP/APN-style navigation input, `rgdata` compatibility input, and `sinf`/`ssinf` traffic-light input without needing a C3.
- It confirms phone speed, SDI, speed-bump, red/green traffic-light, turn, and model-speed fields are parsed into local evidence.
- It confirms Carrot status broadcast fields preserve TBT, SDI, speed-bump, model-speed, traffic-light, and phone-speed evidence.
- It confirms high-risk navigation commands are kept as ignored evidence and every replay remains read-only with `controlOutput=false`.
- The alpha release gate and static check now run this contract explicitly.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.14`.

## 2026-06-20 Local Carrot Web/API Contract

Added a dedicated local API contract for the Carrot Web parameter bridge:

- Added `scripts/personal/genius_carrot_web_api_contract.py`.
- The contract writes and reads back Carrot active speed, auto-turn, traffic-light stop, Fishop overtake, curve-speed mode, NNLC, and Genius visualization params while offroad.
- It confirms cloud params are not exposed through the local API.
- It confirms read-only params such as `OffroadMode`, `SpeedFromPCM`, and `SshEnabled` reject writes.
- It confirms changed writes are blocked while onroad while same-value probes remain harmless.
- The alpha release gate and static check now run this contract explicitly.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.13`.

## 2026-06-20 Carrot World Visualization Overlay

Added a separate Carrot-style world evidence overlay instead of mixing every visual system into one renderer:

- Added `GeniusCarrotWorldOverlay`, default off, on the Visuals page and local Carrot Web/API.
- The overlay draws side-lane, blindspot, lane-change, lead, and radar evidence on top of Sunny, Carrot, or Fusion.
- The base presets remain mutually exclusive: Sunny, Carrot, or Fusion. Fishop and Carrot World are independent overlays.
- The current implementation uses only fields available in the SunnyPilot 0.11 base and does not fake ajouatom-only side radar/lane schema.
- `scripts/personal/genius_visualization_contract.py` now checks the Carrot world overlay wiring and display-only boundary.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.12`.

## 2026-06-20 User-Facing Branding And Firehose Cloud Removal

Cleaned up another user-facing SunnyPilot/cloud-upload surface:

- Firehose now displays `Data Uploads Disabled` and explains that Genius Pilot keeps cloud training uploads off.
- The Firehose page no longer imports or calls the upstream firehose API, device token helper, registration dongle ID, or request session.
- The alpha snapshot title is now `Genius Pilot C3 Alpha Snapshot`.
- Cruise policy copy no longer labels the hidden ICBM/SCC-V/SCC-M group as a SunnyPilot feature in the visible description.
- Simplified and Traditional Chinese translations were added for the new local/no-cloud Firehose copy.
- Added `scripts/personal/genius_branding_contract.py` and wired it into static/release gates so old SunnyPilot branding and Firehose upload client paths cannot silently return.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.11`.

## 2026-06-20 Visualization Ownership Tightening

Added `docs/personal/VISUALIZATION_POLICY.md` to make the display ownership rules explicit:

- One base preset is active at a time: Sunny, Carrot, or Fusion.
- Fusion remains the C3 default: Sunny HUD structure with Carrot-style lane/path/lead cues.
- Lane-line style, lead/radar display, and lane-change cues are editable visual details.
- Fishop/lidar is an independent evidence overlay, not a base preset and not a control gate.
- ajouatom Carrot cluster/world visualization is tracked as a separate future surface instead of being mixed directly into the main HUD.

`scripts/personal/genius_visualization_contract.py` now checks the policy doc, default visual params, preset callback behavior, and display-only boundaries.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.10`.

## 2026-06-20 Curve-Speed Ownership

`CurveSpeedControlMode` now owns the Sunny model-curvature slowdown path:

- Added `sunnypilot/selfdrive/controls/lib/smart_cruise_control/curve_speed_policy.py`.
- Sunny SCC-V now follows `CurveSpeedControlMode`: Off and Carrot disable it; Sunny and Fusion enable it.
- Sunny SCC-M remains inert in every Genius Pilot mode, so map target velocities do not become default speed truth.
- Legacy hidden `SmartCruiseControlVision` and `SmartCruiseControlMap` params no longer decide control behavior.
- Added `docs/personal/CURVE_SPEED_POLICY.md` and `scripts/personal/genius_curve_speed_contract.py`.
- The alpha release gate and static check now enforce the curve-speed policy.

Fusion now means Sunny model-curvature quality plus Carrot navigation/phone/lane inputs, without enabling Sunny map-speed control.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.9`.

## 2026-06-20 Visualization Replay Contract

Expanded `scripts/personal/genius_visualization_contract.py` so the local gate now checks the full display coexistence contract:

- Sunny, Carrot, and Fusion remain distinct base visual presets.
- Carrot path/ribbon, lane-line, lead-box, radar-label, and lane-change intent display paths are all required.
- Synthetic C3 replay geometry verifies nonblank path, lanes, lead box, and lane-change cues.
- The replay check keeps path, lanes, lead box, and lane-change cue below the top speed/HUD area.
- Display code remains read-only: it cannot publish planner/CAN/control messages, write params, open sockets, or alter lane-change decisions.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.8`.

## 2026-06-20 Genius Settings Matrix

Added a repeatable owner matrix for the imported settings and display modes:

- `scripts/personal/genius_settings_matrix.py` generates `docs/personal/SETTINGS_MATRIX.md` and `docs/personal/settings_matrix.json`.
- The matrix classifies each setting family as Carrot, Sunny primitive, Fishop hardware input, ESCC vehicle interface, model manager, local network/update, visualization, or removed cloud.
- Sunny/Carrot/Fusion visualization coexistence is now checked as a rule: one base visual preset at a time, with Fishop/lidar as an independent evidence overlay.
- DEC remains a Sunny primitive when longitudinal support is available; ICBM, SCC-V, SCC-M, Sunnylink, upload, and connect-style cloud controls stay hidden or inert.
- The alpha release gate and static check now run the settings matrix so future merges cannot silently reintroduce conflicting settings.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.7`.

## 2026-06-20 Genius Visualization Modes

The driving screen now has explicit visualization modes instead of a single SunnyPilot-style renderer:

- Added `GeniusVisualMode`: Sunny, Carrot, and Fusion presets.
- Added `GeniusLaneLineStyle`: Simple, Colored, and Carrot lane-line drawing.
- Added `GeniusLeadRadarVisualMode`: Sunny chevron, Carrot lead box, and radar speed labels.
- Added `GeniusLaneChangeVisuals` for model lane-change intent cues.
- Added `GeniusFishopVisualOverlay` as an independent display-only entry for Fishop lane/lidar/blindspot evidence.

The first renderer migration is display-only:

- TICI/C3 onroad model rendering now supports Sunny-compatible simple lanes, Sunny/MICI colored lane confidence, and Carrot-style adjacent-lane emphasis.
- Lead vehicles can be drawn as Carrot-style outline boxes, with radar/model colors and optional speed tags.
- Lane-change intent cues use the existing onroad event stream and do not alter lane-change control.
- Fishop overlay reads fresh local `/data/fishop_hardware.jsonl` evidence and draws compact left/right lane, lidar, camera, dynamic-risk, and overtake-hint status on top of any base preset.
- The route path itself now follows the visual preset: Sunny keeps the stock path, Carrot draws a route ribbon with edge/center track cues, and Fusion keeps the Sunny path body with light Carrot cues.
- Added `scripts/personal/genius_visualization_contract.py` to gate the path/lane/lead/Fishop display-only wiring and a synthetic C3 geometry check before alpha publishing.
- Visualization coexistence is explicit: Sunny, Carrot, and Fusion are mutually exclusive base presets; Fishop overlay is an independent top layer; every renderer switch remains display-only.

The legacy Sunnylink onboarding component is now inert if it is ever imported: it always keeps `SunnylinkEnabled=0`, records the cloud consent as declined, and shows short Genius Pilot local-mode text instead of remote-pairing copy.

Genius Pilot version is bumped to `2026.002.000-gp.20260620.6`.

## 2026-06-20 NNLC And Super Advanced Carrot Controls

The personal alpha now treats NNLC/NLC as a supported-car default:

- `NeuralNetworkLateralControl` defaults to `1`.
- SunnyPilot's existing unsupported-car cleanup remains in place, so angle-steering or unsupported NNLC-model vehicles remove the param automatically.
- The local Carrot Web/API whitelist exposes NNLC as a writable offroad setting.

The `Super Advanced` page has been expanded from a small staged page into a Carrot-first control hub:

- Speed/maps/navigation: phone speed source, map overlay, curve-speed mode, curve lower limit, curve factor, curve aggressiveness, navigation decel rate, active speed control, ATC/auto-turn, red-light stop, traffic-light mode, traffic-stop distance adjustment, and rain/wet mode.
- Cruise/longitudinal: Sunny DEC, Carrot driving mode, auto driving mode, Eco, cruise decel, ATC decel, stop distance, dynamic following, speed-based following, lane-change following, follow gaps, cruise acceleration table, long gains, actuator delay, stopping threshold, radar reaction, lead response, and acceleration-change cost.
- Steering/path: turn-speed mode, Auto Turn Control, turn-control speed/end/map adaptation, path offset, steer actuator delay, steer ratio rate, lane-line speed, and lane-line curve speed.
- Fishop hardware: lane curve, lidar blindspot, lidar lane data, and auto-overtake settings.

Important behavior changes:

- Carrot active speed, ATC/auto-turn, red-light stop, and Fishop auto-overtake are no longer forcibly reset to off by the UI.
- Those advanced settings default off but are user-toggleable while offroad.
- Sunny DEC remains available and no longer disables Carrot active speed, ATC, or red-light stop.
- Sunny ICBM, SCC-V, and SCC-M remain hidden/inert because they overlap with Carrot cruise and speed behavior.
- The local Carrot Web/API now allows these advanced params to be changed while offroad, while onroad writes are still rejected.
- `SpeedLimitMode` can be set through assist mode by the local API while offroad.
- The local Web status page uses normal feature status wording instead of describing the Carrot/Fishop features as locked.

Runtime parameter support:

- Added the first batch of Carrot/CarrotPad-style params for ATC, curve speed, red-light stop, driving mode, longitudinal gains, follow behavior, lane-line curve input, and Fishop hardware.
- Rebuilt `common/params_pyx.so` on the user's aarch64 C3 so the new params are recognized by the device runtime.
- Static verification now checks the new key strings inside the ARM64 `.so`.

Verification:

```bash
python3 -m py_compile \
  selfdrive/ui/sunnypilot/layouts/settings/carrot.py \
  selfdrive/ui/sunnypilot/layouts/settings/cruise.py \
  selfdrive/carrot/carrot_server.py

python3 scripts/personal/sunnypilot_c3_alpha_static_check.py
```

## 2026-06-20 Genius Pilot Versioning

The alpha line now has its own visible version number while keeping the
SunnyPilot upstream version as the base.

Current format:

```text
Genius Pilot 2026.002.000-gp.20260620.1
```

Rules:

- `2026.002.000` follows the SunnyPilot base.
- `gp` marks the Genius Pilot personal build.
- `20260620` is the publish date.
- The final number is the same-day Genius Pilot alpha patch number.

The version is now used by the updater description and by the home/software UI
fallbacks, so the device no longer has to show a generic SunnyPilot version on
the personal alpha line.

## 2026-06-20 CJK Font And Settings Entry Hotfix

Real-device feedback showed the first Chinese localization pass could render some UI strings as question marks because the generated `unifont.fnt` atlas did not include newly added Chinese glyphs, and the unifont design was visibly pixelated.

Changes:

- Added Noto Sans CJK SC Regular as the CJK fallback font for Simplified Chinese, Traditional Chinese, and Japanese.
- Kept `unifont` as the broad fallback for Thai and symbols/scripts not covered by Noto CJK.
- Updated the font generator so CJK fonts receive the extended translation glyph set.
- Updated raygui text boxes to use the same language fallback font path as normal text rendering.
- Added static checks that the CJK fallback is wired, Noto CJK contains common Chinese settings glyphs, and unifont remains available as a broad fallback.

Real-device feedback also showed the left sidebar gear was still too sensitive and could open settings and immediately close it from the same touch sequence.

Changes:

- Sidebar gear now opens settings on touch release instead of touch press.
- Settings entry now ignores close/sidebar touch handling for 0.6 seconds after opening and until the opening touch is released.

## 2026-06-20 Clone C3 Menu Touch And Vehicle Selector Hotfix

Real-device feedback showed settings menus were still too easy to trigger accidentally on the user's clone C3 touch panel.

Changes:

- Reduced generic tap movement tolerance from 42 px to 24 px.
- Cancel a widget click if its touch becomes invalid during a scroll gesture.
- Raised the vertical list drag threshold to 24 px so click and scroll thresholds align.
- Settings sidebar panel selection now records press state and only switches panels on a valid release.

UI organization changes:

- The former `Carrot` sidebar panel is now labeled `Super Advanced`.
- Cruise now exposes common staged longitudinal controls directly: Speed Limit entry, Sunny DEC, Carrot stop distance, dynamic following, decel follow boost, and follow-gap presets.
- `Kia Seltos 2023` is now present in `sunnypilot/selfdrive/car/car_list.json` so the manual vehicle selector can show the `KIA_SELTOS_2023` profile.

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
- SunnyPilot ICBM, SCC-V, and SCC-M are not personal-build features; they are hidden from the Cruise panel and old params are removed during interface setup.
- Sunny DEC is treated differently: it can remain as an off-by-default advanced longitudinal candidate, exposed under Carrot/Genius settings with conflict warnings.
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
- The packed TICI updater is a separate embedded Python payload. It is now patched with the same Wi-Fi manager as the main tree, so fresh installs and updater boots get the `nmcli` fallback when `jeepney` is absent.
- `scripts/personal/patch_tici_updater_wifi_manager.py --check` and the alpha static/release gates now compare the updater's embedded `openpilot/system/ui/lib/wifi_manager.py` against `system/ui/lib/wifi_manager.py` and reject stale packed payloads.
- Settings page touch handling now ignores the touch that opened the page, so the sidebar gear cannot immediately close settings.
- SunnyPilot ICBM, SCC-V, and SCC-M are hidden and forced inert in the personal alpha. DEC is retained only as an off-by-default candidate because it controls E2E/classic longitudinal selection rather than directly replacing Carrot curve/map speed logic.
- The sidebar temperature label now prefers numeric `maxTempC` and only uses the color state as a warning hint.
- A Simplified Chinese overlay was added for the high-use alpha pages, but this is the first pass; real-device wording feedback should continue to update the `.po` file and the setting descriptions.
- After pushing commit `ec7e73dc`, the user's C3 was aligned to `alpha-sunnypilot-c3` and the working tree was clean. The Wi-Fi fallback reported connected SSID `zhao`, IP `192.168.100.174`, and 13 scanned networks after the UI-style activation path.
- A quick process check found no `athenad`, `sunnylinkd`, `uploader`, `statsd_sp`, or `backup_manager` process running.

Open follow-up from the same bench test:

- Replace user-facing SunnyPilot branding with Genius Pilot where it is accurate and does not conflict with upstream package names.
- Keep the welcome/training flow, but replace the long SunnyPilot consent copy with short personal-build copy and verify that Agree advances on C3.
- Build a real Carrot-style settings surface. The alpha must not feel like SunnyPilot with a few hidden toggles; CarrotPilot, mechanical/Auto-Tuner, ESCC, APN/N, and Fishop controls need explicit settings, descriptions, defaults, and evidence gates.

## 2026-06-20 Settings Conflict Audit And Carrot Settings Split

Real-device feedback confirmed that the first Carrot settings page was operational but too flat and incomplete. The Carrot/Genius page has been split into categories:

- Speed Limit, Maps, and Navigation
- Cruise and Longitudinal Control
- Auto-Tuner
- Steering and Path
- Fishop Hardware
- Local Web and Evidence

The first pass exposed existing personal params instead of inventing new control behavior: phone speed source, map overlay, Carrot advanced output switches, DEC candidate mode, stop/follow/braking tuning targets, cruise acceleration table entries, Auto-Tuner apply/clear/reset actions, path/steer tuning values, and Fishop lane/lidar input gates.

Cross-branch setting conflict audit was added as `scripts/personal/sunnypilot_c3_settings_conflict_audit.py`. Current findings:

- SunnyPilot `staging` and `release-tizi` keep `SunnylinkEnabled=1` and `OnroadUploads=1`; personal alpha keeps them inert/off.
- ajouatom and jixiexiaoge older Carrot branches expose `EnableConnect`; personal alpha must not expose it as a cloud-connect control.
- jixiexiaoge `release-new` has `OnroadUploads=1`; personal alpha keeps uploads off.
- DEC exists in Sunny and current alpha with default `0`; it can be retained as a candidate advanced longitudinal mode.
- SCC-V, SCC-M, and ICBM overlap more directly with Carrot speed, curve, map, and button behavior, so they stay hidden or inert.

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
