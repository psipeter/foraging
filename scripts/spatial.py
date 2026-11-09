"""Spatial evenness of the reward over the map: metrics, a tile-balanced assignment and swap optimisation.

Bush attributes are drawn independently of position, so with about 700 bushes the rewarding ones cluster by chance, and a participant who happens onto a rich cluster
can exhaust it. This module measures how patchy a world's bush values are, at several spatial scales, and can rearrange which bush has which (shape, colour) record so that
the values are more even at those scales. Nothing about the reward function or the set of attribute values changes: the records are only dealt to other positions, so
the marginal distribution of every attribute and of the reward is exactly what the independent draw gave. It is a switch on the session (`SessionConfig.spatialBalance`:
Off, Tiles, TilesAndSwaps; Off, the default, draws as before and every existing world is unchanged), used by `world.generate_world`.

Scales (`SCALES`, world units) are the side of a tile and the diameter of a disk: 40, 60 and 120 (a disk holds about 3, 6 and 24 bushes; the lattice spacing is about 18). Large
scales are left out on purpose (PI, 2026-11-05): the spread of disk means that a random world has is already small there (0.15 of the bushes' own spread at 240 units against 0.44 at 60 and
0.69 at 30), so the evenness that matters to a forager is at the scale of a few neighbouring bushes.

Metrics (`metrics`), for the value of each bush and for the indicator of the top decile (`top`), at each scale:
  * `local_value`, `local_top`: the spread of the means of disks laid on a grid over the valley (centres half a disk apart), divided by the spread a random assignment of the
    same values would give (the finite-population null of a disk of n bushes). 1 = a random world, below 1 = more even, above 1 = patchier. Their squares averaged over scales and
    channels are `cost`, which the swap step minimises.
  * `moran`: Moran's I over the pairs of bushes closer than half a disk (0 = no spatial structure).
  * `top_max`: the most top-decile bushes in one disk, against the `top_expected` of a random world.
  * `cluster`: the largest group of top-decile bushes each within `link` (1.5 lattice spacings) of the next.

`tile_assignment` deals the sorted values hierarchically, coarse tiles first: each tile gets an even interleave of the quantiles, and within it each finer tile does the same,
down to the finest scale, where the order is random. `optimise` then swaps pairs of bushes' records, keeping a swap when `cost` falls, until it reaches `TARGET` or `SWAP_STEPS`.
`balance` runs them as a mode says. All of it draws from one random stream (stream 10 of the world seed), so a world is still determined by its seed.
"""

import numpy as np
from scipy.spatial import cKDTree

SCALES = (40.0, 60.0, 120.0)        # a tile's side and a disk's diameter, world units
TOP_QUANTILE = 0.9                  # the "top" bushes: the best tenth
MIN_IN_DISK = 3                     # a disk with fewer bushes is not used (2 at scales below 60, whose disks hold only a few)
SWAP_STEPS = 40_000
TARGET = 0.4                        # the swap step stops when `cost` (1 for a random world) is at or below this: lower is more even and more regular (neighbours more unlike)
LINK = 34.5                         # the largest gap inside a cluster of top bushes: 1.5 lattice spacings

OFF, TILES, TILES_AND_SWAPS = 0, 1, 2


class Disks:
    """The disks of one scale: members of each disk, and for each bush the disks it is in."""

    def __init__(self, pos, scale, half):
        self.scale, self.radius = float(scale), float(scale) / 2.0
        step = self.radius
        axis = np.arange(-half + step / 2, half, step)
        centres = np.array([(x, z) for x in axis for z in axis])
        found = cKDTree(pos).query_ball_point(centres, self.radius)
        minimum = MIN_IN_DISK if scale >= 60.0 else 2
        keep = [k for k, m in enumerate(found) if len(m) >= minimum]
        self.members = [np.array(found[k], dtype=int) for k in keep]
        self.size = np.array([len(m) for m in self.members], dtype=float)
        self.of_bush = [[] for _ in range(len(pos))]
        for d, m in enumerate(self.members):
            for b in m:
                self.of_bush[b].append(d)
        self.of_bush = [np.array(x, dtype=int) for x in self.of_bush]

    def means(self, v):
        return np.array([v[m].mean() for m in self.members])

    def null_variance(self, v):
        """Variance of a disk's mean under a random assignment of the values, averaged over the disks (finite population)."""
        n = len(v)
        return float(np.mean(v.var(ddof=1) * (n - self.size) / ((n - 1.0) * self.size)))


