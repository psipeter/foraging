import numpy as np

import ranking_recovery as rr


def test_the_ranking_probabilities_of_a_set_sum_to_one_and_favour_the_true_order():
    values = [1.0, 3.0, 2.0, 5.0, 4.0]
    logp = rr.ranking_log_probs(values, 1.0)
    assert logp.shape == (120,) and abs(np.exp(logp).sum() - 1.0) < 1e-9
    best = rr.PERMS[int(np.argmax(logp))]
    assert list(best) == [3, 4, 1, 2, 0]                                     # the bushes from the most to the least valuable
    flat = rr.ranking_log_probs(values, 1e6)
    assert np.allclose(np.exp(flat), 1 / 120, atol=1e-4)                     # a very hot learner ranks at random


def test_two_learners_that_agree_cannot_be_told_apart_and_ones_that_differ_can():
    rng = np.random.default_rng(0)
    same = rr.ranking_log_probs([1, 2, 3, 4, 5], 1.0)[None]
    other = rr.ranking_log_probs([5, 4, 3, 2, 1], 1.0)[None]
    assert abs(rr.recovery_accuracy(np.exp(same), np.exp(same), same - same, [(np.array([0]), 10)], 2000, rng) - 0.5) < 0.05
    assert rr.recovery_accuracy(np.exp(same), np.exp(other), same - other, [(np.array([0]), 10)], 2000, rng) > 0.99


def test_the_learners_are_the_map_its_additive_part_and_its_marginals():
    import synthetic
    params = synthetic.session()
    models = rr.learners(params)
    s, c = np.array([0.2, 0.7]), np.array([0.9, 0.4])
    assert np.allclose(models["shape"](s, c), models["shape"](s, c[::-1]))              # a shape learner ignores colour
    assert np.allclose(models["colour"](s, c), models["colour"](s[::-1], c))
    assert np.allclose(models["additive"](s, c) - models["additive"](s, c[::-1]), models["colour"](s, c) - models["colour"](s, c[::-1]))
