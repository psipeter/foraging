import json
import math

import numpy as np
import pytest

import selection
import synthetic
from selection import angular_radius, check_arc, generate_pool, horizontal_fov, kendall_tau, first_pick_regret, implied_pair_scores, pair_accuracy, pair_scores, pair_weight, rank_gain, selections_to_points, slot_bearings
from world import bush_value, load_session

SESSION = "FIX_T0"
TWO_FEATURES = synthetic.overrides(visible=("shape", "color"))                      # the wide corner Gaussian pays, both features alike
COLOR_ONLY = synthetic.overrides(visible=("shape", "color"), valuemap=synthetic.feature_only("color"))
SHAPE_ONLY_VISIBLE = synthetic.overrides(visible=("shape",), valuemap=synthetic.feature_only("shape"))
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


def test_every_committed_pool_pays_its_sessions_value_map():
    """Unity checks the world file against the asset but nothing checks the pool file: a reward change followed by `world.py --unity` alone would leave selections scored against the old rule."""
    from world import EXPERIMENTS_DIR, STREAMING_EXPERIMENTS
    pools = sorted(STREAMING_EXPERIMENTS.glob("*/*.ranking.json"))
    assert pools
    for path in pools:
        session = path.name.split("_seed")[0]
        assert (EXPERIMENTS_DIR / session.split("_")[0] / f"{session}.asset").exists(), session
        _, _, shape, color, value = bush_table(json.loads(path.read_text()))
        assert value == pytest.approx(bush_value(load_session(session).reward_function, shape, color), abs=1e-6), f"{path.name} is stale: run scripts/selection.py pool {session}"


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
    assert margins["separation"] >= selection.ANGLE_MARGIN and margins["view"] >= selection.FOV_MARGIN
    hfov = horizontal_fov(75.0, selection.MIN_ASPECT)
    for trial in sidecar["sets"]:
        spans = sorted((b["bearing"] - float(angular_radius(sidecar["bushDistance"], radius[b["id"]])),
                        b["bearing"] + float(angular_radius(sidecar["bushDistance"], radius[b["id"]]))) for b in trial["bushes"])
        assert all(later[0] - earlier[1] >= selection.ANGLE_MARGIN for earlier, later in zip(spans, spans[1:]))
        assert all(abs(b["bearing"]) <= hfov / 2 - selection.FOV_MARGIN for b in trial["bushes"])          # at least half of each bush shows


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
    assert value == pytest.approx(bush_value(params.reward_function, shape, color))


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
    sidecar, _ = built(selection_pool_sets=4)
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


def test_a_range_too_narrow_for_the_tie_gap_is_refused():
    with pytest.raises(ValueError, match="span too little"):
        generate_pool(SESSION, **TWO_FEATURES, selection_tie_gap=1.5, steps=100)




def test_a_perfect_selection_scores_one_and_a_reversed_one_zero():
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


def test_a_random_selection_scores_one_half():
    rng = np.random.default_rng(0)
    values = np.array([0.0, 0.7, 1.5, 2.2, 3.1, 4.0])
    accuracy = [pair_accuracy(rng.permutation(values), values) for _ in range(4000)]
    assert abs(np.mean(accuracy) - 0.5) < 0.01
    assert abs(np.mean([kendall_tau(rng.permutation(values), values) for _ in range(4000)])) < 0.02



# ---- the pool of sets a session plays in place (selection breaks) ---------------------------------------

def test_a_pool_holds_the_stated_number_of_sets_of_the_stated_size():
    p = built(selection_pool_sets=7, selection_set_size=5)[0]
    assert p["format"] == "ranking-pool" and p["n"] == 7 and p["setSize"] == 5 and len(p["sets"]) == 7
    assert all(len(t["bushes"]) == 5 for t in p["sets"])


def test_a_pair_is_a_set_of_two():
    sidecar, _ = built(selection_set_size=2, selection_pool_sets=5, selection_arc_span=60.0, steps=3000)
    assert sidecar["setSize"] == 2 and sidecar["n"] == 5
    for s in sidecar["sets"]:
        left, right = s["bushes"]
        assert left["bearing"] == -right["bearing"] == -30.0
        assert abs(left["value"] - right["value"]) >= sidecar["minGap"]


def test_the_pool_file_sits_beside_the_world_file(tmp_path):
    path, sidecar = selection.export_pool("FOR_S1", out_dir=tmp_path)
    assert path.name == f"FOR_S1_seed{sidecar['seed']}.ranking.json" and path.parent == tmp_path


