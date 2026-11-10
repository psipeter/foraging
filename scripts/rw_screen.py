"""Screening the RW peak parameters with the simulated agents (docs/EXPERIMENTS.md, RW build plan, phase 4).

Question: over the parameters that make an instance harder (how narrow the peaks are, how far apart, how close in height) and over the session's length, how often does an
agent find the peaks, and how much does it score? The answer picks the ranges of the pool and the sessions' durations before any asset exists.

    ./venv/bin/python scripts/rw_screen.py plan                        the cells (parameter combinations) and the size of the run; touches nothing
    ./venv/bin/python scripts/rw_screen.py run --tag T [--workers N]   plays the agents on every instance (resumable: instances already in the files are skipped)
    ./venv/bin/python scripts/rw_screen.py report --tag T              tables of score, found and trapped fractions by cell, agent and session length

**Instances.** A cell is a session type (one or two peaks over one or two paying features) with a spread level and, for two peaks, a separation (in spreads) and a height
ratio; `cells()` keeps only the combinations that are possible (the spread is at least what holds NARROWEST_EXPECTED bushes in a peak, and two peaks fit in the allowed box).
An instance is WORLDS_PER_CELL worlds of a cell: the world seed draws the terrain and the bushes (the plane-coverage assignment, `featureCoverage`), and a generator seeded by it
draws the peaks (and, for a one-feature cell, which feature pays); a world in which a peak holds fewer than MIN_PEAK_BUSHES bushes in its top-10% region is replaced by the next
seed (`attempts` in the instances file). The reward noise is the same everywhere (`rewardStd` 0.6), moisture is flat (the ground is the same everywhere, as in FN's early sessions).

**Session length** is a parameter scanned for free: each agent plays one episode of the longest length (DURATIONS[-1]) and the score at each shorter length is read from its fruit log,
which equals a shorter session for an agent whose choices do not depend on the session's length (`deadline_dependent` False; the others are refused here).

**Outputs** (flat files in results/, none of them in the results database, which keys a run to one environment and every instance here has its own reward function):
    results/rw_screen_<tag>_instances.csv     one row per instance: cell, world seed, attempts, which feature pays, the peaks, the sparsity at x = 10, 20, 30, the bushes in each peak
    results/rw_screen_<tag>_episodes.csv      one row per (instance, agent): the score at each length (`score_60` ... `score_240`) and, for each peak and for the top-10% and top-30%
                                              regions, the time of the first fruit from a bush in it (`first30_global`, empty if none) and how many fruits came from it (`n30_global`)
    results/rw_screen_<tag>_fruits.jsonl.gz   one line per episode: every fruit (time, bush, reward, region 0 none / 1 global / 2 local top-30%), so that a definition of "found" or
                                              "settled" can be changed afterwards without running anything again
"""

import argparse
import csv
import gzip
import json
import math
import sys
import time
from multiprocessing import Pool

import numpy as np

import agents
import rw_peaks
import sim
import synthetic
import world
from world import PROJECT_ROOT

