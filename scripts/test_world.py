import numpy as np

from world import Perlin, Terrain, World, generate_world, load_session, make_world


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


def test_overrides_change_density():
    assert make_world("S1", 1, tree_spacing=40).n < make_world("S1", 1).n * 0.5


def test_attributes_and_rewards():
    w = make_world("S1", 1)   # S1: value = 3 * color
    assert np.allclose(w.value, 3 * w.color)
    assert ((0 <= w.moisture) & (w.moisture <= 1)).all()
    assert w.canopy_radius.min() >= 0.5 - 1e-9 and w.canopy_radius.max() <= 3 + 1e-9
    assert w.fruit_reward.min() >= 0 and w.fruit_reward.shape == (w.n, 10)
    assert abs(w.fruit_reward.mean() - w.value.mean()) < 0.1   # rounding + clipping at 0 barely bias a 0.3 sd


def test_s2_gaussian_shape_component():
    w = make_world("S2", 1)
    # shape peak 0.65, width 0.2, weight 3; color and moisture irrelevant
    i = np.argmin(np.abs(w.shape - 0.65))
    assert abs(w.value[i] - 3 * np.exp(-((w.shape[i] - 0.65) ** 2) / (2 * 0.2 ** 2))) < 1e-9


def test_s4_all_features_additive():
    w = make_world("S4", 1)   # inverted-linear shape w2, linear color w3, linear moisture w1.5
    assert np.allclose(w.value, 2 * (1 - w.shape) + 3 * w.color + 1.5 * w.moisture)


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
    w = make_world("S1", 1)
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


def test_terrace_off_for_early_sessions():
    # S1 has no terracing: moisture is the plain continuous field and the valley has little relief (elev 12)
    p = load_session("S1")
    assert int(p.moisture_terrace_levels) == 0 and p.terrain_max_elevation <= 14
    t = Terrain.from_seed(p, 1)
    g = np.linspace(-100, 100, 50)
    x, z = np.meshgrid(g, g)
    assert np.array_equal(t.moisture(x, z), t._raw_moisture(x, z))


def test_terrace_levels_balanced_and_in_range():
    for name, seed in [("S3", 3), ("S4", 4)]:
        p = load_session(name)
        n, amp = int(p.moisture_terrace_levels), p.moisture_terrace_residual
        assert n == 4
        w = generate_world(p, seed)
        assert 0 <= w.moisture.min() and w.moisture.max() <= 1
        lvl = np.clip(np.round((w.moisture - amp) / (1 - 2 * amp) * (n - 1)), 0, n - 1).astype(int)
        counts = np.bincount(lvl, minlength=n)
        assert counts.min() > 0.7 * counts.mean() and counts.max() < 1.3 * counts.mean()   # rank-normalised


def test_terrace_snaps_to_levels_when_sharp_and_no_residual():
    w = make_world("S3", 3, moisture_terrace_sharpness=1.0, moisture_terrace_residual=0.0)
    levels = np.array([0, 1 / 3, 2 / 3, 1])
    nearest = np.abs(w.moisture[:, None] - levels[None]).min(axis=1)
    assert (nearest < 0.02).mean() > 0.9
