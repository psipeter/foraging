"""The fruit colour ramp: its stops are even perceptual steps, and the SessionConfig assets carry exactly what the script generates."""

import re
from pathlib import Path

import numpy as np

import fruit_ramp

ASSETS = Path(__file__).resolve().parent.parent / "Assets" / "ScriptableObjects" / "SessionConfig"


def test_ramp_has_even_steps_in_gamut_and_no_red():
    lin = fruit_ramp.ramp()
    assert len(lin) == fruit_ramp.STOPS and lin.min() >= -1e-6 and lin.max() <= 1 + 1e-6
    gaps = [fruit_ramp.distance(lin[i], lin[i + 1]) for i in range(len(lin) - 1)]
    assert max(gaps) - min(gaps) < 0.05 * np.mean(gaps)            # equal perceptual steps by construction
    lab = fruit_ramp.oklab(lin)
    chroma, hue = np.hypot(lab[:, 1], lab[:, 2]), np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360
    assert not np.any((chroma > 0.06) & ((hue >= 345) | (hue <= 35)))   # no red (OKLab hue 345 to 35 degrees)


def test_smallest_step_is_visible_for_every_vision_type():
    scores = fruit_ramp.score(fruit_ramp.ramp())
    assert min(scores[v] for v in ("normal", "protan", "deutan", "tritan")) > 3.0


def test_assets_carry_the_generated_stops():
    for path in sorted(ASSETS.glob("*.asset")):
        text = path.read_text()
        expected = np.round(fruit_ramp.to_srgb(fruit_ramp.ramp()), 4)
        stops = re.findall(r"- \{r: ([\d.e-]+), g: ([\d.e-]+), b: ([\d.e-]+), a: 1\}", text.split("fruitColorRamp:")[1].split("\n  fruitColorPreservation")[0])
        assert len(stops) == fruit_ramp.STOPS, f"{path.name} has {len(stops)} fruit colour stops"
        assert np.allclose(np.array(stops, float), expected, atol=2e-3), f"{path.name}: fruit colour ramp is stale; see scripts/fruit_ramp.py --stops"


def test_hue_arc_ramps_have_constant_lightness_even_steps_and_disjoint_hues():
    hues = {}
    for name in fruit_ramp.ARCS:
        lin = fruit_ramp.ramp(name)
        lab = fruit_ramp.oklab(lin)
        assert len(lin) == fruit_ramp.STOPS and lin.min() >= -1e-6 and lin.max() <= 1 + 1e-6
        assert np.ptp(lab[:, 0]) < 0.01                                     # lightness carries no information
        gaps = [fruit_ramp.distance(lin[i], lin[i + 1]) for i in range(len(lin) - 1)]
        assert max(gaps) - min(gaps) < 0.15 * np.mean(gaps)                 # equal perceptual steps (one chord is shorter where the gamut edge has a cusp)
        assert fruit_ramp.score(lin)["normal"] > 3.0                        # the smallest 10% step is visible
        hues[name] = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360
    warm, cool = hues["warm_arc"], hues["cool_arc"]
    wheel_gap = lambda a, b: np.abs((a[:, None] - b[None] + 180) % 360 - 180).min()
    assert wheel_gap(warm, cool) > 25                                       # the two sets share no hues
