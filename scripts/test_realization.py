"""Does what a configuration intends show up in what the generators produce? These tests state a configuration (synthetic.py, a tiles world built on the frozen
session FIX_T0) and look at the world that comes out: which features vary, what each pays, how noisy a fruit is. They are not
about one shipped session, so they hold for any experiment built from the same pieces."""

import numpy as np
import pytest

import synthetic
from world import FEATURES, generate_world, session_features

CONFIGS = {
    "all three, unequal, mixed directions": dict(visible=FEATURES, weights={"shape": 0.5, "color": 0.3, "moisture": 0.2}, direction={"color": 1}),
    "shape alone": dict(visible=("shape",), weights={"shape": 1.0}),
    "two visible, the second pays": dict(visible=("shape", "color"), weights={"color": 1.0}, direction={"color": 1}),
    "moisture pays, others visible": dict(visible=FEATURES, weights={"moisture": 1.0}),
    "shape and moisture pay": dict(visible=FEATURES, weights={"shape": 0.6, "moisture": 0.4}),
    "moisture alone": dict(visible=("moisture",), weights={"moisture": 1.0}, direction={"moisture": 1}),
}
_WORLDS = {}


def world_of(label, seed=11):
    if (label, seed) not in _WORLDS:
        _WORLDS[(label, seed)] = generate_world(synthetic.session(**CONFIGS[label]), seed)
    return _WORLDS[(label, seed)]


def attributes(w):
    return {"shape": w.shape, "color": w.color, "moisture": w.moisture}


def slopes(w):
    """Least-squares slope of the bush values on the three attributes (exact for a linear reward)."""
    x = np.column_stack([*attributes(w).values(), np.ones(w.n)])
    return dict(zip(FEATURES, np.linalg.lstsq(x, w.value, rcond=None)[0][:3]))


@pytest.mark.parametrize("label", CONFIGS)
def test_a_feature_varies_across_bushes_exactly_when_it_is_visible(label):
    w, visible = world_of(label), CONFIGS[label]["visible"]
    for feature, values in attributes(w).items():
        assert (np.ptp(values) > 0.5) == (feature in visible), f"{feature}: range {np.ptp(values):.2f}"          # visible: spread over the range; hidden: one value
        if feature in visible:
            assert abs(np.mean(values) - 0.5) < 0.12 or feature == "moisture"                                    # (moisture is the terrain's, not uniform)


@pytest.mark.parametrize("label", CONFIGS)
def test_each_feature_pays_what_the_configuration_says_in_the_direction_it_says(label):
    w, cfg = world_of(label), CONFIGS[label]
    got = slopes(w)
    for feature in FEATURES:
        sign = -1.0 if cfg.get("direction", {}).get(feature, 0) else 1.0
        intended = sign * synthetic.REWARD_SCALE * cfg["weights"].get(feature, 0.0)
        if np.ptp(attributes(w)[feature]) > 0.5:                                                                 # a hidden feature cannot show a slope
            assert got[feature] == pytest.approx(intended, abs=1e-3), feature


@pytest.mark.parametrize("label", CONFIGS)
def test_a_fruit_is_its_bush_value_plus_noise_of_the_stated_size(label):
    w = world_of(label)
    rich = w.value > 2.5                                                                                         # far from the floor at 0, which clips the noise
    assert rich.sum() > 20
    noise = w.fruit_reward[rich] - w.value[rich, None]
    assert abs(noise.mean()) < 0.1 and noise.std() == pytest.approx(0.6, rel=0.2)                               # (rounding to whole points adds a little, more where the bushes' values sit on a few levels, as a tile's moisture does)


@pytest.mark.parametrize("label", CONFIGS)
def test_the_session_declares_the_features_the_configuration_makes_visible_and_rewarded(label):
    cfg = CONFIGS[label]
    declared = session_features(synthetic.session(**cfg))
    assert {f for f, d in declared.items() if d["visible"]} == set(cfg["visible"])
    assert {f for f, d in declared.items() if d["rewarded"]} == set(cfg["weights"])
