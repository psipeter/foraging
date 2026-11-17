"""A gallery of value maps: one heatmap for each complexity class (additive, multiplicative, non-separable) at each Gini, to see what the sparsity knob does to the map.

    ./venv/bin/python scripts/map_gallery.py [--ginis 0.3,0.4,0.5,0.6,0.7] [--gains results/independence_m4b.jsonl] [--out docs/value_map_gallery.png]

Each map is calibrated by `value_maps.calibrate_map` to its Gini and to the interaction of its class (the design of `independence.py`: additive a Gaussian exactly on a corner, its interaction the smallest that leaves; multiplicative 90 percent of what an aligned map of
that Gini can reach; non-separable 0.4). With `--gains` (an independence run) the map is drawn at the gain a session of that Gini needs to hold the anchor (a straight line fitted to the run), on the
fixed 0 to 9 scale of a fruit's pay, so the picture shows the level as well as the shape; without it the gain is 1.
"""

import argparse
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np

import independence as ind
import value_maps as vm

ROOT = Path(__file__).resolve().parent.parent
CLASSES = (("additive", "corner"), ("multiplicative", "aligned"), ("non-separable", "rotated"))


def interaction_of(name, gini):
    """The interaction asked of a class at a Gini (the design of independence.py)."""
    return {"additive": None, "multiplicative": ind.MULTIPLICATIVE_SHARE_OF_CAP * ind.aligned_cap(gini), "non-separable": 0.4}[name]


def one(args):
    (name, klass), gini = args
    return vm.calibrate_map(gini, interaction_of(name, gini), klass, share=(0.3, 0.7) if klass == "corner" else (0.25, 0.75))


def gain_line(path):
    """(slope, intercept) of the gain on the Gini of the realised sessions of an independence run (no sessions: gain 1)."""
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    ok = [r for r in rows if r["ok"] and r["map"]["gini"] <= 0.62]
    return tuple(np.polyfit([r["map"]["gini"] for r in ok], [r["gain"] for r in ok], 1)) if len(ok) > 3 else (0.0, 1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ginis", default="0.3,0.4,0.5,0.6,0.7")
    ap.add_argument("--gains", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "docs" / "value_map_gallery.png"))
    args = ap.parse_args()
    ginis = [float(g) for g in args.ginis.split(",")]
    slope, intercept = gain_line(args.gains) if args.gains else (0.0, 1.0)
    jobs = [(c, g) for c in CLASSES for g in ginis]
    cache = ROOT / "results" / "map_gallery_maps_v2.json"
    saved = json.loads(cache.read_text()) if cache.exists() else {}
    key = lambda job: f"{job[0][0]}@{job[1]}"
    todo = [j for j in jobs if key(j) not in saved]
    if todo:
        with mp.Pool(args.workers) as pool:
            for job, m in zip(todo, pool.map(one, todo)):
                saved[key(job)] = m.to_json()
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(saved))
    maps = [vm.ValueMap.from_json(saved[key(j)]) for j in jobs]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(CLASSES), len(ginis), figsize=(2.3 * len(ginis) + 1.2, 2.5 * len(CLASSES) + 0.9), sharex=True, sharey=True)
    for (cls, g), m, ax in zip(jobs, maps, axes.ravel()):
        gain = slope * g + intercept
        scaled = vm.ValueMap(m.bumps, m.noise, {"type": "gain", "value": float(gain)})
        axis, r = scaled.grid()
        image = ax.imshow(r.T, origin="lower", extent=(0, 1, 0, 1), cmap="Blues", vmin=0, vmax=9)
        d = scaled.descriptors()
        ax.set_title(f"Gini {d['gini']:.2f}, interaction {d['interaction']:.2f}\npeak {d['max']:.1f}, {100 * d['fraction_above_half_max']:.0f}% above half", fontsize=7.5, loc="left")
        ax.tick_params(labelsize=7)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    for ax, (name, _) in zip(axes[:, 0], CLASSES):
        ax.set_ylabel(f"{name}\ncolour", fontsize=9)
    for ax in axes[-1]:
        ax.set_xlabel("shape", fontsize=8)
    fig.suptitle("Value maps by sparsity (columns) and class (rows); colour is the expected pay of a fruit, 0 to 9; 'above half' is the share of the plane above half the peak" + ("" if args.gains else " (gain 1)"), fontsize=10, x=0.01, ha="left")
    cbar = fig.colorbar(image, ax=axes, shrink=0.8, pad=0.02)
    cbar.set_label("points per fruit", fontsize=8)
    cbar.ax.tick_params(labelsize=7)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=200, bbox_inches="tight", facecolor="white")
    print("saved", args.out)


if __name__ == "__main__":
    main()
