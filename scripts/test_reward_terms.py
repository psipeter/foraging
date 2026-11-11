"""The reward terms FI added: a bump's `angle` and the two-factor `factors` term, against the values the C# classes give (read from the Editor with `eval_file`), the world-file
entries, and the hash of a reward function that does not use them."""
import numpy as np
import pytest

import fingerprint
import world

ZERO = {"basisFunctionType": 0, "weight": 0.0, "peak": 0.0, "width": 0.0}
BASE = {"shapeComponent": ZERO, "colorComponent": ZERO, "moistureComponent": ZERO}
SUM_OF_SIGMOIDS = {**BASE, "factors": [{"combine": 1, "shapeFactor": {"kind": 0, "center": 0.5, "scale": 10, "inverted": False},
                                        "colorFactor": {"kind": 0, "center": 0.3, "scale": 4, "inverted": True}, "height": 4}]}
SIGMOID_GAUSSIAN = {**BASE, "factors": [{"combine": 0, "shapeFactor": {"kind": 0, "center": 0.4, "scale": 30, "inverted": False},
                                         "colorFactor": {"kind": 1, "center": 0.4, "scale": 0.2, "inverted": False}, "height": 4}]}
TILTED_BUMP = {**BASE, "bumps": [{"centerShape": 0.4, "centerColor": 0.6, "width": 0.1, "widthColor": 0.25, "angle": 35, "height": 3}]}
POINTS = [(0.1, 0.9), (0.7, 0.3), (0.5, 0.5), (0.95, 0.05), (0.3, 0.8), (0.0, 0.0), (1.0, 1.0)]
# RewardFactors.Evaluate / RewardBump.Evaluate in the Editor (Unity 6000.3.12f1, 2026-11-11), the three terms above at POINTS
FROM_CSHARP = ("0.693971157/2.16863282E-05/0.565893352;3.53869057/3.529552/0.5658935;2.47060156/3.36257482/2.49249244;3.96628857/0.8650606/0.0110249687;"
               "1.09144449/0.0256735813/1.9221164;2.013476/3.3260942E-06/2.742433E-10;2.49110246/0.0444359854/1.55032081E-11")


def test_python_terms_equal_the_csharp_ones():
    for row, (s, c) in zip(FROM_CSHARP.split(";"), POINTS):
        for text, rf in zip(row.split("/"), (SUM_OF_SIGMOIDS, SIGMOID_GAUSSIAN, TILTED_BUMP)):
            assert world.bush_value(rf, s, c, 0.5) == pytest.approx(float(text), abs=1e-5)


def test_a_sigmoid_factor_is_one_at_the_paying_end_and_the_inverted_one_pays_the_low_end():
    up = {"kind": 0, "center": 0.5, "scale": 12, "inverted": False}
    down = {**up, "inverted": True}
    assert world.factor_value(up, 1.0) == pytest.approx(1.0) and world.factor_value(down, 0.0) == pytest.approx(1.0)
    assert world.factor_value(up, 0.0) < 0.01 and world.factor_value(up, 0.5) == pytest.approx(0.5 / (1 / (1 + np.exp(-6))), rel=1e-6)


def test_the_product_needs_both_features_high_and_the_mean_pays_for_one():
    shape = {"kind": 0, "center": 0.5, "scale": 30, "inverted": False}
    for combine, one_high in ((0, 0.0), (1, 2.0)):
        rf = {**BASE, "factors": [{"combine": combine, "shapeFactor": shape, "colorFactor": shape, "height": 4}]}
        assert world.bush_value(rf, 1.0, 1.0, 0.5) == pytest.approx(4.0)
        assert world.bush_value(rf, 1.0, 0.0, 0.5) == pytest.approx(one_high, abs=0.02)


def test_a_bump_at_angle_zero_is_the_old_bump_and_an_angle_turns_it_about_its_centre():
    old = {**BASE, "bumps": [{"centerShape": 0.5, "centerColor": 0.5, "width": 0.3, "widthColor": 0.05, "height": 1}]}
    zero = {**BASE, "bumps": [{**old["bumps"][0], "angle": 0.0}]}
    turned = {**BASE, "bumps": [{**old["bumps"][0], "angle": 90.0}]}
    s, c = np.meshgrid(np.linspace(0, 1, 9), np.linspace(0, 1, 9), indexing="ij")
    assert np.allclose(world.bush_value(old, s, c, 0.5), world.bush_value(zero, s, c, 0.5))
    assert np.allclose(world.bush_value(turned, s, c, 0.5), world.bush_value(old, c, s, 0.5))          # (90 degrees swaps the two spreads)


def test_a_factors_term_makes_both_features_relevant():
    relevance = world.terms_relevance(SUM_OF_SIGMOIDS)
    assert relevance["shape"] == relevance["color"] == 4.0


def test_the_hash_of_a_reward_function_does_not_change_by_the_new_default_keys():
    plain = {**BASE, "bumps": [{"centerShape": 0.5, "centerColor": 0.5, "width": 0.3, "widthColor": 0.0, "height": 1}], "products": []}
    resaved = {**plain, "factors": [], "bumps": [{**plain["bumps"][0], "angle": 0.0}]}
    assert fingerprint._reward_without_new_defaults(resaved) == plain
    used = {**plain, "factors": SUM_OF_SIGMOIDS["factors"]}
    assert fingerprint._reward_without_new_defaults(used) != plain
