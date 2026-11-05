"""A test bed for the design of the Interlude: how well can the participants' kind of fit recover what an agent has learned, given a trial set?

A *target* is a learned value function f(attributes): the critic of an agent after it learned from a participant's session (replay critics,
`human_agents.replay_into_agent` in fast mode), or a synthetic critic with known weights. A *design* is a set of pairs (left, right) of
attribute points: `sample_design` draws one with the number of trials, the share of them that repeat an earlier pair (sides swapped), and the
range of the pairs' similarity (a feature gap, `interlude.feature_gap`, or a true reward gap), spread evenly over that range. The target
*chooses* by a softmax on its value difference, P(right) = sigmoid((f(right) - f(left)) / (tau * spread of f over the world's bushes)), and a
*basis* is fitted to those choices as a preference model, P(right) = sigmoid(w . (phi(right) - phi(left))), with a ridge penalty chosen by
cross-validated choice log-likelihood (the experimenter cannot tune it on the truth). The fitted function f^(x) = w . phi(x) is defined up to
scale and offset (comparisons carry neither), so it is scored after that is allowed for:

    pearson, spearman   f^ against f over the world's bushes
    pair                held-out pairs of those bushes ordered the same way by f^ and f (weighted by the size of f's gap)
    cos, wrmse, signs   the least-squares attribute weights of f^ against those of f (each normalised): cosine, root mean square error per
                        attribute, and the attributes of at least 20% of the largest weight whose sign is wrong
    cv_ll               held-out choice log-likelihood per trial against the target's own choice probabilities (what the fit could reach)

The sampler is in attribute space with no terrain (moisture is free), so it maps the landscape quickly; a design the real generator can build
(`interlude.generate_interlude`, which also enforces the terrain rules) is confirmed afterwards.

    ./venv/bin/python scripts/interlude_design.py timing
"""

import argparse
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import rankdata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents  # noqa: E402
import agent_inference as ai  # noqa: E402
import human_agents  # noqa: E402
import interlude  # noqa: E402
import replay  # noqa: E402
import world as worldmod  # noqa: E402
from idle_analysis import finished_runs  # noqa: E402

REFERENCE_BUSHES = 400          # world bushes a fitted function is scored on
POOL_PAIRS = 4000               # random pairs a design is chosen from
RIDGES = (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0)
FOLDS = 5
SMALL_WEIGHT = 0.2              # an attribute counts for the sign check when its weight is at least this share of the largest


# --------------------------------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------------------------------

class Target:
    """A learned value function `f(attrs (n, 3)) -> (n,)` with the session whose bushes and reward function define its reference set and
    its true reward gaps."""

    def __init__(self, name, session, f, reward_function, reference):
        self.name, self.session, self.f, self.reward_function, self.reference = name, session, f, reward_function, reference
        self.spread = max(float(np.std(f(reference))), 1e-9)
        u = np.random.default_rng(7).random((4000, 3))
        self.reward_scale = max(float(np.std(worldmod.bush_value(reward_function, u[:, 0], u[:, 1], u[:, 2]))), 1e-9)   # the spread of the true reward over random bushes


def _reference(world, rng):
    attrs = np.column_stack([world.shape, world.color, world.moisture])
    return attrs[rng.choice(len(attrs), size=min(REFERENCE_BUSHES, len(attrs)), replace=False)]


def replay_targets(agent_name="replay_len0_5", sessions=("S1", "S2", "S3", "S4", "S5")):
    """The critic of `agent_name` after it learned from each finished participant's session (fast replay): one target per participant and session."""
    index = {f"S{i}": f"{2 * i:02d}" for i in range(1, 6)}
    out, rng = [], np.random.default_rng(0)
    for who, run in finished_runs().items():
        for name in sessions:
            log = replay.load_session_log(replay.DATA_DIR / run / index[name])
            world = human_agents.session_world(log)
            agent = human_agents.replay_into_agent(agents.REGISTRY[agent_name](), log, world=world, fast=True).agent
            out.append(Target(f"{who}/{name}", name, lambda X, c=agent.critic: np.asarray(c.value(X, None)[0], dtype=float),
                              world.params.reward_function, _reference(world, rng)))
    return out


