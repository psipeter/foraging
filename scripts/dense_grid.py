"""A dense 5x5 selection grid with the true peak on one of its points, zooming in over the session (PI idea, 2026-11-25). One fixed schedule per session: every participant sees the same grids.

The participant harvests the best 5 of the 25 bushes (any order); the score is the summed true value of the 5 against the best 5 of the grid (the payment rule comes later).

How the five grids of a session are chosen (a table and a solver, 2026-11-25):
  1. **Table** (`build_table`, about a second per session). A grid is its shape spacing s, its colour:shape spacing ratio and the peak's index (i, j) (the peak is exactly one grid point). For every selection, every
     spacing on `S_GRID` and every index the table holds: whether the grid fits in the map (all 25 points inside [MARGIN, 1 - MARGIN], a peak on the edge excepted), the count of its points inside the high-value region
     (value at least `REGION` of the peak) and whether the best 5 bushes are all in the peak's row. The ratio rises over the session as (selection / last) ** power from 1 to the session's final ratio (the map's
     own stretch to the power `ASPECT_POWER`, or `SPEC`'s); the solver tries each power in `RATIO_POWERS`.
  2. **Solver** (`solve`, a vectorised beam search over the table). Hard constraints: the grid fits; the count inside never falls and rises by at most `MAX_STEP` points between selections and by at least
     `MIN_RISE` over the session; the first and last counts lie in the session's ranges (`SPEC`, default 4 to 7 and 10 to 13 of 25, that is 16 to 28% and 40 to 52%); the geometric-mean spacing never grows, falls by at most 30% per selection and ends at 50 to 72% of its first value, and every step of the count is at least 1 (no plateau); and the peak's column and row differ from the selection before's (always where the other constraints allow; `repeat` "both" (hard), else "soft" (a cost of `repeat` per repeated column or row), tried in that order at each relaxation level of the other constraints, `RELAX`). Costs, by preset (`PRESETS`): the count's
     rise being uneven (second difference) or flat, the first grid being narrow, the spacing's total fall and the last count being above the least allowed, the peak at the same cell, column or row as at another selection (more when consecutive), a border coordinate of the peak's index, and an uneven fall of the spacing.
  3. **Presets** `even`, `balanced`, `diverse` weight those costs differently; `plans` returns all three for a session and `options` writes them side by side (`docs/pilots/pilot_selection_options.txt`).
     The figure uses `balanced` unless a preset is given.
  Where a map pins the peak (a corner, or an edge position such as Complexity 2's shape 0.12) only what is left can vary. No history, no displacement. A session has 5 selections (human pilots: 4.7 on average, 1 to 8).

    dense_grid.py figure SESSIONS [--preset even|balanced|diverse] [--out file.png]
    dense_grid.py options SESSIONS [--out file.txt]

Not an engine file; nothing here is read by the game.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import adaptive_grid_sim as ag

DOCS = Path(__file__).resolve().parent.parent / "docs" / "pilots"
N = 5
TOP = 5
MARGIN = ag.MARGIN
REGION = 0.5                   # the high-value region: value at least this share of the peak
S_GRID = np.arange(0.25, 0.0599, -0.005)               # candidate shape spacings, widest first
ASPECT_POWER = 0.77            # a map stretched r : 1 along shape gets a grid whose colour spacing ends at r ** ASPECT_POWER times the shape spacing (r = 2 gives 1.7)
RATIO_POWERS = (1.0, 2.0)      # the colour:shape ratio rises as (selection / last) ** power; more than 1 keeps early, coarse grids squarer, leaving rows for the peak
NAMES = {"PCX": "Complexity", "PSC": "Spacing", "PSP": "Sparsity"}
MAX_STEP = 4                   # the count inside rises by at most this many points (of 25) between selections
MIN_RISE = 4                   # and by at least this many over the session
RELAX = [{}, {"first": (3, 9)}, {"first": (3, 9), "last": (9, 15)}, {"first": (3, 11), "last": (9, 15), "zoom": (0.4, 0.85)}, {"first": (3, 11), "last": (9, 15), "zoom": (0.4, 0.85), "min_step": 0},
         {"first": (3, 12), "last": (8, 17), "zoom": (0.3, 0.9), "min_step": 0, "max_drop": 0.5, "min_rise": 2}]   # tried in order when a session has no plan: wider count ranges and zoom, steps of 0, a bigger fall of the spacing, a smaller rise
MAX_DROP = 0.70                # the geometric-mean spacing falls to at least this share of the selection before
SPEC = {                       # per-session overrides: first and last count ranges, the final ratio
    "PSP_S1": {"first": (10, 11), "last": (13, 15), "zoom": (0.4, 0.85)},   # at a coarse spacing a peak at (0.455, 0.665) of a colour-wide map already has 10 of 25 points inside; it ends at 52 to 60%
    "PCX_S3": {"first": (4, 11), "last_ratio": 1.3},
}
DEFAULT_SPEC = {"first": (4, 7), "last": (10, 13), "last_ratio": None, "zoom": (0.50, 0.72), "min_step": 1, "repeat": "both", "first_geo_min": 0.19}
PRESETS = {                    # cost weights
    "even": {"even": 8.0, "plateau": 6.0, "same_cell": 3.0, "same_line": 0.5, "neighbour": 0.3, "edge": 0.3, "smooth": 30.0, "shrink": 1.0, "last_count": 0.4, "broad_first": 15.0, "repeat": 10.0},
    "balanced": {"even": 3.0, "plateau": 4.0, "same_cell": 4.0, "same_line": 2.0, "neighbour": 1.0, "edge": 1.0, "smooth": 30.0, "shrink": 1.0, "last_count": 0.4, "broad_first": 15.0, "repeat": 10.0},
    "diverse": {"even": 1.0, "plateau": 2.0, "same_cell": 6.0, "same_line": 3.0, "neighbour": 1.5, "edge": 1.5, "smooth": 30.0, "shrink": 1.0, "last_count": 0.4, "broad_first": 15.0, "repeat": 10.0},
}
BEAM = 4000


def spec_of(session):
    return {**DEFAULT_SPEC, **SPEC.get(session, {})}


def load_world(session):
    """(world, last ratio): the session's world (`adaptive_grid_sim.World`) and the final ratio of the colour spacing to the shape spacing of its grids: the session's in `SPEC`, else the stretch of an
    axis-aligned Gaussian (shape width over colour width) to the power `ASPECT_POWER`, 1 for any other map."""
    world = ag.World(session)
    if spec_of(session)["last_ratio"] is not None:
        return world, float(spec_of(session)["last_ratio"])
    bumps = world.params.reward_function["bumps"]
    if len(bumps) == 1 and abs(bumps[0].get("angle", 0.0)) < 1e-9 and bumps[0]["widthColor"] > 0:
        return world, float((bumps[0]["width"] / bumps[0]["widthColor"]) ** ASPECT_POWER)
    return world, 1.0


def grid_cells(peak, i, j, s, ratio=1.0):
    """The N x N cells of the grid with shape spacing s and colour spacing s x ratio, with the peak as its (i, j)-th point."""
    axis = np.arange(N)
    return np.array([(peak[0] + (a - i) * s, peak[1] + (b - j) * s * ratio) for a in axis for b in axis])


def count_inside(world, cells):
    return int((world.value(cells) >= REGION * world.vmax).sum())


def build_table(world, ratio):
    """For one selection's colour:shape ratio: arrays over (spacing in S_GRID, i, j): `fit` and `count` inside the region."""
    s = S_GRID[:, None, None, None, None]
    i = np.arange(N)[None, :, None, None, None]
    j = np.arange(N)[None, None, :, None, None]
    a = np.arange(N)[None, None, None, :, None]
    b = np.arange(N)[None, None, None, None, :]
    x = world.peak[0] + (a - i) * s
    y = world.peak[1] + (b - j) * s * ratio
    values = world.value(np.stack(np.broadcast_arrays(x, y), axis=-1))                    # (S, I, J, A, B)
    count = (values >= REGION * world.vmax).sum(axis=(3, 4))
    lo_x, hi_x = min(MARGIN, world.peak[0]), max(1.0 - MARGIN, world.peak[0])
    lo_y, hi_y = min(MARGIN, world.peak[1]), max(1.0 - MARGIN, world.peak[1])
    sv = S_GRID[:, None]
    fit_i = (world.peak[0] - np.arange(N)[None, :] * sv >= lo_x - 1e-9) & (world.peak[0] + (N - 1 - np.arange(N)[None, :]) * sv <= hi_x + 1e-9)
    fit_j = (world.peak[1] - np.arange(N)[None, :] * sv * ratio >= lo_y - 1e-9) & (world.peak[1] + (N - 1 - np.arange(N)[None, :]) * sv * ratio <= hi_y + 1e-9)
    return {"fit": fit_i[:, :, None] & fit_j[:, None, :], "count": count}


