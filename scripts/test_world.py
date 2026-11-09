from types import SimpleNamespace

import numpy as np
import pytest

from legacy_sessions import legacy
from world import PROJECT_ROOT, Perlin, Terrain, World, _basis, bush_value, check_values, generate_world, load_session, make_world


def test_deterministic_and_seed_dependent():
    a, b, c = make_world("S1", 3), make_world("S1", 3), make_world("S1", 4)
    assert np.array_equal(a.pos, b.pos) and np.array_equal(a.fruit_reward, b.fruit_reward)
    assert not (a.n == c.n and np.array_equal(a.pos, c.pos))


def test_lattice_rules():
    p = load_session("S1")
    for seed in range(5):
        w = generate_world(p, seed)
        d = np.hypot(*(w.pos[:, None] - w.pos[None]).transpose(2, 0, 1))
        np.fill_diagonal(d, np.inf)
        assert d.min() >= p.tree_spacing * (1 - p.placement_jitter) - 1e-9   # guaranteed by disc jitter
        assert np.hypot(*w.pos.T).min() >= p.start_clearing_radius
        assert np.abs(w.pos).max() <= p.world_half_extent - p.tree_edge_margin
        valley = (2 * (p.world_half_extent - p.mountain_band_width)) ** 2   # tree count scales with valley area
        assert 0.9 < w.n * 0.866 * p.tree_spacing ** 2 / valley < 1.5


def test_bush_ids_are_not_spatially_ordered():
    w = make_world("S1", 0)
    consecutive = np.hypot(*(w.pos[1:] - w.pos[:-1]).T).mean()
    random_pairs = np.hypot(*(w.pos - w.pos[np.random.default_rng(0).permutation(w.n)]).T).mean()
    assert consecutive > 0.8 * random_pairs
    assert abs(np.corrcoef(np.arange(w.n), w.pos[:, 0])[0, 1]) < 0.2


def test_overrides_change_density():
    assert make_world("S1", 1, tree_spacing=40).n < make_world("S1", 1).n * 0.5


def _weights(w):
    """The (shape, color, moisture) component dicts of the session's reward function, read from the SessionConfig asset like world.py does."""
    rf = w.params.reward_function
    return rf["shapeComponent"], rf["colorComponent"], rf["moistureComponent"]


def _expected(w):
    """The session's reward function evaluated on the world's bushes, term by term (the asset says which features and directions)."""
    shape, color, moisture = _weights(w)
    return _basis(shape, w.shape) + _basis(color, w.color) + _basis(moisture, w.moisture)


def _nonzero(w):
    return [c for c in _weights(w) if c["weight"] != 0]


def test_attributes_and_rewards():
    w = make_world("S1", 1)   # S1: one rewarded feature, linear (either direction)
    (rewarded,) = _nonzero(w)
    assert rewarded["basisFunctionType"] in (0, 1)
    assert np.allclose(w.value, _expected(w))
    assert ((0 <= w.moisture) & (w.moisture <= 1)).all()
    assert w.canopy_radius.min() >= 0.5 - 1e-9 and w.canopy_radius.max() <= 3 + 1e-9
    assert w.fruit_reward.min() >= 0 and w.fruit_reward.shape == (w.n, 10)
    assert abs(w.fruit_reward.mean() - w.value.mean()) < 0.1   # rounding and clipping at 0 barely bias the mean at the asset's reward_std


def test_s2_gaussian_component():
    w = make_world("S2", 1)
    (rewarded,) = _nonzero(w)                  # one rewarded feature, a Gaussian peak inside the range
    assert rewarded["basisFunctionType"] == 2 and 0.2 < rewarded["peak"] < 0.8
    assert np.allclose(w.value, _expected(w))


def test_s3_two_features_and_one_irrelevant():
    w = make_world("S2", 1, **legacy("S3"))                     # (the old S3: moisture and one other feature pay)
    assert len(_nonzero(w)) == 2 and _weights(w)[2]["weight"] != 0 and all(c["basisFunctionType"] in (0, 1) for c in _nonzero(w))
    assert np.allclose(w.value, _expected(w))


def test_s4_all_features_additive_with_one_inverted():
    w = make_world("S2", 1, **legacy("S4"))                     # (the old S4)
    assert len(_nonzero(w)) == 3 and sorted(c["basisFunctionType"] for c in _nonzero(w)) == [0, 0, 1]
    assert np.allclose(w.value, _expected(w))


