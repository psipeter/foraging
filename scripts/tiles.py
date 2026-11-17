"""Hexagonal tiles: the terrain, the bush layout and the feature assignment of the tiles world (`layout = "tiles"`; SessionConfig, "Tiles").

The valley is cut into regular hexagonal tiles. Each tile is a plateau at its own ground level (a moisture value, so its colour and height), with a short ramp to its
neighbours; a tight cluster of bushes sits in the middle of it, and the walk from a tile's edge to the cluster is the cost of going there. The ground level is drawn on its own stream
and never depends on what the tile's bushes pay (a later option may make it a cue).

The bushes' features come in two steps (see "Assignment" below). First the world's POOL of bushes: as many points of the (shape, colour) plane as there are bush sites, an even cover of the
plane (scrambled Halton), so the function is learnable wherever the bushes are and the world's distribution of bush values is the value map's own. Second a PLACEMENT, which deals the pool's bushes to
the sites of the tiles and changes nothing else; checks on the result (a neighbourhood of tiles must span enough of the plane, the tiles around the start must differ enough) redraw it. `stats` reports
what a world realised (tile contrast, spatial and bush sparsity). Tables of methods, so a new one is one entry:

    ARRANGEMENTS    where the bushes lie inside a tile: `random` (a minimum spacing)
    PLACEMENTS      how the pool is dealt to the tiles: `random` (the others of earlier versions, which chose the tiles' centres and scattered the bushes around them, were removed 2026-11-18)

The tile of a bush is found again from its position (`TileGrid.nearest`), so the bush table needs no tile column. Random streams (world.py's list): 17 the grid (rotation, ground levels), 18 the
clusters, 19 the assignment.
"""

import math

import numpy as np

SQRT3 = math.sqrt(3.0)
TILE_PARAMS = ("tile_radius", "tile_ramp_width", "tile_moisture_levels", "tile_bushes", "tile_cluster_radius", "tile_cluster_spacing", "tile_coverage_min", "tile_start_spread_min")
CLUSTER_MARGIN = 5.0              # world units: a cluster (plus this) must lie inside the valley
RELAX_STEPS = 500                 # pushes `arrange_random` makes in one try
REPAIR_PASSES = 20                # passes that give a tile sharing its level with a neighbour another one
RELAX_TRIES = 30                  # fresh starts it makes before it gives up on a cluster
NEIGHBOURS = ((0, 0), (1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))      # a tile and its six neighbours, in lattice steps (the lattice basis is 60 degrees apart)


