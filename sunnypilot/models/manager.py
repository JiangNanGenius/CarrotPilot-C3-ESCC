"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

import asyncio
import os
import time

import aiohttp
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.system.hardware.hw import Paths

from cereal import messaging, custom
from openpilot.sunnypilot.models.fetcher import ModelFetcher
from openpilot.sunnypilot.models.helpers import get_active_bundle, validate_active_bundle, verify_file


class ModelManagerSP:
  """Manages model downloads and status reporting"""

  def __init__(self):
    self.params = Params()
    self.model_fetcher = ModelFetcher(self.params)
    self.pm = messaging.PubMaster(["modelManagerSP"])
    self.available_models: list[custom.ModelManagerSP.ModelBundle] = []
    self.selected_bundle: custom.ModelManagerSP.ModelBundle = None
    self.active_bundle: custom.ModelManagerSP.ModelBundle = get_active_bundle(self.params)
    self._chunk_size = 128 * 1000  # 128 KB chunks
    self._download_start_times: dict[str, float] = {}  # Track start time per model

  def _sync_artifact_progress(self, source_artifact) -> None:
    """Mirror download progress to all artifacts sharing the same filename in the selected bundle."""
    if not self.selected_bundle:
      return
    for model in self.selected_bundle.models:
      for artifact in (model.artifact, model.metadata):
        if artifact is not source_artifact and artifact.fileName == source_artifact.fileName:
          artifact.downloadProgress.status = source_artifact.downloadProgress.status
          artifact.downloadProgress.progress = source_artifact.downloadProgress.progress
          artifact.downloadProgress.eta = source_artifact.downloadProgress.eta

  @staticmethod
  def _download_temp_path(full_path: str) -> str:
    return f"{full_path}.download-{os.getpid()}-{time.monotonic_ns()}"

  @staticmethod
  def _chunk_artifact_paths(base_path: str) -> list[str]:
    from openpilot.common.file_chunker import get_chunk_name, get_manifest_path
    manifest_path = get_manifest_path(base_path)
    if not os.path.isfile(manifest_path):
      return []

    try:
      with open(manifest_path) as f:
        num_chunks = int(f.read().strip())
    except Exception:
      return [manifest_path]
    return [manifest_path] + [get_chunk_name(base_path, i, num_chunks) for i in range(num_chunks)]

  @staticmethod
  def _remove_chunk_artifacts(base_path: str, keep: set[str] | None = None) -> None:
    directory = os.path.dirname(base_path) or "."
    prefix = f"{os.path.basename(base_path)}.chunk"
    keep = {os.path.abspath(path) for path in (keep or set())}
    if not os.path.isdir(directory):
      return
    for filename in os.listdir(directory):
      path = os.path.join(directory, filename)
      if filename.startswith(prefix) and os.path.abspath(path) not in keep and os.path.isfile(path):
        os.remove(path)

  def _cleanup_download_artifact(self, base_path: str) -> None:
    if os.path.isfile(base_path):
      os.remove(base_path)
    self._remove_chunk_artifacts(base_path)

  def _install_downloaded_artifact(self, temp_path: str, full_path: str) -> None:
    from openpilot.common.file_chunker import get_chunk_name, get_manifest_path
    temp_chunk_paths = self._chunk_artifact_paths(temp_path)
    if not temp_chunk_paths:
      os.replace(temp_path, full_path)
      self._remove_chunk_artifacts(full_path)
      return

    final_manifest = get_manifest_path(full_path)
    final_chunks = [get_chunk_name(full_path, i, len(temp_chunk_paths) - 1) for i in range(len(temp_chunk_paths) - 1)]
    for temp_chunk_path, final_chunk_path in zip(temp_chunk_paths[1:], final_chunks):
      os.replace(temp_chunk_path, final_chunk_path)
    os.replace(temp_chunk_paths[0], final_manifest)
    if os.path.isfile(full_path):
      os.remove(full_path)
    self._remove_chunk_artifacts(full_path, keep={final_manifest, *final_chunks})

  def _calculate_eta(self, filename: str, progress: float) -> int:
    """Calculate ETA based on elapsed time and current progress"""
    if filename not in self._download_start_times or progress <= 0:
      return 60  # Default ETA for new downloads

    elapsed_time = time.monotonic() - self._download_start_times[filename]
    if elapsed_time <= 0:
      return 60

    # If we're at X% after Y seconds, we can estimate total time as (Y / X) * 100
    total_estimated_time = (elapsed_time / progress) * 100
    eta = total_estimated_time - elapsed_time

    return max(1, int(eta))  # Return at least 1 second if download is ongoing

  async def _download_file(self, url: str, path: str, model) -> None:
    """Downloads a file with progress tracking"""
    self._download_start_times[model.fileName] = time.monotonic()

    async with aiohttp.ClientSession() as session:
      async with session.get(url) as response:
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        bytes_downloaded = 0

        with open(path, 'wb') as f:
          async for chunk in response.content.iter_chunked(self._chunk_size):  # type: bytes
            f.write(chunk)
            bytes_downloaded += len(chunk)

            if self.params.get("ModelManager_DownloadIndex") is None:
              raise Exception("Download cancelled")

            if total_size > 0:
              progress = (bytes_downloaded / total_size) * 100
              model.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.downloading
              model.downloadProgress.progress = progress
              model.downloadProgress.eta = self._calculate_eta(model.fileName, progress)
              self._sync_artifact_progress(model)
              self._report_status()

        # Clean up start time after download completes
        del self._download_start_times[model.fileName]

  async def _download_chunked(self, base_url: str, base_path: str, artifact) -> None:
    from openpilot.common.file_chunker import get_manifest_path, get_chunk_name
    manifest_url = get_manifest_path(base_url)
    manifest_path = get_manifest_path(base_path)

    async with aiohttp.ClientSession() as session:
      async with session.get(manifest_url) as resp:
        if resp.status == 404:
          raise FileNotFoundError
        resp.raise_for_status()
        num_chunks = int((await resp.read()).strip())

    self._download_start_times[artifact.fileName] = time.monotonic()

    for i in range(num_chunks):
      chunk_url = get_chunk_name(base_url, i, num_chunks)
      chunk_path = get_chunk_name(base_path, i, num_chunks)
      chunk_downloaded = 0
      async with aiohttp.ClientSession() as session:
        async with session.get(chunk_url) as response:
          response.raise_for_status()
          chunk_size = int(response.headers.get("content-length", 0))
          with open(chunk_path, 'wb') as f:
            async for data in response.content.iter_chunked(self._chunk_size):
              f.write(data)
              chunk_downloaded += len(data)
              if self.params.get("ModelManager_DownloadIndex") is None:
                raise Exception("Download cancelled")
              intra = chunk_downloaded / max(chunk_size, 1)
              progress = min(99, (i + intra) / num_chunks * 100)
              artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.downloading
              artifact.downloadProgress.progress = progress
              artifact.downloadProgress.eta = self._calculate_eta(artifact.fileName, progress)
              self._sync_artifact_progress(artifact)
              self._report_status()

    with open(manifest_path, 'w') as f:
      f.write(str(num_chunks))
    if os.path.isfile(base_path):
      os.remove(base_path)
    del self._download_start_times[artifact.fileName]

  async def _process_artifact(self, artifact, destination_path: str) -> None:
    if not artifact.downloadUri.uri:
      return None

    url = artifact.downloadUri.uri
    expected_hash = artifact.downloadUri.sha256
    filename = artifact.fileName
    full_path = os.path.join(destination_path, filename)
    temp_path = self._download_temp_path(full_path)

    try:
      if await verify_file(full_path, expected_hash):
        artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.cached
        artifact.downloadProgress.progress = 100
        artifact.downloadProgress.eta = 0
        self._sync_artifact_progress(artifact)
        self._report_status()
        return

      try:
        await self._download_chunked(url, temp_path, artifact)
      except (FileNotFoundError, aiohttp.ClientResponseError):
        await self._download_file(url, temp_path, artifact)

      if not await verify_file(temp_path, expected_hash):
        raise ValueError(f"Hash validation failed for {filename}")

      self._install_downloaded_artifact(temp_path, full_path)
      artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.downloaded
      artifact.downloadProgress.progress = 100
      artifact.downloadProgress.eta = 0
      self._sync_artifact_progress(artifact)
      self._report_status()

    except Exception as e:
      cloudlog.error(f"Error downloading {filename}: {str(e)}")
      artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.failed
      artifact.downloadProgress.eta = 0
      self._sync_artifact_progress(artifact)
      if self.selected_bundle:
        self.selected_bundle.status = custom.ModelManagerSP.DownloadStatus.failed
      self._report_status()
      self._download_start_times.pop(artifact.fileName, None)
      raise
    finally:
      self._cleanup_download_artifact(temp_path)

  async def _process_model(self, model, destination_path: str) -> None:
    """Processes a single model download including verification"""
    model_artifact = model.artifact
    metadata_artifact = model.metadata

    await self._process_artifact(metadata_artifact, destination_path)
    await self._process_artifact(model_artifact, destination_path)

  def _report_status(self) -> None:
    """Reports current status through messaging system"""
    msg = messaging.new_message('modelManagerSP', valid=True)
    model_manager_state = msg.modelManagerSP
    if self.selected_bundle:
      model_manager_state.selectedBundle = self.selected_bundle

    if self.active_bundle:
      model_manager_state.activeBundle = self.active_bundle

    model_manager_state.availableBundles = self.available_models
    self.pm.send('modelManagerSP', msg)

  async def _download_bundle(self, model_bundle: custom.ModelManagerSP.ModelBundle, destination_path: str) -> None:
    """Downloads all models in a bundle"""
    self.selected_bundle = model_bundle
    self.selected_bundle.status = custom.ModelManagerSP.DownloadStatus.downloading
    os.makedirs(destination_path, exist_ok=True)

    try:
      seen_artifacts: set[str] = set()
      for model in self.selected_bundle.models:
        for artifact in (model.metadata, model.artifact):
          if not artifact.fileName:
            continue
          if artifact.fileName in seen_artifacts:
            artifact.downloadProgress.status = custom.ModelManagerSP.DownloadStatus.cached
            artifact.downloadProgress.progress = 100
            artifact.downloadProgress.eta = 0
          else:
            seen_artifacts.add(artifact.fileName)
            await self._process_artifact(artifact, destination_path)

      self.active_bundle = self.selected_bundle
      self.active_bundle.status = custom.ModelManagerSP.DownloadStatus.downloaded
      self.params.put("ModelManager_ActiveBundle", self.active_bundle.to_dict(), block=True)
      self.selected_bundle = None

    except Exception:
      self.selected_bundle.status = custom.ModelManagerSP.DownloadStatus.failed
      raise

    finally:
      self._report_status()

  def download(self, model_bundle: custom.ModelManagerSP.ModelBundle, destination_path: str) -> None:
    """Main entry point for downloading a model bundle"""
    asyncio.run(self._download_bundle(model_bundle, destination_path))

  def main_thread(self) -> None:
    """Main thread for model management"""
    rk = Ratekeeper(1, print_delay_threshold=None)

    while True:
      try:
        self.available_models = self.model_fetcher.get_available_bundles()
        validate_active_bundle(self.params, self.available_models)
        self.active_bundle = get_active_bundle(self.params)

        if (index_to_download := self.params.get("ModelManager_DownloadIndex")) is not None:
          if model_to_download := next((model for model in self.available_models if model.index == index_to_download), None):
            try:
              self.download(model_to_download, Paths.model_root())
            except Exception as e:
              cloudlog.exception(e)
            finally:
              self.params.remove("ModelManager_DownloadIndex")
              self.selected_bundle = None

        if self.params.get("ModelManager_ClearCache"):
          self.clear_model_cache()
          self.params.remove("ModelManager_ClearCache")

        self._report_status()
        rk.keep_time()

      except Exception as e:
        cloudlog.exception(f"Error in main thread: {str(e)}")
        rk.keep_time()

  def clear_model_cache(self) -> None:
    """
    Clears the model cache directory of all files except those in the active model bundle.
    """

    # Get list of files used by active model bundle
    active_files = []
    if self.active_bundle is not None: # When the default model is active
      for model in self.active_bundle.models:
        if hasattr(model, 'artifact') and model.artifact.fileName:
          active_files.append(model.artifact.fileName)
        if hasattr(model, 'metadata') and model.metadata.fileName:
          active_files.append(model.metadata.fileName)

    # Remove all files except active ones (including their chunk files)
    model_dir = Paths.model_root()
    try:
      for filename in os.listdir(model_dir):
        base = filename.split('.chunk')[0] if '.chunk' in filename else filename
        if base not in active_files and filename not in active_files:
          file_path = os.path.join(model_dir, filename)
          if os.path.isfile(file_path):
            os.remove(file_path)
      cloudlog.info("Model cache cleared, keeping active model files")
    except Exception as e:
      cloudlog.exception(f"Error clearing model cache: {str(e)}")

def main():
  ModelManagerSP().main_thread()


if __name__ == "__main__":
  main()