RESULTS = PROJECT_ROOT / "results"
AGENTS = ("nearest", "learner", "softmax", "curious")
DURATIONS = tuple(range(60, 241, 30))                    # seconds: the lengths of session scanned (the longest is what is played)
WORLDS_PER_CELL = 30
BASE_SESSION = "FN_S1"                                   # the terrain, lighting and so on of the session assets the instances copy
SPREAD_LEVELS = 6                                        # spreads per type, geometrically spaced between the narrowest and the widest that is possible
SEPARATIONS = (3.0, 4.0, 5.0, 6.0, 8.0)                  # in spreads (two peaks)
HEIGHT_RATIOS = (0.3, 0.45, 0.6, 0.75, 0.9)              # local over global height (two peaks)
N_TYPICAL = 695                                          # bushes in a world, to find the narrowest spread (the worlds have 684 to 707)
REGION_X = (10, 30)                                      # the top-x% regions of a peak that "found" is read in
MAX_ATTEMPTS = 20                                        # world seeds tried for an instance before it is given up
REWARD_STD = 0.6
TYPES = ((1, 1), (1, 2), (2, 1), (2, 2))                 # (peaks, paying features)
PEAK_NAMES = ("global", "local")
DESIGN_GUARANTEE = (30, 3)                               # the session plan's guarantee (docs/EXPERIMENTS.md): at least 3 bushes in each peak's top-30% region; a grid cell keeps 5 in the top-10%
DESIGN_RATIO = 0.75                                      # local over global height in the session plan's two-peak cells
MODEL_C = {1: 0.355, 2: 0.50}                            # the discovery model fitted on rw2: P(found a region by t) = 1 - exp(-c t S), S the region's share of the feature space
# The session plan's ladder (docs/EXPERIMENTS.md, RW session plan): id, stage, features, peaks, total sparsity (the share of all bushes that pay at least 70% of the best, split equally over the
# peaks), session length in seconds, separation of the peaks in spreads. B: baseline at 15%; S: one peak, 15% and 5%; T: two peaks, 10% and 5% crossed with the separation.
LADDER = [("B1", "B", 1, 1, .15, 120, None), ("B2", "B", 2, 1, .15, 120, None), ("B3", "B", 1, 2, .15, 120, 3.0), ("B4", "B", 2, 2, .15, 120, 3.0),
          ("S2F-15", "S", 2, 1, .15, 180, None), ("S2F-5", "S", 2, 1, .05, 180, None),
          ("T2F-10-near", "T", 2, 2, .10, 180, 3.0), ("T2F-10-far", "T", 2, 2, .10, 180, 4.5), ("T2F-5-near", "T", 2, 2, .05, 180, 3.0), ("T2F-5-far", "T", 2, 2, .05, 180, 4.5)]
INSTANCE_FIELDS = ["instance", "cell", "k", "status", "world_seed", "attempts", "n_bushes", "paying", "spread", "centers", "heights", "sparsity10", "sparsity20", "sparsity30",
                   "bushes10", "separation", "height_ratio", "bushes30"]
EPISODE_FIELDS = (["instance", "agent", "id", "n_peaks", "dims", "level", "separation", "ratio", "spread"] + [f"score_{d}" for d in DURATIONS] + ["fruits"]
                  + [f"{kind}{x}_{name}" for x in REGION_X for name in PEAK_NAMES for kind in ("first", "n")] + ["stage", "total", "length"])       # fixed: a file's columns must not depend on which row came first
MAX_ERROR_SHARE = 0.05                                   # a run stops when more than this share of its instances (after the first 200) failed: something is wrong, not one world


def spread_levels(dims, n_peaks, n=N_TYPICAL, levels=None):
    """The spreads of a type: SPREAD_LEVELS values, geometrically spaced from the narrowest that holds the guaranteed bushes to the widest that is possible (one peak: the margin's
    cap; two peaks: the widest at which two peaks at the least separation fit in the allowed box)."""
    low = rw_peaks.narrowest_spread(n, dims, rw_peaks.NARROWEST_EXPECTED)
    high = 0.9 * rw_peaks.MAX_SPREAD
    if n_peaks == 2:
        if not rw_peaks.fits(low, dims, rw_peaks.MIN_SEPARATION):
            raise ValueError(f"two peaks do not fit at the narrowest spread {low:.3f} ({dims} features)")
        lo, hi = low, high
        for _ in range(60):                                                  # the widest spread at which two peaks at the least separation still fit
            mid = (lo + hi) / 2.0
            lo, hi = (mid, hi) if rw_peaks.fits(mid, dims, rw_peaks.MIN_SEPARATION) else (lo, mid)
        high = lo
    return [float(v) for v in np.geomspace(low, high, levels or SPREAD_LEVELS)]


