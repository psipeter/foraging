"""The typed Interlude trials of FI (interlude.interaction_trials): the class plan of each kind of Gaussian, the tie rule, the spread of the reward gaps, the repeats, the one-feature and along/across pairs, reversal pairs."""
import collections

import numpy as np
import pytest

import fi_terms
import interlude

CASES = [("corner", {}), ("middle", {}), ("elongated", {}), ("elongated", {"tilt": 0.0})]
IDS = ["corner", "middle", "rotated", "aligned"]
OVERRIDES = dict(interlude_trial_count=20, interlude_repeat_count=3, interlude_interaction_trials=17, interlude_peak_trials=0, interlude_mode=4, interlude_feature_trials=0)


def draw(kind, seed=3, **kwargs):
    return fi_terms.draw_instance(np.random.default_rng(seed), kind, target=0.20, x=40, **kwargs)


@pytest.fixture(scope="module", params=CASES, ids=IDS)
def built(request):
    kind, kwargs = request.param
    inst = draw(kind, **kwargs)
    sidecar, params, _ = interlude.generate_interlude("RW_I1", reward_function=inst.reward_function(), **OVERRIDES)
    return interlude.interaction_kind(inst.reward_function()), inst, sidecar["trials"]


def test_twenty_trials_follow_the_plan_with_one_repeat_in_each_named_class(built):
    kind, _, trials = built
    assert len(trials) == 20 and {t["type"] for t in trials} == {"interaction"}
    repeats = [t for t in trials if "repeatOf" in t]
    assert sorted(t["varied"] for t in repeats) == sorted(interlude.INTERACTION_REPEATS[kind])
    plan = dict(interlude.INTERACTION_PLANS[kind])
    distinct = collections.Counter(t["varied"] for t in trials if "repeatOf" not in t)
    assert sum(distinct.values()) == 17
    shortfall = plan.get("R", 0) - distinct.get("R", 0)                # reversal pairs a rule cannot supply go to SHORTFALL_CLASS
    for cls, n in plan.items():
        expected = n + (shortfall if cls == interlude.SHORTFALL_CLASS else 0) - (shortfall if cls == "R" else 0)
        assert distinct.get(cls, 0) == expected, (cls, dict(distinct))


def test_no_pair_is_a_tie_and_the_correct_sides_match_the_values(built):
    _, _, trials = built
    for t in trials:
        assert abs(t["deltaValue"]) >= interlude.PEAK_MIN_GAP and t["correct"] in ("left", "right")
        assert (t["correct"] == "left") == (t["left"]["value"] > t["right"]["value"])
    assert 7 <= sum(t["correct"] == "left" for t in trials) <= 13


def test_a_repeat_is_an_exact_copy_at_least_eight_trials_later(built):
    _, _, trials = built
    for t in trials:
        if "repeatOf" in t:
            source = trials[t["repeatOf"]]
            assert t["index"] - source["index"] >= interlude.REPEAT_SEPARATION
            assert (t["left"]["shape"], t["left"]["color"], t["right"]["shape"], t["right"]["color"]) == (source["left"]["shape"], source["left"]["color"], source["right"]["shape"], source["right"]["color"])
            assert t["correct"] == source["correct"]


def test_the_level_classes_pair_the_stated_parts_of_the_reward(built):
    _, inst, trials = built
    top = float(inst.record["max_reward"])
    level = lambda v: "H" if v >= interlude.PEAK_TOP * top else "L" if v <= interlude.PEAK_OFF * top else "M"
    for t in trials:
        if t["varied"] in ("HL", "HM", "ML", "MM"):
            better, worse = max(t["left"]["value"], t["right"]["value"]), min(t["left"]["value"], t["right"]["value"])
            assert (level(better), level(worse)) == tuple(t["varied"]), t["varied"]


def test_the_one_feature_classes_vary_that_feature_only(built):
    _, _, trials = built
    for t in trials:
        if t["varied"] == "S":
            assert t["left"]["color"] == t["right"]["color"] and t["left"]["shape"] != t["right"]["shape"]
        if t["varied"] == "C":
            assert t["left"]["shape"] == t["right"]["shape"] and t["left"]["color"] != t["right"]["color"]


