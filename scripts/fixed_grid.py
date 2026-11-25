"""A 3x3 selection grid on a fixed schedule: broad at selection 1, then shifted and zoomed toward the true value region by a fixed amount at every selection (PI's hybrid, 2026-11-25).

Nothing here depends on what the participant did. Selection r of R (r = 1..R) has progress p = (r - 1) / (R - 1):
  * spacing   s(p) = s_max + p (s_min - s_max)                      (linear zoom from the broad grid to the finest the session allows);
  * middle    m(p) = (0.5, 0.5) + p (target - (0.5, 0.5)) + jitter    where target = the session's peak + a per-participant displacement of `displace` final spacings in a random
    direction (so the schedule does not point exactly at the peak), and the jitter is a random offset of up to `jitter` spacings along each axis (selection 1 has none: it is the broad grid).
The grid is clamped inside the map as in `adaptive_grid_sim.grid_cells`. The three knobs are the design: `displace` trades leaking the peak against the fine grids landing near it
(DECISIONS.md, "PI's fixed-schedule idea"). `figure` draws one row per example session, one column per selection.

    fixed_grid.py figure PSC_S1 PSC_S2 PSC_S3 PSP_S1 PSP_S2 [--selections 6] [--displace 2] [--jitter 1] [--out file.png]

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

DOCS = Path(__file__).resolve().parent.parent / "docs" / "pilots"


def draw_participant(rng):
    """The per-participant random numbers of the schedule: a unit direction for the displacement and one jitter draw (-1..1 per axis) per selection (drawn for up to 64 selections)."""
    angle = rng.uniform(0.0, 2.0 * math.pi)
    return np.array([math.cos(angle), math.sin(angle)]), rng.uniform(-1.0, 1.0, (64, 2))


def schedule(world, selections, direction, jitters, *, displace=2.0, jitter=1.0, s_max=ag.S_MAX):
    """The grids of one participant: a list of dicts (centre, s, cells), one per selection."""
    target = world.peak + displace * world.s_min * direction
    grids = []
    for r in range(selections):
        p = r / max(selections - 1, 1)
        s = s_max + p * (world.s_min - s_max)
        centre = np.array([0.5, 0.5]) + p * (target - 0.5)
        if r > 0:
            centre = centre + jitter * jitters[r] * s
        cells = ag.grid_cells(centre, s)
        grids.append({"centre": centre, "s": float(s), "cells": cells, "values": world.value(cells)})
    return grids


def figure(sessions, selections=6, displace=2.0, jitter=1.0, seed=11):
    fig, axes = plt.subplots(len(sessions), selections, figsize=(3.3 * selections, 3.4 * len(sessions)), layout="constrained", squeeze=False)
    axis = np.linspace(0, 1, 101)
    for row, session in enumerate(sessions):
        world = ag.World(session)
        direction, jit = draw_participant(np.random.default_rng([seed, row]))
        grids = schedule(world, selections, direction, jit, displace=displace, jitter=jitter)
        field = world.value(np.stack(np.meshgrid(axis, axis, indexing="ij"), axis=-1))
        for col, g in enumerate(grids):
            ax = axes[row, col]
            ax.imshow(field.T, origin="lower", extent=(0, 1, 0, 1), cmap="Greys", vmin=0, vmax=world.vmax * 1.05)
            ax.plot(*g["cells"].T, "o", color="#1f77b4", markersize=6)
            lo, hi = g["cells"].min(axis=0), g["cells"].max(axis=0)
            ax.plot([lo[0], hi[0], hi[0], lo[0], lo[0]], [lo[1], lo[1], hi[1], hi[1], lo[1]], "--", color="#1f77b4", linewidth=1)
            ax.plot(*world.peak, "*", color="gold", markeredgecolor="black", markersize=13)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_title(f"selection {col + 1}: spacing {g['s']:.2f}\nbest cell {g['values'].max() / world.vmax:.2f} of peak", fontsize=9)
            if col == 0:
                ax.set_ylabel(f"{session}\ncolour", fontsize=9)
            if row == len(sessions) - 1:
                ax.set_xlabel("shape")
    fig.suptitle(f"Fixed schedule: broad grid at selection 1, then zoom and shift toward the peak (star) by a fixed amount; the target is displaced {displace:g} fine spacings in a random "
                 f"direction per participant, jitter up to {jitter:g} spacing (blue: the nine bushes)")
    return fig


def main():
    ap = argparse.ArgumentParser(description="Fixed-schedule selection grids.")
    ap.add_argument("mode", choices=["figure"])
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--selections", type=int, default=6)
    ap.add_argument("--displace", type=float, default=2.0)
    ap.add_argument("--jitter", type=float, default=1.0)
    ap.add_argument("--out", default=str(DOCS / "fixed_grid_schedule.png"))
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    figure(args.sessions, args.selections, args.displace, args.jitter).savefig(out, dpi=85)
    print(out)


if __name__ == "__main__":
    main()
