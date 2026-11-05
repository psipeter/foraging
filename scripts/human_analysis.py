"""The participants' data, one entry point for the exploratory analyses.

    ./venv/bin/python scripts/human_analysis.py <analysis> [options of that analysis]

    idle       idle windows in play (idle_analysis.py)
    gap        participants against the registry agents on the worlds they played (human_gap.py)
    carryover  the prior each session leaves and how far it steers the next (prior_carryover.py)
    decay      the hand-over from an earlier session's prior to the later session's reward (carryover_decay.py)
    attribute  does an attribute (default: moisture) steer choices, and how strongly (this file)

The first four are the scripts of those names, run unchanged with the remaining command line.

attribute: conditional-logit test of how strongly each participant weights an attribute, in the sessions where the rule uses it.
  * Visits (`--sessions`, default S3): the first-visit choice sets of prior_carryover.py, scored by  b . (shape, color, moisture) - gamma . walk,
    gamma fitted once per participant from walk alone. Per participant and pooled: coefficients with standard errors, the likelihood-ratio test of
    dropping each attribute, and the same fit in thirds of the visits (experience, not clock time) to separate "never uses it" from "learns it late".
    The ideal ratio is the least-squares weight of each attribute on the session's true reward over its bushes; the scale of a choice model
    (a temperature) is free, so compare the ratio of the moisture to the shape coefficient with the ideal ratio, not the coefficients themselves.
  * Interlude trials (`--interludes`, default S3_Interlude): a two-bush choice, so a logistic regression on the difference (right minus left) of each
    attribute (no intercept). Reported with the correlation between the attribute differences across the trials, since a design that moves two
    attributes together cannot tell them apart.
Both use a small ridge (`--ridge`). With four participants read per-participant rows as indications; the pooled row ignores that participants differ.

    ./venv/bin/python scripts/human_analysis.py attribute [--sessions S3] [--interludes S3_Interlude] [--attr moisture] [--ridge 0.1] [--refresh]
"""

import argparse
import runpy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prior_carryover as pc  # noqa: E402
from idle_analysis import finished_runs  # noqa: E402
from world import load_session, make_world  # noqa: E402

SCRIPTS = {"idle": "idle_analysis.py", "gap": "human_gap.py", "carryover": "prior_carryover.py", "decay": "carryover_decay.py"}
ATTRS = pc.ATTRS
THIRDS = ((0.0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1.0001))


def loglik(sets, beta, ridge):
    """Penalised log-likelihood of conditional-logit choice sets [(X, chosen index, offset)] at beta."""
    total = -0.5 * ridge * float(beta @ beta)
    for X, c, off, *_ in sets:
        u = X @ beta + off
        total += u[c] - (u.max() + np.log(np.exp(u - u.max()).sum()))
    return total


def fit(sets, cols, ridge):
    """(beta, se, loglik, n) of the choice sets with only the attribute columns `cols`."""
    sub = [(X[:, cols], c, off) for X, c, off, *_ in sets]
    beta, se, n = pc.fit_logit(sub, len(cols), ridge)
    return beta, se, loglik(sub, beta, ridge), n


def ideal(world):
    """Least-squares weight of each attribute (per unit) on the session's true reward of its bushes."""
    X = np.stack([world.shape, world.color, world.moisture, np.ones(world.n)], axis=1)
    return np.linalg.lstsq(X, world.value, rcond=None)[0][:3]


def lr_columns(sets, b, ll, tested, ridge):
    """{'LR <attr>': likelihood-ratio statistic of dropping that attribute, 'p <attr>': its p-value} for each tested attribute."""
    out = {}
    for attr in tested:
        lr = 2 * (ll - fit(sets, [i for i in range(3) if ATTRS[i] != attr], ridge)[2])
        out[f"LR {attr[:5]}"] = round(lr, 1)
        out[f"p {attr[:5]}"] = round(float(chi2.sf(max(lr, 0), 1)), 3)
    return out


def cosine(b, ide):
    """Similarity of the fitted weights to the ideal ones, independent of the choice model's scale (1 = the right proportions)."""
    return float(b @ ide / (np.linalg.norm(b) * np.linalg.norm(ide))) if np.linalg.norm(b) > 0 else np.nan


def attribute_table(sets_by_who, tested, ide, ridge, label):
    """Per-participant and pooled coefficients, the LR test of dropping each tested attribute, and the cosine to the ideal weights."""
    rows = []
    for who, sets in {**sets_by_who, "pooled": [s for v in sets_by_who.values() for s in v]}.items():
        if len(sets) < 5:
            continue
        b, se, ll, n = fit(sets, [0, 1, 2], ridge)
        rows.append({"who": who, "n": n, **{a: f"{b[i]:+.2f}+-{se[i]:.2f}" for i, a in enumerate(ATTRS)},
                     **lr_columns(sets, b, ll, tested, ridge), "cos to ideal": round(cosine(b, ide), 2)})
    print(f"\n{label}")
    print(pd.DataFrame(rows).to_string(index=False))


def thirds_table(sets_by_who, frac_by_who, tested, ide, ridge):
    """Pooled coefficients in thirds of the visits (by share of the session elapsed)."""
    rows = []
    for lo, hi in THIRDS:
        sets = [s for who, v in sets_by_who.items() for s, f in zip(v, frac_by_who[who]) if lo <= f < hi]
        if len(sets) < 5:
            continue
        b, se, ll, n = fit(sets, [0, 1, 2], ridge)
        rows.append({"third": f"{lo:.0%}-{min(hi, 1):.0%}", "n": n, **{a: f"{b[i]:+.2f}+-{se[i]:.2f}" for i, a in enumerate(ATTRS)},
                     **lr_columns(sets, b, ll, tested, ridge), "cos to ideal": round(cosine(b, ide), 2)})
    print("\n-- pooled, by share of the session elapsed")
    print(pd.DataFrame(rows).to_string(index=False))


