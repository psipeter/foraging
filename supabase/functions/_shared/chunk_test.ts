// Run: deno test supabase/functions/_shared/chunk_test.ts
// The golden chunk is the one pinned in scripts/test_trajectory_codec.py (GOLDEN), produced by the Python reference codec.

import { assertEquals, assertRejects } from 'jsr:@std/assert@1';
import { ChunkError, decodeChunk } from './chunk.ts';

const GOLDEN = '4654524a0103000000030000008dedb5a0f7c6b03e7b14ae47e17a843f7b14ae47e17a943f' +
  'df76eefa6398348fa9a989e99b0003c30b65062060ba21d5be8069e62fc685c20f393900';

const bytes = (hex: string) => Uint8Array.from(hex.match(/../g)!.map((h) => parseInt(h, 16)));

Deno.test('decodes the Python golden chunk', async () => {
  const c = await decodeChunk(bytes(GOLDEN));
  assertEquals(c.firstSeq, 3);
  assertEquals(c.nFrames, 3);
  assertEquals(c.tStart, 0);
  assertEquals(Math.abs(c.tEnd - 0.004) < 1e-9, true);
  assertEquals(Math.abs(c.last.x - -1.23) < 1e-9 && Math.abs(c.last.z - 5) < 1e-9 && Math.abs(c.last.yaw - -3) < 1e-9, true);
  assertEquals(c.last.pitch, -12.5);
  assertEquals(c.last.keys, 5);
});

Deno.test('refuses a flipped bit, a truncated chunk and a wrong magic', async () => {
  const good = bytes(GOLDEN);
  const flipped = good.slice();
  flipped[45] ^= 1;
  await assertRejects(() => decodeChunk(flipped), ChunkError);
  await assertRejects(() => decodeChunk(good.slice(0, good.length - 1)), ChunkError);
  const wrong = good.slice();
  wrong[0] = 0x58;
  await assertRejects(() => decodeChunk(wrong), ChunkError);
  await assertRejects(() => decodeChunk(good.slice(0, 10)), ChunkError);
});
