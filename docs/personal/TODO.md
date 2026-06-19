# CarrotPilot-C3-ESCC Alpha TODO

This file tracks the personal C3 alpha line. Stable daily use stays on `/i`; the SunnyPilot 0.11 alpha line is installed from `/x`.

## Installers

- [x] Keep `/i` as the stable `personal/c3-escc-atune` installer.
- [x] Publish `/x` as the alpha `alpha-sunnypilot-c3` installer.
- [x] Add Genius Pilot versioning that follows the SunnyPilot base and appends the published date plus same-day patch number.
- [x] Rename the user-facing Fusion preset to Balanced while keeping the internal mode value stable.
- [x] Replace the incompatible Raylib `/x` binary with a C3 Qt-compatible ARM64 installer.
- [x] Verify the published `/x` binary contains the CarrotPilot-C3-ESCC repo and `alpha-sunnypilot-c3` branch.
- [x] Add `scripts/personal/build_c3_qt_compat_installer.py` so the Qt-compatible `/x` can be rebuilt reproducibly.
- [x] Add `scripts/personal/sunnypilot_c3_installer_audit.py` so future updates reject incompatible Raylib/new-GLIBC and stale upstream installer binaries.
- [x] Add `scripts/personal/sunnypilot_c3_device_collect.py` to collect installer crash logs or parked/model/no-cloud evidence from the C3 over SSH.
- [x] Add `scripts/personal/sunnypilot_c3_parked_hardware_probe.py` for parked camera/modeld/IMU validation, with cleanup after the probe and speaker checks opt-in only.
- [x] Recover from the first `/x` boot failures: missing Python dependency, settings tap release handling, and onboarding/settings navigation blockers.
- [x] Rebuild or patch the packed TICI updater so its embedded Wi-Fi manager includes the same `jeepney`/`nmcli` fallback as the main source tree.
- [x] Add an installer/update audit that checks both the main source tree and the packed TICI updater for the Wi-Fi dependency contract.
- [x] Keep the welcome/training flow, but replace SunnyPilot-specific legal/consent copy with Genius Pilot personal-build copy that is short enough for C3 and advances reliably.
- [x] Rename user-facing alpha branding from SunnyPilot to Genius Pilot where accurate: welcome screen, version/about panel, settings headers, update prompts, boot/update text, and alpha evidence snapshots.
- [x] Add a parent-level touch fallback to the TICI dependency/update prompt so `Connect to Wi-Fi`, `Install`, and failure `Reboot` can fire even when clone C3 loses the child button release event.
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
- [x] Decide the permanent C3 rescue access policy: no GitHub/cloud registration required, no public hardcoded password in release builds, and a bench-only recovery method for the user's device.
- [x] Verify local LAN services after the C3 hotfix: SSH works, local Carrot Web/API health responds, Navipilot 7000/7705/7712/7713 checks pass, and no cloud services are exposed.
- [ ] Run real device parking test on clone C3.
- [ ] Pull a C3 evidence bundle with `sunnypilot_c3_device_collect.py` after `/x` install succeeds.
- [ ] Run `sunnypilot_c3_device_collect.py --parked-hardware-probe` on the connected clone C3 and archive camera/modeld/IMU evidence; keep the probe silent unless the user explicitly asks for `--with-sound-probe`.

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
- [x] Confirm parked model startup can work without a physical panda: the C3 produced `modelV2`, `drivingModelData`, and `cameraOdometry` from `modeld_tinygrad` while parked.

## Speed Limit And Maps