SYNTHETIC = {"one": (3.0, 0.0, 0.0), "two": (3.0, 3.0, 0.0), "small": (3.0, 1.5, 0.3), "mixed": (3.0, -2.0, 1.0)}


def synthetic_targets(session="S3"):
    """Linear critics with known weights on `session`'s bushes: one dominant attribute, two equal, one small, mixed signs; and a peaked one
    (a Gaussian on shape) that a linear basis cannot represent."""
    world = worldmod.make_world(session, worldmod.load_session(session).world_seed)
    rng = np.random.default_rng(1)
    ref, rf = _reference(world, rng), world.params.reward_function
    out = [Target(f"linear-{k}", session, lambda X, w=np.array(w): np.asarray(X, dtype=float) @ w, rf, ref) for k, w in SYNTHETIC.items()]
    out.append(Target("peak-shape", session, lambda X: 4.0 * np.exp(-((np.asarray(X, dtype=float)[:, 0] - 0.5) ** 2) / (2 * 0.15 ** 2)), rf, ref))
    return out


# --------------------------------------------------------------------------------------------------
# Designs
# --------------------------------------------------------------------------------------------------

def sample_design(target, n_trials, repeat_share, axis, low, high, rng):
    """(left (n, 3), right (n, 3), pair id (n,)) of `n_trials` trials: round(n_trials x (1 - repeat_share)) distinct pairs whose gap on `axis`
    ("feature": `interlude.feature_gap`; "reward": the target session's true reward, with low and high in units of its spread over random bushes, as the
    generator's graded trials are) is spread evenly over [low, high] (the generator's own
    `choose_gap_trials`, here on uniform random pairs), the rest repeats of earlier pairs with the sides swapped, in a random order."""
    n_unique = max(1, n_trials - int(round(n_trials * repeat_share)))
    a, b = rng.random((POOL_PAIRS, 3)), rng.random((POOL_PAIRS, 3))
    value = lambda x: worldmod.bush_value(target.reward_function, x[:, 0], x[:, 1], x[:, 2])
    rgap = np.abs(value(a) - value(b))
    fgap = np.sqrt(((a - b) ** 2).mean(axis=1))
    rows = [(i, a[i], b[i], rgap[i], fgap[i], bool(value(a)[i] > value(b)[i])) for i in range(POOL_PAIRS)]
    col = {"reward": 3, "feature": 4}[axis]
    if axis == "reward":
        low, high = low * target.reward_scale, high * target.reward_scale
    keep = [r for r in rows if low <= r[col] <= high]
    chosen, _ = interlude.choose_gap_trials(keep, n_unique, (col,), {col: low}, rng)
    left = np.array([r[1] for r in chosen])
    right = np.array([r[2] for r in chosen])
    ids = np.arange(n_unique)
    extra = rng.integers(n_unique, size=n_trials - n_unique)
    left, right = np.vstack([left, right[extra]]), np.vstack([right, left[extra]])     # a repeat shows the pair with the sides swapped
    ids = np.concatenate([ids, extra])
    order = rng.permutation(n_trials)
    return left[order], right[order], ids[order]


def simulate_choices(target, left, right, tau, rng):
    """Picks (1 = right) of the target on the trials: a softmax on its value difference over tau times the spread of its values."""
    return (rng.random(len(left)) < expit((target.f(right) - target.f(left)) / (tau * target.spread))).astype(float), \
        expit((target.f(right) - target.f(left)) / (tau * target.spread))


# --------------------------------------------------------------------------------------------------
# Bases and the preference fit
# --------------------------------------------------------------------------------------------------

def _linear(X):
    return np.asarray(X, dtype=float) - 0.5


def _quadratic(X):
    c = np.asarray(X, dtype=float) - 0.5
    return np.hstack([c, c ** 2])


def _rbf(length_scale, n_centers=8):
    return agents.RBFFeatures(length_scale=length_scale, n_centers=n_centers)


