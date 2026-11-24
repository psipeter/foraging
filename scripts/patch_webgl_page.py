"""Make a Unity WebGL build's index.html robust against canvas resizing (run by deploy_webgl.sh on the copy it publishes).

Resizing the canvas while the game runs (the page's fullscreen button, F11, a window resize, browser zoom) left the drawing black
and unrecoverable in Chrome on Linux (docs/DECISIONS.md, "WebGL: no code-driven fullscreen"). Unity normally keeps the WebGL render
target the size of the canvas element; this makes the render target a fixed WIDTH x HEIGHT (1920 x 1080 by default) (`matchWebGLToCanvasSize = false`) and lets
CSS scale the canvas to the window with a box of the same shape as the picture, so Unity never sees a size change and every participant gets the same
16:9 picture (field of view and resolution do not depend on the window). The Unity footer (title and fullscreen button) is hidden.

It also adds the hardware-acceleration gate (`scripts/webgl_gpu_check.js`, docs/DECISIONS.md "WebGL: hardware acceleration is required"): a browser that
renders WebGL in software gets instructions for its browser and Unity's loader is never added to the page. `--dev` leaves the gate out (development
builds and `scripts/webgl_smoke.mjs`, whose headless browser renders in software).

    python3 scripts/patch_webgl_page.py <index.html> [--width 1920 --height 1080] [--dev]

It fails loudly if the template no longer contains what it replaces (a Unity upgrade); it is idempotent.
"""

import argparse
import os
import sys

MARKER = "<!-- patched by scripts/patch_webgl_page.py -->"
SCRIPT = """  <script>
    // Chrome rejects a pointer-lock request made right after the participant left the lock (Escape) with a SecurityError. The game
    // just asks again on the next click; Unity would show this harmless rejection as an "error occurred" pop-up, so it is swallowed
    // here, before Unity's own handler is registered.
    window.addEventListener('unhandledrejection', function (e) {
      var m = e.reason && (e.reason.message || String(e.reason));
      if (m && /pointer ?lock/i.test(m)) { e.preventDefault(); e.stopImmediatePropagation(); }
    });
  </script>
"""
GATE_CSS = """    #gpu-gate { position: fixed; inset: 0; z-index: 100; background: #14161c; color: #e8e8ee; overflow: auto; font: 18px/1.5 system-ui, sans-serif; display: flex; align-items: center; justify-content: center; -webkit-user-select: text; user-select: text }
    #gpu-gate .gpu-card { max-width: 640px; padding: 32px }
    #gpu-gate h1 { font-size: 28px; margin: 0 0 16px }
    #gpu-gate li { margin: 6px 0 }
    #gpu-gate .gpu-more { color: #aab; margin-bottom: 0 }
    #gpu-gate button { font: inherit; padding: 8px 20px; cursor: pointer }
"""


def gate_script():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "webgl_gpu_check.js"), encoding="utf-8") as f:
        return "  <script>\n" + f.read() + "  </script>\n"


def css(width, height, gate=False):
    # The canvas element is sized to the picture (the largest width x height-shaped box that fits the window, centred), not stretched
    # over the window with object-fit: Unity maps the mouse from the element's box, so a letterboxed picture would offset every click.
    return f"""  <style>
    html, body {{ margin: 0; height: 100%; overflow: hidden; background: #000 }}
    #unity-container.unity-desktop {{ position: fixed !important; left: 0 !important; top: 0 !important; width: 100% !important; height: 100% !important; transform: none !important; display: flex; align-items: center; justify-content: center }}
    #unity-canvas {{ display: block; flex: none; width: min(100vw, calc(100vh * {width} / {height})) !important; height: min(100vh, calc(100vw * {height} / {width})) !important; background: #000 }}
    #unity-canvas {{ outline: none !important; -webkit-tap-highlight-color: transparent }}
    html, body, #unity-container {{ -webkit-user-select: none; user-select: none }}
    #unity-footer {{ display: none }}
{GATE_CSS if gate else ""}  </style>
"""


def patch(html, width, height, gate=True):
    if MARKER in html:
        return html
    swaps = [
        ("<title>Unity Web Player | foraging</title>", "<title>Foraging task</title>"),
        ('<canvas id="unity-canvas" width=960 height=600 tabindex="-1"></canvas>',
         f'<canvas id="unity-canvas" width={width} height={height} tabindex="-1"></canvas>'),
        ("// config.matchWebGLToCanvasSize = false;",
         "config.matchWebGLToCanvasSize = false;   // the render target stays the canvas's width x height attributes; CSS scales it"),
        ('canvas.style.width = "960px";\n        canvas.style.height = "600px";',
         f"// fixed {width}x{height} drawing buffer, scaled to the window by CSS (see the style block in <head>)"),
        ("</head>", MARKER + "\n" + SCRIPT + (gate_script() if gate else "") + css(width, height, gate) + "</head>"),
    ]
    if gate:
        # Unity's loader is added to the page only when the check passed (the check ran in <head>, before this line).
        swaps.append(("document.body.appendChild(script);", "if (window.gpuCheckPassed) document.body.appendChild(script);"))
    for old, new in swaps:
        if html.count(old) != 1:
            sys.exit(f"patch_webgl_page: expected exactly one occurrence of {old!r} in the page, found {html.count(old)} "
                     "(has the Unity page template changed?)")
        html = html.replace(old, new)
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("page")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--dev", action="store_true", help="no hardware-acceleration gate (development builds, the software-GL smoke test)")
    args = parser.parse_args()
    with open(args.page, encoding="utf-8") as f:
        html = f.read()
    patched = patch(html, args.width, args.height, gate=not args.dev)
    if patched != html:
        with open(args.page, "w", encoding="utf-8") as f:
            f.write(patched)
        print(f"patched {args.page} ({args.width}x{args.height} fixed drawing buffer)")


if __name__ == "__main__":
    main()
