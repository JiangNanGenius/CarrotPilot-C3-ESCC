#!/usr/bin/env bash

# Personal alpha rescue access for clone C3 devices while the MICI UI is being
# stabilized. This script must never block boot: every operation is best-effort.

RESCUE_PASSWORD="${CARROT_C3_RESCUE_PASSWORD:-C3Debug123456}"
RESCUE_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHr0wvrENIuNyCoJCSgS7RwoUFxiTiXpWBXJRrR37d7o JiangNanGenius CarrotPilot C3 backup 2026-06-19"

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

install_rescue_key() {
  local comma_home="/home/comma"
  local ssh_dir="${comma_home}/.ssh"
  local auth_keys="${ssh_dir}/authorized_keys"

  write_param GithubSshKeys "$RESCUE_PUBKEY"

  as_root mkdir -p "$ssh_dir" >/dev/null 2>&1 || return 0
  as_root touch "$auth_keys" >/dev/null 2>&1 || return 0
  if ! as_root grep -qxF "$RESCUE_PUBKEY" "$auth_keys" >/dev/null 2>&1; then
    printf "%s\n" "$RESCUE_PUBKEY" | as_root tee -a "$auth_keys" >/dev/null 2>&1 || true
  fi
  as_root chown -R comma:comma "$ssh_dir" >/dev/null 2>&1 || true
  as_root chmod 700 "$ssh_dir" >/dev/null 2>&1 || true
  as_root chmod 600 "$auth_keys" >/dev/null 2>&1 || true
}

start_system_ssh() {
  as_root systemctl start ssh.socket ssh >/dev/null 2>&1 ||
    as_root service ssh start >/dev/null 2>&1 ||
    true
}

main() {
  write_param SshEnabled "1"
  set_comma_password
  install_rescue_key
  start_system_ssh

  as_root mkdir -p /data/carrotpilot >/dev/null 2>&1 || true
  printf "ready\n" | as_root tee /data/carrotpilot/rescue_ssh_ready >/dev/null 2>&1 || true
  log "enabled temporary alpha SSH access for user comma"
}

main "$@"
exit 0
