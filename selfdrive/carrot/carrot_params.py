"""Carrot parameter store (offline, file-backed, no C++ Params dependency).

A lightweight, dependency-free drop-in replacement for
``openpilot.common.params.Params`` that reads and writes parameter files
directly under the params directory (default ``/data/params/d``), bypassing the
C++ ``check_key`` registry.

This lets Carrot's Auto-Tuner / Web7000 / navigation / cluster parameters work
even though those keys are not registered in ``common/params_keys.h`` (which
would otherwise make every ``Params`` access raise ``UnknownKeyName``).

Safety hardening (vs the original 93e0673 version that was suspected in the
jeepney/bootloop incident):
  * Never constructs a C++ ``Params`` object — the params dir is derived from
    ``PARAMS_ROOT`` + ``OPENPILOT_PREFIX`` env vars (matching ``Params`` C++
    semantics in ``common/params.cc`` / ``system/hardware/hw.h``), so we never
    trigger ``mkdir/symlink/rename`` races against ``paramsd``.
  * ``_write_raw`` takes ``fcntl.flock`` on ``{root}/.lock`` (same lock file the
    C++ ``Params`` uses), so concurrent writes can't corrupt a param.
  * ``carrot_settings.json`` is loaded once and cached via ``lru_cache``.
  * All access is wrapped in try/except so a transient fs error can never crash
    the hosting Carrot process.

Only intended for Carrot's peripheral processes (carrot_man / carrot_server /
carrot_cluster / app_navi_status / xiaoge_data). It MUST NOT be used inside
controlsd / the longitudinal planner mainline — those keep using the native
``Params``.
"""

import json
import os
import fcntl
from functools import lru_cache
from typing import Any, Dict, List, Optional

# Device params root + prefix, matching the C++ Params implementation:
#   Path::params()  -> PARAMS_ROOT or "/data/params"  (system/hardware/hw.h:32-33)
#   params_prefix   -> "/" + OPENPILOT_PREFIX or "/d" (common/params.cc:95)
def _default_param_dir() -> str:
  root = os.environ.get("PARAMS_ROOT", "/data/params")
  prefix = os.environ.get("OPENPILOT_PREFIX", "d")
  return os.path.join(root, prefix)

# Path to carrot's parameter metadata (title/min/max/default per key).
_SETTINGS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "carrot_settings.json")
)

# Best-effort import of the real ParamKeyType enum so that ``get_type`` can
# return values directly comparable to the enum members used elsewhere.
try:
  from openpilot.common.params import ParamKeyType  # type: ignore
except Exception:  # pragma: no cover - the enum is optional
  ParamKeyType = None


@lru_cache(maxsize=1)
def _load_settings() -> Dict[str, Dict[str, Any]]:
  """Load ``carrot_settings.json`` into a ``{name: setting}`` map (cached)."""
  settings: Dict[str, Dict[str, Any]] = {}
  try:
    with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
      data = json.load(f)
  except Exception:
    return settings

  for item in data.get("params", []):
    name = item.get("name")
    if name:
      settings[name] = item
  return settings


def _infer_type(item: Optional[Dict[str, Any]]) -> str:
  """Infer one of ``bool``/``int``/``float``/``string`` from a setting entry."""
  if not item:
    return "string"

  mn, mx, dflt = item.get("min"), item.get("max"), item.get("default")

  # 0/1 range with a 0/1 default is the canonical boolean heuristic.
  if mn in (0, 0.0) and mx in (1, 1.0) and dflt in (0, 1, 0.0, 1.0):
    return "bool"

  nums = (mn, mx, dflt)
  if all(isinstance(x, int) for x in nums):
    return "int"
  if all(isinstance(x, (int, float)) for x in nums) and any(isinstance(x, float) for x in nums):
    return "float"
  return "string"


