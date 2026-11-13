"""Calibration of the tiles world: is leaving a patch early the right policy, given the layout?

A forager that knows every bush's value (the learned critic of the experiment's late sessions: `OracleCritic`, the whole map in memory) can harvest the whole of a tile before it
walks to the next, or only its best few bushes. This script runs those policies in the real simulator (the engine charges the times the game does: turning, key presses, walking,
harvesting) on the worlds a layout makes, and asks which is best:

  top-k    in every tile it visits, harvest the k best bushes (by true value) and leave; the next tile is the one whose k best bushes pay the most per second. k = the bushes of a
           tile is "exhaust": harvest everything in a tile before leaving it.
  thr-q    in every tile it visits, harvest the bushes worth at least the q-th percentile of all the world's bush values and leave when none is left (the marginal-value rule with a fixed
           cut-off: it stays long in a rich tile and leaves a poor one at once, which top-k cannot do); the next tile is the one whose qualifying bushes pay the most per second.
  greedy   the standard rate actor (the best reward per second of walk plus harvest, within 15 s of walking, whole bush): it leaves a tile when its remaining bushes' rate falls below
           that of a bush elsewhere.
  plan     the beam-search planner's route (`PlannerActor`, whole-bush harvesting, no proof of optimality): what a good forager does, read off as how many bushes it takes in each tile
           it visits and whether they are the tile's good ones. It can fall below the simple policies (it does in worlds whose tiles differ a lot, at a width of 60): a warning says so.

The two things the layout must satisfy (PI, 2026-11-12): the spacing must not be so large that harvesting everything is always right, and a modest policy of harvesting a few of the
good bushes of a tile must be favoured. The verdict states both: the best partial policy (any top-k below exhaust, any thr-q) beats exhaust by at least `--margin` (paired over the same
worlds, with its standard error), and it takes a number of bushes per tile visit in the `--few` range. The planner, when asked for, is a reference only.

    ./venv/bin/python scripts/tile_calibration.py FOR_S1 --seeds 0-9
    ./venv/bin/python scripts/tile_calibration.py FOR_S1 --seeds 0-9 --sweep tile_radius=45,60,70,95 --set session_duration=180

--sweep NAME=v1,v2,... (snake_case session parameters; several give their grid), --set NAME=value (fixed overrides), --ks 1-9 (the k values; default every k up to the tile's bushes), --quantiles 10-90 (the thr-q percentiles, step 10; 0 = off),
--plan (also run the planner; slow, and in worlds whose tiles differ a lot its beam search can fall below the simple policies, which a warning says), --beam-width N, --few LO-HI, --margin FRACTION. It writes nothing. Not covered: what the learner does before it has learned (this is the policy once the
critic is learned), the view cone and terrain occlusion (the whole map is known), and the noise of a single fruit (bushes are harvested whole).
"""

import argparse
import itertools
import time

import numpy as np

import agents
import sim
import tiles
import world
from agents import Actor, ComposedAgent, FullKnowledge, Harvest, OracleCritic, PlannerAgent, rate_of

DEFAULT_FEW = (2, 5)           # the number of bushes per tile that counts as "a few"
DEFAULT_MARGIN = 0.03          # the best top-k must beat exhaust by this share of exhaust's score
DEFAULT_BEAM = 100
DEFAULT_QUANTILES = tuple(range(10, 100, 10))
CONFIDENCE = 2.0               # the paired gain over exhaust must exceed this many standard errors


class TileTopK(Actor):
    """Knows every bush's true value and its tile (`bind`). Visits the tiles one by one: in each it harvests the `k` best bushes by value, best rate first, and leaves; the next tile is the unvisited
    one whose k best bushes pay the most per second (their reward over the first walk, the harvesting and the moves between them). When every tile is visited it takes what is left, best rate first."""

    def __init__(self, k):
        self.k = int(k)

    def bind(self, tile_of):
        self.tile_of = np.asarray(tile_of, dtype=int)
        return self

    def begin(self, task, rng):
        super().begin(task, rng)
        self.tiles_left = set(np.unique(self.tile_of).tolist())
        self.chosen = np.zeros(len(self.tile_of), dtype=bool)

    def act(self, view):
        mean, _ = view.values()
        cand = view.candidates()
        rate = rate_of(view, mean)
        here = self.chosen & cand
        if here.any():                                           # still working in the tile
            return Harvest(int(np.argmax(np.where(here, rate, -np.inf))))
        self.chosen[:] = False
        t_first = view.travel_times()
        left = view.memory.fruits_left()
        speed, fd = self.task.speed, self.task.fruit_duration
        best, best_rate = None, -np.inf
        for t in sorted(self.tiles_left):
            members = np.flatnonzero((self.tile_of == t) & cand)
            if len(members) == 0:
                self.tiles_left.discard(t)
                continue
            top = members[np.argsort(-mean[members])[:self.k]]
            pos = view.memory.pos[top]
            gap = float(np.mean(np.hypot(*(pos[:, None, :] - pos[None, :, :]).transpose(2, 0, 1)))) / speed if len(top) > 1 else 0.0
            duration = float(t_first[top].min()) + float(left[top].sum()) * fd + (len(top) - 1) * gap
            r = float((mean[top] * left[top]).sum()) / duration
            if r > best_rate:
                best, best_rate = top, r
        if best is None:                                         # every tile has been visited: what is left, best rate first
            return Harvest(int(np.argmax(np.where(cand, rate, -np.inf)))) if cand.any() else None
        self.tiles_left.discard(int(self.tile_of[best[0]]))
        self.chosen[best] = True
        return Harvest(int(best[np.argmax(rate[best])]))


