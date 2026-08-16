#!/usr/bin/env bash

SP_C3_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
DIR="$( cd "$SP_C3_DIR/../../../../.." >/dev/null 2>&1 && pwd )"

source "$SP_C3_DIR/launch_env.sh"

# --- boot diagnostics: write each milestone so a stuck boot can be localized ---
DBG=/data/launch_debug.log
dbg() { echo "$(date +%H:%M:%S 2>/dev/null) $1" >> "$DBG" 2>/dev/null; }
: > "$DBG" 2>/dev/null
dbg "launch_chffrplus(c3) start, DIR=$DIR MODEL=$(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null)"

# Determine the panda MCU type (F4=DOS, H7=TRES) and set TICI_* env vars.
# Ported from Mr.One's clone-C3 init; uses sunnypilot's bundled `panda` package.
set_tici_hw() {
  grep -qi "tici" /sys/firmware/devicetree/base/model 2>/dev/null || return 0
  export TICI_HW=1
  dbg "set_tici_hw: tici detected"

  local cache="/persist/dp_dev_panda_mcu_type"
  local attempts=15 confirm=3
  local mcu="" count=0 last="" cur cached

  cached=$(cat "$cache" 2>/dev/null)
  case "$cached" in
    F4|H7) mcu="$cached"; dbg "panda MCU $mcu [cached]" ;;
  esac

  if [ -z "$mcu" ]; then
    dbg "querying panda MCU type..."
    for attempt in $(seq 1 "$attempts"); do
      if [ -n "$last" ]; then sleep 1; else sleep 3; fi
      case "$(PYTHONPATH="$DIR" python3 -c "from panda.python import Panda; p = Panda(cli=False); print(p.get_mcu_type()); p.close()" 2>/dev/null)" in
        *McuType.F4*) cur="F4" ;;
        *McuType.H7*) cur="H7" ;;
        *)            cur="" ;;
      esac
      if [ -n "$cur" ] && [ "$cur" = "$last" ]; then count=$((count + 1)); else count=1; last="$cur"; fi
      if [ -n "$cur" ] && [ "$count" -ge "$confirm" ]; then mcu="$cur"; break; fi
      dbg "panda MCU read='${cur:-UNKNOWN}' ($count/$confirm, attempt $attempt/$attempts)"
    done

    if [ -z "$mcu" ]; then
      # Do NOT hard-exit on a clone: unknown MCU must not brick the boot.
      dbg "panda MCU UNKNOWN after $attempts attempts, continuing without TICI_DOS/TRES"
      return 0
    fi

    if sudo mount -o remount,rw /persist 2>/dev/null; then
      echo "$mcu" | sudo tee "$cache" >/dev/null 2>&1
      sudo mount -o remount,ro /persist 2>/dev/null
    fi
  fi

  if [ "$mcu" = "F4" ]; then
    dbg "TICI (DOS/F4) detected"
    mount_nvme
    export TICI_DOS=1
  else
    dbg "TICI (TRES/H7) detected"
    export TICI_TRES=1
  fi
}

mount_nvme() {
  for i in $(seq 1 10); do
    [ -b /dev/nvme0n1p1 ] && break
    sleep 1
  done
  [ -b /dev/nvme0n1p1 ] || return 0
  if ! mountpoint -q /data/media/0/realdata; then
    mount /dev/nvme0n1p1 /data/media/0/realdata 2>/dev/null
  fi
  if mountpoint -q /data/media/0/realdata; then
    chown comma:comma /data/media/0/realdata 2>/dev/null
    chmod 755 /data/media/0/realdata 2>/dev/null
  fi
}

function agnos_init {
  # TODO: move this to agnos
  sudo rm -f /data/etc/NetworkManager/system-connections/*.nmmeta

  # set success flag for current boot slot
  sudo abctl --set_success

  # TODO: do this without udev in AGNOS
  # udev does this, but sometimes we startup faster
  sudo chgrp gpu /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0
  sudo chmod 660 /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0


  if [ $(< /VERSION) != "$AGNOS_VERSION" ]; then
    AGNOS_PY="$DIR/openpilot/common/hardware/comma/agnos.py"
    MANIFEST="$SP_C3_DIR/agnos.json"
    if $AGNOS_PY --verify $MANIFEST; then
      sudo reboot
    fi
    $DIR/openpilot/common/hardware/comma/updater $AGNOS_PY $MANIFEST
  fi
}

function launch {
  # Remove orphaned git lock if it exists on boot
  [ -f "$DIR/.git/index.lock" ] && rm -f $DIR/.git/index.lock

  # Rescue SSH first (background) so a stuck boot stays debuggable over LAN.
  [ -x "$SP_C3_DIR/rescue_ssh.sh" ] && "$SP_C3_DIR/rescue_ssh.sh" >/dev/null 2>&1 &
  dbg "rescue_ssh launched"

  # Check to see if there's a valid overlay-based update available. Conditions
  # are as follows:
  #
  # 1. The DIR init file has to exist, with a newer modtime than anything in
  #    the DIR Git repo. This checks for local development work or the user
  #    switching branches/forks, which should not be overwritten.
  # 2. The FINALIZED consistent file has to exist, indicating there's an update
  #    that completed successfully and synced to disk.

  if [ -f "${DIR}/.overlay_init" ]; then
    find ${DIR}/.git -newer ${DIR}/.overlay_init | grep -q '.' 2> /dev/null
    if [ $? -eq 0 ]; then
      echo "${DIR} has been modified, skipping overlay update installation"
    else
      if [ -f "${STAGING_ROOT}/finalized/.overlay_consistent" ]; then
        if [ ! -d /data/safe_staging/old_openpilot ]; then
          echo "Valid overlay update found, installing"
          LAUNCHER_LOCATION="${BASH_SOURCE[0]}"

          mv $DIR /data/safe_staging/old_openpilot
          mv "${STAGING_ROOT}/finalized" $DIR
          cd $DIR

          echo "Restarting launch script ${LAUNCHER_LOCATION}"
          unset AGNOS_VERSION
          exec "${LAUNCHER_LOCATION}"
        else
          echo "openpilot backup found, not updating"
          # TODO: restore backup? This means the updater didn't start after swapping
        fi
      fi
    fi
  fi

  # handle pythonpath
  ln -sfn $(pwd) /data/pythonpath
  export PYTHONPATH="$PWD"

  # hardware specific init
  if [ -f /AGNOS ]; then
    dbg "AGNOS present, running set_tici_hw + agnos_init"
    set_tici_hw
    agnos_init
    dbg "hw init done"
  fi

  # write tmux scrollback to a file
  tmux capture-pane -pq -S-1000 > /tmp/launch_log

  # start manager
  cd $DIR/system/manager
  if [ ! -f $DIR/prebuilt ]; then
    dbg "no prebuilt, running build.py"
    ./build.py
  fi
  dbg "starting manager.py"
  ./manager.py
  dbg "manager.py exited code=$?"

  # if broken, keep on screen error
  while true; do sleep 1; done
}

launch
