"""Milestone 2 of the new session structure: a feature that does not vary, the random per-bush value of the practice session, and moisture as
decoration (out of the Interlude's feature gap and out of what the simulated agents sense)."""

import numpy as np

import world
from interlude import feature_gap, feature_weights, generate_interlude
from world import generate_world, moisture_matters
from world import load_session as _load_session


def load_session(name="S2", **overrides):
    """A session as the ladder does not set it: both features vary and no random reward, unless overridden (the ladder's own sessions
    have identical shapes or colours, which these tests would otherwise inherit)."""
    return _load_session(name, **{"shape_varies": True, "color_varies": True, "random_bush_value_range": (0.0, 0.0), "spatial_balance": 0, **overrides})


def moisture_weight(w):
    """The reward function of S2 with a moisture reward weight `w`."""
    rf = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _load_session("S2").reward_function.items()}
    rf["moistureComponent"]["weight"] = w
    return rf


def test_old_assets_get_the_new_fields_by_default(tmp_path):
    text = world.session_asset_path("S2").read_text()
    old = "\n".join(line for line in text.split("\n") if not line.strip().startswith(("shapeVaries", "colorVaries", "shapeWhenFixed", "colorWhenFixed", "randomBushValueRange")))
    path = tmp_path / "Old.asset"                              # an asset file saved before the fields existed
    path.write_text(old)
    p = _load_session(str(path))
    assert p.shape_varies is True and p.color_varies is True and tuple(p.random_bush_value_range) == (0.0, 0.0) and p.shape_when_fixed == 0.5


def test_a_feature_that_does_not_vary_is_constant_and_nothing_else_moves():
    base = generate_world(load_session("S2"), 1)
    flat = generate_world(load_session("S2", shape_varies=False, color_varies=False), 1)
    assert np.all(flat.shape == 0.5) and np.all(flat.color == 0.5)
    assert np.array_equal(base.pos, flat.pos) and np.array_equal(base.moisture, flat.moisture)         # the other streams did not move
    assert np.allclose(flat.canopy_radius, flat.canopy_radius[0])                                    # identical canopies
    only_color = generate_world(load_session("S2", shape_varies=False), 1)
    assert np.array_equal(only_color.color, base.color)                                              # the colour draws are the same ones


def test_random_bush_value_is_independent_of_the_attributes_and_leaves_other_worlds_unchanged():
    base = generate_world(load_session("S2"), 2)
    rnd = generate_world(load_session("S2", random_bush_value_range=(1.0, 3.0)), 2)
    assert np.array_equal(base.pos, rnd.pos) and np.array_equal(base.shape, rnd.shape)
    extra = rnd.value - base.value
    assert extra.min() >= 1.0 and extra.max() <= 3.0 and extra.std() > 0.4                        # a spread of about 0.58
    for attr in (rnd.shape, rnd.color, rnd.moisture):
        assert abs(np.corrcoef(extra, attr)[0, 1]) < 0.15                                        # no attribute predicts it
    assert np.array_equal(generate_world(load_session("S2"), 2).fruit_reward, base.fruit_reward)  # off by default: nothing moved


def test_check_values_carry_the_new_fields_only_when_they_differ_from_the_default():
    default = world.check_values(load_session("S2"))
    assert not any(k in default for k in ("shapeVaries", "colorVaries", "randomBushValueRange.min", "randomBushValueRange.max"))   # old world files stay identical
    v = world.check_values(load_session("S2", shape_varies=False, random_bush_value_range=(1.0, 3.0)))
    assert v["shapeVaries"] == 0.0 and "colorVaries" not in v
    assert v["randomBushValueRange.min"] == 1.0 and v["randomBushValueRange.max"] == 3.0


def test_moisture_matters_follows_the_reward_weight():
    decoration, pays = load_session("S2", reward_function=moisture_weight(0.0)), load_session("S2", reward_function=moisture_weight(1.5))
    assert not moisture_matters(decoration) and moisture_matters(pays)


def test_session_features_declare_what_is_visible_and_what_pays():
    from world import session_features
    f = session_features(load_session("S2", color_varies=False, reward_function=moisture_weight(0.0)))
    assert (f["shape"]["visible"], f["color"]["visible"], f["moisture"]["visible"]) == (True, False, False)     # a decoration moisture is not declared
    assert f["shape"]["rewarded"] == (f["shape"]["relevance"] > 0.0) and not f["moisture"]["rewarded"]
    pays = session_features(load_session("S2", reward_function=moisture_weight(1.5)))
    assert pays["moisture"]["visible"] and pays["moisture"]["rewarded"] and pays["moisture"]["relevance"] == 1.5
    assert session_features(load_session("S2", reward_function=moisture_weight(0.0), moisture_varies=True))["moisture"]["visible"]   # declared, though it pays nothing


def test_feature_gap_counts_only_the_channels_that_vary_and_pay():
    a, b = {"shape": 0.0, "color": 0.0, "moisture": 0.0}, {"shape": 1.0, "color": 0.0, "moisture": 1.0}
    assert feature_gap(a, b) == (2 / 3) ** 0.5                                                      # the default: all three channels
    w = feature_weights(load_session("S2", color_varies=False, reward_function=moisture_weight(0.0)))   # moisture is decoration
    assert w == {"shape": 1.0, "color": 0.0, "moisture": 0.0}
    assert feature_gap(a, b, w) == 1.0                                                              # only the shape counts


def test_a_random_reward_interlude_has_no_correct_side_and_constant_flat_features():
    sidecar, params, _ = generate_interlude("P_Interlude", pool_samples=60_000, random_bush_value_range=(1.0, 3.0), shape_varies=False, color_varies=True)
    assert all(t["correct"] == "either" for t in sidecar["trials"])
    assert set(sidecar["shape"]) == {0.5} and len(set(sidecar["color"])) > 1
