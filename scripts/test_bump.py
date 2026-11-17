"""The reward function's one term, the Gaussian bump: its formula, its `angle`, and the values the C# class gives (read from the Editor with `eval_file`)."""
import numpy as np
import pytest

import world

TILTED_BUMP = {"bumps": [{"centerShape": 0.4, "centerColor": 0.6, "width": 0.1, "widthColor": 0.25, "angle": 35, "height": 3}]}
POINTS = [(0.1, 0.9), (0.7, 0.3), (0.5, 0.5), (0.95, 0.05), (0.3, 0.8), (0.0, 0.0), (1.0, 1.0)]
# RewardBump.Evaluate in the Editor (Unity 6000.3.12f1, 2026-11-11), the tilted bump above at POINTS
FROM_CSHARP = (0.565893352, 0.5658935, 2.49249244, 0.0110249687, 1.9221164, 2.742433E-10, 1.55032081E-11)


def test_python_bump_equals_the_csharp_one():
    for expected, (s, c) in zip(FROM_CSHARP, POINTS):
        assert world.bush_value(TILTED_BUMP, s, c) == pytest.approx(expected, abs=1e-5)


def test_a_bump_at_angle_zero_is_the_unturned_bump_and_an_angle_turns_it_about_its_centre():
    old = {"bumps": [{"centerShape": 0.5, "centerColor": 0.5, "width": 0.3, "widthColor": 0.05, "height": 1}]}
    zero = {"bumps": [{**old["bumps"][0], "angle": 0.0}]}
    turned = {"bumps": [{**old["bumps"][0], "angle": 90.0}]}
    s, c = np.meshgrid(np.linspace(0, 1, 9), np.linspace(0, 1, 9), indexing="ij")
    assert np.allclose(world.bush_value(old, s, c), world.bush_value(zero, s, c))
    assert np.allclose(world.bush_value(turned, s, c), world.bush_value(old, c, s))          # (90 degrees swaps the two spreads)


def test_bush_value_is_the_height_at_the_centre_of_a_bump_and_falls_by_exp_minus_a_half_one_width_away():
    rf = {"bumps": [{"centerShape": 0.3, "centerColor": 0.6, "width": 0.2, "height": 2.0}]}
    assert abs(world.bush_value(rf, 0.3, 0.6) - 2.0) < 1e-12
    d = 0.2
    assert abs(world.bush_value(rf, 0.3 + d, 0.6) - 2.0 * np.exp(-0.5)) < 1e-12                       # one width away along either axis: height * exp(-1/2)
    assert abs(world.bush_value(rf, 0.3, 0.6 - d) - 2.0 * np.exp(-0.5)) < 1e-12
    assert np.array_equal(world.bush_value({"bumps": []}, np.array([0.1, 0.2]), np.array([0.3, 0.4])), np.zeros(2))     # no bump: zero, as an array


def test_a_bump_with_its_own_color_spread_has_the_documented_formula():
    x = np.array([0.0, 0.3, 0.7, 1.0])
    y = np.array([0.2, 0.7, 0.9, 0.0])
    round_bump = {"bumps": [{"centerShape": 0.3, "centerColor": 0.7, "width": 0.2, "height": 2.0}]}
    assert np.allclose(world.bush_value(round_bump, x, y), 2.0 * np.exp(-(((x - 0.3) ** 2 + (y - 0.7) ** 2) / (2 * 0.2 ** 2))))        # no widthColor: round
    stretched = {"bumps": [{"centerShape": 0.3, "centerColor": 0.7, "width": 0.25, "widthColor": 0.15, "height": 4.0}]}
    assert np.allclose(world.bush_value(stretched, x, y), 4.0 * np.exp(-((x - 0.3) ** 2 / (2 * 0.25 ** 2) + (y - 0.7) ** 2 / (2 * 0.15 ** 2))))
