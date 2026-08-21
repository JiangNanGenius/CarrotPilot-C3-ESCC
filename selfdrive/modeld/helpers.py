import io
import pickle
import struct


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
