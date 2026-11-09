"""Spatial evenness: the metrics, the tile-balanced assignment, the swap step and the world switch."""

import numpy as np

import spatial
import synthetic
import world


def PLAIN(**extra):
    """A session of a stated plain configuration (both features pay, moisture decoration) on the template asset."""
    return world.load_session(synthetic.TEMPLATE, **{**synthetic.overrides(synthetic.FEATURES, {"shape": 0.6, "color": 0.4}, moisture_is_feature=False), **extra})


def lattice(n=600, half=300.0, seed=0):
    rng = np.random.default_rng(seed)
    return rng.uniform(-half, half, (n, 2))


def test_a_random_assignment_has_cost_near_one_and_a_clustered_one_has_more():
    pos = lattice()
    rng = np.random.default_rng(1)
    costs = [spatial.metrics(pos, rng.uniform(0, 1, len(pos)), half=300.0)["cost"] for _ in range(6)]
    assert 0.8 < np.mean(costs) < 1.2
    clustered = pos[:, 0] / 600.0 + 0.5                                                  # a gradient: every disk differs from the others
    assert spatial.metrics(pos, clustered, half=300.0)["cost"] > 3.0
    assert spatial.metrics(pos, clustered, half=300.0)[spatial.SCALES[0]]["moran"] > 0.3


def test_tiles_keep_the_values_and_lower_the_cost_and_swaps_lower_it_further():
    pos, rng = lattice(), np.random.default_rng(2)
    values = rng.uniform(0, 1, len(pos))
    base = spatial.metrics(pos, values, half=300.0)["cost"]
    index = spatial.tile_assignment(pos, values, np.random.default_rng(3), half=300.0)
    assert sorted(index) == list(range(len(pos)))                                         # every record is dealt exactly once
    tiled = spatial.metrics(pos, values[index], half=300.0)["cost"]
    assert tiled < 0.75 * base
    swapped, cost = spatial.optimise(pos, values, np.random.default_rng(4), half=300.0, start=index, steps=8000, target=0.1)
    assert sorted(swapped) == list(range(len(pos)))
    assert spatial.metrics(pos, values[swapped], half=300.0)["cost"] < tiled - 0.05
    assert abs(spatial.metrics(pos, values[swapped], half=300.0)["cost"] - cost) < 1e-6    # the bookkeeping of the swap step matches the metric


def test_off_is_the_identity_and_the_assignment_is_deterministic():
    pos, values = lattice(200), np.random.default_rng(5).uniform(0, 1, 200)
    assert np.array_equal(spatial.balance(pos, values, np.random.default_rng(0), spatial.OFF), np.arange(200))
    a = spatial.balance(pos, values, np.random.default_rng(7), spatial.TILES_AND_SWAPS, half=300.0, steps=500)
    b = spatial.balance(pos, values, np.random.default_rng(7), spatial.TILES_AND_SWAPS, half=300.0, steps=500)
    assert np.array_equal(a, b)


def test_the_world_switch_rearranges_records_without_changing_them_and_off_changes_nothing():
    off = world.generate_world(PLAIN(spatial_balance=0), 3)
    tiles = world.generate_world(PLAIN(spatial_balance=1), 3)
    assert np.array_equal(off.pos, tiles.pos) and np.array_equal(off.moisture, tiles.moisture)
    assert np.allclose(np.sort(off.shape), np.sort(tiles.shape)) and np.allclose(np.sort(off.value), np.sort(tiles.value))
    assert spatial.metrics(tiles.pos, tiles.value)["cost"] < spatial.metrics(off.pos, off.value)["cost"]
    assert world.check_values(PLAIN(spatial_balance=1))["spatialBalance"] == 1.0
    assert "spatialBalance" not in world.check_values(PLAIN(spatial_balance=0))     # (older world files stay identical)
    assert world.check_values(PLAIN(spatial_balance=2))["spatialBalance"] == 2.0


def test_the_practice_session_balances_its_random_values():
    p = world.load_session(synthetic.TEMPLATE, **{**synthetic.overrides(weights={"shape": 1.0}), "random_bush_value_range": (1.0, 3.0), "spatial_balance": 1})
    tiles, off = world.generate_world(p, 5), world.generate_world(world.load_session(synthetic.TEMPLATE, **{**synthetic.overrides(weights={"shape": 1.0}), "random_bush_value_range": (1.0, 3.0), "spatial_balance": 0}), 5)
    assert np.allclose(np.sort(tiles.value), np.sort(off.value))
    assert spatial.metrics(tiles.pos, tiles.value)["cost"] < spatial.metrics(off.pos, off.value)["cost"]   # the random value moves with its record


