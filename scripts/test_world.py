from types import SimpleNamespace

import numpy as np
import pytest

import synthetic
from legacy_sessions import legacy
from world import FEATURES, PROJECT_ROOT, Perlin, Terrain, World, _basis, bush_value, check_values, generate_world, load_session

DEFAULT = dict(visible=FEATURES, weights={"shape": 0.5, "color": 0.3, "moisture": 0.2}, direction={"color": 1})      # what the generic world tests build


def make(seed=1, **extra):
    """A world of the default configuration (all three features visible and paying, one inverted); `extra` are load_session overrides or configuration keys."""
    return generate_world(synthetic.session(**{**DEFAULT, **extra}), seed)


def make_old(name, seed=1, **extra):
    """A world of an old terraced or bump session (legacy_sessions.py: the archived assets), built on the template."""
    return generate_world(load_session(synthetic.TEMPLATE, **{**legacy(name), **extra}), seed)


def test_deterministic_and_seed_dependent():
    a, b, c = make(3), make(3), make(4)
    assert np.array_equal(a.pos, b.pos) and np.array_equal(a.fruit_reward, b.fruit_reward)
    assert not (a.n == c.n and np.array_equal(a.pos, c.pos))


def test_lattice_rules():
    p = synthetic.session(**DEFAULT)
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
    w = make(0)
    consecutive = np.hypot(*(w.pos[1:] - w.pos[:-1]).T).mean()
    random_pairs = np.hypot(*(w.pos - w.pos[np.random.default_rng(0).permutation(w.n)]).T).mean()
    assert consecutive > 0.8 * random_pairs
    assert abs(np.corrcoef(np.arange(w.n), w.pos[:, 0])[0, 1]) < 0.2


def test_overrides_change_density():
    assert make(1, tree_spacing=40).n < make(1).n * 0.5


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
    w = make(1, weights={"color": 1.0}, direction={"color": 1})                  # one rewarded feature, linear
    (rewarded,) = _nonzero(w)
    assert rewarded["basisFunctionType"] in (0, 1)
    assert np.allclose(w.value, _expected(w))
    assert ((0 <= w.moisture) & (w.moisture <= 1)).all()
    lo, hi = w.params.canopy_width_range
    assert w.canopy_radius.min() >= lo / 2 - 1e-9 and w.canopy_radius.max() <= hi / 2 + 1e-9
    assert w.fruit_reward.min() >= 0 and w.fruit_reward.shape == (w.n, int(w.params.fruit_count))
    assert abs(w.fruit_reward.mean() - w.value.mean()) < 0.1   # rounding and clipping at 0 barely bias the mean at the reward_std


def test_a_gaussian_component_peaks_where_it_is_told_to():
    rf = synthetic.reward_function({"shape": 1.0})
    rf["shapeComponent"] = {"basisFunctionType": 2, "weight": 4.0, "peak": 0.4, "width": 0.2}
    w = make(1, reward_function=rf)
    (rewarded,) = _nonzero(w)                  # one rewarded feature, a Gaussian peak inside the range
    assert rewarded["basisFunctionType"] == 2 and 0.2 < rewarded["peak"] < 0.8
    assert np.allclose(w.value, _expected(w))
    assert abs(w.shape[np.argmax(w.value)] - 0.4) < 0.05


def test_s3_two_features_and_one_irrelevant():
    w = make_old("S3")                                           # (the old S3: moisture and one other feature pay)
    assert len(_nonzero(w)) == 2 and _weights(w)[2]["weight"] != 0 and all(c["basisFunctionType"] in (0, 1) for c in _nonzero(w))
    assert np.allclose(w.value, _expected(w))


def test_s4_all_features_additive_with_one_inverted():
    w = make_old("S4")                                           # (the old S4)
    assert len(_nonzero(w)) == 3 and sorted(c["basisFunctionType"] for c in _nonzero(w)) == [0, 0, 1]
    assert np.allclose(w.value, _expected(w))


