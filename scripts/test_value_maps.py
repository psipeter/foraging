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
    g = vm.ValueMap(m.terms, m.noise, {"type": "gain", "value": 2.5})
    assert np.allclose(g.grid()[1], 2.5 * m.grid()[1])
    d0, d1 = m.descriptors(), g.descriptors()
    for key in ("gini", "interaction", "nonlinearity", "shape_share", "fraction_above_half_max"):
        assert d1[key] == pytest.approx(d0[key], abs=1e-9)


def test_a_single_ramp_is_additive_and_a_plane():
    d = vm.ValueMap((vm.Ramp("shape", 3.0, 1),)).descriptors()
    assert d["interaction"] == pytest.approx(0, abs=1e-12) and d["nonlinearity"] == pytest.approx(0, abs=1e-12)
    assert d["shape_share"] == pytest.approx(1.0) and d["effective_weight_color"] == pytest.approx(0, abs=1e-12) and d["effective_weight_shape"] == pytest.approx(3.0, rel=1e-6)


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


def test_the_additive_proxy_stays_additive_over_the_shares_and_the_corners_and_ramps_are_exact():
    for share in (0.3, 0.5, 0.7):
        rows = [vm.additive(s, shape_share=share).descriptors() for s in SEEDS]
        assert all(x["interaction"] < 0.04 and x["nonlinearity"] < 0.07 for x in rows)
        assert all(abs(x["shape_share"] - share) < 0.1 or abs(x["shape_share"] - (1 - share)) < 0.1 for x in rows)      # (the seed may swap which feature carries it)
    assert all(vm.ramps(s).descriptors()["interaction"] == pytest.approx(0, abs=1e-12) for s in SEEDS)


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
    with pytest.raises(NotImplementedError):
        vm.ValueMap((vm.Ramp("shape"),), {"type": "map"}).compile()
    with pytest.raises(NotImplementedError):
        vm.ValueMap((vm.Ramp("shape"),), equaliser={"type": "shift", "value": 1.0}).compile()
    with pytest.raises(ValueError):
        vm.ValueMap((vm.Ramp("shape"), vm.Ramp("shape", 2.0))).compile()


def test_the_reference_examples_fall_in_separability_up_the_ladder():
    import value_map_examples
    d = value_map_examples.table()
    assert d["additive"]["interaction"] < 0.05 and d["additive"]["log_interaction"] < 1e-9
    assert d["multiplicative"]["interaction"] > 3 * d["additive"]["interaction"] and d["multiplicative"]["log_interaction"] < 1e-9
    assert d["nonseparable"]["interaction"] > 2 * d["multiplicative"]["interaction"] and d["nonseparable"]["log_interaction"] > 0.5
