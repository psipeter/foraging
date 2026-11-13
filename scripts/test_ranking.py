import math

import numpy as np
import pytest

import ranking
import synthetic
from ranking import angular_radius, check_arc, generate_pool, horizontal_fov, kendall_tau, first_pick_regret, implied_pair_scores, pair_accuracy, pair_scores, rank_gain, slot_bearings
from world import bush_value

SESSION = "FIX_T0"
TWO_FEATURES = synthetic.overrides(visible=("shape", "color"), weights={"shape": 0.5, "color": 0.5})
COLOR_ONLY = synthetic.overrides(visible=("shape", "color"), weights={"color": 1.0})
SHAPE_ONLY_VISIBLE = synthetic.overrides(visible=("shape",), weights={"shape": 1.0})
_CACHE = {}


def built(label="two", **options):
    key = (label, tuple(sorted(options.items())))
    if key not in _CACHE:
        base = {"two": TWO_FEATURES, "color": COLOR_ONLY, "shape": SHAPE_ONLY_VISIBLE}[label]
        _CACHE[key] = generate_pool(SESSION, **base, **options)
    return _CACHE[key]


def bush_table(sidecar):
    pos = np.asarray(sidecar["treePos"]).reshape(-1, 2)
    return pos, np.asarray(sidecar["canopyRadius"]), np.asarray(sidecar["shape"]), np.asarray(sidecar["color"]), np.asarray(sidecar["value"])


# ---- geometry -------------------------------------------------------------------------------------

def test_every_bush_has_the_same_edge_distance_and_the_slots_bearing():
    sidecar, _ = built()
    pos, radius, *_ = bush_table(sidecar)
    for trial in sidecar["sets"]:
        for b in trial["bushes"]:
            x, z = pos[b["id"]]
            assert math.hypot(x, z) - radius[b["id"]] == pytest.approx(sidecar["bushDistance"], abs=1e-9)
            assert math.degrees(math.atan2(x, z)) == pytest.approx(b["bearing"], abs=1e-9)
        assert sorted(b["slot"] for b in trial["bushes"]) == list(range(sidecar["setSize"]))
        assert trial["start"] == [0.0, 0.0] and trial["yaw"] == 0.0


def test_canopies_never_overlap_in_the_view_and_fit_a_narrow_window():
    sidecar, params = built()
    pos, radius, *_ = bush_table(sidecar)
    margins = sidecar["margins"]
    assert margins["separation"] >= ranking.ANGLE_MARGIN and margins["view"] >= ranking.FOV_MARGIN
    hfov = horizontal_fov(75.0, ranking.MIN_ASPECT)
    for trial in sidecar["sets"]:
        spans = sorted((b["bearing"] - float(angular_radius(sidecar["bushDistance"], radius[b["id"]])),
                        b["bearing"] + float(angular_radius(sidecar["bushDistance"], radius[b["id"]]))) for b in trial["bushes"])
        assert all(later[0] - earlier[1] >= ranking.ANGLE_MARGIN for earlier, later in zip(spans, spans[1:]))
        assert all(abs(b["bearing"]) <= hfov / 2 - ranking.FOV_MARGIN for b in trial["bushes"])          # at least half of each bush shows


def test_an_arc_that_cannot_hold_the_set_is_refused():
    _, params = built()
    with pytest.raises(ValueError, match="neighbouring canopies"):
        check_arc(params, 5, 84.0, 12.0)
    with pytest.raises(ValueError, match="window"):
        check_arc(params, 3, 120.0, 40.0)


def test_slot_bearings_are_symmetric_and_one_slot_looks_straight_ahead():
    assert slot_bearings(5, 60.0).tolist() == pytest.approx([-30.0, -15.0, 0.0, 15.0, 30.0])
    assert slot_bearings(1, 60.0).tolist() == [0.0]


# ---- the sets -------------------------------------------------------------------------------------

def test_values_are_the_rewards_of_the_bushes_and_a_set_has_one_moisture():
    sidecar, params = built()
    _, _, shape, color, value = bush_table(sidecar)
    moisture = np.asarray(sidecar["moisture"])
    assert np.ptp(moisture) == 0.0 and moisture[0] == sidecar["groundMoisture"]
    assert value == pytest.approx(bush_value(params.reward_function, shape, color, moisture))


def test_every_set_is_a_ladder_with_no_tie_and_the_sets_are_disjoint():
    sidecar, _ = built()
    seen = set()
    for trial in sidecar["sets"]:
        values = sorted(b["value"] for b in trial["bushes"])
        assert np.diff(values).min() >= sidecar["minGap"] - 1e-9 and trial["minGap"] == pytest.approx(np.diff(values).min())
        assert trial["trueOrder"] == [b["id"] for b in sorted(trial["bushes"], key=lambda b: -b["value"])]
        ids = {b["id"] for b in trial["bushes"]}
        assert not ids & seen
        seen |= ids
    assert len(seen) == len(sidecar["canopyRadius"]) == sidecar["n"] * sidecar["setSize"]


def test_the_sets_together_fill_the_value_range_and_each_spans_it():
    sidecar, _ = built(set_count=4)
    spans = [t["valueSpan"] for t in sidecar["sets"]]
    allv = np.asarray(sidecar["value"])
    assert min(spans) > 0.8 * np.ptp(allv)                                 # each set covers about the whole range
    levels = np.sort(allv)
    assert np.diff(levels).max() < 0.25 * np.ptp(levels)                    # and the union leaves no big hole


