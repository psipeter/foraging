"""Does what a configuration intends show up in what the generators produce? These tests state a configuration (synthetic.py, a tiles world built on the frozen
session FIX_T0) and look at the world that comes out: which features vary, what the value map pays, how noisy a fruit is. They are not
about one shipped session, so they hold for any experiment built from the same pieces."""

import numpy as np
import pytest

import synthetic
import value_maps
from world import FEATURES, generate_world

CONFIGS = {
    "all three vary, the additive rung": dict(visible=FEATURES, valuemap=value_maps.wide_corner((1.0, 0.0), shape_share=0.7)),
    "shape alone varies": dict(visible=("shape",), valuemap=synthetic.feature_only("shape", high=False)),
    "two vary, colour alone pays": dict(visible=("shape", "color"), valuemap=synthetic.feature_only("color")),
    "two vary, a turned Gaussian pays": dict(visible=("shape", "color"), valuemap=value_maps.nonseparable(3)),
    "moisture alone varies": dict(visible=("moisture",)),
}
_WORLDS = {}


def world_of(label, seed=11):
    if (label, seed) not in _WORLDS:
        _WORLDS[(label, seed)] = generate_world(synthetic.session(**CONFIGS[label]), seed)
    return _WORLDS[(label, seed)]


def attributes(w):
    return {"shape": w.shape, "color": w.color, "moisture": w.moisture}


@pytest.mark.parametrize("label", CONFIGS)
def test_a_feature_varies_across_bushes_exactly_when_it_is_visible(label):
    w, visible = world_of(label), CONFIGS[label]["visible"]
    for feature, values in attributes(w).items():
        assert (np.ptp(values) > 0.5) == (feature in visible), f"{feature}: range {np.ptp(values):.2f}"          # visible: spread over the range; hidden: one value
        if feature in visible:
            assert abs(np.mean(values) - 0.5) < 0.12 or feature == "moisture"                                    # (moisture is the terrain's, not uniform)


@pytest.mark.parametrize("label", CONFIGS)
def test_a_fruit_is_its_bush_value_plus_noise_of_the_stated_size(label):
    w = world_of(label)
    rich = w.value > 1.5                                                                                         # far from the floor at 0, which clips the noise
    assert rich.sum() > 20
    noise = w.fruit_reward[rich] - w.value[rich, None]
    assert abs(noise.mean()) < 0.1 and noise.std() == pytest.approx(0.6, rel=0.2)                               # (rounding to whole points adds a little, more where the bushes' values sit on a few levels, as a tile's moisture does)
