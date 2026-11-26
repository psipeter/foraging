"""Selection sets: k bushes in view at once, harvested in best-to-worst order, played in place during a session's selection breaks.

The participant (or agent) stands still and sees every bush of the set on an arc in front of them, all with the same distance from the player to the
canopy's edge. Harvesting needs no walking (the game ignores the harvest range here and takes the bush the crosshair is on), so no bush hides another,
and the rank of a bush is the order in which it was harvested. A bush stays, spent, after it is harvested. Outcomes are never shown.

A session's sets are one pool file (`<session>_seed<N>.ranking.json`, `selection.py pool <session>`), chosen together so that, across them, the true values fill
the range evenly and the bushes fill the feature plane; within a set the values are a ladder with every neighbouring gap at least the tie gap
(`selectionTieGap`). The geometry of a set is fixed by the arc (`selectionDistance`, `selectionArcSpan`, `selectionSetSize`), positions are relative to the player
(standing at the origin, facing +z), and the game turns and moves them to the player's pose.

The module holds the generator (`generate_pool`), the geometry checks (`check_arc`) and the scores a selection can be given from its picks
(`pair_scores` (the payout rule), `implied_pair_scores`, `kendall_tau`, `first_pick_regret`, `rank_gain`: all are computed from the raw order and the true values, so the metric
can be chosen at analysis time). Scoring is not part of a run (see docs/SIMULATION.md).
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from world import REWARDS, load_session, stage_names, unity_world_path

TIE_TOLERANCE = 0.05        # a pair whose true values differ by less than this is a tie: it is not scored
MIN_ASPECT = 4.0 / 3.0      # the narrowest window the arc must fit in (the camera's vertical field of view is fixed)
FOV_MARGIN = 1.0            # degrees between the outermost bush's centre and the edge of the view at MIN_ASPECT: at least half of each bush is on screen without turning
ANGLE_MARGIN = 2.0          # degrees between neighbouring canopies at the widest radius
POOL_SIZE = 8000            # (shape, colour) candidates the sets are chosen from
SEARCH_STEPS = 30000        # replacements tried when choosing the sets
VALUE_LOW_QUANTILE = 0.02   # the ladder of values spans these quantiles of the candidates' values
VALUE_HIGH_QUANTILE = 0.995
REPULSION = 0.12            # spread (feature units) of the repulsion that spreads the chosen bushes over the feature plane
SAME_SET_REPULSION = 2.0    # bushes of one set repel this much more than bushes of different sets (they must look different)
FEATURE_AXES = ("shape", "color")      # moisture is the player's ground value in a set: it is no feature of a selection


def canopy_radius(params, shape):
    """The canopy's horizontal radius at a shape value (Tree.ApplyAttributes)."""
    lo, hi = params.shape_range
    t = np.clip((np.asarray(shape) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    w_lo, w_hi = params.canopy_width_range
    return (w_hi + (w_lo - w_hi) * t) * 0.5


# --------------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------------

def slot_bearings(set_size, arc_span):
    """Bearing (degrees from the heading, + to the right) of each slot's bush centre, evenly spread and symmetric about the heading."""
    if set_size == 1:
        return np.zeros(1)
    return np.linspace(-arc_span / 2.0, arc_span / 2.0, int(set_size))


def slot_position(distance, bearing_deg, radius):
    """Centre (x, z) of a bush on the arc, for the heading +z (yaw 0) at the spawn point (0, 0): the canopy's edge is `distance` from the
    spawn point, at the bearing of its centre."""
    d = float(distance) + np.asarray(radius, dtype=float)
    theta = math.radians(bearing_deg)
    return np.array([d * math.sin(theta), d * math.cos(theta)])


def angular_radius(distance, radius):
    """Half the angle a canopy of this radius subtends, seen from the spawn point with its edge `distance` away (degrees)."""
    return np.degrees(np.arcsin(np.asarray(radius, dtype=float) / (float(distance) + np.asarray(radius, dtype=float))))


def horizontal_fov(vertical_fov, aspect):
    return math.degrees(2.0 * math.atan(math.tan(math.radians(vertical_fov) / 2.0) * aspect))


def check_arc(params, set_size, arc_span, distance, aspect=MIN_ASPECT):
    """Margins of the arc in degrees, for the widest canopy the session can draw: `separation` between neighbouring canopies and `view` between the
    outermost bush's centre and the edge of the view at `aspect` (at least half of that bush is then on screen). Raises if either is too small (the bushes would overlap, or fall outside a narrow window)."""
    rmax = max(float(v) for v in params.canopy_width_range) * 0.5
    alpha = float(angular_radius(distance, rmax))
    separation = (arc_span / max(set_size - 1, 1) - 2.0 * alpha) if set_size > 1 else float("inf")
    view = horizontal_fov(float(getattr(params, "camera_field_of_view", 75.0)), aspect) / 2.0 - arc_span / 2.0
    if separation < ANGLE_MARGIN:
        raise ValueError(f"{set_size} bushes over {arc_span} degrees at {distance}: neighbouring canopies would be {separation:.1f} degrees apart (at least {ANGLE_MARGIN} needed); "
                         f"widen the arc, move the bushes farther away or reduce the set size")
    if view < FOV_MARGIN:
        raise ValueError(f"an arc of {arc_span} degrees leaves {view:.1f} degrees from the outermost bush's centre to the edge of a {aspect:.2f}:1 window (at least {FOV_MARGIN} needed, so half of it shows); narrow the arc")
    return {"separation": float(separation), "view": float(view), "angularRadiusMax": alpha}


# --------------------------------------------------------------------------------------------------
# Choosing the sets
# --------------------------------------------------------------------------------------------------

def candidate_pool(params, rng, n=POOL_SIZE, moisture=0.5):
    """Random bushes to choose from: shape and colour uniform where they vary (else their fixed value), moisture a fixed value, each with its true value."""
    shape = rng.uniform(0.0, 1.0, n) if params.shape_varies else np.full(n, float(params.shape_when_fixed))
    color = rng.uniform(0.0, 1.0, n) if params.color_varies else np.full(n, float(params.color_when_fixed))
    mois = np.full(n, float(moisture))
    value = np.asarray(REWARDS[stage_names(params)[2]](params.reward_function, shape, color), dtype=float)
    return {"shape": shape, "color": color, "moisture": mois, "value": value}


def value_ladder(values, set_count, set_size):
    """Target true values of the sets: set_count * set_size levels evenly spread between two quantiles of the candidates' values, dealt round-robin so
    every set spans the whole range (set s takes levels s, s + set_count, ...) and, together, the sets fill it evenly. Returns (targets[set, rank], step)."""
    total = set_count * set_size
    lo, hi = (float(np.quantile(values, q)) for q in (VALUE_LOW_QUANTILE, VALUE_HIGH_QUANTILE))
    levels = np.linspace(lo, hi, total)
    step = (hi - lo) / max(total - 1, 1)
    return levels.reshape(set_size, set_count).T, step


def choose_sets(params, pool, set_count, set_size, min_gap, rng, steps=SEARCH_STEPS):
    """Indices into the pool of the bushes of each set, shape (set_count, set_size), the rows ordered from the lowest true value to the highest.

    The loss is the squared distance of each bush's value from its ladder level (in ladder steps), a large penalty for each neighbouring pair of a set closer
    than `min_gap`, and a repulsion in the (shape, colour) plane (stronger within a set) that spreads the bushes over it. The search replaces one bush at a time by a candidate near its level."""
    targets, step = value_ladder(pool["value"], set_count, set_size)
    if step * set_count < min_gap:
        raise ValueError(f"the values of the candidates span too little for {set_count} sets of {set_size}: neighbouring bushes of a set would differ by "
                         f"{step * set_count:.3f} < the tie gap {min_gap} (lower the gap, lower the set size or count, or widen the reward)")
    axes = [a for a in FEATURE_AXES if bool(getattr(params, f"{a}_varies"))] or list(FEATURE_AXES)
    plane = np.column_stack([pool[a] for a in axes])
    values = pool["value"]
    near = [np.flatnonzero(np.abs(values - t) <= step) for t in targets.reshape(-1)]
    near = [c if len(c) else np.array([int(np.argmin(np.abs(values - t)))]) for c, t in zip(near, targets.reshape(-1))]
    flat_targets = targets.reshape(-1)
    owner = np.repeat(np.arange(set_count), set_size)               # flat position p = set * set_size + rank holds the bush for targets[set, rank]
    chosen = np.array([c[rng.integers(0, len(c))] for c in near])
    sigma2 = REPULSION ** 2

    def repulsion_of(index, cand):
        """Repulsion felt by bush `cand` placed at flat position `index` from every other chosen bush."""
        d2 = ((plane[chosen] - plane[cand]) ** 2).sum(axis=1)
        weight = np.where(owner == owner[index], SAME_SET_REPULSION, 1.0)
        mask = np.arange(len(chosen)) != index
        return float((weight * np.exp(-d2 / (2.0 * sigma2)))[mask].sum())

    def gap_penalty(s):
        row = np.sort(values[chosen[s * set_size:(s + 1) * set_size]])
        short = np.maximum(0.0, min_gap - np.diff(row))
        return float((short ** 2).sum()) / (step ** 2) * 50.0

    def local(index, cand):
        s = index // set_size
        old = chosen[index]
        chosen[index] = cand
        loss = ((values[cand] - flat_targets[index]) / step) ** 2 + repulsion_of(index, cand) + gap_penalty(s)
        chosen[index] = old
        return loss

    for _ in range(int(steps)):
        index = int(rng.integers(0, len(chosen)))
        cand = int(near[index][rng.integers(0, len(near[index]))])
        if cand in chosen:
            continue
        if local(index, cand) < local(index, chosen[index]):
            chosen[index] = cand
    return chosen.reshape(set_count, set_size)


# --------------------------------------------------------------------------------------------------
# The plus design (`selectionDesign` "plus")
# --------------------------------------------------------------------------------------------------

PLUS_AXES_MODES = ("aligned", "bump", "random")
PLUS_ARM_JITTER = (0.7, 1.3)    # each arm draws its own length between these multiples of the nominal one, so the four values are never symmetric
PLUS_MIN_FRACTION = 0.25        # every bush of a plus pays at least this share of the map's peak: each one looks "good" to some degree
PLUS_TRIES = 8                  # draws of the arms and axes per centre position before the centre is moved
PLUS_INWARD = tuple(np.arange(0.1, 1.0001, 0.1))     # provisional (PI, 2026-11-24: the rule for a peak at an edge is still to be designed): shares of the way from the peak to the map's middle
PLUS_PULLS = tuple(np.arange(1.0, -1e-9, -0.1))     # the shares of its offset from the peak a centre may keep
PLUS_MIXED = ("aligned", "random", "random")     # the axes modes "mixed" takes in turn
PLUS_OFF_AXIS = 15.0            # degrees: a random plus stays at least this far from the feature axes
PLUS_MIN_SCALE = 0.5            # a plus that does not fit is shrunk to at most this share of its nominal arms
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))
PLUS_MARGIN = 0.02              # the five points stay this far inside the unit (shape, colour) square
PLUS_ROLES = ("centre", "+1", "-1", "+2", "-2")