def test_s5_one_gaussian_bump_over_shape_and_color_plus_linear_moisture():
    w = make_old("S5")                                           # (the old S5)
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
    w = make(5)
    w.save(tmp_path / "w.npz")
    r = World.load(tmp_path / "w.npz")
    assert r.seed == 5 and np.array_equal(r.pos, w.pos) and np.array_equal(r.fruit_reward, w.fruit_reward)
    assert r.params.tree_spacing == w.params.tree_spacing and r.params.reward_function == w.params.reward_function


def test_unity_export_roundtrip(tmp_path):
    from world import export_unity, read_unity_world
    w = make(1)
    export_unity(w, tmp_path / "w.world")
    h, g = read_unity_world(tmp_path / "w.world")
    res = int(w.params.terrain_mesh_resolution)
    assert h["treeCount"] == w.n and h["res"] == res and set(g) == {"moisture", "elevation", "rock", "snow", "ramp"}
    assert np.allclose(np.array(h["treePos"]).reshape(-1, 2), w.pos)
    assert np.array_equal(np.array(h["fruitRewards"]).reshape(w.n, -1), w.fruit_reward)
    assert dict(zip(h["checkNames"], h["checkValues"]))["treeSpacing"] == float(w.params.tree_spacing)
    for a in g.values():
        assert a.shape == (res, res) and np.isfinite(a).all()


def test_terrain_grids_match_rules():
    w = make(1, moisture_terrace_levels=0)                       # (continuous moisture: the grid then matches the bushes' moisture closely; terraces have sharp ramps)
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
    # with no terrace levels moisture is the plain continuous field; with levels it is snapped to them
    g = np.linspace(-100, 100, 50)
    x, z = np.meshgrid(g, g)
    flat = Terrain.from_seed(synthetic.session(**DEFAULT, moisture_terrace_levels=0), 1)
    assert np.array_equal(flat.moisture(x, z), flat._raw_moisture(x, z))
    terraced = Terrain.from_seed(synthetic.session(**DEFAULT, moisture_terrace_levels=4), 1)
    assert not np.array_equal(terraced.moisture(x, z), terraced._raw_moisture(x, z))


def test_terrace_levels_balanced_and_in_range():
    for name, seed in [("S3", 3), ("S4", 4)]:
        p = load_session(synthetic.TEMPLATE, **legacy(name))    # (the old terraced sessions)
        n, amp = int(p.moisture_terrace_levels), p.moisture_terrace_residual
        assert n == 4
        w = generate_world(p, seed)
        assert 0 <= w.moisture.min() and w.moisture.max() <= 1
        lvl = np.clip(np.round((w.moisture - amp) / (1 - 2 * amp) * (n - 1)), 0, n - 1).astype(int)
        counts = np.bincount(lvl, minlength=n)
        assert counts.min() > 0.7 * counts.mean() and counts.max() < 1.3 * counts.mean()   # rank-normalised


def test_terrace_snaps_to_levels_when_sharp_and_no_residual():
    w = make_old("S3", 3, moisture_terrace_sharpness=1.0, moisture_terrace_residual=0.0)
    levels = np.array([0, 1 / 3, 2 / 3, 1])
    nearest = np.abs(w.moisture[:, None] - levels[None]).min(axis=1)
    assert (nearest < 0.02).mean() > 0.9


def test_canopy_ranges_are_staleness_checked_and_mirrored_in_unity():
    # Unity recomputes the canopy radius from these ranges; the file stores the radius, so a changed range must make
    # the file stale. Every checked name must also be compared by WorldData.FindMismatches (a name Unity does not know
    # is always reported stale).
    params = synthetic.session(**DEFAULT)
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
    p = synthetic.session(**DEFAULT)
    w = generate_world(p, 1)
    lo, hi = p.canopy_width_range
    assert np.corrcoef(w.shape, w.canopy_radius)[0, 1] < -0.999
    i, j = int(np.argmin(w.shape)), int(np.argmax(w.shape))
    assert abs(w.canopy_radius[i] - hi / 2) < 0.02 * (hi - lo) and abs(w.canopy_radius[j] - lo / 2) < 0.02 * (hi - lo)
    mid = int(np.argmin(np.abs(w.shape - 0.5)))
    assert abs(w.canopy_radius[mid] - (lo + hi) / 4) < 0.05