def visit_analysis(session, runs, data, gamma, attr, ridge):
    w = make_world(session, load_session(session).world_seed)
    ide = ideal(w)
    tested = ATTRS if attr == "all" else (attr,)
    print(f"\n=== {session} visits: {attr} (log-odds per attribute unit; walk as an offset)")
    print("ideal least-squares weight of each attribute on the true reward: " + ", ".join(f"{a} {x:+.2f}" for a, x in zip(ATTRS, ide)) +
          f"   (corr of attributes over bushes: " + ", ".join(f"{a}-{b} {np.corrcoef(getattr(w, a), getattr(w, b))[0, 1]:+.2f}"
                                                              for i, a in enumerate(ATTRS) for b in ATTRS[i + 1:]) + ")")
    sets_by_who, frac_by_who = {}, {}
    for who in runs:
        visits = data.get((who, session), {}).get("visits", [])
        sets_by_who[who] = [(pc.attr_matrix(w, v["cand"], False), v["chosen"], gamma[who] * v["walk"]) for v in visits]
        frac_by_who[who] = [v["frac"] for v in visits]
    attribute_table(sets_by_who, tested, ide, ridge, f"-- {session}: per participant (first visits)")
    thirds_table(sets_by_who, frac_by_who, tested, ide, ridge)
    for t in tested:
        # how often the chosen bush is the one with the highest value of the attribute among the candidates (chance = mean 1/size)
        top = [(int(np.argmax(getattr(w, t)[v["cand"]]) == v["chosen"]), 1 / len(v["cand"])) for who in runs for v in data.get((who, session), {}).get("visits", [])]
        if top:
            print(f"chosen bush has the highest {t} among its candidates: {np.mean([x[0] for x in top]):.0%} of {len(top)} visits (chance {np.mean([x[1] for x in top]):.0%})")


def trial_analysis(name, runs, data, attr, ide, ridge):
    trials = {who: data.get((who, name), {}).get("trials", []) for who in runs}
    if not any(trials.values()):
        print(f"\n=== {name}: no trials")
        return
    print(f"\n=== {name} trials: logistic regression of the choice on the attribute differences (right minus left), no intercept")
    diffs = np.array([np.subtract(t["right"], t["left"]) for v in trials.values() for t in v])
    cor = np.corrcoef(diffs.T)
    print("design: correlation of the attribute differences across trials: " +
          ", ".join(f"{a}-{b} {cor[i, j]:+.2f}" for i, a in enumerate(ATTRS) for j, b in enumerate(ATTRS) if j > i) +
          f"; mean |difference|: " + ", ".join(f"{a} {np.abs(diffs[:, i]).mean():.2f}" for i, a in enumerate(ATTRS)))
    sets = {who: [(np.array([t["left"], t["right"]], dtype=float) - 0.5, t["chosen"], np.zeros(2)) for t in v] for who, v in trials.items()}
    attribute_table(sets, ATTRS if attr == "all" else (attr,), ide, ridge, f"-- {name}: per participant")
    acc = {who: np.mean([t["correct"] for t in v]) for who, v in trials.items() if v}
    print("accuracy: " + ", ".join(f"{who} {a:.0%}" for who, a in acc.items()))


def attribute_main(argv):
    ap = argparse.ArgumentParser(prog="human_analysis.py attribute", description=__doc__.split("attribute:")[1].split("\n")[0])
    ap.add_argument("--sessions", default="S3", help="comma-separated sessions whose visits are analysed")
    ap.add_argument("--interludes", default="S3_Interlude", help="comma-separated Interludes whose trials are analysed")
    ap.add_argument("--attr", default="moisture", choices=(*ATTRS, "all"), help="the attribute to test (all: each of the three)")
    ap.add_argument("--ridge", type=float, default=0.1)
    ap.add_argument("--refresh", action="store_true", help="rebuild the cached choice sets (about 10 minutes)")
    a = ap.parse_args(argv)
    runs = finished_runs()
    data = pc.load_choice_sets(runs, a.refresh)
    worlds = {s: make_world(s, load_session(s).world_seed) for s in pc.MAIN}
    gamma = {who: pc.gamma_of([data[(who, s)]["visits"] for s in pc.MAIN if (who, s) in data], worlds) for who in runs}
    print("participants:", ", ".join(runs), "| walk coefficient per 10 units:", {who: round(g, 2) for who, g in gamma.items()})
    for s in filter(None, a.sessions.split(",")):
        visit_analysis(s, runs, data, gamma, a.attr, a.ridge)
    for name in filter(None, a.interludes.split(",")):
        w = make_world(name.removesuffix("_Interlude"), load_session(name.removesuffix("_Interlude")).world_seed)
        ide = ideal(w)
        trial_analysis(name, runs, data, a.attr, ide, a.ridge)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    name, rest = sys.argv[1], sys.argv[2:]
    if name == "attribute":
        attribute_main(rest)
    elif name in SCRIPTS:
        script = Path(__file__).resolve().parent / SCRIPTS[name]
        sys.argv = [str(script)] + rest
        runpy.run_path(str(script), run_name="__main__")
    else:
        sys.exit(f"unknown analysis {name!r}; choose from {', '.join([*SCRIPTS, 'attribute'])}")


if __name__ == "__main__":
    main()
