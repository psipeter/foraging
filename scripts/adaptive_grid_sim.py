"""Simulation: how should the 3x3 selection grid adapt? Three policies for placing a grid of nine bushes (axis-aligned, shape across and colour up) over the value map.

A grid is a centre and a spacing `s`: its nine cells are the centre plus -s, 0, +s along each axis (clamped inside the unit square). The spacing is held between
`s_max` (1/3: three cells that share the whole space evenly) and `s_min` (the smallest spacing at which, for a grid at the peak, the median value difference between
neighbouring cells is at least twice the tie gap). Policies:

    fixed      the grid at s_max in the middle of the map, every selection (no adaptation).
    staircase  the spacing follows the participant's performance (Kendall's tau of the selection against the true values): s <- s * exp(-k * (tau - target)), a stochastic-approximation
               staircase; the centre is a rank-weighted estimate of where the participant thinks the best cell is, plus a random offset of up to half a spacing.
    posterior  the spacing is the posterior spread of the participant's believed peak (k times, clamped); the centre is the posterior mean plus the same random offset. The posterior
               is over (believed peak, breadth, choice temperature) of a Gaussian subjective map under Plackett-Luce choice, updated after every selection with a forgetting factor
               (the belief changes as people learn). It uses nothing but the participant's selections: the true map never enters the placement.

Simulated participants hold a Gaussian subjective map (peak b, breadth w) and rank the cells by Plackett-Luce at temperature tau over its values; the belief moves toward the truth as
rho^t. Types: fast, slow, noisy (high tau), wrong (never learns, a fixed offset), sandbag (fast, but feigns ignorance for the first five selections), centre (ranks by distance from the
window's centre and knows nothing). Metrics: recovery (distance from the posterior-mean peak, computed from the selections of each policy, to the participant's actual belief), pay (the two-term
rule, 100 * (L + R) / 2 with L = true value of the top-ranked cell over the peak and R = (tau + 1) / 2), the scale against the belief error (how much the grid size tells a participant),
and the honest minus the sandbagger's pay.

    adaptive_grid_sim.py PSC_S1 PCX_S3 [--participants 100] [--selections 10] [--out file.png] [--txt file.txt]

Not an engine file; nothing here is read by the game.
"""

import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import kendalltau, pearsonr

import selection
from world import REWARDS, load_session, stage_names

DOCS = Path(__file__).resolve().parent.parent / "docs" / "pilots"
S_MAX = 1.0 / 3.0
MARGIN = 0.02
POLICIES = ("fixed", "staircase", "posterior")
TYPES = ("fast", "slow", "noisy", "wrong", "sandbag", "centre")
PEAKS = np.linspace(0.0, 1.0, 21)
WIDTHS = np.array([0.10, 0.15, 0.22, 0.33, 0.50])
TAUS = np.array([0.25, 0.5, 1.0, 2.0])
FORGET = 0.85                      # the weight of the old log posterior each selection
TARGET_TAU = 0.6                   # the staircase's target Kendall tau
STAIR_K = 1.2
OFFSET = 0.5                       # the random offset of a centre, in spacings
DX, DY = np.meshgrid([-1, 0, 1], [-1, 0, 1], indexing="ij")
OFFS = np.column_stack([DX.ravel(), DY.ravel()]).astype(float)        # cell offsets: x = shape, y = colour (row-major in x)


