import asyncio

from cereal import custom

from openpilot.sunnypilot.models.fetcher import ModelParser
from openpilot.sunnypilot.models.helpers import _bundle_artifacts, _bundle_is_valid_locally, _bundle_signature
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
