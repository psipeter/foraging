"""Pairs against rankings: which Interlude design recovers a learned value function best, for the same number of harvests?

The test bed of `interlude_design.py` for the ranking format. A *target* is a learned value function over (shape, colour) (the truth, a partial
learner that knows only one feature, or a peak found in the wrong place) whose *design* is built from the true reward, as the game builds it. The
target chooses with noise (a softmax with temperature `tau` times the spread of its values over the plane); a design is either `pairs`
(`n_pairs` pairs, reward and feature gaps both spread evenly, as the Hybrid generator does) or `ranking` (`sets` sets of `size` bushes from
`ranking.choose_sets`, ranked by a sequential softmax, i.e. a Plackett-Luce draw: one pair is the same logistic). A basis is fitted to the picks (a
ridge logistic preference for pairs, a ridge Plackett-Luce for rankings, the ridge chosen by held-out likelihood over whole pairs or sets) and the
fitted function is scored against the target over random bushes: Pearson and Spearman correlation and the gap-weighted share of pairs ordered alike.

The designs are compared at the same number of *harvests* (a pair is one, a ranking of size k is k, of which the last costs nothing in
information), since in the game a harvest is the unit of time; a pair also costs a walk and a fade that a ranking does not, so the comparison favours pairs.

    ./venv/bin/python scripts/ranking_design.py run --seeds 20
"""

import argparse
import sys
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logsumexp
from scipy.stats import rankdata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents
import interlude
import ranking
import synthetic
from world import bush_value

RIDGES = (0.01, 0.1, 1.0, 10.0)
FOLDS = 5
POOL = 4000                      # candidate bushes a ranking design is chosen from
PAIR_CANDIDATES = 3000           # random pairs a pair design is chosen from
REFERENCE = 600                  # random bushes the fitted function is scored on
MIN_GAP = 0.25                   # the tie gap of both designs (points per fruit)
STAGE_MOISTURE = 0.5


def with_bump(centre_shape, centre_colour, width, height=4.0, width_colour=0.0, angle=0.0):
    return {**synthetic.reward_function({}), "bumps": [{"centerShape": centre_shape, "centerColor": centre_colour, "width": width, "widthColor": width_colour,
                                                       "height": height, "angle": angle}]}


REWARDS = {
    "linear two": synthetic.reward_function({"shape": 0.5, "color": 0.5}),
    "linear one": synthetic.reward_function({"color": 1.0}),
    "linear mixed": synthetic.reward_function({"shape": 0.7, "color": 0.3}, direction={"color": 1}),
    "round peak": with_bump(0.65, 0.35, 0.18),
    "ridge": with_bump(0.5, 0.5, 0.3, width_colour=0.1, angle=40.0),
}


def value_of(reward_function, x):
    return np.asarray(bush_value(reward_function, x[:, 0], x[:, 1], np.full(len(x), STAGE_MOISTURE)), dtype=float)


class Target:
    """A learned function f(x (n, 2)) -> (n,) on the plane, and the true reward function the designs are built from."""

    def __init__(self, name, reward_function, f):
        self.name, self.reward_function, self.f = name, reward_function, f
        u = np.random.default_rng(7).random((4000, 2))
        self.spread = max(float(np.std(f(u))), 1e-9)
        self.reward_scale = max(float(np.std(value_of(reward_function, u))), 1e-9)


def targets():
    """For each reward: the learner that has it exactly, and a flawed one (a linear reward learned on one feature only, a peak found displaced)."""
    out = []
    for name, rf in REWARDS.items():
        out.append(Target(f"{name} / exact", rf, lambda x, rf=rf: value_of(rf, x)))
    out.append(Target("linear two / shape only", REWARDS["linear two"], lambda x: value_of(synthetic.reward_function({"shape": 1.0}), x)))
    out.append(Target("round peak / displaced", REWARDS["round peak"], lambda x: value_of(with_bump(0.5, 0.5, 0.22), x)))
    return out


# ---- designs --------------------------------------------------------------------------------------

def pair_design(target, n_pairs, rng):
    """(left (n, 2), right (n, 2)): pairs whose true reward gap and feature distance are both spread evenly (the Hybrid generator's own selection)."""
    a, b = rng.random((PAIR_CANDIDATES, 2)), rng.random((PAIR_CANDIDATES, 2))
    va, vb = value_of(target.reward_function, a), value_of(target.reward_function, b)
    rgap, fgap = np.abs(va - vb), np.sqrt(((a - b) ** 2).mean(axis=1))
    rows = [(i, a[i], b[i], rgap[i], fgap[i], bool(va[i] > vb[i])) for i in range(PAIR_CANDIDATES)]
    chosen, _ = interlude.choose_gap_trials(rows, n_pairs, (3, 4), {3: MIN_GAP, 4: 0.1}, rng)
    return np.array([r[1] for r in chosen]), np.array([r[2] for r in chosen])


