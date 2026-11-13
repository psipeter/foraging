from types import SimpleNamespace

import numpy as np
import pytest

import synthetic
from world import FEATURES, PROJECT_ROOT, Perlin, World, _basis, bush_value, check_values, generate_world, load_session

DEFAULT = dict(visible=FEATURES, weights={"shape": 0.5, "color": 0.3, "moisture": 0.2}, direction={"color": 1})      # what the generic world tests build


def make(seed=1, **extra):
    """A world of the default configuration (all three features visible and paying, one inverted); `extra` are load_session overrides or configuration keys."""
    return generate_world(synthetic.session(**{**DEFAULT, **extra}), seed)


def test_deterministic_and_seed_dependent():
    a, b, c = make(3), make(3), make(4)
    assert np.array_equal(a.pos, b.pos) and np.array_equal(a.fruit_reward, b.fruit_reward)
    assert not (a.n == c.n and np.array_equal(a.pos, c.pos))


def test_bush_ids_are_not_spatially_ordered():
    w = make(0)
    consecutive = np.hypot(*(w.pos[1:] - w.pos[:-1]).T).mean()
    random_pairs = np.hypot(*(w.pos - w.pos[np.random.default_rng(0).permutation(w.n)]).T).mean()
    assert consecutive > 0.8 * random_pairs
    assert abs(np.corrcoef(np.arange(w.n), w.pos[:, 0])[0, 1]) < 0.2


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
    w = make(1)
    g = w.terrain.grids()
    half, res = w.params.world_half_extent, g["ramp"].shape[0]
    assert g["ramp"][res // 2, res // 2] == 0 and g["elevation"][res // 2, res // 2] < w.params.terrain_max_elevation + 1e-3
    assert g["ramp"][0, 0] == 1 and g["elevation"][0, 0] > 0.5 * w.params.mountain_height   # crest at the mesh edge
    assert (g["rock"][g["ramp"] == 0] == 0).all() and (g["snow"] <= g["rock"] + 1e-6).all()
    # a bush's moisture is its tile's level (bushes stand in the middle of a tile, off the ramps), close to the grid there
    x = np.linspace(-half, half, res)
    i = np.abs(x[:, None] - w.pos[:, 0]).argmin(0)
    j = np.abs(x[:, None] - w.pos[:, 1]).argmin(0)
    assert np.abs(g["moisture"][i, j] - w.moisture).max() < 0.03


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
    from world import GRID_BITS
    for name in expected:                                             # right values under the right name, not just shapes, to within the file's quantization step
        step = np.ptp(expected[name]) / ((1 << GRID_BITS[name]) - 1)
        assert np.abs(g[name] - expected[name]).max() <= 0.5 * step * 1.001 + 2e-5, name           # plus float32 rounding of the decoded values
    # elevation is the valley's moisture coupling (dry = high) plus the mountains: the game renders and the tools sample it
    res = expected["elevation"].shape[0]
    axis = np.linspace(-w.params.world_half_extent, w.params.world_half_extent, res)
    x, z = np.meshgrid(axis[::25], axis[::25], indexing="ij")
    assert np.allclose(w.terrain.elevation(x, z), expected["elevation"][::25, ::25], atol=1e-3)
    assert (tmp_path / "w.world").stat().st_size < 0.35 * 5 * res * res * 4              # the grids are stored quantized and compressed (version 1 was 4 bytes each)
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
    from world import export_unity, read_unity_world, unity_world_path
    from world import EXPERIMENTS_DIR
    for path in sorted(EXPERIMENTS_DIR.glob("*/*_S*.asset")):                 # every session of every experiment
        name = path.stem
        p = load_session(name)
        seed = int(p.world_seed)
        committed = unity_world_path(name, seed)
        assert committed.exists(), f"{committed} is missing: run scripts/world.py {name} --unity"
        fresh = tmp_path / committed.name
        export_unity(generate_world(p, seed), fresh)
        (h_new, g_new), (h_old, g_old) = read_unity_world(fresh), read_unity_world(committed)          # the content, not the bytes: they depend on the zlib that compressed them
        assert h_new == h_old and all(np.array_equal(g_new[k], g_old[k]) for k in g_old), (
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


def test_a_session_defaults_to_the_tiles_and_terms_stages():
    from world import ASSIGNMENTS, LAYOUTS, REWARDS, stage_names
    assert stage_names(synthetic.session(**DEFAULT)) == ("tiles", "tiles", "terms")
    assert set(LAYOUTS) == set(ASSIGNMENTS) == {"tiles"} and "terms" in REWARDS


def test_a_terrace_mode_set_on_a_session_is_still_echoed_into_the_world_check():
    """The generators no longer read the terrace fields, but a session asset that sets one still writes it into its world file's header (the game compares it)."""
    assert "moistureTerraceMode" not in check_values(synthetic.session(**DEFAULT, moisture_terrace_mode=0))
    v = check_values(synthetic.session(**DEFAULT, moisture_terrace_mode=2))
    assert v["moistureTerraceMode"] == 2 and {"terraceMeanWidth", "terracePhaseShift", "terraceStrength", "terraceDiffusionIterations", "terraceDiffusionEdge"} <= set(v)


# ---- the staircase and diffusion terrace modes (no level count) ----

def test_a_version_1_world_file_still_reads(tmp_path):
    """The raw-float32 layout of version 1 (before the grids were quantized) stays readable."""
    import json
    import struct
    from world import WORLD_MAGIC, GRID_NAMES, read_unity_world
    header = {"version": 1, "res": 3, "grids": GRID_NAMES}
    blob = json.dumps(header).encode()
    grid = np.arange(9, dtype="<f4").reshape(3, 3)
    (tmp_path / "old.world").write_bytes(WORLD_MAGIC + struct.pack("<II", 1, len(blob)) + blob + b"".join(grid.tobytes() for _ in GRID_NAMES))
    h, g = read_unity_world(tmp_path / "old.world")
    assert set(g) == set(GRID_NAMES) and np.array_equal(g["snow"], grid)


def test_a_constant_grid_survives_quantization():
    from world import dequantize_grid, quantize_grid
    codes, lo, hi = quantize_grid(np.full((4, 4), 0.37), 16)
    assert np.allclose(dequantize_grid(codes, 16, lo, hi), 0.37)
