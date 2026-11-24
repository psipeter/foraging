// Hardware-acceleration check for the WebGL page (embedded into the build's index.html by scripts/patch_webgl_page.py; also loaded by
// scripts/test_webgl_gpu_check.mjs, which runs it with stubbed browsers). It runs before Unity's loader is added to the page: a browser that
// renders WebGL in software (hardware acceleration off, or a blocklisted GPU) makes the game crawl and fail to connect, so the participant gets
// instructions to turn it on and the game is not loaded until the check passes (docs/DECISIONS.md, "WebGL: hardware acceleration is required").
(function (root) {
  'use strict';

  var SOFTWARE = /swiftshader|llvmpipe|softpipe|software|microsoft basic render|mesa offscreen|\bgdi generic\b/i;

  // The browser family, from the user agent (order matters: Edge, Opera and Chromium forks also say "Chrome", Chrome on iOS says "Safari").
  function browserOf(ua, hasBrave) {
    if (hasBrave) return 'brave';
    if (/Edg(e|A|iOS)?\//.test(ua)) return 'edge';
    if (/OPR\/|Opera/.test(ua)) return 'opera';
    if (/Firefox\/|FxiOS\//.test(ua)) return 'firefox';
    if (/Chrome\/|Chromium\/|CriOS\//.test(ua)) return 'chrome';
    if (/Safari\//.test(ua) && /Version\//.test(ua)) return 'safari';
    return 'unknown';
  }

  // {ok: true, renderer} or {ok: false, reason: 'none' | 'software', renderer}. `doc` is a document-like object (createElement('canvas')).
  function check(doc) {
    var canvas = doc.createElement('canvas');
    var gl = null;
    try {
      // failIfMajorPerformanceCaveat: no context at all when the browser would fall back to software rendering.
      gl = canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: true });
    } catch (e) { gl = null; }
    if (!gl) {
      var soft = null;      // is WebGL2 there at all, only in software? (decides the wording)
      try { soft = canvas.getContext('webgl2') || doc.createElement('canvas').getContext('webgl2'); } catch (e) { soft = null; }
      return { ok: false, reason: soft ? 'software' : 'none', renderer: rendererOf(soft) };
    }
    var renderer = rendererOf(gl);
    if (SOFTWARE.test(renderer)) return { ok: false, reason: 'software', renderer: renderer };
    return { ok: true, renderer: renderer };
  }

  function rendererOf(gl) {
    if (!gl) return '';
    try {
      var info = gl.getExtension('WEBGL_debug_renderer_info');
      return String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER) || '');
    } catch (e) { return ''; }
  }

  // The steps for a browser: a title and an ordered list.
  var STEPS = {
    chrome: ['Chrome', ['Open Chrome’s menu (⋮) → Settings → System.',
      'Turn on “Use graphics acceleration when available”.', 'Click “Relaunch” (close every Chrome window and open it again).']],
    edge: ['Microsoft Edge', ['Open Edge’s menu (…) → Settings → System and performance.',
      'Turn on “Use graphics acceleration when available”.', 'Click “Restart” (close every Edge window and open it again).']],
    brave: ['Brave', ['Open Brave’s menu → Settings → System.',
      'Turn on “Use graphics acceleration when available”.', 'Click “Relaunch” (close every Brave window and open it again).']],
    opera: ['Opera', ['Open Opera’s settings (Alt+P) → Advanced → Browser → System.',
      'Turn on “Use hardware acceleration when available”.', 'Restart Opera (close every Opera window and open it again).']],
    firefox: ['Firefox', ['Open Firefox’s menu (☰) → Settings → General, and scroll to Performance.',
      'Untick “Use recommended performance settings”.', 'Tick “Use hardware acceleration when available”.',
      'Restart Firefox (close every Firefox window and open it again).']],
    safari: ['Safari', ['Safari has no switch for this. Update macOS and Safari (Apple menu → System Settings → General → Software Update).',
      'Quit Safari completely and open this page again.', 'If it still fails, use Chrome, Firefox or Edge on this computer.']]
  };

  var COMMON = ['Update your graphics drivers (Windows Update, or your graphics card’s website).',
    'On a laptop, plug in the charger and turn off battery saver.',
    'If it still fails, open this page in a different major browser (Chrome, Firefox, Safari or Edge).'];

  // The overlay's HTML for a failed check. `browser` is a key of STEPS or 'unknown' (then: use a supported browser, no steps).
  function messageHtml(result, browser) {
    var why = result.reason === 'none'
      ? 'This browser could not start WebGL (the graphics technology the game needs).'
      : 'This browser is drawing graphics in software instead of on your graphics card, so the game would run very slowly and may fail to connect.';
    var body;
    if (browser === 'unknown') {
      body = '<p>This browser is not one we support. Please open this page in <b>Chrome, Firefox, Safari or Edge</b>, then come back here.</p>';
    } else {
      body = '<p>To turn on hardware acceleration in <b>' + STEPS[browser][0] + '</b>:</p><ol>' +
        STEPS[browser][1].map(function (s) { return '<li>' + s + '</li>'; }).join('') + '</ol>' +
        '<p>Then reload this page.</p>' +
        '<p class="gpu-more">Still stuck?</p><ul>' + COMMON.map(function (s) { return '<li>' + s + '</li>'; }).join('') + '</ul>';
    }
    return '<h1>Hardware acceleration is required</h1><p>' + why + '</p>' + body +
      '<p><button id="gpu-recheck">Check again</button></p>';
  }

  var api = { check: check, browserOf: browserOf, messageHtml: messageHtml, SOFTWARE: SOFTWARE };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.GpuCheck = api;

  // In the page: run now. `window.gpuCheckPassed` tells the loader whether to start Unity (the patch script reads it).
  if (typeof document !== 'undefined' && root === window) {
    var result = check(document);
    window.gpuCheckResult = result;
    window.gpuCheckPassed = result.ok;
    if (!result.ok) {
      var browser = browserOf(navigator.userAgent, !!(navigator.brave));
      var box = document.createElement('div');
      box.id = 'gpu-gate';
      box.innerHTML = '<div class="gpu-card">' + messageHtml(result, browser) + '</div>';
      var show = function () {
        document.body.appendChild(box);
        document.getElementById('gpu-recheck').onclick = function () { location.reload(); };
      };
      if (document.body) show(); else document.addEventListener('DOMContentLoaded', show);
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);
