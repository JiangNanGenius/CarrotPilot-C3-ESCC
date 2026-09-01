"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

import time
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError, RequestException, SSLError
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.models.helpers import is_bundle_version_compatible

from cereal import custom


OFFLINE = False

# The manager polls once a second. An expired catalog must not turn a temporary
# loss of connectivity into one blocking HTTP request (and one warning) per
# poll. Keep retries responsive at first, then settle at five minutes; the
# settings "Refresh Model List" action still bypasses an active backoff.
FETCH_RETRY_INITIAL_SECONDS = 30.0
FETCH_RETRY_MAX_SECONDS = 5 * 60.0


class ModelParser:
  """Handles parsing of model data into cereal objects"""

  @staticmethod
  def _parse_download_uri(download_uri_data) -> custom.ModelManagerSP.DownloadUri:
    download_uri = custom.ModelManagerSP.DownloadUri()
    download_uri.uri = download_uri_data.get("url")
    download_uri.sha256 = download_uri_data.get("sha256")
    return download_uri

  @staticmethod
  def _parse_chunk(chunk_data) -> custom.ModelManagerSP.Chunk:
    chunk = custom.ModelManagerSP.Chunk()
    chunk.fileName = chunk_data.get("file_name")
    chunk.sha256 = chunk_data.get("sha256")
    return chunk

  @staticmethod
  def _parse_artifact(artifact_data) -> custom.ModelManagerSP.Artifact:
    artifact = custom.ModelManagerSP.Artifact()
    artifact.fileName = artifact_data.get("file_name")
    artifact.downloadUri = ModelParser._parse_download_uri(artifact_data.get("download_uri", {}))

    if "chunks" in artifact_data:
      artifact.chunks = [ModelParser._parse_chunk(chunk_data) for chunk_data in artifact_data["chunks"]]

    return artifact

  @staticmethod
  def _parse_model(model_data) -> custom.ModelManagerSP.Model:
    model = custom.ModelManagerSP.Model()

    model.type = model_data.get("type")
    model.artifact = ModelParser._parse_artifact(model_data.get("artifact", {}))
    if metadata := model_data.get("metadata"):
      model.metadata = ModelParser._parse_artifact(metadata)
    return model

  @staticmethod
  def _parse_overrides(overrides_data: dict[str, str]) -> list[custom.ModelManagerSP.Override]:
    overrides = []
    for key, value in overrides_data.items():
      override = custom.ModelManagerSP.Override()
      override.key = key
      override.value = value
      overrides.append(override)
    return overrides

  @staticmethod
  def _parse_bundle(bundle) -> custom.ModelManagerSP.ModelBundle:
    model_bundle = custom.ModelManagerSP.ModelBundle()
    model_bundle.index = int(bundle["index"])
    model_bundle.internalName = bundle["short_name"]
    model_bundle.displayName = bundle["display_name"]
    model_bundle.models = [ModelParser._parse_model(model) for model in bundle.get("models",[])]
    model_bundle.status = 0
    model_bundle.generation = int(bundle["generation"])
    model_bundle.environment = bundle["environment"]
    model_bundle.runner = bundle.get("runner", custom.ModelManagerSP.Runner.snpe)
    model_bundle.is20hz = bundle.get("is_20hz", False)
    model_bundle.minimumSelectorVersion = int(bundle["minimum_selector_version"])
    model_bundle.overrides = ModelParser._parse_overrides(bundle.get("overrides", {}))
    model_bundle.ref = bundle.get("ref")

    return model_bundle

  @staticmethod
  def parse_models(json_data: dict) -> list[custom.ModelManagerSP.ModelBundle]:
    found_bundles = [ModelParser._parse_bundle(bundle) for bundle in json_data.get("bundles", [])]
    return [bundle for bundle in found_bundles if is_bundle_version_compatible(bundle.to_dict())]


class ModelCache:
  """Handles caching of model data to avoid frequent remote fetches"""

  def __init__(self, params: Params, cache_timeout: int = int(3600 * 1e9), suffix: str = ""):
    self.params = params
    self.cache_timeout = cache_timeout
    self._LAST_SYNC_KEY = f"ModelManager_LastSyncTime{suffix}"
    self._CACHE_KEY = f"ModelManager_ModelsCache{suffix}"

  def _is_expired(self) -> bool:
    """Checks if the cache has expired"""
    current_time = int(time.monotonic() * 1e9)
    last_sync = self.last_sync_time()
    return bool(last_sync == 0) or (current_time - last_sync) >= self.cache_timeout

  def last_sync_time(self) -> int:
    return int(self.params.get(self._LAST_SYNC_KEY) or 0)

  def consume_refresh_request(self) -> bool:
    """Consume the negative timestamp used as the model-list refresh signal."""
    if self.last_sync_time() >= 0:
      return False
    self.params.put(self._LAST_SYNC_KEY, 0, block=True)
    return True

  def get(self) -> tuple[dict, bool]:
    """
    Retrieves cached model data and expiration status atomically.
    Returns: Tuple of (cached_data, is_expired)
    If no cached data exists or on error, returns an empty dict
    """
    try:
      cached_data = self.params.get(self._CACHE_KEY)
      if not cached_data:
        # This is expected on first boot and while offline. ModelFetcher logs
        # the failed network attempt once, together with its retry delay.
        return {}, True
      return cached_data, self._is_expired()
    except Exception as e:
      cloudlog.exception(f"Error retrieving cached model data: {str(e)}")
      return {}, True

  def set(self, data: dict) -> None:
    """Updates the cache with new model data"""
    self.params.put(self._CACHE_KEY, data, block=True)
    self.params.put(self._LAST_SYNC_KEY, int(time.monotonic() * 1e9), block=True)


