# CarrotPilot-C3-ESCC Alpha TODO

This file tracks the personal C3 alpha line. Stable daily use stays on `/i`; the SunnyPilot 0.11 alpha line is installed from `/x`.

## Installers

- [x] Keep `/i` as the stable `personal/c3-escc-atune` installer.
- [x] Publish `/x` as the alpha `alpha-sunnypilot-c3` installer.
- [x] Add Genius Pilot versioning that follows the SunnyPilot base and appends the published date plus same-day patch number.
- [x] Replace the incompatible Raylib `/x` binary with a C3 Qt-compatible ARM64 installer.
- [x] Verify the published `/x` binary contains the CarrotPilot-C3-ESCC repo and `alpha-sunnypilot-c3` branch.
- [x] Add `scripts/personal/build_c3_qt_compat_installer.py` so the Qt-compatible `/x` can be rebuilt reproducibly.
- [x] Add `scripts/personal/sunnypilot_c3_installer_audit.py` so future updates reject incompatible Raylib/new-GLIBC and stale upstream installer binaries.
- [x] Add `scripts/personal/sunnypilot_c3_device_collect.py` to collect installer crash logs or parked/model/no-cloud evidence from the C3 over SSH.
- [x] Recover from the first `/x` boot failures: missing Python dependency, settings tap release handling, and onboarding/settings navigation blockers.
- [x] Rebuild or patch the packed TICI updater so its embedded Wi-Fi manager includes the same `jeepney`/`nmcli` fallback as the main source tree.
- [x] Add an installer/update audit that checks both the main source tree and the packed TICI updater for the Wi-Fi dependency contract.
- [x] Keep the welcome/training flow, but replace SunnyPilot-specific legal/consent copy with Genius Pilot personal-build copy that is short enough for C3 and advances reliably.
- [x] Rename user-facing alpha branding from SunnyPilot to Genius Pilot where accurate: welcome screen, version/about panel, settings headers, update prompts, boot/update text, and alpha evidence snapshots.
- [ ] Keep `/x` as the single short alpha entry; avoid new test URLs unless there is a clear rollback reason.
- [ ] Bump the Genius Pilot suffix before every pushed alpha build: same date increments patch, new date resets patch to `1`, SunnyPilot base changes only when upstream base changes.
- [ ] After the next clean `/x` install, collect device evidence even if the install succeeds, so the success path is documented.

## Base And C3

- [x] Start from SunnyPilot 0.11.2 staging.
- [x] Define the alpha product direction as CarrotPilot-first: SunnyPilot is the architecture base, while cruise/speed behavior should converge to CarrotPilot-style granular controls.
- [x] Add C3/TICI channel gate for `alpha-sunnypilot-c3` and `experimental/sunnypilot-011-c3`.
- [x] Route clone C3 `comma tici` devices through the C3 launcher.
- [x] Keep normal shutdown policy; do not import Mr.One never-shutdown behavior.
- [x] Keep local Wi-Fi, SSH, local web, GitHub update, and model download paths.
- [x] Keep a robust local Wi-Fi UI on clone C3 even when the `jeepney` DBus dependency is absent; prefer DBus when available and fall back to `nmcli`.
- [x] Remove the fresh-install dependency on `jeepney` by patching the packed TICI updater to use the same `nmcli` fallback as the main Wi-Fi manager.
- [ ] Decide the permanent C3 rescue access policy: no GitHub/cloud registration required, no public hardcoded password in release builds, and a bench-only recovery method for the user's device.
- [ ] Verify local LAN services after every install: Wi-Fi status, SSH, local web, updater, model manager, and no dependency crashes in `/tmp/launch_log`.
- [ ] Run real device parking test on clone C3.
- [ ] Pull a C3 evidence bundle with `sunnypilot_c3_device_collect.py` after `/x` install succeeds.

## Cloud Removal

- [x] Disable manager registration for athenad, uploader, Sunnylink daemon, Sunnylink registration, statsd_sp, and backup manager.
- [x] Keep `SunnylinkEnabled`, `EnableSunnylinkUploader`, and `OnroadUploads` ineffective as cloud-start controls.
- [x] Remove user-facing Sunnylink and Onroad Uploads entry points from the alpha UI.
- [x] Confirm on device that no cloud/upload process exists after boot.

## Seltos 2023 And ESCC

