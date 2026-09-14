# Cruise, distance settings and notification release — 2026-09-09

## Production deployed, with an explicit unresolved stopping boundary

61 scoped files (initial bundle 66,445,339 bytes) were deployed to `/data/openpilot` on base
`0498a35497800ba9514459187f04d3099a41b834`. The file manifest is
`artifacts/20260909-scc-recovery/release-files.txt`. No upstream push, model
change, calibration reset, CAN/safety gate change or automatic-resume change.

Delivered:

- Ceiling-only cruise policy and its schema/producer/consumer dependencies:
  ceiling 80 / road 40 produces road 40; release-pedal instrument speed can
  temporarily override; new valid road limit clears override; braking,
  disengagement and stopping clear it. Curve/lead/traffic constraints remain.
- The `CarrotSpeedLimitEnable` menu is now “道路限速来源”, with source and
  ceiling behavior explained. Existing stored key and value are preserved.
- Cruise menu exposes radar follow-stop target (3–12 m, default 6) and visual
  stop-point buffer (1–6 m, default 2), with units, expandable explanation,
  durable reads/writes and the native seven-parameter MPC interface.
- Existing SCC-V/SCC-M display/input guards retained; ESCC control freshness
  and authoritative cruise-source HUD updates included.
- Traffic display says “检测到停车”, “模型放行 / 请确认路况”, or “未检测到”.
  Planner trafficState is not ground-truth lamp classification.
- `TrafficCueSound`, default enabled: one low chime after 0.5 s stable stop
  classification; one high chime after at least 1 s stationary dwell followed
  by 0.15 s autonomous forward movement above 0.3 m/s. This only reads state.
  Brake/gas/longitudinal disable or stale inputs cancel start arming. Existing
  alerts win and cues are dropped, never queued. Existing one-shot assets are
  reused. No new control action. The final courtesy toggle is independent of
  global QuietMode, and does not unmute any other prompt. The device had
  QuietMode=true: the original implementation would have silently suppressed
  the requested sounds. A scoped three-file follow-up fixed that and retained
  the user's global setting. Its previous files/manifest are in backup's
  `quiet-scope` directory; the top-level after-manifest records final hashes.

## Latest route replay and red-stop mismatch

Route `0000003e--1a56b426a7`, ten full rlog segments. 2,702 healthy recorded
5-Hz samples were extracted using monotonic times. Reader warns of corrupted
events; coverage is limited to readable valid inputs, not all events.

At t=256.06 s the recorded speed was 15.67 km/h, planner stop point 10.19 m,
trafficState=1, target 21.41 km/h, acceleration request -0.08 m/s² and command
-0.11 m/s². Around t=256.85 it requested positive acceleration; the driver
pressed the brake around t=257. Stopped hold later retained target zero.
This supports the user's distinction: hold works, approach response is late.
It does not prove the visible lamp color, physical line distance or model
perception accuracy. The earlier 1.7 m near-stop was a separate lead-follow
case, not this visual-stop case.

The old visual envelope used roughly 2.4 m/s² comfort braking while its output
goes through the ordinary cruise channel, limited to -1.2 m/s² and jerk
filtered. The deployed correction budgets at most 1.0 m/s² and reserves
max(1.5 s, CP actuator delay + 1 s): solve d = v*t + v²/(2*b) after subtracting
the user buffer. It lowers a target, not actuator safety limits; it does not
alter stop detection or green/release conditions.

Full new planner open-loop replay: 10,817 frames, zero parameter-write
attempts, no solver failure or non-finite acceleration. Around t=256 the
candidate target is 10.1 km/h and acceleration -1.2 m/s², replacing the old
21 km/h target. Recorded car states are held fixed: this is not a prediction
of resulting real stopping clearance.

**Unresolved safety boundary:** the first ideal fixed-point test starting at
15.67 km/h and only 10.19 m remaining still overran by about 1.61 m with the
unchanged cruise brake/jerk channel and 0.5 s actuator delay. Both 2 m and 4 m
buffer runs failed the initial no-overrun expectation. This is retained as
an explicit negative-boundary test, NOT hidden as a completed repair. Timely
detection at 40 km/h / 90 m and 60 km/h / 180 m passed no-overrun tests for
2 m and 4 m buffers. The late case improves over the old envelope but remains
unsafe. Settings and the speed-envelope correction do not guarantee a stop;
late perception, moving stop estimates and actual actuation need further
engineering and controlled vehicle validation. Do not recommend relying on
automatic red-light stopping on public roads based on this release.

The physical lead-follow near-stop root cause also remains unclosed. The new
slider default is the same 6 m as the old compiled comfort target, not proof
that the previously observed 1.7 m stop is solved.

## Build, tests and reboot

- Native C3 full SCons build completed using `/data/c3-build-deps/bin` first
  in PATH. Initial default capnpc 1.0.2 mismatched headers 1.0.1; regenerated
  with the matching 1.0.1 compiler and completed the build. No mismatched
  artifacts were deployed.
- 192 regression tests and 256 subtests passed, including following-distance
  maneuvers, MPC, source policy, settings, sound priority and HDA/ESCC reports.
- Subsequently 16 focused tests passed after stationary negative-noise
  handling and addition of the explicit late-stop simulation boundary. These
  overlap the previous set; do not sum counts as unique coverage.
- 57 tests passed against the actual production import path after deployment.
  Production ldd resolves MPC libraries under `/data/openpilot`, not staging.
- Final independent-quiet behavior passed 20 focused sound/state tests,
  including proof that only an explicitly issued courtesy chime bypasses quiet
  mode. UI was restarted by manager after the three-file follow-up; soundd is
  normally off offroad and will import the updated implementation on ignition.
- Reboot changed boot id from `725b9d27-7ee6-45a1-9c06-94ec5fcf4c81` to
  `f1c438c8-c61e-42cf-8632-003cb0807f05`. AGNOS first entered its reset dialog
  because boot touch_count >4 (`got taps`). The exact reset-dialog process
  was terminated before any reset; comma.sh then continued normal launch.
  No OS boot-gesture logic was changed.
- Post-boot all 61 hashes match; all preexisting Carrot settings and checked
  CalibrationParams/LiveTorqueParameters match backup. UI running, exitCode
  zero; one Panda; offroad; no unexpectedly stopped required processes.
  Current values: TrafficCueSound=1, follow=600 cm, visual buffer=200 cm,
  road source enabled, instrument reference enabled.

## UI evidence and rollback

`cruise-menu-final.mp4` / `menu-distances-final.png` are isolated device
renderer acceptance evidence, not photographs of the live production screen.
An additional functional navigation check, requested after the user reported
an inaccessible menu, clicked the home Settings button and then the Cruise
sidebar item, and asserted the resulting panel before expanding anything.
It passed (`cruise-navigation.mp4`); it did not directly call open_settings to
bypass navigation. This too is isolated UI input replay of matching deployed
code, not a claim to have physically tapped the user's running screen.
The validation and production distinction explains why the user previously
could not find the unshipped settings. Labels and expandable explanations
follow the impeccable clarification workflow, preserving the incumbent UI.

Backup: `/data/codex-cruise-release-backup-20260909`, mode 0700, contains
original files, native and Carrot parameter stores, and before/after hash
manifest. A failed preflight backup was retained separately at
`/data/codex-cruise-preflight-backup-20260909`; no files had been deployed then.
Rollback must restore the entire manifest's original files while offroad,
archive the manifest's originally absent additions, and reboot. Do not mix
the old MPC binaries with the new seven-parameter caller. Restore parameters
only if needed after comparing current user changes; never blanket-reset.