def cells(n=N_TYPICAL, levels=None, separations=None, ratios=None):
    """The possible parameter combinations (spread level x separation x height ratio, fully crossed for two peaks), each a dict with an `id` and an `index`. The arguments default
    to the module's grid."""
    separations, ratios = separations or SEPARATIONS, ratios or HEIGHT_RATIOS
    out = []
    for n_peaks, dims in TYPES:
        for level, spread in enumerate(spread_levels(dims, n_peaks, n, levels)):
            if n_peaks == 1:
                out.append({"n_peaks": 1, "dims": dims, "level": level, "spread": spread, "separation": None, "ratio": None, "id": f"1p{dims}f_s{level}"})
                continue
            for separation in separations:
                if rw_peaks.fits(spread, dims, separation):
                    for ratio in (r for r in ratios if rw_peaks.separable(separation, r)):
                        out.append({"n_peaks": 2, "dims": dims, "level": level, "spread": spread, "separation": separation, "ratio": ratio,
                                    "id": f"2p{dims}f_s{level}_d{separation:g}_r{ratio:g}"})
    for i, cell in enumerate(out):
        cell["index"] = i
    return out


def design_cells(name="ladder"):
    """The cells of a named design (DESIGNS), the same dict as `cells` gives plus `stage`, `total` (the sparsity), `length`, `guarantee` and `margin`; each spread follows from the peak's own
    share (total / peaks) at the top-30% region, and each must fit the feature plane and be two hills. An entry may end with a height ratio (default DESIGN_RATIO) and a margin in spreads."""
    out = []
    for i, entry in enumerate(DESIGNS[name]):
        cid, stage, dims, peaks, total, length, separation = entry[:7]
        ratio = entry[7] if len(entry) > 7 else DESIGN_RATIO
        margin = entry[8] if len(entry) > 8 else rw_peaks.MARGIN_SPREADS
        spread = rw_peaks.spread_for_sparsity(total / peaks, dims, 30)
        if peaks == 2 and not (rw_peaks.fits(spread, dims, separation, margin) and rw_peaks.separable(separation, ratio)):
            raise ValueError(f"{cid}: two peaks {separation} spreads apart at a ratio of {ratio} do not fit at a spread of {spread:.3f} with a margin of {margin} spreads")
        out.append({"id": cid, "index": i, "stage": stage, "n_peaks": peaks, "dims": dims, "level": int(round(total * 100)), "total": total, "spread": spread, "separation": separation,
                    "ratio": ratio if peaks == 2 else None, "length": length, "guarantee": DESIGN_GUARANTEE, "margin": margin})
    return out


# The crossing screen (PI, 2026-11-10): the two candidate crossing factors of T side by side at 15% and 10%, two features, two peaks, 180 s: the separation (3 and 4.5 spreads) at the
# ratio 0.75, and the height ratio (0.3, 0.75 and 0.9) at the separation 4.5. The margin is 1.0 spread (the default 1.48 leaves room for only 3.5 spreads at 15%).
CROSSING_MARGIN = 1.0
CROSSING = [(f"T{t}-sep{sep:g}-r{ratio:g}", "T", 2, 2, t / 100, 180, sep, ratio, CROSSING_MARGIN)
            for t in (15, 10) for sep, ratio in ((3.0, .75), (4.5, .3), (4.5, .75), (4.5, .9))]
# The sparsity ladder (PI, 2026-11-10): a crossing is too much to characterise sparsity, so S and T take three sparsities (15, 10, 5%) with the height ratio and the separation fixed.
SPARSITY_RATIO, SPARSITY_SEPARATION = 0.5, 4.5
SPARSITY = ([(f"S2F-{t}", "S", 2, 1, t / 100, 180, None) for t in (15, 10, 5)]
            + [(f"T2F-{t}", "T", 2, 2, t / 100, 180, SPARSITY_SEPARATION, SPARSITY_RATIO, CROSSING_MARGIN) for t in (15, 10, 5)])
