"""The reward rules of FI (fi_terms.py): the sparsity each draw is solved for, the best reward, the draws of roles and tilt, the instance interface, and worlds that populate every part of the reward."""
import numpy as np
import pytest

import fi_terms
import rw_peaks
import rw_screen
import world

CASES = [("sum", 4.0), ("sum", 30.0), ("product", 4.0), ("product", 30.0), ("sigmoid_gaussian", 4.0), ("sigmoid_gaussian", 30.0), ("bump", 10.0)]
TARGET, X = 0.30, 40


def draw(kind, steepness, seed):
    return fi_terms.draw_instance(np.random.default_rng(seed), kind, steepness=steepness, target=TARGET, x=X)


@pytest.mark.parametrize("kind,steepness", CASES)
def test_every_draw_has_the_target_sparsity_and_the_best_bush_pays_the_reward_scale(kind, steepness):
    for seed in range(12):
        inst = draw(kind, steepness, seed)
        assert abs(inst.record["sparsity"][str(X)] / TARGET - 1.0) <= fi_terms.TOLERANCE
        assert inst.record["max_reward"] == pytest.approx(fi_terms.REWARD_SCALE, abs=0.01)


@pytest.mark.parametrize("kind,steepness", CASES)
def test_roles_directions_and_tilt_are_drawn(kind, steepness):
    records = [draw(kind, steepness, seed).record for seed in range(16)]
    if kind in ("sum", "product"):
        assert {r["inverted"]["shape"] for r in records} == {True, False} and {r["inverted"]["color"] for r in records} == {True, False}
    if kind == "sigmoid_gaussian":
        assert {r["gate"] for r in records} == {"shape", "color"} and {r["inverted"] for r in records} == {True, False}
    if kind == "bump":
        tilts = [r["tilt"] for r in records]
        assert min(tilts) < 0 < max(tilts) and all(fi_terms.TILT_DEGREES[0] <= abs(t) <= fi_terms.TILT_DEGREES[1] for t in tilts)


def test_steep_sigmoids_pay_nothing_outside_the_high_region_and_shallow_ones_pay_nearly_everywhere():
    assert np.mean([draw("product", 30.0, s).record["nonzero"] for s in range(8)]) < 0.55
    assert np.mean([draw("product", 4.0, s).record["nonzero"] for s in range(8)]) > 0.9
    assert np.mean([draw("sum", 30.0, s).record["nonzero"] for s in range(8)]) > 0.75       # a bush with one feature high pays about half


def test_the_same_generator_state_gives_the_same_instance():
    assert draw("bump", 10.0, 5).record == draw("bump", 10.0, 5).record


def test_an_instance_has_the_interface_the_screens_and_checks_use():
    inst = draw("sigmoid_gaussian", 10.0, 1)
    assert inst.dims == 2 and inst.paying == ("shape", "color")
    assert float(inst.value(0.3, 0.6)) == pytest.approx(float(world.bush_value(inst.reward_function(), 0.3, 0.6, 0.5)))
    assert rw_peaks.sparsity(inst, X) == pytest.approx(inst.record["sparsity"][str(X)], abs=0.005)
    fields = inst.session_fields()
    assert fields["rewardFunction.factors.Array.size"] == 1 and fields["rewardFunction.bumps.Array.size"] == 0 and fields["rewardFunction.products.Array.size"] == 0
    assert fields["rewardFunction.factors.Array.data[0].colorFactor.kind"] in (0, 1)
    bump = draw("bump", 10.0, 1)
    assert bump.session_fields()["rewardFunction.factors.Array.size"] == 0 and bump.session_fields()["rewardFunction.bumps.Array.data[0].angle"] == bump.bumps[0]["angle"]


@pytest.mark.parametrize("kind,steepness", CASES)
def test_worlds_populate_every_part_of_the_reward(kind, steepness):
    passed = 0
    for seed in range(4):
        inst = draw(kind, steepness, seed)
        params = rw_screen.session_params(inst, "FN_S1")
        params.moisture_varies = True
        w = world.generate_world(params, 700 + seed)
        passed += fi_terms.check_regions(inst, w.shape, w.color)
        counts = fi_terms.region_counts(inst, w.shape, w.color)
        assert counts["high"] + counts["mid"] + counts["low"] == len(w.shape)
    assert passed >= 3, f"{kind} k={steepness}: only {passed} of 4 worlds put enough bushes on every part of the reward"


def test_a_target_out_of_reach_raises():
    with pytest.raises(RuntimeError):
        fi_terms.draw_instance(np.random.default_rng(0), "sigmoid_gaussian", steepness=30.0, target=0.95, x=40)
