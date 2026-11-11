"""The reward rules of FI (fi_terms.py): the sparsity each draw is solved for, the best reward, the three kinds of Gaussian, the instance interface, and worlds that populate every part of the reward."""
import numpy as np
import pytest

import fi_terms
import rw_peaks
import rw_screen
import world

TARGET, X = 0.20, 40


def draw(kind, seed, **kwargs):
    return fi_terms.draw_instance(np.random.default_rng(seed), kind, target=TARGET, x=X, **kwargs)


@pytest.mark.parametrize("kind", fi_terms.KINDS)
def test_every_draw_has_the_target_sparsity_and_the_best_bush_pays_the_reward_scale(kind):
    for seed in range(10):
        inst = draw(kind, seed)
        assert abs(inst.record["sparsity"][str(X)] / TARGET - 1.0) <= fi_terms.TOLERANCE
        assert inst.record["max_reward"] == pytest.approx(fi_terms.REWARD_SCALE, abs=0.01)


def test_a_corner_gaussian_is_round_and_centred_on_a_corner():
    for seed in range(8):
        b = draw("corner", seed).bumps[0]
        assert b["centerShape"] in (0.0, 1.0) and b["centerColor"] in (0.0, 1.0) and b["width"] == b["widthColor"] and b["angle"] == 0.0


def test_a_middle_gaussian_is_round_and_centred_near_the_middle():
    for seed in range(8):
        b = draw("middle", seed).bumps[0]
        assert all(fi_terms.MIDDLE_CENTER[0] <= b[k] <= fi_terms.MIDDLE_CENTER[1] for k in ("centerShape", "centerColor")) and b["width"] == b["widthColor"] and b["angle"] == 0.0


def test_an_elongated_gaussian_is_stretched_and_turned_with_either_sign():
    angles = []
    for seed in range(12):
        b = draw("elongated", seed).bumps[0]
        assert b["width"] == pytest.approx(fi_terms.ELONGATION * b["widthColor"], rel=1e-3)
        angles.append(b["angle"])
    assert set(np.sign(angles)) == {-1.0, 1.0} and all(abs(abs(a) - fi_terms.TILT_DEGREES) < 1e-6 for a in angles)


def test_the_corner_and_the_sign_of_the_tilt_can_be_fixed_by_the_design():
    assert (draw("corner", 1, corner=(1, 0)).bumps[0]["centerShape"], draw("corner", 1, corner=(1, 0)).bumps[0]["centerColor"]) == (1.0, 0.0)
    assert draw("elongated", 1, tilt_sign=1.0).bumps[0]["angle"] > 0 > draw("elongated", 1, tilt_sign=-1.0).bumps[0]["angle"]
    assert draw("elongated", 1, tilt=0.0).bumps[0]["angle"] == 0.0                                       # (the axis-aligned control)


def test_a_rotated_gaussian_is_far_less_additive_than_the_same_gaussian_aligned():
    aligned = [draw("elongated", s, tilt=0.0) for s in range(4)]
    rotated = [draw("elongated", s) for s in range(4)]
    import interlude
    class Des:
        p = type("P", (), {})()
    def share(inst):
        Des.p.reward_function = inst.reward_function(); pl = interlude._Plane(Des); V = pl.grid; S = pl.f[:, None] + pl.g[None, :]
        return ((V - S - (V - S).mean()) ** 2).sum() / ((V - V.mean()) ** 2).sum()
    assert np.mean([share(i) for i in aligned]) < 0.1 < 0.5 < np.mean([share(i) for i in rotated])


def test_the_same_generator_state_gives_the_same_instance():
    assert draw("elongated", 5).record == draw("elongated", 5).record


def test_an_instance_has_the_interface_the_screens_and_checks_use():
    inst = draw("middle", 1)
    assert inst.dims == 2 and inst.paying == ("shape", "color")
    assert float(inst.value(0.3, 0.6)) == pytest.approx(float(world.bush_value(inst.reward_function(), 0.3, 0.6, 0.5)))
    assert rw_peaks.sparsity(inst, X) == pytest.approx(inst.record["sparsity"][str(X)], abs=0.005)
    fields = inst.session_fields()
    assert fields["rewardFunction.bumps.Array.size"] == 1 and fields["rewardFunction.factors.Array.size"] == 0 and fields["rewardFunction.products.Array.size"] == 0
    assert fields["rewardFunction.bumps.Array.data[0].angle"] == inst.bumps[0]["angle"]


@pytest.mark.parametrize("kind", fi_terms.KINDS)
def test_worlds_populate_every_part_of_the_reward(kind):
    passed = 0
    for seed in range(4):
        inst = draw(kind, seed)
        params = rw_screen.session_params(inst, "FN_S1")
        params.moisture_varies = True
        w = world.generate_world(params, 700 + seed)
        passed += fi_terms.check_regions(inst, w.shape, w.color)
        counts = fi_terms.region_counts(inst, w.shape, w.color)
        assert counts["high"] + counts["mid"] + counts["low"] == len(w.shape)
    assert passed >= 3, f"{kind}: only {passed} of 4 worlds put enough bushes on every part of the reward"


def test_an_unknown_kind_raises():
    with pytest.raises(ValueError):
        fi_terms.draw_instance(np.random.default_rng(0), "sigmoid")
