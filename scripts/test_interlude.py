import json

import numpy as np
import pytest

from interlude import (FEATURES, ONE_LEVEL, SAME_TOL, TIE_TOLERANCE, TWO_LEVELS_MIN, bush_position, canopy_radius,
                       check_geometry, generate_interlude, has_hump, sidecar_path, trial_mix, write_sidecar)
from interlude import CANOPY_AIM_HEIGHT, HUMP_TOLERANCE
from world import _basis, bush_value, check_values, generate_world, load_session

NAMES = ["P_Interlude", "S1_Interlude", "S2_Interlude", "S3_Interlude", "S4_Interlude"]

# Generating an Interlude searches half a million placements (a few seconds each), so each one is generated once per run.
_CACHE = {}


def get(name):
    """The designed-mode Interlude of an asset (whatever the asset's own interludeMode is; the designed-stimulus tests are about this)."""
    if name not in _CACHE:
        _CACHE[name] = generate_interlude(name, mode="designed")
    return _CACHE[name]


_ASSET = {}


def get_asset(name):
    """The Interlude as the asset itself says (its own interludeMode): what the game plays."""
    if name not in _ASSET:
        _ASSET[name] = generate_interlude(name)
    return _ASSET[name]


@pytest.fixture(scope="module", params=NAMES)
def built_asset(request):
    sidecar, params, terrain = get_asset(request.param)
    return request.param, sidecar, params, terrain


@pytest.fixture(scope="module", params=NAMES)
def built(request):
    sidecar, params, terrain = get(request.param)
    return request.param, sidecar, params, terrain


RANDOM_NAMES = ["S1_Interlude", "S3_Interlude"]
_RANDOM = {}


def get_random(name, seed=None):
    if (name, seed) not in _RANDOM:
        _RANDOM[(name, seed)] = generate_interlude(name, mode="random", interlude_trial_count=50, seed=seed)
    return _RANDOM[(name, seed)]


@pytest.fixture(scope="module", params=RANDOM_NAMES)
def built_random(request):
    sidecar, params, terrain = get_random(request.param)
    return request.param, sidecar, params, terrain


@pytest.fixture(scope="module", params=[(n, "designed") for n in NAMES] + [(n, "random") for n in RANDOM_NAMES])
def built_any(request):
    """Every kind of generated Interlude: the generic geometry, terrain and view checks hold for each."""
    name, mode = request.param
    sidecar, params, terrain = get(name) if mode == "designed" else get_random(name)
    return name, sidecar, params, terrain


@pytest.mark.slow
def test_deterministic():
    # a smaller search keeps this fast; the property (same inputs, same output) does not depend on its size
    a, *_ = generate_interlude("S3_Interlude", pool_samples=120_000, mode="designed")
    b, *_ = generate_interlude("S3_Interlude", pool_samples=120_000, mode="designed")
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
def test_committed_interlude_file_is_fresh(built_asset):
    """Unity does not warn when an *.interlude.json is stale. Regenerating from the current assets (the session's terrain,
    seed and reward function, and the Interlude's own geometry and trial count) must give the committed file."""
    name, sidecar, params, terrain = built_asset
    committed = sidecar_path(name, sidecar["seed"])
    assert committed.exists(), f"{committed} is missing: run scripts/interlude.py {name}"
    on_disk = json.load(open(committed))
    assert _same(on_disk, json.loads(json.dumps(sidecar))), (
        f"{committed.name} is stale: re-run ./venv/bin/python scripts/interlude.py {name}")


def test_interlude_assets_copy_the_session_they_probe(built):
    name, sidecar, params, terrain = built
    base = load_session(params.interlude_for)
    assert params.reward_function == base.reward_function
    assert int(params.world_seed) == int(base.world_seed) == sidecar["seed"]
    assert check_values(params) == check_values(base)           # every terrain parameter is a copy


def test_trial_counts_and_mix(built):
    name, sidecar, params, terrain = built
    n = int(params.interlude_trial_count)
    assert sidecar["n"] == n == len(sidecar["trials"]) and len(sidecar["shape"]) == 2 * n
    kinds = [t["type"] for t in sidecar["trials"]]
    if bool(params.is_practice):
        assert n == 3 and "extrapolation" not in kinds and kinds.count("graded") == 1
    else:
        assert n == 5 and kinds.count("contrast") == 2


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


def test_contrasts_differ_in_exactly_one_feature(built):
    name, sidecar, params, terrain = built
    for t in sidecar["trials"]:
        if t["type"] != "contrast":
            continue
        diff = [f for f in FEATURES if abs(t["left"][f] - t["right"][f]) > SAME_TOL + 1e-9]
        assert diff == [t["varied"]]


def test_contrasts_cover_relevant_features_and_one_irrelevant():
    for name in ["S1_Interlude", "S3_Interlude", "S4_Interlude"]:
        sidecar, params, _ = get(name)
        rf = params.reward_function
        relevant = {f for f in FEATURES if rf[f + "Component"]["weight"] != 0}
        varied = [t["varied"] for t in sidecar["trials"] if t["type"] == "contrast"]
        # With fewer contrasts than relevant features (5 trials in S4: 2 contrasts for 3 features) coverage is partial.
        if len(varied) >= len(relevant):
            assert relevant <= set(varied)
        else:
            assert set(varied) <= relevant
        if relevant != set(FEATURES) and len(varied) > len(relevant):
            assert set(varied) - relevant        # an ignored-feature check


