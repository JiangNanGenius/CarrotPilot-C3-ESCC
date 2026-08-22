import io
import json
import pickle
import struct
from pathlib import Path


MODELS_DIR = Path(__file__).resolve().parent / "models"
TG_INPUT_DEVICES_PATH = MODELS_DIR / "tg_input_devices.json"


def get_tg_input_devices(process_name: str, usbgpu: bool = False):
  with open(TG_INPUT_DEVICES_PATH) as f:
    return json.load(f)[process_name]["usbgpu" if usbgpu else "default"]


def modeld_pkl_path(usbgpu: bool = False):
  prefix = "big_" if usbgpu else ""
  return MODELS_DIR / f"{prefix}driving_tinygrad.pkl"


def usbgpu_present() -> bool:
  # C3 has no Chestnut USB-GPU path. Keeping this explicit prevents current
  # upstream build descriptors from probing C4-only hardware modules.
  return False


def load_oob(file_obj):
  """Load a protocol-5 pickle whose buffers follow the opcode stream."""
  header = file_obj.read(8)
  if len(header) != 8:
    raise ValueError("Invalid combined model: missing pickle opcode header")
  opcode_size = struct.unpack('<q', header)[0]
  opcodes = file_obj.read(opcode_size)
  if len(opcodes) != opcode_size:
    raise ValueError("Invalid combined model: truncated pickle opcode stream")

  def buffers():
    while header := file_obj.read(8):
      if len(header) != 8:
        raise ValueError("Invalid combined model: truncated buffer header")
      size = struct.unpack('<q', header)[0]
      pickle_buffer = pickle.PickleBuffer(bytearray(size))
      read_size = file_obj.readinto(pickle_buffer)
      if read_size != size:
        raise ValueError("Invalid combined model: truncated out-of-band buffer")
      yield pickle_buffer

  return pickle.load(io.BytesIO(opcodes), buffers=buffers())
