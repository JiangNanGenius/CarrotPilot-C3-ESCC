#!/usr/bin/env bash

# Personal alpha rescue access for clone C3 devices while the MICI UI is being
# stabilized. This script must never block boot: every operation is best-effort.

RESCUE_PASSWORD="${CARROT_C3_RESCUE_PASSWORD:-C3Debug123456}"

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

log() {
  echo "carrot-c3-rescue-ssh: $*"
}

write_param() {
  local key="$1"
  local value="$2"
  local path="/data/params/d/${key}"

  as_root mkdir -p /data/params/d || return 0
  printf "%s" "$value" | as_root tee "$path" >/dev/null || true
  as_root chown comma:comma "$path" >/dev/null 2>&1 || true
  as_root chmod 644 "$path" >/dev/null 2>&1 || true
}

set_comma_password() {
  if command -v chpasswd >/dev/null 2>&1; then
    printf "comma:%s\n" "$RESCUE_PASSWORD" | as_root chpasswd >/dev/null 2>&1 || true
  fi
}

start_system_ssh() {
  as_root systemctl start ssh.socket ssh >/dev/null 2>&1 ||
    as_root service ssh start >/dev/null 2>&1 ||
    true
}

main() {
  write_param SshEnabled "1"
  set_comma_password
  start_system_ssh

  as_root mkdir -p /data/carrotpilot >/dev/null 2>&1 || true
  printf "ready\n" | as_root tee /data/carrotpilot/rescue_ssh_ready >/dev/null 2>&1 || true
  log "enabled temporary alpha SSH access for user comma"
}

main "$@"
exit 0
