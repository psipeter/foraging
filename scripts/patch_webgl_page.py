"""Make a Unity WebGL build's index.html robust against canvas resizing (run by deploy_webgl.sh on the copy it publishes).

Resizing the canvas while the game runs (the page's fullscreen button, F11, a window resize, browser zoom) left the drawing black
and unrecoverable in Chrome on Linux (docs/DECISIONS.md, "WebGL: no code-driven fullscreen"). Unity normally keeps the WebGL render
target the size of the canvas element; this makes the render target a fixed WIDTH x HEIGHT (`matchWebGLToCanvasSize = false`) and lets
CSS scale the canvas to the window with `object-fit: contain`, so Unity never sees a size change and every participant gets the same
16:9 picture (field of view and resolution do not depend on the window). The Unity footer (title and fullscreen button) is hidden.

    python3 scripts/patch_webgl_page.py <index.html> [--width 1280 --height 720]

It fails loudly if the template no longer contains what it replaces (a Unity upgrade); it is idempotent.
"""

import argparse
import sys

MARKER = "<!-- patched by scripts/patch_webgl_page.py -->"
CSS = """  <style>
    html, body { margin: 0; height: 100%; overflow: hidden; background: #000 }
    #unity-container.unity-desktop { position: fixed !important; left: 0 !important; top: 0 !important; width: 100% !important; height: 100% !important; transform: none !important }
    #unity-canvas { display: block; width: 100vw !important; height: 100vh !important; object-fit: contain; background: #000 }
    #unity-footer { display: none }
  </style>
"""


def patch(html, width, height):
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
        ("</head>", MARKER + "\n" + CSS + "</head>"),
    ]
    for old, new in swaps:
        if html.count(old) != 1:
            sys.exit(f"patch_webgl_page: expected exactly one occurrence of {old!r} in the page, found {html.count(old)} "
                     "(has the Unity page template changed?)")
        html = html.replace(old, new)
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("page")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    with open(args.page, encoding="utf-8") as f:
        html = f.read()
    patched = patch(html, args.width, args.height)
    if patched != html:
        with open(args.page, "w", encoding="utf-8") as f:
            f.write(patched)
        print(f"patched {args.page} ({args.width}x{args.height} fixed drawing buffer)")


if __name__ == "__main__":
    main()
