# Genius Pilot Curve-Speed Policy

Last checked: 2026-06-20 with `scripts/personal/genius_curve_speed_contract.py --self-test`.

## Why This Exists

SunnyPilot and CarrotPilot both contain curve/turn slowdown ideas, but they do
not own the same signals. Genius Pilot keeps the useful Sunny model-curvature
logic while making Carrot navigation, phone, and hardware inputs explicit.

## Source Comparison

Sunny SCC-V:

- Code: `sunnypilot/selfdrive/controls/lib/smart_cruise_control/vision_controller.py`.
- Uses `modelV2.orientationRate.z * modelV2.velocity.x` and a 97th percentile
  predicted lateral-acceleration estimate.
- Uses current lateral acceleration from `vEgo ** 2 * controlsState.curvature`.
- Runs a state machine: enabled, entering, turning, leaving, overriding.
- Produces an acceleration target and a target speed based on a lateral
  acceleration limit.
- This is the Sunny curve algorithm worth keeping for model-predicted curves.

Sunny SCC-M:

- Code: `sunnypilot/selfdrive/controls/lib/smart_cruise_control/map_controller.py`.
- Uses map target velocities and GPS route points from shared params.
- In the personal C3 alpha this remains disabled because map/route speed data
  is not trusted as a default speed truth.

Carrot / Genius Inputs:

- Phone/APN/N/Navipilot speed limits enter through the phone-first speed-limit
  resolver and timeout if stale.
- Navigation events, SDI, speed bumps, model speed, and traffic-light evidence
  enter through local Carrot Web/API inputs.
- Lane-line curve and Fishop lane/lidar evidence are explicit Super Advanced
  settings and evidence paths.
- Carrot active speed, auto-turn, and traffic stop remain separate user gates.

## Mode Contract

`CurveSpeedControlMode` is the only user-facing owner for Sunny curve-speed
participation:

| Mode | Label | Sunny SCC-V | Carrot Inputs | Sunny SCC-M |
|---|---|---:|---:|---:|
| 0 | Off | Off | Off for curve mode | Off |
| 1 | Sunny | On | Off for curve mode | Off |
| 2 | Carrot | Off | On | Off |
| 3 | Fusion | On | On | Off |

Fusion means Sunny model-curvature quality plus Carrot navigation/phone/lane inputs. It does not mean enabling Sunny map-speed control.

## Safety Boundary

- `SmartCruiseControlVision` and `SmartCruiseControlMap` are hidden legacy
  params and must not decide control behavior.
- SmartCruiseControlMap remains inert in all Genius Pilot modes.
- `SpeedLimitPolicy`, `CarrotPhoneSpeedLimitEnabled`,
  `CarrotActiveSpeedControlEnabled`, `CarrotAutoTurnControlEnabled`, and
  `UseLaneLineCurveSpeed` keep their own gates; curve mode does not bypass them.
- Every upstream update must pass the curve-speed contract before publishing
  `/x`.