def test_s5_one_gaussian_bump_over_shape_and_color_plus_linear_moisture():
    w = make_world("S2", 1, **legacy("S5"))                     # (the old S5)
    shape, color, moisture = _weights(w)
    bumps = w.params.reward_function["bumps"]
    assert shape["weight"] == 0 and color["weight"] == 0 and moisture["weight"] != 0 and moisture["basisFunctionType"] in (0, 1)
    assert len(bumps) == 1                                                                    # a single optimum (two bumps were too hard in the pilots)
    centres = np.array([[b["centerShape"], b["centerColor"]] for b in bumps])
    assert ((0.1 <= centres) & (centres <= 0.9)).all()
    expected = _basis(moisture, w.moisture)
    for b in bumps:
        expected = expected + b["height"] * np.exp(-((w.shape - b["centerShape"]) ** 2 + (w.color - b["centerColor"]) ** 2) / (2 * b["width"] ** 2))
    assert np.allclose(w.value, expected)
    assert 3.0 < w.value.max() < 4.4                                                          # the best bush pays about 4, as in the other sessions


def test_bush_value_adds_the_bumps_to_the_component_terms():
    rf = {"shapeComponent": {"basisFunctionType": 0, "weight": 0, "peak": 0, "width": 0}, "colorComponent": {"basisFunctionType": 0, "weight": 0, "peak": 0, "width": 0},
          "moistureComponent": {"basisFunctionType": 0, "weight": 1.0, "peak": 0, "width": 0},
          "bumps": [{"centerShape": 0.3, "centerColor": 0.6, "width": 0.2, "height": 2.0}]}
    assert abs(bush_value(rf, 0.3, 0.6, 0.5) - 2.5) < 1e-12                                   # at the centre: the height plus the moisture term
    d = 0.2
    assert abs(bush_value(rf, 0.3 + d, 0.6, 0.0) - 2.0 * np.exp(-0.5)) < 1e-12                # one width away along either axis: height * exp(-1/2)
    assert abs(bush_value(rf, 0.3, 0.6 - d, 0.0) - 2.0 * np.exp(-0.5)) < 1e-12


def test_noise_range_and_smoothness():
    f = Perlin(np.random.default_rng(0))
    g = np.linspace(0, 20, 400)
    X, Z = np.meshgrid(g, g)
    n = f(X, Z)
    assert 0 <= n.min() and n.max() <= 1 and 0.3 < n.mean() < 0.7
    assert np.abs(np.diff(n, axis=1)).max() < 0.1   # continuous


def test_save_load_roundtrip(tmp_path):
    w = make_world("S2", 5)
    w.save(tmp_path / "w.npz")
    r = World.load(tmp_path / "w.npz")
    assert r.seed == 5 and np.array_equal(r.pos, w.pos) and np.array_equal(r.fruit_reward, w.fruit_reward)
    assert r.params.tree_spacing == w.params.tree_spacing and r.params.reward_function == w.params.reward_function


def test_unity_export_roundtrip(tmp_path):
    from world import export_unity, read_unity_world
    w = make_world("S1", 1)
    export_unity(w, tmp_path / "w.world")
    h, g = read_unity_world(tmp_path / "w.world")
    res = int(w.params.terrain_mesh_resolution)
    assert h["treeCount"] == w.n and h["res"] == res and set(g) == {"moisture", "elevation", "rock", "snow", "ramp"}
    assert np.allclose(np.array(h["treePos"]).reshape(-1, 2), w.pos)
    assert np.array_equal(np.array(h["fruitRewards"]).reshape(w.n, -1), w.fruit_reward)
    assert dict(zip(h["checkNames"], h["checkValues"]))["treeSpacing"] == 23.0
    for a in g.values():
        assert a.shape == (res, res) and np.isfinite(a).all()