def peak_and_frame(params, grid=201):
    """The value map's peak (shape, colour, value) on a grid, and the frame of the bump nearest to it: (angle in degrees, sigma along its first axis, sigma along its second)."""
    axis = np.linspace(0.0, 1.0, grid)
    field = np.asarray(REWARDS[stage_names(params)[2]](params.reward_function, axis[:, None], axis[None, :]), dtype=float)
    i, j = np.unravel_index(int(np.argmax(field)), field.shape)
    peak = (float(axis[i]), float(axis[j]), float(field[i, j]))
    bumps = params.reward_function.get("bumps") or []
    if not bumps:
        raise ValueError("the plus design needs a value map with at least one bump")
    nearest = min(bumps, key=lambda b: (float(b["centerShape"]) - peak[0]) ** 2 + (float(b["centerColor"]) - peak[1]) ** 2 - 1e-6 * float(b["height"]))
    s1 = float(nearest["width"])
    s2 = float(nearest.get("widthColor") or 0.0) or s1
    return peak, (float(nearest.get("angle") or 0.0), s1, s2)


def plus_axes(mode, frame, arm, ratio, rng):
    """(u1, u2, length1, length2): the plus's two unit axes in the (shape, colour) plane and the nominal arm length along each, for an axes mode.
    aligned: the shape and colour axes, the lengths the bump's own spreads along them; bump: the bump's turned axes, lengths `arm` spreads along each;
    random: a random turn, the lengths `arm` times the bump's mean spread, the ratio of the two log-uniform up to `ratio` either way."""
    angle, s1, s2 = frame
    th = math.radians(angle)
    if mode == "bump":
        return np.array([math.cos(th), math.sin(th)]), np.array([-math.sin(th), math.cos(th)]), arm * s1, arm * s2
    if mode == "aligned":
        along_shape = math.sqrt((s1 * math.cos(th)) ** 2 + (s2 * math.sin(th)) ** 2)
        along_color = math.sqrt((s1 * math.sin(th)) ** 2 + (s2 * math.cos(th)) ** 2)
        return np.array([1.0, 0.0]), np.array([0.0, 1.0]), arm * along_shape, arm * along_color
    if mode == "random":
        phi = math.radians(rng.uniform(PLUS_OFF_AXIS, 90.0 - PLUS_OFF_AXIS))      # off the feature axes, or a random plus would look like an aligned one
        r = math.exp(rng.uniform(-math.log(max(ratio, 1.0)), math.log(max(ratio, 1.0))))
        m = math.sqrt(s1 * s2)
        return np.array([math.cos(phi), math.sin(phi)]), np.array([-math.sin(phi), math.cos(phi)]), arm * m * math.sqrt(r), arm * m / math.sqrt(r)
    raise ValueError(f"unknown selectionPlusAxes {mode!r}: one of {PLUS_AXES_MODES} or 'mixed'")


