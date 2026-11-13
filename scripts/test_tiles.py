"""The tiles world (tiles.py): the hexagonal ground, the clusters in the middle of the tiles, and how the tiles' features are dealt.

Tests state their configuration (`synthetic.session`: shape and colour pay equally, a tiles layout and assignment) and do not name a shipped session.
"""

import numpy as np
import pytest

import synthetic
import tiles
import world

SEEDS = range(6)


def tile_params(**extra):
    return synthetic.session(visible=("shape", "color"), weights={"shape": 0.5, "color": 0.5}, layout="tiles", assignment="tiles", **{"moisture_varies": True, **extra})


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


def test_the_terrain_rebuilt_from_the_seed_is_the_terrain_the_world_was_made_on():
    w = tile_world(6)
    rebuilt = world.Terrain.from_seed(w.params, 6)
    assert np.allclose(rebuilt.moisture(w.pos[:, 0], w.pos[:, 1]), w.moisture)


def test_features_scatter_around_the_tiles_centre_by_the_stated_spread_and_stay_in_range():
    within, means = [], []
    for seed in SEEDS:
        w = tile_world(seed, tile_value_mode="random", tile_within_mode="scatter", tile_spread=0.08)
        assert 0.0 <= w.shape.min() and w.shape.max() <= 1.0 and 0.0 <= w.color.min() and w.color.max() <= 1.0
        ids = tile_of(w)
        for t in range(ids.max() + 1):
            s = w.shape[ids == t]
            means.append(s.mean())
            if 0.3 < s.mean() < 0.7:                                  # away from the ends, where the reflection would shrink the scatter
                within.append(s.var(ddof=1))
    assert np.sqrt(np.mean(within)) == pytest.approx(0.08, abs=0.02)
    assert np.std(means) == pytest.approx(np.sqrt(1.0 / 12.0), abs=0.06)       # the tiles' centres are uniform over the plane


def realised(seed=1, **extra):
    w = tile_world(seed, **extra)
    return w, tiles.stats(w.params, w.pos, w.shape, w.color, w.terrain.tiles, world.bush_value)


def test_graded_tiles_run_evenly_from_poor_to_rich_and_smoothness_makes_neighbours_alike():
    w0, s0 = realised(2, tile_value_mode="graded", tile_within_mode="scatter", tile_spread=0.02)
    ids = tile_of(w0)
    means = np.sort([w0.value[ids == t].mean() for t in range(ids.max() + 1)])
    plane = world.bush_value(w0.params.reward_function, *np.random.default_rng(1).uniform(0, 1, (2, 5000)), np.full(5000, 0.5))
    assert means[0] < np.quantile(plane, 0.15) and means[-1] > np.quantile(plane, 0.85)
    assert np.max(np.abs(np.diff(means) - np.ptp(means) / (len(means) - 1))) < 0.15 * np.ptp(means)

    def neighbour_corr(passes):
        out = []
        for seed in range(4):
            w = tile_world(seed, tile_value_mode="graded", tile_within_mode="scatter", tile_smoothness=passes)
            ts = tiles.TileSet(w.terrain.tiles, w.pos)
            m = np.array([w.value[ts.tile_of == t].mean() for t in range(ts.n_tiles)])
            out += [(m[t], m[u]) for t in range(ts.n_tiles) for u in ts.neighbours[t]]
        return np.corrcoef(np.array(out).T)[0, 1]
    assert neighbour_corr(6) > neighbour_corr(0) + 0.3


def test_the_modes_are_tables_and_an_unknown_mode_is_an_error():
    assert set(tiles.BETWEEN_MODES) >= {"none", "random", "graded", "bimodal"} and set(tiles.WITHIN_MODES) >= {"pool", "scatter", "gradient"} and set(tiles.ARRANGEMENTS) >= {"random"}
    with pytest.raises(KeyError):
        tile_world(tile_value_mode="nonsense")
    with pytest.raises(KeyError):
        tile_world(tile_within_mode="nonsense")


