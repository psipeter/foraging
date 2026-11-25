import numpy as np

import adaptive_grid_sim as ag
import harvest_grid as hg

RNG = lambda: np.random.default_rng(0)
VAR3 = dict(spread="var", k=(3.0, 3.0))


def test_with_no_harvests_the_grid_is_the_broad_one_and_stays_inside_the_square():
    grid = hg.grid_from_harvests(np.empty((0, 2)), np.empty(0), 0.1, RNG(), jitter=0.0, **VAR3)
    assert grid["sx"] == grid["sy"] == hg.S_MAX
    cells = hg.cells_of(grid)
    assert cells.min() >= ag.MARGIN - 1e-9 and cells.max() <= 1 - ag.MARGIN + 1e-9


def test_similar_harvests_give_a_small_grid_and_diverse_ones_a_wide_one_within_the_clamps():
    r = RNG()
    tight = 0.6 + r.normal(0, 0.02, (12, 2))
    wide = r.uniform(0, 1, (12, 2))
    small = hg.grid_from_harvests(tight, np.ones(12), 0.1, RNG(), jitter=0.0, **VAR3)
    large = hg.grid_from_harvests(wide, np.ones(12), 0.1, RNG(), jitter=0.0, **VAR3)
    assert small["sx"] < large["sx"] - 0.05
    assert small["sx"] >= 0.1 - 1e-9 and large["sx"] <= hg.S_MAX + 1e-9


def test_a_sample_spread_along_one_axis_stretches_the_grid_along_it():
    r = RNG()
    f = np.column_stack([r.uniform(0.1, 0.9, 16), 0.5 + r.normal(0, 0.01, 16)])
    grid = hg.grid_from_harvests(f, np.ones(16), 0.08, RNG(), jitter=0.0, **VAR3)
    assert grid["sx"] > 1.5 * grid["sy"]


def test_a_larger_k_gives_a_larger_grid_until_the_clamp_and_the_sd_rule_saturates_where_the_variance_rule_does_not():
    f = RNG().uniform(0.0, 1.0, (12, 2))
    small = hg.grid_from_harvests(f, np.ones(12), 0.1, RNG(), jitter=0.0, spread="var", k=(2.0, 2.0))
    big = hg.grid_from_harvests(f, np.ones(12), 0.1, RNG(), jitter=0.0, spread="var", k=(3.5, 3.5))
    assert small["sx"] < big["sx"] <= hg.S_MAX
    sd = hg.grid_from_harvests(f, np.ones(12), 0.1, RNG(), jitter=0.0, spread="sd", k=(1.5, 1.5))
    assert sd["sx"] == hg.S_MAX                                                             # a sample spread over the square has an SD of about 0.29: 1.5 of it is over the maximum


def test_the_jitter_moves_the_middle_of_the_grid_by_up_to_that_many_spacings_and_zero_leaves_it_on_the_mean():
    f = RNG().uniform(0.3, 0.7, (10, 2))
    none = hg.grid_from_harvests(f, np.ones(10), 0.1, RNG(), jitter=0.0, **VAR3)
    assert np.allclose(none["centre"], none["mean"])
    moved = hg.grid_from_harvests(f, np.ones(10), 0.1, RNG(), jitter=2.0, unit_offset=[1.0, -0.5], **VAR3)
    assert np.allclose(moved["centre"] - moved["mean"], [2.0 * moved["sx"], -1.0 * moved["sy"]])


def test_an_extrapolation_probe_shifts_toward_the_rising_reward_and_a_widen_probe_widens():
    f = RNG().uniform(0.3, 0.7, (12, 2))
    rewards = 5.0 * f[:, 0]                                                                 # rewards rise with shape
    plain = hg.grid_from_harvests(f, rewards, 0.1, RNG(), jitter=0.0, **VAR3)
    shifted = hg.grid_from_harvests(f, rewards, 0.1, RNG(), probe="extrapolate", **VAR3)
    assert shifted["centre"][0] > plain["centre"][0] + 0.1 and abs(shifted["centre"][1] - plain["centre"][1]) < 0.05
    wider = hg.grid_from_harvests(f, rewards, 0.1, RNG(), probe="widen", jitter=0.0, **VAR3)
    assert wider["sx"] >= plain["sx"] and wider["sy"] >= plain["sy"] and wider["kind"] == "widen"


def test_the_window_is_the_last_n_harvests_or_the_last_k_patches():
    visits = [(i, (i // 3, 0), 1.0) for i in range(12)]                                      # four patches of three harvests
    assert [v[0] for v in hg.window(visits, 12, 5, 0)] == [7, 8, 9, 10, 11]
    assert [v[0] for v in hg.window(visits, 12, 5, 2)] == [6, 7, 8, 9, 10, 11]
    assert hg.selection_times(visits) == [3, 6, 9]