class ModelFetcher:
  """Handles fetching and caching of model data from remote source"""
  MODEL_URL = "https://raw.githubusercontent.com/sunnypilot/sunnypilot-models/refs/heads/gh-pages/docs/driving_models_v20.json"

  def __init__(self, params: Params):
    self.params = params
    self.model_cache = ModelCache(params)
    self.model_parser = ModelParser()
    self.has_usable_catalog = False
    self._fetch_failures = 0
    self._next_fetch_time = 0.0
    self._last_fetch_error = ""
    self._last_retry_delay = 0.0
    self._last_sync_time = self.model_cache.last_sync_time()
    self._last_cache_parse_error = ""

  def _reset_fetch_backoff(self) -> None:
    had_failures = self._fetch_failures > 0
    self._fetch_failures = 0
    self._next_fetch_time = 0.0
    self._last_fetch_error = ""
    self._last_retry_delay = 0.0
    if had_failures:
      cloudlog.info("Model catalog fetch recovered")

  def _record_fetch_failure(self, error: Exception | str) -> None:
    delay = min(FETCH_RETRY_INITIAL_SECONDS * (2 ** min(self._fetch_failures, 10)),
                FETCH_RETRY_MAX_SECONDS)
    self._fetch_failures += 1
    self._last_retry_delay = delay
    self._next_fetch_time = time.monotonic() + delay
    self._last_fetch_error = str(error)

  def _parse_cached_models(self, cached_data: dict) -> list[custom.ModelManagerSP.ModelBundle]:
    if not cached_data:
      self._last_cache_parse_error = ""
      return []
    try:
      bundles = self.model_parser.parse_models(cached_data)
      self._last_cache_parse_error = ""
      return bundles
    except Exception as e:
      # Treat a corrupt cache as unavailable. The network path below may repair
      # it, while the active bundle remains subject only to local file checks.
      error = str(e)
      if error != self._last_cache_parse_error:
        cloudlog.warning(f"Ignoring invalid cached model catalog: {error}")
        self._last_cache_parse_error = error
      return []

  def _fetch_and_cache_models(self) -> list[custom.ModelManagerSP.ModelBundle] | None:
    """Fetches fresh model data from remote and updates cache.
    Returns None on transport, HTTP, parse, or compatibility errors.
    """
    if OFFLINE:
      self._record_fetch_failure("offline mode enabled")
      return None

    try:
      response = requests.get(self.MODEL_URL, timeout=10)

      # Explicitly handle 404 differently
      if response.status_code == 404:
        cloudlog.error(f"Models URL returned 404 Not Found: {self.MODEL_URL}")
        raise HTTPError(f"404 Not Found: {self.MODEL_URL}", response=response)

      # Raise for any other 4xx/5xx
      response.raise_for_status()

      json_data = response.json()
      bundles = self.model_parser.parse_models(json_data)
      if not bundles:
        raise ValueError("remote model catalog contains no compatible bundles")

      # Never replace a usable offline catalog with malformed or incompatible
      # remote data. Parse first, then commit the cache atomically.
      self.model_cache.set(json_data)
      self._last_sync_time = self.model_cache.last_sync_time()
      self._reset_fetch_backoff()
      cloudlog.debug("Successfully updated models cache")
      return bundles

    except SSLError as e:
      self._record_fetch_failure(e)
    except RequestsConnectionError as e:
      self._record_fetch_failure(e)
    except RequestException as e:
      self._record_fetch_failure(e)
    except Exception as e:
      self._record_fetch_failure(e)

    return None

  def get_available_bundles(self, force_refresh: bool = False) -> list[custom.ModelManagerSP.ModelBundle]:
    """Gets the list of available models, with smart cache handling"""
    cached_data, is_expired = self.model_cache.get()
    cached_bundles = self._parse_cached_models(cached_data)
    self.has_usable_catalog = bool(cached_bundles)

    # The existing refresh button invalidates LastSyncTime. Detect the
    # nonzero->zero transition so a user-requested refresh is not held behind a
    # previous offline retry delay. A zero value at process start is not a
    # permanent force-refresh signal.
    force_refresh |= self.model_cache.consume_refresh_request()
    sync_time = self.model_cache.last_sync_time()
    force_refresh |= self._last_sync_time > 0 and sync_time == 0
    self._last_sync_time = sync_time
    if force_refresh:
      self._next_fetch_time = 0.0

    if cached_bundles and not is_expired and not force_refresh:
      cloudlog.debug("Using valid cached models data")
      return cached_bundles

    if time.monotonic() < self._next_fetch_time:
      return cached_bundles

    fetched_bundles = self._fetch_and_cache_models()
    if fetched_bundles is not None:
      self.has_usable_catalog = True
      return fetched_bundles

    fallback = "using cached catalog" if cached_bundles else "no cached catalog available"
    warning = f"Model catalog fetch failed ({self._last_fetch_error}); {fallback}; retrying in {int(self._last_retry_delay)}s"
    cloudlog.warning(warning)
    return cached_bundles

if __name__ == "__main__":
  params = Params()
  model_fetcher = ModelFetcher(params)
  bundles = model_fetcher.get_available_bundles()
  for bundle in bundles:
    for model in bundle.models:
      model_overrides = {override.key: override.value for override in bundle.overrides}
      print(f"Bundle: {bundle.internalName}, Type: {model.type}, Status: {bundle.status}, Overrides: {model_overrides}")
      print(f"Artifact: {model.artifact.fileName}, Download URI: {model.artifact.downloadUri.uri}")
      if model.artifact.chunks:
        print(f"Contains {len(model.artifact.chunks)} chunks.")
