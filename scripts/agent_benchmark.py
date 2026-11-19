"""Five agents on the realised sessions of an experiment: points earned and bushes harvested per patch, as a table.

    ./venv/bin/python scripts/agent_benchmark.py PCX FOR TUT [--worlds 20] [--workers 3] [--out docs/pilots/agents.md]

For each session of `design/realized/<code>.json`, `--worlds` worlds (the session's own world seed first, then seeds 1000 up) are played by

    nearest   the nearest-bush forager (`agents.NearestAgent`: no learning, no value)
    learner   the delta-rule learner with the standard rate actor (`agents.DeltaRuleAgent`: the map from the view cone, the value learned)
    top-k     the best fixed number of bushes per patch, k of 1 to 9 chosen on each world after the fact (`tile_calibration.TileTopK`, an oracle: true values, tuned with hindsight)
    thr-q     the best value threshold, a percentile q of the world's bush values chosen the same way (`tile_calibration.TileThreshold`)
    mvt       the marginal value theorem at the optimal long-run rate (`patch_foraging`, true values, no tuning on the world: the rate comes from the model)

and each agent's mean points and mean bushes per patch visit (`tile_calibration.route_stats`) are reported with their standard errors across worlds. The table is Markdown (`--out`), the numbers a
CSV beside it. top-k and thr-q are tuned with hindsight, so they are an empirical ceiling of their family; `mvt` is parameter-free.
"""

import argparse
import csv
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np

import cells
import patch_foraging
import sim
import tile_calibration as tc
import value_maps
import world
from agents import REGISTRY

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ("nearest", "learner", "top-k", "thr-q", "mvt")
LABELS = {"nearest": "nearest", "learner": "learner (delta rule)", "top-k": "best top-k (hindsight)", "thr-q": "best thr-q (hindsight)", "mvt": "mvt (marginal value)"}
KS = tuple(range(1, 10))
QUANTILES = tuple(range(10, 100, 10))
EXTRA_SEEDS = 1000


def play(job):
    """One session: {agent: (points per world, bushes per patch per world)} and the chosen k and q per world."""
    code, name, session, duration, cell, n_worlds = job
    valuemap = value_maps.ValueMap.from_dict(cell["map"])
    params = world.load_session(session, session_duration=float(duration), **cell["settings"], **valuemap.compile())
    seeds = [int(cell["world_seed"])] + [EXTRA_SEEDS + i for i in range(n_worlds - 1)]
    points = {a: [] for a in AGENTS}
    bushes = {a: [] for a in AGENTS}
    chosen = {"top-k": [], "thr-q": []}
    for seed in seeds:
        w = world.generate_world(params, seed)
        tile_of, tile_ids = tc.tile_of_world(w)
        for a in ("nearest", "learner", "mvt"):
            r = patch_foraging.run(a, w) if a == "mvt" else sim.run_episode(REGISTRY[a](), w)
            points[a].append(r.total)
            bushes[a].append(tc.route_stats(r, tile_of, w.value)["per_visit"])
        table = tc.calibrate_world(w, list(KS), QUANTILES)
        for a, prefix in (("top-k", "top-"), ("thr-q", "thr-")):
            best = max((n for n in table if n.startswith(prefix)), key=lambda n: table[n][0])
            points[a].append(table[best][0])
            bushes[a].append(table[best][1]["per_visit"])
            chosen[a].append(int(best[len(prefix):]))
    return {"code": code, "session": name, "knobs": cell["knobs"], "points": points, "bushes": bushes, "chosen": chosen, "n_worlds": len(seeds), "n_tiles": int(tile_ids.size)}


def jobs_of(code, n_worlds):
    data = json.loads((cells.REALIZED / f"{code}.json").read_text())
    ok = [c for c in data["cells"] if c["status"] == "ok"]
    return [(code, f"{code}_S{i}", data.get("session", "FOR_S1"), c.get("duration", data.get("duration", 120.0)), c, n_worlds) for i, c in enumerate(ok, 1)]


def stats(x):
    x = np.asarray(x, dtype=float)
    return float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("nan")


def markdown(results):
    """One table per experiment: a row per agent, the points and the bushes per patch of each session."""
    lines = ["# Agents on the realised sessions", "",
             "Mean points earned and mean bushes harvested per patch visit (± standard error across worlds) of five agents, from `scripts/agent_benchmark.py`. top-k and thr-q are tuned with hindsight on each world, mvt is not.", ""]
    for code in dict.fromkeys(r["code"] for r in results):
        rows = [r for r in results if r["code"] == code]
        lines += [f"## {code}", ""]
        lines.append("| agent | " + " | ".join(f"{r['session']} points | {r['session']} bushes/patch" for r in rows) + " |")
        lines.append("|---|" + "---:|---:|" * len(rows))
        for a in AGENTS:
            cols = []
            for r in rows:
                (pm, ps), (bm, bs) = stats(r["points"][a]), stats(r["bushes"][a])
                cols += [f"{pm:.0f} ± {ps:.0f}", f"{bm:.2f} ± {bs:.2f}"]
            lines.append(f"| {LABELS[a]} | " + " | ".join(cols) + " |")
        chosen = "; ".join(f"{r['session']}: top-{np.mean(r['chosen']['top-k']):.1f}, thr-{np.mean(r['chosen']['thr-q']):.0f}" for r in rows)
        knobs = "; ".join(f"{r['session']}: " + ", ".join(f"{k} {v}" for k, v in r["knobs"].items() if k in ("class", "gini", "travel_time", "interaction")) for r in rows)
        lines += ["", f"Worlds per session: {rows[0]['n_worlds']} (the session's own, then seeds {EXTRA_SEEDS} up). Mean k and q chosen: {chosen}.", f"Knobs: {knobs}.", ""]
    return "\n".join(lines)


def write_csv(results, path):
    with open(path, "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["code", "session", "agent", "worlds", "points_mean", "points_se", "bushes_per_patch_mean", "bushes_per_patch_se", "chosen_mean"])
        for r in results:
            for a in AGENTS:
                (pm, ps), (bm, bs) = stats(r["points"][a]), stats(r["bushes"][a])
                out.writerow([r["code"], r["session"], a, r["n_worlds"], f"{pm:.2f}", f"{ps:.2f}", f"{bm:.3f}", f"{bs:.3f}", f"{np.mean(r['chosen'][a]):.2f}" if a in r["chosen"] else ""])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--worlds", type=int, default=20)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "docs" / "pilots" / "agents.md"))
    args = ap.parse_args()
    jobs = [j for code in args.codes for j in jobs_of(code, args.worlds)]
    with mp.Pool(max(1, min(args.workers, len(jobs)))) as pool:
        results = pool.map(play, jobs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = markdown(results)
    out.write_text(text + "\n")
    write_csv(results, out.with_suffix(".csv"))
    print(text)
    print(f"\ntable {out}, numbers {out.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
