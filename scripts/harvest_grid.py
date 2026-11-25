"""A 3x3 selection grid built from the participant's own recent harvests, tested on simulated foragers.

`grid_from_harvests` turns the last `n` harvests into an axis-aligned, evenly spaced 3x3 grid (shape across, colour up):

  * the spacing along each axis is `k` (above 1) times the variance of the harvested values along it (the standard deviation and the interquartile range are options): similar harvests give a
    small grid, diverse ones a wide one, a sample spread along one axis stretches the grid along it, and a larger k reaches beyond the sampled range (generalisation); a small sample is
    shrunk toward the broad grid; the spacing is clamped between `s_min` and `s_max`;
  * the middle of the grid is the recency-weighted mean of the harvests plus a random jitter of up to `jitter` spacings along each axis (0 = centred on the mean);
  * (optional, off by default) a probe: *widen* or *extrapolate* along the direction in which the participant's own rewards rose.

The module also holds the simulation that checks it: simulated foragers (`agents.REGISTRY`: oracle, learner, softmax, curious, nearest) forage a session's worlds; a selection is due at
every patch leaving (as in the game); the grid is built from the harvests so far. `rules` draws the first four grids of one forager, one row per placement rule; `table` compares the rules
over all foragers and worlds (spacing, share of windows clamped at the maximum, share of cells outside the range of the harvests, cells near a harvest, best cell, middle cell best,
coverage of the high-value region).

    harvest_grid.py rules PSC_S1 [--agent learner] [--n 8] [--out file.png]
    harvest_grid.py table PSC_S1 [--seeds 8] [--n 8] [--txt file.txt]

Not an engine file; nothing here is read by the game.
"""

import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import adaptive_grid_sim as ag
import agents
import sim

DOCS = Path(__file__).resolve().parent.parent / "docs" / "pilots"
S_MAX = ag.S_MAX
OFFS = ag.OFFS
KINDS = ("oracle", "learner", "softmax", "curious", "nearest")


# --------------------------------------------------------------------------------------------------
# The heuristic
# --------------------------------------------------------------------------------------------------

def weighted_quantile(values, weights, q):
    order = np.argsort(values)
    v, w = np.asarray(values)[order], np.asarray(weights)[order]
    cum = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, cum, v))


def robust_spread(values, weights=None):
    """The spread of `values` as a standard deviation: the interquartile range over 1.35 (a stray harvest does not widen it); weighted when `weights` are given."""
    if len(values) < 2:
        return 0.0
    if weights is None:
        weights = np.ones(len(values))
    q1, q3 = weighted_quantile(values, weights, 0.25), weighted_quantile(values, weights, 0.75)
    return float((q3 - q1) / 1.35)


def reward_direction(features, rewards):
    """The unit direction in (shape, colour) in which the harvested rewards rise (least-squares slope), or None when there are too few harvests or the slope is flat."""
    if len(features) < 4:
        return None
    x = features - features.mean(axis=0)
    if np.linalg.matrix_rank(x) < 2:
        return None
    slope = np.linalg.lstsq(x, rewards - rewards.mean(), rcond=None)[0]
    norm = float(np.hypot(*slope))
    return None if norm < 1e-6 else slope / norm