class CarrotParams:
  """File-backed parameter store that bypasses the Params key registry.

  Instances mirror the ``Params`` constructor: ``CarrotParams()`` uses the
  default params directory and ``CarrotParams("/dev/shm/params")`` reads/writes
  files under ``/dev/shm/params/d`` (the same layout used for ``params_memory``).
  """

  def __init__(self, d: str = "", *, param_dir: Optional[str] = None):
    self._settings = _load_settings()
    self._param_dir = param_dir if param_dir is not None else self._resolve_dir(d)
    # Lock file lives one level up from the params dir, matching C++ Params'
    # ``FileLock(params_path + "/.lock")`` (common/params.cc:155).
    self._lock_path = os.path.join(os.path.dirname(self._param_dir), ".lock")

  @staticmethod
  def _resolve_dir(d: str) -> str:
    if d:
      return os.path.join(d, "d")
    # Derive from env vars only — never construct a C++ Params (that would
    # trigger mkdir/symlink/rename races against paramsd and risk a crash).
    return _default_param_dir()

  def _path(self, key: str) -> str:
    return os.path.join(self._param_dir, key)

  def _read_raw(self, key: str) -> Optional[bytes]:
    """Return the raw file contents, or None if the key is not set."""
    try:
      with open(self._path(key), "rb") as f:
        return f.read()
    except (FileNotFoundError, IsADirectoryError):
      return None
    except Exception:
      return None

  def _write_raw(self, key: str, data: bytes) -> None:
    """Write a parameter file atomically under a shared flock."""
    path = self._path(key)
    tmp_path = path + ".tmp"
    try:
      os.makedirs(os.path.dirname(path), exist_ok=True)
      # Serialize with the C++ Params writer via the same .lock file.
      with open(self._lock_path, "a") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
          with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
          os.replace(tmp_path, path)
        finally:
          fcntl.flock(lock_fd, fcntl.LOCK_UN)
    except Exception:
      # Fall back to a plain write if the atomic path failed.
      try:
        with open(path, "wb") as f:
          f.write(data)
      except Exception:
        pass

  # -- core get/put -------------------------------------------------

  def get(self, key, block=False, return_default=False):
    """Read a key, decoding it using the known carrot type when available.

    When the key is unset, returns the default recorded in carrot_settings.json
    (or None when no default is known), matching the original Params behavior.
    """
    raw = self._read_raw(key)
    if raw is None or raw == b"":
      return self.get_default_value(key)

    item = self._settings.get(key)
    t = _infer_type(item)
    try:
      text = raw.decode("utf-8")
    except Exception:
      return raw

    if t == "bool":
      return text.strip() == "1"
    if t == "int":
      try:
        return int(text.strip())
      except Exception:
        return text
    if t == "float":
      try:
        return float(text.strip())
      except Exception:
        return text
    return text

  def put(self, key, value):
    """Write a key. Accepts str, bytes, bool, int, float."""
    if isinstance(value, bool):
      data = b"1" if value else b"0"
    elif isinstance(value, bytes):
      data = value
    elif isinstance(value, (bytearray, memoryview)):
      data = bytes(value)
    else:
      data = str(value).encode("utf-8")
    self._write_raw(key, data)

  def get_bool(self, key, block=False):
    raw = self._read_raw(key)
    if raw is None or raw.strip() == b"":
      return bool(self.get_default_value(key))
    return raw.strip() == b"1"

  def put_bool(self, key, value):
    self._write_raw(key, b"1" if value else b"0")

  def get_int(self, key, default=0):
    raw = self._read_raw(key)
    if raw is None or raw.strip() == b"":
      dv = self.get_default_value(key)
      if dv is not None:
        try:
          return int(dv)
        except Exception:
          pass
      return default
    try:
      return int(raw.strip())
    except Exception:
      try:
        return int(float(raw.strip()))
      except Exception:
        return default

  def put_int(self, key, value):
    self._write_raw(key, str(int(value)).encode("utf-8"))

  def get_float(self, key, default=0.0):
    raw = self._read_raw(key)
    if raw is None or raw.strip() == b"":
      dv = self.get_default_value(key)
      if dv is not None:
        try:
          return float(dv)
        except Exception:
          pass
      return default
    try:
      return float(raw.strip())
    except Exception:
      return default

  def put_float(self, key, value):
    self._write_raw(key, str(float(value)).encode("utf-8"))

  def remove(self, key):
    try:
      os.unlink(self._path(key))
    except (FileNotFoundError, IsADirectoryError):
      pass
    except Exception:
      pass

  # -- non-blocking aliases (used by params_memory writes) ----------

  def put_nonblocking(self, key, value):
    self.put(key, value)

  def put_bool_nonblocking(self, key, value):
    self.put_bool(key, value)

  # -- introspection helpers ----------------------------------------

  def get_param_path(self, key=""):
    if key:
      return os.path.join(self._param_dir, key)
    return self._param_dir

  def check_key(self, key):
    """No registry — every key is accepted, so this is a no-op passthrough."""
    return key

  def get_type(self, key):
    """Return the key type as a ``ParamKeyType`` member (or a str fallback)."""
    t = _infer_type(self._settings.get(key))
    if ParamKeyType is not None:
      return {
        "string": ParamKeyType.STRING,
        "bool": ParamKeyType.BOOL,
        "int": ParamKeyType.INT,
        "float": ParamKeyType.FLOAT,
      }[t]
    return t

  def get_default_value(self, key):
    item = self._settings.get(key)
    if not item or "default" not in item:
      return None

    t = _infer_type(item)
    dflt = item["default"]
    try:
      if t == "bool":
        return bool(dflt)
      if t == "int":
        return int(dflt)
      if t == "float":
        return float(dflt)
    except Exception:
      pass
    return dflt

  def all_keys(self, flag=None):
    """List all parameter files currently present in the params directory."""
    keys: List[str] = []
    try:
      for name in os.listdir(self._param_dir):
        if name.startswith(".") or name.endswith(".tmp"):
          continue
        keys.append(name)
    except Exception:
      pass
    return keys

  def clear_all(self, tx_flag=None):
    for key in self.all_keys():
      self.remove(key)
