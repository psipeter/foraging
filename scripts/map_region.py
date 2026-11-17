"""Which (sparsity, complexity) pairs the Gaussian family of `value_maps` can make (docs/SESSION_FACTORS_PLAN.md, milestone 3, step 1): sample the family, describe each map, and show
the reachable region of (Gini, interaction), the two numbers the map calibrator will be asked to hit.

    ./venv/bin/python scripts/map_region.py [--n 6000] [--seed 0] [--out docs/value_map_region.png]

The family: a Gaussian with its centre anywhere on the plane (a corner or an edge a fifth of the time), a short axis `across` from 0.05 to 1.5, an `aspect` from 1 to 6 and an angle (axis-aligned half
the time, else 0 to 90 degrees; the other signs mirror these). Everything is computed on the grid of `value_maps` (61 x 61 here, which is within 2 percent of the 101 x 101 of the reference examples).
"""

import argparse
from pathlib import Path

import numpy as np

import value_maps as vm

GRID = 61
BINS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
AXIS_ALIGNED = 0.05          # a log interaction below this counts as axis-aligned (multiplicative or additive), above as turned (non-separable)


def sample(n, seed=0):
    """`n` maps of the family: a list of (parameters, descriptors)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        centre = rng.uniform(0.0, 1.0, 2)
        if rng.uniform() < 0.2:
            centre = np.where(rng.uniform(size=2) < 0.5, 0.0, 1.0) if rng.uniform() < 0.5 else np.array([rng.choice([0.0, 1.0]), rng.uniform()])[rng.permutation(2)]
        p = {"centre_shape": float(centre[0]), "centre_color": float(centre[1]), "across": float(np.exp(rng.uniform(np.log(0.05), np.log(1.5)))),
             "aspect": float(np.exp(rng.uniform(0.0, np.log(6.0)))), "angle": 0.0 if rng.uniform() < 0.5 else float(rng.uniform(0.0, 90.0))}
        d = vm.gaussian(p["centre_shape"], p["centre_color"], p["across"], p["aspect"], p["angle"]).descriptors(GRID)
        out.append((p, d))
    return out


def summarise(samples):
    """Per Gini bin, the interaction reachable by axis-aligned and by turned maps: {bin: (n_aligned, lo, hi, n_turned, lo, hi)}."""
    gini = np.array([d["gini"] for _, d in samples])
    inter = np.array([d["interaction"] for _, d in samples])
    turned = np.array([d["log_interaction"] > AXIS_ALIGNED for _, d in samples])
    rows = {}
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        inside = (gini >= lo) & (gini < hi)
        row = []
        for mask in (inside & ~turned, inside & turned):
            row += [int(mask.sum()), float(inter[mask].min()) if mask.any() else np.nan, float(inter[mask].max()) if mask.any() else np.nan]
        rows[(lo, hi)] = tuple(row)
    return rows


def plot(samples, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from plots import SERIES
    import value_map_examples
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    gini = np.array([d["gini"] for _, d in samples])
    inter = np.array([d["interaction"] for _, d in samples])
    turned = np.array([d["log_interaction"] > AXIS_ALIGNED for _, d in samples])
    ax.scatter(gini[~turned], inter[~turned], s=8, alpha=0.35, color=SERIES[0], marker="o", linewidths=0, label="axis-aligned (additive or multiplicative)")
    ax.scatter(gini[turned], inter[turned], s=10, alpha=0.35, color=SERIES[1], marker="^", linewidths=0, label="rotated (non-separable)")
    for name, d in value_map_examples.table().items():
        ax.scatter([d["gini"]], [d["interaction"]], s=70, facecolors="white", edgecolors="black", linewidths=1.5, zorder=3)
        ax.annotate(name, (d["gini"], d["interaction"]), textcoords="offset points", xytext=(7, 5), fontsize=9)
    ax.set_xlabel("sparsity: Gini of the map over the feature plane", fontsize=10)
    ax.set_ylabel("complexity: interaction (1 - R^2 of an additive fit)", fontsize=10)
    ax.set_title("Reachable (sparsity, complexity) of the Gaussian family; open circles: the reference examples", fontsize=10, loc="left")
    ax.legend(fontsize=9, frameon=False, loc="upper right", markerscale=2.0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "value_map_region.png"))
    args = ap.parse_args()
    samples = sample(args.n, args.seed)
    print("Gini bin     axis-aligned: n   interaction range       rotated: n   interaction range")
    for (lo, hi), (na, alo, ahi, nt, tlo, thi) in summarise(samples).items():
        a = f"{alo:5.2f} to {ahi:5.2f}" if na else "      -      "
        t = f"{tlo:5.2f} to {thi:5.2f}" if nt else "      -      "
        print(f"{lo:.1f} - {hi:.1f}   {na:14d}   {a}     {nt:11d}   {t}")
    plot(samples, args.out)
    print("saved", args.out)


if __name__ == "__main__":
    main()