def plus_fit_options(turnable):
    """The (cost, scale along axis 1, scale along axis 2, turn in degrees) a plus may take to fit, cheapest first. A turnable plus (random axes) shrinks both axes together (down to
    PLUS_MIN_SCALE) and may turn up to 45 degrees (a plus is the same turned by 90); the cost is the shrink as a share of the most it may shrink plus the turn as a share of 45.
    A plus on given axes (aligned, bump) never turns: it only stretches, each axis' arms shrinking by their own factor, the cost the mean shrink share. The nominal plus comes first."""
    scales = np.arange(1.0, PLUS_MIN_SCALE - 1e-9, -0.05)
    span = 1.0 - PLUS_MIN_SCALE
    if turnable:
        turns = [0.0] + [sign * d for d in range(5, 46, 5) for sign in (1.0, -1.0)]
        options = [((1.0 - sc) / span + abs(t) / 45.0, float(sc), float(sc), t) for sc in scales for t in turns]
    else:
        options = [(((1.0 - a) + (1.0 - b)) / (2.0 * span), float(a), float(b), 0.0) for a in scales for b in scales]
    return sorted(options, key=lambda o: o[0])


def plus_sets(params, set_count, set_size, min_gap, rng):
    """The pool's sets as a plus: a centre around the map's peak and four arms, two along each of the plus's two axes (`selectionPlusAxes`; "mixed" takes aligned, random, random in turn),
    each arm of its own length.
    The centres are spread evenly: for each axes mode the centres of its sets lie on a sunflower spiral over the ellipse of radius `selectionPlusJitter` spreads of the peak bump
    (equal area per set, a random turn of the spiral per mode), so every part of the neighbourhood of the peak is visited; a centre that falls outside the unit square is moved onto its edge.
    A plus is kept when all five points lie in the unit square, pay at least PLUS_MIN_FRACTION of the peak, are `selectionPlusMinSeparation` apart in the plane, and their values differ by the
    tie gap. When the nominal plus does not fit, a random plus is shrunk (down to PLUS_MIN_SCALE) and turned (up to 45 degrees about its centre) and an aligned (or bump) plus is only stretched
    (each axis' arms shrunk by their own factor, never turned, so it stays on its axes), by the smallest change that fits (`plus_fit_options`);
    only when none fits are the arms and axes drawn again, and only then is the centre moved toward the peak (`pull` in the meta). Returns (pool, chosen, roles, meta): `pool` the bushes (set s, rank j from the lowest value at index s * set_size + j), `chosen`
    the indices that arrange them, `roles[s][j]` the role of the rank-j bush ("centre", "+1", "-1", "+2", "-2") and `meta[s]` how the set was drawn."""
    plan, difficulty = str(getattr(params, "selection_plus_plan", "spiral") or "spiral"), str(getattr(params, "selection_plus_difficulty", "free") or "free")
    if plan != "spiral" or difficulty != "free":
        import plus_plans                                                  # (the other plans and the ladder of values live there; this function is the baseline)
        return plus_plans.plus_sets(params, set_count, set_size, min_gap, rng, plan, difficulty)
    if set_size != 5:
        raise ValueError(f"the plus design has five bushes (a centre and four arms), not selectionSetSize {set_size}")
    if not (bool(params.shape_varies) and bool(params.color_varies)):
        raise ValueError("the plus design needs both shape and colour to vary")
    mode_setting = str(getattr(params, "selection_plus_axes", "mixed") or "mixed")
    jitter, arm = float(getattr(params, "selection_plus_jitter", 1.0)), float(getattr(params, "selection_plus_arm", 1.0))
    ratio, sep = float(getattr(params, "selection_plus_arm_ratio", 2.0)), float(getattr(params, "selection_plus_min_separation", 0.08))
    peak, frame = peak_and_frame(params)
    angle, s1, s2 = frame
    th = math.radians(angle)
    f1, f2 = np.array([math.cos(th), math.sin(th)]), np.array([-math.sin(th), math.cos(th)])
    floor = PLUS_MIN_FRACTION * peak[2]
    valuefn = REWARDS[stage_names(params)[2]]
    options = {turnable: plus_fit_options(turnable) for turnable in (False, True)}

    modes = [PLUS_MIXED[s % len(PLUS_MIXED)] if mode_setting == "mixed" else mode_setting for s in range(set_count)]
    members = {m: [s for s in range(set_count) if modes[s] == m] for m in set(modes)}
    phase = {m: rng.uniform(0.0, 2.0 * math.pi) for m in sorted(members)}
    spiral = {}                                                    # the set -> its centre's offset from the peak (before the square's edge)
    for m, ids in members.items():
        for k, s in enumerate(ids):
            r, a = jitter * math.sqrt((k + 0.5) / len(ids)), k * GOLDEN_ANGLE + phase[m]
            spiral[s] = r * (math.cos(a) * s1 * f1 + math.sin(a) * s2 * f2)

    def rotated(u, deg):
        c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return np.array([c * u[0] - sn * u[1], sn * u[0] + c * u[1]])

    shapes, colors, values, roles, meta = [], [], [], [], []
    for s in range(set_count):
        mode = modes[s]
        flip = rng.choice((-1.0, 1.0))                              # which way a plus that must turn turns first
        found = False
        homes = [(pull, 0.0, np.array(peak[:2]) + pull * spiral[s]) for pull in PLUS_PULLS]        # last resorts: the centre moves toward the peak (pull 1 = where the spiral put it) ...
        homes += [(0.0, t, np.array(peak[:2]) + t * (0.5 - np.array(peak[:2]))) for t in PLUS_INWARD]     # ... then from the peak toward the middle of the map (a peak at an edge has no room)
        for pull, inward, home in homes:
            centre = np.clip(home, PLUS_MARGIN, 1.0 - PLUS_MARGIN)
            for _try in range(PLUS_TRIES):
                u1, u2, l1, l2 = plus_axes(mode, frame, arm, ratio, rng)
                u1, u2 = u1 * rng.choice((-1.0, 1.0)), u2 * rng.choice((-1.0, 1.0))      # which end is '+' is arbitrary: no role is systematically the arm toward the peak
                lengths = np.array([l1, l1, l2, l2]) * rng.uniform(*PLUS_ARM_JITTER, 4)
                for _cost, sc1, sc2, turn in options[mode == "random"]:
                    v1, v2 = rotated(u1, flip * turn), rotated(u2, flip * turn)
                    if mode == "random" and min(abs(math.degrees(math.atan2(v1[1], v1[0]))) % 90.0, 90.0 - abs(math.degrees(math.atan2(v1[1], v1[0]))) % 90.0) < PLUS_OFF_AXIS:
                        continue
                    ln = lengths * np.array([sc1, sc1, sc2, sc2])
                    pts = np.vstack([centre, centre + ln[0] * v1, centre - ln[1] * v1, centre + ln[2] * v2, centre - ln[3] * v2])
                    if pts.min() < PLUS_MARGIN or pts.max() > 1.0 - PLUS_MARGIN:
                        continue
                    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
                    if d[np.triu_indices(5, 1)].min() < sep:
                        continue
                    v = np.asarray(valuefn(params.reward_function, pts[:, 0], pts[:, 1]), dtype=float)
                    if v.min() < floor or np.diff(np.sort(v)).min() < min_gap:
                        continue
                    found = True
                    break
                if found:
                    break
            if found:
                break
        if not found:
            raise ValueError(f"set {s}: no plus fits (axes {mode}, jitter {jitter}, arm {arm}, separation {sep}, gap {min_gap}); relax a setting")
        order = np.argsort(v)                                          # rank j from the lowest value
        shapes += list(pts[order, 0])
        colors += list(pts[order, 1])
        values += list(v[order])
        roles.append([PLUS_ROLES[k] for k in order])
        meta.append({"axes": mode, "centre": [float(centre[0]), float(centre[1])], "u1": [float(v1[0]), float(v1[1])], "u2": [float(v2[0]), float(v2[1])],
                     "arms": [float(x) for x in ln], "offset": [float(c - p) for c, p in zip(centre, peak[:2])], "scale": float((sc1 + sc2) / 2.0), "scales": [float(sc1), float(sc2)], "turn": float(flip * turn), "pull": float(pull), "inward": float(inward)})
    n = set_count * set_size
    pool = {"shape": np.array(shapes), "color": np.array(colors), "moisture": np.full(n, float(params.moisture_when_fixed)), "value": np.array(values),
            "peak": peak, "frame": frame}
    return pool, np.arange(n).reshape(set_count, set_size), roles, meta


