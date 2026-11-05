"""Do participants carry what they learned in one session into the start of the next?

Exploratory (hypothesis: the practice session leaves a shape prior, so the first seconds of S1 are spent foraging on shape).

Behaviour is read as choices, because a participant never reports a belief:
  * a visit: the bush harvested first among the bushes still unvisited that were in view since the previous bout ended (visibility.py;
    the chosen bush is always in the set), with the walk to each as a cost;
  * an Interlude trial: one of two bushes (outcomes are hidden, so the choice shows what was learned).
A choice model (conditional logit) scores a bush as  beta . phi(shape, color, moisture) - gamma . walk,  phi = the three attributes
and their squares, centred on 0.5 (a squared term lets a peaked rule like S2's show up). The walk coefficient gamma is fitted once per
participant, from walk alone.

1. Prior from session s (per participant): beta fitted (ridge) to the visits of the last `--tail` (0.2) of session s plus the 20 trials
   of its Interlude (P's has 3). The prior's utility of any bush is beta . phi.
2. Early window of the next session: the visits of each fifth of session s' (`--window`) are modelled with the prior's utility, standardised,
   and the session's true reward of the bush, standardised, as the two predictors of the choice (walk as an offset):
     lambda_prior  how much the choice follows the earlier session's behavioural prior,
     lambda_rule   how much it follows the session's actual reward (learned or not).
   Log-odds per standard deviation, pooled over participants. The same is done with the *rule* of the earlier session in place of the
   behavioural prior (what a participant who had learned s perfectly would carry), which does not depend on the thin data of step 1.
3. Feature view: the same model with the three attributes as predictors per fifth of each session: which feature steers the choices when.

Few visits fall in a fifth of a short session (S1: about 3 per participant), so every estimate carries its n and standard error;
read them as indications. Choice sets are cached in results/prior_choice_sets.pkl (`--refresh` rebuilds; about 10 minutes).

    ./venv/bin/python scripts/prior_carryover.py [--tail 0.2] [--window 0.2] [--ridge 2] [--refresh]
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay  # noqa: E402
import rundata  # noqa: E402
import visibility  # noqa: E402
from idle_analysis import DATA, MAIN, ROOT, bouts_of, finished_runs  # noqa: E402
from world import bush_value, load_session, make_world  # noqa: E402

CACHE = ROOT / "results" / "prior_choice_sets.pkl"
VIEW_STEP = 0.2          # s between the frames at which what was in view is sampled
WALK_SCALE = 10.0        # world units per unit of the walk covariate
ATTRS = ("shape", "color", "moisture")
PRIOR_FEATURES = [f"{a}" for a in ATTRS] + [f"{a}^2" for a in ATTRS]


def phi(shape, color, moisture, quadratic=True):
    x = np.stack([np.asarray(shape) - 0.5, np.asarray(color) - 0.5, np.asarray(moisture) - 0.5], axis=-1)
    return np.concatenate([x, x * x], axis=-1) if quadratic else x


# --------------------------------------------------------------------------------------------------
# Choice sets
# --------------------------------------------------------------------------------------------------

def build_sets(runs):
    """{(who, session): {"visits": [...], "trials": [...], "length": s}} for P and S1-S5 and their Interludes."""
    out = {}
    for who, run in runs.items():
        for folder in sorted((DATA / run).glob("[0-9][0-9]")):
            data = rundata.read_session(folder)
            name = data["session"]["name"]
            if name.endswith("_Interlude"):
                rows = []
                for t in data["trials"]:
                    if t["timed_out"] or t["choice"] not in ("left", "right"):
                        continue
                    x = {s: [t[f"{s}_{a}"] for a in ATTRS] for s in ("left", "right")}
                    rows.append({"left": x["left"], "right": x["right"], "chosen": int(t["choice"] == "right"), "correct": int(t["choice_correct"])})
                out[(who, name)] = {"trials": rows}
                continue
            if name not in MAIN:
                continue
            log = replay.load_session_log(folder)
            w = make_world(name, log.manifest["world_seed"])
            tr = log.traj
            t = tr[:, 0]
            bouts = bouts_of(log.events, w.fruit_count)
            windows, visited, t_prev, at = [], set(), 0.0, (0.0, 0.0)
            for b in bouts:
                if b["tree"] not in visited:
                    times = np.arange(t_prev, b["press"], VIEW_STEP)
                    frames = np.unique(np.clip(np.searchsorted(t, times if len(times) else [b["press"]]), 0, len(t) - 1))
                    windows.append({"who": who, "session": name, "press": b["press"], "frac": b["press"] / float(t[-1]),
                                    "chosen": int(b["tree"]), "frames": frames, "from": at, "visited": set(visited)})
                    visited.add(b["tree"])
                i = min(np.searchsorted(t, b["release"] - 1e-6), len(t) - 1)
                at, t_prev = (float(tr[i, 1]), float(tr[i, 2])), b["release"]
            frames = np.unique(np.concatenate([x["frames"] for x in windows])) if windows else np.array([], dtype=int)
            vis = visibility.visible_bushes(log, dt=None, frames=frames) if len(frames) else None
            row_of = {int(f): k for k, f in enumerate(frames)}
            visits = []
            for x in windows:
                seen = set()
                for f in x["frames"]:
                    seen.update(int(j) for j in vis.at(row_of[int(f)])["tree_id"])
                cand = sorted((seen - x["visited"]) | {x["chosen"]})
                p = np.array(x["from"])
                walk = np.maximum(0.0, np.hypot(*(w.pos[cand] - p).T) - w.reach[cand])
                visits.append({"frac": x["frac"], "chosen": cand.index(x["chosen"]), "cand": np.array(cand), "walk": walk / WALK_SCALE,
                               "seen_chosen": x["chosen"] in seen})
            out[(who, name)] = {"visits": visits, "length": float(t[-1])}
            print(f"  {who} {name}: {len(visits)} first visits", flush=True)
    return out


def load_choice_sets(runs, refresh=False):
    """The cached choice sets (built on first use, or when `refresh`)."""
    if CACHE.exists() and not refresh:
        return pickle.loads(CACHE.read_bytes())
    print("building choice sets ...")
    data = build_sets(runs)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_bytes(pickle.dumps(data))
    return data


def trial_attrs(t):
    """(shape, color, moisture) of an Interlude trial's two bushes, each an array of (left, right)."""
    return tuple(np.array([t["left"][i], t["right"][i]]) for i in range(3))


