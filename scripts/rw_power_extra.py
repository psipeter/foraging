"""More power cases for the RW design: two-session designs that vary one factor only, and the sparsity hypothesis (H1). Uses the model and the tests of rw_power.py."""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import rw_power as P
rng = P.rng
# two-session designs that vary one factor only, the other held at the trap-friendly level
def two_sep(N): return np.tile([(3, .8), (5, .8)], (N, 1, 1))
def two_ratio(N): return np.tile([(5, .4), (5, .8)], (N, 1, 1))
def run(design, N, m, reps=400, tau=0.8):
    hits = 0
    for _ in range(reps):
        pts = design(N); sep, ratio = pts[..., 0], pts[..., 1]
        u = rng.normal(0, tau, N)[:, None]
        y = (rng.random(sep.shape) < 1 / (1 + np.exp(-(P.eta(sep, ratio, m) + u)))).astype(float)
        grp = np.repeat(np.arange(N), sep.shape[1])
        x = (sep.ravel() - sep.mean()) if design is two_sep else (ratio.ravel() - ratio.mean())
        b, pv = P.robust(np.column_stack([np.ones(len(x)), x]), y.ravel(), grp); hits += pv[1] < .05
    return hits / reps
print("=== TWO-session designs (one factor varied, the other fixed at the trap-friendly level); power of that factor ===")
for m in (1.0, 0.5):
    print(f"humans' slopes {m} x agents'")
    for name, d in (("separation 3 vs 5 at ratio .8", two_sep), ("ratio .4 vs .8 at separation 5", two_ratio)):
        print("  ", name, {N: run(d, N, m) for N in (30, 60, 100, 200)})
# H1: sparsity -> discovery, stage 1+2 series; person's discovery = 1 - exp(-m c t S30 / slowdown) at the session's effective time
print("\n=== H1: does sparsity (S30) change discovery? slope of discovery on log10 S30 across a participant's one-peak sessions ===")
sessions = [(1, .10, 120), (2, .07, 120), (1, .07, 120), (2, .05, 120)] + [(d, s, 180) for d in (1, 2) for s in (.03, .02, .01)]
C = {1: 0.355, 2: 0.5}
def h1(N, m, reps=400, tau=0.8):
    hits = 0
    for _ in range(reps):
        u = rng.normal(0, tau, N)[:, None]
        pr = np.array([1 - np.exp(-m * C[d] * (T / 1.5) * s) for d, s, T in sessions])[None, :]
        pr = np.clip(pr, 1e-4, 1 - 1e-4); lg = np.log(pr / (1 - pr)) + u
        y = (rng.random((N, len(sessions))) < 1 / (1 + np.exp(-lg))).astype(float)
        x = np.log10([s for d, s, T in sessions]); x = np.tile(x, (N, 1)); dm = np.tile([d for d, s, T in sessions], (N, 1))
        grp = np.repeat(np.arange(N), len(sessions))
        X = np.column_stack([np.ones(y.size), (x - x.mean()).ravel(), (dm.ravel() - 1.5)])
        b, pv = P.robust(X, y.ravel(), grp); hits += pv[1] < .05
    return hits / reps
for m in (1.0, 0.5, 0.25):
    print(f"human discovery rate scaled by {m}:", {N: h1(N, m) for N in (10, 20, 30, 60)})
