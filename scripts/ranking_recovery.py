"""Model recovery for the plus ranking design: which axes mode tells learners with different knowledge apart?

Four simulated learners know a session's value map to different degrees: `full` (the true map), `additive` (its best additive approximation, a function of shape plus a function of
colour: no conjunction knowledge), `shape` (the map averaged over colour: a shape-only learner) and `colour` (averaged over shape). A learner ranks a set of five bushes by a
Plackett-Luce choice over its own values at temperature `tau` (points per fruit): first it picks the best, then the best of the rest, and so on. Four contrasts ask what a set of
rankings can tell apart:

    conjunction   additive vs full    (does the participant know the joint structure?)
    colour use    shape vs additive   (does the participant use colour at all?)
    shape use     colour vs additive  (does the participant use shape at all?)
    which feature shape vs colour

For each set the distributions over its 120 possible rankings under the two learners are exact, so the Jeffreys divergence (KL both ways, nats) is the expected evidence one ranking
of that set gives; its mean over the sets of an axes mode says how informative that mode is. Recovery accuracy is the share of simulated participants (n sets, drawn from the
mode, ranked by one learner or the other) whose summed log-likelihood ratio picks the right learner. Where two learners agree on a map (an additive map: additive and full) the
divergence is 0 for every mode.

    ranking_recovery.py PSC_S1 PCX_S1 ... [--seeds 8] [--tau 1.0] [--reps 4000] [--out file.png] [--txt file.txt]

The sets are the plus pools of `--seeds` world seeds (the session's own seed and the next ones), so a mode's mean rests on a few hundred sets. Not an engine file.
"""

import argparse
import itertools
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import ranking
from world import REWARDS, stage_names

DOCS = Path(__file__).resolve().parent.parent / "docs" / "pilots"
PERMS = np.array(list(itertools.permutations(range(5))))                     # (120, 5): the bush picked first, second, ...
CONTRASTS = (("conjunction", "additive", "full"), ("colour use", "shape", "additive"), ("shape use", "colour", "additive"), ("which feature", "shape", "colour"))
MODES = ("aligned", "random")
GRID = 101


def learners(params):
    """{name: f(shape, colour) -> value} for the four learners of a session's value map."""
    axis = np.linspace(0.0, 1.0, GRID)
    field = np.asarray(REWARDS[stage_names(params)[2]](params.reward_function, axis[:, None], axis[None, :]), dtype=float)
    by_shape, by_colour, mean = field.mean(axis=1), field.mean(axis=0), float(field.mean())
    full = lambda s, c: np.asarray(REWARDS[stage_names(params)[2]](params.reward_function, s, c), dtype=float)
    shape = lambda s, c: np.interp(s, axis, by_shape) + 0.0 * np.asarray(c)
    colour = lambda s, c: np.interp(c, axis, by_colour) + 0.0 * np.asarray(s)
    additive = lambda s, c: np.interp(s, axis, by_shape) + np.interp(c, axis, by_colour) - mean
    return {"full": full, "additive": additive, "shape": shape, "colour": colour}


def ranking_log_probs(values, tau):
    """log P of each of the 120 rankings of five bushes with these values under Plackett-Luce at temperature tau (in pick order: best first)."""
    u = np.asarray(values, dtype=float)[PERMS] / tau                          # (120, 5): utilities in the order picked
    tail = np.logaddexp.accumulate(u[:, ::-1], axis=1)[:, ::-1]               # log of the sum over the bushes not yet picked
    return (u - tail).sum(axis=1)


def collect_sets(session, seeds):
    """(sets, params): each set a dict with its axes mode and the shape and colour of its five bushes, from the plus pools of `seeds` consecutive world seeds."""
    base = ranking.load_session(session).world_seed
    sets, params, failed = [], None, 0
    for k in range(seeds):
        try:
            sidecar, params = ranking.generate_pool(session, ranking_design="plus", world_seed=int(base) + k)
        except ValueError:
            failed += 1
            continue
        for trial, meta in zip(sidecar["sets"], sidecar["plus"]):
            sets.append({"axes": meta["axes"], "shape": np.array([b["shape"] for b in trial["bushes"]]), "colour": np.array([b["color"] for b in trial["bushes"]])})
    return sets, params, failed