class TileThreshold(Actor):
    """Knows every bush's true value and its tile (`bind`). In each tile it visits it harvests the bushes worth at least `theta` per fruit (best rate first) and leaves when none is left; the next
    tile is the unvisited one whose qualifying bushes pay the most per second. When no tile has a qualifying bush it takes what is left, best rate first."""

    def __init__(self, theta):
        self.theta = float(theta)

    def bind(self, tile_of):
        self.tile_of = np.asarray(tile_of, dtype=int)
        return self

    def begin(self, task, rng):
        super().begin(task, rng)
        self.tiles_left = set(np.unique(self.tile_of).tolist())
        self.chosen = np.zeros(len(self.tile_of), dtype=bool)

    def act(self, view):
        mean, _ = view.values()
        cand = view.candidates()
        rate = rate_of(view, mean)
        here = self.chosen & cand
        if here.any():
            return Harvest(int(np.argmax(np.where(here, rate, -np.inf))))
        self.chosen[:] = False
        t_first = view.travel_times()
        left = view.memory.fruits_left()
        speed, fd = self.task.speed, self.task.fruit_duration
        best, best_rate = None, -np.inf
        for t in sorted(self.tiles_left):
            members = np.flatnonzero((self.tile_of == t) & cand)
            if len(members) == 0:
                self.tiles_left.discard(t)
                continue
            top = members[mean[members] >= self.theta]
            if len(top) == 0:
                continue
            pos = view.memory.pos[top]
            gap = float(np.mean(np.hypot(*(pos[:, None, :] - pos[None, :, :]).transpose(2, 0, 1)))) / speed if len(top) > 1 else 0.0
            duration = float(t_first[top].min()) + float(left[top].sum()) * fd + (len(top) - 1) * gap
            r = float((mean[top] * left[top]).sum()) / duration
            if r > best_rate:
                best, best_rate = top, r
        if best is None:
            return Harvest(int(np.argmax(np.where(cand, rate, -np.inf)))) if cand.any() else None
        self.tiles_left.discard(int(self.tile_of[best[0]]))
        self.chosen[best] = True
        return Harvest(int(best[np.argmax(rate[best])]))


def tile_of_world(w):
    """(tile number per bush, bushes per tile) of a tiles world."""
    ts = tiles.TileSet(w.terrain.tiles, w.pos)
    return ts.tile_of, np.bincount(ts.tile_of)


def oracle(actor):
    return ComposedAgent(actor, OracleCritic(), FullKnowledge())


def route_stats(result, tile_of, value):
    """What a run did tile by tile: the runs of consecutive harvests in one tile (a visit), their length, how many tiles it visited, the share of a visited tile's bushes it took, and the share of
    the bushes it took that are in the top half (by value) of their tile."""
    bushes = [int(b) for b, fruits, _ in result.trace if fruits > 0]
    if not bushes:
        return {"bushes": 0, "visits": 0, "tiles": 0, "per_visit": 0.0, "tile_share": 0.0, "top_half": 0.0, "walk_share": 0.0}
    sizes = np.bincount(tile_of)
    runs = [(t, len(list(g))) for t, g in itertools.groupby(tile_of[bushes])]
    visited = {t for t, _ in runs}
    top_half = []
    for b in bushes:
        members = np.flatnonzero(tile_of == tile_of[b])
        top_half.append(float((value[b] >= np.median(value[members])) if len(members) > 1 else True))
    taken = sum(n for _, n in runs)
    return {"bushes": len(bushes), "visits": len(runs), "tiles": len(visited), "per_visit": taken / len(runs),
            "tile_share": taken / sum(int(sizes[t]) for t in visited), "top_half": float(np.mean(top_half)),
            "walk_share": result.walk_time / max(result.walk_time + result.harvest_time + result.look_time + result.press_time, 1e-9)}


