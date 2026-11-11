"""What the Interlude trials of FI contain: per kind of rule, how many trials of each class, their reward gaps, and how many of them are reversal pairs (the best separable fit to the reward, a function of
shape plus a function of colour, orders the pair the wrong way), which says whether a class of reversal pairs of its own is needed.

    fi_interlude_report.py                      draws instances of every kind (`--draws`, default 6), generates their Interludes and reports
    fi_interlude_report.py --experiment FI      reports the built Interlude files of an experiment's sessions (their sessions' reward functions)

A pair is a reversal when the separable fit (backfitted on a grid over the plane) predicts a gap of at least REVERSAL_MARGIN of the best reward in the wrong direction.
"""

import argparse
import collections
import glob
import json

import numpy as np

import fi_terms
import interlude
import world

KINDS = [("corner", {}), ("middle", {}), ("elongated", {}), ("elongated, aligned", {"tilt": 0.0})]
OVERRIDES = dict(interlude_trial_count=20, interlude_repeat_count=3, interlude_interaction_trials=17, interlude_peak_trials=0, interlude_mode=4, interlude_feature_trials=0)


def reversal_flags(reward_function, trials):
    """For each trial, whether it is a reversal pair of the rule `reward_function`."""
    class Des:
        p = type("P", (), {"reward_function": reward_function})()
    plane = interlude._Plane(Des)
    out = []
    for t in trials:
        predicted = float(plane.separable(t["left"]["shape"], t["left"]["color"]) - plane.separable(t["right"]["shape"], t["right"]["color"]))
        out.append(bool(np.sign(predicted) != np.sign(t["deltaValue"]) and abs(predicted) >= interlude.REVERSAL_MARGIN * plane.top))
    return out


def summarise(rows):
    """rows: (reward function, trials) -> {class: [trials, reversals, min gap, max gap]} over the distinct trials of every row."""
    table = collections.defaultdict(lambda: [0, 0, np.inf, 0.0])
    for rf, trials in rows:
        flags = reversal_flags(rf, trials)
        for t, flag in zip(trials, flags):
            if "repeatOf" in t:
                continue
            row = table[t["varied"]]
            gap = abs(t["deltaValue"])
            row[0] += 1
            row[1] += flag
            row[2], row[3] = min(row[2], gap), max(row[3], gap)
    return dict(table)


def print_table(label, rows):
    table = summarise(rows)
    total, rev = sum(r[0] for r in table.values()), sum(r[1] for r in table.values())
    print(f"{label}: {total} distinct trials, {rev} reversals ({100 * rev / max(total, 1):.0f}%)")
    for cls in sorted(table):
        n, r, lo, hi = table[cls]
        print(f"    {cls:7} {n:3} trials, {r:3} reversals ({100 * r / n:3.0f}%), gaps {lo:.2f} to {hi:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", help="report the built Interlude files of this experiment code (e.g. FI)")
    ap.add_argument("--draws", type=int, default=6)
    ap.add_argument("--target", type=float, default=0.30)
    ap.add_argument("--x", type=int, default=40)
    args = ap.parse_args()
    if args.experiment:
        rows = []
        for path in sorted(glob.glob(str(world.STREAMING_EXPERIMENTS / args.experiment / f"{args.experiment}_I*_seed*.interlude.json"))):
            data = json.load(open(path))
            params = world.load_session(data["interludeFor"])
            rows.append((params.reward_function, data["trials"]))
        by_kind = collections.defaultdict(list)
        for rf, trials in rows:
            by_kind[interlude.interaction_kind(rf)].append((rf, trials))
        for kind, group in by_kind.items():
            print_table(f"{args.experiment} {kind} ({len(group)} sessions)", group)
        return
    for label, kwargs in KINDS:
        kind, rows = label.split(",")[0], []
        for seed in range(args.draws):
            inst = fi_terms.draw_instance(np.random.default_rng(seed), kind, target=args.target, x=args.x, **kwargs)
            sidecar, _, _ = interlude.generate_interlude("RW_I1", reward_function=inst.reward_function(), **OVERRIDES)
            rows.append((inst.reward_function(), sidecar["trials"]))
        print_table(f"{label} ({args.draws} draws, target {args.target} at x = {args.x})", rows)


if __name__ == "__main__":
    main()
