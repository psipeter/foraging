"""The tiles world (tiles.py): the hexagonal ground, the clusters in the middle of the tiles, and how the tiles' features are dealt.

Tests state their configuration (`synthetic.session`: the wide corner Gaussian pays, a tiles layout and assignment) and do not name a shipped session.
"""

import numpy as np
import pytest

import synthetic
import tiles
import world

SEEDS = range(6)


def tile_params(**extra):
    return synthetic.session(visible=("shape", "color"), layout="tiles", assignment="tiles", **{"moisture_varies": True, **extra})


def tile_world(seed=1, **extra):
    return world.generate_world(tile_params(**extra), seed)


def tile_of(w):
    i, j = w.terrain.tiles.nearest(w.pos[:, 0], w.pos[:, 1])
    return np.unique(i * 1_000_003 + j, return_inverse=True)[1]


def test_the_ground_is_flat_at_a_tile_centre_and_has_the_tiles_level():
    w = tile_world()
    grid = w.terrain.tiles
    for i, j, c in grid.tile_centres()[::7]:
        assert abs(grid.moisture(c[0], c[1]) - grid.levels[i + grid.k, j + grid.k]) < 1e-6


def test_the_ground_has_no_jump_across_a_tile_edge():
    grid = tile_world().terrain.tiles
    x = np.linspace(-150, 150, 1201)                                  # 0.25 units apart, across several tiles and their vertices
    for z in (-90.0, 0.0, 77.0):
        step = np.abs(np.diff(grid.moisture(x, np.full_like(x, z))))
        assert step.max() < 0.05                                      # the steepest part of a unit change over the ramp is about 0.11 per unit


def test_neighbouring_tiles_mostly_differ_in_level():
    grid = tile_world().terrain.tiles
    n = 2 * grid.k + 1
    same = total = 0
    for i in range(1, n - 1):
        for j in range(1, n - 1):
            for di, dj in tiles.NEIGHBOURS[1:]:
                total += 1
                same += grid.levels[i, j] == grid.levels[i + di, j + dj]
    assert same / total < 0.05


def test_a_continuous_level_count_of_zero_draws_a_level_per_tile():
    levels = tile_world(tile_moisture_levels=0).terrain.tiles.levels
    assert len(np.unique(levels)) > 0.9 * levels.size


def test_every_cluster_has_the_stated_bushes_in_the_middle_of_its_tile():
    for seed in SEEDS:
        w = tile_world(seed)
        grid = w.terrain.tiles
        ids = tile_of(w)
        assert np.all(np.bincount(ids) == int(w.params.tile_bushes))
        i, j = grid.nearest(w.pos[:, 0], w.pos[:, 1])
        offset = w.pos - grid.centre(i, j)
        assert np.hypot(offset[:, 0], offset[:, 1]).max() <= float(w.params.tile_cluster_radius) + 1e-6
        assert np.all(grid.moisture(w.pos[:, 0], w.pos[:, 1]) == pytest.approx(grid.levels[i + grid.k, j + grid.k], abs=1e-6))      # a cluster stands on its plateau


def test_bushes_of_a_cluster_keep_the_minimum_spacing_and_stand_in_the_valley():
    w = tile_world(3)
    ids = tile_of(w)
    spacing = float(w.params.tile_cluster_spacing)
    for t in range(ids.max() + 1):
        p = w.pos[ids == t]
        d = np.hypot(*(p[:, None, :] - p[None, :, :]).transpose(2, 0, 1)) + np.eye(len(p)) * 1e9
        assert d.min() >= spacing - 1e-6
    assert np.all(w.terrain.is_tree_site(w.pos[:, 0], w.pos[:, 1]))


def test_the_walk_from_a_tiles_edge_to_its_bushes_is_at_least_the_stated_distance():
    w = tile_world(2)
    grid = w.terrain.tiles
    i, j = grid.nearest(w.pos[:, 0], w.pos[:, 1])
    rel = w.pos - grid.centre(i, j)
    normals = np.array([grid.a, grid.b, grid.b - grid.a]) / grid.pitch
    normals = np.concatenate([normals, -normals])
    edge = grid.apothem - (rel @ normals.T).max(axis=1)               # distance from each bush to the nearest edge of its tile
    assert edge.min() >= grid.apothem - float(w.params.tile_cluster_radius) - 1e-6
    assert np.hypot(*w.pos.T).min() > 20.0                            # the start is at a tile's edge, not in a cluster


def test_the_same_seed_gives_the_same_world_and_another_seed_another():
    a, b, c = tile_world(4), tile_world(4), tile_world(5)
    assert np.array_equal(a.pos, b.pos) and np.array_equal(a.shape, b.shape) and np.array_equal(a.fruit_reward, b.fruit_reward)
    assert a.n != c.n or not np.array_equal(a.pos, c.pos)


def realised(seed=1, **extra):
    w = tile_world(seed, **extra)
    return w, tiles.stats(w.params, w.pos, w.shape, w.color, w.terrain.tiles, world.bush_value)


def test_the_pool_is_an_even_cover_of_the_feature_plane_and_a_placement_only_deals_it():
    pool = tiles.bush_pool(400, np.random.default_rng(3))
    assert pool.shape == (400, 2) and pool.min() >= 0.0 and pool.max() <= 1.0
    cells = np.minimum((pool * 4).astype(int), 3)
    assert np.bincount(cells[:, 0] * 4 + cells[:, 1], minlength=16).min() >= 15                  # an even cover: 25 a cell on average, never fewer than 15
    dealt = tiles.place_random(None, None, pool, np.random.default_rng(1), None)
    assert not np.array_equal(dealt, pool) and np.array_equal(np.sort(dealt, axis=0), np.sort(pool, axis=0))
    assert np.array_equal(np.unique(dealt, axis=0), np.unique(pool, axis=0))                     # the same bushes, in another order