def grid_from_harvests(features, rewards, s_min, rng, *, k=(1.5, 1.5), jitter=1.0, spread="sd", s_max=S_MAX, prior_n=3.0, recency=0.9, reward_power=0.0,
                       probe=None, widen=2.0, shift=2.0, unit_offset=None):
    """features (m, 2) harvested (shape, colour) from the oldest to the newest; rewards (m,) the reward per fruit of each. Returns a dict: centre, mean, sx, sy, kind.

    The grid is evenly spaced and axis-aligned, its spacing along axis a is k[a] times the dispersion of the harvests along it (`spread` "var": the variance; "sd": the standard
    deviation; "iqr": the interquartile range over 1.35). With "sd" a grid reaches k standard deviations each side of its middle, but the harvests of a forager spread over the square have a
    standard deviation of about 0.28, so every k above 1.2 is clamped at the maximum; with "var" (about 0.08 for such a sample) k = 3 gives a spacing of about 0.24 and the spacing falls
    much faster as the harvests get similar. A small sample is shrunk toward the broad grid (`prior_n` pseudo-harvests at the maximum spacing); the spacing is clamped between `s_min` and `s_max`.
    The middle of the grid is the recency-weighted mean of the harvests plus a random jitter of up to `jitter` spacings along each axis (`unit_offset`, two numbers in -1..1, replaces the draw)."""
    m = len(features)
    s_prior = s_max / max(k)
    if m == 0:
        mean, sd = np.array([0.5, 0.5]), np.array([s_prior, s_prior])
    else:
        w = recency ** np.arange(m - 1, -1, -1)
        if reward_power > 0.0:                                         # the region where the points came from: each harvest counts as its reward to this power (the participant's own data)
            w = w * np.maximum(rewards, 1e-3) ** reward_power
        mean = (features * w[:, None]).sum(axis=0) / w.sum()
        var = (w[:, None] * (features - mean) ** 2).sum(axis=0) / w.sum()
        if spread == "iqr":
            raw = np.array([robust_spread(features[:, 0], w), robust_spread(features[:, 1], w)])
        elif spread == "var":
            raw = var                                                  # the variance itself (feature units squared: about 0.08 for a sample spread over the square)
        else:
            raw = np.sqrt(var)
        sd = (m * raw + prior_n * s_prior) / (m + prior_n)               # shrunk toward the broad grid while the sample is small
    sx, sy = (float(np.clip(k[a] * sd[a], s_min, s_max)) for a in (0, 1))
    centre, kind = mean.copy(), "normal"
    if probe == "widen":
        sx, sy, kind = min(s_max, sx * widen), min(s_max, sy * widen), "widen"
    elif probe == "extrapolate":
        d = reward_direction(features, rewards) if m else None
        if d is None:
            ang = rng.uniform(0.0, 2.0 * math.pi)
            d = np.array([math.cos(ang), math.sin(ang)])
        centre = centre + shift * np.array([sx, sy]) * d
        kind = "extrapolate"
    if probe in (None, "widen"):                                      # (an extrapolation probe is already shifted; the others get the jitter so the middle cell is not the best)
        u = rng.uniform(-1.0, 1.0, 2) if unit_offset is None else np.asarray(unit_offset, dtype=float)
        centre = centre + jitter * u * np.array([sx, sy])
    return {"centre": centre, "mean": mean, "sx": sx, "sy": sy, "kind": kind}


def cells_of(grid):
    s = np.array([grid["sx"], grid["sy"]])
    centre = np.clip(grid["centre"], ag.MARGIN + s, 1.0 - ag.MARGIN - s)
    return centre + OFFS * s


# --------------------------------------------------------------------------------------------------
# Simulation on foraging agents
# --------------------------------------------------------------------------------------------------

def forage(kind, world):
    """One simulated session: the harvest visits in order as (bush, tile, reward per fruit)."""
    result = sim.run_episode(agents.REGISTRY[kind](), world)
    tiles = world.terrain.tiles
    visits = []
    for bush, fruits, reward in result.trace:
        if fruits > 0:
            x, z = world.pos[bush]
            i, j = tiles.nearest(x, z)
            visits.append((int(bush), (int(i), int(j)), float(reward) / fruits))
    return visits


def selection_times(visits):
    """Indices (counts of visits so far) at which a selection falls due: the visit after which the next one is in another patch."""
    return [i + 1 for i in range(len(visits) - 1) if visits[i][1] != visits[i + 1][1]]


def window(visits, count, n, patches):
    """The visits the grid is built from: the last `n`, or those of the last `patches` patches when `patches` > 0."""
    seen = visits[:count]
    if patches > 0:
        tiles, keep = [], []
        for v in reversed(seen):
            if v[1] not in tiles:
                if len(tiles) == patches:
                    break
                tiles.append(v[1])
            keep.append(v)
        return keep[::-1]
    return seen[-n:]