class TileGrid:
    """The hexagonal lattice of tiles of one world: geometry, ground levels, the nearest tile of a point and the ground level at a point."""

    def __init__(self, params, rng):
        self.radius = float(params.tile_radius)
        self.ramp = max(float(params.tile_ramp_width), 1e-3)
        if self.radius <= 0.0:
            raise ValueError("tile_radius must be positive")
        self.pitch = SQRT3 * self.radius                     # centre to centre of neighbouring tiles
        self.apothem = 0.5 * self.pitch                      # centre to the middle of an edge
        self.tau = self.ramp / 6.0                           # a logistic step: 5% to 95% over the ramp width
        self.cluster_radius = float(params.tile_cluster_radius)
        if self.cluster_radius > self.apothem - self.ramp / 2.0:
            raise ValueError(f"tile_cluster_radius {self.cluster_radius} does not fit the plateau (at most {self.apothem - self.ramp / 2.0:.1f} for tile_radius {self.radius}, tile_ramp_width {self.ramp})")
        angle = rng.uniform(0.0, math.pi / 3.0)
        self.a = self.pitch * np.array([math.cos(angle), math.sin(angle)])
        self.b = self.pitch * np.array([math.cos(angle + math.pi / 3.0), math.sin(angle + math.pi / 3.0)])
        self.det = self.a[0] * self.b[1] - self.a[1] * self.b[0]
        # the start (0, 0), the middle of the world, is the corner where tiles (0, 0), (1, 0) and (0, 1) meet (the centre of the triangle of their centres): the three nearest clusters
        # are one circumradius away and the first walk is the same in every world
        self.origin = -(self.a + self.b) / 3.0
        half = float(params.world_half_extent)
        self.k = int(math.ceil(2.0 * half / self.pitch)) + 2
        self.levels = self._draw_levels(int(params.tile_moisture_levels), rng)

    # ---- geometry --------------------------------------------------------------------------------

    def centre(self, i, j):
        i, j = np.asarray(i, dtype=float), np.asarray(j, dtype=float)
        return np.stack([self.origin[0] + i * self.a[0] + j * self.b[0], self.origin[1] + i * self.a[1] + j * self.b[1]], axis=-1)

    def nearest(self, x, z):
        """The lattice indices (i, j) of the tile whose centre is nearest to each point (arrays of the points' shape)."""
        x, z = np.asarray(x, dtype=float), np.asarray(z, dtype=float)
        px, pz = x - self.origin[0], z - self.origin[1]
        u = (px * self.b[1] - pz * self.b[0]) / self.det
        v = (-px * self.a[1] + pz * self.a[0]) / self.det
        iu, iv = np.floor(u), np.floor(v)
        best_i, best_j, best = None, None, None
        for di, dj in ((0, 0), (1, 0), (0, 1), (1, 1)):      # the corners of the lattice cell holding the point: one of them is the nearest centre
            c = self.centre(iu + di, iv + dj)
            d2 = (c[..., 0] - x) ** 2 + (c[..., 1] - z) ** 2
            if best is None:
                best_i, best_j, best = iu + di, iv + dj, d2
            else:
                better = d2 < best
                best_i, best_j, best = np.where(better, iu + di, best_i), np.where(better, iv + dj, best_j), np.where(better, d2, best)
        return best_i.astype(int), best_j.astype(int)

    def tile_centres(self):
        """[(i, j, (x, z))] of every tile of the lattice range, in index order."""
        r = range(-self.k, self.k + 1)
        return [(i, j, self.centre(i, j)) for i in r for j in r]

    # ---- ground levels ---------------------------------------------------------------------------

    def _draw_levels(self, count, rng):
        """The ground level (moisture, 0 to 1) of every tile of the lattice range, an array [i + k, j + k]. With `count` >= 2 the levels are the evenly spaced values and a tile avoids those
        its already-drawn neighbours have (tiles in a random order), and a repair pass follows, so neighbouring tiles differ and the tile edges show; with 0 each tile draws a continuous level, redrawn a few times to
        stay at least 0.15 from its neighbours'."""
        n = 2 * self.k + 1
        levels = np.full((n, n), np.nan)
        values = np.linspace(0.0, 1.0, count) if count >= 2 else None
        for flat in rng.permutation(n * n):
            i, j = divmod(int(flat), n)
            near = [levels[i + di, j + dj] for di, dj in NEIGHBOURS[1:] if 0 <= i + di < n and 0 <= j + dj < n]
            near = np.array([v for v in near if not np.isnan(v)])
            if values is not None:
                counts = np.array([np.sum(np.isclose(near, v)) for v in values])
                levels[i, j] = rng.choice(values[counts == counts.min()])
            else:
                for _ in range(20):
                    draw = rng.uniform(0.0, 1.0)
                    if near.size == 0 or np.min(np.abs(near - draw)) >= 0.15:
                        break
                levels[i, j] = draw
        if values is not None:                                # repair: a tile that still shares its level with a neighbour takes a level few of its neighbours have (min-conflicts)
            for _ in range(REPAIR_PASSES):
                moved = False
                for flat in rng.permutation(n * n):
                    i, j = divmod(int(flat), n)
                    near = np.array([levels[i + di, j + dj] for di, dj in NEIGHBOURS[1:] if 0 <= i + di < n and 0 <= j + dj < n])
                    counts = np.array([np.sum(np.isclose(near, v)) for v in values])
                    if counts[np.argmin(np.abs(values - levels[i, j]))] > 0:
                        levels[i, j] = rng.choice(values[counts == counts.min()])
                        moved = True
                if not moved:
                    break
        return levels

    def moisture(self, x, z):
        """The ground level at each point: the tile's own on its plateau, a logistic ramp of width `tile_ramp_width` across each edge. The weight of each of the nearest tile and its six
        neighbours falls as exp(-(d^2 - d_nearest^2) / (2 * pitch * tau)), which is exp(-distance from the bisector / tau), so the level is continuous everywhere, vertices included."""
        x, z = np.asarray(x, dtype=float), np.asarray(z, dtype=float)
        i0, j0 = self.nearest(x, z)
        d2, lev = [], []
        for di, dj in NEIGHBOURS:
            i, j = i0 + di, j0 + dj
            c = self.centre(i, j)
            d2.append((c[..., 0] - x) ** 2 + (c[..., 1] - z) ** 2)
            lev.append(self.levels[np.clip(i + self.k, 0, 2 * self.k), np.clip(j + self.k, 0, 2 * self.k)])
        d2, lev = np.stack(d2), np.stack(lev)
        w = np.exp(-(d2 - d2.min(axis=0)) / (2.0 * self.pitch * self.tau))
        return (w * lev).sum(axis=0) / w.sum(axis=0)


# --------------------------------------------------------------------------------------------------
# Layout: where the bushes lie
# --------------------------------------------------------------------------------------------------