BASES = {"linear": _linear, "quadratic": _quadratic, "rbf0.5": _rbf(0.5), "rbf0.3": _rbf(0.3)}


def fit_preference(D, y, ridge, iters=40):
    """Ridge logistic regression of the picks `y` (1 = right) on the feature differences `D` (right minus left), no intercept, by Newton."""
    w = np.zeros(D.shape[1])
    for _ in range(iters):
        p = expit(D @ w)
        grad = D.T @ (y - p) - ridge * w
        hess = (D * (p * (1 - p))[:, None]).T @ D + ridge * np.eye(D.shape[1])
        step = np.linalg.solve(hess, grad)
        w = w + np.clip(step, -5, 5)
        if np.abs(step).max() < 1e-7:
            break
    return w


def loglik(D, y, w):
    p = np.clip(expit(D @ w), 1e-9, 1 - 1e-9)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_cv(D, y, ids, rng, ridges=RIDGES, folds=FOLDS):
    """(w, chosen ridge): the ridge with the best held-out choice log-likelihood over `folds` folds that keep a repeated pair in one fold."""
    pairs = np.unique(ids)
    fold_of = dict(zip(rng.permutation(pairs), np.arange(len(pairs)) % folds))
    fold = np.array([fold_of[i] for i in ids])
    scores = []
    for r in ridges:
        s = 0.0
        for k in range(folds):
            test = fold == k
            if test.any() and (~test).any():
                s += loglik(D[test], y[test], fit_preference(D[~test], y[~test], r))
        scores.append(s)
    best = ridges[int(np.argmax(scores))]
    return fit_preference(D, y, best), best


# --------------------------------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------------------------------

def _unit(w):
    n = np.linalg.norm(w)
    return w / n if n > 1e-12 else w


def score(target, fhat, rng, n_pairs=2000):
    """Pearson and Spearman correlation of the fitted function with the target over the reference bushes, the gap-weighted share of random
    pairs of those bushes they order alike, and the cosine, normalised RMSE and sign errors of their least-squares attribute weights."""
    X, f = target.reference, target.f(target.reference)
    g = fhat(X)
    pearson = float(np.corrcoef(f, g)[0, 1]) if np.std(g) > 1e-12 else 0.0
    spearman = float(np.corrcoef(rankdata(f), rankdata(g))[0, 1]) if np.std(g) > 1e-12 else 0.0
    i, j = rng.integers(len(X), size=(2, n_pairs))
    wgt = np.abs(f[i] - f[j])
    pair = float(np.sum(wgt * (np.sign(f[i] - f[j]) == np.sign(g[i] - g[j]))) / max(np.sum(wgt), 1e-12))
    w_true, w_fit = ai.least_squares_weights(X, f), ai.least_squares_weights(X, g)
    cos = float(_unit(w_true) @ _unit(w_fit)) if np.linalg.norm(w_fit) > 1e-12 else 0.0
    wrmse = float(np.sqrt(np.mean((_unit(w_true) - _unit(w_fit)) ** 2)))
    big = np.abs(w_true) >= SMALL_WEIGHT * np.abs(w_true).max()
    signs = int(np.sum(big & (np.sign(w_true) != np.sign(w_fit))))
    return {"pearson": pearson, "spearman": spearman, "pair": pair, "cos": cos, "wrmse": wrmse, "signs": signs}


# --------------------------------------------------------------------------------------------------
# One cell of a sweep
# --------------------------------------------------------------------------------------------------

_DESIGNS = {}


def design_for(target, n_trials, repeat_share, axis, low, high, seed):
    """The design of this configuration and seed, drawn once and shared by every basis and target that needs it (a feature-gap design does
    not depend on the target; a reward-gap one on its session's reward function)."""
    key = (target.session if axis == "reward" else None, n_trials, repeat_share, axis, low, high, seed)
    if key not in _DESIGNS:
        _DESIGNS[key] = sample_design(target, n_trials, repeat_share, axis, low, high, np.random.default_rng([seed, zlib.crc32(repr(key).encode())]))
    return _DESIGNS[key]