def plus_summary(sidecar):
    """What a plus pool reveals to someone who sees only the bushes: the distance from the mean of the sets' centres to the true peak (in the peak bump's mean spread), the
    mean spread of the centres, the share of the peak the centre and arm bushes pay, and how often the centre is the best bush of its set."""
    peak = np.array(sidecar["peak"][:2])
    spread = math.sqrt(sidecar["frame"][1] * sidecar["frame"][2])
    centres = np.array([m["centre"] for m in sidecar["plus"]])
    by_role = {r: [] for r in PLUS_ROLES}
    best = 0
    for st in sidecar["sets"]:
        top = max(st["bushes"], key=lambda b: b["value"])
        best += top["role"] == "centre"
        for b in st["bushes"]:
            by_role[b["role"]].append(b["value"] / sidecar["peak"][2])
    return {"meanCentreToPeak": float(np.linalg.norm(centres.mean(axis=0) - peak) / spread),
            "centreScatter": float(np.sqrt(((centres - centres.mean(axis=0)) ** 2).sum(axis=1).mean()) / spread),
            "centreIsBest": best / len(sidecar["sets"]),
            "fitted": float(np.mean([m["scale"] < 1.0 or m["turn"] != 0.0 for m in sidecar["plus"]])), "meanScale": float(np.mean([m["scale"] for m in sidecar["plus"]])),
            "shareOfPeak": {r: float(np.mean(v)) for r, v in by_role.items()}, "minShareOfPeak": float(min(min(v) for v in by_role.values()))}