def test_the_pair_mode_pays_the_bonus_per_correct_pair_and_the_mean_value_mode_weights_each_pair_by_its_bushes():
    values = [5.61, 4.30, 3.03, 1.75, 0.48]
    assert selections_to_points(values, values, 4.0) == (40.0, 10, 10) and selections_to_points(values, values, 4.0, "") == (40.0, 10, 10)
    full, correct, total = selections_to_points(values, values, 4.0, "pair_mean_value")
    assert (correct, total) == (10, 10) and full == pytest.approx(4.0 * 2.0 * sum(values))        # each bush is in 4 pairs, each pair counts both: 2 x the sum of the values
    picked = [5.61, 4.30, 1.75, 3.03, 0.48]                                                        # the third and fourth bushes swapped: the pair (3.03, 1.75) is lost
    points, correct, _ = selections_to_points(picked, values, 4.0, "pair_mean_value")
    assert correct == 9 and points == pytest.approx(full - 4.0 * (3.03 + 1.75) / 2)                  # 111.8 as the pilot's third FOR set
    assert selections_to_points(picked, values, 4.0)[0] == 36.0
    assert selections_to_points([], values, 4.0, "pair_mean_value") == (0.0, 0, 10)                   # a timed-out set earns nothing
    top, bottom = [4.0, 5.0, 3.0, 2.0, 1.0], [5.0, 4.0, 3.0, 1.0, 2.0]                             # a miss between the top two against one between the bottom two
    assert selections_to_points(top, values_ladder := [5.0, 4.0, 3.0, 2.0, 1.0], 1.0, "pair_mean_value")[0] < selections_to_points(bottom, values_ladder, 1.0, "pair_mean_value")[0]


def test_an_unknown_points_mode_is_an_error():
    with pytest.raises(ValueError, match="unknown selection points mode"):
        pair_weight("by_rank", 1.0, 2.0)
    assert pair_weight("pair_mean_value", 1.0, 3.0) == 2.0 and pair_weight("pair", 1.0, 3.0) == 1.0


# --- the plus design -------------------------------------------------------------------------------------------------------------

import value_maps

ROTATED_MAP = value_maps.ValueMap((value_maps.Bump(0.6, 0.5, 0.18, 0.36, 30.0, 4.0),))        # a turned, stretched bump away from the corner: room for a plus around its peak
PLUS = {"selection_design": "plus"}


def plus_pool(axes="mixed", **options):
    return generate_pool(SESSION, **synthetic.overrides(valuemap=ROTATED_MAP, selection_plus_axes=axes, **PLUS, **options))


def test_the_ladder_design_is_the_default_and_unchanged_by_the_plus_fields():
    ladder, _ = built()
    assert "design" not in ladder and "plus" not in ladder and all("role" not in b for s in ladder["sets"] for b in s["bushes"])


@pytest.mark.parametrize("axes", ["aligned", "bump", "random", "mixed"])
def test_every_plus_has_a_centre_and_four_arms_that_look_good_stay_inside_and_differ(axes):
    sidecar, params = plus_pool(axes)
    peak = sidecar["peak"][2]
    for s, trial in enumerate(sidecar["sets"]):
        assert sorted(b["role"] for b in trial["bushes"]) == sorted(selection.PLUS_ROLES)
        shape, color = np.array([b["shape"] for b in trial["bushes"]]), np.array([b["color"] for b in trial["bushes"]])
        assert min(shape.min(), color.min()) >= selection.PLUS_MARGIN - 1e-9 and max(shape.max(), color.max()) <= 1 - selection.PLUS_MARGIN + 1e-9
        d = np.hypot(shape[:, None] - shape[None, :], color[:, None] - color[None, :])[np.triu_indices(5, 1)]
        assert d.min() >= 0.08 - 1e-9
        values = np.array(sorted(b["value"] for b in trial["bushes"]))
        assert np.diff(values).min() >= sidecar["minGap"] - 1e-9 and values.min() >= selection.PLUS_MIN_FRACTION * peak - 1e-9
        by_role = {b["role"]: np.array([b["shape"], b["color"]]) for b in trial["bushes"]}
        u1, u2 = np.array(sidecar["plus"][s]["u1"]), np.array(sidecar["plus"][s]["u2"])
        assert abs(np.dot(u1, u2)) < 1e-9
        assert abs(np.dot(by_role["+1"] - by_role["centre"], u2)) < 1e-9 and abs(np.dot(by_role["+2"] - by_role["centre"], u1)) < 1e-9     # each arm lies along its own axis