@pytest.mark.parametrize("seed", SEEDS)
def test_a_world_holds_the_whole_plane_and_stays_in_range(seed):
    w = tile_world(seed)
    assert 0.0 <= w.shape.min() and w.shape.max() <= 1.0 and 0.0 <= w.color.min() and w.color.max() <= 1.0
    cells = np.minimum((np.stack([w.shape, w.color], axis=1) * 4).astype(int), 3)
    assert len(np.unique(cells[:, 0] * 4 + cells[:, 1])) == 16


def test_the_placements_are_a_table_and_an_unknown_one_is_an_error():
    assert set(tiles.PLACEMENTS) == {"random", "balanced"} and set(tiles.ARRANGEMENTS) >= {"random"}
    with pytest.raises(KeyError):
        tile_world(tile_placement="nonsense")


def test_random_placement_gives_tiles_that_differ_no_more_than_chance():
    stats = [realised(seed)[1] for seed in range(4)]
    assert np.mean([s["contrast"] for s in stats]) < 0.6                  # the tile means vary only as nine bushes' means do (about a third of the within SD)
    assert min(s["within_sd"] for s in stats) > 0.5                       # and the bushes of a tile vary as the whole map does


def test_balanced_placement_deals_the_same_pool_and_equalises_tile_totals():
    for seed in range(4):
        w, s = realised(seed, tile_placement="balanced")
        r, sr = realised(seed, tile_placement="random")
        key = lambda x: np.lexsort((x.color, x.shape))
        assert np.allclose(np.stack([w.shape, w.color], 1)[key(w)], np.stack([r.shape, r.color], 1)[key(r)])      # the same bushes, dealt differently
        assert np.bincount(tile_of(w)).min() == np.bincount(tile_of(w)).max()
        assert s["tile_sum_dev_share"] < 0.05 and s["tile_sum_dev"] < sr["tile_sum_dev"] / 3
        assert s["contrast"] < 0.1 and s["within_sd"] > 0.5 * sr["within_sd"]                                   # tiles alike in total, each still spread out as the map is


def test_the_tile_sum_check_redraws_until_it_holds_and_an_impossible_one_is_an_error():
    _, s = realised(2, tile_placement="balanced", tile_sum_tol=0.5)
    assert s["tile_sum_dev"] <= 0.5
    with pytest.raises(ValueError, match="tile_sum_tol"):
        tile_world(tile_placement="random", tile_sum_tol=0.01)


def test_the_neighbourhood_coverage_check_redraws_until_it_holds_and_an_impossible_one_is_an_error():
    _, s = realised(2, tile_coverage_min=0.8)
    assert s["coverage_min"] >= 0.8
    with pytest.raises(ValueError, match="no placement"):
        tile_world(tile_bushes=1, tile_coverage_min=0.6)                  # seven bushes cannot span more than seven of the sixteen cells


def test_the_start_check_makes_the_tiles_around_the_start_differ():
    _, s = realised(2, tile_start_spread_min=0.15)
    assert s["start_spread"] >= 0.15


def test_stats_reports_the_realised_pattern():
    _, s = realised(1)
    assert set(s) == {"n_tiles", "tile_value_sd", "within_sd", "contrast", "good_tile_share", "good_bush_share", "coverage_min", "start_spread",
                    "tile_sum_dev", "tile_sum_dev_share", "within_sd_range"} and s["n_tiles"] > 10


def test_the_ground_level_of_a_tile_does_not_predict_its_value():
    ground, value = [], []
    for seed in range(10):
        w = tile_world(seed)
        ids = tile_of(w)
        for t in range(ids.max() + 1):
            ground.append(w.moisture[ids == t].mean())
            value.append(w.value[ids == t].mean())
    assert abs(np.corrcoef(ground, value)[0, 1]) < 0.25


def test_a_cluster_that_does_not_fit_its_tile_or_its_disc_is_an_error():
    with pytest.raises(ValueError, match="plateau"):
        tile_world(tile_cluster_radius=60.0)
    with pytest.raises(ValueError, match="do not fit"):
        tile_world(tile_bushes=40, tile_cluster_spacing=15.0)


def test_a_flat_ground_option_keeps_the_tiles_clusters_and_removes_the_levels():
    w = tile_world(moisture_varies=False)
    assert np.ptp(w.moisture) == 0.0 and w.n == tile_world().n


def test_the_world_file_records_the_tile_parameters():
    keys = world.check_values(tile_params())
    assert keys["tileRadius"] == 70.0 and keys["tileBushes"] == 9.0


def test_a_tiles_world_file_carries_the_tile_centres(tmp_path):
    w = tile_world()
    world.export_unity(w, tmp_path / "t.world")
    header, _ = world.read_unity_world(tmp_path / "t.world")
    centres = np.asarray(header["tileCentres"]).reshape(-1, 2)
    expected = np.asarray([c for _, _, c in w.terrain.tiles.tile_centres()])
    assert np.allclose(centres, expected) and header["tileRadius"] == w.terrain.tiles.radius


@pytest.mark.parametrize("seed", [1, 2, 3, 7])
def test_the_start_is_the_corner_where_three_tiles_meet_at_the_middle_of_the_world(seed):
    grid = tile_world(seed).terrain.tiles
    d = np.sort(np.hypot(*grid.centre(*np.meshgrid(np.arange(-3, 4), np.arange(-3, 4))).reshape(-1, 2).T))
    assert np.allclose(d[:3], grid.radius) and d[3] > grid.radius * 1.5                 # three centres a circumradius away, the next one much farther
    w = tile_world(seed)
    assert len(tiles.TileSet(w.terrain.tiles, w.pos).start) == 3                         # the three tiles of the start have clusters