class World:
    """A session's true map, its peak and the grid limits."""

    def __init__(self, session):
        self.params = load_session(session)
        self.valuefn = REWARDS[stage_names(self.params)[2]]
        axis = np.linspace(0.0, 1.0, 201)
        field = np.asarray(self.valuefn(self.params.reward_function, axis[:, None], axis[None, :]), dtype=float)
        i, j = np.unravel_index(int(np.argmax(field)), field.shape)
        self.peak = np.array([axis[i], axis[j]])
        self.vmax = float(field[i, j])
        _, frame = selection.peak_and_frame(self.params)
        self.sigma = math.sqrt(frame[1] * frame[2])
        self.gap = float(self.params.selection_tie_gap)
        self.s_min = self.find_s_min()

    def value(self, points):
        p = np.asarray(points, dtype=float)
        return np.asarray(self.valuefn(self.params.reward_function, p[..., 0], p[..., 1]), dtype=float)

    def find_s_min(self):
        for s in np.arange(0.02, S_MAX, 0.005):
            cells = grid_cells(self.peak, s)
            v = self.value(cells).reshape(3, 3)
            diffs = np.concatenate([np.abs(np.diff(v, axis=0)).ravel(), np.abs(np.diff(v, axis=1)).ravel()])
            if np.median(diffs) >= 2.0 * self.gap:
                return float(s)
        return S_MAX


def grid_centre_clamp(centre, s):
    lo, hi = MARGIN + s, 1.0 - MARGIN - s
    return np.clip(centre, lo, hi)


def grid_cells(centre, s):
    return grid_centre_clamp(np.asarray(centre, dtype=float), s) + s * OFFS


# --------------------------------------------------------------------------------------------------
# Choice model, estimator
# --------------------------------------------------------------------------------------------------

def pl_loglik(u, order, tau):
    """log P(order | utilities u (..., n), temperature tau (broadcastable)): Plackett-Luce, `order` the cells from the first picked."""
    z = np.take_along_axis(u, np.broadcast_to(order, u.shape), axis=-1) / tau
    tail = np.logaddexp.accumulate(z[..., ::-1], axis=-1)[..., ::-1]
    return (z - tail).sum(axis=-1)


def sample_order(u, tau, rng):
    """A Plackett-Luce selection of the cells (Gumbel trick): indices from the first picked."""
    return np.argsort(-(u / tau + rng.gumbel(size=len(u))))


class Estimator:
    """A grid posterior over (believed peak, breadth, temperature) with forgetting."""

    def __init__(self, amp, power=1.0, forget=FORGET):
        px, py, w, t = np.meshgrid(PEAKS, PEAKS, WIDTHS, TAUS, indexing="ij")
        self.px, self.py, self.w, self.t = px.ravel(), py.ravel(), w.ravel(), t.ravel()
        self.amp, self.power, self.forget = amp, power, forget          # `power` < 1 tempers the likelihood: the posterior stays wider than one selection's evidence says
        self.logp = np.zeros(len(self.px))

    def update(self, cells, order):
        d2 = (cells[None, :, 0] - self.px[:, None]) ** 2 + (cells[None, :, 1] - self.py[:, None]) ** 2
        u = self.amp * np.exp(-d2 / (2.0 * self.w[:, None] ** 2))
        self.logp = self.forget * self.logp + self.power * pl_loglik(u, order, self.t[:, None])
        self.logp -= self.logp.max()

    def summary(self):
        p = np.exp(self.logp)
        p /= p.sum()
        mx, my = float((p * self.px).sum()), float((p * self.py).sum())
        var = float((p * ((self.px - mx) ** 2 + (self.py - my) ** 2)).sum())
        return np.array([mx, my]), math.sqrt(var / 2.0)           # the mean peak and its spread per axis


# --------------------------------------------------------------------------------------------------
# Participants
# --------------------------------------------------------------------------------------------------

