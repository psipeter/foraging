import numpy as np

import adaptive_grid_sim as ag


def test_a_grid_stays_inside_the_square_and_has_nine_cells_a_spacing_apart():
    for centre in ([0.5, 0.5], [0.0, 1.0], [0.95, 0.05]):
        for s in (0.1, 0.2, 1 / 3):
            cells = ag.grid_cells(centre, s)
            assert cells.shape == (9, 2) and cells.min() >= ag.MARGIN - 1e-9 and cells.max() <= 1 - ag.MARGIN + 1e-9
            assert np.isclose(np.diff(np.unique(np.round(cells[:, 0], 9))).min(), s)


def test_the_plackett_luce_likelihood_prefers_the_ranking_the_utilities_imply():
    u = np.array([3.0, 1.0, 2.0, 0.0, 4.0])
    good, bad = np.array([4, 0, 2, 1, 3]), np.array([3, 1, 2, 0, 4])
    assert ag.pl_loglik(u, good, 1.0) > ag.pl_loglik(u, bad, 1.0)
    assert np.isclose(ag.pl_loglik(u, good, 1e6), 5 * 0 + np.log(1 / 120), atol=1e-3)               # a very hot chooser ranks at random


def test_the_estimator_finds_the_peak_of_a_consistent_chooser():
    rng = np.random.default_rng(0)
    est = ag.Estimator(5.0)
    belief = np.array([0.3, 0.7])
    for _ in range(6):
        cells = ag.grid_cells([0.5, 0.5], 1 / 3)
        u = 5.0 * np.exp(-((cells - belief) ** 2).sum(axis=1) / (2 * 0.2 ** 2))
        est.update(cells, ag.sample_order(u, 0.3, rng))
    mean, sd = est.summary()
    assert np.hypot(*(mean - belief)) < 0.15 and sd < 0.2
