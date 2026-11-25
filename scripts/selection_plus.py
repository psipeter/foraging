"""Figures of the plus selection design (`SessionConfig.selectionDesign` "plus"): the pool's sets drawn on the session's value map.

`selection_plus.py mock <session> --shots a.png b.png c.png [--set-index 0 1 2]` pairs sets with screenshots of them in the game.
`selection_plus.py preview <session> [--axes mixed] [--jitter 1] [--arm 1] [--ratio 2] [--sep 0.08] [--sets 30] [--seed N] [--out file.png]` generates the pool the settings
would give (the session's own, with any setting given here replacing it; nothing is written to the project except the figure) and draws, for each axes mode present, the
value map over (shape, colour) with each set's five bushes as a plus (the centre a disc, the arms squares, joined through the centre), then what the sets show of the map to
someone who sees only the bushes: where the centres lie around the peak and what share of the peak each role pays. The default output is `docs/pilots/<session>_selection_plus.png`.
"""

import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import selection
from world import REWARDS, stage_names

DOCS = Path(__file__).resolve().parent.parent / "docs" / "pilots"
SET_COLOURS = plt.get_cmap("tab10").colors


def field_on_grid(params, n=201):
    axis = np.linspace(0.0, 1.0, n)
    return axis, np.asarray(REWARDS[stage_names(params)[2]](params.reward_function, axis[:, None], axis[None, :]), dtype=float)


def draw_map(ax, axis, field, peak):
    ax.imshow(field.T, origin="lower", extent=(0, 1, 0, 1), cmap="Greys", vmin=0, vmax=peak[2] * 1.05, aspect="equal")
    ax.contour(axis, axis, field.T, levels=np.linspace(0.2, 0.9, 6) * peak[2], colors="#888888", linewidths=0.5)
    ax.plot(*peak[:2], marker="*", color="gold", markeredgecolor="black", markersize=13, linestyle="none", zorder=5)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("shape")
    ax.set_ylabel("colour")


def draw_set(ax, bushes, colour):
    pts = {b["role"]: (b["shape"], b["color"]) for b in bushes}
    c = pts["centre"]
    for a, b_ in (("+1", "-1"), ("+2", "-2")):
        ax.plot([pts[a][0], pts[b_][0]], [pts[a][1], pts[b_][1]], color=colour, linewidth=1.3, zorder=3)
    for role, (x, y) in pts.items():
        ax.plot(x, y, marker="o" if role == "centre" else "s", color=colour, markeredgecolor="white", markeredgewidth=0.6,
                markersize=7 if role == "centre" else 5, zorder=4)
    return c