def arrange_slots(count, set_size, rng):
    """A slot permutation for each set (the bush at rank j goes to slot perm[j]); the best bush of one set does not take the slot another set's did while slots remain."""
    perms, best_slots = [], set()
    for _ in range(count):
        for _try in range(200):
            perm = rng.permutation(set_size)
            if perm[set_size - 1] not in best_slots or len(best_slots) >= set_size:
                break
        best_slots.add(int(perm[set_size - 1]))
        perms.append(perm)
    return perms


# --------------------------------------------------------------------------------------------------
# The dense design: five 5x5 grids, one per selection (scripts/dense_grid.py plans them), picked best 5 of 25
# --------------------------------------------------------------------------------------------------

GRID_N = 5
NEW_FIELDS = ("selection_design", "selection_times", "selection_max_wait", "selection_picks", "selection_grid_spacing", "selection_grid_distance", "selection_stage_tilt", "selection_grid_preset",
              "selection_top_k_points", "selection_paid")      # fields an asset may not hold yet (world.py's loader would refuse them as overrides)
TOPK_PRESETS = ("even", "balanced", "diverse")


def grid_slot_position(a, b, spacing, distance, flip_shape=False, flip_color=False):
    """The stage position (x to the right, z ahead, the player at the origin) of grid slot (a, b): the shape index a runs left to right, the colour index b near to far, the grid's middle `distance` ahead.
    `flip_shape` / `flip_color` reverse that axis (shape right to left, colour far to near): the grid's orientation, see `grid_orientations`."""
    a = GRID_N - 1 - a if flip_shape else a
    b = GRID_N - 1 - b if flip_color else b
    return np.array([(a - (GRID_N - 1) / 2.0) * spacing, distance + (b - (GRID_N - 1) / 2.0) * spacing])


def grid_orientations(count, seed):
    """The orientation of each of `count` grids, (flip_shape, flip_color): the four orientations in a seeded random order, again in a new random order when there are more grids than four (so the
    best region of a grid does not always lie in the same part of the stage, and a participant must read the bushes, not the places)."""
    rng = np.random.default_rng(int(seed))
    order = []
    while len(order) < count:
        order += [(bool(o & 1), bool(o >> 1)) for o in rng.permutation(4)]
    return order[:count]


def dense_sets(params, count=None):
    """The `count` (default one per selectionTimes entry, else 5) grids of the session's plan (`dense_grid.plan_session`), each as 25 bushes in the slot order a * 5 + b:
    their (shape, colour) cells clipped to the unit square. Returns (list of per-set dicts with 'cells', 'plan'): the plan record has the peak index, the spacing, the ratio and the count inside."""
    import dense_grid
    times = list(getattr(params, "selection_times", None) or [])
    count = int(count or len(times) or 5)
    preset = str(getattr(params, "selection_grid_preset", "") or "balanced")
    if preset not in TOPK_PRESETS:
        raise ValueError(f"unknown selectionGridPreset {preset!r}: {TOPK_PRESETS}")
    world, last_ratio = dense_grid.load_world(params.session_name)
    plan_count = max(count, GRID_N)                                  # the planner is built for five selections: fewer (the tutorial's one) are the first grids of a five-selection plan
    return dense_grid.plan_session(params.session_name, world, last_ratio, dense_grid.PRESETS[preset], plan_count)[:count]


