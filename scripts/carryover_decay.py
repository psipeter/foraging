"""How fast does an earlier session's prior give way to what the later session actually pays? A decay model over experience.

Exploratory; builds on prior_carryover.py (same cached choice sets, the same conditional-logit choice model with a walk offset).
For an earlier session S and a later one T, every choice in T is a visit (the k-th first visit of the session; k = bushes already
visited, the experience axis) or an Interlude trial of T (placed at k = the number of visits, since an Interlude shows no outcomes
and teaches nothing). The model scores each candidate bush by

    walk offset  +  A exp(-k/tau) z  +  B (1 - exp(-k/tau)) r

where z is the earlier session's prediction of the bush (standardised within the set) and r the later session's true reward of it,
so one timescale tau hands the choice from the carried prior (initial weight A, log-odds per SD) to the actual reward (asymptote B).
Interlude trials have their own gain g (on both terms), because a trial is a clean pair with no walking. Free: A, B, tau, g.

The earlier prediction z is either
  behaviour  the participant's own prior from S: a choice model fitted to S's Interlude trials and to S's visits weighted by
             (share of the session elapsed)^recency, so late visits count most and there is no cut-off (`--recency`, default 2);
  rule       the reward function of S applied to T's bushes (what a participant who had learned S perfectly would carry).
When the two sessions order T's bushes alike (|r| > 0.9) A and B are separated only by how the weight changes with k.

For every (S, T) pair: the transfer alignment (the correlation of S's rule with T's true reward over T's bushes), the fit (weak log-normal priors on tau, median 10 visits, and on g keep them off their bounds), the gain in
log-likelihood over the same model without the carried prior (A = 0), standard errors from the numerical Hessian, and the range of A and
tau when each participant is left out. The adjacent transitions are drawn in results/carryover_decay.png (`--save`).

    ./venv/bin/python scripts/carryover_decay.py [--kind behaviour,rule] [--recency 2] [--ridge 2] [--save]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prior_carryover as pc  # noqa: E402
from idle_analysis import MAIN, ROOT, finished_runs  # noqa: E402
from world import bush_value, load_session, make_world  # noqa: E402

NAMES = ("A", "B", "tau", "g")
LOWER = np.array([-6.0, -6.0, np.log(0.3), np.log(0.2)])
UPPER = np.array([6.0, 8.0, np.log(80.0), np.log(5.0)])
PENALTY = 0.01     # on A^2 + B^2, only to keep the fit finite when a set of choices is (nearly) separable
TAU_PRIOR = (np.log(10.0), 1.5)   # weak log-normal priors (median, sd of the log) on tau and the Interlude gain: the data are few and
GAIN_PRIOR = (0.0, 1.2)           # would otherwise leave them at their bounds


class Choices:
    """The choices of one later session as padded arrays: z and r per candidate, the walk offset, the chosen index, k, interlude flag."""

    def __init__(self, rows):
        self.n = len(rows)
        width = max(len(r["z"]) for r in rows)
        self.Z, self.R, self.O = (np.zeros((self.n, width)) for _ in range(3))
        self.mask = np.zeros((self.n, width), dtype=bool)
        for i, r in enumerate(rows):
            m = len(r["z"])
            self.Z[i, :m], self.R[i, :m], self.O[i, :m], self.mask[i, :m] = r["z"], r["r"], r["off"], True
        self.chosen = np.array([r["chosen"] for r in rows])
        self.k = np.array([r["k"] for r in rows], dtype=float)
        self.inter = np.array([r["inter"] for r in rows])
        self.who = np.array([r["who"] for r in rows])

    def subset(self, keep):
        out = object.__new__(Choices)
        for name in ("Z", "R", "O", "mask", "chosen", "k", "inter", "who"):
            setattr(out, name, getattr(self, name)[keep])
        out.n = int(keep.sum())
        return out

    def nll(self, theta):
        A, B, log_tau, log_g = theta
        decay = np.exp(-self.k / np.exp(log_tau))
        gain = np.where(self.inter, np.exp(log_g), 1.0)
        u = self.O + (gain * A * decay)[:, None] * self.Z + (gain * B * (1 - decay))[:, None] * self.R
        u = np.where(self.mask, u, -1e9)
        top = u.max(axis=1, keepdims=True)
        lse = top[:, 0] + np.log(np.exp(u - top).sum(axis=1))
        prior = 0.5 * ((log_tau - TAU_PRIOR[0]) / TAU_PRIOR[1]) ** 2 + 0.5 * ((log_g - GAIN_PRIOR[0]) / GAIN_PRIOR[1]) ** 2
        return -(u[np.arange(self.n), self.chosen] - lse).sum() + PENALTY * (A * A + B * B) + prior


def fit(ch, fixed_a=None, start=None):
    """Maximum a posteriori over (A, B, log tau, log g) (weak priors on the last two); `fixed_a` holds A (0: no carried prior). Returns (theta, nll)."""
    free = [i for i in range(4) if not (i == 0 and fixed_a is not None)]

    def expand(x):
        theta = np.empty(4)
        theta[free] = x
        if fixed_a is not None:
            theta[0] = fixed_a
        return theta

    starts = [start] if start is not None else [np.array([a, 1.0, np.log(t), 0.0]) for a in (-1.0, 1.0) for t in (3.0, 15.0)]
    best = None
    for s0 in starts:
        r = minimize(lambda x: ch.nll(expand(x)), np.asarray(s0, dtype=float)[free], method="L-BFGS-B",
                     bounds=list(zip(LOWER[free], UPPER[free])))
        if best is None or r.fun < best.fun:
            best = r
    return expand(best.x), float(best.fun)


def std_errors(ch, theta, h=1e-3):
    """Standard errors of (A, B, log tau, log g) from the central-difference Hessian of the negative log-likelihood."""
    H = np.zeros((4, 4))
    for i in range(4):
        for j in range(i, 4):
            ei, ej = np.eye(4)[i] * h, np.eye(4)[j] * h
            H[i, j] = H[j, i] = (ch.nll(theta + ei + ej) - ch.nll(theta + ei - ej) - ch.nll(theta - ei + ej) + ch.nll(theta - ei - ej)) / (4 * h * h)
    try:
        return np.sqrt(np.diag(np.linalg.inv(H)))
    except np.linalg.LinAlgError:
        return np.full(4, np.nan)


def standardise_with(values, sd):
    return [v - v.mean() for v in values] if not sd else [(v - v.mean()) / sd for v in values]


def build_choices(S, T, kind, ctx):
    """The choices of session T for the earlier prediction of session S."""
    data, worlds, rules, prior, gamma, who_list = (ctx[x] for x in ("data", "worlds", "rules", "prior", "gamma", "who_list"))
    wT = worlds[T]
    z_raw, r_raw, meta = [], [], []

    def predict(who, shape, color, moisture):
        if kind == "behaviour":
            return pc.phi(shape, color, moisture) @ prior[(who, S)]
        return np.asarray(bush_value(rules[S], shape, color, moisture), dtype=float)

    for who in who_list:
        visits = data[(who, T)]["visits"]
        for k, v in enumerate(visits):
            c = v["cand"]
            z_raw.append(predict(who, wT.shape[c], wT.color[c], wT.moisture[c]))
            r_raw.append(wT.value[c])
            meta.append({"who": who, "k": k, "inter": False, "off": gamma[who] * v["walk"], "chosen": v["chosen"]})
        for t in data.get((who, f"{T}_Interlude"), {}).get("trials", []):
            sh, co, mo = pc.trial_attrs(t)
            z_raw.append(predict(who, sh, co, mo))
            r_raw.append(np.asarray(bush_value(rules[T], sh, co, mo), dtype=float))
            meta.append({"who": who, "k": len(visits), "inter": True, "off": np.zeros(2), "chosen": t["chosen"]})
    is_visit = [not m["inter"] for m in meta]
    sd_z = np.concatenate([z - z.mean() for z, v in zip(z_raw, is_visit) if v]).std()
    sd_r = np.concatenate([r - r.mean() for r, v in zip(r_raw, is_visit) if v]).std()
    if not sd_z > 0:
        return None
    zs, rs = standardise_with(z_raw, sd_z), standardise_with(r_raw, sd_r)
    return Choices([{**m, "z": z, "r": r} for m, z, r in zip(meta, zs, rs)])


def behaviour_priors(ctx, ridge, recency):
    """Per participant and session: the choice-model weights from the session's Interlude and its visits weighted by (elapsed share)^recency."""
    data, worlds, gamma = ctx["data"], ctx["worlds"], ctx["gamma"]
    prior = {}
    for s in MAIN:
        for who in ctx["who_list"]:
            sets = [(pc.attr_matrix(worlds[s], v["cand"]), v["chosen"], gamma[who] * v["walk"], v["frac"] ** recency)
                    for v in data[(who, s)]["visits"]]
            for t in data.get((who, f"{s}_Interlude"), {}).get("trials", []):
                sh, co, mo = pc.trial_attrs(t)
                sets.append((pc.phi(sh, co, mo), t["chosen"], np.zeros(2), 1.0))
            prior[(who, s)] = pc.fit_logit(sets, 6, ridge)[0]
    return prior


