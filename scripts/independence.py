"""The independence test of the session knobs (docs/SESSION_FACTORS_PLAN.md, milestone 4): realise sessions at a space-filling set of knob settings and see which factors move together.

    ./venv/bin/python scripts/independence.py run --tag T [--n 40] [--session FOR_S1] [--workers 3]
    ./venv/bin/python scripts/independence.py report --tag T
    ./venv/bin/python scripts/independence.py plot --tag T [--out docs/independence_correlations.png]

`run` appends one JSON line per session to `results/independence_<tag>.jsonl` (flat, gitignored): the knobs asked, then either the realised session (map descriptors, gain, layout, the factors and
points measured on fresh worlds, whether the anchor was met, whether a ranking pool could be built) or the reason it could not be made (an unreachable pair, a gain
that does not settle). A rerun with the same tag skips the settings already done. `report` prints the failures, the correlation matrix of the realised factors and the side effects of each knob.

The knobs (the PI's ranges, 2026-11-17): Gini 0.3 to 0.7 (0.2 to 0.8 in the first runs: 0.2 is too undifferentiated to learn from, and above 0.7 few classes stay under the cap); travel time 3 to 12 s (within-patch diversity is no longer a knob: the pool is placed at random, 2026-11-18); complexity in the three classes of the ladder (
additive: a Gaussian exactly on a corner, round or stretched 2:1 or 3:1 along shape or colour (the interaction is what that gives, 0.05 to 0.3 with the Gini); multiplicative: aligned, an interaction of 90 percent of what an aligned map of that Gini can reach; non-separable: rotated, an interaction of 0.15 to 0.65).
"""

import argparse
import json
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np

import factors
import value_maps

ROOT = Path(__file__).resolve().parent.parent
RANGES = {"gini": (0.3, 0.7), "travel_time": (3.0, 12.0)}
ROTATED_INTERACTION = (0.15, 0.65)
MULTIPLICATIVE_SHARE_OF_CAP = value_maps.MULTIPLICATIVE_SHARE_OF_CAP
aligned_cap = value_maps.aligned_cap
CLASSES = ("additive", "multiplicative", "nonseparable")


def design(n=40, seed=0):
    """`n` knob settings spread evenly over the ranges (a Latin hypercube over Gini, class, the position within the class and travel time)."""
    from scipy.stats import qmc
    out = []
    rng = np.random.default_rng(seed)
    for gu, cu, iu, tu in qmc.LatinHypercube(d=4, seed=seed).random(n):
        gini = RANGES["gini"][0] + gu * (RANGES["gini"][1] - RANGES["gini"][0])
        name = CLASSES[min(int(cu * 3), 2)]
        corner = [int(c) for c in rng.integers(0, 2, 2)]                     # which feature pays more when higher: a nuisance, drawn for every setting
        aspect = value_maps.corner_aspect(rng.choice(value_maps.CORNER_STRETCHES), bool(rng.integers(2)))     # the stretch of an additive map (round, 2:1, 3:1), along shape or colour: a nuisance
        if name == "additive":
            klass, interaction = "corner", None
        elif name == "multiplicative":
            klass, interaction = "aligned", MULTIPLICATIVE_SHARE_OF_CAP * aligned_cap(gini)
        else:
            klass, interaction = "rotated", ROTATED_INTERACTION[0] + iu * (ROTATED_INTERACTION[1] - ROTATED_INTERACTION[0])
        out.append({"gini": round(float(gini), 3), "class": name, "klass": klass, "interaction": None if interaction is None else round(float(interaction), 3), "corner": corner, "aspect": round(aspect, 4),
                    "travel_time": round(float(RANGES["travel_time"][0] + tu * (RANGES["travel_time"][1] - RANGES["travel_time"][0])), 2)})
    return out


def pool_builds(session, valuemap, settings):
    """Whether the ranking pool of the session can be built (sparse maps leave many bushes tied near zero); True, or the error text."""
    import ranking
    try:
        ranking.generate_pool(session, **settings, **valuemap.compile())
        return True
    except ValueError as e:
        return str(e)[:160]


def run_one(args):
    session, knobs, check_pool, max_peak = args
    t = time.time()
    row = {"knobs": knobs}
    try:
        r = factors.realize(session, knobs["gini"], knobs["interaction"], knobs["klass"], knobs["travel_time"], max_peak=max_peak, corner=tuple(float(c) for c in knobs.get("corner", (1, 1))), aspect=knobs.get("aspect", 1.0))
    except ValueError as e:
        row.update(ok=False, reason=str(e)[:240], seconds=round(time.time() - t))
        return row
    d = r["map"].descriptors()
    row.update(ok=True, within_tolerance=r["within_tolerance"], gain=r["map"].gain(), settings=r["settings"], map={k: d[k] for k in ("gini", "interaction", "log_interaction", "shape_share", "max", "mean")},
               factors=r["achieved"]["factors"], points=r["achieved"]["points"], pool=pool_builds(session, r["map"], r["settings"]) if check_pool else None, seconds=round(time.time() - t))
    return row


def done(path):
    return {json.dumps(json.loads(line)["knobs"], sort_keys=True) for line in path.read_text().splitlines()} if path.exists() else set()


def run(args):
    path = ROOT / "results" / f"independence_{args.tag}.jsonl"
    path.parent.mkdir(exist_ok=True)
    todo = [k for k in design(args.n) if json.dumps(k, sort_keys=True) not in done(path)]
    print(f"{len(todo)} of {args.n} sessions to realise, {args.workers} at a time -> {path}", flush=True)
    with mp.Pool(args.workers) as pool, path.open("a") as out:
        for i, row in enumerate(pool.imap_unordered(run_one, [(args.session, k, not args.no_pool, args.max_peak) for k in todo]), 1):
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(f"{i}/{len(todo)} {row['knobs']['class']:14s} gini {row['knobs']['gini']:.2f} travel {row['knobs']['travel_time']:5.1f}: " +
                  (f"ok, gain {row['gain']:.2f}, nearest {row['points']['nearest'][0]:.0f}" + ("" if row["within_tolerance"] else " (anchor missed)") if row["ok"] else "FAILED " + row["reason"][:90]) + f" ({row['seconds']} s)", flush=True)