class Participant:
    def __init__(self, kind, world, rng):
        self.kind, self.world, self.rng = kind, world, rng
        offset = rng.normal(0.0, 0.25, 2)
        self.b0 = np.clip(world.peak + offset, 0.0, 1.0)
        if kind == "wrong":
            ang = rng.uniform(0, 2 * math.pi)
            self.b0 = np.clip(world.peak + 0.3 * np.array([math.cos(ang), math.sin(ang)]), 0.0, 1.0)
        self.rho = {"fast": 0.55, "slow": 0.85, "noisy": 0.7, "wrong": 1.0, "sandbag": 0.55, "centre": 1.0}[kind]
        self.tau = {"noisy": 1.5}.get(kind, 0.5)
        self.w0, self.w_true = 0.4, world.sigma

    def belief(self, t):
        b = self.world.peak + (self.b0 - self.world.peak) * self.rho ** (t + 1)
        w = self.w_true + (self.w0 - self.w_true) * self.rho ** (t + 1)
        tau = self.tau
        if self.kind == "sandbag" and t < 5:                    # feigned ignorance: the first five selections are broad and noisy
            b, w, tau = self.b0, 0.45, 2.0
        return b, w, tau

    def rank(self, cells, centre, t):
        if self.kind == "centre":                               # knows nothing: ranks by distance from the middle of the grid
            u = -np.hypot(*(cells - centre).T) * 10.0
            return sample_order(u, 0.3, self.rng)
        b, w, tau = self.belief(t)
        u = self.world.vmax * np.exp(-((cells - b) ** 2).sum(axis=1) / (2.0 * w ** 2))
        return sample_order(u, tau, self.rng)


# --------------------------------------------------------------------------------------------------
# One participant under one policy
# --------------------------------------------------------------------------------------------------

def rank_weighted_centre(cells, order):
    w = np.exp(-np.arange(len(order)) / 1.5)
    return (cells[order] * w[:, None]).sum(axis=0) / w.sum()


def make_estimator(policy, vmax):
    """`posterior` uses the defaults; `posterior:<power>:<forget>` a tempered likelihood and its own forgetting factor."""
    if policy.startswith("posterior:"):
        _, power, forget = policy.split(":")
        return Estimator(vmax, float(power), float(forget))
    return Estimator(vmax)


def run(policy, kind, world, selections, rng):
    person = Participant(kind, world, rng)
    est = make_estimator(policy, world.vmax)
    s_min = world.s_min
    s, centre = S_MAX, np.array([0.5, 0.5])
    rows = []
    for t in range(selections):
        cells = grid_cells(centre, s)
        order = person.rank(cells, centre, t)
        values = world.value(cells)
        tau_k = kendalltau(values, -np.argsort(order))[0]                   # tau of the selection against the true values
        tau_k = 0.0 if np.isnan(tau_k) else float(tau_k)
        top = cells[order[0]]
        level = float(world.value(top) / world.vmax)
        pay = 100.0 * (level + (tau_k + 1.0) / 2.0) / 2.0
        est.update(cells, order)
        mean, sd = est.summary()
        belief = person.belief(t)[0] if kind != "centre" else centre
        span_lo, span_hi = grid_centre_clamp(centre, s) - s, grid_centre_clamp(centre, s) + s
        best_cell = int(np.argmax(values))
        rows.append({"t": t, "s": s, "err": float(np.hypot(*(mean - belief))), "pay": pay, "tau": tau_k, "level": level, "sd": sd,
                     "contains": float(np.all(world.peak >= span_lo - 1e-9) and np.all(world.peak <= span_hi + 1e-9)), "centre_best": float(best_cell == 4),
                     "drift": float(np.dot(centre - belief, world.peak - belief) / (np.hypot(*(world.peak - belief)) + 1e-9)),
                     "belief_err": float(np.hypot(*(belief - world.peak)))})
        if policy == "fixed":
            continue
        jitter = rng.uniform(-OFFSET, OFFSET, 2)
        if policy == "staircase":
            s = float(np.clip(s * math.exp(-STAIR_K * (tau_k - TARGET_TAU)), s_min, S_MAX))
            centre = rank_weighted_centre(cells, order) + jitter * s
        elif policy.startswith("truthdist"):                               # the spacing is K times how far the estimated belief is from the true peak (K from "truthdist:K")
            k = float(policy.split(":")[1]) if ":" in policy else 1.0
            s = float(np.clip(k * np.hypot(*(mean - world.peak)), s_min, S_MAX))
            centre = mean + jitter * s
        else:
            s = float(np.clip(sd, s_min, S_MAX))
            centre = mean + jitter * s
    return rows


