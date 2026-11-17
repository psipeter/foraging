"""Value maps (value_maps.py): the specification round-trips, the descriptors give the analytic answers, the compiled map is what the world generator produces, and the
nuisance draws of the ladder leave its character alone. Sessions are stated configurations on the frozen FIX_T0 (synthetic.py), not shipped ones."""

import numpy as np
import pytest

import synthetic
import value_maps as vm
from world import generate_world

SEEDS = range(20)


def world_of(valuemap, seed=3):
    return generate_world(synthetic.session(visible=("shape", "color"), **valuemap.compile()), seed)


@pytest.mark.parametrize("rung", vm.LADDER)
def test_a_map_round_trips_through_json(rung):
    m = vm.LADDER[rung](4)
    assert vm.ValueMap.from_json(m.to_json()) == m


def test_a_map_with_a_flat_gain_scales_every_value_and_keeps_the_shape_descriptors():
    m = vm.nonseparable(2)
    g = vm.ValueMap(m.bumps, m.noise, {"type": "gain", "value": 2.5})
    assert np.allclose(g.grid()[1], 2.5 * m.grid()[1])
    d0, d1 = m.descriptors(), g.descriptors()
    for key in ("gini", "interaction", "nonlinearity", "shape_share", "fraction_above_half_max"):
        assert d1[key] == pytest.approx(d0[key], abs=1e-9)


def test_a_gaussian_wide_along_one_feature_depends_on_the_other_alone():
    d = synthetic.feature_only("shape", high=False).descriptors()
    assert d["interaction"] < 1e-6 and d["shape_share"] > 0.999 and d["effective_weight_color"] < 1e-3          # a function of shape only: additive, and colour has no slope
    assert synthetic.feature_only("color").evaluate(0.0, 1.0) > synthetic.feature_only("color").evaluate(1.0, 0.0)


def test_a_flat_map_has_no_sparsity_and_a_narrow_bump_has_a_lot():
    flat = vm.ValueMap((vm.Bump(0.5, 0.5, 100.0, 0.0, 0.0, 2.0),)).descriptors()
    spike = vm.ValueMap((vm.Bump(0.5, 0.5, 0.05, 0.0, 0.0, 2.0),)).descriptors()
    assert flat["gini"] < 0.01 and spike["gini"] > 0.9
    assert spike["fraction_above_half_max"] < 0.05 and flat["fraction_above_half_max"] == 1.0


def test_an_axis_aligned_gaussian_is_multiplicative_wherever_it_lies_and_however_stretched():
    for centre in ((0.5, 0.5), (1.0, 1.0), (0.2, 0.8)):
        for aspect in (1.0, 2.0, 3.0):
            for angle in (0.0, 90.0):
                assert vm.gaussian(*centre, 0.2, aspect, angle).descriptors()["log_interaction"] == pytest.approx(0, abs=1e-9)


def test_turning_a_stretched_gaussian_makes_it_non_separable_and_most_at_45_degrees():
    li = [vm.gaussian(0.5, 0.5, 0.2, 3.0, a).descriptors()["log_interaction"] for a in (0, 15, 30, 45)]
    assert li[0] == pytest.approx(0, abs=1e-9) and li[0] < li[1] < li[2] < li[3] and li[3] > 0.5
    assert vm.gaussian(0.5, 0.5, 0.2, 1.0, 45).descriptors()["log_interaction"] == pytest.approx(0, abs=1e-9)         # a round bump has no axes to turn


def test_the_additive_proxy_stays_additive_over_the_shares_and_the_corners():
    for share in (0.3, 0.5, 0.7):
        rows = [vm.additive(s, shape_share=share).descriptors() for s in SEEDS]
        assert all(x["interaction"] < 0.04 and x["nonlinearity"] < 0.07 for x in rows)
        assert all(abs(x["shape_share"] - share) < 0.1 or abs(x["shape_share"] - (1 - share)) < 0.1 for x in rows)      # (the seed may swap which feature carries it)


def test_a_gaussian_approaches_an_additive_map_when_wide_in_a_corner_and_is_one_feature_along_an_edge():
    corner = lambda w: vm.gaussian(1.0, 1.0, w, 1.0).descriptors()["interaction"]
    assert corner(0.15) > corner(0.3) > corner(0.6) and corner(0.6) < 0.1
    edge = vm.ValueMap((vm.Bump(1.0, 0.5, 0.15, 1.5, 0.0, 4.0),)).descriptors()
    assert edge["interaction"] < 0.005 and edge["shape_share"] > 0.95            # (not exactly 0: the bump still falls off a little along the edge)


def test_the_ladder_rungs_have_their_separability_class_whatever_the_draw():
    d = {rung: [make(s).descriptors() for s in SEEDS] for rung, make in vm.LADDER.items()}
    assert all(x["interaction"] < 0.04 for x in d["additive"])                                               # additive (the wide corner Gaussian): almost no interaction in the value
    assert all(x["log_interaction"] == pytest.approx(0, abs=1e-9) for x in d["multiplicative"])               # multiplicative: none in the log
    assert all(x["interaction"] > 0.25 and x["log_interaction"] > 0.25 for x in d["nonseparable"])           # non-separable: in both
    for rows in d.values():
        assert all(x["max"] == pytest.approx(4.0, abs=0.01) for x in rows)                                   # the best bush pays about `scale`, whatever the draw