def test_terrain_grids_match_rules():
    w = make_world("S1", 1, moisture_terrace_levels=0)           # (continuous moisture: the grid then matches the bushes' moisture closely; terraces have sharp ramps)
    g = w.terrain.grids()
    half, res = w.params.world_half_extent, g["ramp"].shape[0]
    assert g["ramp"][res // 2, res // 2] == 0 and g["elevation"][res // 2, res // 2] < w.params.terrain_max_elevation + 1e-3
    assert g["ramp"][0, 0] == 1 and g["elevation"][0, 0] > 0.5 * w.params.mountain_height   # crest at the mesh edge
    assert (g["rock"][g["ramp"] == 0] == 0).all() and (g["snow"] <= g["rock"] + 1e-6).all()
    # bush moisture is the continuous field at the bush position, close to the grid there
    x = np.linspace(-half, half, res)
    i = np.abs(x[:, None] - w.pos[:, 0]).argmin(0)
    j = np.abs(x[:, None] - w.pos[:, 1]).argmin(0)
    assert np.abs(g["moisture"][i, j] - w.moisture).max() < 0.03


def test_terrace_off_when_the_levels_are_zero():
    # with no terrace levels moisture is the plain continuous field (every session of the ladder is terraced, with a relief of 6)
    p = load_session("S1", moisture_terrace_levels=0)
    assert int(load_session("S1").moisture_terrace_levels) == 4 and p.terrain_max_elevation <= 14
    t = Terrain.from_seed(p, 1)
    g = np.linspace(-100, 100, 50)
    x, z = np.meshgrid(g, g)
    assert np.array_equal(t.moisture(x, z), t._raw_moisture(x, z))


def test_terrace_levels_balanced_and_in_range():
    for name, seed in [("S3", 3), ("S4", 4)]:
        p = load_session("S2", **legacy(name))                  # (the old terraced sessions)
        n, amp = int(p.moisture_terrace_levels), p.moisture_terrace_residual
        assert n == 4
        w = generate_world(p, seed)
        assert 0 <= w.moisture.min() and w.moisture.max() <= 1
        lvl = np.clip(np.round((w.moisture - amp) / (1 - 2 * amp) * (n - 1)), 0, n - 1).astype(int)
        counts = np.bincount(lvl, minlength=n)
        assert counts.min() > 0.7 * counts.mean() and counts.max() < 1.3 * counts.mean()   # rank-normalised


def test_terrace_snaps_to_levels_when_sharp_and_no_residual():
    w = make_world("S2", 3, **{**legacy("S3"), "moisture_terrace_sharpness": 1.0, "moisture_terrace_residual": 0.0})
    levels = np.array([0, 1 / 3, 2 / 3, 1])
    nearest = np.abs(w.moisture[:, None] - levels[None]).min(axis=1)
    assert (nearest < 0.02).mean() > 0.9


def test_canopy_ranges_are_staleness_checked_and_mirrored_in_unity():
    # Unity recomputes the canopy radius from these ranges; the file stores the radius, so a changed range must make
    # the file stale. Every checked name must also be compared by WorldData.FindMismatches (a name Unity does not know
    # is always reported stale).
    params = load_session("S1")
    base = check_values(params)
    wide = SimpleNamespace(**{**vars(params), "canopy_width_range": (params.canopy_width_range[0], params.canopy_width_range[1] + 1)})
    shaped = SimpleNamespace(**{**vars(params), "shape_range": (0.0, params.shape_range[1] + 0.5)})
    assert check_values(wide) != base and check_values(shaped) != base
    src = (PROJECT_ROOT / "Assets" / "Scripts" / "World" / "WorldData.cs").read_text()
    for name in base:
        if not name.startswith("reward."):
            assert f'"{name}"' in src, name


def test_canopy_radius_runs_from_wide_for_squat_to_narrow_for_tall():
    # Tree.ApplyAttributes: width = lerp(widthRange.max, widthRange.min, shape), radius = width / 2 (S1: width 2..5).
    p = load_session("S1", shape_varies=True)             # (S1 of the new ladder has identical shapes)
    w = generate_world(p, 1)
    lo, hi = p.canopy_width_range
    assert np.corrcoef(w.shape, w.canopy_radius)[0, 1] < -0.999
    i, j = int(np.argmin(w.shape)), int(np.argmax(w.shape))
    assert abs(w.canopy_radius[i] - hi / 2) < 0.02 * (hi - lo) and abs(w.canopy_radius[j] - lo / 2) < 0.02 * (hi - lo)
    mid = int(np.argmin(np.abs(w.shape - 0.5)))
    assert abs(w.canopy_radius[mid] - (lo + hi) / 4) < 0.05


def test_exported_grids_hold_the_terrains_values_under_their_names(tmp_path):
    from world import export_unity, read_unity_world
    w = make_world("S1", 1)
    export_unity(w, tmp_path / "w.world")
    h, g = read_unity_world(tmp_path / "w.world")
    expected = w.terrain.grids()
    for name in expected:
        assert np.array_equal(g[name], expected[name]), name          # right values under the right name, not just shapes
    # elevation is the valley's moisture coupling (dry = high) plus the mountains: the game renders and the tools sample it
    res = expected["elevation"].shape[0]
    axis = np.linspace(-w.params.world_half_extent, w.params.world_half_extent, res)
    x, z = np.meshgrid(axis[::25], axis[::25], indexing="ij")
    assert np.allclose(w.terrain.elevation(x, z), expected["elevation"][::25, ::25], atol=1e-3)
    inside = expected["ramp"] == 0
    assert np.corrcoef(expected["moisture"][inside], expected["elevation"][inside])[0, 1] < -0.5
    assert (expected["snow"] < expected["rock"] - 1e-3).any() and expected["snow"].max() > 0


def test_checked_parameters_cover_the_world_shaping_ones():
    names = set(check_values(load_session("S3")))
    assert {"rewardStd", "fruitCount", "treeSpacing", "mountainHeight", "terrainMaxElevation",
            "canopyWidthRange.min", "shapeRange.max", "reward.shape.weight"} <= names


@pytest.mark.slow
def test_committed_world_files_are_fresh(tmp_path):
    """The generated .world files are what the game plays and what replay loads. Regenerating from the current
    SessionConfig assets must reproduce them exactly (this also pins the RNG streams and draw order); Unity warns at
    startup about stale parameters, but not about a changed generator."""
    from world import export_unity, unity_world_path
    for name in ("P", "S1", "S2", "S3", "S4", "S5", "S6", "S7"):
        p = load_session(name)
        seed = int(p.world_seed)
        committed = unity_world_path(name, seed)
        assert committed.exists(), f"{committed} is missing: run scripts/world.py {name} --unity"
        fresh = tmp_path / committed.name
        export_unity(generate_world(p, seed), fresh)
        assert fresh.read_bytes() == committed.read_bytes(), (
            f"{committed.name} is stale: re-run ./venv/bin/python scripts/world.py {name} --unity")


def test_bump_with_its_own_color_spread_and_product_terms_have_the_documented_formulas():
    rf = {"shapeComponent": {"basisFunctionType": 0, "weight": 0, "peak": 0, "width": 0}, "colorComponent": {"basisFunctionType": 0, "weight": 0, "peak": 0, "width": 0},
          "moistureComponent": {"basisFunctionType": 0, "weight": 0, "peak": 0, "width": 0}}
    x = np.array([0.0, 0.3, 0.7, 1.0])
    y = np.array([0.2, 0.7, 0.9, 0.0])
    round_bump = {**rf, "bumps": [{"centerShape": 0.3, "centerColor": 0.7, "width": 0.2, "height": 2.0}]}
    assert np.allclose(bush_value(round_bump, x, y, x), 2.0 * np.exp(-(((x - 0.3) ** 2 + (y - 0.7) ** 2) / (2 * 0.2 ** 2))))        # no widthColor: round
    flipped = {**rf, "products": [{"linearInShape": 0, "linearInverted": 1, "center": 0.4, "width": 0.3, "height": 1.0}]}
    assert np.allclose(bush_value(flipped, x, y, x), (1.0 - y) * np.exp(-((x - 0.4) ** 2) / (2 * 0.3 ** 2)))                         # linear in colour (inverted), Gaussian in shape


def test_new_reward_terms_agree_with_unity():
    """Values of RewardFunction.Evaluate in Unity (read through the editor on 2026-11-05) for the S6 product term and the S7 anisotropic bump."""
    zero = {"basisFunctionType": 0, "weight": 0, "peak": 0, "width": 0}
    base = {"shapeComponent": zero, "colorComponent": zero, "moistureComponent": zero}
    s6 = {**base, "products": [{"linearInShape": 1, "linearInverted": 0, "center": 0.6, "width": 0.25, "height": 4.0}]}
    s7 = {**base, "bumps": [{"centerShape": 0.30, "centerColor": 0.70, "width": 0.25, "widthColor": 0.15, "height": 4.0}]}
    points = [(0.2, 0.7), (0.9, 0.5), (0.3, 0.7), (0.6, 0.1)]
    for rf, expected in ((s6, [0.738493, 3.323219, 1.107740, 0.324805]), (s7, [3.692465, 0.092311, 4.000000, 0.000653])):
        assert np.allclose([float(bush_value(rf, a, b, 0.5)) for a, b in points], expected, atol=2e-6)


def test_a_session_defaults_to_the_lattice_independent_terms_stages_and_balances_when_asked():
    from world import ASSIGNMENTS, LAYOUTS, REWARDS, stage_names
    assert stage_names(load_session("S2", spatial_balance=0)) == ("lattice", "independent", "terms")
    assert stage_names(load_session("S2", spatial_balance=2))[1] == "balanced"
    assert stage_names(load_session("S2", assignment="independent", spatial_balance=2))[1] == "independent"     # a named stage wins
    assert {"lattice"} <= set(LAYOUTS) and {"independent", "balanced"} <= set(ASSIGNMENTS) and "terms" in REWARDS