# T's sparsity levels (PI, 2026-11-10): where between 15% and 5% the three levels of T should sit; read at 180 and 240 s (the 240 s episode is played anyway).
TSWEEP = [(f"T2F-{t}", "T", 2, 2, t / 100, 180, SPARSITY_SEPARATION, SPARSITY_RATIO, CROSSING_MARGIN) for t in (15, 13, 11, 9, 7, 5)]
DESIGNS = {"ladder": LADDER, "crossing": CROSSING, "sparsity": SPARSITY, "tsweep": TSWEEP}


def model_found(dims, share30, length, region=10, k=1.0):
    """The discovery model: the fraction that found the peak's top-`region`% region by `length` seconds, for a peak whose top-30% region is `share30` of the feature space; `k` the slowdown
    (1 = the agents). A region's share scales with the width of its half-width, so by (k_region / k_30) for one feature and its square for two."""
    ratio = math.sqrt(math.log(1 - region / 100.0) / math.log(0.7))
    return 1.0 - math.exp(-MODEL_C[dims] * (length / k) * share30 * (ratio if dims == 1 else ratio ** 2))


def session_params(peaks, base=BASE_SESSION):
    """The session of an instance: the base session's terrain with the peaks as the reward, both features varying and dealt by plane coverage, the longest length."""
    return synthetic.session(visible=("shape", "color"), weights={"shape": 1.0}, base=base, std=REWARD_STD, reward_function=peaks.reward_function(), spatial_balance=0,
                             feature_balance=0, feature_coverage=1, session_duration=float(max(DURATIONS)))


def build_instance(cell, k, base=BASE_SESSION):
    """(world seed, attempts, peaks, world) of the k-th world of a cell, or None when no seed gave every peak its bushes."""
    for attempt in range(MAX_ATTEMPTS):
        seed = 10_000 + 100 * cell["index"] + k + 1_000_000 * attempt
        rng = np.random.default_rng([seed, 7])
        paying = ("shape", "color") if cell["dims"] == 2 else (str(rng.choice(["shape", "color"])),)
        peaks = rw_peaks.draw_peaks(rng, paying, cell["n_peaks"], cell["spread"], cell["separation"], cell["ratio"], margin_spreads=cell.get("margin"))
        w = world.generate_world(session_params(peaks, base), seed)
        x, need = cell.get("guarantee", (10, rw_peaks.MIN_PEAK_BUSHES))
        if min(rw_peaks.bush_counts(peaks, w.shape, w.color, x)) >= need:
            return seed, attempt, peaks, w
    return None


def episode_row(w, peaks, result):
    """The score at each length and, per peak and region, the first fruit's time and the number of fruits, from an episode's fruit log; and the log in compact form."""
    fruits = np.array(result.fruits, dtype=float).reshape(-1, 5)                       # (t, bush, k, reward, running total)
    t, bush, reward = fruits[:, 0], fruits[:, 1].astype(int), fruits[:, 3]
    row = {f"score_{d}": float(reward[t <= d].sum()) for d in DURATIONS}
    row["fruits"] = int(len(t))
    region = np.zeros(len(t), dtype=int)
    for x in REGION_X:
        masks = rw_peaks.peak_regions(peaks, w.shape, w.color, x)
        for p, name in enumerate(PEAK_NAMES):                                     # the same columns for one peak and two (the local peak's are empty for one)
            if p >= len(masks):
                row[f"first{x}_{name}"], row[f"n{x}_{name}"] = "", ""
                continue
            inside = masks[p][bush]
            row[f"first{x}_{name}"] = float(t[inside].min()) if inside.any() else ""
            row[f"n{x}_{name}"] = int(inside.sum())
            if x == max(REGION_X):
                region[inside] = p + 1
    log = {"t": [round(float(v), 2) for v in t], "bush": [int(v) for v in bush], "reward": [float(v) for v in reward], "region": [int(v) for v in region]}
    return row, log


def run_instance(task):
    """Worker: one instance of a cell, every agent on it. Returns (instance row or None, episode rows, fruit logs)."""
    cell, k, agent_names, base = task
    instance = f"{cell['id']}_w{k}"
    try:
        return _run_instance(cell, k, agent_names, base, instance)
    except Exception as error:                                       # one bad instance must not end a long unattended run: it is recorded and the run goes on
        return {"instance": instance, "cell": cell["id"], "k": k, "status": f"error: {type(error).__name__}: {error}"}, [], []


