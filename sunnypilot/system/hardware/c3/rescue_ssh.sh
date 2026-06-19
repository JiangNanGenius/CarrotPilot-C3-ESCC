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

start_password_sshd() {
  local sshd_bin
  local sshd_config="/data/carrotpilot/ssh/sshd_config"

  sshd_bin="$(command -v sshd 2>/dev/null || true)"
  [ -n "$sshd_bin" ] || [ ! -x /usr/sbin/sshd ] || sshd_bin="/usr/sbin/sshd"
  [ -n "$sshd_bin" ] || return 0

  as_root mkdir -p /data/carrotpilot/ssh /run/sshd >/dev/null 2>&1 || true
  cat <<'EOF' | as_root tee "$sshd_config" >/dev/null || true
Port 22
ListenAddress 0.0.0.0
HostKey /data/etc/ssh/ssh_host_rsa_key
HostKey /data/etc/ssh/ssh_host_ecdsa_key
HostKey /data/etc/ssh/ssh_host_ed25519_key
PasswordAuthentication yes
PubkeyAuthentication yes
AuthorizedKeysFile /data/params/d/GithubSshKeys .ssh/authorized_keys
KbdInteractiveAuthentication yes
ChallengeResponseAuthentication yes
UsePAM yes
PermitRootLogin no
AllowUsers comma
StrictModes no
X11Forwarding no
PrintMotd no
Subsystem sftp internal-sftp
PidFile /tmp/carrot_c3_sshd.pid
EOF

  as_root "$sshd_bin" -t -f "$sshd_config" >/dev/null 2>&1 || return 0
  if [ -f /tmp/carrot_c3_rescue_sshd.pid ]; then
    as_root kill "$(cat /tmp/carrot_c3_rescue_sshd.pid 2>/dev/null)" >/dev/null 2>&1 || true
    as_root rm -f /tmp/carrot_c3_rescue_sshd.pid >/dev/null 2>&1 || true
  fi
  as_root systemctl stop ssh.socket ssh >/dev/null 2>&1 || true
  as_root service ssh stop >/dev/null 2>&1 || true
  as_root "$sshd_bin" -f "$sshd_config" -E /tmp/carrot_c3_sshd.log >/dev/null 2>&1 || true
}

main() {
  write_param SshEnabled "1"
  set_comma_password
  start_password_sshd

  as_root mkdir -p /data/carrotpilot >/dev/null 2>&1 || true
  printf "ready\n" | as_root tee /data/carrotpilot/rescue_ssh_ready >/dev/null 2>&1 || true
  log "enabled temporary alpha SSH password access for user comma"
}

main "$@"
exit 0
