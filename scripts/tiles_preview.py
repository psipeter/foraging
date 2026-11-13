"""A picture of a tiles world: the ground height, the bushes coloured by their true value, the start and the tile numbers of the clusters.

    ./venv/bin/python scripts/tiles_preview.py <session asset> [--seed N] [--out file.png] [--set name=value ...]
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import world


def plot_world(w, path):
    """Height map (valley only), bushes by value, the start, in one PNG."""
    half = float(w.params.world_half_extent)
    axis = np.linspace(-half, half, 351)
    gx, gz = np.meshgrid(axis, axis, indexing="ij")
    height = w.terrain.elevation(gx, gz)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(height.T, origin="lower", extent=(-half, half, -half, half), cmap="terrain", alpha=0.8)
    sc = ax.scatter(w.pos[:, 0], w.pos[:, 1], c=w.value, cmap="plasma", s=18, edgecolor="k", linewidth=0.3)
    ax.plot([w.start[0]], [w.start[1]], marker="*", color="red", markersize=14, linestyle="")
    fig.colorbar(sc, ax=ax, shrink=0.7, label="bush value (points per fruit)")
    ax.set_title(f"{w.params.session_name} seed {w.seed}: {w.n} bushes")
    ax.set_aspect("equal")
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="tiles_preview.png")
    ap.add_argument("--set", nargs="*", default=[], help="session overrides, name=value")
    args = ap.parse_args()
    overrides = {}
    for item in args.set:
        key, value = item.split("=", 1)
        overrides[key] = float(value) if value.replace(".", "", 1).lstrip("-").isdigit() else value
    plot_world(world.make_world(args.session, args.seed, **overrides), Path(args.out))


if __name__ == "__main__":
    main()