- [x] Add `KIA_SELTOS_2023` as a pure-CAN SCC Seltos profile using the known Seltos 2021-compatible path.
- [x] Keep ESCC automatic through SunnyPilot enhanced SCC detection on `0x2AB`.
- [x] Do not add a broad manual ESCC switch.
- [x] Keep Non-SCC Seltos out of personal matching/selection.
- [x] Default NNLC/NLC on for supported cars by setting `NeuralNetworkLateralControl=1`; keep SunnyPilot's unsupported-car cleanup path so unsupported vehicles remove it automatically.
- [ ] Validate on the user's Kia Seltos 2023 with stock model and Carrot controls off first.

## Model Manager

- [x] Use SunnyPilot native model manager and `modeld_tinygrad`.
- [x] Keep stock model as default.
- [x] Restrict model download, verify, switch, and rollback to offroad.
- [ ] Verify model list download and active bundle evidence on C3.

## Speed Limit And Maps

- [x] Add phone/APN/N/Navipilot speed source with freshness timeout.
- [x] Default speed source order: fresh phone, car/instrument, Sunny OSM/mapd.
- [x] Keep route and map display from becoming speed-limit truth by default.
- [x] Default speed offset to zero.
- [x] Add fixed and percentage speed offset modes.
- [x] Default `CarrotMapOverlayEnabled` to off so Mapbox/Kakao overlay does not cover the HUD.
- [x] Hide and hard-disable SunnyPilot ICBM, SCC-V, and SCC-M in the personal alpha; cruise-speed behavior should move toward CarrotPilot logic instead of SunnyPilot black-box toggles.
- [x] Retain Sunny DEC as an off-by-default advanced longitudinal option, exposed in Cruise and Super Advanced without locking Carrot controls.
- [x] Add `CurveSpeedControlMode` with Off / Sunny / Carrot / Fusion so Sunny curve quality and Carrot navigation/phone inputs can be compared and then combined.
- [x] Add Carrot curve-speed tuning params: lower speed limit, curve factor, curve aggressiveness, navigation decel rate, and wet-road mode.
- [ ] Remove or relabel any remaining user-facing SunnyPilot cruise concepts that conflict with Carrot behavior: ICBM, SCC-V, SCC-M, map-speed assumptions, and opaque speed-control presets.
- [ ] Replace remaining Sunny speed-control internals with Carrot-style staged controls: independent switches for active speed, curve/turn slowdown, traffic-light stop, ATC, and button management.
- [x] Audit old params so `IntelligentCruiseButtonManagement`, `SmartCruiseControlVision`, `SmartCruiseControlMap`, and `DynamicExperimentalControl` cannot affect control output after boot.
- [ ] Validate speed source switching before relying on active speed assist.

## Onroad Visualization

- [x] Document the multi-visualization requirement: Sunny HUD remains available, Carrot lane/lead visualization is preferred for lane-change and lane display, and Fishop/lidar data needs a future display overlay.
- [x] Define the visualization layer model: one mutually exclusive base preset, editable lane/lead details, and independent Fishop/lidar evidence overlay.
- [x] Add `GeniusVisualMode` presets: Sunny, Carrot, and Fusion.
- [x] Make Fusion the default C3 preset: Sunny HUD structure with Carrot-style lane/path/lead cues.
- [x] Add `GeniusLaneLineStyle`: Simple, Colored, and Carrot.
- [x] Add `GeniusLeadRadarVisualMode`: Sunny chevron, Carrot lead box, and radar speed labels.
- [x] Add `GeniusLaneChangeVisuals` and render lane-change intent cues from the existing `onroadEvents` stream.
- [x] Add `GeniusFishopVisualOverlay` as a display-only Fishop/lidar visual entry with default off.
- [x] Move visualization controls into the Visuals settings page instead of mixing them with cruise or Super Advanced control settings.
- [x] Wire C3/TICI `selfdrive/ui/onroad/model_renderer.py` to draw Sunny-compatible simple lanes, colored lane confidence, Carrot-style adjacent-lane emphasis, Carrot lead boxes, and optional radar speed tags.
- [x] Keep visualization changes display-only: no planner, CAN, lane-change, or Fishop control output is added by these renderer switches.
- [x] Add Carrot path drawing modes as a separate renderer stage: Sunny original path, Carrot route ribbon/track markers, and Fusion Sunny body with Carrot path cues.
- [x] Add a real Fishop overlay panel for lane curve, lidar left/right lane, lidar blindspot, navigation gate, and overtake suggestion evidence.
- [x] Decide visualization coexistence rules: Sunny minimal, Carrot dense, Fusion balanced, and Fishop overlay independent on top only when local data is fresh.
- [x] Document that Fishop/lidar visual data is evidence-only and cannot enable auto-overtake or lane-change output by itself.
- [x] Add `GeniusCarrotWorldOverlay` as an independent Carrot-style world evidence layer for side-lane, blindspot, lane-change, lead, and radar cues.
- [x] Keep the Carrot world overlay display-only and default off, separate from the mutually exclusive Sunny/Carrot/Fusion base presets and from the Fishop hardware overlay.
- [x] Define the render stack explicitly: base road renderer, Carrot World overlay, Fishop overlay, then HUD/alerts.
- [x] Confirm Carrot World and Fishop overlays can be enabled together on top of any Sunny/Carrot/Fusion base preset while the base preset remains mutually exclusive.
- [x] Add a local screenshot/replay check that verifies each visualization mode renders nonblank lanes, path, lead markers, and lane-change cues without covering the speed HUD.
- [x] Add Simplified/Traditional Chinese translations for the new visualization controls.
- [ ] Map the remaining ajouatom Carrot cluster/world view into a separate optional surface: detected vehicles, source-colored objects, raw/merged side radar points, ajouatom-only lane-line type fields, and distance/speed labels.
- [ ] Add an ajouatom cluster/world schema map that names every imported field, its fallback when missing, and whether it comes from model, radar, side radar, or Fishop.
- [ ] After cluster/world view mapping, decide whether it should be a standalone page, an explicit overlay, or a debug-only visual mode; do not merge it into the main HUD by default.
- [ ] Add a cluster/world-view replay fixture before enabling that larger renderer on the C3.

