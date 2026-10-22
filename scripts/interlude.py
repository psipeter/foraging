"""Interlude design generator: the forced-choice block run after each session.

An Interlude looks like its session: the same world (terrain, mountains, sun), but only two bushes are present.
The player turns toward the one they think pays more, walks to it and harvests it. Outcomes are never shown. This
module is the source of truth for the stimulus set and bush placement (Unity only plays the file back), mirroring
how world.py works for the main sessions. There is no Interlude-specific terrain: a bush's moisture and elevation
come from the session's own terrain at the position it stands on, exactly as in the main task, so the design
searches that terrain for places where the two bush positions have the moisture a trial needs.

Inputs are two SessionConfig assets, read through world.load_session:
  <name>              an Interlude asset (isInterlude, interludeFor, interludeTrialCount, interludeBushDistance /
                      Bearing, worldSeed = the probed session's seed, ...). Its reward function and every terrain
                      parameter are copies of the session it probes (checked here).
  <interludeFor>      the session asset it probes; its world file (<session>_seed<N>.world) supplies the terrain.

Output (Assets/StreamingAssets/Worlds/<name>_seed<N>.interlude.json): the bush table for all trials (ids 2i and 2i+1 =
left and right of trial i) plus the per-trial metadata: type, varied feature, spawn point and heading, both bushes'
attributes and true reward, and the correct side. Unity loads the terrain from the session's world file and replaces
its bush table with this one.

Geometry. The two bushes must be equal in the terms the game's harvest rules use, which refer to the canopy edge: the
distance from the spawn point to each canopy edge is the same (`interludeBushDistance`), and so is the bearing of each
canopy's inner edge from the heading (`interludeBushBearing`, on opposite sides), so the heading bisects the pair and
turning and walking to either is the same. A canopy's radius depends on its shape, so each bush's centre is placed from
its own radius; the two centres are therefore not exactly symmetric about the heading when the radii differ.

Stimulus types (see DECISIONS "Interlude"):
  contrast       the two bushes differ in one feature only (others equal): isolates a feature's effect
  graded         two bushes whose true reward differs by a chosen amount: a psychometric curve
  extrapolation  bushes built from extreme values of the relevant features, as trade-offs when several features
                 matter: tests the rule and the relative weights away from typical bushes
Moisture cannot be chosen freely: it is whatever the terrain has at the two final positions, so the design picks a
placement with the moisture relation a trial needs ("same", one plateau level apart, two or more levels apart), then
chooses shape and colour, and checks the relation again at the final positions. The practice Interlude has only easy
contrasts on the relevant feature and one large graded pair.

Usage:
    python scripts/interlude.py P_Interlude S1_Interlude S2_Interlude S3_Interlude S4_Interlude
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from world import (PROJECT_ROOT, _basis, bush_value, check_values, generate_world, load_session,
                   unity_world_path)

FEATURES = ["shape", "color", "moisture"]
TIE_TOLERANCE = 0.05          # |R_left - R_right| below this: either answer is "correct"

# Placement search (module constants: they shape the stimulus set, not the game)
POOL_SAMPLES = 500_000        # random (spawn, heading) placements searched for the moisture relations below
SAME_TOL = 0.02               # |moisture difference| for "the same moisture"
ONE_LEVEL = (0.20, 0.34)      # |moisture difference| for "one plateau level apart" (levels are ~0.27 apart)
TWO_LEVELS_MIN = 0.45         # ... and for "two or more levels apart"
MIN_SITE_SPACING = 80.0       # trials' spawn points are at least this far apart (relaxed if the pool is thin)
MAX_SPAWN_SLOPE = 0.6         # rise/run at the spawn point
LOS_SAMPLES = 14              # terrain samples checked along the line of sight to each bush
CANOPY_AIM_HEIGHT = 1.0       # line of sight is checked to a point this far above the ground at each bush (near its base)
PROFILE_SAMPLES = 30          # terrain samples along the path from the spawn point to each bush
HUMP_TOLERANCE = 0.5          # a rise then a fall of more than this (world units) between the spawn and a bush is a hump
MAX_ATTEMPTS = 300            # placements tried per trial before giving up
GRADED_TARGETS = [0.15, 1.2]  # range of |R difference| in units of the spread of R across random bushes (geometric steps)
PRACTICE_GRADED_TARGET = 1.5


# --------------------------------------------------------------------------------------------------
# Placement geometry
# --------------------------------------------------------------------------------------------------

def canopy_radius(params, shape):
    lo, hi = params.shape_range
    t = np.clip((np.asarray(shape) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    w_lo, w_hi = params.canopy_width_range
    return (w_hi + (w_lo - w_hi) * t) * 0.5


def bush_offsets(params, radius):
    """(forward, lateral) distance of a bush's centre from the spawn point in the heading frame, for a canopy of this
    radius: its edge is `interludeBushDistance` from the spawn and its inner edge is `interludeBushBearing` degrees off
    the heading (centre bearing = that + the canopy's angular radius). Works on arrays."""
    edge = float(params.interlude_bush_distance)
    bearing = math.radians(float(params.interlude_bush_bearing))
    radius = np.asarray(radius, dtype=float)
    d = edge + radius
    theta = bearing + np.arcsin(np.minimum(radius / d, 1.0))
    return d * np.cos(theta), d * np.sin(theta)


def bush_position(params, spawn, yaw_radians, side, radius):
    """Centre of the left or right bush for a spawn point, heading (0 faces +z, as the game's camera yaw) and radius."""
    fwd, lat = bush_offsets(params, radius)
    f = np.array([math.sin(yaw_radians), math.cos(yaw_radians)])
    r = np.array([math.cos(yaw_radians), -math.sin(yaw_radians)])
    sign = -1.0 if side == "left" else 1.0
    return np.asarray(spawn, dtype=float) + float(fwd) * f + sign * float(lat) * r


def nominal_radius(params):
    w_lo, w_hi = params.canopy_width_range
    return (w_lo + w_hi) / 4.0         # mean canopy radius over the shape range


def check_geometry(params):
    """Raise if a bush could be harvested without turning toward it (the widest canopy would be selected by default):
    its centre must be at least the harvest range + its radius to the side of the heading."""
    gap = float(params.harvest_range_gap_base)
    lo, hi = float(min(params.canopy_width_range)) * 0.5, float(max(params.canopy_width_range)) * 0.5
    for r in (lo, hi):
        _, lat = bush_offsets(params, r)
        if float(lat) < gap + r:
            raise ValueError(f"interludeBushBearing {params.interlude_bush_bearing}: a canopy of radius {r} would stand "
                             f"{float(lat):.1f} to the side, closer than harvest range {gap} + {r}; it could be harvested "
                             f"while walking straight ahead")


def has_hump(terrain, spawn, pos, params=None):
    """True if the ground rises and then falls between `spawn` and `pos` (a hill in the way). Only a rise followed by a
    fall hides a bush; a steady climb or descent, or a dip, does not count."""
    ts = np.linspace(0.0, 1.0, PROFILE_SAMPLES)
    e = np.asarray(terrain.elevation(spawn[0] + ts * (pos[0] - spawn[0]), spawn[1] + ts * (pos[1] - spawn[1])), dtype=float)
    k = int(np.argmax(e))
    return 0 < k < len(e) - 1 and e[k] - e[0] > HUMP_TOLERANCE and e[k] - e[-1] > HUMP_TOLERANCE


def make_pool(params, terrain, rng, n=None):
    """Random placements (spawn, heading) in the valley, with the moisture at the two bush positions for a canopy of the
    mean radius (the final positions shift slightly with each bush's actual radius and are checked again)."""
    n = POOL_SAMPLES if n is None else int(n)
    half = float(params.world_half_extent)
    fwd, lat = bush_offsets(params, nominal_radius(params))
    fwd, lat = float(fwd), float(lat)
    spawn = rng.uniform(-half, half, (n, 2))
    yaw = rng.uniform(0.0, 2.0 * math.pi, n)
    f = np.stack([np.sin(yaw), np.cos(yaw)], axis=1)
    r = np.stack([np.cos(yaw), -np.sin(yaw)], axis=1)
    left = spawn + fwd * f - lat * r
    right = spawn + fwd * f + lat * r
    ok = terrain.is_tree_site(spawn[:, 0], spawn[:, 1]) & terrain.is_tree_site(left[:, 0], left[:, 1]) \
        & terrain.is_tree_site(right[:, 0], right[:, 1])
    spawn, yaw, left, right = spawn[ok], yaw[ok], left[ok], right[ok]
    m_left = terrain.moisture(left[:, 0], left[:, 1])
    m_right = terrain.moisture(right[:, 0], right[:, 1])
    return {"spawn": spawn, "yaw": yaw, "m_left": m_left, "m_right": m_right, "dm": np.abs(m_left - m_right)}


KIND_MASKS = {
    "same": lambda dm: dm <= SAME_TOL,
    "one": lambda dm: (dm >= ONE_LEVEL[0]) & (dm <= ONE_LEVEL[1]),
    "two": lambda dm: dm >= TWO_LEVELS_MIN,
    "any": lambda dm: np.ones_like(dm, dtype=bool),
}


# --------------------------------------------------------------------------------------------------
# Stimulus design
# --------------------------------------------------------------------------------------------------

def relevant_features(params):
    rf = params.reward_function
    w = {f: abs(float(rf[f + "Component"]["weight"])) for f in FEATURES}
    return sorted(FEATURES, key=lambda f: -w[f]), [f for f in FEATURES if w[f] > 0.0]


class Designer:
    def __init__(self, params, terrain, pool, rng):
        self.p = params
        self.t = terrain
        self.pool = pool
        self.rng = rng
        self.order, self.relevant = relevant_features(params)
        self.used = []                                  # spawn points already taken
        self._masks = {}
        self._cache = {}
        # spread of R_bush over typical bushes: shape and colour uniform, moisture as the terrain has it
        m = pool["m_left"][rng.integers(0, len(pool["m_left"]), 4000)]
        sh, co = rng.uniform(0, 1, 4000), rng.uniform(0, 1, 4000)
        self.scale = float(np.asarray(bush_value(params.reward_function, sh, co, m)).std())

    def value(self, bush):
        return float(bush_value(self.p.reward_function, bush["shape"], bush["color"], bush["moisture"]))

    # ---- placements ---------------------------------------------------------------------------
    def _los_ok(self, spawn, pos):
        """The terrain does not hide the bush from the spawn point: a clear line from the camera to a point just above the
        ground at `pos`, and no hump on the way (the ground must not rise and then fall between the player and the bush)."""
        t = self.t
        cam = float(t.elevation(spawn[0], spawn[1])) + float(self.p.eye_height)
        target = float(t.elevation(pos[0], pos[1])) + CANOPY_AIM_HEIGHT
        ts = np.linspace(0.05, 0.95, LOS_SAMPLES)
        ground = t.elevation(spawn[0] + ts * (pos[0] - spawn[0]), spawn[1] + ts * (pos[1] - spawn[1]))
        if np.any(ground + 0.3 > cam + ts * (target - cam)):
            return False
        return not has_hump(t, spawn, pos, self.p)

    def _spawn_ok(self, i):
        """Gentle slope under the spawn point (and a clear view toward the nominal bush positions)."""
        t, s = self.t, self.pool["spawn"][i]
        gx = (float(t.elevation(s[0] + 1.0, s[1])) - float(t.elevation(s[0] - 1.0, s[1]))) / 2.0
        gz = (float(t.elevation(s[0], s[1] + 1.0)) - float(t.elevation(s[0], s[1] - 1.0))) / 2.0
        if math.hypot(gx, gz) > MAX_SPAWN_SLOPE:
            return False
        yaw = float(self.pool["yaw"][i])
        for side in ("left", "right"):
            if not self._los_ok(s, bush_position(self.p, s, yaw, side, nominal_radius(self.p))):
                return False
        return True

    def pick(self, kind):
        """A placement whose (nominal) moisture relation is `kind`, away from the spawn points already used."""
        if kind not in self._masks:
            self._masks[kind] = np.flatnonzero(KIND_MASKS[kind](self.pool["dm"]))
        cand = self.rng.permutation(self._masks[kind])
        for spacing in (MIN_SITE_SPACING, MIN_SITE_SPACING / 2.0, 0.0):
            for i in cand[:6000]:
                s = self.pool["spawn"][i]
                if any(np.hypot(*(s - u)) < spacing for u in self.used):
                    continue
                if not self._spawn_ok(int(i)):
                    continue
                self.used.append(s.copy())
                return int(i)
        raise RuntimeError(f"no placement found for moisture relation '{kind}'")

    def attempt(self, kind, builder):
        """Pick placements until `builder(i)` returns a valid (left, right) pair, with every final bush position in the
        valley and in view of the spawn point."""
        for _ in range(MAX_ATTEMPTS):
            i = self.pick(kind)
            pair = builder(i)
            if pair is not None and self._final_ok(i, *pair):
                return i, pair[0], pair[1]
            self.used.pop()
        raise RuntimeError(f"could not build a '{kind}' trial after {MAX_ATTEMPTS} placements")

    def _final_ok(self, i, lt, rt):
        s = self.pool["spawn"][i]
        for b in (lt, rt):
            if not bool(self.t.is_tree_site(b["pos"][0], b["pos"][1])) or not self._los_ok(s, b["pos"]):
                return False
        return True

    # ---- bushes -------------------------------------------------------------------------------
    def bush(self, i, side, shape, color):
        """A bush on placement `i`. Its position comes from its own canopy radius, and its moisture is the terrain's
        moisture at that final position."""
        shape = round(float(shape), 2)
        key = (i, side, shape)
        if key not in self._cache:
            r = float(canopy_radius(self.p, shape))
            pos = bush_position(self.p, self.pool["spawn"][i], float(self.pool["yaw"][i]), side, r)
            self._cache[key] = (pos, r, float(self.t.moisture(pos[0], pos[1])))
        pos, r, m = self._cache[key]
        return {"shape": shape, "color": round(float(color), 2), "moisture": m, "pos": pos, "radius": r}

    def contributions(self, bush):
        rf = self.p.reward_function
        return {f: float(_basis(rf[f + "Component"], bush[f])) for f in FEATURES}

    def orient(self, i, x, y, want_left_better):
        """Put the (shape, colour) pair x on the left and y on the right, or the reverse, so that the requested side
        is the better one when either orientation allows it."""
        opts = []
        for x_left in (True, False):
            lt = self.bush(i, "left", *(x if x_left else y))
            rt = self.bush(i, "right", *(y if x_left else x))
            opts.append((lt, rt, self.value(lt) - self.value(rt)))
        if want_left_better is not None:
            for lt, rt, d in opts:
                if abs(d) >= TIE_TOLERANCE and (d > 0) == want_left_better:
                    return lt, rt
        choice = opts[int(self.rng.integers(2))]
        return choice[0], choice[1]

    # ---- trial types --------------------------------------------------------------------------
    def contrast(self, feature, easy, want_left_better):
        kind = "two" if feature == "moisture" else "same"

        def build(i):
            shape, color = (round(float(self.rng.uniform(0.3, 0.7)), 2) for _ in range(2))
            if feature == "moisture":
                # moisture comes from the placement; the other features (and so the radii) are equal
                lt, rt = self.bush(i, "left", shape, color), self.bush(i, "right", shape, color)
                return (lt, rt) if abs(lt["moisture"] - rt["moisture"]) >= TWO_LEVELS_MIN else None
            lo, hi = (0.1, 0.9) if easy else (0.15, 0.85)
            a, b = [shape, color], [shape, color]
            slot = 0 if feature == "shape" else 1
            a[slot], b[slot] = lo, hi
            lt, rt = self.orient(i, tuple(a), tuple(b), want_left_better)
            return (lt, rt) if abs(lt["moisture"] - rt["moisture"]) <= SAME_TOL else None

        return self.attempt(kind, build)

    def graded(self, target_fraction, want_left_better):
        target = target_fraction * self.scale

        def build(i):
            best = None
            for _ in range(1500):
                lt = self.bush(i, "left", *self.rng.uniform(0, 1, 2))
                rt = self.bush(i, "right", *self.rng.uniform(0, 1, 2))
                d = self.value(lt) - self.value(rt)
                if want_left_better is not None and (d > 0) != want_left_better:
                    continue
                score = abs(abs(d) - target)
                if best is None or score < best[0]:
                    best = (score, lt, rt)
            return None if best is None else (best[1], best[2])

        return self.attempt("any", build)

    def _extreme(self, feature):
        if feature not in self.relevant:
            return float(self.rng.uniform(0, 1))
        return float(self.rng.uniform(0.0, 0.12) if self.rng.random() < 0.5 else self.rng.uniform(0.88, 1.0))

    def extrapolation(self, want_left_better, taken):
        """Extreme-valued bushes. With several relevant features the pair is a genuine trade-off (each bush is better on
        some relevant feature and worse on another, by a clear margin) with a moderate true-reward difference, which is
        what exposes the relative weights; with one relevant feature it is an opposed pair of tail values."""
        lo, hi = 0.3 * self.scale, 1.0 * self.scale
        conflict = len(self.relevant) >= 2
        kind = ["one", "two"][int(self.rng.integers(2))] if "moisture" in self.relevant else "any"
        margin = {f: 0.2 * abs(float(self.p.reward_function[f + "Component"]["weight"])) for f in self.relevant}

        def pair_for(i, allow_repeat):
            for _ in range(1500):
                lt = self.bush(i, "left", self._extreme("shape"), self._extreme("color"))
                rt = self.bush(i, "right", self._extreme("shape"), self._extreme("color"))
                d = self.value(lt) - self.value(rt)
                if abs(d) < lo or (conflict and abs(d) > hi):
                    continue
                if want_left_better is not None and (d > 0) != want_left_better:
                    continue
                if conflict:
                    cl, cr = self.contributions(lt), self.contributions(rt)
                    if not (any(cl[f] - cr[f] > margin[f] for f in self.relevant)
                            and any(cr[f] - cl[f] > margin[f] for f in self.relevant)):
                        continue
                else:
                    f = self.relevant[0] if self.relevant else None
                    if f is not None and f != "moisture" and (lt[f] < 0.5) == (rt[f] < 0.5):
                        continue                  # one tail on each side
                key = tuple(round(lt[f] * 4) / 4 for f in ("shape", "color") if f in self.relevant) + \
                    tuple(round(rt[f] * 4) / 4 for f in ("shape", "color") if f in self.relevant) + (kind,)
                if not allow_repeat and key in taken:
                    continue
                taken.add(key)
                return lt, rt
            return None

        for allow_repeat in (False, True):
            try:
                return self.attempt(kind, lambda i: pair_for(i, allow_repeat))
            except RuntimeError:
                continue
        raise RuntimeError("no extrapolation pair found; relax the constraints")


def trial_mix(n, practice, n_relevant=3):
    """Trials per type. With a single relevant feature extrapolation is nearly redundant with the contrasts (it is
    one pair of opposed tails), so it gets one trial and the rest go to graded pairs."""
    if practice:
        return {"contrast": max(n - 1, 0), "graded": min(1, n), "extrapolation": 0}
    contrast = int(round(0.3 * n))
    extrapolation = int(round(0.3 * n)) if n_relevant >= 2 else min(1, n - contrast)
    return {"contrast": contrast, "graded": n - contrast - extrapolation, "extrapolation": extrapolation}


def build_trials(params, terrain, pool, rng):
    """List of dicts: type, varied, placement index and the two bushes' attributes."""
    n = int(params.interlude_trial_count)
    practice = bool(params.is_practice)
    des = Designer(params, terrain, pool, rng)
    mix = trial_mix(n, practice, len(des.relevant))

    kinds = ["contrast"] * mix["contrast"] + ["graded"] * mix["graded"] + ["extrapolation"] * mix["extrapolation"]
    # contrasts cover every relevant feature, plus one irrelevant feature as an ignored-feature check (not in practice)
    irrelevant = [f for f in des.order if f not in des.relevant]
    seq = list(des.relevant) + (irrelevant[:1] if not practice else [])
    varied_for, c = {}, 0
    for j, k in enumerate(kinds):
        if k == "contrast":
            varied_for[j] = seq[c % len(seq)]
            c += 1
    k_graded = mix["graded"]
    if practice:
        targets = [PRACTICE_GRADED_TARGET] * k_graded
    elif k_graded > 1:
        targets = [float(t) for t in np.geomspace(GRADED_TARGETS[0], GRADED_TARGETS[-1], k_graded)]
    else:
        targets = [0.6] * k_graded
    # requested sides: half of the trials put the better bush on the left (a moisture contrast cannot be steered)
    n_left = (n + int(rng.integers(0, 2))) // 2
    wants = [bool(w) for w in rng.permutation([True] * n_left + [False] * (n - n_left))]

    # moisture contrasts first (their placements are the scarcest), then the rest
    order = sorted(range(n), key=lambda j: 0 if (kinds[j] == "contrast" and varied_for.get(j) == "moisture") else 1)
    taken, graded_i, trials = set(), 0, [None] * n
    for j in order:
        k = kinds[j]
        if k == "contrast":
            f = varied_for[j]
            i, lt, rt = des.contrast(f, practice, None if f == "moisture" else wants[j])
            varied = f
        elif k == "graded":
            i, lt, rt = des.graded(targets[graded_i], wants[j])
            graded_i += 1
            varied = ""
        else:
            i, lt, rt = des.extrapolation(wants[j], taken)
            varied = ""
        trials[j] = {"type": k, "varied": varied, "place": i, "left": lt, "right": rt}

    # file order is shuffled once (seeded); Unity shuffles again per participant
    trials = [trials[j] for j in rng.permutation(n)]
    for t in trials:
        t["left_value"], t["right_value"] = des.value(t["left"]), des.value(t["right"])
        delta = t["left_value"] - t["right_value"]
        t["correct"] = "either" if abs(delta) < TIE_TOLERANCE else ("left" if delta > 0 else "right")
        t["delta_value"] = delta
    return trials, des


# --------------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------------

def generate_interlude(name, pool_samples=None, seed=None, **overrides):
    """Build the sidecar dict (bush table + trials) for the Interlude asset `name`; returns (sidecar, params, terrain).
    `pool_samples` overrides POOL_SAMPLES (the tests use a smaller search to run fast). `seed` replaces the world seed of
    the Interlude and of the session it probes, and `overrides` (snake_case SessionConfig fields) apply to both, so the
    simulator can build, for any world it plays, the very Interlude the game would show for that world."""
    if seed is not None:
        overrides = {**overrides, "world_seed": int(seed)}
    params = load_session(name, **overrides)
    if not bool(params.is_interlude):
        raise ValueError(f"{name} is not an Interlude asset (isInterlude is off)")
    base = load_session(params.interlude_for, **overrides)
    if params.reward_function != base.reward_function:
        raise ValueError(f"{name}: reward function differs from {params.interlude_for}")
    mine, theirs = check_values(params), check_values(base)
    mismatched = [k for k in theirs if mine.get(k) != theirs[k]]
    if mismatched:
        raise ValueError(f"{name}: parameters differ from {params.interlude_for}: {mismatched}")
    if int(params.world_seed) != int(base.world_seed):
        raise ValueError(f"{name}: worldSeed must equal {params.interlude_for}'s ({base.world_seed}) so the terrain is the same")
    check_geometry(params)

    seed = int(params.world_seed)
    terrain = generate_world(base, seed).terrain
    rngs = [np.random.default_rng(c) for c in np.random.SeedSequence([seed, 913]).spawn(3)]
    pool = make_pool(params, terrain, rngs[0], pool_samples)
    trials, des = build_trials(params, terrain, pool, rngs[1])
    n = len(trials)

    pos = np.zeros((2 * n, 2))
    shape = np.zeros(2 * n)
    color = np.zeros(2 * n)
    moisture = np.zeros(2 * n)
    radius = np.zeros(2 * n)
    for i, t in enumerate(trials):
        p = t["place"]
        for j, key in enumerate(("left", "right")):
            b = t[key]
            pos[2 * i + j] = b["pos"]
            shape[2 * i + j], color[2 * i + j], moisture[2 * i + j], radius[2 * i + j] = b["shape"], b["color"], b["moisture"], b["radius"]
        t["index"] = i
        t["start"] = [float(v) for v in pool["spawn"][p]]
        t["yaw"] = float(math.degrees(pool["yaw"][p]))

    value = np.asarray(bush_value(params.reward_function, shape, color, moisture), dtype=float)
    fruit_count = int(params.fruit_count)
    noise = rngs[2].standard_normal((2 * n, fruit_count)) * float(params.reward_std)
    fruit_reward = np.maximum(0, np.rint(value[:, None] + noise)).astype(np.int32)

    sidecar = {
        "session": params.session_name,
        "interludeFor": params.interlude_for,
        "seed": seed,
        "n": n,
        "tieTolerance": TIE_TOLERANCE,
        "scale": des.scale,
        # the bush table Unity loads in place of the session world file's bushes (same layout as the world file)
        "fruitCount": fruit_count,
        "treePos": pos.reshape(-1).tolist(),
        "shape": shape.tolist(),
        "color": color.tolist(),
        "moisture": moisture.tolist(),
        "canopyRadius": radius.tolist(),
        "value": value.tolist(),
        "fruitRewards": fruit_reward.reshape(-1).astype(int).tolist(),
        "trials": [{
            "index": t["index"], "type": t["type"], "varied": t["varied"], "start": t["start"], "yaw": t["yaw"],
            "correct": t["correct"], "deltaValue": float(t["delta_value"]),
            "left": {"id": 2 * t["index"], **{k: float(t["left"][k]) for k in FEATURES}, "value": float(t["left_value"])},
            "right": {"id": 2 * t["index"] + 1, **{k: float(t["right"][k]) for k in FEATURES}, "value": float(t["right_value"])},
        } for t in trials],
    }
    return sidecar, params, terrain


def sidecar_path(name, seed, out_dir=None):
    path = unity_world_path(name, seed, out_dir)
    return Path(str(path)[: -len(".world")] + ".interlude.json")


def write_sidecar(sidecar, name, out_dir=None):
    """Write an already-generated sidecar dict to <name>_seed<N>.interlude.json and return the path."""
    path = sidecar_path(name, sidecar["seed"], out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sidecar, f, indent=1)
    return path


def export(name, out_dir=None):
    sidecar, params, terrain = generate_interlude(name)
    return write_sidecar(sidecar, name, out_dir), sidecar


def main():
    ap = argparse.ArgumentParser(description="Generate Interlude trial files for Unity.")
    ap.add_argument("sessions", nargs="+", help="Interlude asset names, e.g. S1_Interlude")
    ap.add_argument("--out", default=None, help="output directory (default Assets/StreamingAssets/Worlds)")
    args = ap.parse_args()
    for name in args.sessions:
        path, sidecar = export(name, args.out)
        kinds = {}
        for t in sidecar["trials"]:
            kinds[t["type"]] = kinds.get(t["type"], 0) + 1
        print(f"{path.name}: {sidecar['n']} trials {kinds}, {path.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
