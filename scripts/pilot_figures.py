"""The two key figures of the pilots on the pilots' value maps: `trends` and `grids`.

    pilot_figures.py trends [--out docs/pilots/pilot_trends.png]
    pilot_figures.py grids  [--out docs/pilots/pilot_selection.png]

`trends`: one row per experiment (Complexity PCX, Spacing PSC, Sparsity PSP), the three sessions' maps in columns (the fixed 0 to 9 fruit scale; a contour at half the peak; the world's bushes
as dots: the world is generated with the map, so the dots are the bushes the participant would see), and a fourth panel with the descriptors across the three sessions (map Gini, bush Gini,
interaction, nonlinearity, as plotted by `value_maps` and `factors.measure`); the text file adds the span-and-hold check of each pilot knob (`pilot_report.PILOTS`). The knob of each pilot is the solid line.
`grids`: the dense 5x5 selection grids of `dense_grid.py`, five selections in columns, one row per experiment and session.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import dense_grid
import factors
import pilot_report
import sim
import value_maps
from selection import load_session

DOCS = Path(__file__).resolve().parent.parent / "docs" / "pilots"
EXPERIMENTS = (("PCX", "Complexity", "interaction"), ("PSC", "Spacing", "travel time"), ("PSP", "Sparsity", "Gini"))
METRICS = (("gini", "map Gini", "#1f77b4"), ("bush_gini", "bush Gini", "#17becf"), ("interaction", "interaction", "#d62728"), ("nonlinearity", "nonlinearity", "#2ca02c"))


def session_record(session):
    """The session's value map, its descriptors, and its generated world's bushes (generated with the map)."""
    world, _ = dense_grid.load_world(session)
    rf = world.params.reward_function
    bumps = tuple(value_maps.Bump(b["centerShape"], b["centerColor"], b["width"], b["widthColor"], b.get("angle", 0.0), b["height"]) for b in rf["bumps"])
    vm = value_maps.ValueMap(bumps)
    seed = int(load_session(session).world_seed)
    w = sim.get_worlds(session, [seed])[0]
    desc = vm.descriptors()
    desc["bush_gini"] = float(factors.measure(w)["bush_gini"])
    return {"vm": vm, "desc": desc, "shape": np.asarray(w.shape), "color": np.asarray(w.color)}


def layout_panel(ax, session):
    """The top-down layout of a session's world: its hexagonal patches (outlines) and bushes coloured by their pay; returns the scatter (for a colourbar) and (seconds between patches, bushes)."""
    from matplotlib.patches import Polygon
    world, _ = dense_grid.load_world(session)
    w = sim.get_worlds(session, [int(load_session(session).world_seed)])[0]
    grid = w.terrain.tiles
    theta = np.arctan2(grid.a[1], grid.a[0]) + np.pi / 6.0
    angles = theta + np.arange(6) * np.pi / 3.0
    corner_x, corner_z = grid.radius * np.cos(angles), grid.radius * np.sin(angles)
    ti, tj = grid.nearest(w.pos[:, 0], w.pos[:, 1])
    used = set(zip(ti.tolist(), tj.tolist()))
    for i, j, c in grid.tile_centres():
        if (i, j) in used:
            ax.add_patch(Polygon(np.column_stack([c[0] + corner_x, c[1] + corner_z]), closed=True, fill=False, edgecolor="#b0b0b0", linewidth=0.8))
    sc = ax.scatter(w.pos[:, 0], w.pos[:, 1], c=w.value, s=9, cmap="viridis", vmin=0, vmax=9)
    ax.plot(0, 0, "*", color="red", markersize=12, markeredgecolor="white")
    pad = 1.2 * grid.radius
    ax.set_xlim(w.pos[:, 0].min() - pad, w.pos[:, 0].max() + pad)
    ax.set_ylim(w.pos[:, 1].min() - pad, w.pos[:, 1].max() + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    return sc, (float(factors.measure(w)["travel_time"]), int(w.n))


def trend_lines(code, descs):
    """Lines saying whether the pilot's knob moved as required in the three sessions' descriptors."""
    spec = pilot_report.PILOTS[code]
    lines = []
    for metric, least in spec["vary"].items():
        if metric not in descs[0]:
            lines.append(f"  vary {metric}: a world metric (not read from the map; unchanged by the maps)")
            continue
        vals = [d[metric] for d in descs]
        rising = all(b > a for a, b in zip(vals, vals[1:]))
        lines.append(f"  vary {metric}: {', '.join(f'{v:.3f}' for v in vals)}  span {vals[-1] - vals[0]:.3f} (needs {least:g}), rising: {'yes' if rising else 'NO'}  -> {'ok' if rising and vals[-1] - vals[0] >= least else 'FLAG'}")
    for metric, (kind, tol) in spec["hold"].items():
        if metric not in descs[0]:
            continue                                                  # world metrics (travel time, mean bush value, ...) are not map descriptors
        vals = [d[metric] for d in descs]
        spread = max(vals) - min(vals)
        lines.append(f"  hold {metric}: {', '.join(f'{v:.3f}' for v in vals)}  spread {spread:.3f} (tolerance {tol:g})  -> {'ok' if spread <= tol else 'FLAG'}")
    return lines


def trends_figure():
    fig, axes = plt.subplots(len(EXPERIMENTS) + 1, 4, figsize=(15, 3.6 * (len(EXPERIMENTS) + 1)), gridspec_kw={"width_ratios": [1, 1, 1, 1.15]}, layout="constrained", squeeze=False)
    lines = []
    for k, (code, name, knob) in enumerate(EXPERIMENTS):
        row = k if k < 2 else k + 1                                    # the layout row of Spacing sits below its trends, above Sparsity
        recs = [session_record(f"{code}_S{k}") for k in range(1, 4)]
        for col, rec in enumerate(recs):
            ax = axes[row, col]
            axis, field = rec["vm"].grid()
            d = rec["desc"]
            ax.imshow(field.T, origin="lower", extent=(0, 1, 0, 1), cmap="Blues", vmin=0, vmax=9)
            ax.contour(axis, axis, field.T, levels=[0.5 * d["max"]], colors="k", linewidths=0.8)
            ax.scatter(rec["shape"], rec["color"], s=6, c="k", alpha=0.35, linewidths=0)
            ax.set_title(f"{name}, session {col + 1}\nGini {d['gini']:.2f}, interaction {d['interaction']:.2f}, nonlinearity {d['nonlinearity']:.2f}", fontsize=8.5, loc="left")
            ax.set_xlabel("shape", fontsize=8)
            if col == 0:
                ax.set_ylabel("colour", fontsize=8)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
        ax = axes[row, 3]
        for key, label, colour in METRICS:
            vals = [r["desc"][key] for r in recs]
            ax.plot([1, 2, 3], vals, "o-", color=colour, label=label, linewidth=2.2 if key in ("interaction", "gini") and knob.lower().startswith(key[:3]) else 1.2)
        ax.set_xticks([1, 2, 3])
        ax.set_xlabel("session", fontsize=8)
        ax.set_ylim(0, 1.0)
        ax.set_title(f"{name} (knob: {knob})", fontsize=8.5, loc="left")
        ax.legend(fontsize=7, loc="upper left", ncol=2)
        lines += [name + " (span and hold check, `pilot_report.PILOTS`)"] + trend_lines(code, [r["desc"] for r in recs])
        lines.append(name + ": " + "; ".join(f"{label} " + ", ".join(f"{r['desc'][key]:.3f}" for r in recs) for key, label, _ in METRICS))
        if code == "PSC":
            for col in range(3):
                sc, (seconds, n) = layout_panel(axes[2, col], f"PSC_S{col + 1}")
                axes[2, col].set_title(f"Spacing, session {col + 1}: {seconds:.0f} s between patches\n{n} bushes in the whole world (star: start)", fontsize=8.5)
            axes[2, 3].axis("off")
            fig.colorbar(sc, ax=axes[2, 3], location="left", shrink=0.8, label="bush value (points)")
            lines.append("Spacing layout: " + ", ".join(f"PSC_S{c + 1}" for c in range(3)))
    fig.suptitle("Pilot value maps and their trends (dots: the world's bushes)", fontsize=11)
    return fig, "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="The two key pilot figures.")
    ap.add_argument("command", choices=["trends", "grids"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = Path(args.out or DOCS / ("pilot_trends.png" if args.command == "trends" else "pilot_selection.png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "trends":
        fig, text = trends_figure()
    else:
        fig, text = dense_grid.figure([f"{c}_S{k}" for c, _, _ in EXPERIMENTS for k in (1, 2, 3)], 5, None)
    fig.savefig(out, dpi=100)
    out.with_suffix(".txt").write_text(text + "\n")
    print(text)
    print(out)


if __name__ == "__main__":
    main()
