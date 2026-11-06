"""The fruit colour ramp: its stops are even perceptual steps, and the SessionConfig assets carry exactly what the script generates."""

import re
from pathlib import Path

import numpy as np

import fruit_ramp

ASSETS = Path(__file__).resolve().parent.parent / "Assets" / "ScriptableObjects" / "SessionConfig"


def test_ramp_has_even_steps_in_gamut():
    lin = fruit_ramp.ramp()
    assert len(lin) == fruit_ramp.STOPS and lin.min() >= -1e-6 and lin.max() <= 1 + 1e-6
    gaps = [fruit_ramp.distance(lin[i], lin[i + 1]) for i in range(len(lin) - 1)]
    assert max(gaps) - min(gaps) < 0.05 * np.mean(gaps)            # equal perceptual steps by construction


def test_smallest_step_is_visible_for_every_vision_type():
    scores = fruit_ramp.score(fruit_ramp.ramp())
    assert min(scores[v] for v in ("normal", "protan", "deutan", "tritan")) > 2.5


def test_assets_carry_the_generated_stops():
    allowed = {name: np.round(fruit_ramp.to_srgb(fruit_ramp.ramp(name)), 4) for name in (fruit_ramp.CHOSEN,)}
    for path in sorted(ASSETS.glob("*.asset")):
        text = path.read_text()
        stops = re.findall(r"- \{r: ([\d.e-]+), g: ([\d.e-]+), b: ([\d.e-]+), a: 1\}", text.split("fruitColorRamp:")[1].split("\n  fruitColorPreservation")[0])
        assert len(stops) == fruit_ramp.STOPS, f"{path.name} has {len(stops)} fruit colour stops"
        assert any(np.allclose(np.array(stops, float), e, atol=2e-3) for e in allowed.values()), f"{path.name}: fruit colour ramp is stale; see scripts/fruit_ramp.py --stops"
