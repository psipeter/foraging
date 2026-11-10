"""The peak model of the sparse-reward experiment (scripts/rw_peaks.py): the margin, the sparsity measure, the separation and the height ratio, a flat decoration axis."""

import math

import numpy as np
import pytest

import rw_peaks
import world
from rw_peaks import MARGIN_SPREADS, MIN_SEPARATION, SPARSITY_X, draw_peaks, margin

PAYING = [("shape",), ("color",), ("shape", "color")]


@pytest.mark.parametrize("paying", PAYING)
def test_a_peak_is_at_least_the_margin_from_each_end_and_the_reward_there_is_at_most_a_third_of_its_height(paying):
    for seed in range(40):
        peaks = draw_peaks(np.random.default_rng(seed), paying, 1, 0.12)
        for position in peaks.centers[0]:
            assert margin(0.12) - 1e-12 <= position <= 1.0 - margin(0.12) + 1e-12
        for k, feature in enumerate(paying):                                  # walk from the centre to each end of that feature
            for end in (0.0, 1.0):
                point = {f: (peaks.centers[0][paying.index(f)] if f in paying else 0.5) for f in rw_peaks.FEATURES}
                point[feature] = end
                assert peaks.value(point["shape"], point["color"]) <= peaks.heights[0] / 3.0 + 1e-9


@pytest.mark.parametrize("paying", PAYING)
def test_the_closed_form_spread_gives_the_sparsity_it_is_asked_for_at_every_x(paying):
    dims = len(paying)
    target = 0.1 if dims == 1 else 0.03                                        # what a plane peak can reach is much less: see test_the_margin_caps_the_sparsity
    for x in SPARSITY_X:
        spread = rw_peaks.spread_for_sparsity(target, dims, x)
        peaks = draw_peaks(np.random.default_rng(1), paying, 1, spread)
        assert rw_peaks.sparsity(peaks, x) == pytest.approx(target, abs=0.01)
        assert rw_peaks.sparsity_for_spread(spread, dims, x) == pytest.approx(target)


def test_the_margin_caps_the_sparsity_of_a_single_peak():
    assert rw_peaks.max_sparsity(1, 10) == pytest.approx(0.31, abs=0.01) and rw_peaks.max_sparsity(2, 10) == pytest.approx(0.075, abs=0.005)
    assert rw_peaks.max_sparsity(1, 30) == pytest.approx(0.57, abs=0.01) and rw_peaks.max_sparsity(2, 30) == pytest.approx(0.25, abs=0.01)
    draw_peaks(np.random.default_rng(0), ("shape",), 1, rw_peaks.MAX_SPREAD * 0.99)
    with pytest.raises(ValueError, match="no room"):
        draw_peaks(np.random.default_rng(0), ("shape",), 1, rw_peaks.MAX_SPREAD * 1.01)


def test_sparsity_grows_with_x_and_with_the_spread_and_a_plane_peak_covers_less_than_a_segment_of_the_same_spread():
    narrow, wide = (draw_peaks(np.random.default_rng(2), ("shape",), 1, s) for s in (0.06, 0.12))
    assert [rw_peaks.sparsity(wide, x) for x in SPARSITY_X] == sorted(rw_peaks.sparsity(wide, x) for x in SPARSITY_X)
    assert all(rw_peaks.sparsity(narrow, x) < rw_peaks.sparsity(wide, x) for x in SPARSITY_X)
    line, plane = (draw_peaks(np.random.default_rng(3), paying, 1, 0.1) for paying in (("shape",), ("shape", "color")))
    assert rw_peaks.sparsity(plane, 20) < rw_peaks.sparsity(line, 20)             # "width alone is not comparable across the two"
    assert rw_peaks.spread_for_sparsity(0.1, 2) > rw_peaks.spread_for_sparsity(0.1, 1)       # a plane peak needs the wider spread for the same coverage


def test_a_peak_over_one_feature_is_flat_along_the_feature_that_does_not_pay():
    peaks = draw_peaks(np.random.default_rng(4), ("shape",), 1, 0.1)
    rf = peaks.reward_function()
    s = np.linspace(0.0, 1.0, 11)
    for c in (0.0, 0.3, 1.0):
        assert np.allclose(world.bush_value(rf, s, c, 0.5), world.bush_value(rf, s, 0.5, 0.5), atol=1e-6)
    other = draw_peaks(np.random.default_rng(4), ("color",), 1, 0.1)                 # and along shape when only the colour pays
    assert np.ptp(other.value(np.linspace(0, 1, 9), 0.5)) < 1e-6


