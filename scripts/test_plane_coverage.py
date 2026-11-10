"""The plane-coverage assignment (world.assign_plane, session field featureCoverage) and the bushes it puts in the sparse-reward experiment's narrowest peaks."""

import numpy as np
import pytest
from scipy.spatial import cKDTree

import rw_peaks
import synthetic
import world

SEEDS = range(12)


def build(seed, coverage=1, weights=None, **extra):
    params = synthetic.session(visible=("shape", "color"), weights=weights or {"shape": 1.0}, spatial_balance=0, feature_coverage=coverage, **extra)
    return world.generate_world(params, seed)


@pytest.fixture(scope="module")
def planes():
    return [build(s) for s in SEEDS]


@pytest.fixture(scope="module")
def independents():
    return [build(s, coverage=0) for s in SEEDS]


def occupancy_std(w, cells=10):
    return np.histogram2d(w.shape, w.color, bins=cells, range=[[0, 1], [0, 1]])[0].std()


def test_the_stage_is_selected_by_the_field_and_excludes_the_other_ways_of_dealing_the_features():
    params = synthetic.session(visible=("shape", "color"), spatial_balance=0, feature_coverage=1)
    assert world.stage_names(params)[1] == "plane" and world.check_values(params)["featureCoverage"] == 1.0
    assert "featureCoverage" not in world.check_values(synthetic.session(visible=("shape", "color"), spatial_balance=0))
    with pytest.raises(ValueError, match="three ways"):
        world.stage_names(synthetic.session(visible=("shape", "color"), spatial_balance=0, feature_balance=2, feature_coverage=1))
    with pytest.raises(ValueError, match="both features must vary"):
        build(1, shape_varies=False)


def test_the_new_random_stream_moves_no_world_that_exists():
    for seed in (0, 5, 301):
        old, new = np.random.SeedSequence(seed).spawn(16), np.random.SeedSequence(seed).spawn(17)
        assert all(np.array_equal(a.generate_state(4), b.generate_state(4)) for a, b in zip(old, new))


def test_the_pairs_cover_the_plane_far_more_evenly_than_independent_draws(planes, independents):
    assert np.mean([occupancy_std(w) for w in planes]) < 0.6 * np.mean([occupancy_std(w) for w in independents])
    for w in planes:
        counts = np.histogram2d(w.shape, w.color, bins=10, range=[[0, 1], [0, 1]])[0]
        assert counts.min() >= 3 and counts.max() <= 11 and w.shape.min() >= 0.0 and w.shape.max() <= 1.0 and w.color.min() >= 0.0 and w.color.max() <= 1.0


def test_every_tile_of_the_map_gets_an_even_sample_of_the_plane(planes):
    side = (world.PLANE_TILE_BUSHES * 0.866 * 23.0 ** 2) ** 0.5
    for w in planes:
        ij = np.floor((w.pos + 350.0) / side).astype(int)
        _, tile = np.unique(ij[:, 0] * 100_000 + ij[:, 1], return_inverse=True)
        for t in range(tile.max() + 1):
            members = tile == t
            if members.sum() >= 12:                                                      # a full tile (the edge ones are cut by the mountains): every quadrant of the plane is represented
                quadrants = {(s >= 0.5, c >= 0.5) for s, c in zip(w.shape[members], w.color[members])}
                assert len(quadrants) == 4


def test_nothing_in_the_assignment_shows_which_feature_pays_or_follows_the_position(planes):
    sc, ps, pc, cs, cc = [], [], [], [], []
    for w in planes:
        _, near = cKDTree(w.pos).query(w.pos, k=7)
        sc.append(abs(np.corrcoef(w.shape, w.color)[0, 1]))
        ps.append(max(abs(np.corrcoef(w.shape, w.pos[:, i])[0, 1]) for i in (0, 1)))
        pc.append(max(abs(np.corrcoef(w.color, w.pos[:, i])[0, 1]) for i in (0, 1)))
        cs.append(np.corrcoef(w.shape, w.shape[near[:, 1:]].mean(axis=1))[0, 1])
        cc.append(np.corrcoef(w.color, w.color[near[:, 1:]].mean(axis=1))[0, 1])
    assert np.mean(sc) < 0.06 and np.mean(ps) < 0.08 and np.mean(pc) < 0.08
    assert abs(np.mean(cs) - np.mean(cc)) < 0.08                                          # the two features are equally regular (the roles are swapped by a coin toss per world)
    assert np.mean(cs) > -0.3 and np.mean(cc) > -0.3                                      # and neither is conspicuously so


def test_the_reward_does_not_enter_the_assignment_and_the_world_is_the_same_for_the_same_seed():
    a, b, c = build(3, weights={"shape": 1.0}), build(3, weights={"color": 1.0}), build(3, weights={"shape": 1.0})
    assert np.array_equal(a.shape, b.shape) and np.array_equal(a.color, b.color) and np.array_equal(a.shape, c.shape)
    assert not np.array_equal(a.shape, build(4).shape)


@pytest.mark.parametrize("paying", [("shape",), ("shape", "color")])
def test_the_narrowest_peak_always_holds_the_guaranteed_bushes_where_an_independent_draw_does_not(planes, independents, paying):
    def fewest(worlds):
        counts = []
        for k, w in enumerate(worlds):
            for j in range(3):
                peaks = rw_peaks.draw_peaks(np.random.default_rng(100 * k + j), paying, 1, rw_peaks.narrowest_spread(w.n, len(paying), rw_peaks.NARROWEST_EXPECTED))
                counts.append(rw_peaks.check_peak_bushes(w.shape, w.color, peaks, minimum=1)[0])
        return min(counts)
    assert fewest(planes) >= rw_peaks.MIN_PEAK_BUSHES
    assert fewest(independents) < fewest(planes)


def test_check_peak_bushes_raises_for_a_peak_with_too_few():
    w = build(1)
    peaks = rw_peaks.draw_peaks(np.random.default_rng(0), ("shape", "color"), 1, 0.01)          # a tiny peak: no bush in it
    with pytest.raises(ValueError, match="only"):
        rw_peaks.check_peak_bushes(w.shape, w.color, peaks)
