"""Small local C ABI helper; no network payload is evaluated or dynamically compiled."""
import ctypes
from pathlib import Path
import sys
import struct

AVAILABLE = False
_error = None
try:
  suffix = '.dylib' if sys.platform == 'darwin' else '.so'
  _lib = ctypes.CDLL(str(Path(__file__).with_name('libopif_native' + suffix)))
  _crc = _lib.opif_crc32c
  _crc.argtypes = (ctypes.c_char_p, ctypes.c_size_t)
  _crc.restype = ctypes.c_uint32
  _finite = _lib.opif_f32_finite
  _finite.argtypes = (ctypes.c_char_p, ctypes.c_size_t)
  _finite.restype = ctypes.c_int
  if _crc(b'123456789', 9) != 0xe3069283 or _crc(b'', 0) != 0:
    raise RuntimeError('Native OPIF CRC32C identity check failed')
  _encode = _lib.opif_encode_tcp
  _encode.argtypes = (ctypes.c_uint8, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint16, ctypes.c_void_p, ctypes.c_size_t)
  _encode.restype = ctypes.c_size_t
  AVAILABLE = True
except OSError as error:
  _error = type(error).__name__


def crc32c(data):
  if not AVAILABLE:
    raise RuntimeError('Build the OPIF native helper before enabling C3 inference')
  data = data if isinstance(data, bytes) else bytes(data)
  return int(_crc(data, len(data)))


def finite_f32(data):
  if not AVAILABLE:
    raise RuntimeError('OPIF native finite check unavailable')
  data = data if isinstance(data, bytes) else bytes(data)
  return bool(_finite(data, len(data)))


class NativePackets:
  def __init__(self, message_type, session, request, body, maximum):
    if not 0 <= int(message_type) <= 255 or not 0 <= session < 2**64 or not 0 <= request < 2**64:
      raise ValueError('Invalid OPIF integer field')
    limit = maximum - 40
    self.count = max(1, (len(body) + limit - 1) // limit)
    self.stride = maximum + 4
    size = len(body) + self.count * 44
    buffer = ctypes.create_string_buffer(size)
    if _encode(int(message_type), session, request, body, len(body), maximum, buffer, size) != size:
      raise ValueError('Native OPIF framing rejected input')
    self.tcp_bytes = buffer.raw
    self.crc = struct.unpack_from('<I', self.tcp_bytes, 40)[0]

  def __len__(self):
    return self.count

  def __getitem__(self, index):
    if index < 0:
      index += self.count
    if not 0 <= index < self.count:
      raise IndexError(index)
    start = index * self.stride
    size = struct.unpack_from('<I', self.tcp_bytes, start)[0]
    return self.tcp_bytes[start + 4:start + 4 + size]

  def select(self, indices):
    if indices is None:
      return self.tcp_bytes
    if isinstance(indices, range) and indices.step == 1:
      return self.tcp_bytes[indices.start * self.stride:min(len(self.tcp_bytes), indices.stop * self.stride)]
    return b''.join(struct.pack('<I', len(self[i])) + self[i] for i in indices)


if AVAILABLE:
  _decoder_create = _lib.opif_decoder_create
  _decoder_create.restype = ctypes.c_void_p
  _decoder_destroy = _lib.opif_decoder_destroy
  _decoder_destroy.argtypes = (ctypes.c_void_p,)
  _decoder_feed = _lib.opif_decoder_feed
  _decoder_feed.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t)
  _decoder_feed.restype = ctypes.c_int
  _decoder_next = _lib.opif_decoder_next
  _decoder_next.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64), ctypes.c_void_p, ctypes.c_size_t)
  _decoder_next.restype = ctypes.c_int
  _decoder_error = _lib.opif_decoder_error
  _decoder_error.argtypes = (ctypes.c_void_p,)
  _decoder_error.restype = ctypes.c_char_p


class Decoder:
  def __init__(self):
    self.handle = _decoder_create()
    if not self.handle:
      raise MemoryError('OPIF decoder allocation failed')
    self.body = ctypes.create_string_buffer(1048576)
    self.metadata = (ctypes.c_uint64 * 5)()

  def __del__(self):
    try:
      if self.handle:
        handle, self.handle = self.handle, 0
        _decoder_destroy(handle)
    except Exception:
      pass

  def feed(self, data):
    if _decoder_feed(self.handle, data, len(data)):
      raise ValueError(_decoder_error(self.handle).decode())

  def pop(self):
    code = _decoder_next(self.handle, self.metadata, self.body, len(self.body))
    if code < 0:
      raise ValueError(_decoder_error(self.handle).decode())
    if code == 0:
      return None
    kind, session, request, size, crc = self.metadata
    return kind, session, request, crc, ctypes.string_at(self.body, size)