def test_the_bushes_spread_over_the_feature_plane_and_a_hidden_feature_stays_fixed():
    sidecar, params = built(label="color")
    _, _, shape, color, _ = bush_table(sidecar)
    assert np.ptp(shape) > 0.7 and np.ptp(color) > 0.7                      # the feature that does not pay still varies and is spread
    sidecar, params = built(label="shape")
    _, _, shape, color, _ = bush_table(sidecar)
    assert np.ptp(color) == 0.0 and color[0] == params.color_when_fixed and np.ptp(shape) > 0.7


def test_same_seed_same_file_and_other_seed_other_file():
    a, _ = generate_pool(SESSION, **TWO_FEATURES, world_seed=5, steps=2000)
    b, _ = generate_pool(SESSION, **TWO_FEATURES, world_seed=5, steps=2000)
    c, _ = generate_pool(SESSION, **TWO_FEATURES, world_seed=6, steps=2000)
    assert a == b and a != c


def test_a_reward_on_moisture_is_refused():
    with pytest.raises(ValueError, match="moisture"):
        generate_pool(SESSION, **synthetic.overrides(weights={"moisture": 1.0}, visible=("shape", "color", "moisture")), steps=100)


def test_a_range_too_narrow_for_the_tie_gap_is_refused():
    with pytest.raises(ValueError, match="span too little"):
        generate_pool(SESSION, **TWO_FEATURES, min_gap=1.5, steps=100)




def test_a_perfect_ranking_scores_one_and_a_reversed_one_zero():
    values = [3.0, 2.0, 1.0, 0.0]
    assert pair_scores(values, values) == (6, 6)
    assert pair_scores(values[::-1], values) == (0, 6)
    assert kendall_tau(values, values) == 1.0 and kendall_tau(values[::-1], values) == -1.0
    assert first_pick_regret(values, values) == 0.0 and first_pick_regret(values[::-1], values) == 3.0
    assert rank_gain(values, values) == pytest.approx(1.0) and rank_gain(values[::-1], values) == pytest.approx(0.0)


def test_ties_are_not_counted_and_unpicked_bushes_sit_below_the_picked():
    assert pair_scores([2.0, 1.0, 1.02], [2.0, 1.0, 1.02]) == (2, 2)               # the near tie is left out
    assert implied_pair_scores([2.0], [2.0, 1.0, 0.0]) == (2, 2)                   # (analysis) one pick over two unpicked: right
    assert implied_pair_scores([0.0], [2.0, 1.0, 0.0]) == (0, 2)                   # the worst picked first
    assert math.isnan(pair_accuracy([1.0], [1.0, 1.01]))                           # nothing to score


def test_the_payout_counts_every_pair_with_an_unranked_bush_as_incorrect():
    values = [4.0, 3.0, 2.0, 1.0, 0.0]
    assert pair_scores(values, values) == (10, 10)
    assert pair_scores(values[:3], values) == (3, 10)                              # three ranked, right: only their 3 pairs; the 7 others are wrong
    assert pair_scores([], values) == (0, 10)                                      # a timed-out set earns nothing
    assert pair_scores([0.0, 1.0, 2.0, 3.0, 4.0], values) == (0, 10)
    assert pair_scores([4.0, 3.0], [4.0, 3.0, 3.02, 0.0]) == (1, 5)                # the near tie is left out of total


def test_a_random_ranking_scores_one_half():
    rng = np.random.default_rng(0)
    values = np.array([0.0, 0.7, 1.5, 2.2, 3.1, 4.0])
    accuracy = [pair_accuracy(rng.permutation(values), values) for _ in range(4000)]
    assert abs(np.mean(accuracy) - 0.5) < 0.01
    assert abs(np.mean([kendall_tau(rng.permutation(values), values) for _ in range(4000)])) < 0.02



# ---- the pool of sets a session plays in place (ranking breaks) ---------------------------------------

def test_a_pool_holds_the_stated_number_of_sets_of_the_stated_size():
    p = built(set_count=7, set_size=5)[0]
    assert p["format"] == "ranking-pool" and p["n"] == 7 and p["setSize"] == 5 and len(p["sets"]) == 7
    assert all(len(t["bushes"]) == 5 for t in p["sets"])


def test_the_pool_default_is_the_session_field_or_twelve_sets():
    assert ranking.POOL_SETS == 12
    assert built()[0]["n"] == 12


def test_a_pool_set_is_a_value_ladder_with_every_gap_at_least_the_tie_gap():
    p = built(set_count=4, set_size=5, min_gap=0.25)[0]
    for t in p["sets"]:
        assert t["minGap"] >= 0.25 - 1e-9


def test_a_pair_is_a_set_of_two():
    sidecar, _ = built(set_size=2, set_count=5, arc_span=60.0, steps=3000)
    assert sidecar["setSize"] == 2 and sidecar["n"] == 5
    for s in sidecar["sets"]:
        left, right = s["bushes"]
        assert left["bearing"] == -right["bearing"] == -30.0
        assert abs(left["value"] - right["value"]) >= sidecar["minGap"]


def test_the_pool_file_sits_beside_the_world_file(tmp_path):
    path, sidecar = ranking.export_pool("FOR_S1", out_dir=tmp_path)
    assert path.name == f"FOR_S1_seed{sidecar['seed']}.ranking.json" and path.parent == tmp_path