- [x] Add phone/APN/N/Navipilot speed source with freshness timeout.
- [x] Default speed source order: fresh phone/APN/N/Navipilot/Carrot data, then car/instrument; Sunny OSM/mapd is opt-in through explicit map policies.
- [x] Migrate early alpha `SpeedLimitPolicy=3` Map First devices back to Phone First so old installs do not keep Sunny map/GPS as the default speed truth.
- [x] Make the Speed Limit panel show Phone First priority and explain that map/GPS policies are separate opt-in choices.
- [x] Keep route and map display from becoming speed-limit truth by default.
- [x] Default speed offset to zero.
- [x] Add fixed and percentage speed offset modes.
- [x] Default `CarrotMapOverlayEnabled` to off so Mapbox/Kakao overlay does not cover the HUD.
- [x] Hide and hard-disable SunnyPilot ICBM, SCC-V, and SCC-M in the personal alpha; cruise-speed behavior should move toward CarrotPilot logic instead of SunnyPilot black-box toggles.
- [x] Retain Sunny DEC as an off-by-default advanced longitudinal option, exposed in Cruise and Super Advanced without locking Carrot controls.
- [x] Add `CurveSpeedControlMode` with Off / Sunny / Carrot / Balanced so Sunny curve quality and Carrot navigation/phone inputs can be compared and then combined.
- [x] Add Carrot curve-speed tuning params: lower speed limit, curve factor, curve aggressiveness, navigation decel rate, and wet-road mode.
- [x] Remove or relabel any remaining user-facing SunnyPilot cruise concepts that conflict with Carrot behavior: ICBM, SCC-V, SCC-M, map-speed assumptions, and opaque speed-control presets.
- [x] Replace remaining Sunny speed-control internals with Carrot-style staged controls: independent switches for active speed, curve/turn slowdown, traffic-light stop, ATC, and button management.
- [x] Audit old params so `IntelligentCruiseButtonManagement`, `SmartCruiseControlVision`, and `SmartCruiseControlMap` stay hidden/inert; `DynamicExperimentalControl` remains a separate off-by-default DEC candidate only when longitudinal support is actually available.
- [x] Make non-curve speed control Carrot/Genius-owned by default: APN/N/Navipilot/Carrot phone data first, vehicle/cluster speed second, with Sunny map/GPS speed control opt-in only through explicit map policies.
- [x] Document the stricter cruise ownership rule: except for explicit curve-speed experiments, active speed control should stay Carrot/Genius-owned and should not fall back to Sunny map/GPS behavior.
- [ ] Validate speed source switching before relying on active speed assist.

## Onroad Visualization