def calibrate_world(w, ks, quantiles=DEFAULT_QUANTILES, plan=False, beam_width=DEFAULT_BEAM):
    """{policy name: (total, route_stats)} for one world: top-k for each k, thr-q for each percentile q, greedy and (optionally) the planner."""
    tile_of, sizes = tile_of_world(w)
    out = {}
    for k in ks:
        r = sim.run_episode(oracle(TileTopK(k).bind(tile_of)), w)
        out[f"top-{k}"] = (r.total, route_stats(r, tile_of, w.value))
    for q in quantiles:
        r = sim.run_episode(oracle(TileThreshold(np.percentile(w.value, q)).bind(tile_of)), w)
        out[f"thr-{q}"] = (r.total, route_stats(r, tile_of, w.value))
    r = sim.run_episode(agents.GreedyAgent(whole_map=True), w)
    out["greedy"] = (r.total, route_stats(r, tile_of, w.value))
    if plan:
        r = sim.run_episode(PlannerAgent("beam", beam_width=beam_width), w)
        out["plan"] = (r.total, route_stats(r, tile_of, w.value))
    return out


def verdict(totals, ks, per_visit, few=DEFAULT_FEW, margin=DEFAULT_MARGIN, confidence=CONFIDENCE):
    """The two conditions on a layout, from `totals` {policy: per-seed totals} (the same worlds) and `per_visit` {policy: bushes taken per tile visit}. Exhaust is the top-k of the largest k. The best
    partial policy is the best mean among every other top-k and every thr-q. Returns (its name, its gain over exhaust as a share of exhaust, the gain's standard error, leaving_favoured,
    few_good, text): leaving is favoured when the gain is at least `margin` and `confidence` standard errors; few-good when, besides, it takes a number of bushes per visit in the `few` range."""
    exhaust_name = f"top-{max(ks)}"
    exhaust = np.asarray(totals[exhaust_name], dtype=float)
    partial = [n for n in totals if (n.startswith("top-") and n != exhaust_name) or n.startswith("thr-")]
    best = max(partial, key=lambda n: float(np.mean(totals[n])))
    diff = (np.asarray(totals[best], dtype=float) - exhaust) / max(float(exhaust.mean()), 1e-9)
    gain = float(diff.mean())
    se = float(diff.std(ddof=1) / np.sqrt(len(diff))) if len(diff) > 1 else float("nan")
    favoured = gain >= margin and (np.isnan(se) or gain >= confidence * se)
    n_bushes = per_visit[best]
    few_good = favoured and few[0] <= n_bushes <= few[1]
    detail = f"{best} takes {n_bushes:.1f} bushes per tile visit and beats exhaust by {gain:+.1%} +- {se:.1%}"
    if not favoured:
        text = (f"EXHAUST: no partial policy beats harvesting whole tiles ({detail}): the spacing is too large for leaving a tile early to pay, or the bushes of a tile do not decline enough within it "
                f"(best first) against the rest of the world")
    elif few_good:
        text = f"FEW GOOD: {detail}"
    elif n_bushes < few[0]:
        text = f"TOO EAGER: {detail}: travel is too cheap or the tiles too uneven for a few"
    else:
        text = f"TOO MANY: {detail}: leaving pays, but only after more than {few[1]} bushes per tile visit"
    return best, gain, se, favoured, few_good, text


