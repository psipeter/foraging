import math
import json

import numpy as np
import pytest

import synthetic
from ranking import generate_ranking, sidecar_path as ranking_sidecar_path
from interlude import (FEATURES, TIE_TOLERANCE, bush_position, canopy_radius,
                       check_geometry, generate_interlude, has_hump, sidecar_path, write_sidecar)
from interlude import CANOPY_AIM_HEIGHT, HUMP_TOLERANCE
from legacy_sessions import legacy
from world import bush_value, check_values, generate_world, load_session, session_features

# The generator tests are about the generator, not about a shipped session: each case is a stated configuration (synthetic.py, or an archived old session from
# legacy_sessions.py) generated on the tutorial's Interlude asset, the one that stays whatever experiments come and go.
ASSET = "TUT_I1"
BOTH_VARY = {"shape_varies": True, "color_varies": True}


def _practice_stand_in():
    """The practice session (a random reward no feature predicts) is stood in for by a shape-linear reward."""
    return synthetic.overrides(visible=synthetic.FEATURES, weights={"shape": 1.0}, moisture_is_feature=False)


CASES = {
    "practice": _practice_stand_in(),
    "one feature": synthetic.overrides(visible=synthetic.FEATURES, weights={"color": 1.0}, moisture_is_feature=False),
    "two features": synthetic.overrides(visible=synthetic.FEATURES, weights={"shape": 0.6, "color": 0.4}, direction={"color": 1}, moisture_is_feature=False),
    "old S3": {**BOTH_VARY, **legacy("S3")},          # moisture paying, terraces (the archived old sessions exercise the generator's moisture and bump logic)
    "old S4": {**BOTH_VARY, **legacy("S4")},
    "old S5": {**BOTH_VARY, **legacy("S5")},
}
NAMES = ["practice", "one feature", "two features", "old S3", "old S4"]

# Generating an Interlude searches thousands of placements (seconds each), so each one is generated once per run.
_CACHE = {}


def generate(case, **kw):
    """The Interlude of a case: the tutorial's Interlude asset with the case's overrides (they apply to the session it probes as well)."""
    return generate_interlude(ASSET, **{**CASES[case], **kw})


def design_overrides(case):
    return CASES[case]


def get(name):
    """A short random-mode Interlude of an asset (whatever the asset's own interludeMode is; the geometry and view tests are about any kind),
    with its own length (3 trials practice, 10 otherwise), not the asset's."""
    if name not in _CACHE:
        _CACHE[name] = generate(name, mode="random", interlude_trial_count=3 if name == "practice" else 10)
    return _CACHE[name]


@pytest.fixture(scope="module", params=NAMES)
def built(request):
    sidecar, params, terrain = get(request.param)
    return request.param, sidecar, params, terrain


RANDOM_NAMES = ["one feature", "old S3"]
_RANDOM = {}


def get_random(name, seed=None):
    if (name, seed) not in _RANDOM:
        _RANDOM[(name, seed)] = generate(name, mode="random", interlude_trial_count=50, seed=seed)
    return _RANDOM[(name, seed)]


@pytest.fixture(scope="module", params=RANDOM_NAMES)
def built_random(request):
    sidecar, params, terrain = get_random(request.param)
    return request.param, sidecar, params, terrain


@pytest.fixture(scope="module", params=[(n, "short") for n in NAMES] + [(n, "random") for n in RANDOM_NAMES])
def built_any(request):
    """Every kind of generated Interlude: the generic geometry, terrain and view checks hold for each."""
    name, mode = request.param
    sidecar, params, terrain = get(name) if mode == "short" else get_random(name)
    return name, sidecar, params, terrain


@pytest.mark.slow
def test_deterministic():
    # a smaller search keeps this fast; the property (same inputs, same output) does not depend on its size
    a, *_ = generate("old S3", pool_samples=120_000, mode="random")
    b, *_ = generate("old S3", pool_samples=120_000, mode="random")
    assert a == b


