# Genius Pilot High-Risk Setting Guide

This guide explains the settings that can change speed, following, braking,
route response, or lane-change-related evidence in the personal C3 alpha.

Use `/i` as the stable rollback installer and `/x` as the current alpha
installer. Test while parked first, then test one feature at a time.

## General Rules

- Keep stock model selected until boot, UI, model manager, and local Web/API are
  confirmed.
- Keep cloud/upload processes absent during every test.
- Do not change control-related settings while onroad.
- Do not combine multiple new high-risk features in the first road test.
- Keep a note of the previous value before changing braking, following, or
  acceleration parameters.

## Offroad Mode

Param: `OffroadMode`

Default: off.

Purpose: keep the device in parked/offroad state with panda no-output for
ACC/CAN-powered clone C3 maintenance. This is not the same as disabling cloud
services and it does not disable local LAN.

Use it for parked updates, SSH, local Web/API, model downloads, and debugging.

## Model Manager

Default: stock model.

Custom model download, validation, switching, and rollback must happen while
offroad. If an active bundle is invalid, the alpha should return to stock or the
previous valid bundle.

## Speed-Limit Source

Key params:

- `SpeedLimitPolicy`
- `CarrotPhoneSpeedLimitEnabled`
- `SpeedLimitMode`
- `SpeedLimitOffsetType`
- `SpeedLimitValueOffset`

Default policy: fresh phone/APN/N/Navipilot/Carrot data first, then vehicle
limit, then OSM/mapd.

Default offset: none, value `0`.

Start in information/display mode. Only move to assist after the phone, vehicle,
and map sources have been compared.

## Carrot Map Overlay

Param: `CarrotMapOverlayEnabled`

Default: off.

When off, external map SDKs and map iframes should not load and should not cover
the driving HUD. Mapbox/Kakao/Carrot route display is not the default
speed-limit truth source.

## Carrot Active Speed Control

Param: `CarrotActiveSpeedControlEnabled`

Default: off, user-toggleable while offroad.

Purpose: allow Carrot/Genius active speed logic to affect cruise targets on
supported paths.

Test only after speed-limit source switching is understood. Watch braking
comfort and whether APN/N data becomes stale.

## Auto-Turn Slowdown

Key params:

- `CarrotAutoTurnControlEnabled`
- `TurnSpeedControlMode`
- `AutoTurnControl`
- `AutoTurnControlSpeedTurn`
- `AutoTurnControlTurnEnd`
- `AutoTurnMapChange`
- `CurveSpeedControlMode`

Default high-risk output switch: off.

`CurveSpeedControlMode` lets Sunny, Carrot, and Balanced slowdown behavior be
compared. Balanced means Sunny model-curvature quality plus Carrot
navigation/phone/lane inputs; it does not mean enabling every Sunny map-speed
feature.

## Traffic-Light Stop

Key params:

- `CarrotTrafficStopEnabled`
- `TrafficLightDetectMode`
- `TrafficStopDistanceAdjust`

Default output switch: off.

The current navigation replay contract proves red/green traffic-light evidence
is parsed and exposed locally. It does not prove road-ready braking behavior.

## Auto-Tuner

Key params:

- `CarrotLearningActive`
- `CarrotLearningAutoApply`
- `CarrotLearningApply`
- `CarrotLearningIgnore`
- `CarrotLearningClear`
- `CarrotTunerApplyLat`
- `CarrotTunerApplyLong`

Default: learner off, auto-apply off.

Recommendations should be reviewed manually before applying. Auto-apply should
stay off until repeated parked and road evidence exists.

## Following And Braking Tuning

Key params:

- `StopDistanceCarrot`
- `TFollowGap1` through `TFollowGap4`
- `DynamicTFollow`
- `TFollowDecelBoost`
- `TFollowSpeedFactor`
- `CarrotCruiseDecel`
- `CarrotCruiseAtcDecel`
- `LongTuningKpV`
- `LongTuningKiV`
- `LongTuningKf`
- `LongActuatorDelay`
- `VEgoStopping`
- `RadarReactionFactor`

Change one value at a time. Keep the user's known-good masang-feiyang values as
the baseline until better evidence exists.

## Fishop Hardware And Auto Overtake

Key params:

- `FishopLaneCurveEnabled`
- `FishopLidarBlindspotEnabled`
- `FishopLidarLaneDataEnabled`
- `FishopAutoOvertakeEnabled`

Default: off, user-toggleable while offroad.

Current Fishop integration records lane curve, left/right lane data,
lidar/camera blindspot, dynamic blindspot risk, navigation gate, and overtake
request evidence. The replay contract proves this evidence reaches local Web/API
as read-only data with `controlOutput=false`.

Auto-overtake must not publish desire, planner, steering, or CAN commands until
the existing lane-change safety chain has separate evidence.

## Visualization

Key params:

- `GeniusVisualMode`
- `GeniusLaneLineStyle`
- `GeniusLeadRadarVisualMode`
- `GeniusLaneChangeVisuals`
- `GeniusCarrotWorldOverlay`
- `GeniusFishopVisualOverlay`

Sunny, Carrot, and Balanced are mutually exclusive base display presets. Carrot
World and Fishop are independent top-layer evidence overlays.

Visualization settings are display-only and must not change lane-change,
planner, steering, or CAN output.

## Sunny DEC

Param: `DynamicExperimentalControl`

Default: off.

Sunny DEC is kept as an advanced candidate and separated from Carrot active
speed, ATC/auto-turn, and traffic-light stop. ICBM, SCC-V, and SCC-M are hidden
or inert because they overlap more directly with Carrot cruise/speed behavior.

## Rollback

If behavior is confusing, uncomfortable, or not understood:

1. Turn the feature off while parked.
2. Reboot if the feature affects model/control state.
3. Return to stock model if a model change was involved.
4. Install `/i` if the alpha branch itself is suspect.