@pytest.mark.parametrize("paying", PAYING)
@pytest.mark.parametrize("separation, ratio", [(3.0, 0.6), (4.0, 0.8), (5.0, 0.4)])
def test_two_peaks_are_the_requested_distance_apart_and_the_realised_height_ratio_is_the_requested_one(paying, separation, ratio):
    for seed in range(10):
        peaks = draw_peaks(np.random.default_rng(seed), paying, 2, 0.08, separation, ratio)
        assert math.dist(*peaks.centers) / peaks.spread == pytest.approx(separation)
        for center in peaks.centers:
            assert all(margin(0.08) - 1e-12 <= p <= 1 - margin(0.08) + 1e-12 for p in center)
        record = rw_peaks.describe(peaks)
        assert record["separation"] == pytest.approx(separation, abs=0.15)        # near hills pull each other's maxima inward, by about 0.1 spreads at 3 spreads apart
        assert record["height_ratio"] == pytest.approx(ratio, abs=0.03)
        assert len(rw_peaks.realized(peaks)) == 2


def test_peaks_that_would_merge_or_do_not_fit_are_refused():
    rng = np.random.default_rng(5)
    with pytest.raises(ValueError, match="merge"):
        draw_peaks(rng, ("shape",), 2, 0.08, MIN_SEPARATION - 0.5, 0.6)
    with pytest.raises(ValueError, match="no room"):
        draw_peaks(rng, ("shape",), 2, 0.2, 5.0, 0.6)                              # 1.0 apart in a box 0.2 wide
    with pytest.raises(ValueError, match="no room for a peak"):
        draw_peaks(rng, ("shape",), 1, 0.4)
    with pytest.raises(ValueError, match="separation"):
        draw_peaks(rng, ("shape",), 2, 0.08)
    with pytest.raises(ValueError, match="height ratio"):
        draw_peaks(rng, ("shape",), 2, 0.08, 4.0, 1.0)


def test_an_instance_is_the_same_for_the_same_seed_and_differs_for_another():
    a, b, c = (draw_peaks(np.random.default_rng(seed), ("shape", "color"), 2, 0.08, 4.0, 0.6) for seed in (7, 7, 8))
    assert a == b and a != c


def test_the_session_fields_are_the_reward_function_and_one_peak_has_the_stated_height():
    peaks = draw_peaks(np.random.default_rng(9), ("shape", "color"), 2, 0.08, 4.0, 0.5)
    fields = peaks.session_fields()
    assert fields["rewardFunction.bumps.Array.size"] == 2 and fields["rewardFunction.shapeComponent.weight"] == 0.0
    for i, term in enumerate(peaks.terms()):
        assert all(fields[f"rewardFunction.bumps.Array.data[{i}].{key}"] == value for key, value in term.items())
    assert peaks.heights == (rw_peaks.REWARD_SCALE, rw_peaks.REWARD_SCALE * 0.5)
    single = draw_peaks(np.random.default_rng(9), ("shape",), 1, 0.1)
    center = single.centers[0][0]
    assert single.value(center, 0.5) == pytest.approx(rw_peaks.REWARD_SCALE)


@pytest.mark.parametrize("dims", [1, 2])
def test_two_peaks_can_be_placed_at_the_very_edge_of_what_fits(dims):
    """An earlier placement (a position, then a try at a direction) almost never succeeded when the distance was nearly the largest that fits."""
    paying = ("shape",) if dims == 1 else ("shape", "color")
    spread = 0.1
    lo, hi = margin(spread), 1 - margin(spread)
    largest = (hi - lo) * (1.0 if dims == 1 else math.sqrt(2.0)) / spread
    for fraction in (0.5, 0.9, 0.999, 1.0):
        separation = largest * fraction
        for seed in range(100):
            peaks = draw_peaks(np.random.default_rng(seed), paying, 2, spread, separation, 0.6)
            assert math.dist(*peaks.centers) / spread == pytest.approx(separation)
            assert all(lo - 1e-9 <= p <= hi + 1e-9 for center in peaks.centers for p in center)


def test_the_separable_check_is_the_one_draw_peaks_applies():
    assert not rw_peaks.separable(3.0, 0.15) and rw_peaks.separable(3.0, 0.3) and not rw_peaks.separable(2.0, 0.9)
    with pytest.raises(ValueError, match="merge"):
        draw_peaks(np.random.default_rng(0), ("shape",), 2, 0.05, 3.0, 0.15)


def test_a_smaller_margin_makes_room_for_two_wide_two_feature_peaks_and_the_peaks_stay_inside_it():
    spread = 0.1829                                                          # two features at 15% total (7.5% per peak)
    assert not rw_peaks.fits(spread, 2, 4.5) and rw_peaks.fits(spread, 2, 4.5, 1.0) and rw_peaks.fits(spread, 2, 3.5)
    with pytest.raises(ValueError, match="no room"):
        draw_peaks(np.random.default_rng(0), ("shape", "color"), 2, spread, 4.5, 0.75)
    for seed in range(50):
        peaks = draw_peaks(np.random.default_rng(seed), ("shape", "color"), 2, spread, 4.5, 0.75, margin_spreads=1.0)
        assert math.dist(*peaks.centers) / spread == pytest.approx(4.5)
        assert all(margin(spread, 1.0) - 1e-9 <= p <= 1 - margin(spread, 1.0) + 1e-9 for center in peaks.centers for p in center)