def simulate(session, participants, selections, policies=POLICIES, seed=20261124):
    world = World(session)
    out = {"session": session, "s_min": world.s_min, "peak": world.peak, "sigma": world.sigma, "data": {}, "policies": tuple(policies)}
    for pi, policy in enumerate(policies):
        for ki, kind in enumerate(TYPES):
            rng = np.random.default_rng([seed, pi, ki])
            out["data"][(policy, kind)] = [run(policy, kind, world, selections, rng) for _ in range(participants)]
    return out


# --------------------------------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------------------------------

def collect(result, policy, kind, key):
    return np.array([[row[key] for row in run_] for run_ in result["data"][(policy, kind)]])


def summarize(result, selections):
    lines = [f"{result['session']}: s_max {S_MAX:.3f}, s_min {result['s_min']:.3f} (peak {np.round(result['peak'], 2).tolist()}, map spread {result['sigma']:.2f}); "
             f"{len(result['data'][('fixed', 'fast')])} participants of each type, {selections} selections", ""]
    learners = ("fast", "slow", "noisy")
    lines.append("recovery: distance from the estimated peak to the participant's actual belief, mean over fast, slow and noisy learners (feature units), at selection 3, 6, 10")
    for policy in result["policies"]:
        e = np.mean([collect(result, policy, k, "err").mean(axis=0) for k in learners], axis=0)
        lines.append(f"  {policy:14s} {e[2]:.3f} {e[5]:.3f} {e[selections - 1]:.3f}")
    lines.append("")
    lines.append("pay per selection (mean of 100*(L+R)/2) by participant type, over all selections")
    lines.append("  " + "policy".ljust(14) + "".join(f"{k:>9s}" for k in TYPES))
    for policy in result["policies"]:
        lines.append("  " + policy.ljust(14) + "".join(f"{collect(result, policy, k, 'pay').mean():9.1f}" for k in TYPES))
    lines.append("")
    lines.append("what the grid size tells a participant: correlation, across fast learners, of the mean spacing of selections 5-10 with how wrong their belief is (0 = nothing)")
    for policy in result["policies"][1:]:
        sc = collect(result, policy, "fast", "s")[:, 4:].mean(axis=1)
        be = collect(result, policy, "fast", "belief_err")[:, 4:].mean(axis=1)
        lines.append(f"  {policy:14s} r = {pearsonr(sc, be)[0]:+.2f}")
    lines.append("")
    lines.append("drift of the window centre toward the truth beyond the belief (mean projection, in spacings; 0 = none), fast learners")
    for policy in result["policies"][1:]:
        s = collect(result, policy, "fast", "s")[:, 1:]
        d = collect(result, policy, "fast", "drift")[:, 1:]
        lines.append(f"  {policy:14s} {np.mean(d / s):+.2f}")
    lines.append("")
    lines.append("what the grid shows: share of windows that contain the true peak, and share whose best cell is the middle one (fast learners, selections 3-10)")
    for policy in result["policies"]:
        lines.append(f"  {policy:14s} contains {collect(result, policy, 'fast', 'contains')[:, 2:].mean():.2f}   best cell is the middle {collect(result, policy, 'fast', 'centre_best')[:, 2:].mean():.2f}")
    lines.append("")
    lines.append("sandbagging: total pay over the selections, honest fast learner minus the one who feigns ignorance for five (positive = honesty pays)")
    for policy in result["policies"]:
        gain = collect(result, policy, "fast", "pay").sum(axis=1).mean() - collect(result, policy, "sandbag", "pay").sum(axis=1).mean()
        lines.append(f"  {policy:14s} {gain:+7.1f} points")
    lines.append("")
    lines.append("the ranker with no knowledge (centre) against the slow learner, mean pay per selection")
    for policy in result["policies"]:
        lines.append(f"  {policy:10s} centre {collect(result, policy, 'centre', 'pay').mean():5.1f}   slow {collect(result, policy, 'slow', 'pay').mean():5.1f}")
    return "\n".join(lines)