def _same(a, b, tol=1e-6):
    """Recursive equality: numbers within `tol` (floating-point noise across machines), everything else exactly."""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k], tol) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(_same(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= tol
    return a == b


@pytest.mark.slow
def test_committed_interlude_files_are_fresh():
    """Unity does not warn when an *.interlude.json is stale. Regenerating from the current assets (the session's terrain, seed and reward function, and the
    Interlude's own geometry, mode and trial count) must give the committed file, for every Interlude of every experiment."""
    from world import EXPERIMENTS_DIR
    for path in sorted(EXPERIMENTS_DIR.glob("*/*_I*.asset")):
        name = path.stem
        ranked = int(getattr(load_session(name), "interlude_format", 0)) == 1
        sidecar = (generate_ranking if ranked else generate_interlude)(name)[0]
        committed = (ranking_sidecar_path if ranked else sidecar_path)(name, sidecar["seed"])
        assert committed.exists(), f"{committed} is missing: run scripts/{'ranking' if ranked else 'interlude'}.py {name}"
        assert _same(json.load(open(committed)), json.loads(json.dumps(sidecar))), f"{committed.name} is stale: re-run ./venv/bin/python scripts/interlude.py {name}"


def test_interlude_assets_copy_the_session_they_probe(built):
    name, sidecar, params, terrain = built
    base = load_session(params.interlude_for, **design_overrides(name))
    assert params.reward_function == base.reward_function
    assert int(params.world_seed) == int(base.world_seed) == sidecar["seed"]
    assert check_values(params) == check_values(base)           # every terrain parameter is a copy


def test_trial_counts(built):
    name, sidecar, params, terrain = built
    n = int(params.interlude_trial_count)
    assert sidecar["n"] == n == len(sidecar["trials"]) and len(sidecar["shape"]) == 2 * n
    assert n == (3 if name == "practice" else 10)


def test_bush_table_matches_trials_and_reward_function(built_any):
    name, sidecar, params, terrain = built_any
    for t in sidecar["trials"]:
        for key, off in (("left", 0), ("right", 1)):
            b = t[key]
            i = t["index"] * 2 + off
            assert b["id"] == i
            assert b["value"] == pytest.approx(float(bush_value(params.reward_function, b["shape"], b["color"], b["moisture"])))
            assert sidecar["value"][i] == pytest.approx(b["value"])
            assert (sidecar["shape"][i], sidecar["color"][i], sidecar["moisture"][i]) == pytest.approx(
                (b["shape"], b["color"], b["moisture"]))
            assert sidecar["canopyRadius"][i] == pytest.approx(float(canopy_radius(params, b["shape"])))
    assert len(sidecar["fruitRewards"]) == 2 * sidecar["n"] * sidecar["fruitCount"]
    assert sidecar["fruitCount"] == int(params.fruit_count)


def test_bush_moisture_is_the_terrains_moisture_at_its_position(built_any):
    """No Interlude-specific terrain: each bush's moisture is what the session's terrain has where it stands."""
    name, sidecar, params, terrain = built_any
    pos = np.array(sidecar["treePos"]).reshape(-1, 2)
    m = terrain.moisture(pos[:, 0], pos[:, 1])
    assert np.allclose(m, sidecar["moisture"], atol=1e-6)
    assert terrain.is_tree_site(pos[:, 0], pos[:, 1]).all()         # all bushes in the valley, away from the mountains


def test_bushes_are_equal_in_the_terms_the_harvest_rules_use(built_any):
    """Equal distance to each canopy's edge and equal inner-edge bearing on opposite sides of the heading, whatever the
    radii (which depend on shape), so turning and walking to either bush is the same."""
    name, sidecar, params, terrain = built_any
    check_geometry(params)
    edge = float(params.interlude_bush_distance)
    bearing = float(params.interlude_bush_bearing)
    gap = float(params.harvest_range_gap_base)
    pos = np.array(sidecar["treePos"]).reshape(-1, 2)
    radius = np.array(sidecar["canopyRadius"])
    radii_differ = False
    for t in sidecar["trials"]:
        spawn = np.array(t["start"])
        yaw = np.radians(t["yaw"])
        fwd = np.array([np.sin(yaw), np.cos(yaw)])
        right = np.array([np.cos(yaw), -np.sin(yaw)])
        i = t["index"]
        radii_differ |= abs(radius[2 * i] - radius[2 * i + 1]) > 0.1
        for k, side, sign in ((0, "left", -1.0), (1, "right", 1.0)):
            c = pos[2 * i + k]
            r = radius[2 * i + k]
            assert tuple(c) == pytest.approx(tuple(bush_position(params, spawn, yaw, side, r)))
            d = c - spawn
            dist = np.hypot(*d)
            assert dist - r == pytest.approx(edge)                                       # same edge distance
            inner = sign * np.degrees(np.arctan2(d @ right, d @ fwd)) - np.degrees(np.arcsin(r / dist))
            assert inner == pytest.approx(bearing)                                       # same edge bearing, mirrored
            assert abs(float(d @ right)) >= gap + r                                      # needs a turn to harvest
    assert radii_differ or len(sidecar["trials"]) <= 3                                   # the check is not vacuous


def test_correct_side_matches_true_values_and_is_roughly_balanced(built):
    name, sidecar, params, terrain = built
    for t in sidecar["trials"]:
        d = t["left"]["value"] - t["right"]["value"]
        assert t["deltaValue"] == pytest.approx(d)
        want = "either" if abs(d) < TIE_TOLERANCE else ("left" if d > 0 else "right")
        assert t["correct"] == want
    sides = [t["correct"] for t in sidecar["trials"]]
    assert abs(sides.count("left") - sides.count("right")) <= len(sides) // 2 + 1     # 3-2 or 4-1 passes, all one side does not


def test_spawn_points_are_spread_out(built_any):
    name, sidecar, params, terrain = built_any
    s = np.array([t["start"] for t in sidecar["trials"]])
    d = np.hypot(*(s[:, None] - s[None]).transpose(2, 0, 1))
    np.fill_diagonal(d, np.inf)
    assert d.min() >= 40


def test_bushes_have_a_clear_view_from_the_spawn(built_any):
    name, sidecar, params, terrain = built_any
    pos = np.array(sidecar["treePos"]).reshape(-1, 2)
    eye = float(params.eye_height)
    for t in sidecar["trials"]:
        s = np.array(t["start"])
        cam = float(terrain.elevation(*s)) + eye
        for k in (0, 1):
            b = pos[2 * t["index"] + k]
            target = float(terrain.elevation(*b)) + CANOPY_AIM_HEIGHT
            ts = np.linspace(0.05, 0.95, 14)
            ground = terrain.elevation(s[0] + ts * (b[0] - s[0]), s[1] + ts * (b[1] - s[1]))
            assert not np.any(ground + 0.3 > cam + ts * (target - cam))


def test_export_writes_only_the_sidecar(tmp_path):
    sidecar = get("old S3")[0]
    path = write_sidecar(sidecar, ASSET, tmp_path)
    assert path == sidecar_path(ASSET, sidecar["seed"], tmp_path)
    assert path.name == f"{ASSET}_seed{sidecar['seed']}.interlude.json"
    assert list(tmp_path.glob("*.world")) == []                      # the terrain is the session's own world file
    assert json.load(open(path))["n"] == 10
    assert path.stat().st_size < 50_000


def test_no_hill_between_the_spawn_and_either_bush(built_any):
    """The ground must not rise and then fall on the way to a bush (a hill would hide it)."""
    name, sidecar, params, terrain = built_any
    pos = np.array(sidecar["treePos"]).reshape(-1, 2)
    for t in sidecar["trials"]:
        for k in (0, 1):
            assert not has_hump(terrain, np.array(t["start"]), pos[2 * t["index"] + k], params)


def test_has_hump_detects_a_hill_but_not_a_slope_or_a_dip():
    class Ground:
        def __init__(self, f):
            self.f = f

        def elevation(self, x, z):
            return self.f(np.asarray(x, dtype=float))

    hill = Ground(lambda x: 4.0 * np.exp(-((x - 10.0) ** 2) / 8.0))
    slope = Ground(lambda x: 0.3 * x)
    descent = Ground(lambda x: -0.3 * x)
    dip = Ground(lambda x: -4.0 * np.exp(-((x - 10.0) ** 2) / 8.0))
    flat = Ground(lambda x: 0.0 * x)
    a, b = np.array([0.0, 0.0]), np.array([20.0, 0.0])
    assert has_hump(hill, a, b)
    assert not has_hump(slope, a, b) and not has_hump(descent, a, b)
    assert not has_hump(dip, a, b) and not has_hump(flat, a, b)
    small = Ground(lambda x: 0.3 * np.exp(-((x - 10.0) ** 2) / 8.0))
    assert HUMP_TOLERANCE > 0.3 and not has_hump(small, a, b)


# --- random mode -----------------------------------------------------------------------------------------------------

def test_random_mode_has_only_random_trials_each_with_a_correct_side(built_random):
    name, sidecar, params, terrain = built_random
    assert sidecar["mode"] == "random" and sidecar["n"] == 50 == len(sidecar["trials"])
    assert {t["type"] for t in sidecar["trials"]} == {"random"} and {t["varied"] for t in sidecar["trials"]} == {""}
    for t in sidecar["trials"]:
        d = t["left"]["value"] - t["right"]["value"]
        assert abs(d) >= TIE_TOLERANCE and t["correct"] == ("left" if d > 0 else "right")      # never an "either" trial
    sides = [t["correct"] for t in sidecar["trials"]]
    assert sides.count("left") == sides.count("right") == 25


def test_random_mode_draws_shape_and_colour_freely_and_moisture_from_the_terrain(built_random):
    name, sidecar, params, terrain = built_random
    shape = np.array(sidecar["shape"])
    color = np.array(sidecar["color"])
    assert shape.min() < 0.1 and shape.max() > 0.9 and color.min() < 0.1 and color.max() > 0.9
    assert abs(np.corrcoef(shape[0::2], shape[1::2])[0, 1]) < 0.5           # the two bushes of a trial are independent
    dm = np.abs(np.array(sidecar["moisture"])[0::2] - np.array(sidecar["moisture"])[1::2])
    assert (dm > 0.2).any()                                                  # some trials differ in moisture, as the terrain allows


def test_random_mode_is_reproducible_and_depends_on_the_seed():
    a = generate("one feature", mode="random", interlude_trial_count=10, seed=3)[0]
    b = generate("one feature", mode="random", interlude_trial_count=10, seed=3)[0]
    c = generate("one feature", mode="random", interlude_trial_count=10, seed=4)[0]
    assert a == b and a["trials"] != c["trials"]


def test_the_mode_comes_from_the_asset_unless_given_and_designed_is_retired():
    from interlude import interlude_mode
    from types import SimpleNamespace as NS
    assert interlude_mode(NS(interlude_mode=1)) == "random" and interlude_mode(NS(interlude_mode=4)) == "hybrid"
    assert interlude_mode(NS()) == "hybrid" and interlude_mode(NS(interlude_mode=1), "reward_gap") == "reward_gap"
    with pytest.raises(ValueError):
        interlude_mode(NS(interlude_mode=0))
    with pytest.raises(ValueError):
        interlude_mode(NS(), "shuffled")
    with pytest.raises(ValueError):
        interlude_mode(NS(), "designed")
    assert get("one feature")[0]["mode"] == "random"


# ---- gap modes: trials spread evenly over the reward gap, the feature gap or both ----

_GAP = {}


def get_gap(name, mode):
    if (name, mode) not in _GAP:
        _GAP[(name, mode)] = generate(name, mode=mode, interlude_trial_count=20, interlude_repeat_count=2)[0]
    return _GAP[(name, mode)]


def test_feature_gap_is_the_weighted_rms_of_the_channel_differences():
    from interlude import feature_gap
    a, b = {"shape": 0.2, "color": 0.5, "moisture": 0.9}, {"shape": 0.2, "color": 0.5, "moisture": 0.9}
    assert feature_gap(a, b) == 0.0
    assert abs(feature_gap({"shape": 0, "color": 0, "moisture": 0}, {"shape": 1, "color": 1, "moisture": 1}) - 1.0) < 1e-12
    assert abs(feature_gap({"shape": 0, "color": 0.5, "moisture": 0.5}, {"shape": 1, "color": 0.5, "moisture": 0.5}) - math.sqrt(1 / 3)) < 1e-12


@pytest.mark.slow
@pytest.mark.parametrize("name,mode", [("one feature", "reward_gap"), ("one feature", "feature_gap"), ("old S3", "hybrid")])
def test_gap_modes_spread_the_gaps_evenly(name, mode):
    sc = get_gap(name, mode)
    n = sc["n"]
    assert n == len(sc["trials"]) == 20 and sc["mode"] == mode
    assert sorted(t["correct"] for t in sc["trials"]) == ["left"] * (n // 2) + ["right"] * (n - n // 2)       # the better side is balanced
    repeats = sum("repeatOf" in t for t in sc["trials"])                                                        # (the asset's own repeat count)
    assert repeats == 2
    assert len({tuple(t["start"]) for t in sc["trials"]}) == n - repeats                                        # one trial per placement, a repeat on its source's
    own = [t for t in sc["trials"] if "repeatOf" not in t]                                                      # the distinct pairs carry the even spread
    for axis, key in (("reward", "rewardGap"), ("feature", "featureGap")):
        if axis not in sc["gapSpan"]:
            continue
        lo, hi = sc["gapSpan"][axis]
        got = np.sort([t[key] for t in own])
        want = lo + (np.arange(len(own)) + 0.5) / len(own) * (hi - lo)
        assert got.min() >= lo - 1e-9 and np.abs(got - want).max() < 0.1 * (hi - lo)                           # evenly spread from the minimum


@pytest.mark.slow
def test_gap_mode_stimuli_are_the_same_every_time():
    a, b = get_gap("one feature", "reward_gap"), generate("one feature", mode="reward_gap", interlude_trial_count=20, interlude_repeat_count=2)[0]
    assert a == b                                                                                              # a function of the world seed only


@pytest.mark.slow
def test_gap_mode_file_order_has_no_structure():
    t = get_gap("one feature", "reward_gap")["trials"]
    sides = "".join(x["correct"][0] for x in t)
    assert not any(len(set(sides[k:k + 4])) == 1 for k in range(len(sides) - 3))                  # no 4 in a row of one side
    assert "lrlr" not in sides and "rlrl" not in sides
    pos = np.arange(len(t))
    for key in ("rewardGap", "featureGap"):
        g = np.array([x[key] for x in t])
        assert abs(np.corrcoef(pos, g)[0, 1]) < 0.3 and abs(np.corrcoef(g[:-1], g[1:])[0, 1]) < 0.3


# ---- S5: the reward function has bumps over (shape, colour) ----

def test_bumps_make_shape_and_colour_relevant():
    params = load_session(ASSET, **CASES["old S5"])                                # (the old S5: a bump over shape and colour, plus moisture)
    features = session_features(params)
    assert all(d["rewarded"] and d["visible"] for d in features.values())          # moisture by its weight, shape and colour by the bumps


def test_gap_ceilings_keep_the_chosen_pairs_inside_the_window_and_spread_them_evenly():
    from interlude import choose_gap_trials
    rng = np.random.default_rng(0)
    rows = [(i, None, None, float(rng.uniform(0, 4)), float(rng.uniform(0, 1)), bool(i % 2)) for i in range(3000)]
    chosen, span = choose_gap_trials(rows, 10, (3, 4), {3: 0.5, 4: 0.2}, np.random.default_rng(1), {3: 2.0, 4: 0.7})
    reward, feature = np.array([r[3] for r in chosen]), np.array([r[4] for r in chosen])
    assert span == {3: (0.5, 2.0), 4: (0.2, 0.7)}
    assert reward.min() >= 0.5 and reward.max() <= 2.0 and feature.min() >= 0.2 and feature.max() <= 0.7
    assert np.abs(np.sort(reward) - (0.5 + (np.arange(10) + 0.5) / 10 * 1.5)).max() < 0.15           # one gap near each evenly spaced target
    _, open_span = choose_gap_trials(rows, 10, (3,), {3: 0.5}, np.random.default_rng(1))
    assert open_span[3][1] > 3.5                                                                      # no ceiling: up to the top quantile, as before


_REPEATS = {}


def test_a_gap_mode_interlude_can_repeat_pairs_exactly_with_their_own_bush_entries_and_apart_in_the_order():
    if "s" not in _REPEATS:
        scale = generate("old S3", mode="hybrid")[0]["scale"]
        extras = {"interlude_max_reward_gap": 1.5 * scale, "interlude_max_feature_gap": 0.55, "interlude_repeat_count": 2}
        _REPEATS["s"] = (generate("old S3", mode="hybrid", interlude_trial_count=20, interlude_min_reward_gap=0.25 * scale,
                                  interlude_min_feature_gap=0.15, extras=extras)[0], scale)
    sc, scale = _REPEATS["s"]
    trials, n = sc["trials"], sc["n"]
    assert n == len(trials) == 20 and len(sc["shape"]) == 40 and len(set(t["left"]["id"] for t in trials)) == 20      # a copy has bush entries of its own
    repeats = [t for t in trials if "repeatOf" in t]
    assert len(repeats) == 2 and sorted(t["correct"] for t in repeats) == ["left", "right"]                              # the correct sides stay balanced
    pos = np.array(sc["treePos"]).reshape(-1, 2)
    for t in repeats:
        o = trials[t["repeatOf"]]
        assert o["index"] < t["index"] and t["index"] - o["index"] >= 8                                                  # the later one names the earlier
        for side in ("left", "right"):
            a, b = t[side]["id"], o[side]["id"]
            assert a != b and np.allclose(pos[a], pos[b]) and sc["canopyRadius"][a] == sc["canopyRadius"][b]
            assert all(t[side][k] == o[side][k] for k in ("shape", "color", "moisture", "value"))
        assert t["start"] == o["start"] and t["yaw"] == o["yaw"] and t["correct"] == o["correct"]
    gaps = np.array([t["rewardGap"] for t in trials]) / scale
    assert gaps.min() >= 0.25 - 1e-9 and gaps.max() <= 1.5 + 1e-9 and max(t["featureGap"] for t in trials) <= 0.55 + 1e-9
    assert sum(t["correct"] == "left" for t in trials) == 10


# ---- per-feature trials (FN): a pair that differs in one visible feature only ----

def _three_linear_features():
    return synthetic.reward_function({"shape": 0.5, "color": 0.3, "moisture": 0.2}, {"color": 1})


_PF = {}


def get_per_feature(**extra):
    key = tuple(sorted(extra.items()))
    if key not in _PF:
        _PF[key] = generate_interlude(ASSET, mode="hybrid", reward_function=_three_linear_features(), shape_varies=True, color_varies=True, moisture_terrace_levels=0, random_bush_value_range=(0.0, 0.0), spatial_balance=0,
                                      interlude_trial_count=14, interlude_repeat_count=2, interlude_feature_trials=2, reward_std=0.6, **extra)[0]
    return _PF[key]


def test_per_feature_trials_differ_in_exactly_one_feature_by_a_gap_in_noise_units():
    sc = get_per_feature()
    typed = [t for t in sc["trials"] if t["type"] == "per_feature" and "repeatOf" not in t]
    assert sc["n"] == 14 and sorted(t["varied"] for t in typed) == ["color", "color", "moisture", "moisture", "shape", "shape"]
    for t in typed:
        diff = {f: abs(t["left"][f] - t["right"][f]) for f in FEATURES}
        others = [d for f, d in diff.items() if f != t["varied"]]
        assert max(others) <= 0.031 and diff[t["varied"]] > 0.1                       # the others are matched, the varied one is not
        assert 0.4 <= t["rewardGap"] / 0.6 <= 3.3 and t["correct"] in ("left", "right")
    for feature in ("shape", "color", "moisture"):
        gaps = sorted(t["rewardGap"] for t in typed if t["varied"] == feature)
        assert len(gaps) == 2 and gaps[1] > gaps[0]                                 # a small effect and a larger one for each feature


def test_per_feature_trials_cover_only_the_visible_features():
    sc = get_per_feature(moisture_varies=False)
    varied = {t["varied"] for t in sc["trials"] if t["type"] == "per_feature"}
    assert varied == {"shape", "color"} and set(sc["moisture"]) == {0.5}


def test_no_per_feature_trials_by_default_and_too_many_are_refused():
    assert all(t["type"] != "per_feature" for t in generate("one feature", mode="hybrid", interlude_trial_count=6, interlude_repeat_count=0)[0]["trials"])
    with pytest.raises(ValueError):
        generate_interlude(ASSET, mode="hybrid", reward_function=_three_linear_features(), shape_varies=True, color_varies=True, moisture_terrace_levels=0, random_bush_value_range=(0.0, 0.0), spatial_balance=0,
                             interlude_trial_count=6, interlude_repeat_count=0, interlude_feature_trials=2)
