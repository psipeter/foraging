"""Plans for the plus ranking design: where the pluses go, how they are oriented and stretched, and what spread of values a set has (docs/DECISIONS.md, "plus ranking").

`ranking.plus_sets` (the first plan, "spiral" with free values) places the centres of each axes mode on a sunflower spiral and fits whatever results. This module holds the plans the
PI asked to play with; `ranking.plus_sets` hands over to `plus_sets` here when `rankingPlusPlan` or `rankingPlusDifficulty` is not the default. Not an engine file.

A **ranking** is `RANKING` = 3 consecutive sets (aligned, random, random). The settings:

Placement (`rankingPlusPlan`, where the centres go and how the random pluses turn and stretch):
  spiral  the baseline: per axes mode a sunflower spiral over the jitter ellipse; random turn and stretch.
  ring    each ranking is a triangle: its three centres 120 degrees apart on a ring around the peak, the ring's radius growing over the rankings (equal area) and its phase
          turning by the golden angle, the mode at each corner rotating; the two random pluses of a ranking turn 45 degrees apart (a plus repeats every 90) and the stretch
          ratio is stratified over the session, so all turns and ratios are visited evenly.
  tile    greedy space filling: sets are placed one at a time, each the best of `TILE_CANDIDATES` draws (centre in the jitter ellipse, turn and stretch for a random plus) by how
          much it lowers the mean distance from the rewarding region (value at least `REGION_FRACTION` of the peak) to its nearest bush.

Values (`rankingPlusDifficulty`):
  free    the arms keep whatever lengths the fit gives (the baseline).
  easy | medium | hard | <number>   a ladder: the five values of a set are `delta` apart (a fraction of the peak: easy 0.16, medium 0.10, hard 0.06, or the number), the centre's
          place in the ladder drawn at random among those the peak and the floor allow, and each arm's length is solved to hit its value (the arms are assigned to the
          ladder's levels as best fit). A random plus that cannot hit its levels along its axes turns (up to 45 degrees); an aligned one only stretches.
  mixed   easy, medium, hard in turn over the rankings.
"""

import itertools
import math

import numpy as np

import ranking
from ranking import GOLDEN_ANGLE, PLUS_MARGIN, PLUS_MIN_FRACTION, PLUS_ROLES, peak_and_frame
from world import REWARDS, stage_names

RANKING = 3
PLANS = ("spiral", "ring", "tile", "cover")
DIFFICULTY = {"easy": 0.16, "medium": 0.10, "hard": 0.06}
TILE_CANDIDATES = 40
REGION_FRACTION = 0.3          # the rewarding region: the map's value is at least this share of the peak
CAP_FRACTION = 0.97            # no ladder level above this share of the peak
LENGTH_STEPS = 80              # candidate arm lengths tried per arm
CENTRE_LOWER = 0.5             # the share of ladder sets whose centre is not the best bush (2nd or 3rd)
LADDER_TOP = (0.80, 0.93)      # the best bush of a ladder with a lower centre is this share of the peak (drawn)
PUSH_LIMIT = 1.6               # a centre pushed outward to take a lower rank goes at most this many jitter ellipses (spreads) from the peak
COVER_REGION = 0.4            # cover: the centres are drawn from the part of the map paying at least this share of the peak
COVER_CANDIDATES = 60
HIT_HOMES = 4                  # centres tried (the planned one, then pulled toward the peak) looking for a plus that hits its ladder before one that misses is accepted
HIT_TOLERANCE = 0.3            # a ladder is hit when every arm is within this many ladder steps of its level