def figure(sidecar, params, title):
    sets, meta = sidecar["sets"], sidecar["plus"]
    peak, frame = sidecar["peak"], sidecar["frame"]
    axis, field = field_on_grid(params)
    modes = [m for m in selection.PLUS_AXES_MODES if any(x["axes"] == m for x in meta)]
    fig = plt.figure(figsize=(5.0 * max(len(modes), 3), 10.2), layout="constrained")
    grid = fig.add_gridspec(2, max(len(modes), 3), height_ratios=[1.0, 0.85])
    for col, mode in enumerate(modes):
        ax = fig.add_subplot(grid[0, col])
        draw_map(ax, axis, field, peak)
        idx = [i for i, m in enumerate(meta) if m["axes"] == mode]
        for k, i in enumerate(idx[:10]):
            draw_set(ax, sets[i]["bushes"], SET_COLOURS[k % len(SET_COLOURS)])
        ax.set_title(f"axes: {mode} ({min(len(idx), 10)} of {len(idx)} sets)")

    sigma = math.sqrt(frame[1] * frame[2])
    ax = fig.add_subplot(grid[1, 0])
    th = math.radians(frame[0])
    f1, f2 = np.array([math.cos(th), math.sin(th)]), np.array([-math.sin(th), math.cos(th)])
    for mode, marker in zip(selection.PLUS_AXES_MODES, "ovs"):
        off = np.array([m["offset"] for m in meta if m["axes"] == mode])
        if len(off):
            ax.plot(off @ f1 / frame[1], off @ f2 / frame[2], marker, label=mode, alpha=0.8)
    ax.plot(0, 0, marker="*", color="gold", markeredgecolor="black", markersize=14, linestyle="none")
    ax.axhline(0, color="#cccccc", linewidth=0.6)
    ax.axvline(0, color="#cccccc", linewidth=0.6)
    ax.set_aspect("equal")
    ax.set_xlabel("centre offset along the peak bump's axis 1 (spreads)")
    ax.set_ylabel("along axis 2 (spreads)")
    ax.set_title("where the centres lie around the peak")
    ax.legend(fontsize=8)

    ax = fig.add_subplot(grid[1, 1])
    shares = {r: [] for r in selection.PLUS_ROLES}
    for st in sets:
        for b in st["bushes"]:
            shares[b["role"]].append(b["value"] / peak[2])
    ax.boxplot([shares[r] for r in selection.PLUS_ROLES], tick_labels=list(selection.PLUS_ROLES), showfliers=True)
    ax.axhline(selection.PLUS_MIN_FRACTION, color="#cc4444", linewidth=0.8, linestyle=":")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("value as a share of the peak")
    ax.set_title("what each role pays")

    ax = fig.add_subplot(grid[1, 2])
    ax.axis("off")
    sm = sidecar["summary"]
    lines = [f"peak {peak[2]:.2f} at (shape {peak[0]:.2f}, colour {peak[1]:.2f})",
             f"peak bump: angle {frame[0]:.0f} deg, spreads {frame[1]:.2f} / {frame[2]:.2f}", "",
             f"sets {sidecar['n']}   min gap in a set {min(s['minGap'] for s in sets):.2f}   tie gap {sidecar['minGap']}",
             f"mean centre to peak: {sm['meanCentreToPeak']:.2f} spreads",
             f"scatter of the centres: {sm['centreScatter']:.2f} spreads",
             f"the centre is the best bush of its set: {100 * sm['centreIsBest']:.0f}%",
             f"lowest bush: {100 * sm['minShareOfPeak']:.0f}% of the peak", "",
             "share of the peak by role: " + ", ".join(f"{r} {100 * v:.0f}%" for r, v in sm["shareOfPeak"].items())]
    ax.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", fontsize=9, family="monospace", wrap=True)
    fig.suptitle(title)
    return fig


MODE_COLOURS = {"aligned": "#1f77b4", "random": "#d95f02", "bump": "#2ca02c"}
GROUND = "#6b4f33"


def ramp_colours(params):
    """The session's fruit colour ramp as an (n, 3) array of sRGB stops."""
    return np.array([[float(c["r"]), float(c["g"]), float(c["b"])] for c in params.fruit_color_ramp])


def ramp_at(stops, t):
    x = float(np.clip(t, 0.0, 1.0)) * (len(stops) - 1)
    lo = int(math.floor(x))
    hi = min(lo + 1, len(stops) - 1)
    return tuple(np.clip(stops[lo] * (1 - (x - lo)) + stops[hi] * (x - lo), 0, 1))