## Carrot, Auto-Tuner, And Fishop Hardware

- [x] Bring over local Carrot Web, CarrotMan-style status, navigation event input, APN/N style phone speed input, SDI/speed-bump/model-speed evidence, and Auto-Tuner core.
- [x] Keep Auto-Tuner auto-apply off by default.
- [x] Keep high-risk controls default off but user-toggleable while offroad: traffic-light stop, auto-turn speed control, active speed control, Auto-Tuner auto-apply, and Fishop auto-overtake.
- [x] Add Fishop lane curve, lane quality, lidar blindspot, target, dynamic risk, navigation gate, and overtake status.
- [x] Expand the Carrot settings panel into categories: speed/maps/navigation, cruise/longitudinal, Auto-Tuner, steering/path, Fishop hardware, and local Web/diagnostics.
- [x] Rename the Carrot sidebar entry to `Super Advanced` while keeping the page as the Carrot/Genius advanced feature hub.
- [x] Embed common staged Carrot longitudinal controls into the Cruise page: speed-limit entry, Sunny DEC, stop distance, dynamic following, decel follow boost, and follow-gap presets.
- [x] Add Super Advanced controls for active speed, ATC/auto-turn, traffic-light stop, traffic-light detect mode, stop-distance adjustment, Carrot rain/wet mode, curve-speed strategy, curve tuning, driving mode, Eco, ATC decel, cruise decel, following, longitudinal gains, lane-line speed, and lane-line curve speed.
- [x] Make the local Carrot Web/API match Super Advanced: advanced params are writable while offroad; `OffroadMode`, `SpeedFromPCM`, cloud params, and hardware-only params remain protected.
- [x] Rebuild ARM64 `common/params_pyx.so` on the C3 so the new Carrot/ATC/curve/NNLC params are recognized at runtime.
- [ ] Map CarrotPilot settings from ajouatom, mechanical/Auto-Tuner, and ESCC forks into personal alpha params with Chinese/English descriptions and defaults.
- [ ] Add a Carrot cruise-control section covering button behavior, curve slowdown, traffic-light logic, speed-limit behavior, and model-speed behavior.
- [x] Add a Fishop hardware section for lane curve, lidar lane data, lidar blindspot, navigation gate, and auto-overtake, including how each input relates to the existing lane-change chain.
- [x] Migrate mechanical/masang-feiyang lane-line curve display, lidar left/right lane data, lidar blindspot data, navigation gate, and automatic-overtake switches as display-first features.
- [ ] Preserve the user's current working masang-feiyang tuning values as a known-good baseline before replacing any longitudinal or braking behavior.
- [ ] Compare ajouatom CarrotPilot, jixiexiaoge mechanical/Auto-Tuner, and ESCC fork settings one-by-one, then create the missing Genius Pilot controls instead of hiding behavior behind SunnyPilot defaults.

## Three-Branch Settings Relationship Plan