def _run_instance(cell, k, agent_names, base, instance):
    built = build_instance(cell, k, base)
    if built is None:
        return {"instance": instance, "cell": cell["id"], "k": k, "status": "no world with enough bushes in every peak"}, [], []
    seed, attempts, peaks, w = built
    record = rw_peaks.describe(peaks)
    info = {"instance": instance, "cell": cell["id"], "k": k, "status": "ok", "world_seed": seed, "attempts": attempts + 1, "n_bushes": w.n, "paying": "+".join(peaks.paying),
            "spread": round(peaks.spread, 5), "centers": json.dumps(record["centers"]), "heights": json.dumps(record["heights"]),
            **{f"sparsity{x}": v for x, v in record["sparsity"].items()}, "bushes10": json.dumps(rw_peaks.bush_counts(peaks, w.shape, w.color, 10)), "bushes30": json.dumps(rw_peaks.bush_counts(peaks, w.shape, w.color, 30)),
            "separation": record.get("separation", ""), "height_ratio": record.get("height_ratio", "")}
    rows, logs = [], []
    for name in agent_names:
        result = sim.run_episode(agents.REGISTRY[name](), w)
        row, log = episode_row(w, peaks, result)
        rows.append({"instance": instance, "agent": name, **{k_: cell[k_] for k_ in ("id", "n_peaks", "dims", "level", "separation", "ratio")}, "spread": cell["spread"],
                     "stage": cell.get("stage", ""), "total": cell.get("total", ""), "length": cell.get("length", ""), **row})
        logs.append({"instance": instance, "agent": name, **log})
    return info, rows, logs


def check_agents(agent_names):
    """Refuses an agent that depends on the session's length: the screen reads shorter sessions from one long run, which is not what such an agent would do."""
    for name in agent_names:
        if getattr(agents.REGISTRY[name](), "deadline_dependent", False):
            raise ValueError(f"{name} depends on the session's length: the screen reads shorter sessions from one long run, which is not what it would do")


def files(tag, directory=RESULTS):
    return {kind: directory / f"rw_screen_{tag}_{kind}" for kind in ("instances.csv", "episodes.csv", "fruits.jsonl.gz")}


def _append(path, rows, fields):
    new = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval="")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def write_plan(tag, directory, worlds, agent_names, grid, base, design=None):
    """The settings of a run beside its results (results/rw_screen_<tag>_plan.json), so that it can be understood and repeated; one line is added each time the run is started."""
    import subprocess
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()
    entry = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "commit": commit, "worlds_per_cell": worlds, "agents": list(agent_names), "durations": list(DURATIONS), "base": base,
             "grid": {"levels": (grid or {}).get("levels") or SPREAD_LEVELS, "separations": list((grid or {}).get("separations") or SEPARATIONS), "ratios": list((grid or {}).get("ratios") or HEIGHT_RATIOS)},
             "design": design, "reward_std": REWARD_STD, "min_peak_bushes": rw_peaks.MIN_PEAK_BUSHES, "narrowest_expected": rw_peaks.NARROWEST_EXPECTED}
    with open(directory / f"rw_screen_{tag}_plan.json", "a") as f:
        f.write(json.dumps(entry) + "\n")


def done_instances(tag, directory=RESULTS):
    """The instances in the files that need no more work: played, or given up for want of a world; one that failed with an error is played again."""
    path = files(tag, directory)["instances.csv"]
    if not path.exists():
        return set()
    with open(path, newline="") as f:
        return {row["instance"] for row in csv.DictReader(f) if not row["status"].startswith("error")}


def _log(message):
    print(message, flush=True)