def draw_bush(ax, x, bush, params, stops, rng):
    """A bush as the game draws it, flat: a half ellipsoid (width and height from the shape as `Tree.ApplyAttributes`) on the ground, fruits of the colour attribute's colour.
    The value is written above it, its role under the ground."""
    t = float(np.clip((bush["shape"] - params.shape_range[0]) / max(params.shape_range[1] - params.shape_range[0], 1e-9), 0, 1))
    w_lo, w_hi = params.canopy_width_range
    h_lo, h_hi = params.canopy_height_range
    half_w, half_h = (w_hi + (w_lo - w_hi) * t) / 2.0, (h_lo + (h_hi - h_lo) * t) / 2.0
    a = np.linspace(0.0, math.pi, 60)
    ax.fill(x + half_w * np.cos(a), half_h * np.sin(a), color="#2f5d2a", zorder=2)
    colour = ramp_at(stops, bush["color"])
    for _ in range(int(params.fruit_count)):
        ang, r = rng.uniform(0.15, math.pi - 0.15), rng.uniform(0.35, 0.92)
        ax.plot(x + r * half_w * math.cos(ang), r * half_h * math.sin(ang), "o", color=colour, markersize=5, markeredgecolor="#00000055", markeredgewidth=0.4, zorder=3)
    ax.text(x, half_h + 0.5, f"{bush['value']:.1f}", ha="center", va="bottom", fontsize=11, fontweight="bold", zorder=4)
    ax.text(x, -0.9, bush["role"], ha="center", va="top", fontsize=8, color="#555555")
    return half_h


def draw_selection_row(axes_row, sidecar, params, ids, stops, field_axis, field, label):
    """One selection (the sets `ids`): the value map with their pluses in column 0, then each set's five bushes with their true values."""
    sets, meta, peak = sidecar["sets"], sidecar["plus"], sidecar["peak"]
    ax = axes_row[0]
    draw_map(ax, field_axis, field, peak)
    for i in ids:
        draw_set(ax, sets[i]["bushes"], MODE_COLOURS.get(meta[i]["axes"], "k"))
    ax.set_title(label, fontsize=10)
    for col, i in enumerate(ids):
        ax = axes_row[1 + col]
        rng = np.random.default_rng(1000 + i)
        top = 0.0
        for b in sets[i]["bushes"]:
            top = max(top, draw_bush(ax, b["slot"] * 7.0, b, params, stops, rng))
        ax.axhline(0, color=GROUND, linewidth=6, solid_capstyle="round", zorder=1)
        ax.set_xlim(-4.0, 4 * 7.0 + 4.0)
        ax.set_ylim(-2.5, max(top, float(params.canopy_height_range[1]) / 2.0) + 2.2)
        ax.axis("off")
        m = meta[i]
        values = sorted(b["value"] for b in sets[i]["bushes"])
        ax.set_title(f"set {i}: {m['axes']}" + (f", shrunk to {100 * m['scale']:.0f}%" if m["scale"] < 1.0 else "") + (f", turned {m['turn']:.0f} deg" if m["turn"] else "")
                     + f"  (steps {min(np.diff(values)):.2f} to {max(np.diff(values)):.2f})", fontsize=10, color=MODE_COLOURS.get(m["axes"], "k"))


def selections_figure(sidecar, params, title, rows=None, group=3):
    """One row per group of `group` consecutive sets (a selection of three pluses: aligned, random, random): the value map with the pluses overlaid, then the five bushes of each set
    drawn in their slots (left to right) with the true value above each bush."""
    n_rows = len(sidecar["sets"]) // group if rows is None else min(rows, len(sidecar["sets"]) // group)
    axis, field = field_on_grid(params)
    stops = ramp_colours(params)
    fig, axes = plt.subplots(n_rows, 1 + group, figsize=(4.0 + 4.1 * group, 3.3 * n_rows), gridspec_kw={"width_ratios": [1.0] + [1.25] * group}, layout="constrained", squeeze=False)
    for row in range(n_rows):
        ids = list(range(row * group, row * group + group))
        draw_selection_row(axes[row], sidecar, params, ids, stops, axis, field, f"selection {row + 1}: sets {ids[0]}-{ids[-1]}")
    fig.suptitle(title)
    return fig


