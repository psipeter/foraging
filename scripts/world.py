"""World generation for the foraging task, in Python.

A world is fully determined by (session parameters, world seed). Parameters are read from the Unity
SessionConfig assets (Assets/ScriptableObjects/Experiments/<code>/<name>.asset), so SessionConfig stays the
single source of truth; any parameter can be overridden per call (e.g. tree_spacing=30).

Everything random derives from the one world seed through fixed, named child streams of a numpy
SeedSequence (the order below is part of the format; add new streams at the end):

    0 moisture-noise permutation    1 mountain-boundary-noise permutation
    2 tree placement (lattice rotation, jitter)
    3 tree attributes (shape, color)
    4 per-fruit reward noise                5 mountain ridge noise
    6 mountain rock-edge noise              7 mountain snow-edge noise
    8 bush id order (a shuffle of the finished bush table: an id says nothing about where a bush is)
    9 per-bush random value (`randomBushValueRange`; drawn only when the range is not (0, 0))
    10 spatial balance (`spatialBalance`; used only when it is not Off, see spatial.py)
    11 plateau levels and heights   12 plateau phase noise   13-15 feature balancing   16 plane coverage
    17 tile grid (rotation, ground levels)   18 tile clusters   19 tiles' feature centres and scatter (tiles layout, see tiles.py)

This module mirrors TreeGenerator.GenerateSites, TerrainManager (moisture field, mountain ramp,
tree-site mask), Tree.ApplyAttributes (canopy radius) and RewardFunction/HarvestManager (bush value,
per-fruit reward). Unity's Perlin implementation is not reproduced bit for bit; the noise here is
classic gradient noise with the same frequencies and range, so fields have the same character.
Terrain grids (moisture, elevation incl. mountains, rock/snow weights, mountain ramp) are generated at the mesh
resolution and exported with the bushes in the binary format Unity loads (see export_unity).

Run as a script to export worlds:
    python scripts/world.py S1 --seeds 0-99 --out worlds        # .npz for the simulator
    python scripts/world.py CF_S1 CF_S2 --unity                 # Unity files into Assets/StreamingAssets/Experiments/<code>
"""

import argparse
import gzip
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml

import spatial
import tiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "Assets" / "ScriptableObjects" / "Experiments"            # <code>/<code>_S1.asset, <code>_I1.asset, <code>.asset
STREAMING_EXPERIMENTS = PROJECT_ROOT / "Assets" / "StreamingAssets" / "Experiments"        # <code>/<name>_seed<N>.world, .interlude.json, instruction texts

# The names the sessions had before they belonged to experiments (the practice session, S1 to S7 and their Interludes), still accepted wherever a session name
# is: the simulator, the agent battery, the results database and the engine tests call sessions by them. Since the CF experiment was removed (2026-11-09) they
# are frozen copies of the tutorial and the CF ladder in `scripts/fixtures/sessions/` (the environment the recorded results were made in), not live assets.
FIXTURE_SESSIONS = Path(__file__).resolve().parent / "fixtures" / "sessions"
LEGACY_NAMES = {"P": "FIX_S0", "P_Interlude": "FIX_I0",
                **{f"S{n}": f"FIX_S{n}" for n in range(1, 8)}, **{f"S{n}_Interlude": f"FIX_I{n}" for n in range(1, 8)}}


def canonical(name):
    """The session's current asset name (`S1` -> `FIX_S1`); a name that is already current, or a path, is returned as it is."""
    return LEGACY_NAMES.get(name, name)


def experiment_of(name):
    """The experiment code of a session name: the part before the first underscore (`FN_S1` -> `FN`), as `SessionConfig.ExperimentCode`."""
    return canonical(name).split("_")[0]


def interlude_name(session):
    """The Interlude of a session: FN_S1 -> FN_I1 (the practice names too: P -> FIX_I0)."""
    code, tail = canonical(session).split("_", 1)
    return f"{code}_I{tail[1:]}"


def session_asset_path(name):
    name = canonical(name)
    if name.startswith("FIX_"):
        return FIXTURE_SESSIONS / f"{name}.asset"
    return EXPERIMENTS_DIR / experiment_of(name) / f"{name}.asset"

BASIS_NAMES = ["Linear", "InvertedLinear", "GaussianPeak", "InvertedGaussian", "Constant"]


# --------------------------------------------------------------------------------------------------
# Session parameters (read from the Unity .asset YAML)
# --------------------------------------------------------------------------------------------------

def _camel(name):
    head, *rest = name.split("_")
    return head + "".join(w.capitalize() for w in rest)


def _snake(name):
    out = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


class _UnityLoader(yaml.SafeLoader):
    pass


def _unity_mapping(loader, tag_suffix, node):
    return loader.construct_mapping(node, deep=True)


_UnityLoader.add_multi_constructor("tag:unity3d.com,2011:", _unity_mapping)


def _convert(value):
    """YAML value -> plain Python: {x,y} -> tuple, {r,g,b,a} left as dict, dicts recursed."""
    if isinstance(value, dict):
        if set(value) == {"x", "y"}:
            return (float(value["x"]), float(value["y"]))
        return {k: _convert(v) for k, v in value.items()}
    return value


# Fields an older asset file does not have yet (Unity adds a field to an asset only when it is saved): their defaults, snake_case names.
FIELD_DEFAULTS = {"spatial_balance": 0, "shape_varies": True, "color_varies": True, "shape_when_fixed": 0.5, "color_when_fixed": 0.5, "random_bush_value_range": (0.0, 0.0), "design_json": "",
                  "moisture_varies": True, "moisture_when_fixed": 0.5, "moisture_is_feature": False, "moisture_terrace_unevenness": 0.0,
                  "feature_balance": 0, "feature_coverage": 0, "feature_balance_target": 0.7, "feature_balance_scales": (40.0, 60.0, 120.0, 240.0),
                  "moisture_terrace_mode": 0, "terrace_mean_width": 0.14, "terrace_width_spread": 0.7, "terrace_max_band": 0.30, "terrace_min_step": 0.08, "terrace_phase_shift": 0.4,
                  "terrace_phase_frequency": 0.6, "terrace_strength": 1.0, "terrace_diffusion_iterations": 500, "terrace_diffusion_edge": 0.1, "interlude_feature_trials": 0, "interlude_peak_trials": 0, "interlude_interaction_trials": 0,
                  "layout": None, "assignment": None, "reward_stage": None,      # (stage names: None = the default, see stage_names)
                  "tile_radius": 70.0, "tile_ramp_width": 14.0, "tile_moisture_levels": 4, "tile_bushes": 9, "tile_cluster_radius": 22.0, "tile_cluster_spacing": 12.0, "tile_spread": 0.12,
                  "tile_arrangement": None, "tile_value_mode": None, "tile_within_mode": None, "tile_good_fraction": 0.25, "tile_smoothness": 0, "tile_gradient": 0.3, "tile_gradient_angle": -1.0,
                  "tile_coverage_min": 0.0, "tile_start_spread_min": 0.0}               # (the tiles layout, tiles.py)


FEATURES = ("shape", "color", "moisture")


def moisture_matters(params):
    """Whether the reward depends on moisture. If not, moisture (the ground colour and the elevation) is decoration: it is out of the Interlude's
    feature gap (the designer knows the reward; the simulated agents sense moisture like participants do)."""
    rf = getattr(params, "reward_function", None)
    return rf is None or abs(float(rf["moistureComponent"]["weight"])) > 0.0