def analyse(S, T, kind, ctx):
    ch = build_choices(S, T, kind, ctx)
    if ch is None:
        return None
    theta, nll = fit(ch)
    _, nll0 = fit(ch, fixed_a=0.0)
    se = std_errors(ch, theta)
    loo = []
    for who in ctx["who_list"]:
        th, _ = fit(ch.subset(ch.who != who), start=theta)
        loo.append(th)
    loo = np.array(loo)
    align = np.corrcoef(bush_value(ctx["rules"][S], *(getattr(ctx["worlds"][T], a) for a in pc.ATTRS)), ctx["worlds"][T].value)[0, 1]
    lr = 2 * (nll0 - nll)
    return {"S": S, "T": T, "kind": kind, "n": ch.n, "alignment": align, "A": theta[0], "se_A": se[0], "B": theta[1], "se_B": se[1],
            "tau": float(np.exp(theta[2])), "se_logtau": se[2], "g": float(np.exp(theta[3])), "gain_logL": nll0 - nll, "p_LR": float(chi2.sf(lr, 1)),
            "A_range": f"{loo[:, 0].min():+.1f}..{loo[:, 0].max():+.1f}", "tau_range": f"{np.exp(loo[:, 2]).min():.1f}..{np.exp(loo[:, 2]).max():.1f}",
            "theta": theta, "k_max": float(ch.k[~ch.inter].max())}


