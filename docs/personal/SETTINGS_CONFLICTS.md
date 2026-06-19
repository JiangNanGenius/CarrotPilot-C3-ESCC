# Genius Pilot C3 Settings Conflict Notes

Last checked: 2026-06-20 with `scripts/personal/sunnypilot_c3_settings_conflict_audit.py --strict`, `scripts/personal/genius_settings_matrix.py --check`, and `scripts/personal/genius_curve_speed_contract.py --self-test`.

## Summary

The reference branches use several settings that look similar but control different systems. Do not merge them by name alone.

## Cloud And Upload

- SunnyPilot `staging` and `release-tizi` default `SunnylinkEnabled=1` and `OnroadUploads=1`.
- jixiexiaoge `release-new` defaults `OnroadUploads=1`.
- ajouatom and jixiexiaoge older Carrot branches expose `EnableConnect`.
- Genius Pilot personal alpha keeps cloud services inert: Sunnylink, comma connect, pairing, uploader, onroad uploads, and backup managers are not user features.
- `EnableConnect` must not be added as a user-facing cloud-connect toggle.

## Offroad And Power

- `OffroadMode` is the only supported parked-maintenance mode.
- Do not add `AlwaysOffline`, `AlwaysOffroad`, or other aliases.
- This setting is for parked updates/debugging and panda no-output behavior, not for disabling local LAN, SSH, or Carrot Web.

## DEC, ICBM, SCC-V, SCC-M

- Sunny DEC (`DynamicExperimentalControl`) is a candidate to retain.
- DEC defaults off and switches longitudinal behavior between classic and experimental/E2E paths. It does not directly replace Carrot map/curve speed logic.
- ICBM overlaps with cruise-button management and should stay hidden/inert in this personal alpha.
- SCC-V and SCC-M overlap with Carrot curve, map, navigation, and speed-limit behavior and should stay hidden/inert.
- DEC is a separate Sunny longitudinal option. It must not lock or hide Carrot active speed control, ATC/auto-turn, or traffic-light stop settings.
- `CurveSpeedControlMode` owns Sunny SCC-V participation. Sunny and Fusion modes may use SCC-V model-curvature slowdown; Off and Carrot modes do not.
- Sunny SCC-M remains inert in all Genius Pilot modes because map target velocities are not trusted as default speed truth.

## Carrot Active Controls

- `CarrotActiveSpeedControlEnabled`, `CarrotAutoTurnControlEnabled`, and `CarrotTrafficStopEnabled` default off and remain user-toggleable while offroad.
- Their owner is the Carrot/Genius path, not Sunny ICBM/SCC-V/SCC-M.
- Related settings that must be tracked together: `SpeedLimitMode`, `CurveSpeedControlMode`, `TurnSpeedControlMode`, `TrafficLightDetectMode`, `TrafficStopDistanceAdjust`, `CarrotCruiseDecel`, and `CarrotCruiseAtcDecel`.

## Auto-Tuner

- `CarrotLearningActive` is allowed as a local data collector.
- `CarrotLearningAutoApply` defaults off.
- Manual apply is parked/offroad only and should preserve the user's known-good baseline until recommendations are reviewed.

## Fishop Hardware

- Lane curve, lidar lane data, lidar blindspot inputs, navigation gate, and auto-overtake are visible Super Advanced settings.
- `FishopAutoOvertakeEnabled` defaults off and remains user-toggleable while offroad.
- Fishop behavior must be related back to the existing lane-change chain instead of introducing a separate hidden steering path.

## Onroad Visualization

- Visualization settings are display-only and live in the Visuals page.
- `GeniusVisualMode` is a preset selector: Sunny keeps the stock look, Carrot emphasizes lane/path/lead/radar information, and Fusion combines Sunny HUD elements with Carrot-style road visualization.
- `GeniusVisualMode` also owns the path display style: Sunny keeps the original route body, Carrot uses a denser route ribbon with edge/center markers, and Fusion keeps the Sunny route body with lighter Carrot path cues.
- `GeniusLaneLineStyle` and `GeniusLeadRadarVisualMode` may be adjusted independently after choosing a preset.
- `GeniusLaneChangeVisuals` uses existing `onroadEvents` lane-change intent events and must not alter lane-change decisions.
- `GeniusFishopVisualOverlay` is independent from the Sunny/Carrot/Fusion preset. It draws local Fishop/lidar evidence only while `/data/fishop_hardware.jsonl` is fresh and must not publish planner, CAN, or automatic-overtake outputs.
- Coexistence rule: Sunny, Carrot, and Fusion are mutually exclusive base presets; lane-line and lead/radar style are editable details; Fishop overlay is an optional top-layer evidence display.
- Do not merge Carrot path animation, Fishop overlay, Sunny HUD, and cruise-control behavior by name alone; each renderer change needs a display-only owner and a separate control-owner decision.
- `docs/personal/SETTINGS_MATRIX.md` is the source of truth for these owner decisions. If a new visual/control setting is added, it must be classified there before publishing `/x`.

## Current Policy

- Retain: DEC as off-by-default advanced option, local Web, local Wi-Fi, SSH, GitHub update, model downloads, APN/N/Navipilot phone speed input, Auto-Tuner, Fishop inputs, Carrot active speed, ATC, red-light stop, Fishop auto-overtake settings, and Genius visualization modes.
- Hide or inert: Sunnylink/comma cloud, OnroadUploads, EnableConnect, ICBM, SCC-V, SCC-M, Fishop auto-overtake output.
- Default off but user-toggleable while offroad: Carrot active speed, ATC/auto-turn slowdown, traffic-light stop, Auto-Tuner auto-apply, Fishop auto-overtake.
- Future audit: produce a one-owner matrix for ajouatom CarrotPilot, jixiexiaoge/mechanical, and masang-feiyang/ESCC settings before importing more behavior.