def ranking_design(target, sets, size, rng):
    """(sets, size, 2) points of `sets` sets of `size` bushes, chosen together as the game's generator does."""
    pool = {"shape": rng.random(POOL), "color": rng.random(POOL)}
    pool["value"] = value_of(target.reward_function, np.column_stack([pool["shape"], pool["color"]]))
    chosen = ranking.choose_sets(SimpleNamespace(shape_varies=True, color_varies=True), pool, sets, size, MIN_GAP, rng, steps=8000)
    return np.stack([np.stack([pool["shape"][chosen[s]], pool["color"][chosen[s]]], axis=1) for s in range(sets)])


# ---- choices --------------------------------------------------------------------------------------

def choose_pairs(target, left, right, tau, rng):
    """1 where the target picks the right bush: a softmax on its value difference."""
    p = expit((target.f(right) - target.f(left)) / (tau * target.spread))
    return (rng.random(len(left)) < p).astype(float)


def rank_sets(target, points, tau, rng):
    """Orders (sets, size): positions within each set, best first, by a Plackett-Luce draw (Gumbel noise on f / (tau * spread))."""
    f = np.stack([target.f(p) for p in points]) / (tau * target.spread)
    return np.argsort(-(f + rng.gumbel(size=f.shape)), axis=1)


# ---- fits -----------------------------------------------------------------------------------------

def fit_pairs(D, y, ridge, iters=40):
    """Ridge logistic regression of the picks y (1 = right) on the feature differences D (right minus left), no intercept, by Newton."""
    w = np.zeros(D.shape[1])
    for _ in range(iters):
        p = expit(D @ w)
        step = np.linalg.solve((D * (p * (1 - p))[:, None]).T @ D + ridge * np.eye(D.shape[1]), D.T @ (y - p) - ridge * w)
        w = w + np.clip(step, -5, 5)
        if np.abs(step).max() < 1e-7:
            break
    return w


def pair_loglik(D, y, w):
    p = np.clip(expit(D @ w), 1e-9, 1 - 1e-9)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def pl_negloglik(w, features, orders, ridge):
    """Negative log-likelihood of the orders under a Plackett-Luce model (the best of those left is picked with a softmax of w . phi), with a ridge penalty, and its gradient."""
    nll, grad = 0.5 * ridge * float(w @ w), ridge * w
    for phi, order in zip(features, orders):
        u = phi @ w
        for r in range(len(order) - 1):
            rest = order[r:]
            p = np.exp(u[rest] - logsumexp(u[rest]))
            nll -= u[order[r]] - logsumexp(u[rest])
            grad = grad - (phi[order[r]] - p @ phi[rest])
    return nll, grad


def fit_orders(features, orders, ridge):
    return minimize(pl_negloglik, np.zeros(features[0].shape[1]), args=(features, orders, ridge), jac=True, method="L-BFGS-B").x


def pl_loglik(w, features, orders):
    return -pl_negloglik(w, features, orders, 0.0)[0]


def cv_ridge(n_units, fit, loglik, rng, folds=FOLDS):
    """The ridge with the best held-out log-likelihood; whole pairs (or whole sets) are held out. `fit(train_ids, ridge)` returns weights, `loglik(test_ids, w)` the score."""
    fold = rng.permutation(n_units) % min(folds, n_units)
    scores = []
    for ridge in RIDGES:
        s = 0.0
        for k in range(min(folds, n_units)):
            test, train = np.flatnonzero(fold == k), np.flatnonzero(fold != k)
            if len(test) and len(train):
                s += loglik(test, fit(train, ridge))
        scores.append(s)
    return RIDGES[int(np.argmax(scores))]


def basis(name):
    if name == "linear":
        return lambda x: np.asarray(x, dtype=float) - 0.5
    if name.startswith("joint"):                  # Gaussian bumps on a 6 x 6 grid of the plane: can hold a peak or a ridge (the additive "rbf" cannot)
        length, axis = float(name.removeprefix("joint")), np.linspace(0.0, 1.0, 6)
        centres = np.array([(a, b) for a in axis for b in axis])
        return lambda x: np.exp(-((np.asarray(x, dtype=float)[:, None, :] - centres[None]) ** 2).sum(-1) / (2.0 * length ** 2))
    rbf = agents.RBFFeatures(length_scale=float(name.removeprefix("rbf")), n_centers=8)
    return lambda x: rbf(np.column_stack([x, np.full(len(x), STAGE_MOISTURE)]))