- [x] Document the multi-visualization requirement: Sunny HUD remains available, Carrot lane/lead visualization is preferred for lane-change and lane display, and Fishop/lidar data needs a future display overlay.
- [x] Define the visualization layer model: one mutually exclusive base preset, editable lane/lead details, and independent Fishop/lidar evidence overlay.
- [x] Add `GeniusVisualMode` presets: Sunny, Carrot, and Balanced.
- [x] Make Balanced the default C3 preset: Sunny HUD structure with Carrot-style lane/path/lead cues.
- [x] Add `GeniusLaneLineStyle`: Simple, Colored, and Carrot.
- [x] Add `GeniusLeadRadarVisualMode`: Sunny chevron, Carrot lead box, and radar speed labels.
- [x] Add `GeniusLaneChangeVisuals` and render lane-change intent cues from the existing `onroadEvents` stream.
- [x] Add `GeniusFishopVisualOverlay` as a display-only Fishop/lidar visual entry with default off.
- [x] Move visualization controls into the Visuals settings page instead of mixing them with cruise or Super Advanced control settings.
- [x] Wire C3/TICI `selfdrive/ui/onroad/model_renderer.py` to draw Sunny-compatible simple lanes, colored lane confidence, Carrot-style adjacent-lane emphasis, Carrot lead boxes, and optional radar speed tags.
- [x] Keep visualization changes display-only: no planner, CAN, lane-change, or Fishop control output is added by these renderer switches.
- [x] Add Carrot path drawing modes as a separate renderer stage: Sunny original path, Carrot route ribbon/track markers, and Balanced Sunny body with Carrot path cues.
- [x] Add a real Fishop overlay panel for lane curve, lidar left/right lane, lidar blindspot, navigation gate, and overtake suggestion evidence.
- [x] Decide visualization coexistence rules: Sunny minimal, Carrot dense, Balanced default, and Fishop overlay independent on top only when local data is fresh.
- [x] Document that Fishop/lidar visual data is evidence-only and cannot enable auto-overtake or lane-change output by itself.
- [x] Add `GeniusCarrotWorldOverlay` as an independent Carrot-style world evidence layer for side-lane, blindspot, lane-change, lead, and radar cues.
- [x] Keep the Carrot world overlay display-only and default off, separate from the mutually exclusive Sunny/Carrot/Balanced base presets and from the Fishop hardware overlay.
- [x] Define the render stack explicitly: base road renderer, Carrot World overlay, Fishop overlay, then HUD/alerts.
- [x] Confirm Carrot World and Fishop overlays can be enabled together on top of any Sunny/Carrot/Balanced base preset while the base preset remains mutually exclusive.
- [x] Add a local screenshot/replay check that verifies each visualization mode renders nonblank lanes, path, lead markers, and lane-change cues without covering the speed HUD.
- [x] Add Simplified/Traditional Chinese translations for the new visualization controls.
- [x] Make the visualization coexistence rule user-facing: Sunny/Carrot/Balanced are mutually exclusive base displays; Carrot World and Fishop can both be opened as evidence overlays.
- [x] Group the Visuals settings page into base display, visual detail controls, evidence overlays, and normal HUD widgets so Carrot lane/merge visuals and Fishop/lidar overlays are not confused with each other.
- [x] Prefer Carrot-style lane and lane-change presentation for Balanced/Carrot modes because it is clearer than Sunny's stock lane display on adjacent-lane awareness.
- [x] Map the remaining ajouatom Carrot cluster/world view into a separate optional surface: detected vehicles, source-colored objects, raw/merged side radar points, ajouatom-only lane-line type fields, and distance/speed labels.
- [x] Add an ajouatom cluster/world schema map that names every imported field, its fallback when missing, and whether it comes from model, radar, side radar, or Fishop.
- [x] Promote the ajouatom cluster/world schema into runtime code and expose `/api/cluster_world` as a local read-only snapshot for future Carrot-style visualization surfaces.
- [x] Add `/cluster_world` as the first debug-only local Web surface for source-colored objects, raw radar points, lane/path drawing, distance labels, speed labels, and source/fallback evidence.
- [x] After cluster/world view mapping, decide whether it should be a standalone page, an explicit overlay, or a debug-only visual mode; do not merge it into the main HUD by default.
- [x] Add a cluster/world-view replay fixture before enabling that larger renderer on the C3.

## Carrot, Auto-Tuner, And Fishop Hardware

