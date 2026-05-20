"""
Upload endpoint + HMAC secret for the CAS firehose uploader.

Secret resolution order:
  1) /data/carrot_upload_secret (runtime override — for users running their own server)
  2) DEFAULT_SECRET below (carrot's public upload server)

Endpoint resolution order:
  1) Params "CarrotUploadEndpoint" (user override)
  2) DEFAULT_ENDPOINT below
"""

from __future__ import annotations

from pathlib import Path


DEFAULT_ENDPOINT = "https://casroute.jominki354.live"
DEFAULT_SECRET = "aa3cd9680e8531ba15a5dde09552b65926cb5db330d8f296fecc315576f465ec"

SECRET_OVERRIDE_PATH = Path("/data/carrot_upload_secret")


def resolve_secret() -> bytes:
  try:
    if SECRET_OVERRIDE_PATH.exists():
      override = SECRET_OVERRIDE_PATH.read_text(encoding="utf-8").strip()
      if override:
        return override.encode("utf-8")
  except OSError:
    pass
  return DEFAULT_SECRET.encode("utf-8")


def resolve_endpoint(params) -> str:
  try:
    override = (params.get("CarrotUploadEndpoint") or b"").decode("utf-8").strip()
  except Exception:
    override = ""
  return override or DEFAULT_ENDPOINT