def top_indicator(v, quantile=TOP_QUANTILE):
    return (v >= np.quantile(v, quantile)).astype(float)


def local_ratio(disks, v):
    """Spread of the disk means over their null spread (1 = random, below 1 = more even)."""
    m = v.mean()
    return float(np.sqrt(np.mean((disks.means(v) - m) ** 2) / disks.null_variance(v)))


def moran(pos, v, distance):
    pairs = cKDTree(pos).query_pairs(distance, output_type="ndarray")
    dev = v - v.mean()
    return float(len(v) / (2 * len(pairs)) * 2 * np.sum(dev[pairs[:, 0]] * dev[pairs[:, 1]]) / np.sum(dev ** 2)) if len(pairs) else 0.0


def largest_cluster(pos, indicator, link=LINK):
    idx = np.flatnonzero(indicator)
    if len(idx) == 0:
        return 0
    pairs = cKDTree(pos[idx]).query_pairs(link, output_type="ndarray")
    parent = list(range(len(idx)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in pairs:
        parent[find(a)] = find(b)
    return int(np.bincount([find(i) for i in range(len(idx))]).max())


def metrics(pos, v, scales=SCALES, half=350.0, disks=None):
    """The evenness metrics of bush values `v` at positions `pos`, per scale, and their `cost` (see the module text)."""
    v = np.asarray(v, dtype=float)
    top = top_indicator(v)
    out, ratios = {}, []
    for s in scales:
        d = disks[s] if disks else Disks(pos, s, half)
        row = {"local_value": local_ratio(d, v), "local_top": local_ratio(d, top), "moran": moran(pos, v, s / 2.0)}
        out[s] = row
        ratios += [row["local_value"] ** 2, row["local_top"] ** 2]
    out["cluster"] = largest_cluster(pos, top)
    out["cost"] = float(np.mean(ratios))
    return out


def tile_assignment(pos, values, rng, scales=SCALES, half=350.0):
    """For each bush the index into `values` of the record it gets: the sorted values dealt coarse tile by tile, each tile an even interleave of the quantiles, random at the finest."""
    pos = np.asarray(pos, dtype=float)
    result = np.empty(len(pos), dtype=int)
    coarse_first = sorted(scales, reverse=True)

    def deal(bushes, records, level):
        if level == len(coarse_first) or len(bushes) <= 1:
            result[bushes] = rng.permutation(records)
            return
        cells = np.floor((pos[bushes] + half) / coarse_first[level]).astype(int)
        _, cell_of = np.unique(cells[:, 0] * 100_000 + cells[:, 1], return_inverse=True)
        sizes = np.bincount(cell_of).astype(float)
        passed = rng.uniform(0.0, 1.0, len(sizes)) / sizes                   # stride scheduling: each cell takes its share of the sorted values in turn
        left = sizes.copy()
        dealt = [[] for _ in sizes]
        for r in records:                                                    # (sorted from the lowest value to the highest)
            k = int(np.argmin(np.where(left > 0, passed, np.inf)))
            dealt[k].append(r)
            passed[k] += 1.0 / sizes[k]
            left[k] -= 1
        for k, got in enumerate(dealt):
            deal(bushes[cell_of == k], np.array(got, dtype=int), level + 1)

    deal(np.arange(len(pos)), np.argsort(values, kind="stable"), 0)
    return result


def optimise(pos, values, rng, scales=SCALES, half=350.0, steps=SWAP_STEPS, target=TARGET, start=None, offset=None):
    """Swap the records of pairs of bushes, keeping a swap when `cost` falls; returns (assignment, final cost). `start` is the assignment to begin from (default: the identity).
    `offset` is an optional reward each site adds to the record it holds (the part of the reward that belongs to the place, such as a moisture term): it is the totals,
    record plus offset, that are made even, and the top bushes are those whose total is in the top decile at the start. None (no offset) is the plain record values."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    index = np.arange(n) if start is None else np.array(start, dtype=int)         # index[i]: the record at bush i
    off = np.zeros(n) if offset is None else np.asarray(offset, dtype=float)
    base = values if offset is None else values[index] + off                         # the totals at the start (by record, without an offset)
    threshold = np.quantile(base, TOP_QUANTILE)
    chans = [base, (base >= threshold).astype(float)]                                 # the two channels, for the null spread and the mean
    disks = [Disks(pos, s, half) for s in scales]
    null = [[d.null_variance(c) for c in chans] for d in disks]

    def channel(ci, record, site):
        """The channel value of a record (index or array) held by a site (index or array)."""
        total = values[record] + off[site]
        return total if ci == 0 else (total >= threshold).astype(float)

    state = []                                                                         # per scale and channel: the disk sums, and the sum of squared deviations of the means
    for d in disks:
        row = []
        for ci in range(2):
            cur = channel(ci, index, np.arange(n))
            sums = np.array([cur[m].sum() for m in d.members])
            row.append(sums)
        state.append(row)
    mean = [c.mean() for c in chans]

    def part(si, ci, sums):
        d = disks[si]
        return float(np.mean((sums / d.size - mean[ci]) ** 2) / null[si][ci])

    total = lambda: float(np.mean([part(si, ci, state[si][ci]) for si in range(len(disks)) for ci in range(2)]))
    cost = total()
    cells = len(disks) * 2
    for _ in range(steps):
        if cost <= target:
            break
        i, j = rng.integers(0, n, 2)
        if i == j or values[index[i]] == values[index[j]]:
            continue
        ri, rj = index[i], index[j]
        change, new_sums = 0.0, []
        for si, d in enumerate(disks):
            affected = np.union1d(d.of_bush[i], d.of_bush[j])
            if len(affected) == 0:
                new_sums.append(None)
                continue
            in_i = np.isin(affected, d.of_bush[i]).astype(float)
            in_j = np.isin(affected, d.of_bush[j]).astype(float)
            per = []
            for ci in range(2):
                delta = (channel(ci, rj, i) - channel(ci, ri, i)) * in_i + (channel(ci, ri, j) - channel(ci, rj, j)) * in_j        # bush i takes j's record and j takes i's
                old = state[si][ci][affected]
                new = old + delta
                size = d.size[affected]
                change += float(np.sum(((new / size - mean[ci]) ** 2 - (old / size - mean[ci]) ** 2)) / len(d.members) / null[si][ci])
                per.append((affected, new))
            new_sums.append(per)
        if change < 0:
            for si, per in enumerate(new_sums):
                if per is None:
                    continue
                for ci, (affected, new) in enumerate(per):
                    state[si][ci][affected] = new
            index[i], index[j] = index[j], index[i]
            cost += change / cells
    return index, cost


def balance(pos, values, rng, mode, scales=SCALES, half=350.0, steps=SWAP_STEPS, target=TARGET, offset=None):
    """The assignment of records to bushes for a spatial-balance mode (OFF: the identity). `offset`: see `optimise` (the swap step only; the tile step deals the records)."""
    n = len(values)
    if mode == OFF:
        return np.arange(n)
    index = tile_assignment(pos, values, rng, scales, half)
    if mode == TILES_AND_SWAPS:
        index, _ = optimise(pos, values, rng, scales, half, steps, target, start=index, offset=offset)
    return index
