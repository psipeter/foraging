"""World generation for the foraging task, in Python.

A world is fully determined by (session parameters, world seed). Parameters are read from the Unity
SessionConfig assets (Assets/ScriptableObjects/SessionConfig/<name>.asset), so SessionConfig stays the
single source of truth; any parameter can be overridden per call (e.g. tree_spacing=30).

Everything random derives from the one world seed through fixed, named child streams of a numpy
SeedSequence (the order below is part of the format; add new streams at the end):

    0 moisture-noise permutation    1 mountain-boundary-noise permutation
    2 tree placement (lattice rotation, jitter)
    3 tree attributes (shape, color)
    4 per-fruit reward noise                5 mountain ridge noise
    6 mountain rock-edge noise              7 mountain snow-edge noise

This module mirrors TreeGenerator.GenerateSites, TerrainManager (moisture field, mountain ramp,
tree-site mask), Tree.ApplyAttributes (canopy radius) and RewardFunction/HarvestManager (bush value,
per-fruit reward). Unity's Perlin implementation is not reproduced bit for bit; the noise here is
classic gradient noise with the same frequencies and range, so fields have the same character.
Terrain grids (moisture, elevation incl. mountains, rock/snow weights, mountain ramp) are generated at the mesh
resolution and exported with the bushes in the binary format Unity loads (see export_unity).

Run as a script to export worlds:
    python scripts/world.py S1 --seeds 0-99 --out worlds        # .npz for the simulator
    python scripts/world.py S1 S2 S3 --unity                    # Unity files into Assets/StreamingAssets/Worlds
"""

import argparse
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = PROJECT_ROOT / "Assets" / "ScriptableObjects" / "SessionConfig"

BASIS_NAMES = ["Linear", "InvertedLinear", "GaussianPeak", "InvertedGaussian", "Constant"]


# --------------------------------------------------------------------------------------------------
# Session parameters (read from the Unity .asset YAML)
# --------------------------------------------------------------------------------------------------

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


def load_session(name="S1", **overrides):
    """Load session parameters as an attribute namespace with snake_case names
    (e.g. tree_spacing, world_half_extent, reward_function). Keyword overrides replace values."""
    path = Path(name)
    if not path.suffix:
        path = SESSION_DIR / f"{name}.asset"
    with open(path) as f:
        doc = yaml.load(f, Loader=_UnityLoader)
    fields = doc["MonoBehaviour"]
    params = {_snake(k): _convert(v) for k, v in fields.items() if not k.startswith("m_")}
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


def bush_value(reward_function, shape, color, moisture):
    """R_bush = w1 f1(shape) + w2 f2(color) + w3 f3(moisture); no normalization."""
    return (_basis(reward_function["shapeComponent"], shape)
            + _basis(reward_function["colorComponent"], color)
            + _basis(reward_function["moistureComponent"], moisture))


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

class Terrain:
    def __init__(self, params, moisture_noise, boundary_noise, ridge_noise=None, rock_noise=None, snow_noise=None):
        self.p = params
        self._moisture_noise = moisture_noise
        self._boundary_noise = boundary_noise
        self._ridge_noise = ridge_noise
        self._rock_noise = rock_noise
        self._snow_noise = snow_noise

    @staticmethod
    def from_seed(params, seed):
        rngs = [np.random.default_rng(c) for c in np.random.SeedSequence(int(seed)).spawn(8)]
        return Terrain(params, Perlin(rngs[0]), Perlin(rngs[1]), Perlin(rngs[5]), Perlin(rngs[6]), Perlin(rngs[7]))

    def moisture(self, x, z):
        """TerrainManager.ComputeMoisture: octave sum of noise at frequency * 0.01."""
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
              "terrainMaxElevation", "mountainBandWidth", "mountainBoundaryJitter", "mountainHeight",
              "mountainNoiseScale", "snowLineFraction", "treeSpacing", "placementJitter", "startClearingRadius",
              "treeEdgeMargin", "fruitCount", "rewardStd"]
REWARD_PARTS = ["shape", "color", "moisture"]
WORLD_MAGIC = b"FWLD"
WORLD_VERSION = 1
GRID_NAMES = ["moisture", "elevation", "rock", "snow", "ramp"]