def run(tag, worlds=WORLDS_PER_CELL, agent_names=AGENTS, workers=1, cell_ids=None, directory=RESULTS, base=BASE_SESSION, log=_log, grid=None, design=None):
    """Play every agent on every instance not yet in the files; appends as instances finish. Returns the number of instances played. `grid`: keyword arguments of `cells`; `design`: the name of a design in DESIGNS, played instead of a grid.
    The instances are played world by world across all cells (world 0 of every cell, then world 1, ...), so a run that is stopped early has the same number of worlds in every cell."""
    check_agents(agent_names)
    directory.mkdir(parents=True, exist_ok=True)
    paths = files(tag, directory)
    write_plan(tag, directory, worlds, agent_names, grid, base, design)
    skip = done_instances(tag, directory)
    chosen = [c for c in (design_cells(design) if design else cells(**(grid or {}))) if cell_ids is None or c["id"] in cell_ids]
    tasks = [(c, k, tuple(agent_names), base) for k in range(worlds) for c in chosen if f"{c['id']}_w{k}" not in skip]
    log(f"{len(tasks)} instances to play ({len(skip)} already done), {len(agent_names)} agents each, {len(DURATIONS)} lengths read from one episode of {max(DURATIONS)} s")
    start = time.time()
    played, errors, statuses = 0, 0, {}

    def store(result):
        nonlocal played, errors
        info, rows, logs = result
        if rows:
            _append(paths["episodes.csv"], rows, EPISODE_FIELDS)
            with gzip.open(paths["fruits.jsonl.gz"], "at") as f:
                f.writelines(json.dumps(entry) + "\n" for entry in logs)
        _append(paths["instances.csv"], [info], INSTANCE_FIELDS)          # last: an instance is done only when its episodes are stored
        played += 1
        kind = info["status"].split(":")[0] if info["status"] != "ok" else "ok"
        statuses[kind] = statuses.get(kind, 0) + 1
        if kind == "error":
            errors += 1
            if errors <= 3:
                log(f"  {info['instance']}: {info['status']}")
            if played >= 200 and errors / played > MAX_ERROR_SHARE:
                raise RuntimeError(f"{errors} of {played} instances failed (more than {MAX_ERROR_SHARE:.0%}): stopping; the files keep what was played ({info['status']})")
        if played % 100 == 0 or played == len(tasks):
            elapsed = time.time() - start
            log(f"  {played}/{len(tasks)} instances, {elapsed:.0f} s, about {elapsed * (len(tasks) - played) / played:.0f} s to go")

    if workers > 1:
        with Pool(workers) as pool:
            for result in pool.imap_unordered(run_instance, tasks, chunksize=2):
                store(result)
    else:
        for task in tasks:
            store(run_instance(task))
    log(f"done: {statuses}")
    return played


def summary(tag, directory=RESULTS, durations=DURATIONS, region=30):
    """A DataFrame, one row per (cell, agent, length): the mean score, the fraction of instances that found the global peak by then (a fruit from its top-30% region), found the
    local peak, and were trapped (found the local peak and never the global one by then). `first30_*` are empty when never."""
    import pandas as pd
    episodes = pd.read_csv(files(tag, directory)["episodes.csv"])
    rows = []
    for (cell, agent), group in episodes.groupby(["id", "agent"], sort=False):
        head = group.iloc[0]
        for d in durations:
            g = group[f"first{region}_global"] <= d
            local = group[f"first{region}_local"] <= d                              # (empty for a one-peak instance: never)
            rows.append({"cell": cell, "n_peaks": int(head["n_peaks"]), "dims": int(head["dims"]), "level": int(head["level"]), "spread": head["spread"], "separation": head["separation"],
                         "ratio": head["ratio"], "agent": agent, "length": d, "n": len(group), "score": group[f"score_{d}"].mean(), "found_global": g.mean(),
                         "found_local": local.mean(), "trapped": (local & ~g).mean()})
    return pd.DataFrame(rows)


