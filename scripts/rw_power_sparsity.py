"""Power of the v9 sparsity design (`./venv/bin/python scripts/rw_power_sparsity.py`): S and T at 15, 10 and 5% (3 iterations each), T's ratio and separation fixed.
True effects: the person proxy of screen rw5 (agents' strict discovery at length / k, k = 2 or 3; trapping in T), as logits per cell, the slope over sparsity times `m` (m = 1 as the
agents, 0.5 half as strong), plus a participant random intercept (sd TAU, logit). Analysis: linear probability, participant-clustered (CR1) t-tests at alpha 0.05, per participant 3 iterations
x 3 sparsities x 2 stages (+ B once, unused here). Outcomes: found the global peak (S and T), trapped (T)."""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import numpy as np
import rw_screen_analysis as A, rw_power
rng = np.random.default_rng(7)
robust = rw_power.robust
SPARS = np.array([15, 10, 5])
e = A.load("rw5"); e = e[e.agent.isin(("learner", "softmax", "curious"))]
def cell_p(cell, kind, k):
    c = e[e.id == cell]; t = float(c["length"].iloc[0]) / k
    glob = c["first10_global"] <= t
    return float(glob.mean()) if kind == "found" else float((~glob & (c["first10_local"] <= t)).mean())
logit = lambda p: np.log(p / (1 - p)); expit = lambda x: 1 / (1 + np.exp(-x))
def truth(kind, stage, k, m):
    p = np.array([cell_p(f"{stage}2F-{s}", kind, k) for s in SPARS]).clip(.02, .98); l = logit(p); mid = l.mean()
    return mid + m * (l - mid)                          # slope scaled around the mean level
def power(N, kind, k, m, tau, reps=1000, iters=3):
    lS, lT = truth(kind if kind == "found" else "found", "S", k, m), truth(kind, "T", k, m)
    stages = [("S", lS)] if kind == "trapped" and False else [("S", lS), ("T", lT)]
    hit = {"S slope": 0, "T slope": 0, "stage x slope": 0}
    for _ in range(reps):
        u = rng.normal(0, tau, N)[:, None]
        rows = []
        for si, (st, l) in enumerate(stages):
            s = np.tile(SPARS, (N, iters)); eta = np.tile(l, (N, iters)) + u
            y = (rng.random(s.shape) < expit(eta)).astype(float)
            rows.append((s, y, np.full(s.shape, si)))
        grp = np.repeat(np.arange(N), iters * 3)
        def test(sel, cols):
            s = np.concatenate([r[0].ravel() for r in rows]); y = np.concatenate([r[1].ravel() for r in rows]); st = np.concatenate([r[2].ravel() for r in rows]); g = np.tile(grp, len(rows))
            return s, y, st, g
        s, y, st, g = test(None, None); sc = (s - 10) / 5.0
        for name, m_ in (("S slope", st == 0), ("T slope", st == 1)):
            b, p = robust(np.column_stack([np.ones(m_.sum()), sc[m_]]), y[m_], g[m_]); hit[name] += p[1] < .05
        b, p = robust(np.column_stack([np.ones(len(y)), sc, st, sc * st]), y, g); hit["stage x slope"] += p[3] < .05
    return {k_: v / reps for k_, v in hit.items()}
if __name__ == "__main__":
    for kind in ("found", "trapped"):
        for k in (2, 3):
            for m in (1, .5):
                print(f"\n{kind}, person {k}x slower, effect x{m}: true p over 15/10/5 S", np.round(expit(truth('found', 'S', k, m)), 2), "T", np.round(expit(truth(kind, 'T', k, m)), 2))
                for tau in (.8,):
                    for N in (20, 40, 60, 100):
                        print(f"  N={N:3d}", power(N, kind, k, m, tau, reps=400))