def analyse(session, seeds, tau, reps, n_sets, rng):
    sets, params, failed = collect_sets(session, seeds)
    models = learners(params)
    logp = {m: np.array([ranking_log_probs(f(s["shape"], s["colour"]), tau) for s in sets]) for m, f in models.items()}
    axes = np.array([s["axes"] for s in sets])
    out = {"session": session, "sets": len(sets), "failedSeeds": failed, "contrasts": {}}
    for name, a, b in CONTRASTS:
        pa, pb = np.exp(logp[a]), np.exp(logp[b])
        jeff = (pa * (logp[a] - logp[b])).sum(axis=1) + (pb * (logp[b] - logp[a])).sum(axis=1)
        entry = {"divergence": {}, "accuracy": {}}
        for mode in MODES:
            d = jeff[axes == mode]
            entry["divergence"][mode] = (float(d.mean()), float(d.std(ddof=1) / math.sqrt(len(d))), int(len(d)))
            entry["accuracy"][mode] = recovery_accuracy(pa, pb, logp[a] - logp[b], [(np.flatnonzero(axes == mode), n_sets)], reps, rng)
        entry["accuracy"]["10 aligned + 20 random"] = recovery_accuracy(pa, pb, logp[a] - logp[b], [(np.flatnonzero(axes == "aligned"), n_sets), (np.flatnonzero(axes == "random"), 2 * n_sets)], reps, rng)
        entry["accuracy"]["30 random"] = recovery_accuracy(pa, pb, logp[a] - logp[b], [(np.flatnonzero(axes == "random"), 3 * n_sets)], reps, rng)
        out["contrasts"][name] = entry
    return out


def recovery_accuracy(pa, pb, llr_table, draws, reps, rng):
    """The share of simulated participants whose summed log-likelihood ratio favours the learner that ranked: `draws` = [(set indices to draw from, how many sets)]; half the
    participants are learner A and half learner B; a tie counts one half."""
    correct = 0.0
    for truth, probs, sign in ((0, pa, 1.0), (1, pb, -1.0)):
        total = np.zeros(reps)
        for pool, n in draws:
            idx = rng.choice(pool, size=(reps, n))
            cdf = np.cumsum(probs[idx], axis=2)
            pick = (cdf < rng.uniform(size=(reps, n, 1)) * cdf[..., -1:]).sum(axis=2)
            total += np.take_along_axis(llr_table[idx], pick[..., None], axis=2)[..., 0].sum(axis=1)
        correct += float(((sign * total) > 0).mean() + 0.5 * ((sign * total) == 0).mean())
    return correct / 2.0


def figure(results, tau, n_sets):
    fig, axes = plt.subplots(len(results), len(CONTRASTS), figsize=(4.0 * len(CONTRASTS), 2.7 * len(results)), layout="constrained", squeeze=False)
    colours = {"aligned": "#1f77b4", "random": "#d95f02"}
    for r, res in enumerate(results):
        for c, (name, a, b) in enumerate(CONTRASTS):
            ax = axes[r, c]
            entry = res["contrasts"][name]
            for k, mode in enumerate(MODES):
                mean, se, count = entry["divergence"][mode]
                ax.bar(k, mean, yerr=se, color=colours[mode], capsize=3)
                ax.text(k, mean + se, f"acc {entry['accuracy'][mode]:.2f}", ha="center", va="bottom", fontsize=8)
            ax.set_xticks(range(len(MODES)), [f"{m} (n={entry['divergence'][m][2]})" for m in MODES], fontsize=8)
            top = max(entry["divergence"][m][0] + entry["divergence"][m][1] for m in MODES)
            ax.set_ylim(0, max(top * 1.25, 0.02))
            if c == 0:
                ax.set_ylabel(f"{res['session']}\nmean divergence per set (nats)", fontsize=8)
            if r == 0:
                ax.set_title(f"{name}: {a} vs {b}", fontsize=10)
    fig.suptitle(f"Model recovery of the plus ranking sets (tau {tau} points per fruit; bars: expected evidence of one set; acc: recovery with {n_sets} sets of that mode)")
    return fig


def text(results, tau, n_sets):
    lines = [f"Model recovery, tau {tau}, accuracy for {n_sets} sets of one mode (10 aligned + 20 random vs 30 random: the design against dropping aligned)", ""]
    for res in results:
        lines.append(f"{res['session']}  ({res['sets']} sets" + (f", {res['failedSeeds']} seeds failed" if res["failedSeeds"] else "") + ")")
        for name, entry in res["contrasts"].items():
            d, acc = entry["divergence"], entry["accuracy"]
            lines.append(f"  {name:14s} divergence aligned {d['aligned'][0]:.3f}+-{d['aligned'][1]:.3f}  random {d['random'][0]:.3f}+-{d['random'][1]:.3f}   "
                         f"accuracy aligned {acc['aligned']:.2f} random {acc['random']:.2f}   10a+20r {acc['10 aligned + 20 random']:.2f}  30r {acc['30 random']:.2f}")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Model recovery of the plus ranking sets by axes mode.")
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--tau", type=float, default=1.0)
    ap.add_argument("--reps", type=int, default=4000)
    ap.add_argument("--sets", type=int, default=10, help="sets of one mode in a participant's data (accuracy columns)")
    ap.add_argument("--out", default=str(DOCS / "ranking_plus_recovery.png"))
    ap.add_argument("--txt", default=None)
    args = ap.parse_args()
    rng = np.random.default_rng(20261124)
    results = [analyse(s, args.seeds, args.tau, args.reps, args.sets, rng) for s in args.sessions]
    report = text(results, args.tau, args.sets)
    print(report)
    if args.txt:
        Path(args.txt).write_text(report + "\n")
    fig = figure(results, args.tau, args.sets)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=110)
    print(args.out)


if __name__ == "__main__":
    main()