RULES = [("variance x 3, centred on the mean", dict(spread="var", k=(3.0, 3.0), jitter=0.0)),
         ("variance x 3, jitter up to 1 spacing", dict(spread="var", k=(3.0, 3.0), jitter=1.0)),
         ("variance x 3, jitter up to 2 spacings", dict(spread="var", k=(3.0, 3.0), jitter=2.0)),
         ("variance x 5, jitter up to 1 spacing", dict(spread="var", k=(5.0, 5.0), jitter=1.0)),
         ("SD x 1.5, jitter up to 1 spacing", dict(spread="sd", k=(1.5, 1.5), jitter=1.0))]


def grid_record(world0, visits, count, n, rng, options, probe=None):
    """The grid for the selection after `count` harvests, with what it shows."""
    w = world0.sim_world
    recent = window(visits, count, n, 0)
    feats = np.array([[w.shape[b], w.color[b]] for b, _, _ in recent]) if recent else np.empty((0, 2))
    rews = np.array([x for _, _, x in recent])
    grid = grid_from_harvests(feats, rews, world0.s_min, rng, probe=probe, **options)
    cells = cells_of(grid)
    values = world0.value(cells)
    near = np.sqrt(((cells[:, None, :] - feats[None, :, :]) ** 2).sum(-1)).min(axis=1) if len(feats) else np.full(9, np.nan)
    inside = np.all((cells >= feats.min(axis=0) - 1e-9) & (cells <= feats.max(axis=0) + 1e-9), axis=1) if len(feats) else np.zeros(9, dtype=bool)
    return {"grid": grid, "cells": cells, "feats": feats, "values": values, "near": float((near <= 0.12).mean()) if len(feats) else np.nan,
            "outside": float((~inside).mean()), "middle_best": float(int(np.argmax(values)) == 4), "best_value": float(values.max() / world0.vmax),
            "clamped": float(max(grid["sx"], grid["sy"]) >= S_MAX - 1e-9), "sx": grid["sx"], "sy": grid["sy"], "n_recent": len(recent)}


def worlds_for(session, seeds):
    world0 = ag.World(session)
    base = int(world0.params.world_seed)
    return world0, sim.get_worlds(session, [base + k for k in range(seeds)])


def table(session, seeds, n, kinds=KINDS, rng_seed=20261124):
    world0, worlds = worlds_for(session, seeds)
    axis = np.linspace(0, 1, 61)
    G = np.array([(a, b) for a in axis for b in axis])
    region = G[world0.value(G) >= 0.5 * world0.vmax]
    histories = [(kind, w, forage(kind, w)) for w in worlds for kind in kinds]
    lines = [f"{session}: last {n} harvests; s_min {world0.s_min:.3f}, s_max {S_MAX:.3f}; {len(worlds)} worlds x {len(kinds)} foragers; windows of selections 3 and later", ""]
    lines.append(f"{'rule':40s} spacing  clamped  outside  near  best/peak  middle  region coverage")
    per_kind = {}
    for label, options in RULES:
        rng = np.random.default_rng(rng_seed)
        recs, covers = [], []
        for kind, w, visits in histories:
            world0.sim_world = w
            run = [grid_record(world0, visits, count, n, rng, options) for count in selection_times(visits)]
            recs += run[2:]
            per_kind.setdefault((label, kind), []).extend((x["sx"] + x["sy"]) / 2 for x in run[2:])
            if run:
                cells = np.vstack([x["cells"] for x in run])
                covers.append(np.sqrt(((region[:, None, :] - cells[None, :, :]) ** 2).sum(-1)).min(axis=1).mean())
        lines.append(f"{label:40s} {np.mean([(x['sx'] + x['sy']) / 2 for x in recs]):.3f}    {np.mean([x['clamped'] for x in recs]):.2f}     {np.mean([x['outside'] for x in recs]):.2f}    "
                     f"{np.nanmean([x['near'] for x in recs]):.2f}   {np.mean([x['best_value'] for x in recs]):.2f}       {np.mean([x['middle_best'] for x in recs]):.2f}    {np.mean(covers):.3f}")
    lines += ["", "spacing by forager (selections 3 and later)", f"{'rule':40s}" + "".join(f"{k:>10s}" for k in kinds)]
    for label, _ in RULES:
        lines.append(f"{label:40s}" + "".join(f"{np.mean(per_kind[(label, k)]):10.3f}" for k in kinds))
    return "\n".join(lines)


