# SCC visibility recovery and route replay — 2026-09-09

## Deployed: display and curve-controller hotfix

Production base remains `0498a35497800ba9514459187f04d3099a41b834`, with three UI hotfix files:

- `selfdrive/ui/sunnypilot/onroad/hud_renderer.py`: restore the missing SCC renderer call. This deployed file was constructed from production HEAD, NOT copied from the larger unshipped candidate.
- `selfdrive/ui/sunnypilot/onroad/smart_cruise_control.py`: persistent SCC-V/SCC-M badges; neutral inactive/standby, amber preview/calculating, green selected curve target with a bounded pulse. Stale or invalid planner/control data clears active display.
- `selfdrive/ui/sunnypilot/onroad/curve_status.py`: pure display-state classifier.

The pulse is display feedback only and does not alter activation thresholds or control authority. A curve controller must be active AND selected as the final cruise source before its green limit indication pulses. Other active constraints do not falsely light the curve badge.

Backups: `/data/codex-scc-ui-backup-20260909/` (original relative paths preserved). The curve_status helper is new. All three deployed UI SHA-256 values matched local hotfix artifacts. Production imports and syntax checks passed. With IsOnroad=false, UI PID 21729 was terminated normally; manager restarted it as PID 69954, running with exitCode=0. Recent post-restart error scan was empty. No model, calibration, saved setting, schema or native binary was changed.

Two additional controller Python files were subsequently deployed with backups in the same directory: vision_controller.py guards malformed/stale/non-finite model curves and zero curvature; map_controller.py validates map snapshots and corrects the constant-jerk quadratic root. These retain the original activation thresholds, acceleration limits and engagement logic. Production import verified vision threshold 1.3 and map time-to-target 1.82574 seconds for 20→19 m/s at jerk -0.6. The onroad planner was not running and was not forced to start.

Rollback: restore the four backed-up files while offroad, then restart only UI. The now-unused new helper can remain or be archived; it does not execute independently.

## Recorded model replay

Route `0000003e--1a56b426a7`, ten rlog segments, approximately 549 seconds. Events sorted by monotonic time within each segment; unsorted ingestion can incorrectly classify valid inputs as future/stale. Reader reported corrupted events; figures cover readable data only.

- 10,818 model frames replayed; five skipped for unavailable/stale required inputs.
- Existing SCC-V entry threshold: 1.3 m/s²; minimum speed: above 20 km/h. Settings were read, not changed.
- 1,359 frames satisfied speed/engagement/non-override eligibility; six exceeded the entry threshold. Maximum eligible prediction: 1.41334 m/s².
- Production rlog contains eight `entering` state messages, approximately 201.14–201.49 seconds. Replayed SCC-V also activated on eight frames, with targets 36.5–39.9 km/h below the 40 km/h ceiling.
- Production and candidate vision replays produced identical counts, maxima and activation examples. The defensive input fix does not manufacture activation on this recorded route.
- SCC-M had no recorded turning state. Its separate MapTargetVelocities input is not recorded in these model logs; no claim that map targets were reconstructed or that map control was validated in motion.

Artifacts: `artifacts/20260909-scc-recovery/{production-replay,candidate-replay}.json`. The reusable audit tool has no publishers or parameter writes.

## Other fixes remain isolated

- Deployed map reader now rejects malformed/non-list/non-finite/out-of-range snapshots instead of throwing into the longitudinal planner; regression cases cover malformed and valid snapshots. This is not proof of the cause of an earlier communication alert.
- Existing candidate speed-ceiling/road-target policy and the follow/traffic distance settings remain in the isolated full build, NOT production. Current saved CarrotSpeedLimitEnable=true, StopDistanceCarrot=600 cm. Production MPC already has a fixed 6 m comfort target: wiring a default-6 m slider alone cannot explain or cure the observed 1.7 m stop.
- Near-stop readable data shows lead-following (`lead0`) and stopPoint=1000 sentinel, not a valid visual red-light stopping point. Actuator request reduced braking at low speed before shouldStop became true near 160 seconds. Actuation delay/tuning and planner feedback must be assessed before changing braking behavior; no ad hoc brake/steer tuning applied here.
- Direct evaluation of the deployed native cost function at zero speed and a 6 m obstacle returned zero distance error. The current native solver really uses 6 m; this is not a hidden old 2 m compiled constant.
- Full candidate planner open-loop replay completed 10,817 frames with no solver failure/non-finite acceleration and zero attempted parameter writes. It uses recorded CP/CP_SP and current settings; no publishers. Default-6 m braking output remains close to production in the near-stop window. At road 40 / ceiling 50 it constrains target to 40; road 50 / ceiling 40 remains capped at 40 as specified. A new higher road limit cannot bypass a lower user ceiling. The replay artifact is planner-replay.json; it is not a closed-loop physical stop-distance test.

## Validation

- 51 focused C3 tests passed, including curve status, original threshold/override/low-speed behavior, malformed map data, candidate target policy and native MPC distance interface.
- After deployment, 26 focused tests passed against the production import path with conftest disabled; deployed controller hashes matched local files. These overlap the 51 tests and must not be added as independent coverage.
- Two bounded real-device renderer passes. First exposed invalid carControl/plan-SP envelopes in the fixture; fixture corrected explicitly. Final simulated acceptance shows standby, preview, vision-selected limiting, map-selected limiting and data invalidation. Replay disables GSM configuration writes and uses an isolated parameter/message namespace. SIMULATION=1 is limited to the replay process.
- `scc-acceptance-final.mp4`, `final-02.png` (preview), `final-03.png` (vision limit), `final-04.png` (map limit), `final-06.png` (invalid) contain synthetic inputs, not vehicle evidence. No further visual polishing is required for this scoped repair.
- Display restoration and isolated curve fixes are deployed; overall cruise/parking repair is NOT complete. Do not present this release as fixing near-stop clearance or deploying the new ceiling policy.
