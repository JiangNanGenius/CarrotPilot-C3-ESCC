"""Install exception handler for process crash."""
import os
import traceback
from datetime import datetime
from enum import Enum

from openpilot.common.params import Params
from openpilot.system.athena.registration import UNREGISTERED_DONGLE_ID
from openpilot.system.hardware.hw import Paths
from openpilot.common.swaglog import cloudlog

CRASHES_DIR = Paths.crash_log_root()


class SentryProject(Enum):
  # python project
  SELFDRIVE = ""
  # native project
  SELFDRIVE_NATIVE = SELFDRIVE


def report_tombstone(fn: str, message: str, contents: str) -> None:
  cloudlog.error({'tombstone': message})


def capture_exception(*args, **kwargs) -> None:
  cloudlog.error("crash", exc_info=kwargs.get('exc_info', 1))

  try:
    save_exception(traceback.format_exc())
  except Exception:
    cloudlog.exception("sentry exception")


def save_exception(content: str) -> None:
  try:
    if not os.path.exists(CRASHES_DIR):
      os.makedirs(CRASHES_DIR)

    files = [
      os.path.join(CRASHES_DIR, datetime.now().strftime("%Y-%m-%d--%H-%M-%S.log")),
      os.path.join(CRASHES_DIR, "error.log")
    ]

    for fn in files:
      with open(fn, 'w') as f:
        if fn == "error.log":
          lines = content.splitlines()[-3:]
          f.write("\n".join(lines))
        else:
          f.write(content)

    cloudlog.error(f"logged crash to {files}")
  except Exception:
    cloudlog.exception("error when attempting to save exception")


def capture_fingerprint_mock() -> None:
  try:
    cloudlog.error("car doesn't match any fingerprints")
  except Exception as e:
    cloudlog.exception(f"sentry fingerprint MOCK exception: {e}")


def capture_fingerprint(candidate: str, car_name: str) -> None:
  try:
    cloudlog.info(f"Fingerprinted {candidate}")
  except Exception as e:
    cloudlog.exception(f"sentry fingerprint exception: {e}")


def set_tag(key: str, value: str) -> None:
  # sentry_sdk reporting disabled for offline builds
  pass


def set_user() -> None:
  # sentry_sdk reporting disabled for offline builds
  pass


def get_properties() -> tuple[str, str]:
  params = Params()
  hardware_serial: str = params.get("HardwareSerial") or ""
  git_username: str = params.get("GithubUsername") or ""
  dongle_id: str = params.get("DongleId") or f"{UNREGISTERED_DONGLE_ID}-{hardware_serial}"

  return dongle_id, git_username


def init(project: SentryProject) -> bool:
  # sentry_sdk reporting disabled for offline builds
  return False
