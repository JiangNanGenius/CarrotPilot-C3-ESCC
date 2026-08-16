#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

source "$DIR/launch_env.sh"

function agnos_init {
  # TODO: move this to agnos
  sudo rm -f /data/etc/NetworkManager/system-connections/*.nmmeta

  # set success flag for current boot slot
  sudo abctl --set_success

  # TODO: do this without udev in AGNOS
  # udev does this, but sometimes we startup faster
  sudo chgrp gpu /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0
  sudo chmod 660 /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0

  # Check if AGNOS update is required
  if [ $(< /VERSION) != "$AGNOS_VERSION" ]; then
    AGNOS_PY="$DIR/system/hardware/tici/agnos.py"
    MANIFEST="$DIR/system/hardware/tici/agnos.json"
    if $AGNOS_PY --verify $MANIFEST; then
      sudo reboot
    fi
    $DIR/system/hardware/tici/updater $AGNOS_PY $MANIFEST
  fi
}

function launch {
  # Remove orphaned git lock if it exists on boot
  [ -f "$DIR/.git/index.lock" ] && rm -f $DIR/.git/index.lock

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
    agnos_init
  fi

  # write tmux scrollback to a file
  tmux capture-pane -pq -S-1000 > /tmp/launch_log

  # ===== DIAGNOSTIC BUILD: dump device truth, open SSH, do NOT start openpilot =====
  DIAG=/data/diag_dump
  mkdir -p "$DIAG" 2>/dev/null
  {
    echo "===== CLONE C3 DIAGNOSTIC DUMP $(date 2>/dev/null) ====="
    echo "--- uname ---"; uname -a
    echo "--- /proc/version ---"; cat /proc/version 2>/dev/null
    echo "--- AGNOS /VERSION ---"; cat /VERSION 2>/dev/null
    echo "--- model ---"; tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null; echo
    echo "--- compatible ---"; tr -d '\0' < /sys/firmware/devicetree/base/compatible 2>/dev/null; echo
  } > "$DIAG/00_core.txt" 2>&1

  # full device tree dump
  ( cd /sys/firmware/devicetree/base 2>/dev/null && find . -type f 2>/dev/null | sort ) > "$DIAG/01_devicetree_files.txt" 2>&1
  ( cd /proc/device-tree 2>/dev/null && find . 2>/dev/null | sort ) > "$DIAG/02_procdt_tree.txt" 2>&1
  # key device tree values
  for f in $(cd /proc/device-tree 2>/dev/null && find . -type f \( -name 'model' -o -name 'compatible' -o -name 'name' \) 2>/dev/null | head -200); do
    echo "== $f =="; tr -d '\0' < "/proc/device-tree/$f" 2>/dev/null; echo
  done > "$DIAG/03_devicetree_values.txt" 2>&1

  lsmod > "$DIAG/04_lsmod.txt" 2>&1
  dmesg > "$DIAG/05_dmesg.txt" 2>&1
  cat /proc/cpuinfo > "$DIAG/06_cpuinfo.txt" 2>&1
  ls -la /sys/class/ > "$DIAG/07_sysfs_class.txt" 2>&1
  ls -la /dev/ > "$DIAG/08_dev.txt" 2>&1
  cat /proc/partitions > "$DIAG/09_partitions.txt" 2>&1
  ( abctl --boot_slot 2>/dev/null; echo; abctl --slot_info 2>/dev/null ) > "$DIAG/10_ab_slot.txt" 2>&1
  cat /proc/mounts > "$DIAG/11_mounts.txt" 2>&1

  # open SSH with known password so we can pull the dump over LAN
  (
    if command -v chpasswd >/dev/null 2>&1; then
      printf "comma:test123456\nroot:test123456\n" | chpasswd >/dev/null 2>&1
    fi
    if [ -f /etc/ssh/sshd_config ]; then
      sed -i -E 's/^#?PasswordAuthentication.*/PasswordAuthentication yes/; s/^#?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config >/dev/null 2>&1
    fi
    ( systemctl restart ssh sshd >/dev/null 2>&1 || service ssh restart >/dev/null 2>&1 || /usr/sbin/sshd >/dev/null 2>&1 )
  ) &

  echo "DIAG BUILD: dump at $DIAG, SSH root/comma = test123456. NOT starting openpilot." > /tmp/launch_log
  # Hold the system (do not exec manager) so SSH stays reachable
  while true; do sleep 5; done


  # if broken, keep on screen error
  while true; do sleep 1; done
}

launch