def test_no_pattern_anywhere_gives_tiles_that_differ_no_more_than_chance():
    ratios = []
    for seed in range(4):
        _, s = realised(seed, tile_value_mode="none", tile_within_mode="pool")
        ratios.append(s["contrast"])
    assert np.mean(ratios) < 0.6                                       # the tile means vary only as nine bushes' means do (about 1/3 of the within SD), against several for patterned tiles
    _, patterned = realised(1, tile_value_mode="random", tile_within_mode="scatter", tile_spread=0.05)
    assert patterned["contrast"] > 2.0 * np.mean(ratios)


def test_pure_tiles_have_no_spread_inside_and_the_same_pattern_in_every_tile_has_none_between():
    _, pure = realised(1, tile_value_mode="random", tile_within_mode="scatter", tile_spread=0.0)
    assert pure["within_sd"] == pytest.approx(0.0, abs=1e-6)
    stats = [realised(seed, tile_value_mode="none", tile_within_mode="gradient", tile_gradient=0.5, tile_spread=0.02)[1] for seed in range(4)]
    assert np.mean([s["tile_value_sd"] / s["within_sd"] for s in stats]) < 0.4 and min(s["within_sd"] for s in stats) > 0.3        # every tile alike (the means of nine bushes differ by about a third of the spread inside), each with a visible line inside


def test_a_gradient_adds_spread_inside_a_tile_along_a_line():
    _, none = realised(3, tile_value_mode="random", tile_within_mode="scatter", tile_spread=0.02)
    _, grad = realised(3, tile_within_mode="gradient", tile_gradient=0.5, tile_spread=0.02)
    assert grad["within_sd"] > none["within_sd"] + 0.2


def test_the_bimodal_mode_sets_the_share_of_good_tiles():
    shares = [realised(seed, tile_value_mode="bimodal", tile_within_mode="scatter", tile_good_fraction=0.3, tile_spread=0.04)[1]["good_tile_share"] for seed in range(4)]
    assert np.mean(shares) == pytest.approx(0.3, abs=0.12)
    few = np.mean([realised(seed, tile_value_mode="bimodal", tile_within_mode="scatter", tile_good_fraction=0.1, tile_spread=0.04)[1]["good_tile_share"] for seed in range(4)])
    assert few < np.mean(shares)


def test_the_neighbourhood_coverage_check_redraws_until_it_holds_and_an_impossible_one_is_an_error():
    _, s = realised(2, tile_value_mode="random", tile_within_mode="scatter", tile_spread=0.04, tile_coverage_min=0.4)
    assert s["coverage_min"] >= 0.4
    with pytest.raises(ValueError, match="no assignment"):
        tile_world(tile_value_mode="none", tile_within_mode="scatter", tile_spread=0.0, tile_coverage_min=0.5)               # identical tiles of identical bushes cover one cell


def test_the_start_check_makes_the_tiles_around_the_start_differ():
    _, s = realised(2, tile_value_mode="random", tile_within_mode="scatter", tile_spread=0.04, tile_start_spread_min=0.4)
    assert s["start_spread"] >= 0.4


def test_the_scatter_for_a_reward_sd_gives_that_sd():
    p = tile_params()
    spread = tiles.spread_for_reward_sd(p, world.bush_value, 0.5)
    sds = [realised(seed, tile_value_mode="random", tile_within_mode="scatter", tile_spread=spread)[1]["within_sd"] for seed in range(4)]
    assert np.mean(sds) == pytest.approx(0.5, abs=0.12)
    with pytest.raises(ValueError, match="outside"):
        tiles.spread_for_reward_sd(p, world.bush_value, 5.0)


def test_the_default_is_no_pattern_anywhere():
    _, default = realised(1)
    _, explicit = realised(1, tile_value_mode="none", tile_within_mode="pool")
    assert default == explicit
    assert default["contrast"] < 0.8 and default["within_sd"] > 0.5      # bushes of a tile vary a lot, the tiles are about equally valuable


def test_stats_reports_the_realised_pattern():
    _, s = realised(1)
    assert set(s) == {"n_tiles", "tile_value_sd", "within_sd", "contrast", "good_tile_share", "good_bush_share", "coverage_min", "start_spread"} and s["n_tiles"] > 10


def test_the_ground_level_of_a_tile_does_not_predict_its_value():
    ground, value = [], []
    for seed in range(10):
        w = tile_world(seed, tile_value_mode="random", tile_within_mode="scatter")
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