- [x] Bring over local Carrot Web, CarrotMan-style status, navigation event input, APN/N style phone speed input, SDI/speed-bump/model-speed evidence, and Auto-Tuner core.
- [x] Keep Auto-Tuner auto-apply off by default.
- [x] Keep high-risk controls default off but user-toggleable while offroad: traffic-light stop, auto-turn speed control, active speed control, Auto-Tuner auto-apply, and Fishop auto-overtake.
- [x] Add Fishop lane curve, lane quality, lidar blindspot, target, dynamic risk, navigation gate, and overtake status.
- [x] Expand the Carrot settings panel into categories: speed/maps/navigation, cruise/longitudinal, Auto-Tuner, steering/path, Fishop hardware, and local Web/diagnostics.
- [x] Rename the Carrot sidebar entry to `Super Advanced` while keeping the page as the Carrot/Genius advanced feature hub.
- [x] Embed common staged Carrot longitudinal controls into the Cruise page: speed-limit entry, Sunny DEC, stop distance, dynamic following, decel follow boost, and follow-gap presets.
- [x] Add a bilingual Carrot settings guide that documents confusing units and tuning directions for curve speed, navigation decel, cruise acceleration table, longitudinal tuning, path offset, steering delay, Auto-Tuner, and Fishop evidence.
- [x] Expand Auto-Tuner descriptions so every recommendation target explains what higher/lower values mean: acceleration, following gap, lead response, stop distance, path offset, steering delay, and steer ratio.
- [x] Add a release-gated contract so corrected Carrot setting descriptions and the Balanced label cannot silently regress.
- [x] Remove the remaining hidden Sunny ICBM runtime from `selfdrived` and keep its state output inactive/none for log compatibility.
- [x] Add Super Advanced controls for active speed, ATC/auto-turn, traffic-light stop, traffic-light detect mode, stop-distance adjustment, Carrot rain/wet mode, curve-speed strategy, curve tuning, driving mode, Eco, ATC decel, cruise decel, following, longitudinal gains, lane-line speed, and lane-line curve speed.
- [x] Make the local Carrot Web/API match Super Advanced: advanced params are writable while offroad; `OffroadMode`, `SpeedFromPCM`, cloud params, and hardware-only params remain protected.
- [x] Rebuild ARM64 `common/params_pyx.so` on the C3 so the new Carrot/ATC/curve/NNLC params are recognized at runtime.
- [x] Map CarrotPilot settings from ajouatom, mechanical/Auto-Tuner, and ESCC forks into personal alpha params with Chinese/English descriptions and defaults.
- [x] Add a Carrot cruise-control section covering button behavior, curve slowdown, traffic-light logic, speed-limit behavior, and model-speed behavior.
- [x] Add a Fishop hardware section for lane curve, lidar lane data, lidar blindspot, navigation gate, and auto-overtake, including how each input relates to the existing lane-change chain.
- [x] Migrate mechanical/masang-feiyang lane-line curve display, lidar left/right lane data, lidar blindspot data, navigation gate, and automatic-overtake switches as display-first features.
- [x] Preserve the user's current working masang-feiyang tuning values as a known-good baseline before replacing any longitudinal or braking behavior.
- [x] Add `scripts/personal/carrot_tuning_baseline.py` so future updates can export the same Carrot/Fishop/model/visual baseline from C3 params.
- [x] Compare ajouatom CarrotPilot, jixiexiaoge mechanical/Auto-Tuner, and ESCC fork settings one-by-one, then create the missing Genius Pilot controls instead of hiding behavior behind SunnyPilot defaults.

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
- [x] Compare Sunny curve slowdown and Carrot curve slowdown in code and document when Balanced should use Sunny curvature, Carrot navigation turns, APN/N speed input, and lane-line curve input.
- [x] Find the source documentation for Carrot/CarrotPad settings and annotate confusing items, especially values where smaller/larger has inverse behavior.

## Current Code And Local Test Phase

