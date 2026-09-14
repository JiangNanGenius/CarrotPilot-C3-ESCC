# Device health check — 2026-09-09 Sydney

Production remains `0498a35497800ba9514459187f04d3099a41b834`; device Git status clean. No candidate control changes, model replacement, firmware update, or reboot performed.

## Observed

- Device is offroad; one Panda is present. All manager processes match their shouldBeRunning state. Thermal status green. No failed systemd units or matching kernel OOM/filesystem I/O errors in the current boot check.
- /data has 6.2 GB available; shared memory uses 22 MB. Recent logs include occasional UI frame drops; onroad frame-rate performance was not tested.
- Model catalog had one startup DNS failure followed by usable cache; earlier live catalog comparison succeeded.
- /data/stats reached its 10,000-file limit (73,072,013 bytes), preventing new statistics from being saved. The cloud consumer is not running in the current configuration; it was not enabled by this check.
- Ubuntu NTP and three alternative NTP endpoints timed out. The wall clock was approximately three minutes behind trusted UTC. GPS-dependent operation was not tested indoors.
- /etc/udev/rules.d/comma-polkit.rules contains a duplicate of the valid /etc/polkit-1/rules.d/comma-polkit.rules. udev reports syntax errors because this is a polkit JavaScript rule, not a udev rule. The root filesystem is read-only.

## Applied recovery

1. Moved the 10,000 statistics files older than one hour to /data/stats-recovery-20260909 using no-clobber moves. No statistics or route logs deleted. Confirmed a new statistics file subsequently appeared in /data/stats. This restores recording now, but does not implement permanent queue retention; the queue can fill again.
2. Rechecked IsOnroad=false, set UTC from the current trusted clock, and saved LastKnownSystemTime using the existing trusted checkpoint helper. No driving/calibration preferences changed. This is a one-time clock correction, not a fix for blocked NTP.

## Deferred / boundaries

- Attempted reversible rename of the misplaced udev rule failed with read-only filesystem; no system file changed and no remount attempted. Correct polkit rule remains intact. Address in a separately validated system-image/configuration repair.
- NTP reachability and durable statistics retention require follow-up; do not treat their immediate recoveries as permanent fixes.
- No live vehicle activation, braking, steering, traffic stopping, GPS fix, or onroad model performance validation. Previous unpublished control candidates remain separate.