def test_a_moisture_reward_is_balanced_on_the_totals_and_with_no_offset_nothing_changes():
    rf = synthetic.reward_function({"shape": 0.5, "color": 0.5, "moisture": 0.5})
    pays = PLAIN(reward_function=rf, spatial_balance=2)
    off, swaps = world.generate_world(PLAIN(reward_function=rf, spatial_balance=0), 5), world.generate_world(pays, 5)
    assert np.allclose(np.sort(off.shape), np.sort(swaps.shape)) and np.allclose(np.sort(off.color), np.sort(swaps.color))      # the same records, dealt elsewhere
    assert np.allclose(swaps.moisture[np.argsort(swaps.pos[:, 0])], world.generate_world(pays, 5).moisture[np.argsort(swaps.pos[:, 0])])
    assert spatial.metrics(swaps.pos, swaps.value)["cost"] < 0.8 * spatial.metrics(off.pos, off.value)["cost"]                    # the totals, moisture included, are more even
    pos, values = lattice(), np.random.default_rng(3).uniform(0, 1, 600)
    a, _ = spatial.optimise(pos, values, np.random.default_rng(4), half=300.0, steps=3000)
    b, _ = spatial.optimise(pos, values, np.random.default_rng(4), half=300.0, steps=3000, offset=np.zeros(600))
    assert (a == b).all()                                                                                                       # a zero offset is no offset


# ---- feature balancing: every visible feature balanced the same way, independently ----

def _balanced(seed, weights, **extra):
    plain = synthetic.overrides(synthetic.FEATURES, weights, moisture_is_feature=False)
    return world.generate_world(world.load_session(synthetic.TEMPLATE, **{**plain, "feature_balance": 2, "spatial_balance": 0, **extra}), seed)


def _ratio(w, v, scale=60.0):
    return spatial.local_ratio(spatial.Disks(w.pos, scale, float(w.params.world_half_extent)), v)


def test_feature_balancing_treats_every_visible_feature_the_same_whichever_one_pays():
    """The leak of balancing the reward is that the rewarded feature is much more regular than the others (a local ratio near 0.45 against 1.0). Balancing each visible feature
    on its own leaves no such difference: over several worlds the rewarded feature is as even as the unrewarded one, and both are more even than chance."""
    gaps = []
    for seed in (5, 6, 7, 8, 9):
        for pays, other in (("shape", "color"), ("color", "shape")):
            w = _balanced(seed, {pays: 1.0})
            a, b = _ratio(w, getattr(w, pays)), _ratio(w, getattr(w, other))
            assert a < 0.95 and b < 0.95
            gaps.append(a - b)
    assert abs(np.mean(gaps)) < 0.06 and np.std(gaps) < 0.15, (np.mean(gaps), np.std(gaps))        # no systematic difference, only the swaps' own variation
    off = world.generate_world(world.load_session(synthetic.TEMPLATE, **synthetic.overrides(synthetic.FEATURES, {"shape": 1.0}, moisture_is_feature=False)), 5)
    assert abs(_ratio(off, off.shape) - 1.0) < 0.15 and abs(_ratio(off, off.color) - 1.0) < 0.15       # (the unbalanced world is at chance)


def test_feature_balancing_keeps_the_values_and_the_independence_of_the_features_and_of_moisture():
    w = _balanced(6, {"shape": 0.5, "color": 0.3, "moisture": 0.2})
    off = world.generate_world(world.load_session(synthetic.TEMPLATE, **synthetic.overrides(synthetic.FEATURES, {"shape": 0.5, "color": 0.3, "moisture": 0.2}, moisture_is_feature=False)), 6)
    assert np.array_equal(w.pos, off.pos) and np.allclose(np.sort(w.shape), np.sort(off.shape)) and np.allclose(np.sort(w.color), np.sort(off.color))   # the same values, dealt elsewhere
    assert abs(np.corrcoef(w.shape, w.color)[0, 1]) < 0.12 and abs(np.corrcoef(w.moisture, w.shape)[0, 1]) < 0.12 and abs(np.corrcoef(w.moisture, w.color)[0, 1]) < 0.12


def test_the_target_sets_how_even_the_features_are_and_the_reward_is_evened_when_shape_and_colour_pay():
    loose, tight = _balanced(7, {"shape": 0.5, "color": 0.5}, feature_balance_target=0.9), _balanced(7, {"shape": 0.5, "color": 0.5}, feature_balance_target=0.5)
    assert _ratio(tight, tight.shape) < _ratio(loose, loose.shape) < 1.0
    off = world.generate_world(world.load_session(synthetic.TEMPLATE, **synthetic.overrides(synthetic.FEATURES, {"shape": 0.5, "color": 0.5}, moisture_is_feature=False)), 7)
    assert spatial.metrics(tight.pos, tight.value)["cost"] < 0.85 * spatial.metrics(off.pos, off.value)["cost"]               # the reward is more even without being balanced itself


def test_feature_balancing_is_in_the_world_check_and_cannot_be_combined_with_reward_balancing():
    import pytest
    v = world.check_values(world.load_session(synthetic.TEMPLATE, **{**synthetic.overrides(), "feature_balance": 2}))
    assert v["featureBalance"] == 2.0 and v["featureBalanceTarget"] == 0.7 and v["featureBalanceScales.count"] == 4.0
    assert "featureBalance" not in world.check_values(world.load_session(synthetic.TEMPLATE, **synthetic.overrides()))
    with pytest.raises(ValueError):
        world.generate_world(world.load_session(synthetic.TEMPLATE, **{**synthetic.overrides(), "feature_balance": 2, "spatial_balance": 2}), 1)
