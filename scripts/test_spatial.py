"""Spatial evenness: the metrics, the tile-balanced assignment, the swap step and the world switch."""

import numpy as np

import spatial
import world


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
    off = world.generate_world(world.load_session("S2", spatial_balance=0), 3)
    tiles = world.generate_world(world.load_session("S2", spatial_balance=1), 3)
    assert np.array_equal(off.pos, tiles.pos) and np.array_equal(off.moisture, tiles.moisture)
    assert np.allclose(np.sort(off.shape), np.sort(tiles.shape)) and np.allclose(np.sort(off.value), np.sort(tiles.value))
    assert spatial.metrics(tiles.pos, tiles.value)["cost"] < spatial.metrics(off.pos, off.value)["cost"]
    assert world.check_values(world.load_session("S2", spatial_balance=1))["spatialBalance"] == 1.0
    assert "spatialBalance" not in world.check_values(world.load_session("S2", spatial_balance=0))     # (older world files stay identical)
    assert world.check_values(world.load_session("S2"))["spatialBalance"] == 2.0                       # the ladder's assets balance (TilesAndSwaps)


def test_the_practice_session_balances_its_random_values_and_a_moisture_reward_is_refused():
    p = world.load_session("P", spatial_balance=1)
    tiles, off = world.generate_world(p, 5), world.generate_world(world.load_session("P", spatial_balance=0), 5)
    assert np.allclose(np.sort(tiles.value), np.sort(off.value))
    assert spatial.metrics(tiles.pos, tiles.value)["cost"] < spatial.metrics(off.pos, off.value)["cost"]   # the random value moves with its record
    import pytest
    from legacy_sessions import legacy
    with pytest.raises(ValueError):
        world.generate_world(world.load_session("S2", **{**legacy("S3"), "spatial_balance": 1}), 1)