def test_the_elongated_pairs_lie_on_its_axes(built):
    kind, inst, trials = built
    if kind != "bump":
        pytest.skip("elongated Gaussians only")
    angle = np.radians(inst.bumps[0]["angle"])
    axes = {"along": np.array([np.cos(angle), np.sin(angle)]), "across": np.array([-np.sin(angle), np.cos(angle)])}
    for t in trials:
        if t["varied"] in axes:
            step = np.array([t["left"]["shape"] - t["right"]["shape"], t["left"]["color"] - t["right"]["color"]])
            other = axes["across" if t["varied"] == "along" else "along"]
            assert abs(step @ other) <= 0.03 * 2 + 1e-9 and abs(step @ axes[t["varied"]]) > 0.05


def test_reward_gaps_within_a_class_are_spread(built):
    _, _, trials = built
    for cls in {t["varied"] for t in trials} - {"R"}:                 # (reversal pairs exist only among close pairs: their gaps cannot spread)
        gaps = sorted(abs(t["deltaValue"]) for t in trials if t["varied"] == cls and "repeatOf" not in t)
        if len(gaps) >= 3:
            assert gaps[-1] - gaps[0] > 0.2, (cls, gaps)


def test_no_two_distinct_trials_look_alike(built):
    _, _, trials = built
    pts = [(t["left"]["shape"], t["left"]["color"], t["right"]["shape"], t["right"]["color"]) for t in trials if "repeatOf" not in t]
    near = lambda a, b: abs(a[0] - b[0]) <= 0.03 and abs(a[1] - b[1]) <= 0.03
    alike = [(i, j) for i in range(len(pts)) for j in range(i + 1, len(pts))
             if (near(pts[i][:2], pts[j][:2]) and near(pts[i][2:], pts[j][2:])) or (near(pts[i][:2], pts[j][2:]) and near(pts[i][2:], pts[j][:2]))]
    assert not alike


def test_the_reversal_trials_are_pairs_the_separable_fit_orders_wrongly(built):
    _, inst, trials = built
    reversals = [t for t in trials if t["varied"] == "R"]
    if not reversals:
        pytest.skip("this rule has no reversal pairs to show")

    class Des:
        p = type("P", (), {"reward_function": inst.reward_function()})()
    plane = interlude._Plane(Des)
    for t in reversals:
        predicted = float(plane.separable(t["left"]["shape"], t["left"]["color"]) - plane.separable(t["right"]["shape"], t["right"]["color"]))
        assert np.sign(predicted) != np.sign(t["deltaValue"]) and abs(predicted) >= interlude.REVERSAL_MARGIN * plane.top - 1e-9


def test_the_kind_of_rule_is_read_from_the_reward_function():
    expected = {"corner": "round", "middle": "round", "elongated": "bump"}
    for kind in fi_terms.KINDS:
        assert interlude.interaction_kind(draw(kind, 1).reward_function()) == expected[kind]
    assert interlude.interaction_kind(draw("elongated", 1, tilt=0.0).reward_function()) == "bump"        # (an elongated Gaussian stays "bump" when it is axis-aligned)


def test_a_rotated_gaussian_has_reversal_pairs_to_offer_and_a_round_one_has_hardly_any():
    class Des:
        p = type("P", (), {})()
    counts = {}
    for kind in ("middle", "elongated"):
        Des.p.reward_function = draw(kind, 1).reward_function()
        plane = interlude._Plane(Des)
        counts[kind] = len(interlude._interaction_candidates(plane, "R", interlude._level_pools(plane, np.random.default_rng(0)), np.random.default_rng(0)))
    assert counts["elongated"] > 10 * max(counts["middle"], 1)


def test_apportion_gives_whole_numbers_that_sum_to_the_total():
    assert interlude._apportion(17, [3, 4, 3, 3, 2, 2, 0]) == [3, 4, 3, 3, 2, 2, 0]
    assert sum(interlude._apportion(20, [3, 3, 3, 2, 3, 3, 0])) == 20 and sum(interlude._apportion(5, [2, 2, 2])) == 5


def test_peak_and_interaction_trials_cannot_both_be_set():
    with pytest.raises(ValueError):
        interlude.generate_interlude("RW_I1", reward_function=draw("middle", 1).reward_function(), **{**OVERRIDES, "interlude_peak_trials": 3})