- [x] Add `scripts/personal/sunnypilot_c3_settings_conflict_audit.py` to catch cross-branch conflicts before updates.
- [x] Document the first conflict policy in `docs/personal/SETTINGS_CONFLICTS.md`.
- [x] Remove the old UI behavior that forced Carrot active speed, ATC, red-light stop, and Fishop auto-overtake back to off.
- [x] Keep Sunny ICBM/SCC-V/SCC-M hidden because they overlap with Carrot cruise/speed behavior.
- [x] Keep Sunny DEC as a separate option; it no longer disables Carrot active speed, ATC, or red-light stop.
- [x] Build a per-setting matrix for ajouatom CarrotPilot, jixiexiaoge/mechanical, and masang-feiyang/ESCC: param name, default, UI label, units, inverse semantics, source branch, code consumer, and conflict notes.
- [x] Classify every setting as one of: Carrot owner, Sunny primitive, Fishop hardware input, ESCC vehicle interface, model manager, local network/update, visualization, or removed cloud feature.
- [x] For each duplicated setting, choose exactly one owner and write the alias/removal decision; do not keep compatibility aliases unless a real on-device migration needs them.
- [x] Audit interactions among `DynamicExperimentalControl`, `SpeedLimitMode`, `CurveSpeedControlMode`, `TurnSpeedControlMode`, `CarrotActiveSpeedControlEnabled`, `CarrotAutoTurnControlEnabled`, `CarrotTrafficStopEnabled`, and `FishopAutoOvertakeEnabled`.
- [x] Add the settings owner matrix to the alpha release gate so future `/x` builds cannot silently reintroduce cloud, Sunny cruise, Carrot, Fishop, model, ESCC, local-network, or visualization conflicts.
- [x] Compare Sunny curve slowdown and Carrot curve slowdown in code and document when Fusion should use Sunny curvature, Carrot navigation turns, APN/N speed input, and lane-line curve input.
- [ ] Find the source documentation for Carrot/CarrotPad settings and annotate confusing items, especially values where smaller/larger has inverse behavior.

## Current Code And Local Test Phase

- [x] Run local static verification after unlocking Carrot advanced settings: `python3 scripts/personal/sunnypilot_c3_alpha_static_check.py`.
- [x] Compile-check changed Python files: Super Advanced UI, Cruise UI, and local Carrot Web.
- [x] Verify `common/params_pyx.so` contains the new runtime params: `CurveSpeedControlMode`, `CarrotCruiseAtcDecel`, `NeuralNetworkLateralControl`, and `FishopLaneCurveEnabled`.
- [x] Add and run the local Genius visualization contract check for path/lane/lead/Fishop display-only wiring.
- [x] Add and run the local Genius settings matrix check for Carrot/Sunny/Fishop/ESCC/model/local-network/cloud/visualization ownership.
- [x] Run the full local release gate after documentation is updated: `python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --full`.
- [x] Push both `experimental/sunnypilot-011-c3` and `alpha-sunnypilot-c3`, then audit `/x`.
- [ ] Sync or reinstall on the user's C3 and confirm Super Advanced opens, NNLC defaults on, Seltos 2023 appears, and new Carrot params do not show unknown-key waits.
- [ ] Run C3 parked checks with the device currently available: UI opens, Wi-Fi/network page reports connected state, local Web/API responds, no cloud processes exist, model manager opens, stock model runner starts.
- [x] Run local Carrot Web/API checks: write and read `CarrotActiveSpeedControlEnabled`, `CarrotAutoTurnControlEnabled`, `CarrotTrafficStopEnabled`, `FishopAutoOvertakeEnabled`, `CurveSpeedControlMode`, and `NeuralNetworkLateralControl` while offroad.
- [x] Run Navipilot/APN/N input replay locally and confirm phone speed, SDI, speed-bump, traffic-light, turn, and model-speed fields are parsed.
- [x] Run Fishop sample replay locally and confirm lane curve, left/right lane, lidar blindspot, dynamic risk, navigation gate, and overtake fields render in Web/API.
- [ ] Road testing is not required for this code/local phase; keep `/i` as rollback until later parked and real-car checks are intentionally performed.

## Localization And Docs