def run_cell(targets, basis, tau=0.25, n_trials=20, repeat_share=0.0, axis="feature", low=0.1, high=0.6, seeds=10, seed0=0):
    """One row per target and seed: a design is drawn, the target chooses on it, the basis is fitted (ridge by cross-validation) and scored."""
    phi, rows = BASES[basis], []
    for t in targets:
        for s in range(seeds):
            left, right, ids = design_for(t, n_trials, repeat_share, axis, low, high, seed0 + s)
            rng = np.random.default_rng([seed0, s, zlib.crc32(t.name.encode())])
            y, p_true = simulate_choices(t, left, right, tau, rng)
            D = phi(right) - phi(left)
            w, ridge = fit_cv(D, y, ids, rng)
            row = score(t, lambda X, w=w: phi(X) @ w, rng)
            row.update(target=t.name, session=t.session, seed=s, ridge=ridge, accuracy=float(np.mean((p_true > 0.5) == (y > 0.5))))
            rows.append(row)
    return pd.DataFrame(rows)


METRICS = ["pearson", "spearman", "pair", "cos", "wrmse", "signs"]


def summarize(frame):
    return frame[METRICS].mean().round(3).to_dict() | {"pearson p10": round(float(frame["pearson"].quantile(0.1)), 3)}


def timing_main(args):
    """A few cells to see how long they take and whether the numbers are sensible."""
    t0 = time.time()
    targets = replay_targets() + synthetic_targets()
    print(f"{len(targets)} targets built in {time.time() - t0:.1f} s")
    t0 = time.time()
    left, right, ids = sample_design(targets[0], 20, 0.0, "feature", 0.1, 0.6, np.random.default_rng(0))
    print(f"one design (20 trials, feature gap 0.1-0.6) in {time.time() - t0:.2f} s; feature gaps "
          f"{np.round(np.sort(np.sqrt(((left - right) ** 2).mean(axis=1))), 2)}")
    for basis in BASES:
        t0 = time.time()
        frame = run_cell(targets, basis, seeds=args.seeds)
        print(f"{basis:10s} {len(frame)} fits in {time.time() - t0:5.1f} s ({1000 * (time.time() - t0) / len(frame):.0f} ms each): {summarize(frame)}")
    t0 = time.time()
    sidecar = interlude.generate_interlude("S3_Interlude", mode="hybrid")[0]
    print(f"real generator, S3 hybrid mode: {time.time() - t0:.1f} s ({sidecar['n']} trials)")


def range_main(args):
    """Sweep C/D: the range of the pairs' similarity (low and high of the gap, evenly spread between them) on the feature-gap or reward-gap axis,
    at one basis, trial count, tau and repeat share; saved to results/interlude_design_range_<axis>.csv."""
    t0 = time.time()
    targets = replay_targets() + synthetic_targets()
    lows = [float(v) for v in args.lows.split(",")]
    highs = [float(v) for v in args.highs.split(",")]
    frames = []
    for low in lows:
        for high in highs:
            if high <= low:
                continue
            frame = run_cell(targets, args.basis, tau=args.tau, n_trials=args.n, repeat_share=args.share, axis=args.axis, low=low, high=high, seeds=args.seeds)
            frames.append(frame.assign(low=low, high=high))
            print(f"{args.axis} gap {low:g}-{high:g} {time.time() - t0:6.1f} s  {summarize(frame)}", flush=True)
    out = pd.concat(frames)
    out.to_csv(replay.PROJECT_ROOT / "results" / f"interlude_design_range_{args.axis}.csv", index=False)
    out["kind"] = np.where(out["target"].str.contains("/"), "replay " + out["session"], np.where(out["target"] == "peak-shape", "synthetic peak", "synthetic linear"))
    print(f"\n{len(out)} rows, {time.time() - t0:.1f} s in all")
    for metric in ("pearson", "wrmse", "signs"):
        print(f"\n{metric}: rows low, columns high")
        print(out.pivot_table(index="low", columns="high", values=metric).round(3).to_string())
    print("\npearson by target kind: rows kind and low, columns high")
    print(out.pivot_table(index=["kind", "low"], columns="high", values="pearson").round(2).to_string())


