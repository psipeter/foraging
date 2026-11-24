// Runs the hardware-acceleration check (webgl_gpu_check.js) against stubbed browsers: node scripts/test_webgl_gpu_check.mjs (exit 1 on a failure).
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const { check, browserOf, messageHtml } = createRequire(import.meta.url)('./webgl_gpu_check.js');

// A document whose canvas gives `strict` for a context asked with failIfMajorPerformanceCaveat and `any` for a plain request (null = none).
function doc(strict, any) {
  return { createElement: () => ({ getContext: (_, opt) => (opt && opt.failIfMajorPerformanceCaveat ? strict : any) }) };
}
const gl = (renderer) => ({ RENDERER: 1, getExtension: () => ({ UNMASKED_RENDERER_WEBGL: 2 }), getParameter: (p) => (p === 2 ? renderer : 'masked') });

const nvidia = gl('ANGLE (NVIDIA, NVIDIA GeForce RTX 3060, OpenGL 4.5)');
assert.deepEqual(check(doc(nvidia, nvidia)), { ok: true, renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060, OpenGL 4.5)' });
const swift = gl('ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device), SwiftShader driver)');
assert.equal(check(doc(swift, swift)).reason, 'software');                      // a strict context that reports software
assert.equal(check(doc(null, swift)).reason, 'software');                       // the caveat refused it
assert.equal(check(doc(null, gl('llvmpipe (LLVM 15, 256 bits)'))).reason, 'software');
assert.equal(check(doc(null, null)).reason, 'none');                            // no WebGL2 at all
assert.equal(check({ createElement: () => ({ getContext: () => { throw new Error('x'); } }) }).reason, 'none');

const UA = {
  chrome: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
  edge: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
  opera: 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0',
  firefox: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
  safari: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
};
for (const [name, ua] of Object.entries(UA)) assert.equal(browserOf(ua, false), name);
assert.equal(browserOf(UA.chrome, true), 'brave');
assert.equal(browserOf('Mozilla/5.0 (X11; Linux) AppleWebKit/538.1 (KHTML, like Gecko) Falkon/3.2', false), 'unknown');

const none = { ok: false, reason: 'none' }, soft = { ok: false, reason: 'software' };
assert.match(messageHtml(soft, 'firefox'), /Use hardware acceleration when available/);
assert.match(messageHtml(soft, 'chrome'), /Use graphics acceleration when available/);
assert.match(messageHtml(none, 'unknown'), /Chrome, Firefox, Safari or Edge/);
assert.doesNotMatch(messageHtml(none, 'unknown'), /<ol>/);                       // an unrecognised browser gets no steps, only "use a supported one"
assert.match(messageHtml(soft, 'safari'), /no switch/);
console.log('webgl_gpu_check: ok');
