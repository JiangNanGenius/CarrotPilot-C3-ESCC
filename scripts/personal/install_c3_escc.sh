#!/usr/bin/env sh
set -eu

PROJECT_NAME="CarrotPilot-C3-ESCC"
DEFAULT_REPO_URL="https://github.com/JiangNanGenius/CarrotPilot-C3-ESCC.git"
DEFAULT_REF="carrotpilot-c3-escc-20260618-test25"

REPO_URL="${CARROTPILOT_REPO_URL:-$DEFAULT_REPO_URL}"
REF="${CARROTPILOT_REF:-$DEFAULT_REF}"
INSTALL_DIR="${CARROTPILOT_INSTALL_DIR:-/data/openpilot}"
TMP_DIR="${CARROTPILOT_TMP_DIR:-/data/tmppilot-carrotpilot-c3-escc}"
BACKUP_ROOT="${CARROTPILOT_BACKUP_ROOT:-/data/carrotpilot-backups}"
PARAMS_DIR="${CARROTPILOT_PARAMS_DIR:-/data/params/d}"
FIRST_BOOT_NOTE="${CARROTPILOT_FIRST_BOOT_NOTE:-/data/media/0/carrotpilot-c3-escc-first-boot.txt}"

DRY_RUN=0
APPLY_PARAMS=1
UPDATE_CONTINUE=1
WRITE_FIRST_BOOT_NOTE=1
RUN_COMMISSIONING=0
FORCE=0

