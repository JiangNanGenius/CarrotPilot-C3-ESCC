from __future__ import annotations

import hashlib


FORMAT_VERSION = 2


def fw_version_bytes(value) -> bytes:
  if isinstance(value, bytes):
    return value
  if isinstance(value, bytearray):
    return bytes(value)
  try:
    return bytes(value)
  except Exception:
    return str(value).encode("utf-8", "ignore")


def is_eps_ecu(ecu) -> bool:
  text = str(ecu).lower()
  return ecu == "eps" or text == "eps" or text.endswith(".eps")


def eps_firmware_hash(car_fw) -> str:
  parts = []
  for fw in car_fw:
    if not is_eps_ecu(getattr(fw, "ecu", "")):
      continue
    address = int(getattr(fw, "address", 0))
    sub_address = int(getattr(fw, "subAddress", 0))
    version = fw_version_bytes(getattr(fw, "fwVersion", b""))
    parts.append((address, sub_address, version))

  if not parts:
    return ""

  digest = hashlib.sha1()
  # carFw may contain duplicate EPS firmware responses in some logs. Duplicates
  # do not mean the EPS firmware changed, so collapse them before hashing.
  for address, sub_address, version in sorted(set(parts)):
    digest.update(address.to_bytes(4, "big", signed=False))
    digest.update(sub_address.to_bytes(1, "big", signed=False))
    digest.update(len(version).to_bytes(2, "big", signed=False))
    digest.update(version)
  return digest.hexdigest()[:12]
