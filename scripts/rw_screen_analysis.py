"""Reading the RW screen (scripts/rw_screen.py): the questions asked of a run's files, as functions and a command line.

    ./venv/bin/python scripts/rw_screen_analysis.py --tag rw2

    agent_differences   score and the fraction that found the global peak, per agent and session length, paired by instance
    time_to_find        the median and 80th-percentile time to the first fruit from the global peak's top-30% region, and the share never found, by sparsity, per type
    trapped_grid        the fraction trapped (found the local peak, not the global one, by the length) by separation and height ratio, per type
    settled             from the fruit logs: in the last third of a session, whether more fruits came from the local peak than the global one (needs the fruit log; two peaks)
    trapping_cost       the score of the instances that were trapped against those that found the global peak
    human_proxy         for a design run: each cell's discovery and trapping for the agents at the session's length and at length / k (a person k times slower), pooled over the learners

"Found" is a fruit from a bush in the peak's top-10% region (strict; `region=30` gives the lenient top-30% definition); "trapped" is found local and not global by the length; "settled on local" is more of the last third's fruits from the
local peak's region than from the global's (all over the stored first-fruit times and fruit log, so a definition can change here without a new run).
"""

import argparse
import gzip
import json

import numpy as np
import pandas as pd

import rw_screen

LENGTHS = (60, 120, 240)
REGION = 10                          # the region "found" is read in: 10 = strict (the top-10% region, the default since 2026-11-10), 30 = lenient


def load(tag, directory=rw_screen.RESULTS):
    paths = rw_screen.files(tag, directory)
    episodes = pd.read_csv(paths["episodes.csv"])
    instances = pd.read_csv(paths["instances.csv"])
    episodes = episodes.merge(instances[["instance", "sparsity10", "sparsity20", "sparsity30", "paying"]], on="instance")
    episodes["type"] = episodes["n_peaks"].astype(str) + "p" + episodes["dims"].astype(str) + "f"
    return episodes


def agent_differences(episodes, lengths=LENGTHS, region=REGION):
    rows = []
    for length in lengths:
        for agent, g in episodes.groupby("agent"):
            rows.append({"length": length, "agent": agent, "score": g[f"score_{length}"].mean(), "found_global": (g[f"first{region}_global"] <= length).mean()})
    table = pd.DataFrame(rows).pivot(index="agent", columns="length", values=["score", "found_global"]).round(3)
    return table


def time_to_find(episodes, bins=6, region=REGION):
    out = {}
    for kind, g in episodes.groupby("type"):
        g = g.assign(bin=pd.qcut(g["sparsity20"], bins, duplicates="drop"), t=g[f"first{region}_global"].fillna(np.inf))
        out[kind] = g.groupby("bin", observed=True).agg(sparsity20=("sparsity20", "mean"), median_t=("t", "median"), p80_t=("t", lambda s: s.quantile(0.8)),
                                                        never_found=(f"first{region}_global", lambda s: s.isna().mean())).round(3)
    return out


def trapped_grid(episodes, length=120, region=REGION):
    two = episodes[episodes.n_peaks == 2].copy()
    two["trapped"] = ((two[f"first{region}_local"] <= length) & ~(two[f"first{region}_global"] <= length)).astype(float)
    return {kind: g.pivot_table(index="separation", columns="ratio", values="trapped", aggfunc="mean").round(2) for kind, g in two.groupby("type")}


def trapping_cost(episodes, length=240, region=REGION):
    two = episodes[episodes.n_peaks == 2].copy()
    two["trapped"] = (two[f"first{region}_local"] <= length) & ~(two[f"first{region}_global"] <= length)
    two["found"] = two[f"first{region}_global"] <= length
    return two.groupby(["dims", "agent"]).apply(lambda g: pd.Series({"trapped": g["trapped"].mean(), "score_trapped": g.loc[g["trapped"], f"score_{length}"].mean(),
                                                                   "score_found_global": g.loc[g["found"] & ~g["trapped"], f"score_{length}"].mean()}), include_groups=False).round(3)


def human_proxy(episodes, ks=(2, 3), region=REGION, agents=("learner", "softmax", "curious")):
    """One row per cell of a design run (`rw_screen.design_cells`): for the given agents pooled, the fraction that found the global peak, and the fraction trapped (found the local peak and not
    the global one), at the cell's session length (`agent`) and at length / k for each k, which is the proxy for a person k times slower than the agents; also the lenient discovery (the top-30%
    region) at the same times and the mean score at the cell's length."""
    g = episodes[episodes.agent.isin(agents)]
    rows = []
    for cell, c in g.groupby("id", sort=False):
        length = float(c["length"].iloc[0]); two = int(c["n_peaks"].iloc[0]) == 2
        row = {"cell": cell, "length": int(length), "n": len(c), "score": c[f"score_{int(length)}"].mean()}
        for label, t in (("agent", length),) + tuple((f"k{k}", length / k) for k in ks):
            glob = c[f"first{region}_global"] <= t
            local = (c[f"first{region}_local"] <= t) if two else pd.Series(False, index=c.index)
            row[f"found_{label}"], row[f"trapped_{label}"] = glob.mean(), (local & ~glob).mean()
            row[f"lenient_{label}"] = (c["first30_global"] <= t).mean()
        rows.append(row)
    return pd.DataFrame(rows).set_index("cell")


def settled(tag, directory=rw_screen.RESULTS, lengths=(120, 240)):
    """One row per two-peak episode: the fruits of the last third of each session length that came from each peak's region, and whether it settled on the local peak."""
    episodes = load(tag, directory).set_index(["instance", "agent"])
    rows = []
    with gzip.open(rw_screen.files(tag, directory)["fruits.jsonl.gz"], "rt") as f:
        for line in f:
            entry = json.loads(line)
            meta = episodes.loc[(entry["instance"], entry["agent"])]
            if meta["n_peaks"] != 2:
                continue
            t, region = np.array(entry["t"]), np.array(entry["region"])
            row = {"agent": entry["agent"], "dims": int(meta["dims"]), "separation": meta["separation"], "ratio": meta["ratio"]}
            for length in lengths:
                late = (t > 2 * length / 3) & (t <= length)
                local, glob = int(((region == 2) & late).sum()), int(((region == 1) & late).sum())
                row[f"late_local_{length}"], row[f"late_global_{length}"] = local, glob
                row[f"settled_local_{length}"] = float(local > glob)
                row[f"settled_global_{length}"] = float(glob > local)
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description="Questions asked of an RW screen run.")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--no-settled", action="store_true", help="skip the fruit logs (the slow part)")
    args = ap.parse_args()
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 40)
    episodes = load(args.tag)
    print("=== agent differences (score, found the global peak) ===")
    print(agent_differences(episodes).to_string())
    print("\n=== time to the first fruit from the global peak's region, by the instance's sparsity at x = 20 ===")
    for kind, table in time_to_find(episodes).items():
        print(f"-- {kind}")
        print(table.to_string())
    for kind, table in trapped_grid(episodes).items():
        print(f"\n=== {kind}: fraction trapped by 120 s, separation (rows) x height ratio (columns) ===")
        print(table.to_string())
    print("\n=== trapping at 240 s and what it costs in score ===")
    print(trapping_cost(episodes).to_string())
    if not args.no_settled:
        s = settled(args.tag)
        print("\n=== settled on the local peak in the last third of a session ===")
        print(s.groupby(["dims", "agent"])[[c for c in s.columns if c.startswith("settled_")]].mean().round(3).to_string())


if __name__ == "__main__":
    main()
