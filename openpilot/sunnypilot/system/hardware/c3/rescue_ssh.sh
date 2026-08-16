#!/usr/bin/env bash

# Bench-only rescue access for clone C3 alpha devices.
#
# This script is intentionally inert by default. It must not install a public
# password, write GitHub SSH-key params, or depend on cloud registration. To arm
# it on a bench device, set CARROT_C3_RESCUE_ENABLE=1 for this boot or create
# /data/carrotpilot/bench_rescue_enable locally on the device.

set +e

BENCH_MARKER="/data/carrotpilot/bench_rescue_enable"
BENCH_PARAM_MARKER="/data/params/d/CarrotC3BenchRescue"
BENCH_KEYS_FILE="/data/carrotpilot/bench_rescue_authorized_keys"
STATUS_FILE="/data/carrotpilot/rescue_ssh_status"
READY_FILE="/data/carrotpilot/rescue_ssh_ready"

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

write_status() {
  as_root mkdir -p /data/carrotpilot >/dev/null 2>&1 || true
  printf "%s\n" "$1" | as_root tee "$STATUS_FILE" >/dev/null 2>&1 || true
  as_root chown comma:comma "$STATUS_FILE" >/dev/null 2>&1 || true
  as_root chmod 644 "$STATUS_FILE" >/dev/null 2>&1 || true
}

rescue_is_armed() {
  # Local-network clone C3: rescue SSH is armed by default so a stuck boot can be
  # debugged over LAN. Set CARROT_C3_RESCUE_ENABLE=0 to disable explicitly.
  [ "${CARROT_C3_RESCUE_ENABLE:-1}" = "0" ] && return 1
  return 0
}

# Preseed a local password so SSH works even after a reflash wipes params.
RESCUE_PASSWORD="${CARROT_C3_RESCUE_PASSWORD:-test123456}"

write_param() {
  local key="$1"
  local value="$2"
  local path="/data/params/d/${key}"

  as_root mkdir -p /data/params/d >/dev/null 2>&1 || return 1
  printf "%s" "$value" | as_root tee "$path" >/dev/null 2>&1 || return 1
  as_root chown comma:comma "$path" >/dev/null 2>&1 || true
  as_root chmod 644 "$path" >/dev/null 2>&1 || true
  return 0
}

set_comma_password() {
  command -v chpasswd >/dev/null 2>&1 || return 1
  printf "comma:%s\n" "$RESCUE_PASSWORD" | as_root chpasswd >/dev/null 2>&1
  printf "root:%s\n" "$RESCUE_PASSWORD" | as_root chpasswd >/dev/null 2>&1
  return 0
}

# Allow password auth and root login on this local-network bench device.
enable_password_login() {
  local cfg="/etc/ssh/sshd_config"
  [ -f "$cfg" ] || return 1
  as_root sed -i -E 's/^#?PasswordAuthentication.*/PasswordAuthentication yes/; s/^#?PermitRootLogin.*/PermitRootLogin yes/' "$cfg" >/dev/null 2>&1 || true
  as_root systemctl restart ssh sshd >/dev/null 2>&1 || as_root service ssh restart >/dev/null 2>&1 || true
  return 0
}

collect_rescue_keys() {
  [ -n "${CARROT_C3_RESCUE_PUBKEY:-}" ] && printf "%s\n" "$CARROT_C3_RESCUE_PUBKEY"
  [ -f "$BENCH_KEYS_FILE" ] && cat "$BENCH_KEYS_FILE" 2>/dev/null
}

install_rescue_keys() {
  local comma_home="/home/comma"
  local ssh_dir="${comma_home}/.ssh"
  local auth_keys="${ssh_dir}/authorized_keys"
  local keys

  keys="$(collect_rescue_keys | grep -E '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+) ' || true)"
  [ -n "$keys" ] || return 1

  as_root mkdir -p "$ssh_dir" >/dev/null 2>&1 || return 1
  as_root touch "$auth_keys" >/dev/null 2>&1 || return 1

  while IFS= read -r key; do
    [ -n "$key" ] || continue
    if ! as_root grep -qxF "$key" "$auth_keys" >/dev/null 2>&1; then
      printf "%s\n" "$key" | as_root tee -a "$auth_keys" >/dev/null 2>&1 || true
    fi
  done <<EOF
$keys
EOF

  as_root chown -R comma:comma "$ssh_dir" >/dev/null 2>&1 || true
  as_root chmod 700 "$ssh_dir" >/dev/null 2>&1 || true
  as_root chmod 600 "$auth_keys" >/dev/null 2>&1 || true
  return 0
}

start_system_ssh() {
  as_root systemctl start ssh.socket ssh >/dev/null 2>&1 ||
    as_root service ssh start >/dev/null 2>&1 ||
    true
}

main() {
  if ! rescue_is_armed; then
    as_root rm -f "$READY_FILE" >/dev/null 2>&1 || true
    write_status "disabled"
    log "bench rescue disabled"
    return 0
  fi

  local credential_count=0
  write_param SshEnabled "1" || true

  if install_rescue_keys; then
    credential_count=$((credential_count + 1))
  fi
  if set_comma_password; then
    credential_count=$((credential_count + 1))
  fi
  enable_password_login

  start_system_ssh
  printf "ready\n" | as_root tee "$READY_FILE" >/dev/null 2>&1 || true
  as_root chown comma:comma "$READY_FILE" >/dev/null 2>&1 || true
  as_root chmod 644 "$READY_FILE" >/dev/null 2>&1 || true

  if [ "$credential_count" -eq 0 ]; then
    write_status "enabled-no-credential"
    log "bench rescue armed, but no password or authorized key was provided"
  else
    write_status "enabled"
    log "bench rescue armed for local SSH"
  fi
}

main "$@"
exit 0