@pytest.mark.parametrize("rung", vm.LADDER)
def test_the_draw_depends_only_on_the_seed(rung):
    assert vm.LADDER[rung](9) == vm.LADDER[rung](9) and vm.LADDER[rung](9) != vm.LADDER[rung](10)


@pytest.mark.parametrize("rung", vm.LADDER)
def test_the_generated_world_pays_what_the_map_says_and_carries_its_noise(rung):
    m = vm.LADDER[rung](5, std=0.3)
    w = world_of(m)
    assert np.allclose(w.value, m.evaluate(w.shape, w.color))
    assert float(w.params.reward_std) == 0.3


def test_what_the_compiler_cannot_make_yet_is_refused():
    bump = vm.Bump()
    with pytest.raises(NotImplementedError):
        vm.ValueMap((bump,), {"type": "map"}).compile()
    with pytest.raises(NotImplementedError):
        vm.ValueMap((bump,), equaliser={"type": "shift", "value": 1.0}).compile()


def test_the_fields_of_a_map_are_its_bumps_and_the_noise_in_the_sessions_serialized_names():
    m = vm.gaussian(0.4, 0.6, 0.2, 2.0, 30.0, scale=3.0, std=0.5)
    f = m.fields()
    assert f["rewardStd"] == 0.5 and f["rewardFunction.bumps.Array.size"] == 1
    assert f["rewardFunction.bumps.Array.data[0].centerShape"] == 0.4 and f["rewardFunction.bumps.Array.data[0].height"] == 3.0
    assert f["rewardFunction.bumps.Array.data[0].width"] == 0.4 and f["rewardFunction.bumps.Array.data[0].widthColor"] == 0.2 and f["rewardFunction.bumps.Array.data[0].angle"] == 30.0


def test_the_reference_examples_fall_in_separability_up_the_ladder():
    import value_map_examples
    d = value_map_examples.table()
    assert d["additive"]["interaction"] < 0.05 and d["additive"]["log_interaction"] < 1e-9
    assert d["multiplicative"]["interaction"] > 3 * d["additive"]["interaction"] and d["multiplicative"]["log_interaction"] < 1e-9
    assert d["nonseparable"]["interaction"] > 2 * d["multiplicative"]["interaction"] and d["nonseparable"]["log_interaction"] > 0.5


def test_the_proxies_of_a_flat_map_are_its_value_and_the_fruit_pay_follows_the_rounding_and_the_clamp():
    flat = vm.ValueMap((vm.Bump(0.5, 0.5, 1e4, 0.0, 0.0, 3.0),))
    p = vm.map_proxies(flat)
    assert p["mean_bush_value"] == pytest.approx(3.0) and p["median_bush_value"] == pytest.approx(3.0) and p["q90_bush_value"] == pytest.approx(3.0)
    assert p["mean_fruit_pay"] == pytest.approx(3.0, abs=0.01)                     # a whole-number mean: the rounding is symmetric, the clamp does not bite
    zero = vm.map_proxies(vm.ValueMap((vm.Bump(0.5, 0.5, 1e4, 0.0, 0.0, 0.0),)))["mean_fruit_pay"]
    assert zero == pytest.approx(0.2086, abs=0.003)                                # a bush worth 0 still pays: the clamp drops the negative draws, a draw above 0.5 rounds up to 1
    half = vm.map_proxies(vm.ValueMap((vm.Bump(0.5, 0.5, 1e4, 0.0, 0.0, 0.5),)))["mean_fruit_pay"]
    assert half > 0.5                                                              # the clamp at 0 lifts the mean of a poor bush


@pytest.mark.parametrize("proxy", ["mean_bush_value", "median_bush_value", "mean_fruit_pay", "q90_bush_value"])
def test_the_gain_makes_a_proxy_equal_its_target_and_scales_the_map(proxy):
    base = vm.nonseparable(2)
    m = vm.solve_gain(base, proxy, 1.7)
    assert vm.map_proxies(m)[proxy] == pytest.approx(1.7, rel=0.011) and m.bumps == base.bumps and m.equaliser["value"] > 0
    with pytest.raises(ValueError, match="outside"):
        vm.solve_gain(base, proxy, 1e4)


def test_calibrate_map_finds_a_map_with_the_stated_sparsity_and_complexity_and_says_when_there_is_none(monkeypatch):
    monkeypatch.setitem(vm.SEARCH, "de_maxiter", 25)
    monkeypatch.setitem(vm.SEARCH, "nm_maxiter", 60)
    aligned = vm.calibrate_map(0.5, 0.10, "aligned", tol=(0.04, 0.04))
    d = aligned.descriptors()
    assert abs(d["gini"] - 0.5) <= 0.04 and abs(d["interaction"] - 0.10) <= 0.04 and d["log_interaction"] < vm.ALIGNED_LOG_MAX and 0.25 <= d["shape_share"] <= 0.75
    rotated = vm.calibrate_map(0.4, 0.4, "rotated", tol=(0.04, 0.04)).descriptors()
    assert abs(rotated["gini"] - 0.4) <= 0.04 and abs(rotated["interaction"] - 0.4) <= 0.04 and rotated["log_interaction"] >= vm.ROTATED_LOG_MIN
    with pytest.raises(ValueError, match="closest"):
        vm.calibrate_map(0.3, 0.3, "aligned", tol=(0.02, 0.02))                                     # an axis-aligned map this smooth cannot have so much interaction