- [x] Remove obvious Korean-only direct text from the personal alpha surface.
- [x] Add Chinese/English descriptions for the confusing personal controls.
- [x] Document installer split, rollback path, and alpha evidence checks.
- [x] Document Genius Pilot version format in `docs/personal/VERSIONING.md`.
- [x] Add a Simplified Chinese translation overlay for the high-use alpha pages: Device, Network, Cruise, Speed Limit, Models, Carrot, Visuals, and Developer.
- [x] Replace the pixelated Chinese fallback with Noto Sans CJK SC for Simplified/Traditional Chinese and Japanese UI text; keep unifont as the broad symbol/script fallback.
- [ ] Replace remaining SunnyPilot wording with Genius Pilot / CarrotPilot wording where it is user-facing and accurate.
- [ ] Keep docs current after every real-device hotfix: installer behavior, UI failures, parameter defaults, and known rollbacks.
- [ ] Continue polishing Chinese descriptions after real-device feedback.
- [x] Add a user-facing README section for alpha use: `/i` stable rollback, `/x` alpha, Wi-Fi/SSH recovery, model manager, Carrot controls, Fishop hardware, and no-cloud policy.
- [x] Add a clear setting guide for high-risk toggles: what it changes, default state, when to test, and how to roll back.
- [x] Add a release note template that records installed branch, commit, installer hash, device evidence, cloud-process evidence, and road-test phase.

## Current C3 UI Hotfixes

- [x] Fix C3/TICI tap release handling so settings buttons and toggles receive release events.
- [x] Fix Network page on clone C3: it could show endless "Scanning Wi-Fi networks..." while the system was already connected.
- [x] Make the sidebar gear entry stable by preventing the opening touch from immediately hitting the settings close button.
- [x] Display numeric device temperature in the left sidebar instead of only `GOOD`/`HIGH` when `deviceState.maxTempC` is available.
- [x] Hide and hard-disable SunnyPilot cruise black-box toggles from the alpha Cruise panel.
- [x] Make the sidebar gear less sensitive: settings now opens on touch release and ignores close/sidebar touches during the first 0.6 seconds after entry.
- [x] Make settings/menu taps less sensitive on clone C3: reject drag/scroll releases, shrink tap movement tolerance, and defer sidebar panel switching until release.
- [x] Add `Kia Seltos 2023` to the Sunny manual vehicle selector list so the existing `KIA_SELTOS_2023` profile is visible in the UI.
- [x] Sync the hotfix files to the user's C3 at `192.168.100.174` and restart UI for bench testing.
- [x] Verify the Wi-Fi fallback on device: after UI-style activation it reports SSID `zhao`, IP `192.168.100.174`, and scanned networks without `jeepney`.
- [x] Move the device from temporary synced dirty files to pushed branch commit `ec7e73dc`.
- [ ] User visual confirmation: Network page leaves scanning state, sidebar gear opens settings consistently, temperature displays as a number, and toggles still work.
- [x] Remove the packed updater `jeepney` traceback from clean alpha installs by patching the updater payload before publishing.

## Update Checklist

- [x] Add `AGENTS.md` with the future-agent update strategy, safety boundaries, branch rules, and C3/Seltos context.
- [x] Add `scripts/personal/sunnypilot_c3_alpha_release_gate.py` as a repeatable fast/full update gate.
- [x] Add `scripts/personal/sunnypilot_c3_alpha_update_audit.py` to fetch/compare SunnyPilot, CarrotPilot, mechanical/Auto-Tuner, and ESCC reference branches.
- [x] Fetch initial `refs/remotes/carrot-audit/*` reference baseline on 2026-06-19.
- [x] Run update audit with `--fetch --strict --scan-risk-tokens` before the next upstream merge.
- [x] Review SunnyPilot staging watched-path deltas.
- [x] Review CarrotPilot watched-path deltas for Carrot, speed, model, and map changes.
- [x] Review mechanical/Auto-Tuner watched-path deltas for Auto-Tuner, APN/N, fishop hardware, and local web changes.
- [x] Re-run static checks, compatibility audit, installer audit, and evidence checker self-tests.
- [x] Add `scripts/personal/sunnypilot_c3_settings_conflict_audit.py` to detect cross-branch setting conflicts such as Sunnylink/OnroadUploads defaults, EnableConnect, DEC, SCC-V/SCC-M, Carrot active controls, and Fishop overtake gates.
- [x] Add `docs/personal/SETTINGS_CONFLICTS.md` with the current retain/hide/lock policy for cross-branch settings.
- [x] Publish alpha only after `/x` installer audit passes.
- [ ] Keep `/i` stable until C3 parking and road evidence are clean.

Last completed alpha update audit: 2026-06-19, `ok=True`, `watchPathCount=26`, `riskTokenCount=14`. Reference branches were refreshed; risk-token hits remain review evidence only and were not imported as cloud/power behavior.