def difficulty_figure(session, plan, levels, overrides, title, group=3):
    """One row per difficulty (the first selection of a pool made with that difficulty and plan): the same four columns as `selections_figure`."""
    import plus_plans
    fig, axes = plt.subplots(len(levels), 1 + group, figsize=(4.0 + 4.1 * group, 3.4 * len(levels)), gridspec_kw={"width_ratios": [1.0] + [1.25] * group}, layout="constrained", squeeze=False)
    for row, level in enumerate(levels):
        sidecar, params = selection.generate_pool(session, selection_design="plus", selection_plus_plan=plan, selection_plus_difficulty=level, **overrides)
        axis, field = field_on_grid(params)
        step = plus_plans.DIFFICULTY.get(level, None)
        label = f"{level}" + (f": a step of {step:.2f} of the peak ({step * sidecar['peak'][2]:.2f} points)" if step else "")
        draw_selection_row(axes[row], sidecar, params, list(range(group)), ramp_colours(params), axis, field, label)
    fig.suptitle(title)
    return fig


def spread_figure(sidecar, title):
    """What the values of the sets look like by axes mode: the five values of each set from best to worst (thin lines, the median thick), the spread (best minus worst) and the
    smallest gap between neighbouring values of a set."""
    peak = sidecar["peak"][2]
    sets, meta = sidecar["sets"], sidecar["plus"]
    modes = [m for m in ("aligned", "bump", "random") if any(x["axes"] == m for x in meta)]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(16, 4.8), layout="constrained")
    for k, mode in enumerate(modes):
        ladders = np.array([sorted((x["value"] for x in sets[i]["bushes"]), reverse=True) for i, m in enumerate(meta) if m["axes"] == mode]) / peak
        for row in ladders:
            a.plot(range(1, 6), row, color=MODE_COLOURS[mode], alpha=0.25, linewidth=1)
        a.plot(range(1, 6), np.median(ladders, axis=0), color=MODE_COLOURS[mode], linewidth=3, label=f"{mode} (median of {len(ladders)})")
        spans, gaps = ladders[:, 0] - ladders[:, -1], np.diff(ladders, axis=1).min(axis=1) * -1
        for ax_, vals in ((b, spans), (c, gaps * peak)):
            ax_.plot(np.full(len(vals), k) + np.random.default_rng(k).uniform(-0.12, 0.12, len(vals)), vals, "o", color=MODE_COLOURS[mode], alpha=0.7)
            ax_.hlines(np.median(vals), k - 0.25, k + 0.25, color="black", linewidth=2)
    a.set_xlabel("rank in the set (1 = best)")
    a.set_ylabel("true value as a share of the peak")
    a.set_xticks(range(1, 6))
    a.set_title("the ladder of values")
    a.legend(fontsize=8)
    b.set_xticks(range(len(modes)), modes)
    b.set_ylabel("best minus worst, share of the peak")
    b.set_title("spread of a set")
    c.set_xticks(range(len(modes)), modes)
    c.axhline(sidecar["minGap"], color="#cc4444", linestyle=":", linewidth=1)
    c.set_ylabel("smallest gap between neighbours (points per fruit)")
    c.set_title("how close the closest pair is (dotted: the tie gap)")
    fig.suptitle(title)
    return fig