def load_session(name="S1", **overrides):
    """Load session parameters as an attribute namespace with snake_case names
    (e.g. tree_spacing, world_half_extent, reward_function). Keyword overrides replace values."""
    path = Path(name)
    if not path.suffix:
        path = session_asset_path(name)
    with open(path) as f:
        doc = yaml.load(f, Loader=_UnityLoader)
    fields = doc["MonoBehaviour"]
    params = {**FIELD_DEFAULTS, **{_snake(k): _convert(v) for k, v in fields.items() if not k.startswith("m_")}}
    params["session_name"] = Path(path).stem
    for key, value in overrides.items():
        if key not in params:
            raise KeyError(f"unknown session parameter '{key}'")
        params[key] = value
    return SimpleNamespace(**params)


# --------------------------------------------------------------------------------------------------
# Reward function
# --------------------------------------------------------------------------------------------------

def _basis(component, x):
    x = np.clip(x, 0.0, 1.0)
    kind = BASIS_NAMES[int(component["basisFunctionType"])]
    if kind == "Linear":
        v = x
    elif kind == "InvertedLinear":
        v = 1.0 - x
    elif kind in ("GaussianPeak", "InvertedGaussian"):
        sigma = max(float(component["width"]), 1e-4)
        g = np.exp(-((x - float(component["peak"])) ** 2) / (2.0 * sigma * sigma))
        v = g if kind == "GaussianPeak" else 1.0 - g
    else:
        v = np.ones_like(x)
    return v * float(component["weight"])


def factor_value(factor, x):
    """One feature's factor of a `factors` term (`RewardFactor.Evaluate`): kind 0 a sigmoid of steepness `scale` about `center`, divided by its value at the paying end (x = 1, or x = 0
    when `inverted`), so it is 1 there; kind 1 a Gaussian of spread `scale` about `center`."""
    x = np.clip(x, 0.0, 1.0)
    center, scale = float(factor["center"]), float(factor["scale"])
    if int(factor["kind"]) == 1:
        sigma = max(scale, 1e-4)
        return np.exp(-((x - center) ** 2) / (2.0 * sigma * sigma))
    if bool(factor["inverted"]):
        x = 1.0 - x
    return (1.0 / (1.0 + np.exp(-scale * (x - center)))) / (1.0 / (1.0 + np.exp(-scale * (1.0 - center))))


def bush_value(reward_function, shape, color, moisture):
    """R_bush = w1 f1(shape) + w2 f2(color) + w3 f3(moisture) + the sum of the Gaussian bumps over (shape, color), each turned by its `angle` (degrees) about its centre
    + the sum of the product terms (one feature linear times a Gaussian of the other) + the sum of the `factors` terms (one sigmoid or Gaussian factor per feature, as their
    product or their mean); no normalization."""
    value = (_basis(reward_function["shapeComponent"], shape)
             + _basis(reward_function["colorComponent"], color)
             + _basis(reward_function["moistureComponent"], moisture))
    for b in reward_function.get("bumps") or []:
        sigma_shape = max(float(b["width"]), 1e-4)
        width_color = float(b.get("widthColor") or 0.0)            # 0 (or absent): the same spread as along shape, a round bump
        sigma_color = max(width_color, 1e-4) if width_color > 0.0 else sigma_shape
        ds, dc = np.clip(shape, 0.0, 1.0) - float(b["centerShape"]), np.clip(color, 0.0, 1.0) - float(b["centerColor"])
        angle = float(b.get("angle") or 0.0)
        if angle != 0.0:                                           # the spreads lie along the axes turned by `angle`: `width` along the turned shape axis
            cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            ds, dc = ds * cos + dc * sin, -ds * sin + dc * cos
        value = value + float(b["height"]) * np.exp(-(ds * ds / (2.0 * sigma_shape ** 2) + dc * dc / (2.0 * sigma_color ** 2)))
    for p in reward_function.get("products") or []:
        in_shape = bool(p["linearInShape"])
        linear = np.clip(shape if in_shape else color, 0.0, 1.0)
        if bool(p["linearInverted"]):
            linear = 1.0 - linear
        sigma = max(float(p["width"]), 1e-4)
        d = np.clip(color if in_shape else shape, 0.0, 1.0) - float(p["center"])
        value = value + float(p["height"]) * linear * np.exp(-(d * d) / (2.0 * sigma * sigma))
    for t in reward_function.get("factors") or []:
        fs, fc = factor_value(t["shapeFactor"], shape), factor_value(t["colorFactor"], color)
        value = value + float(t["height"]) * (fs * fc if int(t["combine"]) == 0 else 0.5 * (fs + fc))
    return value


def terms_relevance(reward_function):
    """How much each feature matters to a `terms` reward: |weight| of its component, plus the height of every bump and product term (each makes
    both of its features, shape and colour, relevant)."""
    w = {f: abs(float(reward_function[f + "Component"]["weight"])) for f in FEATURES}
    for b in list(reward_function.get("bumps") or []) + list(reward_function.get("products") or []) + list(reward_function.get("factors") or []):
        w["shape"] += abs(float(b["height"]))
        w["color"] += abs(float(b["height"]))
    return w


# --------------------------------------------------------------------------------------------------
# Noise
# --------------------------------------------------------------------------------------------------

# Amplitude gain so the field spreads like Unity's Mathf.PerlinNoise: the moisture field's std over the valley is
# 0.166 in Unity (8 seeds, 0.153-0.174) vs 0.135 here without gain.
PERLIN_GAIN = 1.23

_GRADS = np.array([[1, 1], [-1, 1], [1, -1], [-1, -1], [1, 0], [-1, 0], [0, 1], [0, -1]], dtype=float)


