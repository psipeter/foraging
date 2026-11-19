"""How the agents' points and bushes per patch change with the walk between patches, on the realised maps of an experiment.

    ./venv/bin/python scripts/travel_scan.py PCX [--times 3-9] [--worlds 12] [--workers 6] [--out results/travel_scan_PCX]

Each session of `design/realized/<code>.json` keeps its map, gain and placement as realised; only the tile radius changes (`factors.travel_time_settings`, the walk across the gap between clusters in
seconds), so the gains are NOT re-solved for the anchor and the points move with the layout. The five agents of `agent_benchmark.py` play `--worlds` worlds of each (session, time); the result is
a CSV (points, bushes per patch and their standard errors, the tile count), a Markdown table and a figure beside it.
"""

import argparse
import csv
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np

import agent_benchmark as ab
import cells
import factors
import plots
import world

ROOT = Path(__file__).resolve().parent.parent


def jobs_of(code, times, n_worlds):
    data = json.loads((cells.REALIZED / f"{code}.json").read_text())
    ok = [c for c in data["cells"] if c["status"] == "ok"]
    session, jobs = data.get("session", "FOR_S1"), []
    for i, c in enumerate(ok, 1):
        duration = c.get("duration", data.get("duration", 120.0))
        for t in times:
            base = world.load_session(session, session_duration=float(duration))
            cell = {**c, "settings": {**c["settings"], **factors.travel_time_settings(base, float(t))}}
            jobs.append((code, f"{code}_S{i}@{t:g}s", session, duration, cell, n_worlds))
    return jobs


def parse_times(text):
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("code")
    ap.add_argument("--times", default="3-9")
    ap.add_argument("--worlds", type=int, default=12)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    times = parse_times(args.times)
    out = Path(args.out) if args.out else ROOT / "results" / f"travel_scan_{args.code}"
    jobs = jobs_of(args.code, times, args.worlds)
    with mp.Pool(max(1, min(args.workers, len(jobs)))) as pool:
        results = pool.map(ab.play, jobs)
    rows = []
    for (code, name, *_), r in zip(jobs, results):
        session, t = name.split("@")
        for a in ab.AGENTS:
            (pm, ps), (bm, bs) = ab.stats(r["points"][a]), ab.stats(r["bushes"][a])
            rows.append({"session": session, "travel_s": float(t[:-1]), "agent": a, "points": pm, "points_se": ps, "bushes_per_patch": bm, "bushes_se": bs, "tiles": r["n_tiles"], "worlds": r["n_worlds"]})
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out.with_suffix(".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    sessions = list(dict.fromkeys(r["session"] for r in rows))
    lines = [f"# {args.code}: agents against the walk between patches", "",
             f"Maps, gains and placement as realised; only the tile radius changes (gains not re-solved). {args.worlds} worlds per cell; mean points / bushes per patch.", ""]
    for s in sessions:
        lines += [f"## {s}", "", "| travel (s) | tiles | " + " | ".join(ab.LABELS[a] for a in ab.AGENTS) + " |", "|---:|---:|" + "---:|" * len(ab.AGENTS)]
        for t in times:
            sel = {r["agent"]: r for r in rows if r["session"] == s and r["travel_s"] == t}
            lines.append(f"| {t:g} | {sel['mvt']['tiles']} | " + " | ".join(f"{sel[a]['points']:.0f} / {sel[a]['bushes_per_patch']:.1f}" for a in ab.AGENTS) + " |")
        lines.append("")
    out.with_suffix(".md").write_text("\n".join(lines))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, len(sessions), figsize=(3.4 * len(sessions) + 1.0, 6.2), sharex=True, squeeze=False)
    for col, s in enumerate(sessions):
        for k, a in enumerate(ab.AGENTS):
            sel = sorted((r for r in rows if r["session"] == s and r["agent"] == a), key=lambda r: r["travel_s"])
            for row, key in enumerate(("points", "bushes_per_patch")):
                axes[row, col].errorbar([r["travel_s"] for r in sel], [r[key] for r in sel], yerr=[r[key + "_se" if key == "points" else "bushes_se"] for r in sel], color=plots.SERIES[k],
                                        linestyle=plots.STYLES[k], linewidth=1.6, marker="o", markersize=3, label=ab.LABELS[a])
        axes[0, col].set_title(s, fontsize=9, loc="left")
        axes[1, col].set_xlabel("walk between patches (s)", fontsize=8)
    axes[0, 0].set_ylabel("points", fontsize=8)
    axes[1, 0].set_ylabel("bushes per patch", fontsize=8)
    axes[0, 0].legend(fontsize=6.5, frameon=False)
    for a in axes.ravel():
        a.tick_params(labelsize=8)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(out.with_suffix(".png"), dpi=200)
    print(out.with_suffix(".md").read_text())
    print(f"\nfiles {out}.csv, .md, .png")


if __name__ == "__main__":
    main()