def top_k_values(values, k):
    return sorted((float(v) for v in values), reverse=True)[:int(k)]


def top_k_score(picked_values, all_values, k=GRID_N, scale=100.0):
    """The score of a dense selection, 0 to `scale`: the picked values' sum against the grid's best k, from the expected sum of k random bushes (so a random pick scores about 0 and the best k `scale`).
    `picked_values` may be fewer than k (a selection that timed out). Mirrored by SelectionSets.TopKScore."""
    best = sum(top_k_values(all_values, k))
    base = float(k) * float(np.mean(all_values))
    if best - base <= 1e-9:
        return 0.0
    got = sum(float(v) for v in list(picked_values)[:int(k)])
    return float(scale) * min(max((got - base) / (best - base), 0.0), 1.0)


def top_k_hits(picked_ids, values_by_id, k=GRID_N):
    """How many of the picked bushes are among the grid's true best k."""
    best = sorted(values_by_id, key=lambda i: -values_by_id[i])[:int(k)]
    return sum(1 for i in picked_ids if i in best)


def paid_set_index(seed, count):
    """The selection (0-based) that pays when only one does (selectionPaid 'one'): drawn from the world seed. Mirrored by SelectionSets.PaidSetIndex."""
    return int((((int(seed) * 2654435761) % (1 << 64)) >> 8) % max(int(count), 1))


# --------------------------------------------------------------------------------------------------
# The file
# --------------------------------------------------------------------------------------------------

def dense_pool(params, seed, rng_fruit):
    """The pool file of the dense design: set s is the grid planned for selection s (25 bushes, ids s * 25 + slot), the positions the same lattice in every set but for its orientation (`grid_orientations`). Returns (sidecar, params)."""
    grids = dense_sets(params)
    count = len(grids)
    spacing, distance = float(getattr(params, "selection_grid_spacing", 7.0)), float(getattr(params, "selection_grid_distance", 18.0))
    picks = int(getattr(params, "selection_picks", GRID_N) or GRID_N)
    moisture = float(params.moisture_when_fixed)
    size = GRID_N * GRID_N
    n = count * size
    pos, shape, color, mois, radius, value = np.zeros((n, 2)), np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    sets = []
    orientations = grid_orientations(count, seed)
    for s, g in enumerate(grids):
        flip_shape, flip_color = orientations[s]
        cells = np.clip(np.asarray(g["cells"], dtype=float), 0.0, 1.0)
        vals = np.asarray(REWARDS[stage_names(params)[2]](params.reward_function, cells[:, 0], cells[:, 1]), dtype=float)
        bushes = []
        for slot in range(size):
            a, b = divmod(slot, GRID_N)
            i = s * size + slot
            shape[i], color[i], mois[i], value[i] = cells[slot, 0], cells[slot, 1], moisture, vals[slot]
            radius[i] = float(canopy_radius(params, shape[i]))
            pos[i] = grid_slot_position(a, b, spacing, distance, flip_shape, flip_color)
            bushes.append({"id": i, "slot": slot, "bearing": 0.0, "shape": float(shape[i]), "color": float(color[i]), "moisture": float(mois[i]), "value": float(value[i])})
        by_value = sorted(bushes, key=lambda x: -x["value"])
        plan = {"peakIndex": list(map(int, g["index"])), "spacing": float(g["s"]), "ratio": float(g["ratio"]), "inside": int(g["inside"]), "flipShape": flip_shape, "flipColor": flip_color,
                "best": top_k_values(vals, picks), "randomExpected": float(picks * vals.mean())}
        sets.append({"index": s, "start": [0.0, 0.0], "yaw": 0.0, "bushes": bushes, "trueOrder": [b["id"] for b in by_value], "minGap": None, "valueSpan": float(by_value[0]["value"] - by_value[-1]["value"]), "grid": plan})
    fruit_count = int(params.fruit_count)
    noise = rng_fruit.standard_normal((n, fruit_count)) * float(params.reward_std)
    fruit_reward = np.maximum(0, np.rint(value[:, None] + noise)).astype(np.int32)
    sidecar = {
        "format": "ranking-pool", "design": "dense", "layout": "grid", "gridN": GRID_N, "pickCount": picks, "preset": str(getattr(params, "selection_grid_preset", "") or "balanced"),
        "session": params.session_name, "seed": seed, "n": count, "setSize": size, "arcSpan": 0.0, "bushDistance": distance, "gridSpacing": spacing, "groundMoisture": moisture,
        "tieTolerance": TIE_TOLERANCE, "minGap": 0.0, "margins": None, "fruitCount": fruit_count, "treePos": pos.reshape(-1).tolist(), "shape": shape.tolist(), "color": color.tolist(),
        "moisture": mois.tolist(), "canopyRadius": radius.tolist(), "value": value.tolist(), "fruitRewards": fruit_reward.reshape(-1).astype(int).tolist(), "sets": sets,
    }
    return sidecar, params