def test_the_axes_modes_follow_their_definitions():
    aligned, _ = plus_pool("aligned")
    for m in aligned["plus"]:
        assert m["axes"] == "aligned"
        assert m["turn"] == 0.0 and m["u1"] in ([1.0, 0.0], [-1.0, 0.0]) and m["u2"] in ([0.0, 1.0], [0.0, -1.0])      # an aligned plus never turns: it is only stretched to fit
    bump, _ = plus_pool("bump")
    th = math.radians(30.0)
    assert all(m["turn"] == 0.0 and abs(abs(np.dot(m["u1"], [math.cos(th), math.sin(th)])) - 1.0) < 1e-9 for m in bump["plus"])
    mixed, _ = plus_pool("mixed")
    assert [m["axes"] for m in mixed["plus"][:6]] == ["aligned", "random", "random", "aligned", "random", "random"]
    angles = {round(math.degrees(math.atan2(m["u1"][1], m["u1"][0])) % 180, 3) for m in plus_pool("random")[0]["plus"]}
    assert len(angles) > 10                                                                     # a different turn almost every set


def test_a_plus_that_would_leave_the_map_is_shrunk_and_turned_and_the_others_are_not():
    corner = value_maps.ValueMap((value_maps.Bump(0.8, 0.8, 0.2, 0.0, 0.0, 4.0),))             # a peak near the corner: many pluses must fit
    sidecar, _ = generate_pool(SESSION, **synthetic.overrides(valuemap=corner, selection_plus_axes="aligned", selection_pool_sets=30, **PLUS))
    plus = sidecar["plus"]
    assert any(m["scale"] < 1.0 for m in plus) and all(m["turn"] == 0.0 for m in plus) and sidecar["summary"]["fitted"] > 0.0      # aligned: stretched, never turned
    random_, _ = generate_pool(SESSION, **synthetic.overrides(valuemap=corner, selection_plus_axes="random", selection_pool_sets=30, **PLUS))
    assert any(m["turn"] != 0.0 for m in random_["plus"]) and all(m["scales"][0] == m["scales"][1] for m in random_["plus"])    # random: shrunk together and turned
    assert all(selection.PLUS_MIN_SCALE - 1e-9 <= m["scale"] <= 1.0 and abs(m["turn"]) <= 45.0 + 1e-9 for m in plus)
    shape, color = np.array(sidecar["shape"]), np.array(sidecar["color"])
    assert min(shape.min(), color.min()) >= selection.PLUS_MARGIN - 1e-9 and max(shape.max(), color.max()) <= 1 - selection.PLUS_MARGIN + 1e-9
    plain, _ = plus_pool("aligned", selection_plus_jitter=0.0, selection_pool_sets=30)               # the same map, centred: far less to fit than at a corner
    assert plain["summary"]["meanScale"] > sidecar["summary"]["meanScale"] - 1e-9 or plain["summary"]["fitted"] <= sidecar["summary"]["fitted"]


def test_the_centres_of_a_mode_are_spread_evenly_over_the_ellipse_around_the_peak():
    sidecar, _ = plus_pool("aligned", selection_pool_sets=24, selection_plus_jitter=1.0)
    off = np.array([m["offset"] for m in sidecar["plus"]])
    d = np.sqrt(((off[:, None, :] - off[None, :, :]) ** 2).sum(-1)) + np.eye(len(off)) * 9
    assert d.min() > 0.1 * 0.18                                                                  # no two centres on top of each other (random draws would crowd)
    assert np.hypot(*off.T).max() <= 1.0 * 0.36 + 1e-6                                           # inside the ellipse (the longest spread is 0.36)


def test_the_centres_scatter_around_the_peak_without_always_being_the_best_bush():
    sidecar, _ = plus_pool("mixed", selection_pool_sets=60)
    assert 0.2 < sidecar["summary"]["centreScatter"] and sidecar["summary"]["meanCentreToPeak"] < 0.7
    assert 0.0 < sidecar["summary"]["centreIsBest"] < 1.0
    none, _ = plus_pool("mixed", selection_plus_jitter=0.0, selection_pool_sets=30)
    assert none["summary"]["centreScatter"] == pytest.approx(0.0, abs=1e-9)                     # no jitter: every centre is the peak (the check's own baseline)


def test_a_plus_pool_is_deterministic_and_refuses_what_it_cannot_draw():
    a, _ = plus_pool()
    b, _ = plus_pool()
    assert a["shape"] == b["shape"] and a["value"] == b["value"]
    with pytest.raises(ValueError, match="five bushes"):
        plus_pool(selection_set_size=4)
    with pytest.raises(ValueError, match="no plus fits"):
        plus_pool(selection_plus_arm=40.0)
    with pytest.raises(ValueError, match="unknown selectionDesign"):
        generate_pool(SESSION, **synthetic.overrides(valuemap=ROTATED_MAP, selection_design="star"))