def plans_figure(session, variants, overrides, title):
    """One row per variant ("plan:difficulty"): all the pool's points on the value map (colour by axes mode, arms thin), the values of all bushes against an even spread, the
    sorted values of each set, and the metrics of `plus_plans.metrics`."""
    import plus_plans
    fig, axes = plt.subplots(len(variants), 4, figsize=(17, 3.6 * len(variants)), gridspec_kw={"width_ratios": [1.0, 0.9, 0.9, 0.8]}, layout="constrained", squeeze=False)
    for row, variant in enumerate(variants):
        plan, difficulty = variant.split(":")
        sidecar, params = selection.generate_pool(session, selection_design="plus", selection_plus_plan=plan, selection_plus_difficulty=difficulty, **overrides)
        peak = sidecar["peak"]
        axis, field = field_on_grid(params)
        ax = axes[row, 0]
        draw_map(ax, axis, field, peak)
        for st, meta in zip(sidecar["sets"], sidecar["plus"]):
            colour = MODE_COLOURS[meta["axes"]]
            pts = {b["role"]: (b["shape"], b["color"]) for b in st["bushes"]}
            for a, b_ in (("+1", "-1"), ("+2", "-2")):
                ax.plot([pts[a][0], pts[b_][0]], [pts[a][1], pts[b_][1]], color=colour, linewidth=0.6, alpha=0.7, zorder=3)
            ax.plot(*zip(*pts.values()), "o", color=colour, markersize=2.5, zorder=4)
            ax.plot(*pts["centre"], "o", color=colour, markersize=5, markeredgecolor="white", markeredgewidth=0.5, zorder=5)
        ax.set_title(variant, fontsize=11)
        ax = axes[row, 1]
        values = np.array(sidecar["value"]) / peak[2]
        ax.hist(values, bins=10, range=(selection.PLUS_MIN_FRACTION, 1.0), color="#777777")
        ax.axhline(len(values) / 10.0, color="#cc4444", linestyle=":", linewidth=1)
        ax.set_xlabel("bush value, share of the peak")
        ax.set_ylabel("bushes")
        ax = axes[row, 2]
        for st, meta in zip(sidecar["sets"], sidecar["plus"]):
            ax.plot(range(1, 6), sorted((b["value"] / peak[2] for b in st["bushes"]), reverse=True), color=MODE_COLOURS[meta["axes"]], alpha=0.35, linewidth=1)
        ax.set_xticks(range(1, 6))
        ax.set_xlabel("rank in the set")
        ax.set_ylabel("value, share of the peak")
        ax.set_ylim(0.2, 1.02)
        ax = axes[row, 3]
        ax.axis("off")
        m = plus_plans.metrics(sidecar, params)
        lines = [f"coverage of the rewarding region", f"  mean distance {m['coverageMean']:.3f}", f"  95th percentile {m['coverageP95']:.3f}", f"  within one selection {m['selectionCoverage']:.3f}", f"nearest-bush distance {m['nearestBush']:.3f}", "",
                 f"value evenness (entropy) {m['valueEntropy']:.2f}", f"step between neighbours (median) {m['stepMedian']:.2f}", f"best minus worst (median) {m['spanMedian']:.2f}", "",
                 f"centre is the best bush {100 * m['centreBest']:.0f}%", f"ladders hit {100 * m['hit']:.0f}%", f"shrunk or turned {100 * m['fitted']:.0f}%", f"centre moved {100 * m['moved']:.0f}%"]
        ax.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", fontsize=9, family="monospace")
    fig.suptitle(title)
    return fig


def mockup(sidecar, params, set_indices, shots, title):
    """One row per set: the set as a plus on the value map beside a screenshot of it in the game (taken in the Editor's Play mode with the pool swapped in; see docs/DECISIONS.md)."""
    peak = sidecar["peak"]
    axis, field = field_on_grid(params)
    fig, axes = plt.subplots(len(set_indices), 2, figsize=(13.5, 4.6 * len(set_indices)), gridspec_kw={"width_ratios": [1, 1.78]}, layout="constrained")
    axes = np.atleast_2d(axes)
    for row, (i, shot) in enumerate(zip(set_indices, shots)):
        draw_map(axes[row, 0], axis, field, peak)
        draw_set(axes[row, 0], sidecar["sets"][i]["bushes"], SET_COLOURS[0])
        for b in sidecar["sets"][i]["bushes"]:
            axes[row, 0].annotate(f"{b['value']:.1f}", (b["shape"], b["color"]), textcoords="offset points", xytext=(5, 5), fontsize=8, color="#b45f00")
        axes[row, 0].set_title(f"set {i}: axes {sidecar['plus'][i]['axes']}; values are points per fruit")
        axes[row, 1].imshow(plt.imread(shot))
        axes[row, 1].axis("off")
        axes[row, 1].set_title("what the participant sees (left to right: the arc's slots)")
    fig.suptitle(title)
    return fig