def figure(results, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    import plots
    cfg = plots.MODES["paper"]
    sns.set_theme(style="ticks", rc={**cfg["rc"], "axes.grid": False})
    adj = [r for r in results if MAIN.index(r["T"]) - MAIN.index(r["S"]) == 1]
    kinds = sorted({r["kind"] for r in adj})
    fig, axes = plt.subplots(len(kinds), len(adj) // len(kinds), figsize=(cfg["width"] * 1.5, cfg["panel_height"] * len(kinds) + 0.8), squeeze=False, sharey=True)
    for ax, r in zip(axes.ravel(), sorted(adj, key=lambda r: (r["kind"], r["T"]))):
        k = np.arange(0, r["k_max"] + 1)
        A, B, lt = r["theta"][0], r["theta"][1], r["theta"][2]
        decay = np.exp(-k / np.exp(lt))
        ax.plot(k, A * decay, color=plots.SERIES[0], ls=plots.STYLES[0], label="earlier prior")
        ax.plot(k, B * (1 - decay), color=plots.SERIES[1], ls=plots.STYLES[1], label="true reward")
        ax.axhline(0, color="0.6", lw=0.6)
        ax.set(title=f"{r['S']} -> {r['T']} ({r['kind']})", xlabel="visits so far in the session")
    for ax in axes[:, 0]:
        ax.set_ylabel("weight (log-odds per SD)")
    axes[0, 0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=cfg["dpi"])
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kind", default="behaviour,rule")
    ap.add_argument("--recency", type=float, default=2.0, help="exponent on the elapsed share that weights an earlier session's visits in its prior")
    ap.add_argument("--ridge", type=float, default=2.0)
    ap.add_argument("--adjacent-only", action="store_true")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    runs = finished_runs()
    data = pc.load_choice_sets(runs)
    who_list = list(runs)
    worlds = {s: make_world(s, load_session(s).world_seed) for s in MAIN}
    ctx = {"data": data, "worlds": worlds, "rules": {s: load_session(s).reward_function for s in MAIN}, "who_list": who_list}
    ctx["gamma"] = {w: pc.gamma_of([data[(w, s)]["visits"] for s in MAIN], worlds) for w in who_list}
    ctx["prior"] = behaviour_priors(ctx, a.ridge, a.recency)
    print("participants:", ", ".join(who_list), "| rules:",
          {s: [(c[:5], round(ctx["rules"][s][c + "Component"]["weight"], 2), ctx["rules"][s][c + "Component"]["basisFunctionType"]) for c in pc.ATTRS if ctx["rules"][s][c + "Component"]["weight"]] +
             ([("bumps", len(ctx["rules"][s]["bumps"]))] if ctx["rules"][s].get("bumps") else []) for s in MAIN})
    results = []
    for T in MAIN[1:]:
        for S in MAIN[:MAIN.index(T)]:
            if a.adjacent_only and MAIN.index(T) - MAIN.index(S) != 1:
                continue
            for kind in a.kind.split(","):
                r = analyse(S, T, kind, ctx)
                if r:
                    results.append(r)
    df = pd.DataFrame(results).drop(columns=["theta", "k_max"])
    pd.set_option("display.width", 250)
    cols = ["S", "T", "kind", "n", "alignment", "A", "se_A", "B", "se_B", "tau", "se_logtau", "g", "gain_logL", "p_LR", "A_range", "tau_range"]
    adj = df[[MAIN.index(t) - MAIN.index(s) == 1 for s, t in zip(df.S, df["T"])]]
    print("\n=== adjacent transitions: A = weight on the earlier prediction at the start, B = weight on the true reward once learned (log-odds per SD), "
          "tau = visits for the hand-over, g = Interlude gain")
    print("(gain_logL: log-likelihood over the same model without the carried prior; p_LR from 2x that, 1 df, ignoring that tau is unidentified at A = 0; "
          "*_range: leave-one-participant-out)")
    print(adj[cols].round(2).to_string(index=False))
    print("\n=== all earlier sessions, for each later one")
    print(df[~df.index.isin(adj.index)][cols].round(2).to_string(index=False))
    if a.save:
        out = ROOT / "results"
        df.to_csv(out / "carryover_decay.csv", index=False)
        figure(results, out / "carryover_decay.png")


if __name__ == "__main__":
    main()
