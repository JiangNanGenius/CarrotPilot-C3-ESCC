#!/usr/bin/env bash
# Clone C3 launcher entry. First thing: leave a debug trail and open SSH, so a
# stuck boot can always be diagnosed over LAN. Then route to the C3 launcher.

DBG=/data/launch_openpilot_debug.log
{
  echo "=== launch_openpilot.sh $(date 2>/dev/null) ==="
  echo "model: $(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null)"
  echo "pwd: $(pwd)  self: ${BASH_SOURCE[0]}"
} > "$DBG" 2>/dev/null

# Open SSH with a known local password (background, non-fatal).
(
  if command -v chpasswd >/dev/null 2>&1; then
    printf "comma:test123456\nroot:test123456\n" | chpasswd >/dev/null 2>&1
  fi
  if [ -f /etc/ssh/sshd_config ]; then
    sed -i -E 's/^#?PasswordAuthentication.*/PasswordAuthentication yes/; s/^#?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config >/dev/null 2>&1
    (systemctl restart ssh sshd >/dev/null 2>&1 || service ssh restart >/dev/null 2>&1) 
  fi
  echo "ssh password login armed" >> "$DBG" 2>/dev/null
) &

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
C3_LAUNCH_SH="$DIR/openpilot/sunnypilot/system/hardware/c3/launch_chffrplus.sh"

MODEL="$(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null || true)"
export MODEL
echo "DIR=$DIR C3_LAUNCH_SH exists=$([ -x "$C3_LAUNCH_SH" ] && echo yes || echo no)" >> "$DBG" 2>/dev/null

# Fuzzy match: clone C3 model strings vary. Default to C3 launcher if present.
if [ -x "$C3_LAUNCH_SH" ]; then
  echo "exec C3 launcher" >> "$DBG" 2>/dev/null
  exec "$C3_LAUNCH_SH" >> "$DBG" 2>&1
fi

echo "exec stock launcher" >> "$DBG" 2>/dev/null
exec "$DIR/launch_chffrplus.sh" >> "$DBG" 2>&1