def main():
    ap = argparse.ArgumentParser(description="Figures of the plus selection design.")
    ap.add_argument("command", choices=["preview", "mock", "selections", "spread", "plans", "difficulty"])
    ap.add_argument("--shots", nargs="*", default=[], help="mock: screenshots of the sets named by --set-index, in order")
    ap.add_argument("--set-index", nargs="*", type=int, default=[0, 1, 2], help="mock: pool set indices")
    ap.add_argument("session")
    ap.add_argument("--axes", default=None, help="aligned, bump, random or mixed (default: the session's, else mixed)")
    ap.add_argument("--jitter", type=float, default=None)
    ap.add_argument("--arm", type=float, default=None)
    ap.add_argument("--ratio", type=float, default=None)
    ap.add_argument("--sep", type=float, default=None)
    ap.add_argument("--sets", type=int, default=None, help="sets in the pool (selectionPoolSets)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--variants", nargs="*", default=["spiral:free", "ring:free", "tile:free", "ring:medium", "tile:mixed"], help="plans: plan:difficulty pairs")
    ap.add_argument("--rows", type=int, default=None, help="selections: draw only this many rows (selections of three sets)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    ov = {"selection_design": "plus"}
    for key, value in (("selection_plus_axes", args.axes), ("selection_plus_jitter", args.jitter), ("selection_plus_arm", args.arm), ("selection_plus_arm_ratio", args.ratio),
                       ("selection_plus_min_separation", args.sep), ("selection_pool_sets", args.sets), ("world_seed", args.seed)):
        if value is not None:
            ov[key] = value
    if args.command == "difficulty":
        given = args.variants != ap.get_default("variants")
        levels = [v.split(":")[-1] for v in args.variants] if given else ["easy", "medium", "hard"]
        plan = args.variants[0].split(":")[0] if given and ":" in args.variants[0] else "tile"
        out = Path(args.out) if args.out else DOCS / f"{args.session}_selection_plus_difficulty.png"
        fig = difficulty_figure(args.session, plan, levels, {k: v for k, v in ov.items() if k != "selection_design"}, f"{args.session}: one selection (aligned, random, random) at each difficulty, plan {plan}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=110)
        print(out)
        return
    if args.command == "plans":
        out = Path(args.out) if args.out else DOCS / f"{args.session}_selection_plus_plans.png"
        fig = plans_figure(args.session, args.variants, {k: v for k, v in ov.items() if k != "selection_design"}, f"{args.session}: plans for placing and valuing the plus sets (seed {args.seed or 'the session'})")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=100)
        print(out)
        return
    sidecar, params = selection.generate_pool(args.session, **ov)
    out = Path(args.out) if args.out else DOCS / f"{args.session}_selection_plus.png"
    if args.command == "selections":
        out = Path(args.out) if args.out else DOCS / f"{args.session}_selection_plus_selections.png"
        fig = selections_figure(sidecar, params, f"{args.session}: the plus selections, the value map and the bushes as the participant sees them (seed {sidecar['seed']})", rows=args.rows)
    elif args.command == "spread":
        out = Path(args.out) if args.out else DOCS / f"{args.session}_selection_plus_spread.png"
        fig = spread_figure(sidecar, f"{args.session}: spread of the plus sets' values by axes mode (seed {sidecar['seed']})")
    elif args.command == "mock":
        fig = mockup(sidecar, params, args.set_index, args.shots, f"{args.session}: plus selection sets in the game (seed {sidecar['seed']})")
    else:
        fig = figure(sidecar, params, f"{args.session}: plus selection sets on the value map (seed {sidecar['seed']})")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(out)
    print(sidecar["summary"])


if __name__ == "__main__":
    main()