class Perlin:
    """Classic 2D gradient noise on a seeded permutation, returned in about [0, 1] like Mathf.PerlinNoise."""

    def __init__(self, rng):
        p = rng.permutation(256)
        self._p = np.concatenate([p, p])

    @staticmethod
    def _fade(t):
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

    def __call__(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        xf0 = np.floor(x)
        yf0 = np.floor(y)
        xf = x - xf0
        yf = y - yf0
        xi = xf0.astype(np.int64) & 255
        yi = yf0.astype(np.int64) & 255
        u = self._fade(xf)
        v = self._fade(yf)
        p = self._p

        def grad(h, dx, dy):
            g = _GRADS[h & 7]
            return g[..., 0] * dx + g[..., 1] * dy

        aa = p[p[xi] + yi]
        ab = p[p[xi] + yi + 1]
        ba = p[p[xi + 1] + yi]
        bb = p[p[xi + 1] + yi + 1]
        x1 = grad(aa, xf, yf) * (1 - u) + grad(ba, xf - 1, yf) * u
        x2 = grad(ab, xf, yf - 1) * (1 - u) + grad(bb, xf - 1, yf - 1) * u
        n = x1 * (1 - v) + x2 * v
        return np.clip(0.5 + 0.5 * PERLIN_GAIN * n, 0.0, 1.0)


# --------------------------------------------------------------------------------------------------
# Terrain fields that matter for the task (moisture, valley mask)
# --------------------------------------------------------------------------------------------------

TERRACE_PARAMS = ("terrace_mean_width", "terrace_width_spread", "terrace_max_band", "terrace_min_step", "terrace_phase_shift", "terrace_phase_frequency", "terrace_strength",
                  "terrace_diffusion_iterations", "terrace_diffusion_edge")
DIFFUSION_GRID = 257            # points across the valley of the grid the diffusion mode works on (about 2.7 world units at the usual size)


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def staircase_map(t, centres, values, sharp):
    """Piecewise map of the rank t: plateau value `values[i]` at `centres[i]`, joined by ramps that fill 1 - sharp of each gap (a smoothstep)."""
    t = np.asarray(t, dtype=float)
    idx = np.clip(np.searchsorted(centres, t, side="right") - 1, 0, len(centres) - 2)
    c0, c1 = centres[idx], centres[idx + 1]
    f = np.clip((t - c0) / (c1 - c0), 0.0, 1.0)
    width = max(0.02, 1.0 - float(sharp))
    out = values[idx] + _smooth((f - (1.0 - width) / 2.0) / width) * (values[idx + 1] - values[idx])
    out = np.where(t <= centres[0], values[0], out)
    return np.where(t >= centres[-1], values[-1], out)


def random_staircase(rng, mean_width, spread, max_band, min_step, min_plateaus=3):
    """The plateaus of a random staircase over the rank 0..1 of a field: (centres, values). Band widths are drawn lognormal around `mean_width` (log spread `spread`,
    none wider than `max_band`) until the ranks are used up, so the number of plateaus is whatever comes out. A plateau's value is its band's middle plus a jitter within
    the band, all rescaled to span 0 to 1 (monotone: the order of the field is kept). Neighbours whose values differ by less than `min_step` are merged."""
    while True:
        widths = []
        while sum(widths) < 1.0:
            widths.append(float(min(max(np.exp(rng.normal(np.log(mean_width), spread)), 0.02), max_band)))
        widths = np.array(widths)
        widths[-1] = max(1.0 - widths[:-1].sum(), 0.0)
        if widths[-1] < 0.02:
            widths[-2] += widths[-1]
            widths = widths[:-1]
        if len(widths) >= min_plateaus:
            break
    widths = widths / widths.sum()
    edges = np.concatenate([[0.0], np.cumsum(widths)])
    values = (edges[:-1] + edges[1:]) / 2.0 + rng.uniform(-1.0, 1.0, len(widths)) * 0.35 * widths
    values = np.maximum.accumulate(values)
    for _ in range(100):
        span = values[-1] - values[0]
        values = (values - values[0]) / span if span > 0 else np.linspace(0.0, 1.0, len(values))
        gaps = np.diff(values)
        i = int(np.argmin(gaps))
        if gaps[i] >= min_step or len(values) <= min_plateaus:
            break
        merged = (widths[i] * values[i] + widths[i + 1] * values[i + 1]) / (widths[i] + widths[i + 1])            # the pair becomes one plateau
        widths = np.concatenate([widths[:i], [widths[i] + widths[i + 1]], widths[i + 2:]])
        values = np.concatenate([values[:i], [merged], values[i + 2:]])
    edges = np.concatenate([[0.0], np.cumsum(widths)])
    return (edges[:-1] + edges[1:]) / 2.0, values


def edge_preserving_diffusion(u, iterations, edge_quantile, dt=0.2):
    """Perona-Malik diffusion of a 2-D field: it flattens where the gradient is small and keeps the steps where it is large. The edge threshold is the
    `edge_quantile` quantile of the field's gradient magnitude (a lower quantile keeps more edges, so more and smaller plateaus); the border is reflected."""
    u = np.array(u, dtype=float)
    gy, gx = np.gradient(u)
    k = float(np.quantile(np.hypot(gx, gy), edge_quantile))
    for _ in range(int(iterations)):
        gy, gx = np.gradient(np.pad(u, 1, mode="reflect"))
        g = 1.0 / (1.0 + (np.hypot(gx, gy) / k) ** 2)
        div = np.gradient(g * gy, axis=0) + np.gradient(g * gx, axis=1)
        u = u + dt * div[1:-1, 1:-1]
    return u


class Terrain:
    def __init__(self, params, moisture_noise, boundary_noise, ridge_noise=None, rock_noise=None, snow_noise=None, level_rng=None, phase_noise=None, tile_rng=None):
        self.p = params
        self.tiles = tiles.TileGrid(params, tile_rng) if getattr(params, "layout", None) == "tiles" else None      # the hexagonal tiles' ground (tiles.py)
        self._level_rng = level_rng
        self._levels = None
        self._phase_noise = phase_noise
        self._stairs = None
        self._diffused = None
        self._moisture_noise = moisture_noise
        self._boundary_noise = boundary_noise
        self._ridge_noise = ridge_noise
        self._rock_noise = rock_noise
        self._snow_noise = snow_noise
        self._valley_cdf = None

    @staticmethod
    def from_seed(params, seed):
        rngs = [np.random.default_rng(c) for c in np.random.SeedSequence(int(seed)).spawn(18)]
        return Terrain(params, Perlin(rngs[0]), Perlin(rngs[1]), Perlin(rngs[5]), Perlin(rngs[6]), Perlin(rngs[7]), rngs[11], Perlin(rngs[12]), rngs[17])

    def _raw_moisture(self, x, z):
        """Octave sum of noise at frequency * 0.01 (the continuous moisture field, before any terracing)."""
        p = self.p
        octaves = max(1, int(p.terrain_noise_octaves))
        freq = p.terrain_noise_frequency * 0.01
        amplitude = 1.0
        value = 0.0
        total = 0.0
        x = np.asarray(x, dtype=float)
        z = np.asarray(z, dtype=float)
        for o in range(octaves):
            value = value + self._moisture_noise(x * freq + o * 17.3, z * freq + o * 31.7) * amplitude
            total += amplitude
            amplitude *= 0.5
            freq *= 2.0
        return np.clip(value / total, 0.0, 1.0)

    def _rank(self, raw):
        """The rank (0..1, uniform over the valley) of a raw field value."""
        cdf = self._valley_quantiles()
        return np.interp(raw, cdf, np.linspace(0.0, 1.0, cdf.size))

    def _staircase(self, x, z, raw):
        """Staircase mode: the rank of the field, shifted by a low-frequency noise (so plateau edges stop following the field's own contours and a plateau's height
        varies from place to place), put through a random staircase (`random_staircase`: no level count), then mixed with the smooth rank by `terrace_strength`."""
        p = self.p
        t = self._rank(raw)
        centres, values = self.staircase_levels()
        f = float(p.terrace_phase_frequency) * 0.01
        shift = float(p.terrace_phase_shift) * 2.0 * (self._phase_noise(np.asarray(x, dtype=float) * f + 3.1, np.asarray(z, dtype=float) * f + 7.7) - 0.5)
        stepped = staircase_map(np.clip(t + shift, 0.0, 1.0), centres, values, float(getattr(p, "moisture_terrace_sharpness", 0.7)))
        s = float(np.clip(p.terrace_strength, 0.0, 1.0))
        return (1.0 - s) * t + s * stepped

    def staircase_levels(self):
        """The plateaus of this seed's staircase, (centres, values) over the rank 0..1 (drawn once, from stream 11)."""
        if self._stairs is None:
            p = self.p
            self._stairs = random_staircase(self._level_rng, float(p.terrace_mean_width), float(p.terrace_width_spread), float(p.terrace_max_band), float(p.terrace_min_step))
        return self._stairs

    def _diffusion(self, x, z):
        """Diffusion mode: the rank field smoothed by edge-preserving diffusion on a grid over the valley (computed once), rescaled linearly to 0..1 (not equalised:
        that would turn the tiny differences on a plateau into a slope), mixed with the smooth rank by `terrace_strength`, and read at (x, z) by bilinear interpolation."""
        p = self.p
        half = float(p.world_half_extent - p.mountain_band_width)
        if self._diffused is None:
            axis = np.linspace(-half, half, DIFFUSION_GRID)
            gx, gz = np.meshgrid(axis, axis, indexing="ij")
            t = self._rank(self._raw_moisture(gx, gz))
            u = edge_preserving_diffusion(t, p.terrace_diffusion_iterations, p.terrace_diffusion_edge)
            u = (u - u.min()) / (u.max() - u.min())
            s = float(np.clip(p.terrace_strength, 0.0, 1.0))
            self._diffused = (1.0 - s) * t + s * u
        grid = self._diffused
        step = 2.0 * half / (DIFFUSION_GRID - 1)
        fx = np.clip((np.asarray(x, dtype=float) + half) / step, 0.0, DIFFUSION_GRID - 1.000001)
        fz = np.clip((np.asarray(z, dtype=float) + half) / step, 0.0, DIFFUSION_GRID - 1.000001)
        i, j = np.floor(fx).astype(int), np.floor(fz).astype(int)
        a, b = fx - i, fz - j
        return (grid[i, j] * (1 - a) * (1 - b) + grid[i + 1, j] * a * (1 - b) + grid[i, j + 1] * (1 - a) * b + grid[i + 1, j + 1] * a * b)

    def _finish(self, level, x, z):
        """The small undulation on plateau tops (`moisture_terrace_residual`) and the clip, shared by the modes that build their own plateaus."""
        amp = float(np.clip(getattr(self.p, "moisture_terrace_residual", 0.0), 0.0, 0.45))
        level = amp + (1.0 - 2.0 * amp) * level
        if amp > 0.0:
            fx = 2.0 * 0.01
            level = level + amp * 2.0 * (self._moisture_noise(np.asarray(x, dtype=float) * fx + 101.3, np.asarray(z, dtype=float) * fx + 57.1) - 0.5)
        return np.clip(level, 0.0, 1.0)

    def terrace_levels(self):
        """The moisture value of each of the `moisture_terrace_levels` plateaus, dry to wet, from 0 to 1. Evenly spaced when `moisture_terrace_unevenness` is 0; at 1 each
        level is drawn at random within its own n-th of the range (so the order is kept and the whole range is still used), then all are rescaled to span 0 to 1; between
        0 and 1 a mix. A seed's levels are fixed (stream 11), so the plateaus are consistent regions with values anywhere in the continuum."""
        if self._levels is None:
            n = int(getattr(self.p, "moisture_terrace_levels", 0))
            even = np.linspace(0.0, 1.0, max(n, 2))
            u = float(np.clip(getattr(self.p, "moisture_terrace_unevenness", 0.0), 0.0, 1.0))
            if u > 0.0 and n >= 2:
                jittered = (np.arange(n) + self._level_rng.uniform(0.0, 1.0, n)) / n
                jittered = (jittered - jittered[0]) / (jittered[-1] - jittered[0])
                even = (1.0 - u) * even + u * jittered
            self._levels = even
        return self._levels

    def _valley_quantiles(self):
        """Sorted raw moisture over the valley, used to rank-normalise the field so each terrace level
        covers about the same area."""
        if self._valley_cdf is None:
            half = self.p.world_half_extent - self.p.mountain_band_width
            axis = np.linspace(-half, half, 257)
            gx, gz = np.meshgrid(axis, axis, indexing="ij")
            self._valley_cdf = np.sort(self._raw_moisture(gx, gz).ravel())
        return self._valley_cdf

    def moisture(self, x, z):
        """The moisture field. With `moisture_terrace_levels` >= 2 the field is rank-normalised over the valley
        and snapped to that many evenly spaced levels (0 .. 1), with ramps between plateaus whose width is set by
        `moisture_terrace_sharpness` (1 = narrow ramps, 0 = ramps spanning the whole cell) and a small
        within-plateau undulation of amplitude `moisture_terrace_residual` (moisture units, +-; the levels are
        inset by that amount so the whole range 0..1 is still used without clipping). With
        levels < 2 (default) it is the plain continuous field."""
        p = self.p
        if not getattr(p, "moisture_varies", True):                  # one moisture over the valley: a flat, single-coloured ground
            return np.full(np.shape(x), float(getattr(p, "moisture_when_fixed", 0.5)))
        if self.tiles is not None:                                    # the tiles layout: a plateau per hexagonal tile
            return self.tiles.moisture(x, z)
        raw = self._raw_moisture(x, z)
        mode = int(getattr(p, "moisture_terrace_mode", 0))
        if mode:
            return self._finish(self._staircase(x, z, raw) if mode == 1 else self._diffusion(x, z), x, z)
        n = int(getattr(p, "moisture_terrace_levels", 0))
        if n < 2:
            return raw
        cdf = self._valley_quantiles()
        t = np.interp(raw, cdf, np.linspace(0.0, 1.0, cdf.size))
        width = max(0.02, 1.0 - float(np.clip(getattr(p, "moisture_terrace_sharpness", 0.8), 0.0, 1.0)))
        g = np.clip(t * n - 0.5, 0.0, n - 1 - 1e-9)
        j = np.floor(g)
        ramp = self._smoothstep((g - j - (1.0 - width) / 2.0) / width)
        amp = float(np.clip(getattr(p, "moisture_terrace_residual", 0.0), 0.0, 0.45))
        # levels are inset by `amp` so the undulation is not clipped at moisture 0 and 1
        if float(getattr(p, "moisture_terrace_unevenness", 0.0)) > 0.0:
            levels = self.terrace_levels()
            k = j.astype(int)
            level = amp + (1.0 - 2.0 * amp) * (levels[k] + ramp * (levels[k + 1] - levels[k]))
        else:
            level = amp + (1.0 - 2.0 * amp) * (j + ramp) / (n - 1)          # evenly spaced (the original expression, kept exactly: worlds are compared byte for byte)
        if amp > 0.0:
            fx = 2.0 * 0.01     # same ~50-unit scale as the old continuous field
            x = np.asarray(x, dtype=float)
            z = np.asarray(z, dtype=float)
            level = level + amp * 2.0 * (self._moisture_noise(x * fx + 101.3, z * fx + 57.1) - 0.5)
        return np.clip(level, 0.0, 1.0)

    def mountain_ramp(self, x, z, inset=0.0):
        """0 across the valley, rising to 1 at the map edge; the foot of the ramp is irregular."""
        p = self.p
        x = np.asarray(x, dtype=float)
        z = np.asarray(z, dtype=float)
        if p.mountain_band_width <= 0:
            return np.zeros(np.broadcast(x, z).shape)
        edge_dist = p.world_half_extent - np.maximum(np.abs(x), np.abs(z)) - inset
        jitter = self._boundary_noise(x / 70.0 + 53.1, z / 70.0 + 11.7)
        band = np.maximum(10.0, p.mountain_band_width + (jitter - 0.5) * 2.0 * p.mountain_boundary_jitter)
        return np.clip(1.0 - edge_dist / band, 0.0, 1.0)

    def ridged(self, x, z):
        """Ridged multifractal noise in [0, 1] (TerrainManager.Ridged): sharp crests."""
        scale = max(1.0, float(self.p.mountain_noise_scale))
        freq = 1.0 / scale
        value = 0.0
        amplitude = 1.0
        total = 0.0
        for o in range(3):
            n = self._ridge_noise(x * freq + o * 23.9, z * freq + o * 41.3)
            value = value + (1.0 - np.abs(2.0 * n - 1.0)) * amplitude
            total += amplitude
            amplitude *= 0.5
            freq *= 2.1
        return value / total

    def mountain_elevation(self, x, z):
        u = self.mountain_ramp(x, z)
        h = self.p.mountain_height * np.power(u, 1.5) * (0.55 + 0.45 * self.ridged(x, z))
        return np.where(u > 0.0, h, 0.0)

    def elevation(self, x, z):
        """Valley elevation (coupled to moisture) plus the mountain term, which is 0 inside the valley."""
        return (1.0 - self.moisture(x, z)) * self.p.terrain_max_elevation + self.mountain_elevation(x, z)

    @staticmethod
    def _smoothstep(t):
        t = np.clip(t, 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    def mountain_weights(self, x, z, elevation):
        """(rock, snow) weights for the terrain shader; 0 in the valley (TerrainManager.MountainWeights)."""
        p = self.p
        u = self.mountain_ramp(x, z)
        rock_noise = self._rock_noise(x / 9.0, z / 9.0 + 97.3)
        rock = self._smoothstep((u + (rock_noise - 0.5) * 0.12) / 0.25)
        snow_line = p.terrain_max_elevation + p.snow_line_fraction * p.mountain_height
        snow_noise = (self._snow_noise(x / 14.0 + 7.7, z / 14.0 + 3.1) - 0.5) * 12.0
        snow = self._smoothstep((elevation + snow_noise - (snow_line - 4.0)) / 8.0)
        inside = u > 0.0
        return np.where(inside, rock, 0.0), np.where(inside, snow * rock, 0.0)

    def grids(self):
        """Terrain on the mesh grid: arrays of shape (res, res) indexed [i (x), j (z)], vertex i*res + j,
        world coordinate lerp(-half, half, i / (res - 1)). Returns a dict of float32 arrays."""
        res = max(2, int(self.p.terrain_mesh_resolution))
        axis = np.linspace(-self.p.world_half_extent, self.p.world_half_extent, res)
        x, z = np.meshgrid(axis, axis, indexing="ij")
        moisture = self.moisture(x, z)
        elevation = (1.0 - moisture) * self.p.terrain_max_elevation + self.mountain_elevation(x, z)
        rock, snow = self.mountain_weights(x, z, elevation)
        ramp = self.mountain_ramp(x, z)
        return {"moisture": moisture.astype(np.float32), "elevation": elevation.astype(np.float32),
                "rock": rock.astype(np.float32), "snow": snow.astype(np.float32), "ramp": ramp.astype(np.float32)}

    def is_tree_site(self, x, z):
        return self.mountain_ramp(x, z, self.p.tree_edge_margin) <= 0.0

    def is_walkable(self, x, z):
        x = np.asarray(x, dtype=float)
        z = np.asarray(z, dtype=float)
        inside = (np.abs(x) <= self.p.world_half_extent - 1.0) & (np.abs(z) <= self.p.world_half_extent - 1.0)
        return inside & (self.mountain_ramp(x, z) < self.p.mountain_block_threshold)


# --------------------------------------------------------------------------------------------------
# World
# --------------------------------------------------------------------------------------------------

@dataclass
class World:
    """One generated world: per-bush arrays plus the parameters the simulator needs.

    Arrays are indexed by bush id 0..n-1 (lattice order). Positions are (x, z) in world units.
    """
    params: SimpleNamespace
    seed: int
    pos: np.ndarray            # (n, 2) bush centers
    shape: np.ndarray          # (n,) attributes in [0, 1]
    color: np.ndarray
    moisture: np.ndarray
    canopy_radius: np.ndarray  # (n,)
    value: np.ndarray          # (n,) R_bush, the true mean reward per fruit (before noise and rounding)
    fruit_reward: np.ndarray   # (n, fruit_count) int: reward of the k-th fruit taken from each bush
    start: np.ndarray          # (2,) player start

    @property
    def n(self):
        return len(self.pos)

    @property
    def terrain(self):
        """The terrain fields of this world, rebuilt from (params, seed)."""
        if getattr(self, "_terrain", None) is None:
            self._terrain = Terrain.from_seed(self.params, self.seed)
        return self._terrain

    @property
    def session_duration(self):
        return float(self.params.session_duration)

    @property
    def move_speed(self):
        return float(self.params.player_move_speed)

    @property
    def fruit_duration(self):
        return float(self.params.fruit_harvest_duration)

    @property
    def fruit_count(self):
        return self.fruit_reward.shape[1]

    @property
    def reach(self):
        """(n,) center distance within which harvesting is possible: canopy radius + range gap."""
        p = self.params
        return self.canopy_radius + p.harvest_range_gap_base + p.harvest_range_gap_per_radius * self.canopy_radius

    @property
    def bush_total(self):
        """(n,) total reward of fully harvesting each bush."""
        return self.fruit_reward.sum(axis=1)

    def center_distances(self):
        """(n+1, n+1) center-to-center distance matrix; row/column n is the start. For planning agents."""
        pts = np.vstack([self.pos, self.start[None, :]])
        d = pts[:, None, :] - pts[None, :, :]
        return np.sqrt((d ** 2).sum(-1))

    # ---- serialization -------------------------------------------------------------------------

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path, pos=self.pos, shape=self.shape, color=self.color, moisture=self.moisture,
            canopy_radius=self.canopy_radius, value=self.value, fruit_reward=self.fruit_reward,
            start=self.start, seed=self.seed, params=json.dumps(vars(self.params)))

    @staticmethod
    def load(path):
        with np.load(path, allow_pickle=False) as z:
            params = json.loads(str(z["params"]))
            params = {k: (tuple(v) if isinstance(v, list) else v) for k, v in params.items()}
            return World(params=SimpleNamespace(**params), seed=int(z["seed"]), pos=z["pos"], shape=z["shape"],
                         color=z["color"], moisture=z["moisture"], canopy_radius=z["canopy_radius"],
                         value=z["value"], fruit_reward=z["fruit_reward"], start=z["start"])


# Parameters that shape a world. Written into Unity world files so the game can warn when SessionConfig has
# changed since the file was generated. Names are the SessionConfig field names (camelCase).
CHECK_KEYS = ["worldHalfExtent", "terrainMeshResolution", "terrainNoiseFrequency", "terrainNoiseOctaves",
              "terrainMaxElevation", "moistureTerraceLevels", "moistureTerraceSharpness", "moistureTerraceResidual",
              "mountainBandWidth", "mountainBoundaryJitter", "mountainHeight",
              "mountainNoiseScale", "snowLineFraction", "treeSpacing", "placementJitter", "startClearingRadius",
              "treeEdgeMargin", "fruitCount", "rewardStd"]
REWARD_PARTS = ["shape", "color", "moisture"]
WORLD_MAGIC = b"FWLD"
WORLD_VERSION = 2
GRID_NAMES = ["moisture", "elevation", "rock", "snow", "ramp"]
GRID_BITS = {"moisture": 16, "elevation": 16, "rock": 8, "snow": 8, "ramp": 8}          # the masks need 8 bits (a step of 0.002), moisture and elevation 16 (about 0.001 world units of height)


def check_values(params):
    """{name: value} of the parameters a world depends on (see CHECK_KEYS)."""
    out = {k: float(getattr(params, _snake(k), 0.0)) for k in CHECK_KEYS}
    # Unity recomputes each bush's canopy radius from these (Tree.ApplyAttributes) while the tools read the radius
    # stored in the file, so a changed range makes replay's harvest range and the simulator's reach wrong.
    for name, key in (("canopyWidthRange", "canopy_width_range"), ("shapeRange", "shape_range")):
        lo, hi = getattr(params, key)
        out[f"{name}.min"], out[f"{name}.max"] = float(lo), float(hi)
    # the three new fields are written only when they differ from the default, so a world file made before they existed stays byte-identical
    # (Unity's FindMismatches treats a name missing from the file as the default)
    for name, value, default in (("spatialBalance", float(params.spatial_balance), 0.0),
                                 ("shapeVaries", float(bool(params.shape_varies)), 1.0), ("colorVaries", float(bool(params.color_varies)), 1.0),
                                 ("moistureVaries", float(bool(params.moisture_varies)), 1.0),
                                 ("shapeWhenFixed", float(params.shape_when_fixed), 0.5), ("colorWhenFixed", float(params.color_when_fixed), 0.5),
                                 ("moistureWhenFixed", float(params.moisture_when_fixed), 0.5),
                                 ("moistureTerraceUnevenness", float(params.moisture_terrace_unevenness), 0.0),
                                 ("randomBushValueRange.min", float(params.random_bush_value_range[0]), 0.0),
                                 ("randomBushValueRange.max", float(params.random_bush_value_range[1]), 0.0)):
        if value != default:
            out[name] = value
    if int(params.feature_balance):                                # feature balancing writes its mode, target and scales (a session without it writes none)
        out["featureBalance"] = float(params.feature_balance)
        out["featureBalanceTarget"] = float(params.feature_balance_target)
        out["featureBalanceScales.count"] = float(len(params.feature_balance_scales))
        out["featureBalanceScales.sum"] = float(sum(params.feature_balance_scales))
    if int(getattr(params, "feature_coverage", 0)):                # plane coverage (the sparse-reward experiment) writes its mode; a session without it writes none
        out["featureCoverage"] = float(params.feature_coverage)
    if getattr(params, "layout", None) == "tiles":                 # the tiles layout writes the numbers it reads (a world of another layout writes none)
        for name in tiles.TILE_PARAMS:
            out[_camel(name)] = float(getattr(params, name))
    if int(params.moisture_terrace_mode):                          # the new modes write their mode and every parameter they read (a session in the Levels mode writes none)
        out["moistureTerraceMode"] = float(params.moisture_terrace_mode)
        for name in TERRACE_PARAMS:
            out[_camel(name)] = float(getattr(params, name))
    for part in REWARD_PARTS:
        comp = params.reward_function[part + "Component"]
        for field in ("basisFunctionType", "weight", "peak", "width"):
            out[f"reward.{part}.{field}"] = float(comp[field])
    for i, b in enumerate(params.reward_function.get("bumps") or []):
        for field in ("centerShape", "centerColor", "width", "height"):
            out[f"reward.bump{i}.{field}"] = float(b[field])
        if float(b.get("widthColor") or 0.0) != 0.0:                # (written only when set, so older world files stay identical)
            out[f"reward.bump{i}.widthColor"] = float(b["widthColor"])
        if float(b.get("angle") or 0.0) != 0.0:
            out[f"reward.bump{i}.angle"] = float(b["angle"])
    for i, p in enumerate(params.reward_function.get("products") or []):
        for field in ("linearInShape", "linearInverted", "center", "width", "height"):
            out[f"reward.product{i}.{field}"] = float(p[field])
    for i, t in enumerate(params.reward_function.get("factors") or []):
        out[f"reward.factor{i}.combine"], out[f"reward.factor{i}.height"] = float(t["combine"]), float(t["height"])
        for side in ("shape", "color"):
            for field in ("kind", "center", "scale", "inverted"):
                out[f"reward.factor{i}.{side}.{field}"] = float(t[side + "Factor"][field])
    return out


def unity_world_path(session, seed, out_dir=None):
    """Where the game reads the session's world (`WorldData.PathFor`): the experiment's folder under StreamingAssets/Experiments."""
    session = canonical(session)
    out_dir = Path(out_dir) if out_dir else STREAMING_EXPERIMENTS / experiment_of(session)
    return out_dir / f"{session}_seed{seed}.world"


def quantize_grid(grid, bits):
    """(integer codes, minimum, maximum): the grid rescaled to 0..2^bits-1 between its own extremes (a constant grid has maximum = minimum)."""
    a = np.asarray(grid, dtype=np.float64)
    lo, hi = float(a.min()), float(a.max())
    top = (1 << bits) - 1
    codes = np.round((a - lo) / (hi - lo) * top) if hi > lo else np.zeros(a.shape)
    return codes.astype("<u2" if bits == 16 else "u1"), lo, hi


def dequantize_grid(codes, bits, lo, hi):
    """Inverse of `quantize_grid`, as float32 (what the game holds); the arithmetic is the loader's (WorldData.Load)."""
    return (np.float32(lo) + codes.astype(np.float32) * np.float32((hi - lo) / ((1 << bits) - 1))).astype(np.float32)


def export_unity(world, path):
    """Write the world in the binary format Unity's WorldData.Load reads (version 2).

    Layout: b"FWLD", uint32 version, uint32 header length, UTF-8 JSON header, then one gzip stream holding, per name in
    header["grids"], res*res little-endian unsigned codes (8 or 16 bits, header["gridBits"]) flattened as i*res + j (i across x,
    j across z); a code c is the value gridMin + c * (gridMax - gridMin) / (2^bits - 1). The header holds the bushes (flat
    arrays, full precision), for a tiles layout the tile centres (`tileCentres`, x z pairs; `tileRadius`, `tileRamp`), and the parameter echo used for staleness checks. Version 1 stored the grids as raw float32.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    grids = world.terrain.grids()
    res = grids["moisture"].shape[0]
    checks = check_values(world.params)
    coded = {name: quantize_grid(grids[name], GRID_BITS[name]) for name in GRID_NAMES}
    header = {
        "version": WORLD_VERSION,
        "session": world.params.session_name,
        "seed": int(world.seed),
        "res": int(res),
        "halfExtent": float(world.params.world_half_extent),
        "treeCount": int(world.n),
        "fruitCount": int(world.fruit_count),
        "grids": GRID_NAMES,
        "gridBits": [GRID_BITS[n] for n in GRID_NAMES],
        "gridMin": [coded[n][1] for n in GRID_NAMES],
        "gridMax": [coded[n][2] for n in GRID_NAMES],
        "treePos": world.pos.reshape(-1).tolist(),
        "shape": world.shape.tolist(),
        "color": world.color.tolist(),
        "moisture": world.moisture.tolist(),
        "canopyRadius": world.canopy_radius.tolist(),
        "value": world.value.tolist(),
        "fruitRewards": world.fruit_reward.reshape(-1).astype(int).tolist(),
        "checkNames": list(checks),
        "checkValues": list(checks.values()),
    }
    tiles_grid = getattr(world.terrain, "tiles", None)
    if tiles_grid is not None:                      # a tiles layout: where the tiles are, for the game's patch switches (the tile of a point is its nearest centre)
        header["tileRadius"] = float(tiles_grid.radius)
        header["tileRamp"] = float(tiles_grid.ramp)
        header["tileCentres"] = [float(v) for _, _, c in tiles_grid.tile_centres() for v in c]
    blob = json.dumps(header, separators=(",", ":")).encode("utf-8")
    block = b"".join(np.ascontiguousarray(coded[n][0]).tobytes() for n in GRID_NAMES)
    with open(path, "wb") as f:
        f.write(WORLD_MAGIC)
        f.write(struct.pack("<II", WORLD_VERSION, len(blob)))
        f.write(blob)
        f.write(gzip.compress(block, compresslevel=9, mtime=0))


def read_unity_world(path):
    """Reader for the export_unity format (replay, visibility and the tests; version 1 files still read). Returns (header dict, {grid name: (res, res) float32 array})."""
    with open(path, "rb") as f:
        if f.read(4) != WORLD_MAGIC:
            raise ValueError("not a world file")
        version, n = struct.unpack("<II", f.read(8))
        header = json.loads(f.read(n).decode("utf-8"))
        res = header["res"]
        if version == 1:
            return header, {name: np.frombuffer(f.read(res * res * 4), dtype="<f4").reshape(res, res) for name in header["grids"]}
        if version != WORLD_VERSION:
            raise ValueError(f"world file format version {version}; this reader knows 1 and {WORLD_VERSION}")
        block = gzip.decompress(f.read())
    grids, offset = {}, 0
    for name, bits, lo, hi in zip(header["grids"], header["gridBits"], header["gridMin"], header["gridMax"]):
        size = res * res * bits // 8
        codes = np.frombuffer(block, dtype="<u2" if bits == 16 else "u1", count=res * res, offset=offset).reshape(res, res)
        grids[name] = dequantize_grid(codes, bits, lo, hi)
        offset += size
    return header, grids


def _lattice_sites(params, terrain, rng):
    """Mirror of TreeGenerator.GenerateSites: hex lattice anchored at the start, seeded rotation,
    disc jitter, start clearing, valley mask."""
    spacing = max(1.0, float(params.tree_spacing))
    jitter_radius = min(max(float(params.placement_jitter), 0.0), 1.0) * spacing * 0.5
    half = float(params.world_half_extent)
    clearing = float(params.start_clearing_radius)

    angle = rng.uniform(0.0, math.pi / 3.0)
    a = np.array([math.cos(angle), math.sin(angle)]) * spacing
    b = np.array([math.cos(angle + math.pi / 3.0), math.sin(angle + math.pi / 3.0)]) * spacing

    rng_extent = int(math.ceil(half * 2.0 / spacing)) + 2
    sites = []
    for i in range(-rng_extent, rng_extent + 1):
        for j in range(-rng_extent, rng_extent + 1):
            r = jitter_radius * math.sqrt(rng.uniform())
            phi = rng.uniform(0.0, 2.0 * math.pi)
            p = i * a + j * b + r * np.array([math.cos(phi), math.sin(phi)])
            if np.hypot(p[0], p[1]) < clearing:
                continue
            if abs(p[0]) <= half and abs(p[1]) <= half and terrain.is_tree_site(p[0], p[1]):
                sites.append(p)
    return np.array(sites, dtype=float).reshape(-1, 2)


# --------------------------------------------------------------------------------------------------
# The three stages of a world: layout (where the bushes are), assignment (which attributes each has) and reward (what a bush pays).
# A session names them (`layout`, `assignment`, `reward_stage`; absent = the defaults below, which are what every session so far used); a
# stage is a function in the table of its kind, so a new experiment adds an entry and leaves the others alone. The random streams are
# numbered per use (see the module docstring), not per stage, so a world is the same whichever way the code is organised.
# --------------------------------------------------------------------------------------------------

def layout_lattice(params, terrain, rngs):
    """Bush positions on the seeded hex lattice (stream 2)."""
    return _lattice_sites(params, terrain, rngs[2])


def assign_independent(params, pos, terrain, rngs, reward):
    """Shape and colour drawn independently of position (stream 3), plus the practice session's per-bush value (stream 9)."""
    n = len(pos)
    shape = rngs[3].uniform(0.0, 1.0, n)
    color = rngs[3].uniform(0.0, 1.0, n)
    if not params.shape_varies:                     # "shapes identical": the draws above are still made, so the other streams do not move
        shape = np.full(n, float(params.shape_when_fixed))
    if not params.color_varies:
        color = np.full(n, float(params.color_when_fixed))
    lo, hi = params.random_bush_value_range
    extra = rngs[9].uniform(lo, hi, n) if hi > lo else np.zeros(n)             # the practice session's reward: a value per bush that no attribute predicts
    return shape, color, extra


def assign_balanced(params, pos, terrain, rngs, reward):
    """The independent draw, then its (shape, colour, random value) records dealt to other bushes so the reward is more even over the map (spatial.py, stream 10).
    The records are the same, only their positions change. Moisture stays with the position; a moisture term in the reward is the sites' offset, so the totals
    (record plus the moisture term) are what the swap step evens."""
    shape, color, extra = assign_independent(params, pos, terrain, rngs, reward)
    records = reward(params.reward_function, shape, color, 0.5) + extra
    offset = None
    if moisture_matters(params):
        moisture = terrain.moisture(pos[:, 0], pos[:, 1])
        offset = reward(params.reward_function, np.full(len(pos), 0.5), np.full(len(pos), 0.5), moisture) \
            - reward(params.reward_function, np.full(len(pos), 0.5), np.full(len(pos), 0.5), np.full(len(pos), 0.5))
    index = spatial.balance(pos, records, rngs[10], int(params.spatial_balance), half=float(params.world_half_extent), offset=offset)
    return shape[index], color[index], extra[index]


def assign_balanced_features(params, pos, terrain, rngs, reward):
    """The independent draw, then each visible feature (shape, colour, and the practice session's random value) balanced over space on its own (spatial.py: tiles at
    several scales, then swaps, until the evenness reaches `feature_balance_target`), each with a stream of its own. The features are dealt separately, so they stay
    independent of one another and of moisture, every visible feature is treated the same whether or not it pays (no feature is more regular than the others), and the
    reward, a sum over the features, is evened where the weights are on shape and colour. It uses no reward, so the reward function does not matter."""
    shape, color, extra = assign_independent(params, pos, terrain, rngs, reward)
    mode, scales, half, target = int(params.feature_balance), tuple(float(x) for x in params.feature_balance_scales), float(params.world_half_extent), float(params.feature_balance_target)
    out = []
    for values, visible, stream in ((shape, params.shape_varies, 13), (color, params.color_varies, 14), (extra, np.ptp(extra) > 0.0, 15)):
        out.append(values[spatial.balance(pos, values, rngs[stream], mode, scales=scales, half=half, target=target)] if visible else values)
    return tuple(out)


PLANE_TILE_BUSHES = 16        # bushes in a tile of the plane-coverage assignment: each tile gets a sample of the plane this size


def plane_points(n, rng):
    """`n` points of the unit square: a scrambled Halton sequence (bases 2 and 3). Any stretch of consecutive points covers the square evenly, however the sequence is cut, which is
    what lets `assign_plane` give every tile of the map, and every union of tiles, an even sample of the plane."""
    from scipy.stats import qmc
    return qmc.Halton(d=2, scramble=True, seed=rng).random(n)


def assign_plane(params, pos, terrain, rngs, reward):
    """(shape, colour) pairs that cover the feature plane evenly, dealt over the map so that every part of it gets an even sample of the plane (stream 16; the sparse-reward
    experiment needs a narrow peak of the reward to have bushes on it, spread over the map). The pairs are a scrambled Halton sequence; the map is cut into square tiles of about
    PLANE_TILE_BUSHES bushes, each tile takes a consecutive stretch of the sequence (the tiles in a random order, so no spatial pattern follows the sequence) and deals it to its bushes
    in a random order. Shape and colour are treated alike and the reward is not used, so nothing shows which feature pays; it needs both to vary. The practice session's random
    value is drawn as in `assign_independent`."""
    if not (params.shape_varies and params.color_varies):
        raise ValueError("featureCoverage deals pairs over the (shape, colour) plane: both features must vary")
    _, _, extra = assign_independent(params, pos, terrain, rngs, reward)             # (its draws are made, so the other streams do not move)
    n = len(pos)
    points = plane_points(n, rngs[16])
    side = math.sqrt(PLANE_TILE_BUSHES * 0.866 * float(params.tree_spacing) ** 2)       # 0.866 * spacing^2: the area of a hexagonal lattice cell, one bush's share of the map
    ij = np.floor((pos + float(params.world_half_extent)) / side).astype(int)
    _, tile_of = np.unique(ij[:, 0] * 100_000 + ij[:, 1], return_inverse=True)
    shape, color = np.empty(n), np.empty(n)
    start = 0
    for tile in rngs[16].permutation(tile_of.max() + 1):
        members = np.nonzero(tile_of == tile)[0]
        block = points[start:start + len(members)]
        start += len(members)
        block = block[rngs[16].permutation(len(block))]
        shape[members], color[members] = block[:, 0], block[:, 1]
    if rngs[16].random() < 0.5:                     # the two axes of the sequence are slightly differently regular (bases 2 and 3): which feature gets which is a coin toss per world
        shape, color = color, shape
    return shape, color, extra


def assign_tiles(params, pos, terrain, rngs, reward):
    """(shape, colour) dealt tile by tile (tiles.py `deal_features`, stream 19): each tile's bushes lie around a centre of the tile in the feature plane. The independent draw is still made
    (the other streams do not move) and gives the practice session's random value; a feature that does not vary is the same value everywhere."""
    shape, color, extra = assign_independent(params, pos, terrain, rngs, reward)
    tile_shape, tile_color = tiles.deal_features(params, pos, terrain.tiles, rngs[19], reward)
    return (tile_shape if params.shape_varies else shape), (tile_color if params.color_varies else color), extra


LAYOUTS = {"lattice": layout_lattice, "tiles": tiles.layout_tiles}
ASSIGNMENTS = {"independent": assign_independent, "balanced": assign_balanced, "balanced_features": assign_balanced_features, "plane": assign_plane, "tiles": assign_tiles}
REWARDS = {"terms": bush_value}
RELEVANCE = {"terms": terms_relevance}          # per reward stage: {feature: how much it matters}, for the Interlude and the instruction texts


def session_features(params):
    """The features a session declares: {name: {"visible": bool, "rewarded": bool, "relevance": float}}, in FEATURES order. Visible = it varies between
    bushes (`shapeVaries`, `colorVaries`; moisture: `moistureVaries`, and then only if it pays or the asset declares it with `moistureIsFeature`, so a
    decoration moisture is not a declared feature). Rewarded = the session's reward stage gives it a nonzero relevance."""
    rf = getattr(params, "reward_function", None)
    relevance = RELEVANCE[stage_names(params)[2]](rf) if rf is not None else {f: 1.0 for f in FEATURES}
    visible = {"shape": bool(params.shape_varies), "color": bool(params.color_varies),
               "moisture": bool(params.moisture_varies) and (relevance["moisture"] > 0.0 or bool(params.moisture_is_feature))}
    return {f: {"visible": visible[f], "rewarded": relevance[f] > 0.0, "relevance": relevance[f]} for f in FEATURES}


def stage_names(params):
    """(layout, assignment, reward) names of a session: its own fields, else the defaults (balanced when `spatialBalance` is not Off)."""
    coverage = int(getattr(params, "feature_coverage", 0))
    if sum(bool(int(v)) for v in (params.feature_balance, params.spatial_balance, coverage)) > 1:
        raise ValueError("featureBalance, spatialBalance and featureCoverage are three ways of dealing the features: set one of them")
    assignment = getattr(params, "assignment", None) or ("plane" if coverage else "balanced_features" if int(params.feature_balance) else "balanced" if int(params.spatial_balance) else "independent")
    return (getattr(params, "layout", None) or "lattice", assignment, getattr(params, "reward_stage", None) or "terms")


def generate_world(params, seed):
    """Build the world for (params, seed). `params` is a namespace from load_session()."""
    layout_name, assignment_name, reward_name = stage_names(params)
    reward = REWARDS[reward_name]
    rngs = [np.random.default_rng(c) for c in np.random.SeedSequence(int(seed)).spawn(20)]          # (streams 11 to 15, the terrace levels, the phase noise and the balancing of shape, colour and the random value, were added after the first 11, 16, the plane coverage, after those, and 17 to 19, the tiles, after those: spawn(20) gives the same first 16 children as spawn(16), so no world moves)
    terrain = Terrain(params, Perlin(rngs[0]), Perlin(rngs[1]), Perlin(rngs[5]), Perlin(rngs[6]), Perlin(rngs[7]), rngs[11], Perlin(rngs[12]), rngs[17])

    pos = LAYOUTS[layout_name](params, terrain, rngs)
    n = len(pos)
    shape, color, extra = ASSIGNMENTS[assignment_name](params, pos, terrain, rngs, reward)
    moisture = terrain.moisture(pos[:, 0], pos[:, 1])

    # Tree.ApplyAttributes: canopy is a sphere scaled (sx, sy, sx); radius = max horizontal scale / 2.
    lo, hi = params.shape_range
    t = np.clip((shape - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    w_lo, w_hi = params.canopy_width_range
    canopy_radius = (w_hi + (w_lo - w_hi) * t) * 0.5

    value = reward(params.reward_function, shape, color, moisture) + extra

    # HarvestManager.CollectNextFruit: max(0, round(R_bush + N(0, std))), independent per fruit.
    fruit_count = int(params.fruit_count)
    noise = rngs[4].standard_normal((n, fruit_count)) * float(params.reward_std)
    fruit_reward = np.maximum(0, np.rint(value[:, None] + noise)).astype(np.int32)

    # The lattice enumerates sites in space order, so ids would be spatially ordered: shuffle them (every per-bush array together),
    # so that an agent, or a future component using ids as numbers, learns nothing about unseen bushes from an id.
    order = rngs[8].permutation(n)
    return World(params=params, seed=int(seed), pos=pos[order], shape=shape[order], color=color[order], moisture=moisture[order],
                 canopy_radius=canopy_radius[order], value=value[order], fruit_reward=fruit_reward[order],
                 start=np.zeros(2))


def make_world(session="S1", seed=0, **overrides):
    """Convenience: load_session(session, **overrides) then generate_world(params, seed)."""
    return generate_world(load_session(session, **overrides), seed)


def _parse_seeds(text):
    seeds = []
    for part in text.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            seeds.extend(range(int(lo), int(hi) + 1))
        else:
            seeds.append(int(part))
    return seeds


def main():
    ap = argparse.ArgumentParser(description="Export generated worlds (simulator .npz or Unity .world files).")
    ap.add_argument("sessions", nargs="+", help="session asset names, e.g. S1 S2 S3")
    ap.add_argument("--seeds", default=None,
                    help="e.g. 0-99 or 1,2,7 (default: each session's own worldSeed)")
    ap.add_argument("--out", default=None, help="output directory (default: worlds/ for .npz, "
                    "Assets/StreamingAssets/Experiments/<code> for --unity)")
    ap.add_argument("--unity", action="store_true", help="write Unity .world files instead of .npz")
    args = ap.parse_args()
    for session in args.sessions:
        params = load_session(session)
        seeds = _parse_seeds(args.seeds) if args.seeds else [int(params.world_seed)]
        for seed in seeds:
            world = generate_world(params, seed)
            if args.unity:
                path = unity_world_path(session, seed, args.out)
                export_unity(world, path)
            else:
                out = Path(args.out or "worlds")
                out = out if out.is_absolute() else PROJECT_ROOT / out
                path = out / f"{canonical(session)}_seed{seed}.npz"
                world.save(path)
            print(f"{path.name}: {world.n} bushes")


if __name__ == "__main__":
    main()