def run_setting(session, seeds, overrides, ks=None, quantiles=DEFAULT_QUANTILES, plan=False, beam_width=DEFAULT_BEAM, few=DEFAULT_FEW, margin=DEFAULT_MARGIN, out=print):
    """Calibrate one layout (session + overrides) over `seeds`; prints a block and returns its numbers as a dict."""
    worlds = sim.get_worlds(session, seeds, **overrides)
    bushes_per_tile = int(worlds[0].params.tile_bushes)
    ks = list(ks) if ks else list(range(1, bushes_per_tile + 1))
    rows = [calibrate_world(w, ks, quantiles, plan, beam_width) for w in worlds]
    names = list(rows[0])
    totals = {n: np.array([r[n][0] for r in rows]) for n in names}
    stats = {n: {key: float(np.mean([r[n][1][key] for r in rows])) for key in rows[0][n][1]} for n in names}
    best, gain, se, favoured, few_good, text = verdict(totals, ks, {n: stats[n]["per_visit"] for n in names}, few, margin)
    p = worlds[0].params
    out(f"== {session} {' '.join(f'{k}={v}' for k, v in overrides.items())}   tiles {np.mean([tile_of_world(w)[1].size for w in worlds]):.0f}, bushes {np.mean([w.n for w in worlds]):.0f}, "
        f"{len(worlds)} seeds, {float(p.session_duration):.0f} s, tile radius {float(p.tile_radius):.0f}, cluster radius {float(p.tile_cluster_radius):.0f}")
    out(f"{'policy':<9}{'points':>8}{'se':>6}{'bushes':>8}{'visits':>8}{'tiles':>7}{'per visit':>10}{'walk':>7}{'top half':>10}")
    for n in names:
        s = stats[n]
        t = totals[n]
        mark = "  <- best partial" if n == best else ""
        out(f"{n:<9}{t.mean():>8.0f}{t.std(ddof=1) / np.sqrt(len(t)) if len(t) > 1 else float('nan'):>6.1f}{s['bushes']:>8.1f}{s['visits']:>8.1f}{s['tiles']:>7.1f}{s['per_visit']:>10.1f}{s['walk_share']:>7.0%}{s['top_half']:>10.0%}{mark}")
    if "plan" in stats:
        ex = totals[f"top-{max(ks)}"].mean()
        out(f"plan takes {stats['plan']['per_visit']:.1f} bushes per visit ({stats['plan']['tile_share']:.0%} of a visited tile's bushes), {stats['plan']['top_half']:.0%} of them in their tile's top half; "
            f"plan beats exhaust by {(totals['plan'].mean() - ex) / ex:+.1%}")
    out(text)
    if "plan" in totals:
        short = (max(totals[n].mean() for n in names if n != "plan") - totals["plan"].mean()) / max(totals["plan"].mean(), 1e-9)
        if short > 0.03:
            out(f"WARNING: the planner scores {short:.0%} below the best simple policy, so its beam search ({beam_width} wide) did not find the best route here: do not read its route as the optimum (widen --beam-width)")
    out("")
    return {"overrides": dict(overrides), "best": best, "gain": gain, "se": se, "favoured": favoured, "few_good": few_good, "totals": totals, "stats": stats}


def _range(text):
    lo, _, hi = text.partition("-")
    return int(lo), int(hi or lo)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Is leaving a tile early the right policy under a layout?")
    ap.add_argument("session")
    ap.add_argument("--seeds", default="0-9")
    ap.add_argument("--set", nargs="*", default=[], metavar="NAME=VALUE", help="session overrides (snake_case)")
    ap.add_argument("--sweep", nargs="*", default=[], metavar="NAME=V1,V2,...", help="session parameters to vary (the grid of all of them)")
    ap.add_argument("--ks", default=None, help="the k values, e.g. 1-9 (default every k up to the tile's bushes)")
    ap.add_argument("--quantiles", default="10-90", help="the thr-q percentiles, step 10 (e.g. 10-90; 0 = none)")
    ap.add_argument("--plan", action="store_true", help="also run the beam planner (slow)")
    ap.add_argument("--beam-width", type=int, default=DEFAULT_BEAM)
    ap.add_argument("--few", default=f"{DEFAULT_FEW[0]}-{DEFAULT_FEW[1]}", help="the range of bushes per tile that counts as a few")
    ap.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    args = ap.parse_args(argv)
    fixed = {k: sim._coerce(v) for k, v in (kv.split("=") for kv in args.set)}
    sweeps = [(k, [sim._coerce(x) for x in v.split(",")]) for k, v in (kv.split("=") for kv in args.sweep)]
    ks = range(_range(args.ks)[0], _range(args.ks)[1] + 1) if args.ks else None
    qlo, qhi = _range(args.quantiles)
    quantiles = tuple(range(max(qlo, 10), qhi + 1, 10)) if qhi > 0 else ()
    start = time.time()
    results = []
    for values in itertools.product(*[vs for _, vs in sweeps]):
        overrides = {**fixed, **{name: v for (name, _), v in zip(sweeps, values)}}
        results.append(run_setting(args.session, world._parse_seeds(args.seeds), overrides, ks, quantiles, args.plan, args.beam_width, _range(args.few), args.margin))
    if len(results) > 1:
        print("summary:")
        for r in results:
            label = " ".join(f"{k}={v}" for k, v in r["overrides"].items() if k in {n for n, _ in sweeps})
            print(f"  {label:<40} best {r['best']}  gain over exhaust {r['gain']:+.1%} +- {r['se']:.1%}  {'FEW GOOD' if r['few_good'] else 'leaving' if r['favoured'] else 'EXHAUST'}")
    print(f"({time.time() - start:.0f} s)")


if __name__ == "__main__":
    main()