# ---- scores ---------------------------------------------------------------------------------------

def score(target, g, rng, n_pairs=2000):
    """Pearson and Spearman correlation of the fitted function g with the target's over random bushes, and the share of random pairs (weighted by the size of the
    target's gap) they order alike."""
    x = rng.random((REFERENCE, 2))
    f, fitted = target.f(x), g(x)
    if np.std(fitted) < 1e-12:
        return {"pearson": 0.0, "spearman": 0.0, "pair": 0.5}
    i, j = rng.integers(REFERENCE, size=(2, n_pairs))
    weight = np.abs(f[i] - f[j])
    return {"pearson": float(np.corrcoef(f, fitted)[0, 1]), "spearman": float(np.corrcoef(rankdata(f), rankdata(fitted))[0, 1]),
            "pair": float(np.sum(weight * (np.sign(f[i] - f[j]) == np.sign(fitted[i] - fitted[j]))) / max(np.sum(weight), 1e-12))}


# ---- one cell -------------------------------------------------------------------------------------

def run_design(target, kind, size, count, basis_name, tau, seed):
    """Scores of one design on one target: `kind` "pairs" (`count` pairs; size 2) or "ranking" (`count` sets of `size` bushes)."""
    rng = np.random.default_rng([seed, zlib.crc32(f"{target.name}{kind}{size}{count}{basis_name}{tau}".encode())])
    phi = basis(basis_name)
    if kind == "pairs":
        left, right = pair_design(target, count, rng)
        y = choose_pairs(target, left, right, tau, rng)
        D = phi(right) - phi(left)
        ridge = cv_ridge(len(y), lambda tr, r: fit_pairs(D[tr], y[tr], r), lambda te, w: pair_loglik(D[te], y[te], w), rng)
        w = fit_pairs(D, y, ridge)
    else:
        points = ranking_design(target, count, size, rng)
        orders = rank_sets(target, points, tau, rng)
        features = [phi(p) for p in points]
        ridge = cv_ridge(count, lambda tr, r: fit_orders([features[i] for i in tr], [orders[i] for i in tr], r),
                         lambda te, w: pl_loglik(w, [features[i] for i in te], [orders[i] for i in te]), rng)
        w = fit_orders(features, orders, ridge)
    row = score(target, lambda x, w=w: phi(x) @ w, rng)
    row.update(ridge=ridge)
    return row


DESIGNS = {"pairs 20": ("pairs", 2, 20), "pairs 10": ("pairs", 2, 10), "rank 3x6": ("ranking", 6, 3), "rank 4x6": ("ranking", 6, 4), "rank 4x4": ("ranking", 4, 4),
           "rank 6x3": ("ranking", 3, 6)}


def harvests(design):
    kind, size, count = DESIGNS[design]
    return count if kind == "pairs" else count * size


def run(designs, basis_names, taus, seeds, target_list=None):
    rows = []
    for t in (target_list or targets()):
        for design in designs:
            kind, size, count = DESIGNS[design]
            for b in basis_names:
                for tau in taus:
                    for s in range(seeds):
                        rows.append({"target": t.name, "design": design, "harvests": harvests(design), "basis": b, "tau": tau, "seed": s, **run_design(t, kind, size, count, b, tau, s)})
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["run"])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--designs", default=",".join(DESIGNS))
    ap.add_argument("--bases", default="linear,rbf0.5,joint0.25")
    ap.add_argument("--taus", default="0.15,0.3,0.6")
    ap.add_argument("--out", default=None, help="write the rows as CSV")
    args = ap.parse_args(argv)
    t0 = time.time()
    frame = run(args.designs.split(","), args.bases.split(","), [float(t) for t in args.taus.split(",")], args.seeds)
    if args.out:
        frame.to_csv(args.out, index=False)
    pd.set_option("display.width", 200)
    for b, part in frame.groupby("basis"):
        print(f"\nbasis {b}: mean over targets and seeds (Pearson of the fitted function with the target's)")
        print(part.pivot_table(index=["design", "harvests"], columns="tau", values="pearson", aggfunc="mean").round(3))
        print(part.pivot_table(index=["design", "harvests"], columns="tau", values="pair", aggfunc="mean").round(3))
    print(f"\n{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