- [x] Run local static verification after unlocking Carrot advanced settings: `python3 scripts/personal/sunnypilot_c3_alpha_static_check.py`.
- [x] Compile-check changed Python files: Super Advanced UI, Cruise UI, and local Carrot Web.
- [x] Verify `common/params_pyx.so` contains the new runtime params: `CurveSpeedControlMode`, `CarrotCruiseAtcDecel`, `NeuralNetworkLateralControl`, and `FishopLaneCurveEnabled`.
- [x] Add and run the local Genius visualization contract check for path/lane/lead/Fishop display-only wiring.
- [x] Add and run the local Genius settings matrix check for Carrot/Sunny/Fishop/ESCC/model/local-network/cloud/visualization ownership.
- [x] Run the full local release gate after documentation is updated: `python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --full`.
- [x] Research comma/openpilot offline testing: use `selfdrive/test/process_replay` for process output regression, `tools/replay` for UI/message replay, and reserve C3 parked probes for physical hardware evidence.
- [x] Add a Genius offline replay checklist/wrapper for Seltos/Carrot logic; readiness checks are local-only, while real process replay is opt-in when route artifacts/network budget are available.
- [x] Run deterministic TICI UI diff replay locally through `genius_ui_replay_check.py --run-ui-replay`; it passed with the Mac native-extension shadow path and produced `selfdrive/ui/tests/diff/report/genius_tizi_ui_replay.mp4` plus the `htmlcov-tizi` report.
- [x] Make `genius_offline_replay_check.py` runnable on macOS with Python 3.12 safe-path mode, caller `PYTHONPATH` shadow precedence, temporary `PARAMS_ROOT`, real upstream process-list arguments, deterministic `--jobs`, and crash/reference/native-blocked result classification.
- [x] Fix process-replay-discovered `controlsd` startup crashes: NNLC now falls back when `CarParamsSP.neuralNetworkLateralControl.model.path` is empty or missing, and legacy torque v0 clamps zero/negative `lat_delay` before lateral-jerk division.
- [x] Run HYUNDAI `controlsd` process replay smoke. It completes crash-free after the NNLC and torque v0 fixes; it still reports expected upstream reference diffs in torque outputs because this fork intentionally changes lateral-control behavior.
- [x] Run HYUNDAI `radard` process replay smoke; it passes against upstream reference data.
- [ ] Complete upstream process replay coverage for affected non-hardware logic before promoting `/x`: `plannerd` is currently blocked on macOS `acados_ocp_solver_pyx.so`, and `locationd`/`paramsd` are currently blocked on macOS rednose `ekf_sym_pyx.so`. Model replay still requires camera frame inputs.
- [x] Push both `experimental/sunnypilot-011-c3` and `alpha-sunnypilot-c3`, then audit `/x`.
- [ ] Sync or reinstall on the user's C3 and confirm Super Advanced opens, NNLC defaults on, Seltos 2023 appears, and new Carrot params do not show unknown-key waits.
- [ ] Run C3 parked checks with the device currently available: UI opens, Wi-Fi/network page reports connected state, local Web/API responds, no cloud processes exist, model manager opens, stock model runner starts.
- [x] Run local Carrot Web/API checks: write and read `CarrotActiveSpeedControlEnabled`, `CarrotAutoTurnControlEnabled`, `CarrotTrafficStopEnabled`, `FishopAutoOvertakeEnabled`, `CurveSpeedControlMode`, and `NeuralNetworkLateralControl` while offroad.
- [x] Run C3 local Carrot Web/API checks: health, params bulk, same-value param write, status broadcast, UDP status, navigation HTTP, and navigation TCP all pass with local-only/no-control evidence.
- [x] Fix C3 evidence collection to use the openpilot venv, and summarize active model bundle JSON without truncation parse errors.
- [x] Run the C3 parked hardware probe enough to confirm camera streams and modeld without real panda: three camera streams, `modelV2`, `drivingModelData`, and `cameraOdometry` were observed.
- [x] Speaker output was user-confirmed good; keep future device probes silent by default and do not trigger sound unless explicitly requested.
- [ ] Re-run IMU as a separate C3 hardware check using the upstream `system/sensord/tests/test_sensord.py` approach, because temperature alone is not enough to validate accelerometer/gyroscope.
- [x] Run Navipilot/APN/N input replay locally and confirm phone speed, SDI, speed-bump, traffic-light, turn, and model-speed fields are parsed.
- [x] Run Fishop sample replay locally and confirm lane curve, left/right lane, lidar blindspot, dynamic risk, navigation gate, and overtake fields render in Web/API.
- [ ] Road testing is not required for this code/local phase; keep `/i` as rollback until later parked and real-car checks are intentionally performed.

## No-Car Diagnostics Matrix

These checks should be run before any real road test. They are allowed while the C3 is on a desk or in recovery/offroad mode, and they must stay silent unless the user explicitly asks for an audible speaker test.