def table(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    ok = [r for r in rows if r["ok"]]
    names = ["gini", "interaction", "travel_time", "diversity", "contrast", "mean_bush_value", "max_bush_value", "n_tiles", "gain", "nearest", "learner", "oracle", "headroom"]
    cols = {
        "gini": [r["map"]["gini"] for r in ok], "interaction": [r["map"]["interaction"] for r in ok], "travel_time": [r["factors"]["travel_time"][0] for r in ok],
        "diversity": [r["factors"]["diversity"][0] for r in ok], "contrast": [r["factors"]["contrast"][0] for r in ok], "mean_bush_value": [r["factors"]["mean_bush_value"][0] for r in ok],
        "max_bush_value": [r["map"]["max"] for r in ok], "n_tiles": [r["factors"]["n_tiles"][0] for r in ok], "gain": [r["gain"] for r in ok],
        "nearest": [r["points"]["nearest"][0] for r in ok], "learner": [r["points"].get("learner", (float("nan"), 0.0))[0] for r in ok], "oracle": [r["points"]["oracle"][0] for r in ok],
    }
    cols["headroom"] = [o / n for o, n in zip(cols["oracle"], cols["nearest"])]
    return rows, ok, names, np.array([cols[n] for n in names])


def report(args):
    path = ROOT / "results" / f"independence_{args.tag}.jsonl"
    rows, ok, names, data = table(path)
    print(f"{len(rows)} sessions asked, {len(ok)} realised, {sum(r['within_tolerance'] for r in ok)} within the anchor tolerance, {sum(r['pool'] is True for r in ok)} with a ranking pool")
    for r in rows:
        if not r["ok"]:
            print("  FAILED", {k: r["knobs"][k] for k in ("class", "gini", "interaction", "travel_time")}, r["reason"][:110])
    for r in ok:
        if r["pool"] not in (True, None):
            print("  NO POOL", {k: r["knobs"][k] for k in ("class", "gini", "travel_time")}, r["pool"])
    if len(ok) < 4:
        return
    corr = np.corrcoef(data)
    print("\ncorrelation of the realised factors (" + str(len(ok)) + " sessions):")
    print(" " * 16 + "".join(f"{n[:7]:>8s}" for n in names))
    for i, n in enumerate(names):
        print(f"{n:16s}" + "".join(f"{corr[i, j]:8.2f}" for j in range(len(names))))
    peak, gini = data[names.index("max_bush_value")], data[names.index("gini")]
    print(f"\nthe best bush (cap {factors.MAX_PEAK}): " + "; ".join(f"Gini {lo:.1f} to {hi:.1f}: mean {peak[m].mean():.1f}, max {peak[m].max():.1f}, {int((peak[m] > factors.MAX_PEAK).sum())} of {int(m.sum())} over" for lo, hi in ((0.2, 0.4), (0.4, 0.6), (0.6, 0.8)) for m in [(gini >= lo) & (gini < hi)] if m.any()))
    fruit = [r["factors"].get("share_fruit_over_cap", (float("nan"), 0))[0] for r in ok]
    print(f"fruits over {factors.FRUIT_CAP}: mean share {np.nanmean(fruit):.4f}, worst session {np.nanmax(fruit):.4f}")
    anchor = data[names.index(factors.ANCHOR_AGENT)]
    print(f"\nthe anchor: {factors.ANCHOR_AGENT} points {anchor.mean():.0f} +- {anchor.std():.0f} (target {factors.anchor_points(120.0):.0f}), travel time within {np.abs(data[2] - np.array([r['knobs']['travel_time'] for r in ok])).max():.3f} s of its target")


def plot(args):
    """The correlation matrix of the realised factors (a diverging scale, grey at 0, the number in every cell) into `--out`."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _, ok, names, data = table(ROOT / "results" / f"independence_{args.tag}.jsonl")
    corr = np.corrcoef(data)
    fig, ax = plt.subplots(figsize=(8.2, 7.0))
    image = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(names)), names, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(len(names)), names, fontsize=9)
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, f"{corr[i, j]:.2f}", ha="center", va="center", fontsize=7.5, color="white" if abs(corr[i, j]) > 0.6 else "#1f2933")
    ax.axhline(2.5, color="black", lw=0.8)
    ax.axvline(2.5, color="black", lw=0.8)
    fig.colorbar(image, ax=ax, shrink=0.8).set_label("correlation across sessions", fontsize=9)
    ax.set_title(f"Realised factors of {len(ok)} sessions: the three knobs (top left block) and what moves with them", fontsize=10, loc="left")
    fig.savefig(args.out, dpi=200, bbox_inches="tight", facecolor="white")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["run", "report", "plot"])
    ap.add_argument("--out", default=str(ROOT / "docs" / "independence_correlations.png"))
    ap.add_argument("--tag", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--session", default="FOR_S1")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-pool", action="store_true", help="skip the ranking-pool check")
    ap.add_argument("--max-peak", type=lambda t: None if t == "none" else float(t), default=factors.MAX_PEAK, help="refuse a session whose best bush is worth more (default factors.MAX_PEAK; `none` records every session, to find the Gini ceiling)")
    args = ap.parse_args()
    {"run": run, "report": report, "plot": plot}[args.command](args)


if __name__ == "__main__":
    main()