def generate_pool(name, pool_size=POOL_SIZE, steps=SEARCH_STEPS, **overrides):
    """The pool of the selection sets a session plays in place after its patch switches: `selectionPoolSets` sets of `selectionSetSize` bushes of the session's own
    reward function, chosen jointly, used in order by the game, on an arc of `selectionArcSpan` degrees at `selectionDistance`, the tie gap `selectionTieGap`.
    Positions (`treePos`) are relative to the player standing at the origin and facing +z; the game turns and moves them to the player's pose and puts the
    bush on the ground there, so `moisture` is only a recorded value (moisture never pays). Returns (sidecar, params)."""
    new_fields = {k: overrides.pop(k) for k in list(overrides) if k in NEW_FIELDS or k.startswith("selection_plus_")}   # (fields an asset may not hold yet: world.py's loader would refuse them)
    params = load_session(name, **overrides)
    for key, value in new_fields.items():
        setattr(params, key, value)
    set_size, set_count = int(params.selection_set_size), int(params.selection_pool_sets)
    arc_span, distance, gap = float(params.selection_arc_span), float(params.selection_distance), float(params.selection_tie_gap)
    moisture = float(params.moisture_when_fixed)
    design = str(getattr(params, "selection_design", "ladder") or "ladder")
    margins = None if design == "dense" else check_arc(params, set_size, arc_span, distance)

    seed = int(params.world_seed)
    rng_pool, rng_sets, rng_slots, rng_fruit = (np.random.default_rng(c) for c in np.random.SeedSequence([seed, 914]).spawn(4))
    if design == "dense":
        return dense_pool(params, seed, rng_fruit)
    if design == "plus":
        pool, chosen, roles, plus_meta = plus_sets(params, set_count, set_size, gap, rng_sets)
    elif design == "ladder":
        pool = candidate_pool(params, rng_pool, pool_size, moisture)
        chosen = choose_sets(params, pool, set_count, set_size, gap, rng_sets, steps=steps)
        roles = plus_meta = None
    else:
        raise ValueError(f"unknown selectionDesign {design!r}: 'ladder', 'plus' or 'dense'")
    bearings = slot_bearings(set_size, arc_span)
    perms = arrange_slots(set_count, set_size, rng_slots)

    n = set_count * set_size
    pos, shape, color, mois, radius, value = np.zeros((n, 2)), np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    sets = []
    for s in range(set_count):
        bushes = []
        for j in range(set_size):                                        # rank j from the lowest true value
            c = chosen[s, j]
            i = s * set_size + int(perms[s][j])                          # bush ids are laid out by slot within the set
            slot = int(perms[s][j])
            r = float(canopy_radius(params, pool["shape"][c]))
            shape[i], color[i], mois[i], radius[i], value[i] = pool["shape"][c], pool["color"][c], pool["moisture"][c], r, pool["value"][c]
            pos[i] = slot_position(distance, bearings[slot], r)
            bushes.append({"id": i, "slot": slot, "bearing": float(bearings[slot]), "shape": float(shape[i]), "color": float(color[i]),
                           "moisture": float(mois[i]), "value": float(value[i])})
            if roles is not None:
                bushes[-1]["role"] = roles[s][j]
        bushes.sort(key=lambda b: b["slot"])
        by_value = sorted(bushes, key=lambda b: -b["value"])
        gaps = np.diff(sorted(b["value"] for b in bushes))
        sets.append({"index": s, "start": [0.0, 0.0], "yaw": 0.0, "bushes": bushes, "trueOrder": [b["id"] for b in by_value],
                     "minGap": float(gaps.min()) if len(gaps) else None, "valueSpan": float(by_value[0]["value"] - by_value[-1]["value"])})

    fruit_count = int(params.fruit_count)
    noise = rng_fruit.standard_normal((n, fruit_count)) * float(params.reward_std)
    fruit_reward = np.maximum(0, np.rint(value[:, None] + noise)).astype(np.int32)
    sidecar = {
        "format": "ranking-pool", "session": params.session_name, "seed": seed, "n": set_count, "setSize": set_size,
        "arcSpan": arc_span, "bushDistance": distance, "groundMoisture": moisture, "tieTolerance": TIE_TOLERANCE, "minGap": gap, "margins": margins,
        "fruitCount": fruit_count, "treePos": pos.reshape(-1).tolist(), "shape": shape.tolist(), "color": color.tolist(), "moisture": mois.tolist(),
        "canopyRadius": radius.tolist(), "value": value.tolist(), "fruitRewards": fruit_reward.reshape(-1).astype(int).tolist(), "sets": sets,
    }
    if design == "plus":
        sidecar.update({"design": "plus", "peak": list(pool["peak"]), "frame": list(pool["frame"]), "plus": plus_meta})
        sidecar["summary"] = plus_summary(sidecar)
    return sidecar, params


def pool_path(name, seed, out_dir=None):
    path = unity_world_path(name, seed, out_dir)
    return Path(str(path)[: -len(".world")] + ".ranking.json")


def export_pool(name, out_dir=None):
    """Generate the pool of the session `name` and write its file for Unity; returns (path, sidecar)."""
    sidecar, _ = generate_pool(name)
    path = pool_path(name, sidecar["seed"], out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sidecar, f, indent=1)
    return path, sidecar


# --------------------------------------------------------------------------------------------------
# Scores of a selection, from the raw picks (computed at analysis time; none is part of a run)
# --------------------------------------------------------------------------------------------------