usage() {
  cat <<EOF
$PROJECT_NAME installer

Usage:
  install_c3_escc.sh [options]

Options:
  --ref REF              Install a tag or branch. Default: $DEFAULT_REF
  --repo URL             Git repository URL. Default: $DEFAULT_REPO_URL
  --install-dir PATH     Target directory. Default: /data/openpilot
  --tmp-dir PATH         Temporary clone directory. Default: /data/tmppilot-carrotpilot-c3-escc
  --backup-root PATH     Backup directory. Default: /data/carrotpilot-backups
  --params-dir PATH      Params directory. Default: /data/params/d
  --first-boot-note PATH Write first-boot next-step note. Default: /data/media/0/carrotpilot-c3-escc-first-boot.txt
  --no-params            Do not write safe first-boot params
  --no-continue          Do not update /data/continue.sh
  --no-first-boot-note   Do not write the first-boot next-step note
  --run-commissioning    Run c3_commissioning.py --archive after install
  --dry-run              Print actions without changing files
  --force                Allow non-aarch64 or non-/data install targets
  -h, --help             Show this help

Environment overrides:
  CARROTPILOT_REPO_URL, CARROTPILOT_REF, CARROTPILOT_INSTALL_DIR,
  CARROTPILOT_TMP_DIR, CARROTPILOT_BACKUP_ROOT, CARROTPILOT_PARAMS_DIR,
  CARROTPILOT_FIRST_BOOT_NOTE
EOF
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

run() {
  log "+ $*"
  if [ "$DRY_RUN" = "0" ]; then
    "$@"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

safe_path_check() {
  path="$1"
  label="$2"

  [ -n "$path" ] || die "$label is empty"
  [ "$path" != "/" ] || die "$label must not be /"
  [ "$path" != "/data" ] || die "$label must not be /data"

  case "$path" in
    /data/*) ;;
    *)
      if [ "$FORCE" != "1" ]; then
        die "$label must be under /data on a C3 device, or pass --force"
      fi
      ;;
  esac
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --ref)
        [ "$#" -ge 2 ] || die "--ref requires a value"
        REF="$2"
        shift 2
        ;;
      --repo)
        [ "$#" -ge 2 ] || die "--repo requires a value"
        REPO_URL="$2"
        shift 2
        ;;
      --install-dir)
        [ "$#" -ge 2 ] || die "--install-dir requires a value"
        INSTALL_DIR="$2"
        shift 2
        ;;
      --tmp-dir)
        [ "$#" -ge 2 ] || die "--tmp-dir requires a value"
        TMP_DIR="$2"
        shift 2
        ;;
      --backup-root)
        [ "$#" -ge 2 ] || die "--backup-root requires a value"
        BACKUP_ROOT="$2"
        shift 2
        ;;
      --params-dir)
        [ "$#" -ge 2 ] || die "--params-dir requires a value"
        PARAMS_DIR="$2"
        shift 2
        ;;
      --first-boot-note)
        [ "$#" -ge 2 ] || die "--first-boot-note requires a value"
        FIRST_BOOT_NOTE="$2"
        shift 2
        ;;
      --no-params)
        APPLY_PARAMS=0
        shift
        ;;
      --no-continue)
        UPDATE_CONTINUE=0
        shift
        ;;
      --no-first-boot-note)
        WRITE_FIRST_BOOT_NOTE=0
        shift
        ;;
      --run-commissioning)
        RUN_COMMISSIONING=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --force)
        FORCE=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown option: $1"
        ;;
    esac
  done
}

write_file() {
  path="$1"
  content="$2"
  dir=$(dirname "$path")
  log "+ write $path"
  if [ "$DRY_RUN" = "0" ]; then
    mkdir -p "$dir"
    tmp="$path.tmp.$$"
    printf '%s' "$content" > "$tmp"
    mv "$tmp" "$path"
  fi
}

write_param() {
  key="$1"
  value="$2"
  write_file "$PARAMS_DIR/$key" "$value"
}

write_continue_script() {
  path="/data/continue.sh"
  tmp="/data/continue.sh.new"
  log "+ write $path"
  if [ "$DRY_RUN" = "0" ]; then
    cat > "$tmp" <<'EOF'
#!/usr/bin/env bash
cd /data/openpilot
exec ./launch_openpilot.sh
EOF
    chmod +x "$tmp"
    mv "$tmp" "$path"
  fi
}

apply_safe_params() {
  [ "$APPLY_PARAMS" = "1" ] || return 0
  log "Applying safe first-boot params"
  write_param "AlwaysOffline" "1"
  write_param "EnableConnect" "0"
  write_param "EnableEscc" "0"
  write_param "CanfdHDA2" "0"
  write_param "HyundaiCameraSCC" "0"
  write_param "EnableRadarTracks" "0"
  write_param "PowerCycleBootOk" "0"
  write_param "PowerCycleBootCommit" ""
  write_param "PowerCycleBootTag" ""
  write_param "PowerCycleBootRecordedAt" ""
}

write_first_boot_note() {
  [ "$WRITE_FIRST_BOOT_NOTE" = "1" ] || return 0
  path="$FIRST_BOOT_NOTE"
  dir=$(dirname "$path")
  log "+ write $path"
  if [ "$DRY_RUN" = "0" ]; then
    mkdir -p "$dir"
    tmp="$path.tmp.$$"
    cat > "$tmp" <<EOF
CarrotPilot-C3-ESCC first boot note

Installed ref:
  $REF

Installed repo:
  $REPO_URL

Safe first-boot params written by the installer:
  AlwaysOffline=1
  EnableConnect=0
  EnableEscc=0
  CanfdHDA2=0
  HyundaiCameraSCC=0
  EnableRadarTracks=0
  PowerCycleBootOk=0

Next parked checks on the C3:
  cd /data/openpilot
  python3 scripts/personal/c3_commissioning.py --archive

After the first successful ACC/CAN power-cycle boot:
  cd /data/openpilot
  python3 scripts/personal/record_power_cycle_boot.py
  python3 scripts/personal/collect_real_car_evidence.py --archive

If you exported settings from a working fishop / feiyang build:
  cd /data/openpilot
  python3 scripts/personal/c3_commissioning.py --migration-input /data/media/0/carrotpilot-fishop-working-params.json --archive

For ESCC evidence, keep the car parked, enable EnableEscc=1 manually only after basic checks pass, then run:
  cd /data/openpilot
  python3 scripts/personal/collect_real_car_evidence.py --sample-seconds 20 --archive

Do not treat this test install as stable until the evidence readiness report and road-test evidence check pass.
EOF
    mv "$tmp" "$path"
  fi
}

run_commissioning() {
  [ "$RUN_COMMISSIONING" = "1" ] || return 0
  script="$INSTALL_DIR/scripts/personal/c3_commissioning.py"
  if [ ! -f "$script" ] && [ "$DRY_RUN" = "0" ]; then
    die "commissioning script not found: $script"
  fi
  run sh -c "cd '$INSTALL_DIR' && python3 scripts/personal/c3_commissioning.py --archive"
}

main() {
  parse_args "$@"

  log "$PROJECT_NAME installer"
  log "repo: $REPO_URL"
  log "ref: $REF"
  log "install dir: $INSTALL_DIR"

  arch=$(uname -m 2>/dev/null || printf unknown)
  if [ "$arch" != "aarch64" ] && [ "$FORCE" != "1" ] && [ "$DRY_RUN" != "1" ]; then
    die "this installer is intended for a C3/aarch64 device; pass --force only if you know why"
  fi

  safe_path_check "$INSTALL_DIR" "install dir"
  safe_path_check "$TMP_DIR" "tmp dir"
  safe_path_check "$BACKUP_ROOT" "backup root"
  if [ "$WRITE_FIRST_BOOT_NOTE" = "1" ]; then
    safe_path_check "$FIRST_BOOT_NOTE" "first boot note"
  fi

  need_cmd git
  need_cmd date
  need_cmd dirname
  need_cmd mkdir
  need_cmd mv
  need_cmd rm
  need_cmd chmod

  timestamp=$(date +%Y%m%d-%H%M%S)
  backup_dir="$BACKUP_ROOT/openpilot-$timestamp"

  if [ -e "$TMP_DIR" ]; then
    run rm -rf "$TMP_DIR"
  fi

  run mkdir -p "$BACKUP_ROOT"
  run git clone --depth 1 --branch "$REF" "$REPO_URL" "$TMP_DIR"

  if [ "$DRY_RUN" = "0" ]; then
    git -C "$TMP_DIR" rev-parse --short HEAD
  else
    log "+ git -C $TMP_DIR rev-parse --short HEAD"
  fi

  if [ -f "$TMP_DIR/launch_openpilot.sh" ]; then
    run chmod +x "$TMP_DIR/launch_openpilot.sh"
  fi

  if [ -e "$INSTALL_DIR" ]; then
    run mv "$INSTALL_DIR" "$backup_dir"
    log "backup: $backup_dir"
  fi

  run mv "$TMP_DIR" "$INSTALL_DIR"

  if [ "$UPDATE_CONTINUE" = "1" ]; then
    write_continue_script
  fi

  apply_safe_params
  write_first_boot_note
  run_commissioning

  log "Install finished."
  log "Keep EnableEscc=0 for first boot/static checks, then enable it manually after basic checks pass."
  if [ "$WRITE_FIRST_BOOT_NOTE" = "1" ]; then
    log "First-boot note: $FIRST_BOOT_NOTE"
  fi
}

main "$@"
