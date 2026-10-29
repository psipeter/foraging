// chunk.ts -- validates and summarizes a trajectory chunk (the format of scripts/trajectory_codec.py, which is the
// reference: read its docstring). The server never trusts the client's claims about a chunk: first_seq, the frame count,
// the time span and the last frame all come from decoding it here.

const HEADER_SIZE = 41;
const MAGIC = 'FTRJ';
const VERSION = 1;
const MAX_FRAMES = 200_000;
const MAX_VARINT_BYTES = 7; // 49 bits: values are exact in a double, and far beyond any quantized coordinate or time

export interface Frame {
  t: number;
  x: number;
  z: number;
  yaw: number;
  pitch: number;
  keys: number;
}

export interface ChunkSummary {
  firstSeq: number;
  nFrames: number;
  tStart: number;
  tEnd: number;
  last: Frame;
}

export class ChunkError extends Error {}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

async function inflateRaw(body: Uint8Array, limit: number): Promise<Uint8Array> {
  const stream = new Blob([body.slice().buffer as ArrayBuffer]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  const reader = stream.getReader();
  const parts: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > limit) throw new ChunkError('chunk body inflates beyond its limit');
      parts.push(value);
    }
  } catch (e) {
    if (e instanceof ChunkError) throw e;
    throw new ChunkError(`corrupt chunk body: ${e instanceof Error ? e.message : e}`);
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

export async function decodeChunk(data: Uint8Array): Promise<ChunkSummary> {
  if (data.length < HEADER_SIZE) throw new ChunkError('chunk shorter than its header');
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const magic = String.fromCharCode(...data.subarray(0, 4));
  if (magic !== MAGIC || view.getUint8(4) !== VERSION) throw new ChunkError('not a trajectory chunk of a known version');
  const n = view.getUint32(5, true);
  const firstSeq = view.getUint32(9, true);
  const steps = [view.getFloat64(13, true), view.getFloat64(21, true), view.getFloat64(29, true)];
  const crc = view.getUint32(37, true);
  if (n === 0 || n > MAX_FRAMES) throw new ChunkError(`chunk claims ${n} frames (1 to ${MAX_FRAMES} allowed)`);
  if (!steps.every((s) => Number.isFinite(s) && s > 0)) throw new ChunkError('quantization steps must be positive');

  const raw = await inflateRaw(data.subarray(HEADER_SIZE), n * 6 * MAX_VARINT_BYTES);
  if (crc32(raw) !== crc) throw new ChunkError('chunk checksum mismatch');

  // Frame by frame, column by column: zigzag varints of deltas; keep the running sums (the quantized values).
  const sum = [0, 0, 0, 0, 0, 0];
  let tFirst = 0;
  let pos = 0;
  for (let frame = 0; frame < n; frame++) {
    for (let col = 0; col < 6; col++) {
      let value = 0;
      let scale = 1;
      let count = 0;
      for (;;) {
        if (pos >= raw.length) throw new ChunkError('truncated varint stream');
        const b = raw[pos++];
        if (++count > MAX_VARINT_BYTES) throw new ChunkError('varint too long');
        value += (b & 0x7f) * scale;
        scale *= 128;
        if ((b & 0x80) === 0) break;
      }
      const delta = value % 2 === 0 ? value / 2 : -(value + 1) / 2; // zigzag
      if (col === 0 && frame > 0 && delta < 0) throw new ChunkError('time goes backwards');
      sum[col] += delta;
    }
    if (frame === 0) tFirst = sum[0];
  }
  if (pos !== raw.length) throw new ChunkError('chunk body has extra bytes');
  return {
    firstSeq,
    nFrames: n,
    tStart: tFirst * steps[0],
    tEnd: sum[0] * steps[0],
    last: { t: sum[0] * steps[0], x: sum[1] * steps[1], z: sum[2] * steps[1], yaw: sum[3] * steps[2], pitch: sum[4] * steps[2], keys: sum[5] },
  };
}

export function fromBase64(text: string): Uint8Array {
  try {
    return Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
  } catch {
    throw new ChunkError('chunk is not valid base64');
  }
}