def check_values(params):
    """{name: value} of the parameters a world depends on (see CHECK_KEYS)."""
    out = {k: float(getattr(params, _snake(k))) for k in CHECK_KEYS}
    for part in REWARD_PARTS:
        comp = params.reward_function[part + "Component"]
        for field in ("basisFunctionType", "weight", "peak", "width"):
            out[f"reward.{part}.{field}"] = float(comp[field])
    return out


def unity_world_path(session, seed, out_dir=None):
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "Assets" / "StreamingAssets" / "Worlds"
    return out_dir / f"{session}_seed{seed}.world"


def export_unity(world, path):
    """Write the world in the binary format Unity's WorldData.Load reads.

    Layout: b"FWLD", uint32 version, uint32 header length, UTF-8 JSON header, then one float32 little-endian
    array per name in header["grids"], each res*res values flattened as i*res + j (i across x, j across z).
    The header holds the bushes (flat arrays) and the parameter echo used for staleness checks.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    grids = world.terrain.grids()
    res = grids["moisture"].shape[0]
    checks = check_values(world.params)
    header = {
        "version": WORLD_VERSION,
        "session": world.params.session_name,
        "seed": int(world.seed),
        "res": int(res),
        "halfExtent": float(world.params.world_half_extent),
        "treeCount": int(world.n),
        "fruitCount": int(world.fruit_count),
        "grids": GRID_NAMES,
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
    blob = json.dumps(header, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f:
        f.write(WORLD_MAGIC)
        f.write(struct.pack("<II", WORLD_VERSION, len(blob)))
        f.write(blob)
        for name in GRID_NAMES:
            f.write(np.ascontiguousarray(grids[name], dtype="<f4").tobytes())


def read_unity_world(path):
    """Reader for the export_unity format (used by tests). Returns (header dict, {grid name: (res, res) array})."""
    with open(path, "rb") as f:
        if f.read(4) != WORLD_MAGIC:
            raise ValueError("not a world file")
        version, n = struct.unpack("<II", f.read(8))
        header = json.loads(f.read(n).decode("utf-8"))
        res = header["res"]
        grids = {name: np.frombuffer(f.read(res * res * 4), dtype="<f4").reshape(res, res)
                 for name in header["grids"]}
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


def generate_world(params, seed):
    """Build the world for (params, seed). `params` is a namespace from load_session()."""
    rngs = [np.random.default_rng(c) for c in np.random.SeedSequence(int(seed)).spawn(8)]
    terrain = Terrain(params, Perlin(rngs[0]), Perlin(rngs[1]), Perlin(rngs[5]), Perlin(rngs[6]), Perlin(rngs[7]))

    pos = _lattice_sites(params, terrain, rngs[2])
    n = len(pos)

    shape = rngs[3].uniform(0.0, 1.0, n)
    color = rngs[3].uniform(0.0, 1.0, n)
    moisture = terrain.moisture(pos[:, 0], pos[:, 1])

    # Tree.ApplyAttributes: canopy is a sphere scaled (sx, sy, sx); radius = max horizontal scale / 2.
    lo, hi = params.shape_range
    t = np.clip((shape - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    w_lo, w_hi = params.canopy_width_range
    canopy_radius = (w_hi + (w_lo - w_hi) * t) * 0.5

    value = bush_value(params.reward_function, shape, color, moisture)

    # HarvestManager.CollectNextFruit: max(0, round(R_bush + N(0, std))), independent per fruit.
    fruit_count = int(params.fruit_count)
    noise = rngs[4].standard_normal((n, fruit_count)) * float(params.reward_std)
    fruit_reward = np.maximum(0, np.rint(value[:, None] + noise)).astype(np.int32)

    return World(params=params, seed=int(seed), pos=pos, shape=shape, color=color, moisture=moisture,
                 canopy_radius=canopy_radius, value=value, fruit_reward=fruit_reward,
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
                    "Assets/StreamingAssets/Worlds for --unity)")
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
                path = out / f"{session}_seed{seed}.npz"
                world.save(path)
            print(f"{path.name}: {world.n} bushes")


if __name__ == "__main__":
    main()