def marginals(table, by, values=("score", "found_global", "trapped")):
    """The mean of `values` over every other parameter, for each value of `by`, agent and length: how one parameter moves the outcome with the others averaged out (the grid is fully
    crossed, so each average covers the same mix of the other parameters, up to the combinations that do not fit)."""
    return table.groupby([by, "agent", "length"])[list(values)].mean().unstack(["agent", "length"])


def report(tag, directory=RESULTS, durations=(60, 120, 180, 240)):
    """Marginal tables, not a table per cell (a fine grid has over a thousand): the one-peak types by spread, then for the two-peak types the outcome by spread, by separation and by height
    ratio, and the fraction of instances that found the global peak against the session's length. All fractions and scores are means over instances."""
    import pandas as pd
    table = summary(tag, directory, durations)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    pd.set_option("display.max_columns", 60)
    print(f"{table['n'].sum() // len(durations)} episodes, {table['cell'].nunique()} cells, lengths {list(durations)}")
    for dims in (1, 2):
        one = table[(table["n_peaks"] == 1) & (table["dims"] == dims)].copy()
        if len(one):
            one["spread"] = one["spread"].round(3)
            print(f"\n=== one peak, {dims} paying feature(s): by spread ===")
            print(marginals(one, "spread", ("score", "found_global")).round(2).to_string())
    for dims in (1, 2):
        two = table[(table["n_peaks"] == 2) & (table["dims"] == dims)].copy()
        if not len(two):
            continue
        two["spread"] = two["spread"].round(3)
        for by in ("spread", "separation", "ratio"):
            print(f"\n=== two peaks, {dims} paying feature(s): by {by} (global found, trapped, score) ===")
            print(marginals(two, by).round(2).to_string())
        print(f"\n=== two peaks, {dims} paying feature(s): found the global peak against session length ===")
        print(two.groupby(["agent", "length"])[["found_global", "found_local", "trapped"]].mean().unstack("agent").round(2).to_string())


def design_report(tag, directory=RESULTS, region=10):
    """The agents' results on a design's cells, at each cell's own session length: the fraction that found the global peak (strict: the top-10% region, by default), found the local one, found
    both, were trapped (found the local peak and not the global one), the mean score, and for the cell's one-peak equivalent the discovery model's value (agents, k = 1) beside it. Also the
    lenient (top-30%) discovery and the strict discovery at 120 s, the length of the baselines."""
    import pandas as pd
    episodes = pd.read_csv(files(tag, directory)["episodes.csv"])
    rows = []
    for (cell, agent), g in episodes.groupby(["id", "agent"], sort=False):
        h = g.iloc[0]; length = int(h["length"]); two = int(h["n_peaks"]) == 2
        glob = g[f"first{region}_global"] <= length
        local = g[f"first{region}_local"] <= length if two else pd.Series(False, index=g.index)
        share = (h["total"] / int(h["n_peaks"]))
        rows.append({"cell": cell, "stage": h["stage"], "feat": int(h["dims"]), "peaks": int(h["n_peaks"]), "total": h["total"], "sep": h["separation"], "length": length, "n": len(g), "agent": agent,
                     "found": glob.mean(), "found_local": local.mean(), "both": (glob & local).mean(), "trapped": (local & ~glob).mean(), "score": g[f"score_{length}"].mean(),
                     "lenient": (g["first30_global"] <= length).mean(), f"found@120": (g[f"first{region}_global"] <= 120).mean(), "model": model_found(int(h["dims"]), share, length, region)})
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
    label = "strict (top-10% region)" if region == 10 else "lenient (top-30% region)"
    print(f"{t['n'].iloc[0]} worlds per cell; discovery: {label}; each cell at its own length; model = the discovery model for the global peak alone, agents (k = 1)\n")
    order = list(dict.fromkeys(t["cell"]))
    for agent_metric in ("found", "trapped", "score", "lenient"):
        w = t.pivot(index="cell", columns="agent", values=agent_metric).loc[order]
        w.insert(0, "model", t.groupby("cell")["model"].first().loc[order] if agent_metric == "found" else float("nan"))
        w = w.drop(columns="model") if agent_metric != "found" else w
        print(f"--- {agent_metric}"); print(w.round(2).to_string()); print()
    return t