def pair_scores(picked_values, all_values, tol=TIE_TOLERANCE):
    """(correct, total): the payout rule (`SelectionSets.ScorePairs`). `total` is the number of non-tied pairs of the whole set (`all_values`, its true values); a pair is
    correct only when both bushes were picked and the one picked first is worth more, so a pair with an unpicked bush (a timed-out set) is never correct.
    `picked_values` are the true values in pick order (best first). Pairs whose values differ by less than `tol` are ties and are not counted."""
    values = np.asarray(all_values, dtype=float)
    gap = np.abs(values[:, None] - values[None, :])[np.triu_indices(len(values), 1)]
    total = int((gap >= tol).sum())
    picked = np.asarray(picked_values, dtype=float)
    correct = sum(1 for i in range(len(picked)) for j in range(i + 1, len(picked)) if picked[i] - picked[j] >= tol)
    return correct, total


POINTS_MODES = ("pair", "pair_mean_value")       # how a correct pair is paid (`SessionConfig.selectionPointsMode`; "" is "pair")


def pair_weight(mode, value_a, value_b):
    """What a correct pair is worth, in units of the bonus, in a points mode: `pair` one; `pair_mean_value` the mean of the pair's two true values (a miss among the best bushes costs more than among the poor ones)."""
    if mode in ("", "pair"):
        return 1.0
    if mode == "pair_mean_value":
        return (float(value_a) + float(value_b)) / 2.0
    raise ValueError(f"unknown selection points mode {mode!r} (one of {POINTS_MODES})")


def selections_to_points(picked_values, all_values, bonus, mode="pair", tol=TIE_TOLERANCE):
    """(points, correct, total) of one ranked set: the payout (`SelectionSets.ScorePairs` and `SelectionBreak.FinishSet` are the same rule). Which pairs are correct is `pair_scores`; each pays `bonus` times its
    `pair_weight` in `mode`, so `pair` pays `bonus` per correct pair. A new way of paying is a new mode here and in `SelectionSets.PairWeight`, nothing else. Arguments as `pair_scores`."""
    correct, total = pair_scores(picked_values, all_values, tol)
    picked = np.asarray(picked_values, dtype=float)
    weight = sum(pair_weight(mode, picked[i], picked[j]) for i in range(len(picked)) for j in range(i + 1, len(picked)) if picked[i] - picked[j] >= tol)
    return float(bonus) * weight, correct, total


def implied_pair_scores(picked_values, all_values, tol=TIE_TOLERANCE):
    """(correct, total) over the pairs the order itself implies (for analysis, not the payout): every picked bush is above every bush not picked, and the picked ones
    are in the order picked; the pairs among unpicked bushes are not counted. Same arguments as `pair_scores`."""
    picked = np.asarray(picked_values, dtype=float)
    unpicked = list(np.asarray(all_values, dtype=float))
    for v in picked:                                    # remove the picked values from the multiset of all values
        unpicked.pop(int(np.argmin(np.abs(np.asarray(unpicked) - v))))
    unpicked = np.asarray(unpicked, dtype=float)
    correct = total = 0
    for i in range(len(picked)):
        higher = np.concatenate([picked[i + 1:], unpicked])         # what bush i was ranked above
        gap = picked[i] - higher
        counted = np.abs(gap) >= tol
        total += int(counted.sum())
        correct += int((gap[counted] > 0).sum())
    return correct, total


def pair_accuracy(picked_values, all_values, tol=TIE_TOLERANCE):
    correct, total = implied_pair_scores(picked_values, all_values, tol)
    return correct / total if total else float("nan")


def kendall_tau(picked_values, all_values, tol=TIE_TOLERANCE):
    """Concordant minus discordant over the non-tied implied pairs, divided by their number (= 2 * pair accuracy - 1; 1 a perfect order, -1 reversed, 0 chance)."""
    accuracy = pair_accuracy(picked_values, all_values, tol)
    return 2.0 * accuracy - 1.0 if accuracy == accuracy else float("nan")


def first_pick_regret(picked_values, all_values):
    """True value of the best bush of the set minus that of the first one picked (0 when it was the best; the whole best value if nothing was picked)."""
    best = float(np.max(all_values))
    return best - float(picked_values[0]) if len(picked_values) else best


def rank_gain(picked_values, all_values):
    """Discounted gain of the order, 1 = the best possible order, 0 = the worst: sum of value / log2(rank + 1) over the picks, between the worst and the best
    orders of the whole set (values shifted so the lowest is zero; a set with no spread in value scores nan)."""
    all_values = np.sort(np.asarray(all_values, dtype=float))[::-1]
    shifted = all_values - all_values.min()
    discount = 1.0 / np.log2(np.arange(len(all_values)) + 2.0)
    best, worst = float((shifted * discount).sum()), float((shifted[::-1] * discount).sum())
    if best - worst <= 0.0:
        return float("nan")
    picked = np.asarray(picked_values, dtype=float) - all_values.min()
    got = float((picked * discount[:len(picked)]).sum())
    return (got - worst) / (best - worst)


def main():
    ap = argparse.ArgumentParser(description="Generate the selection pools of sessions for Unity.")
    ap.add_argument("command", choices=["pool"])
    ap.add_argument("sessions", nargs="+", help="session names, e.g. FOR_S1")
    ap.add_argument("--out", default=None, help="output directory (default Assets/StreamingAssets/Experiments/<code>)")
    args = ap.parse_args()
    for name in args.sessions:
        path, sidecar = export_pool(name, args.out)
        print(f"{path.name}: {sidecar['n']} sets of {sidecar['setSize']}, value spans {[round(t['valueSpan'], 2) for t in sidecar['sets']]}, margins {sidecar['margins']}")


if __name__ == "__main__":
    main()
