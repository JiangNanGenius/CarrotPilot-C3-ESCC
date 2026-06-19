# Genius Pilot C3 Settings Conflict Notes

Last checked: 2026-06-20 with `scripts/personal/sunnypilot_c3_settings_conflict_audit.py --strict`.

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
- DEC must not be combined with unvalidated Carrot active speed control, auto-turn slowdown, or traffic-light stop outputs.

## Carrot Active Controls

- `CarrotActiveSpeedControlEnabled`, `CarrotAutoTurnControlEnabled`, and `CarrotTrafficStopEnabled` default off and remain locked in the C3 alpha UI.
- They can collect/display evidence through Carrot Web and settings, but they must not command braking or cruise targets until staged road evidence exists.

## Auto-Tuner

- `CarrotLearningActive` is allowed as a local evidence collector.
- `CarrotLearningAutoApply` defaults off.
- Manual apply is parked/offroad only and should preserve the user's known-good baseline until recommendations are reviewed.

## Fishop Hardware

- Lane curve, lidar lane data, and lidar blindspot inputs are display/evidence gates first.
- `FishopAutoOvertakeEnabled` defaults off and remains locked until hardware logs, navigation gate evidence, rollback, and road review exist.

## Current Policy

- Retain: DEC as off-by-default advanced candidate, local Web, local Wi-Fi, SSH, GitHub update, model downloads, APN/N/Navipilot phone speed input, Auto-Tuner evidence, Fishop input evidence.
- Hide or inert: Sunnylink/comma cloud, OnroadUploads, EnableConnect, ICBM, SCC-V, SCC-M, Fishop auto-overtake output.
- Lock until validated: Carrot active speed, auto-turn slowdown, traffic-light stop, Auto-Tuner auto-apply.