def trials_main(args):
    """Sweep A: the number of trials (all new pairs) against the basis, at one tau; the frame is saved to results/interlude_design_trials.csv."""
    t0 = time.time()
    targets = replay_targets() + synthetic_targets()
    frames = []
    for n in (int(v) for v in args.trials.split(",")):
        for basis in BASES:
            frame = run_cell(targets, basis, tau=args.tau, n_trials=n, seeds=args.seeds)
            frames.append(frame.assign(n_trials=n, basis=basis, tau=args.tau))
            print(f"N={n:2d} {basis:9s} {time.time() - t0:6.1f} s  {summarize(frame)}", flush=True)
    out = pd.concat(frames)
    path = replay.PROJECT_ROOT / "results" / "interlude_design_trials.csv"
    out.to_csv(path, index=False)
    out["kind"] = np.where(out["target"].str.contains("/"), "replay " + out["session"], "synthetic")
    print(f"\nsaved {len(out)} rows to {path}; {time.time() - t0:.1f} s in all")
    for metric in ("pearson", "wrmse", "signs"):
        print(f"\n{metric} (mean over targets and seeds)")
        print(out.pivot_table(index="basis", columns="n_trials", values=metric).round(3).to_string())
    print("\npearson by target kind")
    print(out.pivot_table(index=["kind", "basis"], columns="n_trials", values="pearson").round(2).to_string())


def repeats_main(args):
    """Sweep B with tau: the share of the trials that repeat an earlier pair against the softmax tau, at one basis and trial count; saved to
    results/interlude_design_repeats.csv."""
    t0 = time.time()
    targets = replay_targets() + synthetic_targets()
    frames = []
    for tau in (float(v) for v in args.taus.split(",")):
        for share in (float(v) for v in args.shares.split(",")):
            frame = run_cell(targets, args.basis, tau=tau, n_trials=args.n, repeat_share=share, seeds=args.seeds)
            frames.append(frame.assign(tau=tau, repeat_share=share, basis=args.basis, n_trials=args.n))
            print(f"tau={tau:<5g} repeats={share:.0%} {time.time() - t0:6.1f} s  {summarize(frame)}", flush=True)
    out = pd.concat(frames)
    out.to_csv(replay.PROJECT_ROOT / "results" / "interlude_design_repeats.csv", index=False)
    out["kind"] = np.where(out["target"].str.contains("/"), "replay " + out["session"], np.where(out["target"] == "peak-shape", "synthetic peak", "synthetic linear"))
    print(f"\n{len(out)} rows, {time.time() - t0:.1f} s in all")
    for metric in ("pearson", "wrmse", "signs"):
        print(f"\n{metric}: rows tau, columns repeated share")
        print(out.pivot_table(index="tau", columns="repeat_share", values=metric).round(3).to_string())
    print("\npearson at each tau by target kind: columns repeated share")
    print(out.pivot_table(index=["kind", "tau"], columns="repeat_share", values="pearson").round(2).to_string())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("timing", "trials", "repeats", "range"))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--trials", default="10,20,30,40")
    ap.add_argument("--tau", type=float, default=0.25)
    ap.add_argument("--taus", default="0.1,0.25,0.5,1.0")
    ap.add_argument("--shares", default="0,0.1,0.3,0.5")
    ap.add_argument("--basis", default="rbf0.3")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--share", type=float, default=0.1)
    ap.add_argument("--axis", choices=("feature", "reward"), default="feature")
    ap.add_argument("--lows", default="0.05,0.1,0.2,0.3")
    ap.add_argument("--highs", default="0.3,0.5,0.7,0.9")
    args = ap.parse_args(argv)
    {"timing": timing_main, "trials": trials_main, "repeats": repeats_main, "range": range_main}[args.what](args)


if __name__ == "__main__":
    main()