# --------------------------------------------------------------------------------------------------
# Conditional logit
# --------------------------------------------------------------------------------------------------

def fit_logit(sets, d, ridge):
    """Penalised conditional logit by Newton. `sets`: [(X (k, d), chosen index, offset (k,)[, weight])]. Returns (beta, standard errors, n)."""
    beta = np.zeros(d)
    if not sets:
        return beta, np.full(d, np.nan), 0
    for _ in range(50):
        grad, hess = -ridge * beta, -ridge * np.eye(d)
        for X, c, off, *wt in sets:
            wt = wt[0] if wt else 1.0
            u = X @ beta + off
            p = np.exp(u - u.max())
            p /= p.sum()
            mean = p @ X
            grad += wt * (X[c] - mean)
            hess -= wt * ((X * p[:, None]).T @ X - np.outer(mean, mean))
        step = np.linalg.solve(-hess, grad)
        beta = beta + np.clip(step, -3, 3)
        if np.abs(step).max() < 1e-7:
            break
    se = np.sqrt(np.maximum(np.diag(np.linalg.inv(-hess)), 0.0))
    return beta, se, len(sets)


def attr_matrix(w, cand, quadratic=True):
    return phi(w.shape[cand], w.color[cand], w.moisture[cand], quadratic)


def gamma_of(visits_by_session, worlds):
    """The walk coefficient of one participant: a walk-only model over all their first visits."""
    sets = [(v["walk"][:, None], v["chosen"], 0.0) for s in visits_by_session for v in s]
    return float(fit_logit(sets, 1, 0.05)[0][0])


# --------------------------------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------------------------------

