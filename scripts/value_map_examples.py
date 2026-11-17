"""One reference example of each rung of the ladder (docs/SESSION_FACTORS_PLAN.md, 7.2): the maps, their separability descriptors and a figure.

    ./venv/bin/python scripts/value_map_examples.py [--out docs/value_map_examples.png]

The parameters are a proposal for a reference guide, not a design: the same centre for the two Gaussians, so that rotation and stretch are the only differences between them;
the additive proxy in the corner where both features pay most. Descriptors are those of `value_maps.descriptors` (the grid of 101 x 101 over the unit plane).
"""

import argparse
from pathlib import Path

import value_maps as vm

EXAMPLES = {
    "additive": ("Additive\nwide corner", vm.wide_corner((1.0, 1.0), shape_share=0.6, base=0.7)),                  # 60 percent of the slope on shape, the spreads' geometric mean 0.7
    "multiplicative": ("Multiplicative\naxis-aligned, stretched", vm.gaussian(0.55, 0.45, 0.15, 1.5, 0.0)),
    "nonseparable": ("Non-separable\nrotated, stretched", vm.gaussian(0.55, 0.45, 0.15, 3.0, 45.0)),
}
SHOWN = (("interaction", "interaction"), ("log_interaction", "log interaction"), ("nonlinearity", "nonlinearity"), ("gini", "Gini"))


def table():
    return {name: m.descriptors() for name, (_, m) in EXAMPLES.items()}


def plot(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, muted = "#1f2933", "#52606d"
    fig, axes = plt.subplots(1, 3, figsize=(10.8, 5.0), sharey=True)
    for ax, (name, (title, m)) in zip(axes, EXAMPLES.items()):
        axis, r = m.grid()
        image = ax.imshow(r.T, origin="lower", extent=(0, 1, 0, 1), cmap="Blues", vmin=0, vmax=4.0)
        d = m.descriptors()
        ax.set_title(title, fontsize=11, color=ink, loc="left")
        ax.set_xlabel("shape\n" + "   ".join(f"{label} {d[key]:.2f}" for key, label in SHOWN[:2]) + "\n" + "   ".join(f"{label} {d[key]:.2f}" for key, label in SHOWN[2:]), fontsize=9, color=ink)
        ax.tick_params(labelsize=9, colors=muted)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("colour", fontsize=10, color=ink)
    cbar = fig.colorbar(image, ax=axes, shrink=0.8, pad=0.02)
    cbar.set_label("expected reward per fruit", fontsize=9, color=ink)
    cbar.ax.tick_params(labelsize=9, colors=muted)
    fig.suptitle("Each map is one Gaussian (interaction: 1 - R^2 of an additive fit to the map; log interaction: of the log map)", fontsize=10, color=muted, x=0.06, y=0.97, ha="left")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "value_map_examples.png"))
    args = ap.parse_args()
    for name, d in table().items():
        print(f"{name:15s} " + "  ".join(f"{label} {d[key]:.3f}" for key, label in SHOWN) + f"  shape share {d['shape_share']:.2f}  range {d['range']:.2f}  mean {d['mean']:.2f}")
    plot(args.out)
    print("saved", args.out)


if __name__ == "__main__":
    main()
