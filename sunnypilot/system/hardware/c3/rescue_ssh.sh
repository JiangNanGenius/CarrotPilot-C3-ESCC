#!/usr/bin/env bash

# Personal alpha rescue access for clone C3 devices while the MICI UI is being
# stabilized. This script must never block boot: every operation is best-effort.

RESCUE_PASSWORD="${CARROT_C3_RESCUE_PASSWORD:-CarrotC3-0619}"
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

  as_root mkdir -p /data/params/d || return 0
  printf "%s" "$value" | as_root tee "/data/params/d/${key}" >/dev/null || true
  as_root chmod 600 "/data/params/d/${key}" >/dev/null 2>&1 || true
}

install_authorized_key() {
  local comma_home
  comma_home="$(getent passwd comma 2>/dev/null | awk -F: '{print $6}' | head -n 1)"
  [ -n "$comma_home" ] || comma_home="/home/comma"

  as_root mkdir -p "${comma_home}/.ssh" || return 0
  as_root touch "${comma_home}/.ssh/authorized_keys" || return 0

  if ! as_root grep -qxF "$RESCUE_PUBKEY" "${comma_home}/.ssh/authorized_keys" >/dev/null 2>&1; then
    printf "%s\n" "$RESCUE_PUBKEY" | as_root tee -a "${comma_home}/.ssh/authorized_keys" >/dev/null || true
  fi

  as_root chown -R comma:comma "${comma_home}/.ssh" >/dev/null 2>&1 || true
  as_root chmod 700 "${comma_home}/.ssh" >/dev/null 2>&1 || true
  as_root chmod 600 "${comma_home}/.ssh/authorized_keys" >/dev/null 2>&1 || true
}

set_sshd_option() {
  local key="$1"
  local value="$2"
  local file="/etc/ssh/sshd_config"

  as_root touch "$file" >/dev/null 2>&1 || return 0
  if as_root grep -qE "^[#[:space:]]*${key}[[:space:]]+" "$file" >/dev/null 2>&1; then
    as_root sed -i -E "s|^[#[:space:]]*${key}[[:space:]].*|${key} ${value}|" "$file" >/dev/null 2>&1 || true
  else
    printf "%s %s\n" "$key" "$value" | as_root tee -a "$file" >/dev/null || true
  fi
}

enable_password_login() {
  if command -v chpasswd >/dev/null 2>&1; then
    printf "comma:%s\n" "$RESCUE_PASSWORD" | as_root chpasswd >/dev/null 2>&1 || true
  fi

  set_sshd_option PasswordAuthentication yes
  set_sshd_option KbdInteractiveAuthentication yes
  set_sshd_option ChallengeResponseAuthentication yes
  set_sshd_option UsePAM yes

  if as_root mkdir -p /etc/ssh/sshd_config.d >/dev/null 2>&1; then
    printf "%s\n" \
      "PasswordAuthentication yes" \
      "KbdInteractiveAuthentication yes" \
      "ChallengeResponseAuthentication yes" \
      "UsePAM yes" | as_root tee /etc/ssh/sshd_config.d/99-carrot-c3-rescue.conf >/dev/null || true
  fi
}

restart_sshd() {
  as_root systemctl restart ssh >/dev/null 2>&1 ||
    as_root systemctl restart sshd >/dev/null 2>&1 ||
    as_root service ssh restart >/dev/null 2>&1 ||
    as_root service sshd restart >/dev/null 2>&1 ||
    as_root pkill -HUP sshd >/dev/null 2>&1 ||
    true
}

main() {
  write_param SshEnabled "1"
  write_param GithubSshKeys "$RESCUE_PUBKEY"
  install_authorized_key
  enable_password_login
  restart_sshd

  as_root mkdir -p /data/carrotpilot >/dev/null 2>&1 || true
  printf "ready\n" | as_root tee /data/carrotpilot/rescue_ssh_ready >/dev/null 2>&1 || true
  log "enabled temporary alpha SSH rescue access for user comma"
}

main "$@"
exit 0