def test_moisture_contrasts_use_the_largest_available_difference():
    for name in ["S3_Interlude", "S4_Interlude"]:
        sidecar, params, _ = get(name)
        mc = [t for t in sidecar["trials"] if t["varied"] == "moisture"]
        assert len(mc) <= 1
        if not mc:        # S4 at 5 trials: the contrasts go to shape and color
            continue
        assert abs(mc[0]["left"]["moisture"] - mc[0]["right"]["moisture"]) >= TWO_LEVELS_MIN
        assert abs(mc[0]["deltaValue"]) > 0.3                           # a clear true-reward difference


def test_extrapolation_pairs_are_tradeoffs_when_several_features_matter():
    for name in ["S3_Interlude", "S4_Interlude"]:
        sidecar, params, _ = get(name)
        rf = params.reward_function
        extras = [t for t in sidecar["trials"] if t["type"] == "extrapolation"]
        assert len(extras) == trial_mix(len(sidecar["trials"]), False, 3)["extrapolation"]
        for t in extras:
            assert abs(t["deltaValue"]) >= 0.25            # clear difference
            ca = {f: float(_basis(rf[f + "Component"], t["left"][f])) for f in FEATURES}
            cb = {f: float(_basis(rf[f + "Component"], t["right"][f])) for f in FEATURES}
            assert any(ca[f] > cb[f] + 1e-9 for f in FEATURES) and any(cb[f] > ca[f] + 1e-9 for f in FEATURES)
            assert abs(t["left"]["moisture"] - t["right"]["moisture"]) >= ONE_LEVEL[0]


def test_non_moisture_contrasts_have_matching_moisture(built):
    name, sidecar, params, terrain = built
    for t in sidecar["trials"]:
        if t["type"] == "contrast" and t["varied"] != "moisture":
            assert abs(t["left"]["moisture"] - t["right"]["moisture"]) <= SAME_TOL + 1e-9


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
    sidecar = get("S3_Interlude")[0]
    path = write_sidecar(sidecar, "S3_Interlude", tmp_path)
    assert path == sidecar_path("S3_Interlude", 3, tmp_path)
    assert path.name == "S3_Interlude_seed3.interlude.json"
    assert list(tmp_path.glob("*.world")) == []                      # the terrain is the session's own world file
    assert json.load(open(path))["n"] == 5
    assert path.stat().st_size < 50_000


def test_trial_mix_rules():
    assert trial_mix(3, True) == {"contrast": 2, "graded": 1, "extrapolation": 0}
    assert trial_mix(10, False) == {"contrast": 3, "graded": 4, "extrapolation": 3}
    assert trial_mix(10, False, n_relevant=1) == {"contrast": 3, "graded": 6, "extrapolation": 1}
    assert trial_mix(5, False) == {"contrast": 2, "graded": 1, "extrapolation": 2}
    assert trial_mix(5, False, n_relevant=1) == {"contrast": 2, "graded": 2, "extrapolation": 1}


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
    a = generate_interlude("S1_Interlude", mode="random", interlude_trial_count=10, seed=3)[0]
    b = generate_interlude("S1_Interlude", mode="random", interlude_trial_count=10, seed=3)[0]
    c = generate_interlude("S1_Interlude", mode="random", interlude_trial_count=10, seed=4)[0]
    assert a == b and a["trials"] != c["trials"]


def test_the_mode_comes_from_the_asset_unless_given_and_designed_files_carry_no_mode_key():
    from interlude import interlude_mode
    from types import SimpleNamespace as NS
    assert interlude_mode(NS(interlude_mode=1)) == "random" and interlude_mode(NS(interlude_mode=0)) == "designed"
    assert interlude_mode(NS()) == "designed" and interlude_mode(NS(interlude_mode=1), "designed") == "designed"
    with pytest.raises(ValueError):
        interlude_mode(NS(), "shuffled")
    designed = get("S1_Interlude")[0]
    assert "mode" not in designed and {t["type"] for t in designed["trials"]} <= {"contrast", "graded", "extrapolation"}


def test_random_mode_elevation_floor_applies_only_where_the_asset_sets_it():
    for name in ("S3_Interlude", "S4_Interlude"):
        sidecar, params, terrain = get_random(name) if name in RANDOM_NAMES else generate_interlude(name, mode="random", interlude_trial_count=50)
        assert params.interlude_min_elevation_difference == 3.0
        m = np.array(sidecar["moisture"])
        assert (np.abs(m[0::2] - m[1::2]) * params.terrain_max_elevation >= 3.0).all()
    sidecar, params, _ = get_random("S1_Interlude")
    m = np.array(sidecar["moisture"])
    assert getattr(params, "interlude_min_elevation_difference", 0.0) == 0.0
    assert (np.abs(m[0::2] - m[1::2]) * params.terrain_max_elevation < 3.0).any()       # without a floor, level pairs occur