def test_exported_grids_hold_the_terrains_values_under_their_names(tmp_path):
    from world import export_unity, read_unity_world
    w = make(1)
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
    names = set(check_values(synthetic.session(**DEFAULT)))
    assert {"rewardStd", "fruitCount", "treeSpacing", "mountainHeight", "terrainMaxElevation",
            "canopyWidthRange.min", "shapeRange.max", "reward.shape.weight"} <= names


@pytest.mark.slow
def test_committed_world_files_are_fresh(tmp_path):
    """The generated .world files are what the game plays and what replay loads. Regenerating from the current
    SessionConfig assets must reproduce them exactly (this also pins the RNG streams and draw order); Unity warns at
    startup about stale parameters, but not about a changed generator."""
    from world import export_unity, unity_world_path
    from world import EXPERIMENTS_DIR
    for path in sorted(EXPERIMENTS_DIR.glob("*/*_S*.asset")):                 # every session of every experiment
        name = path.stem
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
    assert stage_names(synthetic.session(**DEFAULT, spatial_balance=0)) == ("lattice", "independent", "terms")
    assert stage_names(synthetic.session(**DEFAULT, spatial_balance=2))[1] == "balanced"
    assert stage_names(synthetic.session(**DEFAULT, assignment="independent", spatial_balance=2))[1] == "independent"     # a named stage wins
    assert {"lattice"} <= set(LAYOUTS) and {"independent", "balanced"} <= set(ASSIGNMENTS) and "terms" in REWARDS


def test_uneven_terrace_levels_keep_their_regions_and_the_order_but_not_the_spacing():
    kw = dict(moisture_terrace_levels=6, moisture_terrace_sharpness=1.0, moisture_terrace_residual=0.0, spatial_balance=0)
    even = make(3, **kw)
    uneven = make(3, moisture_terrace_unevenness=1.0, **kw)
    other = make(4, moisture_terrace_unevenness=1.0, **kw)
    assert np.array_equal(even.pos, uneven.pos)                                                     # the same bushes: only the ground's values changed
    levels = generate_world(synthetic.session(**DEFAULT, **kw, moisture_terrace_unevenness=1.0), 3).terrain.terrace_levels()
    assert len(levels) == 6 and levels[0] == 0.0 and levels[-1] == 1.0 and (np.diff(levels) > 0).all()   # in order, the whole range
    assert not np.allclose(np.diff(levels), 0.2)                                                    # not evenly spaced
    near = np.abs(uneven.moisture[:, None] - levels[None]).min(axis=1)
    assert (near < 0.02).mean() > 0.9                                                               # still plateaus: most bushes stand on one of the six values
    assert not np.allclose(generate_world(synthetic.session(**DEFAULT, **kw, moisture_terrace_unevenness=1.0), 4).terrain.terrace_levels(), levels)   # each seed has its own
    half = generate_world(synthetic.session(**DEFAULT, **kw, moisture_terrace_unevenness=0.5), 3).terrain.terrace_levels()
    assert np.allclose(half, 0.5 * np.linspace(0, 1, 6) + 0.5 * levels)                             # a mix of the even and the random levels
    assert check_values(synthetic.session(**DEFAULT, **kw, moisture_terrace_unevenness=0.5))["moistureTerraceUnevenness"] == 0.5
    assert "moistureTerraceUnevenness" not in check_values(synthetic.session(**DEFAULT, **kw))       # (older world files stay identical)


# ---- the staircase and diffusion terrace modes (no level count) ----

def _ground(seed, mode, **extra):
    return generate_world(synthetic.session(**DEFAULT, moisture_terrace_mode=mode, terrain_noise_frequency=0.8, moisture_terrace_sharpness=0.7, moisture_terrace_residual=0.0,
                                            spatial_balance=0, **extra), seed)


def test_the_new_terrace_modes_leave_the_default_mode_and_the_bushes_alone():
    smooth = _ground(3, 0)
    for mode in (1, 2):
        w = _ground(3, mode)
        assert np.array_equal(w.pos, smooth.pos) and np.array_equal(w.shape, smooth.shape)          # the same bushes: only the ground changed
        assert 0.0 <= w.moisture.min() and w.moisture.max() <= 1.0
    assert "moistureTerraceMode" not in check_values(synthetic.session(**DEFAULT))                  # (older world files stay identical)