class Ctx:
    """What the plans share: the session's map, peak and frame, and the constraints."""

    def __init__(self, params, min_gap, rng):
        self.params, self.rng, self.gap = params, rng, float(min_gap)
        self.valuefn = REWARDS[stage_names(params)[2]]
        self.peak, self.frame = peak_and_frame(params)
        self.angle, self.s1, self.s2 = self.frame
        th = math.radians(self.angle)
        self.f1, self.f2 = np.array([math.cos(th), math.sin(th)]), np.array([-math.sin(th), math.cos(th)])
        self.jitter = float(getattr(params, "ranking_plus_jitter", 1.0))
        self.arm = float(getattr(params, "ranking_plus_arm", 1.0))
        self.ratio = float(getattr(params, "ranking_plus_arm_ratio", 2.0))
        self.sep = float(getattr(params, "ranking_plus_min_separation", 0.08))
        self.floor = PLUS_MIN_FRACTION * self.peak[2]
        self.options = {t: ranking.plus_fit_options(t) for t in (False, True)}
        axis = np.linspace(0.0, 1.0, 64)
        gs, gc = np.meshgrid(axis, axis, indexing="ij")
        field = self.value(gs, gc)
        keep = field >= REGION_FRACTION * self.peak[2]
        self.region = np.column_stack([gs[keep], gc[keep]])           # sample points of the rewarding region

    def value(self, shape, colour):
        return np.asarray(self.valuefn(self.params.reward_function, shape, colour), dtype=float)

    def offset_to_centre(self, radius, angle):
        """A point `radius` (a share of the jitter ellipse) and `angle` from the peak, in the peak bump's frame."""
        r = self.jitter * radius
        return np.array(self.peak[:2]) + r * (math.cos(angle) * self.s1 * self.f1 + math.sin(angle) * self.s2 * self.f2)


OFF_AXIS = 15.0               # a random plus stays at least this many degrees from the feature axes (a plus repeats every 90), so it never looks like an aligned one


def axis_distance(u):
    """Degrees from the nearest feature axis of the direction `u` (0 = along an axis, 45 at most)."""
    ang = abs(math.degrees(math.atan2(u[1], u[0]))) % 90.0
    return min(ang, 90.0 - ang)


def rotated(u, deg):
    c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([c * u[0] - sn * u[1], sn * u[0] + c * u[1]])


def axes_for(ctx, mode, phi=None, ratio=None):
    """(u1, u2, length1, length2) nominal axes: aligned/bump from `ranking.plus_axes`; random with the given turn `phi` (radians) and stretch `ratio` (drawn when None)."""
    if mode != "random":
        return ranking.plus_axes(mode, ctx.frame, ctx.arm, ctx.ratio, ctx.rng)
    phi = math.radians(ctx.rng.uniform(OFF_AXIS, 90.0 - OFF_AXIS)) if phi is None else phi
    r = math.exp(ctx.rng.uniform(-math.log(ctx.ratio), math.log(ctx.ratio))) if ratio is None else ratio
    m = math.sqrt(ctx.s1 * ctx.s2)
    return np.array([math.cos(phi), math.sin(phi)]), np.array([-math.sin(phi), math.cos(phi)]), ctx.arm * m * math.sqrt(r), ctx.arm * m / math.sqrt(r)