def standardise(values_per_set):
    """Centre each set and divide by the standard deviation of the pooled centred values."""
    centred = [v - v.mean() for v in values_per_set]
    sd = np.concatenate(centred).std() if centred else 1.0
    return [c / sd for c in centred] if sd > 0 else centred


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tail", type=float, default=0.2, help="the last share of a session whose visits define its behavioural prior")
    ap.add_argument("--window", type=float, default=0.2, help="width of a session-time window, as a share of the session")
    ap.add_argument("--ridge", type=float, default=2.0, help="L2 penalty on the prior's weights (the data are few)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--hide-rules", action="store_true", help="do not print each session's true reward weights")
    a = ap.parse_args()
    runs = finished_runs()
    data = load_choice_sets(runs, a.refresh)
    who_list = list(runs)
    sessions = list(MAIN)
    worlds = {s: make_world(s, load_session(s).world_seed) for s in sessions}
    rules = {s: load_session(s).reward_function for s in sessions}
    true = {s: worlds[s].value for s in sessions}
    nwin = int(round(1 / a.window))
    pd.set_option("display.width", 220)

    gamma = {w: gamma_of([data[(w, s)]["visits"] for s in sessions if (w, s) in data], worlds) for w in who_list}
    print("participants:", ", ".join(who_list), "| walk coefficient per 10 units:", {w: round(g, 2) for w, g in gamma.items()})
    if not a.hide_rules:
        print("rules:", {s: [(c[:5], round(rules[s][c + "Component"]["weight"], 2)) for c in ATTRS if rules[s][c + "Component"]["weight"]] +
                         ([("bumps", len(rules[s]["bumps"]))] if rules[s].get("bumps") else []) for s in sessions})

    def visit_sets(who, s, lo=0.0, hi=1.0001):
        return [v for v in data.get((who, s), {}).get("visits", []) if lo <= v["frac"] < hi]

    # ---- 1. the prior each session leaves ------------------------------------------------------------------------
    prior = {}
    rows = []
    for s in sessions:
        w = worlds[s]
        for who in who_list:
            sets = []
            for v in visit_sets(who, s, 1 - a.tail):
                sets.append((attr_matrix(w, v["cand"]), v["chosen"], gamma[who] * v["walk"]))
            n_visits = len(sets)
            trials = data.get((who, f"{s}_Interlude"), {}).get("trials", [])
            for t in trials:
                X = phi(np.array([t["left"][0], t["right"][0]]), np.array([t["left"][1], t["right"][1]]), np.array([t["left"][2], t["right"][2]]))
                sets.append((X, t["chosen"], np.zeros(2)))
            beta, se, n = fit_logit(sets, 6, a.ridge)
            prior[(who, s)] = beta
            u = attr_matrix(w, np.arange(w.n)) @ beta
            rows.append({"session": s, "who": who, "visits": n_visits, "trials": len(trials), **{f: beta[i] for i, f in enumerate(PRIOR_FEATURES)},
                         "corr_with_true": np.corrcoef(u, true[s])[0, 1] if np.std(u) > 0 else np.nan,
                         "interlude_correct": np.mean([t["correct"] for t in trials]) if trials else np.nan})
    pr = pd.DataFrame(rows)
    print(f"\n=== 1. the prior each session leaves (ridge {a.ridge}; weights in log-odds per attribute unit, centred on 0.5)")
    print(pr.round(2).to_string(index=False))
    print("\n-- pooled over participants (mean weights; correlation of the prior's utility with the session's true reward over all bushes)")
    print(pr.groupby("session")[PRIOR_FEATURES + ["corr_with_true", "interlude_correct"]].mean().reindex(sessions).round(2).to_string())

    # ---- 2. feature view: what steers the choices in each fifth of each session --------------------------------------
    print(f"\n=== 2. which attribute steers visit choices, by share of the session elapsed (pooled over participants; log-odds per attribute "
          f"unit +- se; walk as an offset)")
    for s in sessions:
        w = worlds[s]
        print(f"\n{s}" + ("   (true reward weights: " + ", ".join(f"{c} {rules[s][c + 'Component']['weight']:.2f}" for c in ATTRS) + ")" if not a.hide_rules else ""))
        out = []
        for k in range(nwin):
            lo, hi = k * a.window, (k + 1) * a.window + (1e-4 if k == nwin - 1 else 0)
            sets = [(attr_matrix(w, v["cand"], False), v["chosen"], gamma[who] * v["walk"])
                    for who in who_list for v in visit_sets(who, s, lo, hi)]
            b, se, n = fit_logit(sets, 3, 0.5)
            out.append({"window": f"{lo:.0%}-{min(hi, 1):.0%}", "sets": n, **{f"{c}": f"{b[i]:+.1f}+-{se[i]:.1f}" for i, c in enumerate(ATTRS)}})
        print(pd.DataFrame(out).to_string(index=False))

    # ---- 3. carry-over ---------------------------------------------------------------------------------------------------
    def design(later, earlier, kind):
        """[(who, visit, z, r)] for every first visit of `later`: the earlier session's predicted utility of each candidate bush and the later
        session's true reward of it, each centred within the set and divided by its SD over the whole session (so windows are comparable)."""
        w = worlds[later]
        meta = [(who, v) for who in who_list for v in visit_sets(who, later)]
        if kind == "behaviour":
            zs = [attr_matrix(w, v["cand"]) @ prior[(who, earlier)] for who, v in meta]
        else:
            zs = [np.asarray(bush_value(rules[earlier], w.shape[v["cand"]], w.color[v["cand"]], w.moisture[v["cand"]]), dtype=float) for who, v in meta]
        rs = [true[later][v["cand"]] for who, v in meta]
        return [(who, v, z, r) for (who, v), z, r in zip(meta, standardise(zs), standardise(rs))]

    def collinear(rows):
        """Whether the earlier prediction and the later true reward are the same ordering of bushes (|r| > 0.9), so they cannot be told apart."""
        z, r = (np.concatenate([x[i] for x in rows]) for i in (2, 3))
        return abs(np.corrcoef(z, r)[0, 1]) > 0.9

    def fit_window(rows, lo, hi, single=False, who=None):
        """Two predictors (earlier prediction, true reward), or the earlier prediction alone when `single`."""
        sets = [(np.stack([z, r], axis=1)[:, :1 if single else 2], v["chosen"], gamma[w_] * v["walk"])
                for w_, v, z, r in rows if lo <= v["frac"] < hi and (who is None or w_ == who)]
        return fit_logit(sets, 1 if single else 2, 0.05)

    def cell(b, se, i):
        return f"{b[i]:+.2f}+-{se[i]:.2f}"

    print(f"\n=== 3. does an earlier session's prior steer the choices of a later one? log-odds per SD of the predictor (+- se), with the later "
          f"session's true reward in the same model; first = the first {a.window:.0%} of the session, rest = everything after it")
    print("(behaviour: the participant's own prior from the earlier session's end; rule: the earlier session's actual reward function.\n"
          " When the earlier prediction and the later true reward order the bushes alike (|r| > 0.9) they cannot be separated: only the earlier "
          "prediction is fitted, and its sign says whether choices follow it (+) or the opposite (-); marked 'alone')")
    for later in sessions[1:]:
        print(f"\nlater session {later}")
        out = []
        for earlier in sessions[:sessions.index(later)]:
            for kind in ("behaviour", "rule"):
                rows_ = design(later, earlier, kind)
                single = collinear(rows_)
                for label, lo, hi in (("first", 0.0, a.window), ("rest", a.window, 1.0001)):
                    b, se, n = fit_window(rows_, lo, hi, single)
                    if n:
                        out.append({"from": earlier, "prior": kind, "window": label, "sets": n, "lambda_prior": cell(b, se, 0) + (" alone" if single else ""),
                                    "lambda_true_reward": "" if single else cell(b, se, 1)})
        print(pd.DataFrame(out).to_string(index=False))

    print("\n=== 3b. decay of the carried prior within the session, adjacent sessions only (behavioural prior of the previous session)")
    for later in sessions[1:]:
        earlier = sessions[sessions.index(later) - 1]
        rows_ = design(later, earlier, "behaviour")
        single = collinear(rows_)
        out = []
        for k in range(nwin):
            lo, hi = k * a.window, (k + 1) * a.window + (1e-4 if k == nwin - 1 else 0)
            b, se, n = fit_window(rows_, lo, hi, single)
            if n:
                out.append({"window": f"{lo:.0%}-{min(hi, 1):.0%}", "sets": n, f"prior({earlier})": cell(b, se, 0) + (" alone" if single else ""),
                            "true reward": "" if single else cell(b, se, 1)})
        print(f"\n{earlier} -> {later}")
        print(pd.DataFrame(out).to_string(index=False))

    print("\n=== 3c. per participant, the earlier session's rule as the one predictor (+: follows the earlier rule), first 40% / last 60% of the session")
    for later in sessions[1:]:
        earlier = sessions[sessions.index(later) - 1]
        rows_ = design(later, earlier, "rule")
        out = []
        for who in who_list:
            r_ = {}
            for label, lo, hi in (("first 40%", 0.0, 0.4), ("last 60%", 0.4, 1.0001)):
                b, se, n = fit_window(rows_, lo, hi, True, who)
                r_[label] = f"{b[0]:+.2f}+-{se[0]:.2f} (n={n})" if n else ""
            out.append({"who": who, **r_})
        print(f"\n{earlier} -> {later}")
        print(pd.DataFrame(out).to_string(index=False))

    n_seen = np.mean([v["seen_chosen"] for d in data.values() for v in d.get("visits", [])])
    print(f"\nthe chosen bush was among those in view since the previous bout ended in {n_seen:.0%} of visits (the rest were added to their set)")


if __name__ == "__main__":
    main()