def rules_figure(session, agent, n, selections=4, seed_index=0, rng_seed=7):
    """One row per placement rule, the first `selections` grids of one forager in columns: the value map, the recent harvests (red x; older ones grey), the sample mean (green +), the grid's
    cells (blue) and the box through its outer cells (dashed); the same random draws in every row, so the rows differ by the rule only."""
    world0, worlds = worlds_for(session, seed_index + 1)
    w = worlds[seed_index]
    world0.sim_world = w
    visits = forage(agent, w)
    times = selection_times(visits)[:selections]
    axis = np.linspace(0, 1, 101)
    field = world0.value(np.stack(np.meshgrid(axis, axis, indexing="ij"), axis=-1))
    fig, axes = plt.subplots(len(RULES), selections, figsize=(4.0 * selections, 4.0 * len(RULES)), layout="constrained", squeeze=False)
    for row, (label, options) in enumerate(RULES):
        for col, count in enumerate(times):
            recent = window(visits, count, n, 0)
            feats = np.array([[w.shape[b], w.color[b]] for b, _, _ in recent])
            rews = np.array([x for _, _, x in recent])
            u = np.random.default_rng([rng_seed, col]).uniform(-1.0, 1.0, 2)
            g = grid_from_harvests(feats, rews, world0.s_min, None, unit_offset=u, **options)
            cells = cells_of(g)
            ax = axes[row, col]
            ax.imshow(field.T, origin="lower", extent=(0, 1, 0, 1), cmap="Greys", vmin=0, vmax=world0.vmax * 1.05)
            older = [(w.shape[b], w.color[b]) for b, _, _ in visits[:count][:-n]]
            if older:
                ax.plot(*zip(*older), "x", color="#aaaaaa", markersize=5)
            ax.plot(*feats.T, "x", color="#cc0000", markersize=7, markeredgewidth=2)
            ax.plot(*g["mean"], "+", color="#2ca02c", markersize=14, markeredgewidth=2.5)
            ax.plot(*cells.T, "o", color="#1f77b4", markersize=7)
            lo, hi = cells.min(axis=0), cells.max(axis=0)
            ax.plot([lo[0], hi[0], hi[0], lo[0], lo[0]], [lo[1], lo[1], hi[1], hi[1], lo[1]], "--", color="#1f77b4", linewidth=1)
            ax.plot(*world0.peak, "*", color="gold", markeredgecolor="black", markersize=14)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_title(f"selection {col + 1}: {len(feats)} harvests in the window\nspacing {g['sx']:.2f} x {g['sy']:.2f}", fontsize=9)
            if col == 0:
                ax.set_ylabel(label + "\ncolour", fontsize=9)
            if row == len(RULES) - 1:
                ax.set_xlabel("shape")
    fig.suptitle(f"{session}, forager '{agent}': grids from the last {n} harvests (red x; older grey; green +: their mean; star: the peak; blue: the grid)")
    return fig


def main():
    ap = argparse.ArgumentParser(description="A selection grid built from recent harvests, on simulated foragers.")
    ap.add_argument("mode", choices=["rules", "table"])
    ap.add_argument("session")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--agent", default="learner")
    ap.add_argument("--out", default=None)
    ap.add_argument("--txt", default=None)
    args = ap.parse_args()
    if args.mode == "table":
        report = table(args.session, args.seeds, args.n)
        print(report)
        if args.txt:
            Path(args.txt).write_text(report + "\n")
        return
    out = Path(args.out) if args.out else DOCS / f"{args.session}_harvest_grid_rules.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    rules_figure(args.session, args.agent, args.n).savefig(out, dpi=90)
    print(out)


if __name__ == "__main__":
    main()
