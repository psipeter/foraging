"""Ranking sets: k bushes in view at once, harvested in best-to-worst order, played in place during a session's ranking breaks.

The participant (or agent) stands still and sees every bush of the set on an arc in front of them, all with the same distance from the player to the
canopy's edge. Harvesting needs no walking (the game ignores the harvest range here and takes the bush the crosshair is on), so no bush hides another,
and the rank of a bush is the order in which it was harvested. A bush stays, spent, after it is harvested. Outcomes are never shown.

A session's sets are one pool file (`<session>_seed<N>.ranking.json`, `ranking.py pool <session>`), chosen together so that, across them, the true values fill
the range evenly and the bushes fill the feature plane; within a set the values are a ladder with every neighbouring gap at least the tie gap
(`rankingTieGap`). The geometry of a set is fixed by the arc (`rankingDistance`, `rankingArcSpan`, `rankingSetSize`), positions are relative to the player
(standing at the origin, facing +z), and the game turns and moves them to the player's pose.

The module holds the generator (`generate_pool`), the geometry checks (`check_arc`) and the scores a ranking can be given from its picks
(`pair_scores`, `kendall_tau`, `first_pick_regret`, `rank_gain`: all are computed from the raw order and the true values, so the metric
can be chosen at analysis time). Scoring is not part of a run (see CLAUDE.md, "Results database").
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from world import REWARDS, load_session, session_features, stage_names, unity_world_path

TIE_TOLERANCE = 0.05        # a pair whose true values differ by less than this is a tie: it is not scored
SET_SIZE = 5                # bushes per set
POOL_SETS = 12              # sets in a session's pool (the breaks play them in order)
BUSH_DISTANCE = 16.0        # player to the nearest point of each canopy (world units); five canopies of radius 3 need at least about 14
ARC_SPAN = 84.0             # degrees from the leftmost to the rightmost bush centre
MIN_ASPECT = 4.0 / 3.0      # the narrowest window the arc must fit in (the camera's vertical field of view is fixed)
FOV_MARGIN = 1.0            # degrees between the outermost bush's centre and the edge of the view at MIN_ASPECT: at least half of each bush is on screen without turning
ANGLE_MARGIN = 2.0          # degrees between neighbouring canopies at the widest radius
POOL_SIZE = 8000            # (shape, colour) candidates the sets are chosen from
SEARCH_STEPS = 30000        # replacements tried when choosing the sets
VALUE_LOW_QUANTILE = 0.02   # the ladder of values spans these quantiles of the candidates' values
VALUE_HIGH_QUANTILE = 0.995
REPULSION = 0.12            # spread (feature units) of the repulsion that spreads the chosen bushes over the feature plane
SAME_SET_REPULSION = 2.0    # bushes of one set repel this much more than bushes of different sets (they must look different)
FEATURE_AXES = ("shape", "color")      # moisture is the player's ground value in a set: it is no feature of a ranking


def canopy_radius(params, shape):
    """The canopy's horizontal radius at a shape value (Tree.ApplyAttributes)."""
    lo, hi = params.shape_range
    t = np.clip((np.asarray(shape) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    w_lo, w_hi = params.canopy_width_range
    return (w_hi + (w_lo - w_hi) * t) * 0.5


def option(params, name, default):
    """A generator option: the SessionConfig field of that name if the asset has it, else the default (the fields are added with the game's side)."""
    value = getattr(params, name, None)
    return default if value is None else value


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
    value = np.asarray(REWARDS[stage_names(params)[2]](params.reward_function, shape, color, mois), dtype=float)
    return {"shape": shape, "color": color, "moisture": mois, "value": value}


def value_ladder(values, set_count, set_size):
    """Target true values of the sets: set_count * set_size levels evenly spread between two quantiles of the candidates' values, dealt round-robin so
    every set spans the whole range (set s takes levels s, s + set_count, ...) and, together, the sets fill it evenly. Returns (targets[set, rank], step)."""
    total = set_count * set_size
    lo, hi = (float(np.quantile(values, q)) for q in (VALUE_LOW_QUANTILE, VALUE_HIGH_QUANTILE))
    levels = np.linspace(lo, hi, total)
    step = (hi - lo) / max(total - 1, 1)
    return levels.reshape(set_size, set_count).T, step


def choose_sets(params, pool, set_count, set_size, min_gap, rng, taken=None, steps=SEARCH_STEPS):
    """Indices into the pool of the bushes of each set, shape (set_count, set_size), the rows ordered from the lowest true value to the highest.

    The loss is the squared distance of each bush's value from its ladder level (in ladder steps), a large penalty for each neighbouring pair of a set closer
    than `min_gap`, and a repulsion in the (shape, colour) plane (stronger within a set) that spreads the bushes over it; `taken` are (shape, colour) points
    of other sets, which the new bushes also keep away from. The search replaces one bush at a time by a candidate near its level."""
    targets, step = value_ladder(pool["value"], set_count, set_size)
    if step * set_count < min_gap:
        raise ValueError(f"the values of the candidates span too little for {set_count} sets of {set_size}: neighbouring bushes of a set would differ by "
                         f"{step * set_count:.3f} < the tie gap {min_gap} (lower the gap, lower the set size or count, or widen the reward)")
    axes = [a for a in FEATURE_AXES if bool(getattr(params, f"{a}_varies"))] or list(FEATURE_AXES)
    plane = np.column_stack([pool[a] for a in axes])
    others = np.zeros((0, plane.shape[1])) if taken is None or len(taken) == 0 else np.asarray(taken, dtype=float).reshape(len(taken), -1)[:, [FEATURE_AXES.index(a) for a in axes]]
    values = pool["value"]
    n = len(values)
    near = [np.flatnonzero(np.abs(values - t) <= step) for t in targets.reshape(-1)]
    near = [c if len(c) else np.array([int(np.argmin(np.abs(values - t)))]) for c, t in zip(near, targets.reshape(-1))]
    flat_targets = targets.reshape(-1)
    owner = np.repeat(np.arange(set_count), set_size)               # flat position p = set * set_size + rank holds the bush for targets[set, rank]
    chosen = np.array([c[rng.integers(0, len(c))] for c in near])
    sigma2 = REPULSION ** 2

    def repulsion_of(index, cand):
        """Repulsion felt by bush `cand` placed at flat position `index` from every other chosen bush and the taken points."""
        d2 = ((plane[chosen] - plane[cand]) ** 2).sum(axis=1)
        weight = np.where(owner == owner[index], SAME_SET_REPULSION, 1.0)
        mask = np.arange(len(chosen)) != index
        total = float((weight * np.exp(-d2 / (2.0 * sigma2)))[mask].sum())
        if len(others):
            total += float(np.exp(-((others - plane[cand]) ** 2).sum(axis=1) / (2.0 * sigma2)).sum())
        return total

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
# The file
# --------------------------------------------------------------------------------------------------

def _significant(reward_function):
    """The reward function without its empty lists (an asset Unity saved after the RewardFunction gained a list field carries the field, an older one does not)."""
    return {k: v for k, v in reward_function.items() if v not in ([], None)}


def _build_sets(params, set_size, set_count, arc_span, distance, gap, moisture, taken, pool_size, steps, head):
    """The sidecar dict of `set_count` sets for the session `params` (its reward function, features and fruit rewards), the keys of `head` first."""
    margins = check_arc(params, set_size, arc_span, distance)

    seed = int(params.world_seed)
    rng_pool, rng_sets, rng_slots, rng_fruit = (np.random.default_rng(c) for c in np.random.SeedSequence([seed, 914]).spawn(4))
    pool = candidate_pool(params, rng_pool, pool_size, moisture)
    chosen = choose_sets(params, pool, set_count, set_size, gap, rng_sets, taken=taken, steps=steps)
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
        bushes.sort(key=lambda b: b["slot"])
        by_value = sorted(bushes, key=lambda b: -b["value"])
        gaps = np.diff(sorted(b["value"] for b in bushes))
        sets.append({"index": s, "start": [0.0, 0.0], "yaw": 0.0, "bushes": bushes, "trueOrder": [b["id"] for b in by_value],
                     "minGap": float(gaps.min()) if len(gaps) else None, "valueSpan": float(by_value[0]["value"] - by_value[-1]["value"])})

    fruit_count = int(params.fruit_count)
    noise = rng_fruit.standard_normal((n, fruit_count)) * float(params.reward_std)
    fruit_reward = np.maximum(0, np.rint(value[:, None] + noise)).astype(np.int32)
    sidecar = {
        **head, "seed": seed, "n": set_count, "setSize": set_size,
        "arcSpan": arc_span, "bushDistance": distance, "groundMoisture": moisture, "tieTolerance": TIE_TOLERANCE, "minGap": gap, "margins": margins,
        "fruitCount": fruit_count, "treePos": pos.reshape(-1).tolist(), "shape": shape.tolist(), "color": color.tolist(), "moisture": mois.tolist(),
        "canopyRadius": radius.tolist(), "value": value.tolist(), "fruitRewards": fruit_reward.reshape(-1).astype(int).tolist(), "sets": sets,
    }
    return sidecar


def generate_pool(name, set_size=None, set_count=None, arc_span=None, distance=None, min_gap=None, pool_size=POOL_SIZE, steps=SEARCH_STEPS, **overrides):
    """The pool of the ranking sets a session plays in place after its patch switches (`SessionConfig.ranking*`): `set_count` sets (default `rankingPoolSets`) of the
    session's own reward function, chosen jointly, used in order by the game. The arc is `ranking_set_size`, `ranking_arc_span`, `ranking_distance`, the tie gap
    `ranking_tie_gap`. Positions (`treePos`, the first set's slots) are relative to the player standing at the origin and facing +z; the game turns and moves them
    to the player's pose and puts the bush on the ground there, so `moisture` is only used to evaluate the values."""
    params = load_session(name, **overrides)
    if session_features(params)["moisture"]["rewarded"]:
        raise ValueError(f"{name}: moisture pays, but a ranking set has no moisture feature; reward shape and colour only")
    set_size = int(option(params, "ranking_set_size", SET_SIZE) if set_size is None else set_size)
    set_count = int(option(params, "ranking_pool_sets", POOL_SETS) if set_count is None else set_count)
    arc_span = float(option(params, "ranking_arc_span", ARC_SPAN) if arc_span is None else arc_span)
    distance = float(option(params, "ranking_distance", BUSH_DISTANCE) if distance is None else distance)
    gap = float(option(params, "ranking_tie_gap", 0.25) if min_gap is None else min_gap)
    moisture = float(params.moisture_when_fixed)
    return _build_sets(params, set_size, set_count, arc_span, distance, gap, moisture, None, pool_size, steps, {"format": "ranking-pool", "session": params.session_name}), params


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
# Scores of a ranking, from the raw picks (computed at analysis time; none is part of a run)
# --------------------------------------------------------------------------------------------------

def pair_scores(picked_values, all_values, tol=TIE_TOLERANCE):
    """(correct, total) over the pairs a ranking implies: every picked bush is above every bush not picked (a timed-out set), and the picked ones are
    in the order picked. `picked_values` are the true values in pick order (best first), `all_values` those of the whole set. Pairs whose values
    differ by less than `tol` are ties and are not counted. A pair is correct when the bush ranked higher is worth more."""
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
    correct, total = pair_scores(picked_values, all_values, tol)
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
    ap = argparse.ArgumentParser(description="Generate the ranking pools of sessions for Unity.")
    ap.add_argument("command", choices=["pool"])
    ap.add_argument("sessions", nargs="+", help="session names, e.g. FOR_S1")
    ap.add_argument("--out", default=None, help="output directory (default Assets/StreamingAssets/Experiments/<code>)")
    args = ap.parse_args()
    for name in args.sessions:
        path, sidecar = export_pool(name, args.out)
        print(f"{path.name}: {sidecar['n']} sets of {sidecar['setSize']}, value spans {[round(t['valueSpan'], 2) for t in sidecar['sets']]}, margins {sidecar['margins']}")


if __name__ == "__main__":
    main()