def plan(worlds=WORLDS_PER_CELL, grid=None, design=None):
    if design:
        table = design_cells(design)
        print(f"design {design}: {len(table)} cells, {worlds} worlds each = {len(table) * worlds} instances, {len(AGENTS)} agents")
        for c in table:
            print(f"  {c['id']:12} stage {c['stage']} {c['dims']} feature(s) {c['n_peaks']} peak(s) sparsity {c['total']:.0%} spread {c['spread']:.3f} separation {c['separation']} length {c['length']} s")
        return
    table = cells(**(grid or {}))
    print(f"{len(table)} cells, {worlds} worlds each = {len(table) * worlds} instances, {len(AGENTS)} agents = {len(table) * worlds * len(AGENTS)} episodes of {max(DURATIONS)} s;"
          f" lengths read from each: {list(DURATIONS)}")
    last = None
    for c in table:
        if (c["n_peaks"], c["dims"], c["level"]) != last:
            last = (c["n_peaks"], c["dims"], c["level"])
            sparsity = {x: round(rw_peaks.sparsity_for_spread(c["spread"], c["dims"], x), 3) for x in rw_peaks.SPARSITY_X}
            print(f"\n{c['n_peaks']} peak(s), {c['dims']} feature(s), spread level {c['level']}: spread {c['spread']:.3f}, sparsity at x=10/20/30 (one peak) {sparsity}")
        if c["n_peaks"] == 2:
            print(f"    {c['id']}")
    singles = [c["id"] for c in table if c["n_peaks"] == 1]
    print("\none-peak cells:", ", ".join(singles))


def main():
    ap = argparse.ArgumentParser(description="Screen the RW peak parameters with the simulated agents.")
    sub = ap.add_subparsers(dest="command", required=True)
    def grid_options(parser):
        parser.add_argument("--spread-levels", type=int, default=SPREAD_LEVELS)
        parser.add_argument("--separations", default=",".join(f"{v:g}" for v in SEPARATIONS))
        parser.add_argument("--ratios", default=",".join(f"{v:g}" for v in HEIGHT_RATIOS))
    pl = sub.add_parser("plan")
    pl.add_argument("--worlds", type=int, default=WORLDS_PER_CELL)
    pl.add_argument("--design", choices=sorted(DESIGNS), help="a named design instead of a grid")
    grid_options(pl)
    r = sub.add_parser("run")
    r.add_argument("--design", choices=sorted(DESIGNS), help="a named design instead of a grid")
    grid_options(r)
    r.add_argument("--tag", required=True)
    r.add_argument("--worlds", type=int, default=WORLDS_PER_CELL)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--cells", help="comma-separated cell ids (default: all)")
    r.add_argument("--agents", default=",".join(AGENTS))
    r.add_argument("--base", default=BASE_SESSION)
    p = sub.add_parser("report")
    p.add_argument("--tag", required=True)
    p.add_argument("--lengths", default="60,120,180,240")
    p.add_argument("--design", action="store_true", help="the report of a design run (per cell, at the cell's length)")
    p.add_argument("--region", type=int, default=10, choices=(10, 30), help="the region found is read in: 10 = strict (the default), 30 = lenient")
    args = ap.parse_args()
    if args.command in ("plan", "run"):
        grid = {"levels": args.spread_levels, "separations": tuple(float(v) for v in args.separations.split(",")), "ratios": tuple(float(v) for v in args.ratios.split(","))}
    if args.command == "plan":
        plan(args.worlds, grid, args.design)
    elif args.command == "run":
        run(args.tag, args.worlds, args.agents.split(","), args.workers, set(args.cells.split(",")) if args.cells else None, base=args.base, grid=grid, design=args.design)
    elif args.design:
        design_report(args.tag, region=args.region)
    else:
        report(args.tag, durations=tuple(int(v) for v in args.lengths.split(",")))


if __name__ == "__main__":
    sys.exit(main())
