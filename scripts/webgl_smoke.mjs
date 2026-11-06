// Smoke test of a WebGL build in headless Chromium (software GL, so slow: it checks that the game loads, logs the participant in, shows the
// experiment menu, starts an experiment, reaches its first session and talks to the data server, not how it plays or looks at speed).
//
//   node scripts/webgl_smoke.mjs <build dir> [--server http://127.0.0.1:54399 --key testkey --pid WEB1 --out <dir> --seconds 90 --row 0
//        --returning --signature "Smoke Test" --release --send-encoding]
//
// The flow (clicks at the screens' fixed positions, since the UI is drawn on a canvas): the ID screen (the pid from the address, locked) ->
// Continue; the consent screen (unless --returning: the server already holds this pid's signature) -> type the name, Continue; the menu -> the
// button of row --row (0 = the first experiment, the Tutorial) -> the experiment's files download -> "Click anywhere to begin" -> click ->
// the instruction screen -> Enter. The server must know the build's commit and offer the experiment (server_admin register-experiment,
// register-release --experiment CODE=N).
//
// --release: a non-development build ignores the URL overrides for the server (by design), so the page is opened with only ?pid=
// and the build's own StreamingAssets/online.json decides where it uploads (patch the copy in the build directory to test).
//
// Serves the build directory (like GitHub Pages, without Content-Encoding for .br/.gz unless --send-encoding), opens it with the development-build
// URL overrides (?onlineUrl=...&onlineKey=...&pid=...), clicks to start, dismisses the instruction screen and records the console
// and screenshots. Playwright comes from PLAYWRIGHT_DIR (default: evidence_integration's task_backend).
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const args = process.argv.slice(2);
const buildDir = path.resolve(args[0] ?? '.');
const opt = (name, fallback) => (args.includes(`--${name}`) ? args[args.indexOf(`--${name}`) + 1] : fallback);
const server = opt('server', 'http://127.0.0.1:54399');
const key = opt('key', 'testkey');
const pid = opt('pid', 'WEB1');
const out = path.resolve(opt('out', '.'));
const seconds = Number(opt('seconds', '90'));
const row = Number(opt('row', '0'));
const returning = args.includes('--returning');
const signature = opt('signature', 'Smoke Test');
const require = createRequire((process.env.PLAYWRIGHT_DIR ?? '/home/psipeter/evidence_integration/task_backend') + '/');
const { chromium } = require('playwright');

const types = { '.html': 'text/html', '.js': 'application/javascript', '.wasm': 'application/wasm', '.json': 'application/json',
  '.data': 'application/octet-stream', '.txt': 'text/plain', '.css': 'text/css', '.png': 'image/png', '.ico': 'image/x-icon' };
const staticServer = http.createServer((req, res) => {
  let file = path.join(buildDir, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (file.endsWith('/')) file += 'index.html';
  if (!file.startsWith(buildDir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end('not found'); return; }
  let name = file;                  // the file name without a compression suffix, for the Content-Type
  const headers = {};
  // Like GitHub Pages: no Content-Encoding for Unity's compressed files (.br/.gz/.unityweb); the build's decompression fallback handles them.
  if (args.includes('--send-encoding')) {
    if (name.endsWith('.br')) { headers['Content-Encoding'] = 'br'; name = name.slice(0, -3); }
    else if (name.endsWith('.gz')) { headers['Content-Encoding'] = 'gzip'; name = name.slice(0, -3); }
  }
  headers['Content-Type'] = types[path.extname(name)] ?? 'application/octet-stream';
  res.writeHead(200, headers);
  fs.createReadStream(file).pipe(res);
});
await new Promise((resolve) => staticServer.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${staticServer.address().port}/index.html?fullscreen=0&pid=${pid}`;
const url = args.includes('--release') ? base : `${base}&onlineUrl=${encodeURIComponent(server)}&onlineKey=${key}`;
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
  '--enable-webgl', '--autoplay-policy=no-user-gesture-required'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const log = [];
page.on('console', (m) => log.push(`[${m.type()}] ${m.text()}`));
page.on('pageerror', (e) => log.push(`[pageerror] ${e.message}`));
page.on('requestfailed', (r) => log.push(`[requestfailed] ${r.url()} ${r.failure()?.errorText}`));
const shot = async (name) => {
  try { await page.screenshot({ path: path.join(out, `${name}.png`), timeout: 90000 }); } catch (e) { log.push(`[smoke] screenshot ${name} failed: ${e.message.split('\n')[0]}`); }
  fs.writeFileSync(path.join(out, 'console.log'), log.join('\n'));
};
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

console.log('opening', url);
await page.goto(url);
const start = Date.now();
const px = (fx, fy) => [fx * 1280, (1 - fy) * 720];        // a point of the 1920 x 1080 reference canvas, as fractions from the bottom left
const click = async (fx, fy) => { const [x, y] = px(fx, fy); await page.mouse.click(x, y); };
const steps = [
  [15, 'id screen: Continue', async () => click(0.775, 0.46)],
  ...(returning ? [] : [[8, 'consent screen: sign and Continue', async () => {
    await click(0.36, 0.22);
    await page.keyboard.type(signature);
    await click(0.8, 0.22);
  }]]),
  [8, `menu: start experiment row ${row}`, async () => click(0.78, 0.7175 - row * 0.125)],
  [25, 'click anywhere to begin', async () => click(0.5, 0.5)],
  [9, 'instructions: Enter', async () => page.keyboard.press('Enter')],
];
let elapsed = 0;
for (const [delay, label, act] of steps) {
  await wait(delay * 1000);
  elapsed += delay;
  await shot(`t${String(elapsed).padStart(3, '0')}_before`);
  log.push(`[smoke] ${label}`);
  await act();
}
for (; elapsed < seconds; elapsed += 5) {
  await wait(5000);
  await shot(`t${String(elapsed + 5).padStart(3, '0')}`);
}
console.log(`ran ${(Date.now() - start) / 1000} s`);
fs.writeFileSync(path.join(out, 'console.log'), log.join('\n'));
console.log(log.slice(-40).join('\n'));
await browser.close();
staticServer.close();
