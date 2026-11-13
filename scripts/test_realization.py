"""Does what a configuration intends show up in what the generators produce? These tests state a configuration (synthetic.py) and look at the
world that comes out: which features vary, what each pays, how noisy a fruit is. They are not
about one shipped session, so they hold for any experiment built from the same pieces; the last test applies them to every built design."""

import importlib
import pkgutil

import numpy as np
import pytest

import design
import synthetic
from world import FEATURES, generate_world, load_session, session_features

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
    assert abs(noise.mean()) < 0.05 and noise.std() == pytest.approx(0.6, rel=0.12)                              # (rounding to whole points adds a little)


@pytest.mark.parametrize("label", CONFIGS)
def test_the_session_declares_the_features_the_configuration_makes_visible_and_rewarded(label):
    cfg = CONFIGS[label]
    declared = session_features(synthetic.session(**cfg))
    assert {f for f, d in declared.items() if d["visible"]} == set(cfg["visible"])
    assert {f for f, d in declared.items() if d["rewarded"]} == set(cfg["weights"])


def test_balancing_the_reward_makes_it_more_even_whichever_features_pay():
    import spatial
    """(A reward only the terrain decides, such as moisture alone, has nothing to deal, so it is not among them.)"""
    for label in ("all three, unequal, mixed directions", "shape and moisture pay"):
        on = generate_world(synthetic.session(**CONFIGS[label], spatial_balance=2), 11)
        off = world_of(label)
        assert spatial.metrics(on.pos, on.value)["cost"] < 0.8 * spatial.metrics(off.pos, off.value)["cost"]


# ---- every built design ----

def built_designs():
    for info in pkgutil.iter_modules(design.__path__):
        module = importlib.import_module(f"design.{info.name}")
        if hasattr(module, "instances"):
            yield module


@pytest.mark.slow
def test_every_built_design_realises_its_stated_visibility_weights_and_directions():
    """Each design instance's `design` dict says which features are visible, what each pays (`weights`, shares summing to one) and in which direction;
    the world generated from its asset must show exactly that. (Skipped for a design whose assets have not been built.)"""
    checked = 0
    for module in built_designs():
        if not hasattr(module, "REWARD_SCALE"):
            continue
        for inst in module.instances():
            if not {"visible", "weights", "direction"} <= set(inst.design):
                continue
            try:
                p = load_session(inst.name)
            except FileNotFoundError:
                continue
            w = generate_world(p, int(p.world_seed))
            got = slopes(w)
            for f in FEATURES:
                varies = np.ptp(attributes(w)[f]) > 0.5
                assert varies == (f in inst.design["visible"]), f"{inst.name} {f}"
                if varies:
                    sign = -1.0 if inst.design["direction"][f] else 1.0
                    assert got[f] == pytest.approx(sign * module.REWARD_SCALE * inst.design["weights"].get(f, 0.0), abs=2e-3), f"{inst.name} {f}"
            checked += 1
    if not checked:
        pytest.skip("no built design states visible / weights / direction in its design dicts (FOR does not yet)")
