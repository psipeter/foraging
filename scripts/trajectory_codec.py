"""Compact, lossless-at-its-quantization encoding of a trajectory chunk (docs/ONLINE_DATA_PLAN.md, section 2).

A chunk is a run of consecutive frames of one session, as an (n, 6) array of t, x, z, yaw, pitch, keys. Each column is
rounded to a multiple of its step, delta-coded against the previous frame (the first frame against zero), zigzag-varint
encoded and DEFLATE-compressed. Decoding returns exactly the quantized values (`quantize`), so what the server holds and
what a local mirror writes agree to the step.

Wire format (little endian):
    4s  magic "FTRJ"
    B   version (1)
    I   n_frames
    I   first_seq     frame index of the first frame within the session
    d   t_step        seconds (1e-6: replay re-derives frame-level harvest decisions from the frame times)
    d   xz_step       world units
    d   angle_step    degrees (yaw and pitch)
    I   crc32         of the varint bytes before compression (DEFLATE has no checksum of its own)
    ... raw DEFLATE (RFC 1951, no zlib header: .NET's DeflateStream) of the varints, frame by frame, column by column

The C# client (Assets/Scripts/Data/TrajectoryCodec.cs) must produce the same varint stream: round half to even on
`value / step` (Math.Round's default), zigzag (v << 1) ^ (v >> 63), LEB128 varints. `GOLDEN` in test_trajectory_codec.py pins
the format; Unity's DeflateStream happens to reproduce its compressed bytes too, but only the varint stream (the CRC) must agree.
"""

import struct
import zlib
from dataclasses import dataclass

import numpy as np

MAGIC = b"FTRJ"
VERSION = 1
HEADER = struct.Struct("<4sBIIdddI")
COLUMNS = ("t", "x", "z", "yaw", "pitch", "keys")
MAX_FRAMES = 200_000            # one chunk is seconds of play; this bounds what a decoder will inflate
MAX_VARINT_BYTES = 10           # a 64-bit value


@dataclass(frozen=True)
class Steps:
    t: float = 1e-6             # at 1 ms replay.verify found 8 mismatches in 4 real logs: the fruit timer sums frame times
    xz: float = 0.01
    angle: float = 0.02         # no coarser than one mouse count (lookDegreesPerCount is 0.022)

    def vector(self):
        return np.array([self.t, self.xz, self.xz, self.angle, self.angle, 1.0])


DEFAULT_STEPS = Steps()


def _as_frames(frames):
    frames = np.asarray(frames, dtype=float)
    if frames.ndim != 2 or frames.shape[1] != 6:
        raise ValueError("frames must have shape (n, 6): t, x, z, yaw, pitch, keys")
    if not np.all(np.isfinite(frames)):
        raise ValueError("frames must be finite")
    return frames


def _quantized(frames, steps):
    q = np.rint(_as_frames(frames) / steps.vector())        # rint rounds half to even, like Math.Round
    if np.abs(q).max(initial=0) >= 2 ** 62:
        raise ValueError("value too large for the quantization step")
    return q.astype(np.int64)


def quantize(frames, steps=DEFAULT_STEPS):
    """The frames as decode(encode(frames)) returns them."""
    return _quantized(frames, steps) * steps.vector()


def _write_varints(values):
    """LEB128 of an array of uint64."""
    bits = np.zeros(len(values), dtype=np.int64)
    rest = values.copy()
    while rest.any():
        bits += rest > 0
        rest >>= np.uint64(1)
    count = np.maximum(1, (bits + 6) // 7)
    start = np.cumsum(count) - count
    out = np.empty(int(count.sum()), dtype=np.uint8)
    for k in range(int(count.max(initial=1))):
        has = count > k
        byte = ((values[has] >> np.uint64(7 * k)) & np.uint64(0x7F)).astype(np.uint8)
        byte |= np.where(count[has] > k + 1, 0x80, 0).astype(np.uint8)
        out[start[has] + k] = byte
    return out


def _read_varints(data, expected):
    if len(data) == 0 or data[-1] & 0x80:
        raise ValueError("truncated varint stream")
    ends = (data & 0x80) == 0
    if int(ends.sum()) != expected:
        raise ValueError(f"expected {expected} values, found {int(ends.sum())}")
    owner = np.cumsum(ends) - ends                          # index of the value each byte belongs to
    first = np.flatnonzero(np.r_[True, ends[:-1]])          # position of each value's first byte
    position = np.arange(len(data)) - first[owner]
    if position.max() >= MAX_VARINT_BYTES:
        raise ValueError("varint too long")
    parts = (data & 0x7F).astype(np.uint64) << (np.uint64(7) * position.astype(np.uint64))
    return np.add.reduceat(parts, first)


def encode(frames, first_seq=0, steps=DEFAULT_STEPS):
    """Bytes of one chunk (n may be 0)."""
    q = _quantized(frames, steps)
    n = len(q)
    if n > MAX_FRAMES:
        raise ValueError(f"chunk of {n} frames exceeds {MAX_FRAMES}")
    delta = np.diff(q, axis=0, prepend=np.zeros((1, 6), dtype=np.int64)) if n else q
    zigzag = ((delta << 1) ^ (delta >> 63)).astype(np.uint64).ravel()
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = _write_varints(zigzag).tobytes() if n else b""
    body = deflate.compress(raw) + deflate.flush() if n else b""
    return HEADER.pack(MAGIC, VERSION, n, first_seq, steps.t, steps.xz, steps.angle, zlib.crc32(raw)) + body


def decode(data):
    """(first_seq, steps, frames) of a chunk; frames is (n, 6) float. Raises ValueError on anything malformed."""
    data = bytes(data)
    if len(data) < HEADER.size:
        raise ValueError("chunk shorter than its header")
    magic, version, n, first_seq, t_step, xz_step, angle_step, crc = HEADER.unpack_from(data)
    if magic != MAGIC or version != VERSION:
        raise ValueError("not a trajectory chunk of a known version")
    if n > MAX_FRAMES:
        raise ValueError(f"chunk claims {n} frames (maximum {MAX_FRAMES})")
    steps = Steps(t_step, xz_step, angle_step)
    if not all(np.isfinite(v) and v > 0 for v in (t_step, xz_step, angle_step)):
        raise ValueError("quantization steps must be positive")
    body = data[HEADER.size:]
    if n == 0:
        if body or crc != zlib.crc32(b""):
            raise ValueError("an empty chunk has no body")
        return first_seq, steps, np.empty((0, 6))
    inflate = zlib.decompressobj(-15)
    limit = n * 6 * MAX_VARINT_BYTES
    try:
        raw = inflate.decompress(body, limit + 1)
    except zlib.error as e:
        raise ValueError(f"corrupt chunk body: {e}")
    if len(raw) > limit or inflate.unconsumed_tail or not inflate.eof or inflate.unused_data:
        raise ValueError("chunk body is too large, incomplete or followed by extra bytes")
    if zlib.crc32(raw) != crc:
        raise ValueError("chunk checksum mismatch")
    zigzag = _read_varints(np.frombuffer(raw, dtype=np.uint8), n * 6).reshape(n, 6)
    delta = (zigzag >> np.uint64(1)).astype(np.int64) ^ -(zigzag & np.uint64(1)).astype(np.int64)
    return first_seq, steps, np.cumsum(delta, axis=0) * steps.vector()
