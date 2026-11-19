// Frame-time benchmark of a WebGL development build in a real browser (Chromium through Playwright), one build, many settings.
//
//   node scripts/perf_browser.mjs <build dir> --tag base [--variant name="renderScale=0.8&ssao=0" ...] [--runs 3] [--seconds 60]
//        [--experiment TUT] [--width 1920 --height 1080] [--headed] [--vsync] [--angle gl|vulkan|swiftshader] [--out results/perf]
//
// The build must be a DEVELOPMENT build (PerfProbe, PerfAutopilot and the address options are compiled out of a release build). Each run opens
// index.html?perf=1&autopilot=1&offline=1&experiment=<code>&perfSeconds=<n>&<variant>, gets past the "click to begin" and instruction screens, and waits for the
// PERF_PART lines the game prints after <n> recorded seconds. `offline=1` keeps a benchmark from writing runs into the real database. The variant
// "base" (no options) is always run first; --variant adds more (the address options are listed in Assets/Scripts/Session/PerfProbe.cs).
// Output: <out>/<tag>/<variant>_<run>.json (the game's JSON plus the browser's version and the flags used). Read them with scripts/perf_report.py <tag>.
//
// The page is patched like a deploy (scripts/patch_webgl_page.py: a fixed drawing buffer, 1920x1080 by default) in a copy of the build under <out>/<tag>/site, so
// the picture has the size participants get. Without --vsync Chromium runs with its frame rate limit and vsync off, so a frame's time is its cost, not the monitor's
// refresh; with --vsync it is what a participant sees on this monitor. The GPU actually used is in the JSON (env.gpu): "SwiftShader" means software drawing, whose
// times mean nothing. Playwright comes from PLAYWRIGHT_DIR (default: evidence_integration's task_backend).
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const buildDir = path.resolve(args[0] ?? '.');
const opt = (name, fallback) => (args.includes(`--${name}`) ? args[args.indexOf(`--${name}`) + 1] : fallback);
const variants = [['base', '']];
args.forEach((a, i) => {
  if (a === '--variant') {
    const m = args[i + 1].match(/^([^=]+)=(.*)$/s);
    variants.push([m[1], m[2]]);
  }
});
const tag = opt('tag', 'run');
const runs = Number(opt('runs', '3'));
const seconds = Number(opt('seconds', '60'));
const experiment = opt('experiment', 'TUT');
const width = Number(opt('width', '1920'));
const height = Number(opt('height', '1080'));
const angle = opt('angle', 'gl');
const headed = args.includes('--headed');
const vsync = args.includes('--vsync');
const outRoot = path.resolve(opt('out', path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'results', 'perf')), tag);
const require = createRequire((process.env.PLAYWRIGHT_DIR ?? '/home/psipeter/evidence_integration/task_backend') + '/');
const { chromium } = require('playwright');

if (!fs.existsSync(path.join(buildDir, 'index.html'))) throw new Error(`${buildDir} is not a WebGL build (no index.html)`);
fs.mkdirSync(outRoot, { recursive: true });
const site = path.join(outRoot, 'site');
if (!fs.existsSync(path.join(site, 'index.html'))) {
  fs.cpSync(buildDir, site, { recursive: true });
  execFileSync('python3', [path.join(path.dirname(fileURLToPath(import.meta.url)), 'patch_webgl_page.py'), path.join(site, 'index.html'),
    '--width', String(width), '--height', String(height)], { stdio: 'inherit' });
}

const types = { '.html': 'text/html', '.js': 'application/javascript', '.wasm': 'application/wasm', '.json': 'application/json', '.data': 'application/octet-stream',
  '.txt': 'text/plain', '.css': 'text/css', '.png': 'image/png', '.ico': 'image/x-icon' };
const server = http.createServer((req, res) => {      // like GitHub Pages: no Content-Encoding for Unity's compressed files
  let file = path.join(site, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (file.endsWith('/')) file += 'index.html';
  if (!file.startsWith(site) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end('not found'); return; }
  const name = file.replace(/\.(br|gz|unityweb)$/, '');
  res.writeHead(200, { 'Content-Type': types[path.extname(name)] ?? 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}/index.html`;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const flags = ['--ignore-gpu-blocklist', '--enable-webgl', '--autoplay-policy=no-user-gesture-required', `--use-gl=angle`, `--use-angle=${angle}`,
  '--enable-gpu-rasterization', ...(angle === 'swiftshader' ? ['--enable-unsafe-swiftshader'] : []),
  ...(vsync ? [] : ['--disable-gpu-vsync', '--disable-frame-rate-limit'])];

async function runOnce(name, query, n) {
  const browser = await chromium.launch({ headless: !headed, args: flags });
  const page = await browser.newPage({ viewport: { width: Math.min(width, 1600), height: Math.min(height, 900) } });
  const lines = [];
  let json = null;
  let started = false;
  const parts = [];
  page.on('console', (m) => {
    const t = m.text().split('\n')[0];          // a development build adds the stack trace after the message
    lines.push(t.slice(0, 300));
    if (t.startsWith('PERF_START')) started = true;
    if (t.startsWith('PERF_PART ')) {          // PERF_PART <i> <n> <text>: a browser cuts a console line at about 8 KB

      const head = t.match(/^PERF_PART (\d+) (\d+) /);
      parts[Number(head[1])] = t.slice(head[0].length);
      if (parts.filter((x) => x !== undefined).length === Number(head[2])) json = parts.join('');
    }
  });
  page.on('pageerror', (e) => lines.push(`[pageerror] ${e.message}`));
  const url = `${base}?fullscreen=0&perf=1&autopilot=1&offline=1&experiment=${experiment}&perfSeconds=${seconds}${query ? '&' + query : ''}`;
  await page.goto(url);
  const t0 = Date.now();
  // Past the loading screens: click (pointer lock, "click to begin") and Enter (the session's instruction screen) until the probe reports its first frame.
  while (!started && !json && Date.now() - t0 < 180000) {
    await wait(1500);
    try { await page.mouse.click(640, 360); await page.keyboard.press('Enter'); } catch { break; }
  }
  while (!json && Date.now() - t0 < 180000 + (seconds + 60) * 1000) await wait(1000);
  const version = browser.version();
  await browser.close();
  if (!json) {
    fs.writeFileSync(path.join(outRoot, `${name}_${n}.fail.log`), lines.join('\n'));
    console.log(`  ${name} run ${n}: no PERF_JSON (see ${name}_${n}.fail.log)`);
    return null;
  }
  const result = JSON.parse(json);
  result.run = { variant: name, query, n, browser: version, flags, vsync, width, height, experiment, seconds };
  fs.writeFileSync(path.join(outRoot, `${name}_${n}.json`), JSON.stringify(result));
  const s = result.summary;
  console.log(`  ${name} run ${n}: ${s.frames} frames, mean ${s.meanMs} ms, p99 ${s.p99Ms}, max ${s.maxMs}, >33ms ${s.over33}  [${result.env.gpu}]`);
  return result;
}

for (const [name, query] of variants) {
  console.log(`${name}: ${query || '(build as is)'}`);
  for (let n = 1; n <= runs; n++) await runOnce(name, query, n);
}
server.close();
console.log(`results in ${outRoot}; report: ./venv/bin/python scripts/perf_report.py ${tag}`);
