"""Power of candidate RW designs (`./venv/bin/python scripts/rw_power.py`; the one-factor and sparsity cases are in rw_power_extra.py)

Power of candidate RW designs to identify the effects of separation and height ratio on trapping (two features, two peaks), by simulation.
True effect: a logistic model fitted to the rw2 agents' trapped-by-180-s data; humans are given the agents' slopes times `m` (1 = as strong, 0.5 = half), a participant random intercept
(sd TAU on the logit scale), and each design's sessions. Analysis: pooled logistic regression with participant-clustered robust standard errors, Wald tests at alpha = 0.05."""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import rw_screen_analysis as A
rng = np.random.default_rng(1)

def irls(X, y, iters=60):
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30))); W = p * (1 - p) + 1e-9
        step = np.linalg.solve(X.T @ (X * W[:, None]) + 1e-8 * np.eye(X.shape[1]), X.T @ (y - p)); b += step
        if np.abs(step).max() < 1e-7: break
    return b

from scipy import stats
def robust(X, y, groups):
    """Linear-probability model with participant-clustered (CR1) standard errors; returns coefficients and two-sided p-values from t with G-1 degrees of freedom."""
    XtX_inv = np.linalg.inv(X.T @ X); b = XtX_inv @ X.T @ y; r = (y - X @ b)[:, None] * X
    G = groups.max() + 1; sums = np.zeros((G, X.shape[1])); np.add.at(sums, groups, r)
    n, k = X.shape; V = XtX_inv @ (sums.T @ sums) @ XtX_inv * (G / (G - 1)) * ((n - 1) / (n - k))
    se = np.sqrt(np.maximum(np.diag(V), 1e-300)); return b, 2 * stats.t.sf(np.abs(b / se), G - 1)

# --- the true model, from the agents
e = A.load("rw2"); g = e[(e.dims == 2) & (e.n_peaks == 2) & (e.agent != "nearest")].copy()
g["y"] = ((g["first30_local"] <= 180) & ~(g["first30_global"] <= 180)).astype(float)
s0, r0 = 4.0, 0.6                                      # centre of the box sep 3..5, ratio 0.4..0.8
X = np.column_stack([np.ones(len(g)), g.separation - s0, g.ratio - r0, (g.separation - s0) * (g.ratio - r0)])
B = irls(X, g.y.to_numpy())
def eta(sep, ratio, m): return B[0] + m * (B[1] * (sep - s0) + B[2] * (ratio - r0) + B[3] * (sep - s0) * (ratio - r0))
print("true model (agents), trapped at 180 s:  (sep, ratio) -> p")
for s in (3, 5):
    print("  ", {r: round(float(1 / (1 + np.exp(-eta(s, r, 1)))), 3) for r in (0.4, 0.8)})
print("interaction coefficient", round(float(B[3]), 2), " (sep slope", round(float(B[1]), 2), "ratio slope", round(float(B[2]), 2), "per unit)")

# --- designs: each participant's four (separation, ratio) sessions
def d_2x2(N): return np.tile([(3, .4), (3, .8), (5, .4), (5, .8)], (N, 1, 1))
def d_sep(N): return np.tile([(s, .8) for s in (3, 3 + 2 / 3, 3 + 4 / 3, 5)], (N, 1, 1))
def d_ratio(N): return np.tile([(5, r) for r in (.4, .4 + .4 / 3, .4 + .8 / 3, .8)], (N, 1, 1))
def d_diag(N): return np.tile([(3 + 2 * t, .4 + .4 * t) for t in (0, 1 / 3, 2 / 3, 1)], (N, 1, 1))
def d_cont(N):                                         # each session a random point of the box: a Latin hypercube over all participants' sessions, dealt to participants at random
    n = 4 * N; u = np.column_stack([rng.permutation(n), rng.permutation(n)]) + rng.random((n, 2)); u /= n
    pts = np.column_stack([3 + 2 * u[:, 0], .4 + .4 * u[:, 1]]); return pts.reshape(N, 4, 2)[rng.permutation(N)]
DESIGNS = {"2x2 (sep 3/5 x ratio .4/.8)": d_2x2, "separation only, 4 levels (ratio .8)": d_sep, "ratio only, 4 levels (sep 5)": d_ratio,
           "one diagonal axis, 4 levels": d_diag, "continuous box (random draws)": d_cont}
def power(design, N, m, tau, reps, iterations=1):
    hits = {"sep": 0, "ratio": 0, "inter": 0, "axis": 0}
    for _ in range(reps):
        pts = design(N)
        if iterations > 1: pts = np.concatenate([pts] * iterations, axis=1)
        sep, ratio = pts[..., 0], pts[..., 1]
        u = rng.normal(0, tau, N)[:, None]
        y = (rng.random(sep.shape) < 1 / (1 + np.exp(-(eta(sep, ratio, m) + u)))).astype(float)
        grp = np.repeat(np.arange(N), sep.shape[1]); sf, rf, yf = sep.ravel() - s0, ratio.ravel() - r0, y.ravel()
        try:
            if design in (d_2x2, d_cont):
                b, pv = robust(np.column_stack([np.ones(len(yf)), sf, rf, sf * rf]), yf, grp)
                hits["sep"] += pv[1] < .05; hits["ratio"] += pv[2] < .05; hits["inter"] += pv[3] < .05
            elif design is d_sep:
                b, pv = robust(np.column_stack([np.ones(len(yf)), sf]), yf, grp); hits["sep"] += pv[1] < .05
            elif design is d_ratio:
                b, pv = robust(np.column_stack([np.ones(len(yf)), rf]), yf, grp); hits["ratio"] += pv[1] < .05
            else:
                b, pv = robust(np.column_stack([np.ones(len(yf)), sf]), yf, grp); hits["axis"] += pv[1] < .05
        except np.linalg.LinAlgError:
            pass
    return {k: v / reps for k, v in hits.items()}
reps = 400
if __name__ != '__main__':
    pass
def show(title, m, designs, Ns=(30, 60, 100, 200), iterations=1, tau=0.8):
    print(f"\n=== {title} ===")
    rows = []
    for name, design in designs.items():
        for N in Ns:
            p = power(design, N, m, tau, reps, iterations)
            keep = ("sep", "ratio", "inter") if design in (d_2x2, d_cont) else ("sep",) if design is d_sep else ("ratio",) if design is d_ratio else ("axis",)
            rows.append({"design": name, "N": N, **{k: round(p[k], 2) for k in keep}})
    print(pd.DataFrame(rows).fillna("").to_string(index=False))
if __name__ == '__main__':
    show("false-positive check: NO effect (all slopes 0) -- every entry should be near 0.05", 0.0, {"2x2": d_2x2, "continuous box": d_cont, "separation only": d_sep}, Ns=(30, 100))
    show("humans' slopes = 1.0 x the agents' (participant random intercept sd 0.8), one session per cell", 1.0, DESIGNS)
    show("humans' slopes = 0.5 x the agents'", 0.5, DESIGNS)
    show("2x2 with TWO iterations of each cell (8 sessions per participant), slopes 1.0 and 0.5", 1.0, {"2x2 x2 iterations, slopes 1.0": d_2x2}, iterations=2)
    show("", 0.5, {"2x2 x2 iterations, slopes 0.5": d_2x2}, iterations=2)
    