def room(centre, direction):
    """How far a ray from `centre` along `direction` stays inside the unit square (less the margin)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(direction > 1e-12, (1.0 - PLUS_MARGIN - centre) / direction, np.where(direction < -1e-12, (PLUS_MARGIN - centre) / direction, np.inf))
    return float(t.min())


def points_ok(ctx, pts, v):
    if pts.min() < PLUS_MARGIN - 1e-9 or pts.max() > 1.0 - PLUS_MARGIN + 1e-9:
        return False
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    return bool(d[np.triu_indices(5, 1)].min() >= ctx.sep - 1e-9 and v.min() >= ctx.floor and np.diff(np.sort(v)).min() >= ctx.gap)


def fit_free(ctx, centre, u1, u2, lengths, mode, flip):
    """The nominal plus, shrunk and turned (random) or stretched (others) by the smallest change that fits (`ranking.plus_fit_options`); None when none fits."""
    for _cost, sc1, sc2, turn in ctx.options[mode == "random"]:
        v1, v2 = rotated(u1, flip * turn), rotated(u2, flip * turn)
        if mode == "random" and axis_distance(v1) < OFF_AXIS:
            continue
        ln = lengths * np.array([sc1, sc1, sc2, sc2])
        pts = np.vstack([centre, centre + ln[0] * v1, centre - ln[1] * v1, centre + ln[2] * v2, centre - ln[3] * v2])
        if pts.min() < PLUS_MARGIN or pts.max() > 1.0 - PLUS_MARGIN:
            continue
        v = ctx.value(pts[:, 0], pts[:, 1])
        if points_ok(ctx, pts, v):
            return pts, v, ln, v1, v2, (sc1 + sc2) / 2.0, flip * turn, True
    return None


def ladder_levels(ctx, vc, delta, u):
    """Values of the four arms for a ladder of step `delta` (points) in which `u` bushes (0 to 4) lie above the centre's value `vc`; None when the peak (CAP_FRACTION of it) or the
    floor leave no room for that."""
    if vc + u * delta > CAP_FRACTION * ctx.peak[2] + 1e-9 or vc - (4 - u) * delta < ctx.floor - 1e-9:
        return None
    return np.array([vc + delta * k for k in range(1, u + 1)] + [vc - delta * k for k in range(1, 4 - u + 1)])


def ladder_centre(ctx, centre, delta, push=True):
    """(centre, u): how many bushes of the ladder lie above the centre, drawn (the centre is the best with probability 1 - CENTRE_LOWER, else its place is the 2nd or the 3rd: along an axis only one
    arm can climb toward the peak, so at most two bushes lie above it), and the centre moved outward from the peak along its own ray, as little as it takes (at most PUSH_LIMIT spreads), until the peak leaves room for that many bushes above it.
    A place that cannot be reached is lowered one step at a time."""
    if not push:                                                      # the centre stays: its place in the ladder is drawn among those its value allows
        vc = float(ctx.value(centre[0], centre[1]))
        feasible = [u for u in range(3) if ladder_levels(ctx, vc, delta, u) is not None]
        return (centre, int(ctx.rng.choice(feasible))) if feasible else (centre, None)
    want = 0 if ctx.rng.uniform() >= CENTRE_LOWER else int(ctx.rng.integers(1, 3))          # at most two bushes lie above it: along an axis only one arm can climb
    peak = np.array(ctx.peak[:2])
    frame = np.array([[ctx.f1[0] / ctx.s1, ctx.f1[1] / ctx.s1], [ctx.f2[0] / ctx.s2, ctx.f2[1] / ctx.s2]])        # features -> the peak bump's unit frame
    off = frame @ (centre - peak)
    rho = float(np.hypot(*off))
    direction = off / rho if rho > 1e-9 else np.array([math.cos(a := ctx.rng.uniform(0.0, 2.0 * math.pi)), math.sin(a)])
    limit = PUSH_LIMIT * max(ctx.jitter, 1.0)
    top = ctx.rng.uniform(*LADDER_TOP) * ctx.peak[2]                 # the best bush of a ladder whose centre is lower: its value is drawn, not the highest the peak allows (an arm line seldom passes the peak)
    goal = {u: top - u * delta for u in range(1, 5)}                 # the centre's value for a place u below the best
    for u in range(want, -1, -1):
        for way in (direction, -direction):                          # outward on its own side first, then on the other side of the peak (an edge may block the first)
            for r in np.linspace(rho, max(limit, rho), 40):
                c = peak + np.linalg.solve(frame, way * r)
                if c.min() < PLUS_MARGIN or c.max() > 1.0 - PLUS_MARGIN:
                    break
                vc = float(ctx.value(c[0], c[1]))
                if vc <= goal.get(u, np.inf) and ladder_levels(ctx, vc, delta, u) is not None:
                    return c, u
    return centre, None


def fit_ladder(ctx, centre, u1, u2, mode, flip, delta, u):
    """A plus whose arms hit a ladder of values `delta` apart: for each turn allowed (none for aligned) the length of every arm is the one (on a grid, from the separation to the
    edge of the square) whose value is nearest each level, the levels assigned to the arms by the best of the 24 orders. Returns the same tuple as `fit_free` (the last item says
    whether every arm is within HIT_TOLERANCE steps of its level), the best found; None when no turn gives a valid plus."""
    vc = float(ctx.value(centre[0], centre[1]))
    levels = ladder_levels(ctx, vc, delta, u)
    if levels is None:
        return None
    turns = [0.0] + ([sign * d for d in range(5, 46, 5) for sign in (1.0, -1.0)] if mode == "random" else [])
    best = None
    for turn in turns:
        v1, v2 = rotated(u1, flip * turn), rotated(u2, flip * turn)
        if mode == "random" and axis_distance(v1) < OFF_AXIS:
            continue
        dirs = [v1, -v1, v2, -v2]
        grids, vals = [], []
        for d in dirs:
            top = room(centre, d)
            if top < ctx.sep:
                break
            lengths = np.linspace(ctx.sep, top, LENGTH_STEPS)
            grids.append(lengths)
            vals.append(ctx.value(centre[0] + lengths * d[0], centre[1] + lengths * d[1]))
        else:
            err = np.array([[np.abs(v - lv).min() for lv in levels] for v in vals])                  # arm x level: the best error
            perm = min(itertools.permutations(range(4)), key=lambda p: err[np.arange(4), list(p)].max())
            worst = float(err[np.arange(4), list(perm)].max())
            ln = np.array([grids[k][int(np.argmin(np.abs(vals[k] - levels[perm[k]])))] for k in range(4)])
            pts = np.vstack([centre, centre + ln[0] * v1, centre - ln[1] * v1, centre + ln[2] * v2, centre - ln[3] * v2])
            v = ctx.value(pts[:, 0], pts[:, 1])
            if points_ok(ctx, pts, v) and (best is None or worst < best[0]):
                best = (worst, (pts, v, ln, v1, v2, 1.0, flip * turn, worst <= HIT_TOLERANCE * delta))
            if best is not None and best[0] <= HIT_TOLERANCE * delta:
                break
    return None if best is None else best[1]


def build(ctx, mode, centre_planned, delta, phi=None, ratio=None, fallback=True, push=True):
    """One plus around `centre_planned`: the fit (free or ladder) with the arm draws and, as last resorts, the centre pulled toward the peak and then toward the map's middle (as
    `ranking.plus_sets`). Returns (pts, v, ln, v1, v2, scale, turn, hit, centre, pull, inward) or None."""
    peak = np.array(ctx.peak[:2])
    homes = [(pull, 0.0, peak + pull * (centre_planned - peak)) for pull in ranking.PLUS_PULLS] if fallback else [(1.0, 0.0, centre_planned)]
    if fallback:
        homes += [(0.0, t, peak + t * (0.5 - peak)) for t in ranking.PLUS_INWARD]
    flip = ctx.rng.choice((-1.0, 1.0))
    spare = None                                                    # a ladder plus that misses a level: used only when no centre tried hits them all
    for k, (pull, inward, home) in enumerate(homes):
        centre = np.clip(home, PLUS_MARGIN, 1.0 - PLUS_MARGIN)
        for _try in range(ranking.PLUS_TRIES if delta is None else 3):
            used = centre                                           # (a ladder may push the centre outward to take a lower place)
            u1, u2, l1, l2 = axes_for(ctx, mode, phi, ratio)
            u1, u2 = u1 * ctx.rng.choice((-1.0, 1.0)), u2 * ctx.rng.choice((-1.0, 1.0))
            if delta is None:
                lengths = np.array([l1, l1, l2, l2]) * ctx.rng.uniform(*ranking.PLUS_ARM_JITTER, 4)
                out = fit_free(ctx, centre, u1, u2, lengths, mode, flip)
            else:
                pushed, u = ladder_centre(ctx, centre, delta * ctx.peak[2], push)
                if u is None:
                    continue
                out = fit_ladder(ctx, pushed, u1, u2, mode, flip, delta * ctx.peak[2], u)
                used = pushed
            if out is not None and out[7]:
                return out + (used, pull, inward)
            if out is not None and spare is None:
                spare = out + (used, pull, inward)
        if spare is not None and k >= HIT_HOMES:
            break
    return spare


# --------------------------------------------------------------------------------------------------
# Plans: where the centres go, how the random pluses turn and stretch
# --------------------------------------------------------------------------------------------------

def mode_of(set_index, mode_setting):
    return ranking.PLUS_MIXED[set_index % len(ranking.PLUS_MIXED)] if mode_setting == "mixed" else mode_setting


def plan_spiral(ctx, modes):
    """Per axes mode a sunflower spiral; the random pluses draw their own turn and stretch. Yields (centre, phi, ratio) per set."""
    members = {m: [s for s in range(len(modes)) if modes[s] == m] for m in set(modes)}
    phase = {m: ctx.rng.uniform(0.0, 2.0 * math.pi) for m in sorted(members)}
    out = [None] * len(modes)
    for m, ids in members.items():
        for k, s in enumerate(ids):
            out[s] = (ctx.offset_to_centre(math.sqrt((k + 0.5) / len(ids)), k * GOLDEN_ANGLE + phase[m]), None, None)
    return out


def plan_ring(ctx, modes):
    """Each ranking a triangle around the peak: ring radius from the equal-area series, phase turned by the golden angle per ranking, the corner of each mode rotating; the two
    random pluses of a ranking 45 degrees apart, the stretch ratio stratified over the rankings (a van der Corput order so neighbouring rankings differ)."""
    n_rank = int(math.ceil(len(modes) / RANKING))
    out = []
    offset = ctx.rng.uniform(0.0, 2.0 * math.pi)
    phase = ctx.rng.uniform()
    order = ctx.rng.permutation(n_rank)                                     # which ring radius each ranking takes: radii are not monotone in time
    for s in range(len(modes)):
        r, j = divmod(s, RANKING)
        corner = (j + r) % RANKING                                         # the mode of corner j rotates with the ranking
        radius = math.sqrt((order[r] + 0.5) / n_rank)
        angle = offset + r * GOLDEN_ANGLE + corner * 2.0 * math.pi / RANKING
        phi = ratio = None
        if modes[s] == "random":
            seat = sum(1 for t in range(r * RANKING, s) if modes[t] == "random")       # 0 or 1: the first or second random plus of the ranking
            u = ((r * 0.6180339887 + seat * 0.5) + phase) % 1.0                        # the two random pluses of a ranking half a cycle apart, the cycle over rankings the golden ratio
            phi = math.radians(OFF_AXIS + (90.0 - 2.0 * OFF_AXIS) * u)                  # always off the axes
            ratio = math.exp(math.log(ctx.ratio) * (2.0 * ((order[r] * 0.6180339887 + 0.5 * seat) % 1.0) - 1.0))
        out.append((ctx.offset_to_centre(radius, angle), phi, ratio))
    return out


def coverage(region, points):
    """Mean distance from the region's sample points to the nearest of `points`."""
    d = np.sqrt(((region[:, None, :] - points[None, :, :]) ** 2).sum(-1)).min(axis=1)
    return float(d.mean())