- [x] Create one repeatable Genius diagnostic command path that ties together C3 snapshot collection, parked camera/model sampling, IMU sampling, UI capture, and no-cloud evidence through `sunnypilot_c3_device_collect.py`.
- [x] Add a process-replay wrapper for non-hardware logic: `controlsd`, `plannerd`, `radard`, `locationd`, and `paramsd`; keep reference updates opt-in only.
- [x] Extend the process-replay wrapper so it distinguishes crash-free upstream reference diffs from true crashes, timeouts, and local native-extension blockers.
- [x] Add a replay/UI diagnostic path using comma's `tools/replay/replay --demo` and UI diff replay so settings, HUD, visual modes, Carrot overlays, and Chinese text can be checked without the car.
- [x] Make the no-car UI replay wrapper self-contained for clean macOS runs by preserving caller `PYTHONPATH` shim precedence, appending the repo path, and creating a temporary `PARAMS_ROOT` for the replay subprocess.
- [x] Add `scripts/personal/build_mac_replay_shadow.py` so macOS process replay can build rednose and acados native extensions without replacing checked-in C3/Linux binaries.
- [x] Run HYUNDAI `controlsd`, `plannerd`, `radard`, `locationd`, and `paramsd` process replay with `crashFree=true` and `nativeExtensionBlocked=false`; remaining `ok=false` is documented as fork reference diffs.
- [ ] Generate and review fork-owned process replay references before treating Carrot/Genius behavior diffs as pass/fail regressions.
- [x] Extend the Navipilot/CPdazi live check so `/api/phone_speed_limit` and `/api/fishop_hardware` are part of the no-car read-only evidence contract, including nested no-control-output checks.
- [x] Add a passive C3 UI/screen capture evidence path to the device tarball; it tries `screencap`, then `fbgrab`, then raw framebuffer fallback, without touching the screen or playing sound.
- [x] Add a C3 camera snapshot evidence path using upstream `system/camerad/snapshot.py` or VisionIPC capture, separate from modeld control checks.
- [x] Confirm parked camera/model path: three camera streams plus `modelV2`, `drivingModelData`, and `cameraOdometry` were observed without a physical panda.
- [x] Add a silent C3 IMU probe based on upstream `system/sensord/tests/test_sensord.py`; require accelerometer and gyroscope, not only temperature.
- [ ] Run the silent C3 IMU probe on the clone C3 and archive `c3_imu_probe.json`.
- [x] Treat speaker output as already user-confirmed good; future speaker tests are opt-in only and must never run from default diagnostics.
- [x] Verify C3 local Web/API diagnostics without car in read-only mode: health, params bulk, status broadcast, UDP 7705 status, 7712 TCP health, 7713 HTTP health, navigation-event snapshot, phone speed state, Fishop evidence state, and no control-output fields.
- [x] Archive the latest read-only LAN evidence under `~/Desktop/CarrotPilot-C3-ESCC-device-evidence/`: `navipilot_live_readonly_20260620_080046.json` and `.md`.
- [ ] Re-run writable same-value and safe navigation probes only after the C3 clearly reports parked/offroad; the 2026-06-20 read-only live check reported `IsOnroad=true`, so writes and injected packets were intentionally skipped.
- [ ] Verify model manager without car: model list/download availability, active bundle summary, runner cache, stock fallback, and no active bundle rollback behavior.
- [ ] Verify Carrot/Super Advanced settings without car: all migrated controls visible, writable while offroad where intended, protected params read-only, and no unknown-key waits on C3.
- [ ] Verify C3 UI/touch without car: settings opens reliably, Network page reports connected/scanned state, Seltos 2023 appears in the vehicle list, temperature displays numerically, and toggles retain state.
- [ ] Archive each no-car diagnostic bundle on the Mac desktop under `CarrotPilot-C3-ESCC-device-evidence` with branch, commit, version, installer hash, and cloud-process evidence.
- [x] Add release-gated self-tests for the no-car UI replay wrapper and the explicit C3 camera snapshot probe.

## Localization And Docs

