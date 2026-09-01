import asyncio

from cereal import custom

from openpilot.sunnypilot.models.fetcher import ModelParser
from openpilot.sunnypilot.models.helpers import _bundle_artifacts, _bundle_is_valid_locally, _bundle_signature
from openpilot.sunnypilot.models import manager as model_manager_module
from openpilot.sunnypilot.models.manager import ModelManagerSP


def make_bundle(*, generation=12, is_20hz=True):
  return ModelParser._parse_bundle({
    "index": 76,
    "short_name": "TEST20",
    "display_name": "Test v20",
    "generation": generation,
    "environment": "release",
    "runner": "tinygrad",
    "is_20hz": is_20hz,
    "minimum_selector_version": "17",
    "ref": "test-v20-ref",
    "models": [{
      "type": "chunked",
      "artifact": {
        "file_name": "driving_test_v20.pkl",
        "download_uri": {"url": "https://example.invalid/driving_test_v20.pkl", "sha256": "0" * 64},
        "chunks": [
          {"file_name": "declared-part-1.pkl", "sha256": "1" * 64},
          {"file_name": "declared-part-2.pkl", "sha256": "2" * 64},
        ],
      },
    }],
  })


def test_bundle_uses_declared_chunks_and_rejects_empty_bundle():
  bundle = make_bundle()
  assert _bundle_artifacts(bundle) == [
    ("declared-part-1.pkl", "1" * 64),
    ("declared-part-2.pkl", "2" * 64),
  ]

  empty = custom.ModelManagerSP.ModelBundle()
  assert not _bundle_is_valid_locally(empty)


def test_bundle_signature_tracks_runtime_compatibility_fields():
  assert _bundle_signature(make_bundle()) != _bundle_signature(make_bundle(generation=11))
  assert _bundle_signature(make_bundle()) != _bundle_signature(make_bundle(is_20hz=False))


def test_download_reports_zero_percent_before_work_and_commits_runner(tmp_path):
  class FakeParams:
    def __init__(self):
      self.values = {}

    def put(self, key, value, block=False):
      self.values[key] = value

  manager = ModelManagerSP.__new__(ModelManagerSP)
  manager.params = FakeParams()
  manager.selected_bundle = None
  manager.active_bundle = None
  reports = []

  def report_status():
    if manager.selected_bundle is None:
      return

    artifact = manager.selected_bundle.models[0].artifact
    reports.append((manager.selected_bundle.status.raw, artifact.downloadProgress.status.raw,
                    artifact.downloadProgress.progress))

  async def process_artifact(artifact, destination_path):
    assert reports == [(custom.ModelManagerSP.DownloadStatus.downloading,
                        custom.ModelManagerSP.DownloadStatus.downloading, 0.0)]
    artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.downloaded
    artifact.downloadProgress.progress = 100

  manager._report_status = report_status
  manager._process_artifact = process_artifact

  asyncio.run(manager._download_bundle(make_bundle(), str(tmp_path)))

  assert manager.params.values["ModelRunnerTypeCache"] == custom.ModelManagerSP.Runner.tinygrad
  assert manager.params.values["ModelManager_ActiveBundle"]["ref"] == "test-v20-ref"


class _StreamingResponse:
  def __init__(self, chunks, content_length=None):
    self._chunks = chunks
    self.headers = {} if content_length is None else {"content-length": str(content_length)}

  def __enter__(self):
    return self

  def __exit__(self, *_):
    return False

  def raise_for_status(self):
    pass

  def iter_content(self, chunk_size):
    yield from self._chunks


class _DownloadParams:
  def get(self, key):
    return 76 if key == "ModelManager_DownloadIndex" else None


def _manager_for_stream_test(artifact):
  manager = ModelManagerSP.__new__(ModelManagerSP)
  manager.params = _DownloadParams()
  manager.selected_bundle = make_bundle()
  manager.active_bundle = None
  manager._chunk_size = 16
  manager._download_start_times = {}
  reports = []
  manager._sync_artifact_progress = lambda _: None
  manager._report_status = lambda: reports.append((artifact.downloadProgress.status.raw,
                                                    float(artifact.downloadProgress.progress)))
  return manager, reports


def test_unchunked_download_without_content_length_stays_observable(monkeypatch, tmp_path):
  artifact = make_bundle().models[0].artifact
  manager, reports = _manager_for_stream_test(artifact)
  monkeypatch.setattr(model_manager_module.requests, "get",
                      lambda *args, **kwargs: _StreamingResponse([b"abc", b"", b"def"]))

  destination = tmp_path / "model.bin"
  asyncio.run(manager._download_file("https://example.invalid/model.bin", str(destination), artifact))

  assert destination.read_bytes() == b"abcdef"
  assert reports == [
    (custom.ModelManagerSP.DownloadStatus.downloading, 0.0),
    (custom.ModelManagerSP.DownloadStatus.downloading, 0.0),
  ]


def test_chunked_download_without_content_length_advances_on_completed_chunks(monkeypatch, tmp_path):
  artifact = make_bundle().models[0].artifact
  manager, reports = _manager_for_stream_test(artifact)

  class FakeSession:
    def __enter__(self):
      return self

    def __exit__(self, *_):
      return False

    def get(self, *args, **kwargs):
      return _StreamingResponse([b"chunk"])

  monkeypatch.setattr(model_manager_module.requests, "Session", FakeSession)
  base_path = tmp_path / artifact.fileName
  asyncio.run(manager._download_chunked("https://example.invalid/model", str(base_path), artifact))

  assert reports == [
    (custom.ModelManagerSP.DownloadStatus.downloading, 0.0),
    (custom.ModelManagerSP.DownloadStatus.downloading, 50.0),
    (custom.ModelManagerSP.DownloadStatus.downloading, 50.0),
    (custom.ModelManagerSP.DownloadStatus.downloading, 99.0),
  ]
  assert (tmp_path / f"{artifact.fileName}.chunkmanifest").read_text() == "2"