def figure(results, selections):
    fig, axes = plt.subplots(len(results), 4, figsize=(19, 4.2 * len(results)), layout="constrained", squeeze=False)
    palette = ["#777777", "#1f77b4", "#d95f02", "#2ca02c", "#9467bd", "#8c564b"]
    colours = {p: palette[i % len(palette)] for i, p in enumerate(results[0]["policies"])}
    x = np.arange(1, selections + 1)
    for r, result in enumerate(results):
        ax = axes[r, 0]
        for policy in result["policies"]:
            e = np.mean([collect(result, policy, k, "err").mean(axis=0) for k in ("fast", "slow", "noisy")], axis=0)
            ax.plot(x, e, "o-", color=colours[policy], label=policy)
        ax.set_title(f"{result['session']}: recovery of the belief", fontsize=10)
        ax.set_xlabel("selection")
        ax.set_ylabel("distance of estimated peak from belief")
        ax.legend(fontsize=8)
        ax = axes[r, 1]
        for policy in result["policies"]:
            for kind, ls in (("fast", "-"), ("slow", "--"), ("wrong", ":")):
                ax.plot(x, collect(result, policy, kind, "s").mean(axis=0), ls, color=colours[policy], label=f"{policy} {kind}" if policy != "fixed" else None)
        ax.axhline(result["s_min"], color="#999999", linewidth=0.6)
        ax.axhline(S_MAX, color="#999999", linewidth=0.6)
        ax.set_title("grid spacing (solid fast, dashed slow, dotted wrong)", fontsize=10)
        ax.set_xlabel("selection")
        ax = axes[r, 2]
        n_pol = len(result["policies"])
        width = 0.8 / n_pol
        for k, policy in enumerate(result["policies"]):
            ax.bar(np.arange(len(TYPES)) + (k - (n_pol - 1) / 2) * width, [collect(result, policy, t, "pay").mean() for t in TYPES], width, color=colours[policy], label=policy)
        ax.set_xticks(range(len(TYPES)), TYPES, fontsize=8)
        ax.set_title("mean pay per selection (points of 100)", fontsize=10)
        ax = axes[r, 3]
        for policy in result["policies"]:
            ax.plot(x, collect(result, policy, "fast", "pay").mean(axis=0), "o-", color=colours[policy], label=f"{policy} fast")
            ax.plot(x, collect(result, policy, "sandbag", "pay").mean(axis=0), "x--", color=colours[policy], label=f"{policy} sandbag")
        ax.set_title("pay over the session: honest fast and sandbagger", fontsize=10)
        ax.set_xlabel("selection")
        if r == 0:
            ax.legend(fontsize=7, ncol=2)
    fig.suptitle("Adaptive 3x3 grid: fixed, staircase and posterior-driven placement (simulated participants)")
    return fig


def main():
    ap = argparse.ArgumentParser(description="Simulation of adaptive 3x3 selection grids.")
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--policies", nargs="*", default=list(POLICIES), help="fixed, staircase, posterior, posterior:<power>:<forget>, truthdist:<K>")
    ap.add_argument("--participants", type=int, default=100)
    ap.add_argument("--selections", type=int, default=10)
    ap.add_argument("--out", default=str(DOCS / "adaptive_grid_sim.png"))
    ap.add_argument("--txt", default=None)
    args = ap.parse_args()
    results = [simulate(s, args.participants, args.selections, tuple(args.policies)) for s in args.sessions]
    report = "\n\n".join(summarize(r, args.selections) for r in results)
    print(report)
    if args.txt:
        Path(args.txt).write_text(report + "\n")
    fig = figure(results, args.selections)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=100)
    print(args.out)


if __name__ == "__main__":
    main()
