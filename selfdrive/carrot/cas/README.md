# Carrot Adaptive Steering

CAS adds a learned residual steering correction on top of the existing lateral
controller. The device only loads JSON weights and runs numpy inference; training
is done off-device with tools under `tools/cas`.

Safety invariant: if CAS is disabled, no matching model exists, or alpha is zero,
the lateral controller output is identical to the base controller output.

Design docs:

- `docs/cas_design.md`: main architecture and rationale
- `docs/cas_roadmap.md`: phased development checklist
- `docs/cas_independent_migration.md`: CAS-independent migration plan for adopting proven steering NN ideas without adding external-model metadata to CAS weights/logs

