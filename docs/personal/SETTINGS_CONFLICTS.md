# Genius Pilot C3 Settings Conflict Notes

Last checked: 2026-06-20 with `scripts/personal/sunnypilot_c3_settings_conflict_audit.py --strict`, `scripts/personal/genius_settings_matrix.py --check`, `scripts/personal/genius_curve_speed_contract.py --self-test`, and `scripts/personal/genius_visualization_contract.py --self-test`.

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
- `CurveSpeedControlMode` owns Sunny SCC-V participation. Sunny and Balanced modes may use SCC-V model-curvature slowdown; Off and Carrot modes do not.
- Sunny SCC-M remains inert in all Genius Pilot modes because map target velocities are not trusted as default speed truth.

## Carrot Active Controls

- `CarrotActiveSpeedControlEnabled`, `CarrotAutoTurnControlEnabled`, and `CarrotTrafficStopEnabled` default off and remain user-toggleable while offroad.
- Their owner is the Carrot/Genius path, not Sunny ICBM/SCC-V/SCC-M.
- These controls are staged gates, not one shared switch:
  - `SpeedLimitPolicy=Phone First` only chooses the source order: fresh APN/N/Navipilot/Carrot phone data, then vehicle/cluster speed. OSM/mapd is opt-in through Map Only, Map First, Car First, or Combined and is not the default speed truth.
  - `SpeedLimitMode=Assist` is the speed-limit-assist gate that allows resolved limits to change cruise targets; Info/Warning stay display/alert only.
  - `CarrotActiveSpeedControlEnabled` is the Carrot cruise-target gate for speed-limit, navigation, SDI, speed-bump, traffic-light, and model-speed evidence.
  - `CarrotAutoTurnControlEnabled` plus `TurnSpeedControlMode` owns ATC/turn slowdown; `CarrotCruiseAtcDecel` only affects this path.
  - `CarrotTrafficStopEnabled` plus `TrafficLightDetectMode` owns red-light stopping and should be tested independently because it can request a much lower target near intersections.
- Related settings that must be tracked together: `SpeedLimitMode`, `SpeedLimitPolicy`, `CarrotPhoneSpeedLimitEnabled`, `CurveSpeedControlMode`, `TurnSpeedControlMode`, `TrafficLightDetectMode`, `TrafficStopDistanceAdjust`, `CarrotCruiseDecel`, and `CarrotCruiseAtcDecel`.

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
- `GeniusVisualMode` is a preset selector: Sunny keeps the stock look, Carrot emphasizes lane/path/lead/radar information, and Balanced combines Sunny HUD elements with Carrot-style road visualization.
- Balanced is the C3 alpha default because it keeps the familiar Sunny HUD structure while preferring Carrot-style lane/path/lead cues where the road display is clearer. It is the user-facing label for the internal fusion renderer.
- `GeniusVisualMode` also owns the path display style: Sunny keeps the original route body, Carrot uses a denser route ribbon with edge/center markers, and Balanced keeps the Sunny route body with lighter Carrot path cues.
- `GeniusLaneLineStyle` and `GeniusLeadRadarVisualMode` may be adjusted independently after choosing a preset.
- `GeniusLaneChangeVisuals` uses existing `onroadEvents` lane-change intent events and must not alter lane-change decisions.
- `GeniusCarrotWorldOverlay` is independent from the Sunny/Carrot/Balanced preset. It draws Carrot-style side-lane, blindspot, lane-change, lead, and radar evidence on top of any base preset.
- `GeniusFishopVisualOverlay` is independent from the Sunny/Carrot/Balanced preset. It draws local Fishop/lidar evidence only while `/data/fishop_hardware.jsonl` is fresh and must not publish planner, CAN, or automatic-overtake outputs.
- Coexistence rule: Sunny, Carrot, and Balanced are mutually exclusive base presets; lane-line and lead/radar style are editable details; Carrot World and Fishop are optional top-layer evidence displays and may be enabled together.
- Render order rule: base road renderer first, Carrot World overlay second, Fishop overlay third, HUD/alerts last.
- The ajouatom Carrot cluster/world visualization is tracked as a separate future surface. Do not merge its world-view renderer into the main HUD without a separate layout/performance/control-boundary pass.
- Do not merge Carrot path animation, Fishop overlay, Sunny HUD, and cruise-control behavior by name alone; each renderer change needs a display-only owner and a separate control-owner decision.
- `docs/personal/SETTINGS_MATRIX.md` is the source of truth for these owner decisions. If a new visual/control setting is added, it must be classified there before publishing `/x`.

## Current Policy

- Retain: DEC as off-by-default advanced option, local Web, local Wi-Fi, SSH, GitHub update, model downloads, APN/N/Navipilot phone speed input, Auto-Tuner, Fishop inputs, Carrot active speed, ATC, red-light stop, Fishop auto-overtake settings, and Genius visualization modes.
- Hide or inert: Sunnylink/comma cloud, OnroadUploads, EnableConnect, ICBM, SCC-V, SCC-M, Fishop auto-overtake output.
- Default off but user-toggleable while offroad: Carrot active speed, ATC/auto-turn slowdown, traffic-light stop, Auto-Tuner auto-apply, Fishop auto-overtake.
- Future audit: produce a one-owner matrix for ajouatom CarrotPilot, jixiexiaoge/mechanical, and masang-feiyang/ESCC settings before importing more behavior.