def arrange_random(rng, n, radius, min_spacing):
    """`n` offsets in a disc of `radius`, no two closer than `min_spacing`: uniform points, then pairs that are too close pushed apart (and back into the disc) until none is, from a fresh
    start when a try jams (plain rejection jams on a dense cluster); raises when no try fits."""
    for _ in range(RELAX_TRIES):
        r, phi = radius * np.sqrt(rng.uniform(size=n)), rng.uniform(0.0, 2.0 * math.pi, n)
        p = np.stack([r * np.cos(phi), r * np.sin(phi)], axis=1)
        for _ in range(RELAX_STEPS):
            diff = p[:, None, :] - p[None, :, :]
            dist = np.sqrt((diff ** 2).sum(-1)) + np.eye(n) * 1e9
            if dist.min() >= min_spacing:
                return p
            push = np.where(dist < min_spacing, (min_spacing - dist) / (2.0 * dist) * 1.02, 0.0)[..., None] * diff
            p = p + push.sum(axis=1)
            norm = np.hypot(p[:, 0], p[:, 1])
            p = p * np.minimum(1.0, radius / np.maximum(norm, 1e-9))[:, None]
    raise ValueError(f"{n} bushes do not fit a cluster of radius {radius} with spacing {min_spacing}")


ARRANGEMENTS = {"random": arrange_random}


def _in_valley(terrain, centre, radius):
    angles = np.linspace(0.0, 2.0 * math.pi, 8, endpoint=False)
    xs = np.concatenate([[centre[0]], centre[0] + radius * np.cos(angles)])
    zs = np.concatenate([[centre[1]], centre[1] + radius * np.sin(angles)])
    return bool(np.all(terrain.is_tree_site(xs, zs)))


def layout_tiles(params, terrain, rngs):
    """Bush positions: a cluster in the middle of every tile whose cluster disc (plus a margin) lies inside the valley (stream 18; tiles in index order)."""
    grid = terrain.tiles
    arrange = ARRANGEMENTS[getattr(params, "tile_arrangement", None) or "random"]
    n, spacing = int(params.tile_bushes), float(params.tile_cluster_spacing)
    sites = []
    for _, _, c in grid.tile_centres():
        if _in_valley(terrain, c, grid.cluster_radius + CLUSTER_MARGIN):
            sites.append(c + arrange(rngs[18], n, grid.cluster_radius, spacing))
    return np.concatenate(sites).reshape(-1, 2)


# --------------------------------------------------------------------------------------------------
# Assignment: which features the bushes have
# --------------------------------------------------------------------------------------------------
# Step 1, the pool: an even cover of the feature plane, one point per bush site (`bush_pool`). Step 2, the placement: which pool bush goes to which site (`PLACEMENTS`, `tile_placement`,
# default `random`: the pool in random order, so a tile's bushes tell nothing about the tile and the tiles are about equally valuable). A placement is a permutation of the pool: it never changes
# which bushes exist. Checks on the finished placement (a neighbourhood of tiles must span enough of the plane, the tiles around the start must differ enough) redraw it until they hold.

GOOD_OF_MAX = 0.7                 # a bush or tile is "good" when it pays at least this share of the best (the sparsity definition of the RW design)
COVERAGE_CELLS = 4                # the feature plane is cut into this many cells per axis to measure how much of it a neighbourhood spans
MAX_ATTEMPTS = 200                # redraws of the assignment before a constraint is declared unsatisfiable
PLANE_SAMPLE = 20000              # points of the feature plane the reward's range is estimated with


class TileSet:
    """What the modes see of a world's tiles: for each tile with a cluster its lattice index, its centre, the tiles beside it that also have one, and for each bush the tile it is in and its offset
    from the tile's centre; `start` are the tiles that meet at the start (those of the three with a cluster)."""

    def __init__(self, grid, pos):
        i, j = grid.nearest(pos[:, 0], pos[:, 1])
        key = i * 1_000_003 + j
        keys, first, self.tile_of = np.unique(key, return_index=True, return_inverse=True)
        self.n_tiles = len(keys)
        self.i, self.j = i[first], j[first]
        self.centres = grid.centre(self.i, self.j)
        number = {int(k): t for t, k in enumerate(keys)}
        self.neighbours = [np.array([number[k] for di, dj in NEIGHBOURS[1:] if (k := int((self.i[t] + di) * 1_000_003 + self.j[t] + dj)) in number], dtype=int) for t in range(self.n_tiles)]
        self.offsets = pos - self.centres[self.tile_of]
        self.start = np.flatnonzero(np.hypot(self.centres[:, 0], self.centres[:, 1]) <= grid.radius * 1.001)       # the corner of three tiles: their centres are a circumradius away


def _p(params, name, default):
    value = getattr(params, name, None)
    return default if value is None else value


def _plane_values(params, rng, reward, n=PLANE_SAMPLE):
    """(points of the feature plane, the reward at each) for `n` uniform points."""
    c = rng.uniform(0.0, 1.0, (n, 2))
    return c, np.asarray(reward(params.reward_function, c[:, 0], c[:, 1]), dtype=float)


