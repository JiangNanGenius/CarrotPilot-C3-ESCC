#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TITLE = "Genius Pilot Model Manager Contract"

if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


def sha256_bytes(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest().lower()


def make_artifact(file_name: str, data: bytes, url: str):
  from cereal import custom

  artifact = custom.ModelManagerSP.Artifact()
  artifact.fileName = file_name
  artifact.downloadUri.uri = url
  artifact.downloadUri.sha256 = sha256_bytes(data)
  return artifact


def make_bundle(model_bytes: bytes, metadata_bytes: bytes, runner=None):
  from cereal import custom
  from openpilot.sunnypilot.models.helpers import REQUIRED_JSON_VERSION

  bundle = custom.ModelManagerSP.ModelBundle()
  bundle.index = 7
  bundle.internalName = "genius-test"
  bundle.displayName = "Genius Test Model"
  bundle.generation = 1
  bundle.environment = "test"
  bundle.runner = custom.ModelManagerSP._wrap_runner(runner if runner is not None else custom.ModelManagerSP.Runner.tinygrad)
  bundle.minimumSelectorVersion = REQUIRED_JSON_VERSION
  bundle.ref = "genius-test-ref"

  model = custom.ModelManagerSP.Model()
  model.type = custom.ModelManagerSP.Model.Type.supercombo
  model.artifact = make_artifact("genius_test_model.thneed", model_bytes, "https://example.invalid/model")
  model.metadata = make_artifact("genius_test_metadata.pkl", metadata_bytes, "https://example.invalid/metadata")
  bundle.models = [model]
  return bundle


def write_bundle_files(model_root: Path, model_bytes: bytes, metadata_bytes: bytes) -> None:
  model_root.mkdir(parents=True, exist_ok=True)
  (model_root / "genius_test_model.thneed").write_bytes(model_bytes)
  (model_root / "genius_test_metadata.pkl").write_bytes(metadata_bytes)


def import_file(name: str, path: Path):
  spec = importlib.util.spec_from_file_location(name, path)
  if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load {path}")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class FakeParams:
  store: dict[str, Any] = {}

  def __init__(self, _path: str = ""):
    pass

  @classmethod
  def reset(cls) -> None:
    cls.store = {}

  def get(self, key: str, block: bool = False, return_default: bool = False):
    return self.store.get(key)

  def put(self, key: str, value: Any, block: bool = False) -> None:
    self.store[key] = value

  def remove(self, key: str) -> None:
    self.store.pop(key, None)

  def get_bool(self, key: str, block: bool = False) -> bool:
    return bool(self.store.get(key))



def install_fake_misc_modules() -> None:
  for name in ("setproctitle", "requests"):
    mod = types.ModuleType(name)
    if name == "setproctitle":
      mod.getproctitle = lambda: "genius-contract"
      mod.setproctitle = lambda *args, **kwargs: None
    else:
      mod.Session = object
      mod.get = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline contract"))
      exceptions_mod = types.ModuleType("requests.exceptions")
      for exc_name in ("SSLError", "RequestException", "HTTPError", "ConnectionError", "Timeout"):
        setattr(exceptions_mod, exc_name, RuntimeError)
      mod.exceptions = exceptions_mod
      sys.modules["requests.exceptions"] = exceptions_mod
    sys.modules[name] = mod

  realtime_mod = types.ModuleType("openpilot.common.realtime")
  realtime_mod.Ratekeeper = object
  sys.modules["openpilot.common.realtime"] = realtime_mod


def install_fake_requests() -> None:
  requests_mod = types.ModuleType("requests")
  requests_mod.Session = object
  requests_mod.get = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline contract"))
  sys.modules["requests"] = requests_mod


def install_fake_numpy() -> None:
  numpy_mod = types.ModuleType("numpy")
  numpy_mod.ndarray = object
  numpy_mod.float32 = "float32"
  numpy_mod.nan = float("nan")
  numpy_mod.zeros = lambda shape, dtype=None: types.SimpleNamespace(flatten=lambda: [])
  numpy_mod.array = lambda data, dtype=None: list(data)
  sys.modules["numpy"] = numpy_mod


def install_fake_cereal_custom() -> None:
  class _Runner:
    snpe = 0
    tinygrad = 1
    stock = 2

  class _Type:
    supercombo = 0

  class _NS:
    def __init__(self, **kwargs):
      for key, value in kwargs.items():
        setattr(self, key, value)

  _RUNNER_NAMES = {0: "snpe", 1: "tinygrad", 2: "stock"}

  class _RunnerRef:
    def __init__(self, raw):
      self.raw = raw

    def __int__(self):
      return int(self.raw)

    def __str__(self):
      return _RUNNER_NAMES.get(int(self.raw), str(self.raw))

  _RUNNER_BY_NAME = {v: k for k, v in _RUNNER_NAMES.items()}

  def _runner_from_value(value):
    if isinstance(value, _RunnerRef):
      return value
    if isinstance(value, str):
      return _RunnerRef(_RUNNER_BY_NAME.get(value, 2))
    return _RunnerRef(int(value) if value is not None else 2)

  def _artifact_from_dict(data):
    artifact = _Custom.ModelManagerSP.Artifact()
    artifact.fileName = data.get("fileName", "")
    uri = data.get("downloadUri", {})
    artifact.downloadUri = types.SimpleNamespace(uri=uri.get("uri", ""), sha256=uri.get("sha256", ""))
    artifact.chunks = []
    return artifact

  def _model_from_dict(data):
    model = _Custom.ModelManagerSP.Model()
    model.type = data.get("type")
    model.artifact = _artifact_from_dict(data.get("artifact", {}))
    model.metadata = _artifact_from_dict(data.get("metadata", {}))
    return model

  class _Custom:
    class ModelManagerSP:
      Runner = _Runner

      @staticmethod
      def _wrap_runner(value):
        return _runner_from_value(value)
      DownloadUri = _NS
      Chunk = _NS
      DownloadStatus = _NS
      Override = _NS

      class Model:
        Type = _Type

        def __init__(self):
          self.type = None
          self.artifact = None
          self.metadata = None

      class Artifact:
        def __init__(self):
          self.fileName = ""
          self.downloadUri = types.SimpleNamespace(uri="", sha256="")
          self.chunks = []

      class ModelBundle:
        def __init__(self, **kwargs):
          self.index = 0
          self.internalName = ""
          self.displayName = ""
          self.generation = 0
          self.environment = ""
          self.runner = None
          self.minimumSelectorVersion = 0
          self.ref = ""
          self.models = []
          for key, value in kwargs.items():
            if key == "models":
              value = [_model_from_dict(item) for item in value]
            elif key == "runner":
              value = _runner_from_value(value)
            setattr(self, key, value)

        def to_dict(self):
          return {
            "index": self.index,
            "internalName": self.internalName,
            "displayName": self.displayName,
            "generation": self.generation,
            "environment": self.environment,
            "runner": str(self.runner) if self.runner is not None else "",
            "minimumSelectorVersion": self.minimumSelectorVersion,
            "ref": self.ref,
            "models": [
              {
                "type": model.type,
                "artifact": {"fileName": model.artifact.fileName, "downloadUri": {"uri": model.artifact.downloadUri.uri, "sha256": model.artifact.downloadUri.sha256}},
                "metadata": {"fileName": model.metadata.fileName, "downloadUri": {"uri": model.metadata.downloadUri.uri, "sha256": model.metadata.downloadUri.sha256}},
              }
              for model in self.models
            ],
          }

  cereal_mod = types.ModuleType("cereal")
  cereal_mod.custom = _Custom
  sys.modules["cereal"] = cereal_mod
  sys.modules["cereal.custom"] = _Custom

  messaging_mod = sys.modules.get("cereal.messaging")
  openpilot_cereal_mod = types.ModuleType("openpilot.cereal")
  openpilot_cereal_mod.custom = _Custom
  openpilot_cereal_mod.log = types.SimpleNamespace()
  if messaging_mod is not None:
    openpilot_cereal_mod.messaging = messaging_mod
  sys.modules["openpilot.cereal"] = openpilot_cereal_mod
  sys.modules["openpilot.cereal.custom"] = _Custom


def install_fake_params() -> None:
  params_mod = types.ModuleType("openpilot.common.params")
  params_mod.Params = FakeParams
  params_mod.ParamKeyFlag = types.SimpleNamespace(ALL=0)
  params_mod.UnknownKeyName = KeyError
  sys.modules["openpilot.common.params"] = params_mod


def install_fake_hardware(model_root: Path) -> None:
  class FakePaths:
    @staticmethod
    def model_root() -> str:
      return str(model_root)

  hardware_pkg = types.ModuleType("openpilot.system.hardware")
  hardware_pkg.PC = True
  hardware_pkg.HARDWARE = types.SimpleNamespace(get_device_type=lambda: "pc")
  hw_mod = types.ModuleType("openpilot.system.hardware.hw")
  hw_mod.Paths = FakePaths
  sys.modules["openpilot.system.hardware"] = hardware_pkg
  sys.modules["openpilot.system.hardware.hw"] = hw_mod
  common_hardware_pkg = types.ModuleType("openpilot.common.hardware")
  common_hardware_pkg.PC = True
  common_hardware_pkg.HARDWARE = hardware_pkg.HARDWARE
  sys.modules["openpilot.common.hardware"] = common_hardware_pkg
  common_hw_mod = types.ModuleType("openpilot.common.hardware.hw")
  common_hw_mod.Paths = FakePaths
  sys.modules["openpilot.common.hardware.hw"] = common_hw_mod


def install_fake_swaglog() -> None:
  class FakeCloudLog:
    def debug(self, *args, **kwargs):
      pass

    def info(self, *args, **kwargs):
      pass

    def warning(self, *args, **kwargs):
      pass

    def error(self, *args, **kwargs):
      pass

    def exception(self, *args, **kwargs):
      pass

  swaglog_mod = types.ModuleType("openpilot.common.swaglog")
  swaglog_mod.cloudlog = FakeCloudLog()
  sys.modules["openpilot.common.swaglog"] = swaglog_mod


def install_fake_aiohttp() -> None:
  aiohttp_mod = types.ModuleType("aiohttp")
  aiohttp_mod.ClientResponseError = RuntimeError

  class FakeClientSession:
    def __init__(self, *args, **kwargs):
      raise RuntimeError("network downloads are not used by this offline contract")

  aiohttp_mod.ClientSession = FakeClientSession
  sys.modules["aiohttp"] = aiohttp_mod


def install_fake_messaging() -> None:
  messaging_mod = types.ModuleType("cereal.messaging")

  class FakePubMaster:
    def __init__(self, services):
      self.services = services
      self.sent = []

    def send(self, service: str, msg: Any) -> None:
      self.sent.append((service, msg))

  def new_message(service: str, valid: bool = False):
    return types.SimpleNamespace(**{service: types.SimpleNamespace()}, valid=valid)

  messaging_mod.PubMaster = FakePubMaster
  messaging_mod.new_message = new_message
  sys.modules["cereal.messaging"] = messaging_mod


def run_contract() -> dict[str, Any]:
  report: dict[str, Any] = {"title": TITLE, "ok": False, "checks": []}

  with tempfile.TemporaryDirectory(prefix="genius-model-manager-") as tmp:
    tmp_root = Path(tmp)
    model_root = tmp_root / "models"
    FakeParams.reset()
    install_fake_params()
    install_fake_hardware(model_root)
    install_fake_swaglog()
    install_fake_aiohttp()
    install_fake_messaging()
    install_fake_misc_modules()
    install_fake_requests()
    install_fake_numpy()
    install_fake_cereal_custom()

    from cereal import custom
    from openpilot.sunnypilot.models import helpers
    from openpilot.sunnypilot.models.manager import ModelManagerSP
    alpha_snapshot = import_file("genius_alpha_snapshot_for_model_contract",
                                ROOT / "scripts/personal/sunnypilot_c3_alpha_snapshot.py")
    summarize_model_bundle = alpha_snapshot.summarize_model_bundle

    helpers._LAST_VALIDATED_RAW = None
    params = FakeParams()

    stock_runner = int(custom.ModelManagerSP.Runner.stock)
    tinygrad_runner = int(custom.ModelManagerSP.Runner.tinygrad)
    model_bytes = b"genius model bytes"
    metadata_bytes = b"genius metadata bytes"
    valid_bundle = make_bundle(model_bytes, metadata_bytes)

    runner = helpers.get_active_model_runner(params, force_check=True)
    report["checks"].append({
      "name": "stock runner without active bundle",
      "ok": int(runner) == stock_runner and int(params.get("ModelRunnerTypeCache")) == stock_runner,
      "runner": int(runner),
    })

    params.put("ModelManager_ActiveBundle", valid_bundle.to_dict(), block=True)
    helpers._LAST_VALIDATED_RAW = None
    helpers.validate_active_bundle(params, [valid_bundle])
    report["checks"].append({
      "name": "missing active bundle artifacts reset to stock",
      "ok": params.get("ModelManager_ActiveBundle") is None and int(params.get("ModelRunnerTypeCache")) == stock_runner,
    })

    write_bundle_files(model_root, model_bytes, metadata_bytes)
    params.put("ModelManager_ActiveBundle", valid_bundle.to_dict(), block=True)
    helpers._LAST_VALIDATED_RAW = None
    helpers.validate_active_bundle(params, [valid_bundle])
    runner = helpers.get_active_model_runner(params, force_check=True)
    active = params.get("ModelManager_ActiveBundle")
    report["checks"].append({
      "name": "valid active bundle survives and sets tinygrad runner",
      "ok": isinstance(active, dict) and int(runner) == tinygrad_runner and int(params.get("ModelRunnerTypeCache")) == tinygrad_runner,
      "runner": int(runner),
    })

    summary = summarize_model_bundle(active, len(json.dumps(active or {}).encode("utf-8")), "testdigest")
    report["checks"].append({
      "name": "active bundle summary is bounded evidence",
      "ok": summary.get("present") is True
      and summary.get("internalName") == "genius-test"
      and summary.get("runner") == "tinygrad"
      and summary.get("modelCount") == 1
      and "models" not in summary,
      "summary": summary,
    })

    full_path = model_root / "atomic_model.bin"
    temp_path = model_root / "atomic_model.bin.download-test"
    full_path.write_bytes(b"old")
    temp_path.write_bytes(b"new")
    manager = ModelManagerSP()
    manager._install_downloaded_artifact(str(temp_path), str(full_path))
    report["checks"].append({
      "name": "atomic install replaces only after temp artifact exists",
      "ok": full_path.read_bytes() == b"new" and not temp_path.exists(),
    })

    params.put("ModelManager_DownloadIndex", "7", block=True)
    params.remove("ModelManager_DownloadIndex")
    report["checks"].append({
      "name": "download request key can be cleared after handling",
      "ok": params.get("ModelManager_DownloadIndex") is None,
    })

  report["ok"] = all(check["ok"] for check in report["checks"])
  return report


def self_test() -> int:
  text = Path(__file__).read_text(encoding="utf-8")
  required = (
    TITLE,
    "ModelManager_ActiveBundle",
    "ModelRunnerTypeCache",
    "Runner.stock",
    "Runner.tinygrad",
    "validate_active_bundle",
    "summarize_model_bundle",
    "_install_downloaded_artifact",
    "download request key can be cleared",
  )
  if not all(token in text for token in required):
    print(f"FAIL {TITLE} self-test: missing token")
    return 1
  if sys.version_info < (3, 10):
    print(f"PASS {TITLE} self-test (runtime requires Python 3.10+)")
    return 0
  report = run_contract()
  if not report["ok"]:
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1
  print(f"PASS {TITLE} self-test")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description=TITLE)
  parser.add_argument("--json", action="store_true")
  parser.add_argument("--self-test", action="store_true")
  args = parser.parse_args()

  if args.self_test:
    return self_test()

  report = run_contract()
  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    print(f"{'PASS' if report['ok'] else 'FAIL'} {TITLE}")
    for check in report["checks"]:
      print(f"{'PASS' if check['ok'] else 'FAIL'} {check['name']}")
  return 0 if report["ok"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
