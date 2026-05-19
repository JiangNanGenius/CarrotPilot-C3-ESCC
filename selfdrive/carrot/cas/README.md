# Carrot Adaptive Steering

CAS adds a learned residual steering correction on top of the existing lateral
controller. The device only loads JSON weights and runs numpy inference; training
is done off-device with tools under `tools/cas`.

Safety invariant: if CAS is disabled, no matching model exists, or alpha is zero,
the lateral controller output is identical to the base controller output.

