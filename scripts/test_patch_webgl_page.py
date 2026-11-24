"""The WebGL page patch (patch_webgl_page.py): the hardware-acceleration gate is embedded and guards Unity's loader, --dev leaves it out, patching twice changes nothing, and the gate's detector passes its node test."""

import shutil
import subprocess
from pathlib import Path

import pytest

import patch_webgl_page as pwp


def built_page():
    """A page shaped like Unity's built index.html (the template's text outside its `{{{ }}}` and `#if` markers)."""
    return """<!DOCTYPE html><html><head>
<title>Unity Web Player | foraging</title></head><body>
<canvas id="unity-canvas" width=960 height=600 tabindex="-1"></canvas>
<script>
// config.matchWebGLToCanvasSize = false;
canvas.style.width = "960px";
        canvas.style.height = "600px";
document.body.appendChild(script);
</script></body></html>"""


def test_the_gate_guards_the_loader_and_is_idempotent():
    out = pwp.patch(built_page(), 1920, 1080)
    assert "if (window.gpuCheckPassed) document.body.appendChild(script);" in out
    assert "GpuCheck" in out and "#gpu-gate" in out
    assert pwp.patch(out, 1920, 1080) == out


def test_dev_leaves_the_gate_out():
    out = pwp.patch(built_page(), 1920, 1080, gate=False)
    assert "gpuCheck" not in out and "gpu-gate" not in out
    assert "document.body.appendChild(script);" in out


def test_the_patch_fails_loudly_when_the_template_changed():
    with pytest.raises(SystemExit):
        pwp.patch(built_page().replace("document.body.appendChild(script);", ""), 1920, 1080)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_detector_and_its_messages():
    result = subprocess.run(["node", str(Path(pwp.__file__).with_name("test_webgl_gpu_check.mjs"))], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
