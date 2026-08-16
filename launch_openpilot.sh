#!/usr/bin/env bash
# Clone C3 launcher entry. Mirror Mr.One's robust approach: no fragile exact-match
# model detection, no set -e that can trap-loop on a misbehaving read.
# Route clone C3 ("tici" in device model) to the C3 launcher; otherwise the stock launcher.

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
C3_LAUNCH_SH="$DIR/openpilot/sunnypilot/system/hardware/c3/launch_chffrplus.sh"

MODEL="$(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null || true)"
export MODEL

# Fuzzy match: clone C3 model strings vary (e.g. "comma tici", "tici", extra chars).
if echo "$MODEL" | grep -qi "tici"; then
  if [ -x "$C3_LAUNCH_SH" ]; then
    exec "$C3_LAUNCH_SH"
  fi
fi

exec "$DIR/launch_chffrplus.sh"