def plus_sets(params, set_count, set_size, min_gap, rng, plan="spiral", difficulty="free"):
    """The pool's sets by a plan and a difficulty; the same return as `ranking.plus_sets`: (pool, chosen, roles, meta) with `delta` (the ladder step as a share of the peak, None
    for free) and `hit` in each set's meta."""
    if set_size != 5:
        raise ValueError(f"the plus design has five bushes, not rankingSetSize {set_size}")
    if plan not in PLANS:
        raise ValueError(f"unknown rankingPlusPlan {plan!r}: one of {PLANS}")
    ctx = Ctx(params, min_gap, rng)
    mode_setting = str(getattr(params, "ranking_plus_axes", "mixed") or "mixed")
    modes = [mode_of(s, mode_setting) for s in range(set_count)]
    deltas = [None] * set_count
    if difficulty != "free":
        steps = ("easy", "medium", "hard") if difficulty == "mixed" else None
        for s in range(set_count):
            key = steps[(s // RANKING) % 3] if steps else difficulty
            deltas[s] = DIFFICULTY[key] if key in DIFFICULTY else float(key)
            if deltas[s] * ctx.peak[2] < 1.1 * ctx.gap:
                raise ValueError(f"difficulty {key}: a step of {deltas[s]:.2f} of the peak is under the tie gap {ctx.gap} (raise the difficulty's step)")
    if plan == "tile":
        return plan_tile(ctx, modes, deltas, set_count)
    if plan == "cover":
        return plan_cover(ctx, modes, deltas, set_count)
    planned = plan_ring(ctx, modes) if plan == "ring" else plan_spiral(ctx, modes)
    built = []
    for s in range(set_count):
        centre, phi, ratio = planned[s]
        out = build(ctx, modes[s], centre, deltas[s], phi, ratio)
        if out is None:
            raise ValueError(f"set {s}: no plus fits (plan {plan}, difficulty {difficulty}); relax a setting")
        built.append(out)
    return assemble(ctx, modes, deltas, built)


def plan_tile(ctx, modes, deltas, set_count):
    """Greedy space filling: each set the best of TILE_CANDIDATES draws by the coverage of the rewarding region it leaves."""
    placed = np.empty((0, 2))
    built = []
    for s in range(set_count):
        best = None
        for _ in range(TILE_CANDIDATES):
            centre = ctx.offset_to_centre(math.sqrt(ctx.rng.uniform()), ctx.rng.uniform(0.0, 2.0 * math.pi))
            out = build(ctx, modes[s], centre, deltas[s], fallback=False, push=False)
            if out is None:
                continue
            score = coverage(ctx.region, np.vstack([placed, out[0]]) if len(placed) else out[0]) + (0.0 if out[7] else 1.0)      # a plus that misses its ladder only when none hits
            if best is None or score < best[0]:
                best = (score, out)
        if best is None:
            out = build(ctx, modes[s], ctx.offset_to_centre(0.0, 0.0), deltas[s])
            if out is None:
                raise ValueError(f"set {s}: no plus fits (plan tile); relax a setting")
            best = (None, out)
        built.append(best[1])
        placed = np.vstack([placed, best[1][0]])
    return assemble(ctx, modes, deltas, built)


def plan_cover(ctx, modes, deltas, set_count):
    """Centres anywhere in the rewarding region (`COVER_REGION` of the peak or more), no tie to the peak: each set is the best of COVER_CANDIDATES draws by three coverage terms of the
    region it leaves: all the bushes over the whole pool, the centres alone over the whole pool (or the arms would do all the covering and the centres cluster in the middle), and all
    the bushes over its own ranking (the three pluses of a ranking tile the region between them). The ladder keeps the centre where it is and draws its place in the ladder among
    those its value allows (a plus that misses its ladder is taken only when none hits)."""
    pool_pts = ctx.region[ctx.value(ctx.region[:, 0], ctx.region[:, 1]) >= COVER_REGION * ctx.peak[2]]
    empty = np.empty((0, 2))
    placed, centres, ranking_pts = empty, empty, empty
    built = []
    for s in range(set_count):
        if s % RANKING == 0:
            ranking_pts = empty
        best = None
        for _ in range(COVER_CANDIDATES):
            centre = pool_pts[int(ctx.rng.integers(len(pool_pts)))] + ctx.rng.uniform(-0.008, 0.008, 2)
            out = build(ctx, modes[s], centre, deltas[s], fallback=False, push=False)
            if out is None:
                continue
            score = (coverage(ctx.region, np.vstack([placed, out[0]])) + coverage(ctx.region, np.vstack([centres, out[8][None, :]]))
                     + coverage(ctx.region, np.vstack([ranking_pts, out[0]])) + (0.0 if out[7] else 1.0))
            if best is None or score < best[0]:
                best = (score, out)
        if best is None:
            raise ValueError(f"set {s}: no plus fits (plan cover); relax a setting")
        built.append(best[1])
        placed = np.vstack([placed, best[1][0]])
        centres = np.vstack([centres, best[1][8][None, :]])
        ranking_pts = np.vstack([ranking_pts, best[1][0]])
    return assemble(ctx, modes, deltas, built)


def assemble(ctx, modes, deltas, built):
    shapes, colors, values, roles, meta = [], [], [], [], []
    peak = np.array(ctx.peak[:2])
    for s, (pts, v, ln, v1, v2, scale, turn, hit, centre, pull, inward) in enumerate(built):
        order = np.argsort(v)
        shapes += list(pts[order, 0])
        colors += list(pts[order, 1])
        values += list(v[order])
        roles.append([PLUS_ROLES[k] for k in order])
        meta.append({"axes": modes[s], "centre": [float(centre[0]), float(centre[1])], "u1": [float(v1[0]), float(v1[1])], "u2": [float(v2[0]), float(v2[1])], "arms": [float(x) for x in ln],
                     "offset": [float(c - p) for c, p in zip(centre, peak)], "scale": float(scale), "scales": [float(scale), float(scale)], "turn": float(turn), "pull": float(pull),
                     "inward": float(inward), "delta": deltas[s], "hit": bool(hit)})
    n = len(built) * 5
    pool = {"shape": np.array(shapes), "color": np.array(colors), "moisture": np.full(n, float(ctx.params.moisture_when_fixed)), "value": np.array(values),
            "peak": ctx.peak, "frame": ctx.frame}
    return pool, np.arange(n).reshape(len(built), 5), roles, meta


# --------------------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------------------

def metrics(sidecar, params):
    """What a plan achieved: coverage of the rewarding region (mean and 95th percentile distance to the nearest bush), the spacing of the bushes, the spread of the values over the
    session (normalised entropy of ten bins between the floor and the peak: 1 = even) and within a set (median step between neighbours, median best-minus-worst), the share of
    ladders hit, and how many pluses were shrunk or turned or moved."""
    ctx = Ctx(params, sidecar["minGap"], np.random.default_rng(0))
    pts = np.column_stack([sidecar["shape"], sidecar["color"]])
    dist = np.sqrt(((ctx.region[:, None, :] - pts[None, :, :]) ** 2).sum(-1)).min(axis=1)
    nn = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)) + np.eye(len(pts)) * 9
    peak = ctx.peak[2]
    vals = np.array(sidecar["value"]) / peak
    hist, _ = np.histogram(vals, bins=10, range=(PLUS_MIN_FRACTION, 1.0))
    p = hist / max(hist.sum(), 1)
    entropy = float(-(p[p > 0] * np.log(p[p > 0])).sum() / math.log(10))
    sets = [sorted(b["value"] / peak for b in s["bushes"]) for s in sidecar["sets"]]
    rank_cover = []
    for r in range(len(sidecar["sets"]) // RANKING):
        rp = pts[r * RANKING * 5:(r + 1) * RANKING * 5]
        rank_cover.append(float(np.sqrt(((ctx.region[:, None, :] - rp[None, :, :]) ** 2).sum(-1)).min(axis=1).mean()))
    meta = sidecar["plus"]
    return {"coverageMean": float(dist.mean()), "coverageP95": float(np.quantile(dist, 0.95)), "nearestBush": float(nn.min(axis=1).mean()), "rankingCoverage": float(np.mean(rank_cover)),
            "valueEntropy": entropy, "stepMedian": float(np.median([np.diff(s).min() for s in sets])), "spanMedian": float(np.median([s[-1] - s[0] for s in sets])),
            "centreBest": float(np.mean([max(st["bushes"], key=lambda b: b["value"])["role"] == "centre" for st in sidecar["sets"]])),
            "hit": float(np.mean([m.get("hit", True) for m in meta])), "fitted": float(np.mean([m["scale"] < 1.0 or m["turn"] != 0.0 for m in meta])),
            "moved": float(np.mean([m["pull"] < 1.0 or m["inward"] > 0.0 for m in meta]))}