def solve(spec, ratios, tables, weights, selections=5):
    """The cheapest plan over the tables: a list of (spacing index, i, j) per selection, and its cost, or (None, inf) when none meets the hard constraints."""
    geo = lambda si, r: S_GRID[si] * np.sqrt(ratios[r])
    # state arrays: cost, positions (B, r) as i * N + j, spacing index, previous spacing index, count, previous count
    cost = np.zeros(1); pos = np.zeros((1, 0), int); sidx = np.zeros((1, 0), int); cnt = np.zeros((1, 0), int)
    for r in range(selections):
        T = tables[r]
        cs, ci, cj = np.nonzero(T["fit"])
        cc = T["count"][cs, ci, cj]
        ok = np.ones(len(cs), bool)
        if r == 0:
            ok &= (cc >= spec["first"][0]) & (cc <= spec["first"][1])
            if spec.get("first_geo_min"):
                ok &= geo(cs, 0) >= spec["first_geo_min"] - 1e-9                 # a broad first grid
        ok &= (cc <= spec["last"][1]) & (cc >= spec["last"][0] - MAX_STEP * (selections - 1 - r))      # so that the last range can still be reached
        if r == selections - 1:
            ok &= (cc >= spec["last"][0]) & (cc <= spec["last"][1])
        cs, ci, cj, cc = cs[ok], ci[ok], cj[ok], cc[ok]
        cpos = ci * N + cj
        B, K = len(cost), len(cs)
        if K == 0 or B == 0:
            return None, np.inf
        total = np.broadcast_to(cost[:, None], (B, K)).copy()
        valid = np.ones((B, K), bool)
        if r > 0:
            g_prev = geo(sidx[:, -1], r - 1)[:, None]
            g_now = geo(cs, r)[None, :]
            valid &= (g_now <= g_prev + 1e-9) & (g_now >= spec.get("max_drop", MAX_DROP) * g_prev - 1e-9)
            step = cc[None, :] - cnt[:, -1][:, None]
            valid &= (step >= spec.get("min_step", 1)) & (step <= MAX_STEP)
            same_col_prev = (pos[:, -1] // N)[:, None] == ci[None, :]
            same_row_prev = (pos[:, -1] % N)[:, None] == cj[None, :]
            if spec["repeat"] == "both":
                valid &= ~(same_col_prev | same_row_prev)                           # the peak's column and row differ from the selection before's
            else:
                total += weights["repeat"] * (same_col_prev.astype(float) + same_row_prev)    # else as few repeats as the other constraints allow
            total += weights["plateau"] * (step == 0) + weights["shrink"] * np.log(g_prev / g_now)
            if r > 1:
                second = step - (cnt[:, -1] - cnt[:, -2])[:, None]
                total += weights["even"] * np.abs(second)
                g2 = geo(sidx[:, -2], r - 2)[:, None]
                total += weights["smooth"] * (np.log(g_now) - 2 * np.log(g_prev) + np.log(g2)) ** 2
            same_cell = pos[:, :, None] == cpos[None, None, :]                                           # (B, r, K)
            same_col = (pos[:, :, None] // N) == (cpos[None, None, :] // N)
            same_row = (pos[:, :, None] % N) == (cpos[None, None, :] % N)
            line = same_col.astype(float) + same_row
            line[:, -1, :] *= 1.0 + weights["neighbour"] / max(weights["same_line"], 1e-9)
            total += weights["same_cell"] * same_cell.sum(axis=1) + weights["same_line"] * line.sum(axis=1)
        if r == 0:
            total += weights["broad_first"] * (S_GRID[0] - geo(cs, 0))[None, :]
        if r == selections - 1:
            total += weights["last_count"] * (cc - spec["last"][0])[None, :]
        total += weights["edge"] * (((ci == 0) | (ci == N - 1)).astype(int) + ((cj == 0) | (cj == N - 1)).astype(int))[None, :]
        total = np.where(valid, total, np.inf)
        flat = total.ravel()
        keep = np.argpartition(flat, min(BEAM, flat.size) - 1)[:BEAM] if flat.size > BEAM else np.arange(flat.size)
        keep = keep[np.isfinite(flat[keep])]
        if keep.size == 0:
            return None, np.inf
        b, k = np.divmod(keep, K)
        cost = flat[keep]
        pos = np.concatenate([pos[b], cpos[k][:, None]], axis=1)
        sidx = np.concatenate([sidx[b], cs[k][:, None]], axis=1)
        cnt = np.concatenate([cnt[b], cc[k][:, None]], axis=1)
    if len(cost) == 0:
        return None, np.inf
    rise_ok = (cnt[:, -1] - cnt[:, 0]) >= spec.get("min_rise", MIN_RISE)
    zoom = geo(sidx[:, -1], selections - 1) / geo(sidx[:, 0], 0)
    rise_ok &= (zoom >= spec["zoom"][0] - 1e-9) & (zoom <= spec["zoom"][1] + 1e-9)
    cost = np.where(rise_ok, cost, np.inf)
    best = int(np.argmin(cost))
    if not np.isfinite(cost[best]):
        return None, np.inf
    return [(int(sidx[best, r]), int(pos[best, r] // N), int(pos[best, r] % N)) for r in range(selections)], float(cost[best])


def plan_session(session, world, last_ratio, weights, selections=5):
    """The best plan of a session over the ratio exponents `RATIO_POWERS`, as grid dicts: cells, index, s, ratio, values, the best 5, the count inside, its share."""
    base = spec_of(session)
    found = None
    for relax in RELAX:                                              # the least relaxation of the other constraints that gives a plan,
        for mode in ("both", "soft"):                                # and at that level the column and the row differing from selection to selection: always (hard), else as few repeats as possible (a heavy cost)
            spec = {**base, **relax, "repeat": mode}
            found = _best_plan(world, spec, last_ratio, weights, selections)
            if found is not None:
                break
        if found is not None:
            break
    else:
        raise ValueError(f"{session}: no plan meets the constraints even relaxed (counts {base['first']} to {base['last']})")
    best = found
    out = []
    for r, (si, i, j) in enumerate(best[1]):
        s = float(S_GRID[si])
        cells = grid_cells(world.peak, i, j, s, best[2][r])
        values = world.value(cells)
        n = int((values >= REGION * world.vmax).sum())
        out.append({"cells": cells, "index": (i, j), "s": s, "ratio": best[2][r], "values": values, "top": np.argsort(values)[::-1][:TOP], "inside": n, "share": n / (N * N), "relaxed": {**relax, "repeat": mode} if (relax or mode != "both") else {}})
    return out


def _best_plan(world, spec, last_ratio, weights, selections):
    """(cost, plan, ratios) of the cheapest plan over the ratio exponents, or None."""
    best = (np.inf, None, None)
    for power in RATIO_POWERS:
        ratios = [1.0 + (r / (selections - 1)) ** power * (last_ratio - 1.0) for r in range(selections)]
        tables = [build_table(world, ratio) for ratio in ratios]
        plan, cost = solve(spec, ratios, tables, weights, selections)
        if plan is not None and cost < best[0]:
            best = (cost, plan, ratios)
    return best if best[1] is not None else None


def plans(session, selections=5):
    """{preset: grids} for the three presets."""
    world, last_ratio = load_world(session)
    return {name: plan_session(session, world, last_ratio, w, selections) for name, w in PRESETS.items()}


def summary(grids):
    ids = [g["index"] for g in grids]
    return {"distinct": len(set(ids)), "columns": len({i for i, _ in ids}), "rows": len({j for _, j in ids}), "border": sum((i in (0, N - 1)) + (j in (0, N - 1)) for i, j in ids)}


def label(session):
    """'PCX_S3' -> 'Complexity, session 3'."""
    return f"{NAMES[session[:3]]}, session {session[-1]}"


def figure(sessions, selections=5, preset=None):
    """One row per session, one column per selection; shared axes, no cell titles. Returns (figure, text): the text lists every cell (spacings, points inside, peak index, best-5 sum)."""
    fig, axes = plt.subplots(len(sessions), selections, figsize=(2.15 * selections, 2.15 * len(sessions)), sharex=True, sharey=True, layout="constrained", squeeze=False)
    axis = np.linspace(0, 1, 101)
    lines = ["session / selection: shape spacing x colour spacing, points inside, peak index (shape, colour), best-5 sum as a share of 5 peaks"]
    for row, session in enumerate(sessions):
        world, last_ratio = load_world(session)
        name = preset or "balanced"
        grids = plan_session(session, world, last_ratio, PRESETS[name], selections)
        field = world.value(np.stack(np.meshgrid(axis, axis, indexing="ij"), axis=-1))
        bump = world.params.reward_function["bumps"][0]
        stretch = bump["width"] / bump["widthColor"] if bump["widthColor"] > 0 else 1.0
        lines.append(f"{label(session)} ({session}, preset {name}) (map stretched {stretch:.2f}:1 along shape, grid colour:shape spacing ends {grids[-1]['ratio']:.2f})")
        for col, g in enumerate(grids):
            ax = axes[row, col]
            ax.imshow(field.T, origin="lower", extent=(0, 1, 0, 1), cmap="Greys", vmin=0, vmax=world.vmax * 1.05)
            ax.contour(axis, axis, field.T, levels=[REGION * world.vmax], colors="#d62728", linewidths=0.7)
            rest = np.setdiff1d(np.arange(len(g["cells"])), g["top"])
            ax.plot(*g["cells"][rest].T, "o", color="#1f77b4", markersize=3)
            ax.plot(*g["cells"][g["top"]].T, "o", color="#ff7f0e", markersize=4.5)
            ax.plot(*world.peak, "*", color="gold", markeredgecolor="black", markersize=9)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_aspect("equal")
            if row == 0:
                ax.set_title(f"selection {col + 1}", fontsize=9)
            lines.append(f"  {col + 1}: {g['s']:.3f} x {g['s'] * g['ratio']:.3f}, {g['inside']}/{N * N} = {g['share']:.0%}, peak {g['index']}, {g['values'][g['top']].sum() / (TOP * world.vmax):.2f}")
        axes[row, 0].set_ylabel(f"{label(session)}\ncolour", fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("shape", fontsize=8)
    fig.suptitle("Dense 5x5 selection grids: star = peak, red = half-peak contour,\norange = best 5 bushes, blue = the other 20", fontsize=9)
    return fig, "\n".join(lines)


def options_text(sessions, selections=5):
    """The three presets' plans of each session side by side: counts inside, peak positions, spacings, how varied the positions are."""
    lines = ["session, preset: share inside (points of 25) | peak index (shape, colour) | shape x colour spacing | distinct positions, columns, rows, border coordinates"]
    for session in sessions:
        for name, grids in plans(session, selections).items():
            sm = summary(grids)
            lines.append(f"{session} {name:9s} " + " ".join(f"{g['inside']:2d}" for g in grids) + " | " + " ".join(f"{g['index']}" for g in grids) + " | "
                         + " ".join(f"{g['s']:.3f}x{g['s'] * g['ratio']:.3f}" for g in grids) + f" | {sm['distinct']}, {sm['columns']}, {sm['rows']}, {sm['border']}" + (f" | relaxed {grids[0]['relaxed']}" if grids[0]["relaxed"] else ""))
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Dense 5x5 selection grids with the peak on the grid.")
    ap.add_argument("command", choices=["figure", "options"])
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--selections", type=int, default=5)
    ap.add_argument("--preset", choices=list(PRESETS), default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.command == "options":
        out = Path(args.out or DOCS / "pilot_selection_options.txt")
        out.write_text(options_text(args.sessions, args.selections) + "\n")
        print(out)
        return
    out = Path(args.out or DOCS / "dense_grid_schedule.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, text = figure(args.sessions, args.selections, args.preset)
    fig.savefig(out, dpi=100)
    out.with_suffix(".txt").write_text(text + "\n")
    print(out)


if __name__ == "__main__":
    main()
