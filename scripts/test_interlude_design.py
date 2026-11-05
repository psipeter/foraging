import numpy as np
import pytest

import interlude_design as d
import world as worldmod


@pytest.fixture(scope="module")
def targets():
    return d.synthetic_targets()


def test_a_design_has_the_asked_trials_repeats_and_gap_range(targets):
    left, right, ids = d.sample_design(targets[0], 20, 0.3, "feature", 0.1, 0.6, np.random.default_rng(0))
    assert len(left) == len(right) == len(ids) == 20 and len(set(ids)) == 14           # 6 of the 20 repeat an earlier pair
    gap = np.sqrt(((left - right) ** 2).mean(axis=1))
    assert gap.min() >= 0.1 - 1e-9 and gap.max() <= 0.6 + 1e-9
    for pair in np.unique(ids):
        seen = [(tuple(np.round(l, 9)), tuple(np.round(r, 9))) for l, r, i in zip(left, right, ids) if i == pair]
        assert all(s in (seen[0], seen[0][::-1]) for s in seen)                          # a repeat is the same pair, sides swapped


def test_the_reward_gap_axis_uses_the_sessions_true_reward(targets):
    left, right, _ = d.sample_design(targets[0], 10, 0.0, "reward", 0.2, 1.0, np.random.default_rng(1))
    rf, scale = targets[0].reward_function, targets[0].reward_scale
    gap = np.abs(worldmod.bush_value(rf, *left.T) - worldmod.bush_value(rf, *right.T)) / scale       # (the range is in units of the reward's spread)
    assert gap.min() >= 0.2 - 1e-9 and gap.max() <= 1.0 + 1e-9


def test_choices_follow_the_targets_value_difference_and_noise_flattens_them(targets):
    t = targets[0]                                                                     # linear: shape weight 3
    left, right = np.array([[0.2, 0.5, 0.5]] * 4000), np.array([[0.8, 0.5, 0.5]] * 4000)
    low = d.simulate_choices(t, left, right, 0.05, np.random.default_rng(2))[1][0]
    high = d.simulate_choices(t, left, right, 2.0, np.random.default_rng(2))[1][0]
    assert low > 0.99 and 0.5 < high < low


def test_a_noiseless_linear_target_is_recovered_by_the_linear_basis_and_a_perfect_function_scores_one(targets):
    frame = d.run_cell([t for t in targets if t.name == "linear-mixed"], "linear", tau=0.02, n_trials=40, seeds=3)
    assert (frame["pearson"] > 0.99).all() and (frame["cos"] > 0.99).all() and (frame["signs"] == 0).all()
    t = targets[1]
    perfect = d.score(t, t.f, np.random.default_rng(3))
    assert perfect["pearson"] == pytest.approx(1.0) and perfect["pair"] == pytest.approx(1.0) and perfect["wrmse"] == pytest.approx(0.0, abs=1e-9)


def test_a_linear_basis_cannot_represent_a_peak_but_a_flexible_one_partly_can(targets):
    peak = [t for t in targets if t.name == "peak-shape"]
    linear = d.run_cell(peak, "linear", tau=0.1, n_trials=30, seeds=6)["pearson"].mean()
    rbf = d.run_cell(peak, "rbf0.3", tau=0.1, n_trials=30, seeds=6)["pearson"].mean()
    assert abs(linear) < 0.3 and rbf > linear + 0.3


def test_designs_are_shared_across_bases_and_runs_repeat(targets):
    a = d.run_cell(targets[:2], "linear", seeds=2)
    b = d.run_cell(targets[:2], "linear", seeds=2)
    assert a.equals(b)
