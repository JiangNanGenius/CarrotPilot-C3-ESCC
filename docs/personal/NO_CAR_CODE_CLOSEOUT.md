# No-Car And Code Phase Closeout

This page defines the current completion boundary for the Genius Pilot C3
alpha no-car/code phase.

## Scope

This phase covers work that can be completed from the Mac workspace or through
local no-car tooling without a new successful C3 install, SSH session, parked C3
session, or Seltos road drive.

Included:

- source code, params, schema, settings, localization, and documentation;
- local static checks and release gates;
- no-car process replay readiness and crash-free smoke coverage;
- local UI replay readiness and deterministic UI replay contracts;
- model manager, Super Advanced, touch fallback, visualization, Carrot Web/API,
  Navipilot/APN replay, Fishop sample replay, and no-cloud contracts;
- published `/x` installer audit and alpha branch consistency.

Not included:

- clean `/x` reinstall confirmation on the physical clone C3;
- SSH recovery after the current key/password rejection state;
- parked C3 UI, IMU, model list/download, and writable-safe probes;
- Kia Seltos 2023 road validation.

## Completion Evidence

The no-car/code phase is considered locally complete only when all of these
commands pass from the alpha worktree:

```bash
python3 scripts/personal/genius_no_car_completion_audit.py --json
python3 scripts/personal/sunnypilot_c3_alpha_static_check.py
python3 scripts/personal/sunnypilot_c3_alpha_release_gate.py --full
python3 scripts/personal/sunnypilot_c3_installer_audit.py
python3 scripts/personal/genius_no_car_evidence_bundle.py --full-gate --json
```

The current audit expectation is:

- no unchecked TODO is classified as local no-car/code work;
- every unchecked TODO is classified as device install, real-car, recurring
  release policy, docs-after-feedback, future fixture/baseline, current release
  archive, or not-required-for-code-phase work;
- full release gate includes the packed TICI updater UI fallback, model manager,
  Super Advanced, C3 touch, no-cloud, local Web/API, visualization, Fishop,
  Navipilot/APN replay, UI replay, and installer checks.

## Current External Dependency

The current C3 connectivity state is:

- LAN SSH port `192.168.100.174:22` is reachable, but rejects available keys and
  password authentication is disabled.
- USB `192.168.5.11:22` does not answer.

Until `/x` is reinstalled or SSH access is restored, device-side no-car checks
must remain pending and visible in `docs/personal/TODO.md`.

## Next Evidence After Device Access

After a clean `/x` install or restored SSH access, collect:

```bash
python3 scripts/personal/sunnypilot_c3_device_collect.py \
  --host 192.168.100.174 \
  --navipilot-live-check \
  --require-no-cloud-processes \
  --parked-hardware-probe \
  --imu-probe \
  --ui-capture
```

Keep this silent by default. Do not run speaker probes unless explicitly asked.
