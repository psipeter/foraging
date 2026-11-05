import numpy as np
import pytest

import agent_inference as ai
import human_analysis as ha

TRUE = np.array([2.0, -1.0, 0.0])


def toy_rows(n=60, seed=0):
    """Trials between bushes whose critic value is linear in the attributes (weights TRUE)."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        attrs = rng.random((2, 3))
        rows.append({"ids": [2 * i, 2 * i + 1], "attrs": attrs.tolist(), "mean": (attrs @ TRUE + 1.0).tolist()})
    return rows


def test_least_squares_weights_return_the_slopes_of_a_linear_value():
    rng = np.random.default_rng(1)
    X = rng.random((50, 3))
    assert np.allclose(ai.least_squares_weights(X, X @ TRUE + 3.0), TRUE)


def test_the_participants_method_recovers_the_direction_of_a_linear_critic_from_its_noisy_choices():
    rows = toy_rows()
    sets = ai.choice_sets(rows, temperature=0.5, draws=300, rng=np.random.default_rng(2))
    beta, _, _, n = ha.fit(sets, [0, 1, 2], 0.1)
    assert n == 60 * 300 and ha.cosine(beta, TRUE) > 0.98 and beta[0] > 0 > beta[1]


def test_a_critic_with_no_spread_chooses_at_random_and_a_greedy_scale_does_not_blow_up():
    rows = toy_rows(10)
    flat = [{**r, "mean": [1.0, 1.0]} for r in rows]
    picks = np.mean([c for _, c, _ in ai.choice_sets(flat, 0.25, 400, np.random.default_rng(3))])
    assert picks == pytest.approx(0.5, abs=0.05)
    assert len(ai.choice_sets(rows, 0.0, 5, np.random.default_rng(4))) == 50          # temperature 0: a hard choice, still finite


def test_the_noise_fit_recovers_the_temperature_and_lapse_that_generated_the_picks():
    rng = np.random.default_rng(5)
    x = rng.normal(size=4000)
    p = 0.2 / 2 + 0.8 / (1 + np.exp(-x / 0.4))
    tau, lapse, ll, n, ll0 = ai.fit_noise(list(zip(x, rng.random(4000) < p)))
    assert tau == pytest.approx(0.4, rel=0.15) and lapse == pytest.approx(0.2, abs=0.05) and n == 4000 and ll > ll0