def _flat_share(terrain, reference):
    """The share of the valley (a grid) whose moisture gradient is below 12% of the median gradient of `reference`'s field: its flat ground."""
    g = np.linspace(-300, 300, 129)
    gx, gz = np.meshgrid(g, g, indexing="ij")
    ref = np.median(np.hypot(*np.gradient(reference._rank(reference._raw_moisture(gx, gz)))))
    return float(np.mean(np.hypot(*np.gradient(terrain.moisture(gx, gz))) < 0.12 * ref))


def test_the_staircase_makes_plateaus_whose_number_nobody_set():
    counts = []
    for seed in (1, 2, 3, 4, 5, 6):
        centres, values = _ground(seed, 1).terrain.staircase_levels()
        counts.append(len(values))
        assert values[0] == 0.0 and values[-1] == 1.0 and (np.diff(values) >= 0.08 - 1e-9).all()           # the whole range, in order, no step below the minimum
        assert (np.diff(centres) > 0).all() and centres[0] > 0.0 and centres[-1] < 1.0
    assert len(set(counts)) > 1 and min(counts) >= 3                                                # the count comes out of the draw, different for each seed


def test_the_staircase_has_flat_ground_and_the_strength_mixes_it_with_the_smooth_field():
    smooth_world = _ground(2, 0)
    stepped, none, half = _ground(2, 1), _ground(2, 1, terrace_strength=0.0), _ground(2, 1, terrace_strength=0.5)
    ref = smooth_world.terrain
    pos = stepped.pos
    assert np.allclose(none.moisture, ref._rank(ref._raw_moisture(pos[:, 0], pos[:, 1])))             # strength 0: the smooth rank field, no terracing
    assert np.allclose(half.moisture, 0.5 * stepped.moisture + 0.5 * none.moisture, atol=1e-9)
    assert _flat_share(stepped.terrain, ref) > _flat_share(ref, ref) + 0.15                            # plateaus: a good share of the ground is flat


def test_a_larger_mean_width_gives_fewer_plateaus_and_a_larger_minimum_step_merges_them():
    plateaus = lambda **kw: np.mean([len(_ground(s, 1, **kw).terrain.staircase_levels()[1]) for s in range(1, 9)])
    assert plateaus(terrace_mean_width=0.30) < plateaus(terrace_mean_width=0.07)
    assert max(len(_ground(s, 1, terrace_min_step=0.25).terrain.staircase_levels()[1]) for s in range(1, 9)) <= 5      # steps of at least 0.25 leave at most 5 plateaus


def test_diffusion_flattens_regions_and_a_lower_edge_quantile_keeps_more_of_them():
    from world import edge_preserving_diffusion
    smooth = _ground(4, 0).terrain
    g = np.linspace(-300, 300, 129)
    gx, gz = np.meshgrid(g, g, indexing="ij")
    t = smooth._rank(smooth._raw_moisture(gx, gz))
    flat = lambda u: np.mean(np.hypot(*np.gradient(u)) < 0.12 * np.median(np.hypot(*np.gradient(t))))
    soft = edge_preserving_diffusion(t, 400, 0.5)
    assert flat(soft) > flat(t) + 0.05 and soft.min() >= t.min() - 1e-9 and soft.max() <= t.max() + 1e-9      # smoothing does not leave the range
    assert np.allclose(edge_preserving_diffusion(t, 0, 0.5), t)                                       # no iterations, no change
    w = _ground(4, 2)
    assert w.terrain.moisture(np.array([-1000.0]), np.array([0.0])).size == 1                          # outside the valley it reads the edge
    assert w.moisture.std() > 0.2 and abs(_ground(4, 2).moisture - w.moisture).max() == 0.0            # deterministic, and it uses the range


def test_the_new_modes_write_their_mode_and_parameters_into_the_world_check():
    for mode in (1, 2):
        v = check_values(synthetic.session(**DEFAULT, moisture_terrace_mode=mode))
        assert v["moistureTerraceMode"] == mode and {"terraceMeanWidth", "terracePhaseShift", "terraceStrength", "terraceDiffusionIterations", "terraceDiffusionEdge"} <= set(v)