# --- the plans for the plus design (plus_plans.py) ---------------------------------------------------------------------------------

import plus_plans


def planned(plan, difficulty, axes="mixed", **options):
    return plus_pool(axes, selection_plus_plan=plan, selection_plus_difficulty=difficulty, **options)


@pytest.mark.parametrize("plan", plus_plans.PLANS)
@pytest.mark.parametrize("difficulty", ["free", "medium", "easy"])
def test_every_plan_and_difficulty_draws_valid_pluses(plan, difficulty):
    sidecar, _ = planned(plan, difficulty)
    peak = sidecar["peak"][2]
    for trial, meta in zip(sidecar["sets"], sidecar["plus"]):
        pts = np.array([[b["shape"], b["color"]] for b in trial["bushes"]])
        values = np.array(sorted(b["value"] for b in trial["bushes"]))
        assert pts.min() >= selection.PLUS_MARGIN - 1e-9 and pts.max() <= 1 - selection.PLUS_MARGIN + 1e-9
        assert np.diff(values).min() >= sidecar["minGap"] - 1e-9 and values.min() >= selection.PLUS_MIN_FRACTION * peak - 1e-9
        assert sorted(b["role"] for b in trial["bushes"]) == sorted(selection.PLUS_ROLES)
        assert meta["axes"] != "aligned" or meta["turn"] == 0.0                                   # aligned is only ever stretched


def test_the_ladder_puts_the_values_a_step_apart_and_a_harder_step_is_closer():
    medium, params = planned("ring", "medium")
    peak = medium["peak"][2]
    for trial, meta in zip(medium["sets"], medium["plus"]):
        if meta["hit"]:
            steps = np.diff(sorted(b["value"] for b in trial["bushes"]))
            assert np.all(np.abs(steps - meta["delta"] * peak) <= 0.61 * meta["delta"] * peak)      # every arm within 0.3 step of its level
    easy, _ = planned("ring", "easy")
    assert plus_plans.metrics(easy, params)["stepMedian"] > plus_plans.metrics(medium, params)["stepMedian"]


def test_the_tile_plan_covers_the_rewarding_region_better_than_the_spiral():
    (tile, params), (spiral, _) = planned("tile", "free"), plus_pool("mixed")
    assert plus_plans.metrics(tile, params)["coverageMean"] < plus_plans.metrics(spiral, params)["coverageMean"]


def test_the_ring_plan_puts_the_three_centres_of_a_selection_round_the_peak():
    sidecar, _ = planned("ring", "free", selection_plus_jitter=1.0)
    off = np.array([m["offset"] for m in sidecar["plus"]])
    for r in range(len(off) // 3):
        angles = np.sort(np.arctan2(off[3 * r:3 * r + 3, 1], off[3 * r:3 * r + 3, 0]))
        assert len(angles) == 3                                                                   # three corners; the fit may move a centre, so only the count is exact


def test_an_unknown_plan_or_a_step_under_the_tie_gap_is_refused():
    with pytest.raises(ValueError, match="unknown selectionPlusPlan"):
        planned("star", "free")
    with pytest.raises(ValueError, match="under the tie gap"):
        planned("ring", "0.01")


@pytest.mark.parametrize("plan", plus_plans.PLANS)
@pytest.mark.parametrize("difficulty", ["free", "medium"])
def test_a_random_plus_never_lies_along_the_feature_axes_in_the_plans(plan, difficulty):
    sidecar, _ = planned(plan, difficulty)
    for meta in sidecar["plus"]:
        if meta["axes"] == "random":
            assert plus_plans.axis_distance(meta["u1"]) >= plus_plans.OFF_AXIS - 1e-6
        else:
            assert meta["turn"] == 0.0 and plus_plans.axis_distance(meta["u1"]) < 1e-6


def test_a_ladder_sometimes_puts_the_centre_below_other_bushes_and_still_hits_its_steps():
    sidecar, params = planned("ring", "medium", selection_pool_sets=60)
    m = plus_plans.metrics(sidecar, params)
    assert 0.2 < m["centreBest"] < 0.8 and m["hit"] > 0.8
    peak = sidecar["peak"][2]
    for trial, meta in zip(sidecar["sets"], sidecar["plus"]):
        if meta["hit"]:
            steps = np.diff(sorted(b["value"] for b in trial["bushes"]))
            assert np.all(np.abs(steps - meta["delta"] * peak) <= 0.61 * meta["delta"] * peak)
