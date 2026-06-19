# Genius Pilot Carrot Settings Guide

Last checked: 2026-06-20 with `scripts/personal/genius_carrot_settings_guide_contract.py --self-test`.

This guide records the Carrot-derived settings that are easy to misread on the
C3 screen. It is a user-facing tuning map, not a claim that every control path
has been road-proven on the user's Seltos.

## Curve And Navigation Speed

| Key | Default | Units | Direction |
| --- | ---: | --- | --- |
| `CurveSpeedControlMode` | 1 | mode | Off / Sunny / Carrot / Balanced. Balanced is the user-facing label for the internal fusion mode. |
| `AutoCurveSpeedLowerLimit` | 30 | km/h | Lowest target speed allowed during automatic curve slowdown. |
| `AutoCurveSpeedFactor` | 120 | percent | Higher values make curve detection more sensitive, usually lower the curve target speed, and slow earlier. If the lower-limit speed is already reached, raising this may have no further effect. |
| `AutoCurveSpeedAggressiveness` | 100 | percent | Secondary compatibility knob. The current active path primarily uses `AutoCurveSpeedFactor`; keep near 100 unless Auto-Tuner or later controller evidence says otherwise. |
| `AutoNaviSpeedDecelRate` | 120 | percent | Lower values start slowing from farther away for navigation speed events; higher values delay the slowdown and can feel later or stronger. |
| `CarrotActiveSpeedControlEnabled` | 0 | bool | Main gate for Carrot speed-limit, navigation, model-speed, and local evidence to change cruise targets. |
| `CarrotAutoTurnControlEnabled` | 0 | bool | Main gate for Carrot turn and junction slowdown. |
| `UseLaneLineCurveSpeed` | 0 | bool-int | Allows lane-line curve evidence to participate where the Carrot path uses it. |

中文速记：

- `AutoCurveSpeedFactor` 数值越高，通常越早、更明显地弯道减速；如果已经压到最低弯道速度，继续调高可能没有效果。
- `AutoNaviSpeedDecelRate` 数值越低，越早开始为导航事件减速；数值越高，减速会更靠后。
- Balanced/平衡不是第三套控制标准，只是把 Sunny 的模型弯道能力和 Carrot 的导航/手机/车道输入放在同一个显式模式里。

## Acceleration Table

`CruiseMaxVals0` through `CruiseMaxVals6` are speed-band cruise acceleration
limits. The reference Carrot UI labels them as 0, 10, 40, 60, 80, 110, and
140 km/h bands. Units are `0.01 m/s^2`; higher values allow stronger requested
acceleration in that band.

| Key | Band | Default | Meaning |
| --- | ---: | ---: | --- |
| `CruiseMaxVals0` | 0 km/h | 160 | Low-speed acceleration limit. |
| `CruiseMaxVals1` | 10 km/h | 200 | 10 km/h band acceleration limit. |
| `CruiseMaxVals2` | 40 km/h | 160 | 40 km/h band acceleration limit. |
| `CruiseMaxVals3` | 60 km/h | 130 | 60 km/h band acceleration limit. |
| `CruiseMaxVals4` | 80 km/h | 110 | 80 km/h band acceleration limit. |
| `CruiseMaxVals5` | 110 km/h | 95 | 110 km/h band acceleration limit. |
| `CruiseMaxVals6` | 140 km/h | 80 | 140 km/h band acceleration limit. |

中文速记：这些值不是目标速度，是不同车速段的巡航加速度上限。数值越高，那个速度段的加速请求越强。

## Following And Lead Response

| Key | Default | Units | Direction |
| --- | ---: | --- | --- |
| `TFollowGap1` | 110 | 0.01 s | Gap 1 following time. |
| `TFollowGap2` | 120 | 0.01 s | Gap 2 following time. |
| `TFollowGap3` | 140 | 0.01 s | Gap 3 following time. |
| `TFollowGap4` | 160 | 0.01 s | Gap 4 following time. |
| `DynamicTFollow` | 0 | percent | Speed/lead-dependent following adjustment. |
| `TFollowSpeedFactor` | 0 | signed percent | Speed-dependent gap adjustment. |
| `TFollowDecelBoost` | 10 | percent | Extra buffer when the ego car is already decelerating. |
| `RadarReactionFactor` | 100 | percent | Higher values react more strongly to lead changes. |
| `JLeadFactor3` | 0 | scalar | Lead-jerk response tuning. |

## Longitudinal Tuning

| Key | Default | Units | Direction |
| --- | ---: | --- | --- |
| `LongTuningKpV` | 100 | percent | Higher reacts harder to speed error; lower can reduce overshoot or oscillation. |
| `LongTuningKiV` | 0 | percent | Integral gain scaling. Change slowly. |
| `LongTuningKf` | 100 | percent | Feed-forward scaling. |
| `LongActuatorDelay` | 20 | 0.01 s | Higher anticipates slower actuator response; too high may feel early. |
| `VEgoStopping` | 50 | 0.01 m/s | Higher can smooth harsh stops; too high can enter stopping behavior early. |
| `StopDistanceCarrot` | 550 | cm | Larger target stop distance. |
| `TrafficStopDistanceAdjust` | -150 | cm | Negative values stop earlier/farther before the line; positive values stop later/closer. |

中文速记：

- `LongTuningKpV` 调高会更强地追速度误差，调低可减少超调或来回震荡。
- `LongActuatorDelay` 单位是 0.01 秒，不是百分比。
- `VEgoStopping` 单位是 0.01 m/s，数值过高可能让停车逻辑过早进入。
- `TrafficStopDistanceAdjust` 负值是更早、更远停车；正值是更晚、更近停车。

## Steering And Path

| Key | Default | Units | Direction |
| --- | ---: | --- | --- |
| `PathOffset` | 0 | cm | 0 is neutral; negative shifts left, positive shifts right. |
| `SteerActuatorDelay` | 0 | 0.01 s | 0 uses live/default delay; higher adds custom delay compensation. |
| `SteerRatioRate` | 100 | percent | 100 is neutral. |
| `UseLaneLineSpeed` | 0 | bool-int | Allows lane-line speed behavior where supported. |
| `UseLaneLineCurveSpeed` | 0 | bool-int | Allows lane-line curve-speed evidence where supported. |

中文速记：`PathOffset` 负值向左，正值向右；`SteerActuatorDelay=0` 表示使用实时/默认延迟。

## Auto-Tuner

| Key | Default | Direction |
| --- | ---: | --- |
| `CarrotLearningActive` | 0 | Collects local evidence only when enabled. |
| `CarrotLearningAutoApply` | 0 | Default off. Manual review/apply is preferred. |
| `CarrotTunerApplyLat` | 1 | Allows lateral recommendations to be applied manually. |
| `CarrotTunerApplyLong` | 1 | Allows longitudinal recommendations to be applied manually. |

Auto-Tuner recommendations should preserve known-good values unless the evidence
is clear. Auto apply remains off by default.

## Fishop Hardware Evidence

| Key | Default | Role |
| --- | ---: | --- |
| `FishopLaneCurveEnabled` | 0 | Fishop lane-curve evidence. |
| `FishopLidarLaneDataEnabled` | 0 | Lidar left/right lane evidence. |
| `FishopLidarBlindspotEnabled` | 0 | Lidar blindspot evidence. |
| `FishopAutoOvertakeEnabled` | 0 | User-toggleable setting, but current output remains display/read-only until the safety chain is validated. |

The Fishop display overlay and Carrot World overlay are evidence layers. They do
not by themselves publish planner, CAN, steering, or automatic-overtake output.