- [x] Remove obvious Korean-only direct text from the personal alpha surface.
- [x] Add Chinese/English descriptions for the confusing personal controls.
- [x] Document installer split, rollback path, and alpha evidence checks.
- [x] Document Genius Pilot version format in `docs/personal/VERSIONING.md`.
- [x] Add a Simplified Chinese translation overlay for the high-use alpha pages: Device, Network, Cruise, Speed Limit, Models, Carrot, Visuals, and Developer.
- [x] Replace the pixelated Chinese fallback with Noto Sans CJK SC for Simplified/Traditional Chinese and Japanese UI text; keep unifont as the broad symbol/script fallback.
- [x] Replace remaining SunnyPilot wording with Genius Pilot / CarrotPilot wording where it is user-facing and accurate.
- [ ] Keep docs current after every real-device hotfix: installer behavior, UI failures, parameter defaults, and known rollbacks.
- [ ] Continue polishing Chinese descriptions after real-device feedback.
- [x] Add a user-facing README section for alpha use: `/i` stable rollback, `/x` alpha, Wi-Fi/SSH recovery, model manager, Carrot controls, Fishop hardware, and no-cloud policy.
- [x] Add a clear setting guide for high-risk toggles: what it changes, default state, when to test, and how to roll back.
- [x] Add a release note template that records installed branch, commit, installer hash, device evidence, cloud-process evidence, and road-test phase.

## Current C3 UI Hotfixes

- [x] Fix C3/TICI tap release handling so settings buttons and toggles receive release events.
- [x] Fix Network page on clone C3: it could show endless "Scanning Wi-Fi networks..." while the system was already connected.
- [x] Make the sidebar gear entry stable by preventing the opening touch from immediately hitting the settings close button.
- [x] Display numeric device temperature in the left sidebar from any available `deviceState` temperature source; fall back to `--C`, never `GOOD`/`HIGH`.
- [x] Add left-sidebar phone/Navipilot status from local Carrot phone/navigation inputs, with fresh/stale/off states and no cloud pairing dependency.
- [x] Add left-sidebar GPS status from `gpsLocationExternal`/`gpsLocation`, showing fix/accuracy/weak/off state.
- [x] Hide and hard-disable SunnyPilot cruise black-box toggles from the alpha Cruise panel.
- [x] Make the sidebar gear less sensitive: settings now opens on touch release and ignores close/sidebar touches during the first 0.6 seconds after entry.
- [x] Make settings/menu taps less sensitive on clone C3: reject drag/scroll releases, shrink tap movement tolerance, and defer sidebar panel switching until release.
- [x] Make setup/update/install dependency buttons more tolerant on clone C3 without loosening normal settings taps: per-widget tap-release movement is supported, and TICI/MICI setup/updater install buttons use a wider release tolerance.
- [x] Add a direct fallback on the standalone TICI dependency/update prompt so critical install buttons do not depend only on child-button release callbacks.
- [x] Add `Kia Seltos 2023` to the Sunny manual vehicle selector list so the existing `KIA_SELTOS_2023` profile is visible in the UI.
- [x] Sync the hotfix files to the user's C3 at `192.168.100.174` and restart UI for bench testing.
- [x] Verify the Wi-Fi fallback on device: after UI-style activation it reports SSID `zhao`, IP `192.168.100.174`, and scanned networks without `jeepney`.
- [x] Move the device from temporary synced dirty files to pushed branch commit `ec7e73dc`.
- [ ] User visual confirmation: setup/update install buttons advance reliably, Network page leaves scanning state, sidebar gear opens settings consistently, temperature displays as a number, and toggles still work.
- [x] Remove the packed updater `jeepney` traceback from clean alpha installs by patching the updater payload before publishing.
- [x] Add a release-gated contract so the sidebar temperature card cannot regress to translated `GOOD`/`HIGH` status text.
- [x] Add a release-gated contract so the sidebar keeps four personal-build cards: temperature, vehicle, phone/Navipilot, and GPS.

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