def bush_pool(n, rng):
    """The world's pool: `n` points of the (shape, colour) plane, a scrambled Halton sequence (an even cover)."""
    from scipy.stats import qmc
    return qmc.Halton(d=2, scramble=True, seed=rng).random(n)


def place_random(params, ts, pool, rng, reward):
    """The pool in random order over the sites."""
    return pool[rng.permutation(len(pool))]


PLACEMENTS = {"random": place_random}


def plane_range(params, reward):
    """(lowest, highest) reward over the feature plane, estimated on a fixed sample (the same for a given reward function)."""
    _, v = _plane_values(params, np.random.default_rng(12345), reward)
    return float(v.min()), float(v.max())


def neighbourhood_coverage(ts, features):
    """The smallest share of the feature plane (cut into COVERAGE_CELLS squared cells) that the bushes of a tile together with its neighbours span, over the tiles with all six neighbours."""
    cell = np.minimum((features * COVERAGE_CELLS).astype(int), COVERAGE_CELLS - 1)
    code = cell[:, 0] * COVERAGE_CELLS + cell[:, 1]
    shares = []
    for t in range(ts.n_tiles):
        if len(ts.neighbours[t]) == 6:
            members = np.isin(ts.tile_of, np.concatenate([[t], ts.neighbours[t]]))
            shares.append(len(np.unique(code[members])) / COVERAGE_CELLS ** 2)
    return min(shares) if shares else 1.0


def start_spread(params, ts, features, reward):
    """How different the tiles that meet at the start are: the range of their mean reward as a share of the reward's range over the plane."""
    if len(ts.start) < 2:
        return 0.0
    v = np.asarray(reward(params.reward_function, features[:, 0], features[:, 1]), dtype=float)
    means = np.array([v[ts.tile_of == t].mean() for t in ts.start])
    lo, hi = plane_range(params, reward)
    return float((means.max() - means.min()) / max(hi - lo, 1e-9))


def constraints_hold(params, ts, features, reward):
    """The session's checks on a finished assignment (each off at 0): `tile_coverage_min` (neighbourhood_coverage) and `tile_start_spread_min` (start_spread)."""
    cov, spread = float(_p(params, "tile_coverage_min", 0.0)), float(_p(params, "tile_start_spread_min", 0.0))
    return (cov <= 0.0 or neighbourhood_coverage(ts, features) >= cov) and (spread <= 0.0 or start_spread(params, ts, features, reward) >= spread)


def deal_features(params, pos, grid, rng, reward):
    """(shape, colour) of every bush: the world's pool (stream 19), then the placement of the pool over the sites (each attempt draws its own generator from the stream), redrawn until the constraints hold."""
    ts = TileSet(grid, pos)
    pool = bush_pool(len(pos), np.random.default_rng(int(rng.integers(2 ** 62))))
    place = PLACEMENTS[getattr(params, "tile_placement", None) or "random"]
    for _ in range(MAX_ATTEMPTS):
        features = place(params, ts, pool, np.random.default_rng(int(rng.integers(2 ** 62))), reward)
        if constraints_hold(params, ts, features, reward):
            return features[:, 0], features[:, 1]
    raise ValueError(f"no placement met tile_coverage_min {_p(params, 'tile_coverage_min', 0.0)} and tile_start_spread_min {_p(params, 'tile_start_spread_min', 0.0)} in {MAX_ATTEMPTS} draws")


# --------------------------------------------------------------------------------------------------
# What a built world realises (recorded with an instance, and the covariates of an analysis)
# --------------------------------------------------------------------------------------------------

def stats(params, pos, shape, color, grid, reward):
    """The realised pattern of a world: tiles, the spread of the tiles' mean reward, the mean within-tile reward SD, their ratio (contrast), the share of tiles whose mean pays at least 70% of the best bush
    (spatial sparsity), the share of bushes that do (bush sparsity), the neighbourhood coverage and the start spread."""
    ts = TileSet(grid, pos)
    v = np.asarray(reward(params.reward_function, shape, color), dtype=float)
    means = np.array([v[ts.tile_of == t].mean() for t in range(ts.n_tiles)])
    within = np.array([v[ts.tile_of == t].std(ddof=1) for t in range(ts.n_tiles)])
    best = v.max()
    features = np.stack([shape, color], axis=1)
    return {"n_tiles": int(ts.n_tiles), "tile_value_sd": float(means.std()), "within_sd": float(within.mean()), "contrast": float(means.std() / max(within.mean(), 1e-9)),
            "good_tile_share": float(np.mean(means >= GOOD_OF_MAX * best)), "good_bush_share": float(np.mean(v >= GOOD_OF_MAX * best)),
            "coverage_min": neighbourhood_coverage(ts, features), "start_spread": start_spread(params, ts, features, reward)}
