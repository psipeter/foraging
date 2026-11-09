"""Interlude design generator: the forced-choice block run after each session.

An Interlude looks like its session: the same world (terrain, mountains, sun), but only two bushes are present.
The player turns toward the one they think pays more, walks to it and harvests it. Outcomes are never shown. This
module is the source of truth for the stimulus set and bush placement (Unity only plays the file back), mirroring
how world.py works for the main sessions. There is no Interlude-specific terrain: a bush's moisture and elevation
come from the session's own terrain at the position it stands on, exactly as in the main task.

Inputs are two SessionConfig assets, read through world.load_session:
  <name>              an Interlude asset (isInterlude, interludeFor, interludeTrialCount, interludeBushDistance /
                      Bearing, worldSeed = the probed session's seed, ...). Its reward function and every terrain
                      parameter are copies of the session it probes (checked here).
  <interludeFor>      the session asset it probes; its world file (<session>_seed<N>.world) supplies the terrain.

Output (Assets/StreamingAssets/Experiments/<code>/<name>_seed<N>.interlude.json): the bush table for all trials (ids 2i and 2i+1 =
left and right of trial i) plus the per-trial metadata: type, varied feature, spawn point and heading, both bushes'
attributes and true reward, and the correct side. Unity loads the terrain from the session's world file and replaces
its bush table with this one.

Geometry. The two bushes must be equal in the terms the game's harvest rules use, which refer to the canopy edge: the
distance from the spawn point to each canopy edge is the same (`interludeBushDistance`), and so is the bearing of each
canopy's inner edge from the heading (`interludeBushBearing`, on opposite sides), so the heading bisects the pair and
turning and walking to either is the same. A canopy's radius depends on its shape, so each bush's centre is placed from
its own radius; the two centres are therefore not exactly symmetric about the heading when the radii differ.

Trials. The default mode is `hybrid`: pairs of random bushes chosen so that both the true reward gap and the perceptual (feature) gap are spread evenly over their
ranges, over the features the session declares (`world.session_features`), with some exact repeats; `reward_gap`, `feature_gap` and `random` are the simpler modes.
A bush's moisture is whatever the terrain has at its position, as in the main task; moisture is a feature channel of the gap only when the session declares it.
Designed trial types (contrast, graded, extrapolation) were removed (2026-11-09) and come back, one kind at a time, in `TRIAL_KINDS` when an experiment needs them. The one registered so far is
`per_feature` (FN): `interludeFeatureTrials` trials for each visible feature that pays enough to show, a pair that differs in that feature only, with the true reward gap spread in noise units (`rewardStd`).

Usage:
    python scripts/interlude.py TUT_I1 CF_I1 CF_I2 CF_I3 CF_I4 CF_I5 CF_I6 CF_I7
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from world import (FEATURES, PROJECT_ROOT, REWARDS, check_values, generate_world, load_session, session_features,
                   stage_names, unity_world_path)

TIE_TOLERANCE = 0.05          # |R_left - R_right| below this: either answer is "correct"

# Placement search (module constants: they shape the stimulus set, not the game)
POOL_SAMPLES = 40_000         # random (spawn, heading) placements searched for valid sites
RANDOM_DRAWS = 300            # (shape, colour) pairs tried on a placement before moving to another
MODES = ("random", "reward_gap", "feature_gap", "hybrid")
MODE_CODES = {1: "random", 2: "reward_gap", 3: "feature_gap", 4: "hybrid"}   # SessionConfig.interludeMode (InterludeMode enum order; 0 = Designed, retired)
DEFAULT_MODE = "hybrid"
GAP_MODES = ("reward_gap", "feature_gap", "hybrid")
GAP_SITES = 60                # placements whose bush pairs the gap modes choose their trials from (one trial per placement)
GAP_PAIRS = 150               # (shape, colour) pairs drawn on each of them
GAP_TOP_QUANTILE = 0.98       # the largest gap a gap mode spreads its trials to: this quantile of the candidate pairs' gaps
GAP_SEARCH_STEPS = 30_000     # swaps tried when choosing the trials from the candidates
ORDER_DRAWS = 3000            # gap modes: random orders tried for the file order (the same for every participant)
REPEAT_SEPARATION = 8         # gap modes with repeats: the fewest trials between a pair and its repeat
ORDER_MAX_RUN = 3             # ... which may not put the same correct side more than this many times in a row
PER_FEATURE_EFFECTS = (0.5, 3.0)   # per-feature trials: the true reward gap, in units of rewardStd, from the smallest to the largest asked of a feature (provisional)
PER_FEATURE_MIN_GAP = 0.15    # a feature gets per-feature trials only if it can make a reward gap at least this large (three times the tie tolerance)
PER_FEATURE_DRAWS = 600       # value pairs tried on a placement for a per-feature trial
MOISTURE_REACH_QUANTILE = 0.97   # per-feature trials on moisture ask for at most the moisture difference that this share of placements offers
MATCHED_MOISTURE = 0.03       # |moisture difference| of two bushes that are to be "the same" in moisture
FEATURE_WEIGHTS = {"shape": 1.0, "color": 1.0, "moisture": 1.0}   # perceptual weight of each channel in `feature_gap` (no measured JNDs yet: equal)
MIN_SITE_SPACING = 80.0       # trials' spawn points are at least this far apart (relaxed if the pool is thin)
MAX_SPAWN_SLOPE = 0.6         # rise/run at the spawn point
LOS_SAMPLES = 14              # terrain samples checked along the line of sight to each bush
CANOPY_AIM_HEIGHT = 1.0       # line of sight is checked to a point this far above the ground at each bush (near its base)
PROFILE_SAMPLES = 30          # terrain samples along the path from the spawn point to each bush
HUMP_TOLERANCE = 0.5          # a rise then a fall of more than this (world units) between the spawn and a bush is a hump
MAX_ATTEMPTS = 300            # placements tried per trial before giving up


def feature_weights(params):
    """The channels `feature_gap` counts for a session: the features it declares visible (`world.session_features`), so a gap is 0 for identical
    bushes and 1 for opposite ends of every counted channel."""
    return {f: FEATURE_WEIGHTS[f] if d["visible"] else 0.0 for f, d in session_features(params).items()}


def feature_gap(a, b, weights=None):
    """Perceptual distance of two bushes: the weighted root mean square of their differences in shape, colour and moisture, each on its
    0-1 scale, so 0 = identical and 1 = opposite ends of every channel. The declared visible channels count (`feature_weights`), relevant to the
    reward or not, because a participant sees them all."""
    w = weights or FEATURE_WEIGHTS
    return math.sqrt(sum(w[f] * (a[f] - b[f]) ** 2 for f in FEATURES) / sum(w.values()))


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
    """Random placements (spawn, heading) in the valley, with the moisture at the left bush position for a canopy of the mean radius (the Designer
    samples it for the spread of R) and the moisture difference `dm` of the two nominal bush positions (a trial that needs equal or different moisture picks
    placements by it; the final positions shift slightly with each bush's actual radius and are checked again)."""
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
    m_left, m_right = terrain.moisture(left[:, 0], left[:, 1]), terrain.moisture(right[:, 0], right[:, 1])
    return {"spawn": spawn, "yaw": yaw, "m_left": m_left, "dm": np.abs(m_left - m_right)}


# --------------------------------------------------------------------------------------------------
# Stimulus design
# --------------------------------------------------------------------------------------------------

class Designer:
    def __init__(self, params, terrain, pool, rng):
        self.p = params
        self.t = terrain
        self.pool = pool
        self.rng = rng
        self.weights = feature_weights(params)
        self.reward = REWARDS[stage_names(params)[2]]
        self.no_correct_side = params.random_bush_value_range[1] > params.random_bush_value_range[0]   # a random reward: no attribute predicts it
        self.used = []                                  # spawn points already taken
        self._cache = {}
        self._site_ok = {}
        # spread of R_bush over typical bushes: shape and colour uniform, moisture as the terrain has it
        m = pool["m_left"][rng.integers(0, len(pool["m_left"]), 4000)]
        sh, co = rng.uniform(0, 1, 4000), rng.uniform(0, 1, 4000)
        self.scale = float(np.asarray(self.reward(params.reward_function, sh, co, m)).std())

    def value(self, bush):
        return float(self.reward(self.p.reward_function, bush["shape"], bush["color"], bush["moisture"]))

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

    def pick(self, dm=None):
        """A placement away from the spawn points already used, with a gentle slope and a clear view of the nominal bush positions. `dm` = (low, high): only
        placements whose two nominal bushes differ in moisture by an amount in that window."""
        if dm is None:
            cand = self.rng.permutation(len(self.pool["spawn"]))
        else:
            cand = self.rng.permutation(np.flatnonzero((self.pool["dm"] >= dm[0]) & (self.pool["dm"] <= dm[1])))
        for spacing in (MIN_SITE_SPACING, MIN_SITE_SPACING / 2.0, 0.0):
            for i in cand[:6000]:
                s = self.pool["spawn"][i]
                if any(np.hypot(*(s - u)) < spacing for u in self.used):
                    continue
                if not self._spawn_ok(int(i)):
                    continue
                self.used.append(s.copy())
                return int(i)
        raise RuntimeError("no placement found")

    def attempt(self, builder, dm=None):
        """Pick placements (with the moisture difference window `dm`, see `pick`) until `builder(i)` returns a valid (left, right) pair, with every final bush
        position in the valley and in view of the spawn point."""
        for _ in range(MAX_ATTEMPTS):
            i = self.pick(dm)
            pair = builder(i)
            if pair is not None and self._final_ok(i, *pair):
                return i, pair[0], pair[1]
            self.used.pop()
        raise RuntimeError(f"could not build a trial after {MAX_ATTEMPTS} placements")

    def _final_ok(self, i, lt, rt):
        s = self.pool["spawn"][i]
        for b in (lt, rt):
            key = (i, tuple(np.round(b["pos"], 6)))
            if key not in self._site_ok:
                self._site_ok[key] = bool(self.t.is_tree_site(b["pos"][0], b["pos"][1])) and self._los_ok(s, b["pos"])
            if not self._site_ok[key]:
                return False
        return True

    # ---- bushes -------------------------------------------------------------------------------
    def bush(self, i, side, shape, color):
        """A bush on placement `i`. Its position comes from its own canopy radius, and its moisture is the terrain's
        moisture at that final position."""
        shape = round(float(shape), 2) if self.p.shape_varies else float(self.p.shape_when_fixed)
        color = color if self.p.color_varies else float(self.p.color_when_fixed)
        key = (i, side, shape)
        if key not in self._cache:
            r = float(canopy_radius(self.p, shape))
            pos = bush_position(self.p, self.pool["spawn"][i], float(self.pool["yaw"][i]), side, r)
            self._cache[key] = (pos, r, float(self.t.moisture(pos[0], pos[1])))
        pos, r, m = self._cache[key]
        return {"shape": shape, "color": round(float(color), 2), "moisture": m, "pos": pos, "radius": r}

    # ---- trials -------------------------------------------------------------------------------
    def random_trial(self, want_left_better):
        """Random mode: both bushes get independent uniform shape and colour (moisture is the terrain's at the final position, as
        everywhere). A pair whose true rewards are within the tie tolerance is redrawn, so a trial always has a correct side;
        `want_left_better` (or None) picks which side that is."""
        def build(i):
            for _ in range(RANDOM_DRAWS):
                lt = self.bush(i, "left", *self.rng.uniform(0, 1, 2))
                rt = self.bush(i, "right", *self.rng.uniform(0, 1, 2))
                d = self.value(lt) - self.value(rt)
                if not self.no_correct_side and (abs(d) < TIE_TOLERANCE or (want_left_better is not None and (d > 0) != want_left_better)):
                    continue
                return lt, rt
            return None

        return self.attempt(build)

    def gap_candidates(self):
        """Gap modes: bush pairs on GAP_SITES placements, GAP_PAIRS random (shape, colour) pairs each, as rows
        (placement, left bush, right bush, reward gap, feature gap, left is better). Pairs within the tie tolerance are left out; whether a pair is in
        view is checked only for the pairs chosen (it is the slow part, a terrain line of sight per bush)."""
        rows = []
        for _ in range(GAP_SITES):
            try:
                i = self.pick()
            except RuntimeError:
                break
            for _ in range(GAP_PAIRS):
                lt = self.bush(i, "left", *self.rng.uniform(0, 1, 2))
                rt = self.bush(i, "right", *self.rng.uniform(0, 1, 2))
                d = self.value(lt) - self.value(rt)
                if abs(d) >= TIE_TOLERANCE:
                    rows.append((i, lt, rt, abs(d), feature_gap(lt, rt, self.weights), d > 0))
        return rows

def per_feature_trial(des, feature, effect, want_left_better):
    """A pair of bushes that differ in `feature` only (the other features equal; moisture, which comes from the terrain, within MATCHED_MOISTURE), with a true
    reward gap of about `effect` noise units (`rewardStd`). For shape and colour the two values are searched for the gap; for moisture the placement is."""
    target = effect * float(des.p.reward_std)
    tolerance = 0.2 * target

    def close(lt, rt):
        d = des.value(lt) - des.value(rt)
        return abs(abs(d) - target) <= tolerance and (want_left_better is None or (d > 0) == want_left_better)

    if feature == "moisture":
        def build(i):
            shape, color = (round(float(des.rng.uniform(0.3, 0.7)), 2) for _ in range(2))
            lt, rt = des.bush(i, "left", shape, color), des.bush(i, "right", shape, color)
            return (lt, rt) if close(lt, rt) else None
        dm0 = target / max(reachable_gap(des, "moisture") / moisture_reach(des), 1e-9)      # the moisture difference that gives the gap (the reward being near linear in it)
        return des.attempt(build, dm=(0.7 * dm0, 1.3 * dm0))

    def build(i):
        base = [round(float(des.rng.uniform(0.3, 0.7)), 2) for _ in range(2)]
        slot = 0 if feature == "shape" else 1
        for _ in range(PER_FEATURE_DRAWS):
            a, b = (round(float(des.rng.uniform(0.0, 1.0)), 2) for _ in range(2))
            left, right = list(base), list(base)
            left[slot], right[slot] = a, b
            lt, rt = des.bush(i, "left", *left), des.bush(i, "right", *right)
            if abs(lt["moisture"] - rt["moisture"]) <= MATCHED_MOISTURE and close(lt, rt):
                return lt, rt
        return None
    return des.attempt(build, dm=(0.0, MATCHED_MOISTURE / 2.0))


def moisture_reach(des):
    """The largest moisture difference two bushes of a trial can have on this terrain: the 97th percentile over the placements (the two bushes stand about
    28 units apart, so a continuous field gives far less than its whole range)."""
    return float(np.quantile(des.pool["dm"], MOISTURE_REACH_QUANTILE))


def reachable_gap(des, feature):
    """The largest true reward gap two bushes can have when they differ in `feature` only (searched over random values; moisture over the placements)."""
    if feature == "moisture":
        dm = moisture_reach(des)
        return abs(float(des.reward(des.p.reward_function, 0.5, 0.5, 0.5 + dm / 2) - des.reward(des.p.reward_function, 0.5, 0.5, 0.5 - dm / 2)))
    v = np.linspace(0.0, 1.0, 21)
    args = [np.full(21, 0.5), np.full(21, 0.5), np.full(21, 0.5)]
    args[{"shape": 0, "color": 1}[feature]] = v
    values = np.asarray(des.reward(des.p.reward_function, *args))
    return float(values.max() - values.min())


# Trial kinds an experiment adds: name -> builder(designer, ...) returning (placement, left bush, right bush).
TRIAL_KINDS = {"per_feature": per_feature_trial}


def feature_trials(des, per_feature, rng):
    """`per_feature` trials for each visible feature, effect sizes spread evenly (geometric) from PER_FEATURE_EFFECTS[0] to its largest noise-unit effect the
    feature can produce (at most PER_FEATURE_EFFECTS[1]); sides alternate. Returns trial dicts of type "per_feature", `varied` the feature."""
    std = float(des.p.reward_std)
    trials, side = [], bool(rng.integers(2))
    for feature, declared in session_features(des.p).items():
        if not declared["visible"] or per_feature <= 0 or reachable_gap(des, feature) < PER_FEATURE_MIN_GAP:
            continue                  # (a feature that pays nothing, or too little to make a pair with a clear better side, has no per-feature trial)
        top = min(PER_FEATURE_EFFECTS[1], 0.9 * reachable_gap(des, feature) / std)
        low = min(PER_FEATURE_EFFECTS[0], top)
        for effect in np.geomspace(low, top, per_feature) if top > 0 else []:
            i, lt, rt = TRIAL_KINDS["per_feature"](des, feature, float(effect), side)
            trials.append({"type": "per_feature", "varied": feature, "place": i, "left": lt, "right": rt})
            side = not side
    return trials


def build_random_trials(params, terrain, pool, rng):
    """Random mode: `interludeTrialCount` pairs of bushes with independent random shape and colour (no trial types), each with a definite better side, half of them on the left."""
    n = int(params.interlude_trial_count)
    des = Designer(params, terrain, pool, rng)
    n_left = (n + int(rng.integers(0, 2))) // 2
    wants = [bool(w) for w in rng.permutation([True] * n_left + [False] * (n - n_left))]
    trials = []
    for j in range(n):
        i, lt, rt = des.random_trial(wants[j])
        trials.append({"type": "random", "varied": "", "place": i, "left": lt, "right": rt})
    return _finish_trials(trials, des, rng), des


def choose_gap_trials(rows, n, axes, minima, rng, maxima=None):
    """From candidate rows (placement, left, right, reward gap, feature gap, left is better) choose `n` on distinct placements, half with
    the left bush better, so that the sorted gaps on each axis (3 = reward, 4 = feature) are as close as possible to n evenly spaced values
    from that axis's minimum to its maximum (`maxima`, if given for the axis: candidates above it are left out) or else to GAP_TOP_QUANTILE of the
    candidates' gaps (the target of bin k is its centre). Hill climbing on swaps.
    Returns (chosen rows, {axis: (low, high)})."""
    maxima = maxima or {}
    rows = [r for r in rows if all(minima[a] <= r[a] <= maxima.get(a, np.inf) for a in axes)]
    if len({r[0] for r in rows}) < n:
        raise RuntimeError(f"only {len(rows)} usable candidate pairs on {len({r[0] for r in rows})} placements for {n} trials; lower the minimum gaps")
    gaps = np.array([[r[a] for a in axes] for r in rows])
    span = {a: (minima[a], maxima[a] if a in maxima else float(np.quantile(gaps[:, j], GAP_TOP_QUANTILE))) for j, a in enumerate(axes)}
    targets = np.array([[lo + (k + 0.5) / n * (hi - lo) for k in range(n)] for lo, hi in (span[a] for a in axes)])
    width = np.array([[hi - lo] for lo, hi in (span[a] for a in axes)])
    left = np.array([r[5] for r in rows])
    site = np.array([r[0] for r in rows])

    def loss(sel):
        return float((((np.sort(gaps[sel], axis=0).T - targets) / width) ** 2).sum())

    n_left = (n + int(rng.integers(0, 2))) // 2
    sel = []
    for side, count in ((True, n_left), (False, n - n_left)):
        for c in rng.permutation(np.flatnonzero(left == side)):
            if len([k for k in sel if left[k] == side]) == count:
                break
            if site[c] not in {site[k] for k in sel}:
                sel.append(int(c))
    if len(sel) < n:
        raise RuntimeError("could not choose Interlude trials on distinct placements with both sides better")
    best = loss(sel)
    for _ in range(GAP_SEARCH_STEPS):
        p = int(rng.integers(n))
        c = int(rng.integers(len(rows)))
        if left[c] != left[sel[p]] or (site[c] in {site[k] for j, k in enumerate(sel) if j != p}):
            continue
        trial = sel.copy()
        trial[p] = c
        value = loss(trial)
        if value <= best:
            sel, best = trial, value
    return [rows[k] for k in sel], span


def build_gap_trials(params, terrain, pool, rng, mode):
    """Gap modes: `interludeTrialCount` pairs spread evenly over the reward gap (`reward_gap`), the feature gap (`feature_gap`) or both
    (`hybrid`; chosen jointly, so each is even on its own; the two gaps are correlated because reward is a function of the features, which is accepted). The same trials for every participant: the pairs come
    from the world seed. No elevation rule is needed: moisture is one of the feature channels and a reward feature in S3/S4."""
    n_total = int(params.interlude_trial_count)
    repeats = min(int(getattr(params, "interlude_repeat_count", 0) or 0), n_total // 2)         # (at most half the trials repeat a pair: a short Interlude keeps its pairs)
    des = Designer(params, terrain, pool, rng)
    per_feature = int(getattr(params, "interlude_feature_trials", 0) or 0)
    typed = feature_trials(des, per_feature, rng) if per_feature else []        # (the scarcest placements first; none by default, so the stimuli of the other sessions do not move)
    n = n_total - repeats - len(typed)
    if n < 1:
        raise ValueError(f"interludeTrialCount {n_total} has no room for the {len(typed)} per-feature trials and {repeats} repeats")
    axes = {"reward_gap": (3,), "feature_gap": (4,), "hybrid": (3, 4)}[mode]
    minima = {3: float(getattr(params, "interlude_min_reward_gap", 0.25)), 4: float(getattr(params, "interlude_min_feature_gap", 0.1))}
    # optional ceilings (reward units for the reward gap, 0-1 for the feature gap); 0 or absent: the gaps spread up to GAP_TOP_QUANTILE of the candidates
    maxima = {a: float(v) for a, v in ((3, getattr(params, "interlude_max_reward_gap", 0)), (4, getattr(params, "interlude_max_feature_gap", 0))) if v}
    rows = des.gap_candidates()
    while True:
        chosen, span = choose_gap_trials(rows, n, axes, minima, rng, maxima)
        hidden = [r for r in chosen if not des._final_ok(*r[:3])]
        if not hidden:
            break
        rows = [r for r in rows if not any(r is h for h in hidden)]          # a chosen pair not in view: choose again without it
    trials = typed + [{"type": mode, "varied": "", "place": r[0], "left": r[1], "right": r[2]} for r in chosen]
    trials += pick_repeats(trials, repeats, des)
    des.gap_span = {("reward", "feature")[a - 3]: span[a] for a in axes}
    return _finish_trials(trials, des, rng, ordered=True, separation=int(getattr(params, "interlude_repeat_separation", REPEAT_SEPARATION))), des


def pick_repeats(trials, k, des):
    """`k` exact repeats of chosen trials: the same placement, spawn point, bushes and sides (shallow copies, linked to their source by
    `repeat_source`; the sidecar gives a copy its own bush entries, so the bush the participant harvested the first time is not the
    depleted one). The pairs repeated are those whose reward gap is nearest the median (neither trivial nor a coin flip), alternating
    the correct side so the sides stay balanced."""
    if k == 0:
        return []
    delta = [des.value(t["left"]) - des.value(t["right"]) for t in trials]
    middle = float(np.median(np.abs(delta)))
    free, copies = list(range(len(trials))), []
    for i in range(k):
        side = i % 2 == 0                                          # left-correct first, then right-correct, ...
        pool = [j for j in free if (delta[j] > 0) == side] or free
        j = min(pool, key=lambda j: abs(abs(delta[j]) - middle))
        free.remove(j)
        copies.append({**trials[j], "repeat_source": trials[j]})
    return copies


def _order_penalty(rows):
    """How much a presentation order invites a strategy other than the learned values: the same correct side more than ORDER_MAX_RUN
    times in a row, alternating sides, and a trend or a lag-1 autocorrelation in either gap (a run of ever-larger or ever-smaller differences)."""
    sides = [r[0] for r in rows]
    runs = sum(1 for k in range(len(sides) - ORDER_MAX_RUN) if len(set(sides[k:k + ORDER_MAX_RUN + 1])) == 1)
    alternating = sum(1 for k in range(len(sides) - 3) if sides[k] == sides[k + 2] != sides[k + 1] and sides[k + 1] == sides[k + 3])
    cost = 10.0 * (runs + alternating)
    pos = np.arange(len(rows))
    for column in (1, 2):
        g = np.array([r[column] for r in rows])
        cost += abs(np.corrcoef(pos, g)[0, 1]) + abs(np.corrcoef(g[:-1], g[1:])[0, 1])
    return cost


def _finish_trials(trials, des, rng, ordered=False, separation=0):
    """Shuffle the file order once (seeded) and add each trial's true values and correct side. The file order is what every participant
    sees. `ordered` (gap modes): of ORDER_DRAWS shuffles keep the one with the least order structure (`_order_penalty`), among those that put
    every repeat at least `separation` trials from its source."""
    for t in trials:
        t["left_value"], t["right_value"] = des.value(t["left"]), des.value(t["right"])
        delta = t["left_value"] - t["right_value"]
        t["correct"] = "either" if abs(delta) < TIE_TOLERANCE else ("left" if delta > 0 else "right")
        t["delta_value"] = delta
    if ordered:
        perms = [rng.permutation(len(trials)) for _ in range(ORDER_DRAWS)]
        def key(perm):
            cost = _order_penalty([(trials[j]["correct"], abs(trials[j]["delta_value"]), feature_gap(trials[j]["left"], trials[j]["right"], des.weights)) for j in perm])
            rank = {id(trials[j]): r for r, j in enumerate(perm)}
            return cost + sum(1000.0 for t in trials if "repeat_source" in t and abs(rank[id(t)] - rank[id(t["repeat_source"])]) < separation)
        perm = min(perms, key=key)
    else:
        perm = rng.permutation(len(trials))
    return [trials[j] for j in perm]


# --------------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------------

def interlude_mode(params, mode=None):
    """The generation mode: `mode` if given (a name), else the asset's `interludeMode` field (absent = hybrid; 0, the retired Designed, is refused)."""
    if mode is None:
        mode = getattr(params, "interlude_mode", None)
        if mode is None:
            return DEFAULT_MODE
        if mode == 0:
            raise ValueError("interludeMode 0 (Designed) was retired; use Random, RewardGap, FeatureGap or Hybrid")
    mode = MODE_CODES.get(mode, mode)
    if mode not in MODES:
        raise ValueError(f"unknown Interlude mode '{mode}' (expected one of {MODES})")
    return mode


def generate_interlude(name, pool_samples=None, seed=None, mode=None, extras=None, **overrides):
    """Build the sidecar dict (bush table + trials) for the Interlude asset `name`; returns (sidecar, params, terrain).
    `pool_samples` overrides POOL_SAMPLES (the tests use a smaller search to run fast). `seed` replaces the world seed of
    the Interlude and of the session it probes, and `overrides` (snake_case SessionConfig fields) apply to both, so the
    simulator can build, for any world it plays, the very Interlude the game would show for that world. `mode` is "random", "reward_gap", "feature_gap" or "hybrid"; None reads the asset's `interludeMode`. `extras` sets generator
    options of the gap modes for an asset that has no field for them (older assets; the same names as the SessionConfig fields): `interlude_max_reward_gap` / `interlude_max_feature_gap` (ceilings of the two gaps),
    `interlude_repeat_count` (how many of the `interludeTrialCount` trials are exact repeats of an earlier pair) and `interlude_repeat_separation`
    (the fewest trials between a pair and its repeat, default REPEAT_SEPARATION)."""
    if seed is not None:
        overrides = {**overrides, "world_seed": int(seed)}
    params = load_session(name, **overrides)
    for key, value in (extras or {}).items():          # generator options that are not asset fields yet (see below)
        setattr(params, key, value)
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
    mode = interlude_mode(params, mode)
    pool = make_pool(params, terrain, rngs[0], pool_samples)
    trials, des = build_random_trials(params, terrain, pool, rngs[1]) if mode == "random" else build_gap_trials(params, terrain, pool, rngs[1], mode)
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
    for t in trials:
        if "repeat_source" in t:                    # a repeat and its source: the later one in the file says which earlier trial it repeats
            early, late = sorted((t, t["repeat_source"]), key=lambda x: x["index"])
            late["repeat_of"] = early["index"]

    value = np.asarray(des.reward(params.reward_function, shape, color, moisture), dtype=float)
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
    sidecar["mode"] = mode
    for entry, t in zip(sidecar["trials"], trials):
        entry["rewardGap"] = abs(float(t["delta_value"]))
        entry["featureGap"] = feature_gap(t["left"], t["right"], des.weights)
    for entry, t in zip(sidecar["trials"], trials):
        if "repeat_of" in t:
            entry["repeatOf"] = t["repeat_of"]      # (the loader ignores it; analysis uses it to pair a trial with its repeat)
    if mode in GAP_MODES:
        sidecar["gapSpan"] = {k: [float(v[0]), float(v[1])] for k, v in des.gap_span.items()}
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
    ap.add_argument("sessions", nargs="+", help="Interlude asset names, e.g. CF_I1")
    ap.add_argument("--out", default=None, help="output directory (default Assets/StreamingAssets/Experiments/<code>)")
    args = ap.parse_args()
    for name in args.sessions:
        path, sidecar = export(name, args.out)
        kinds = {}
        for t in sidecar["trials"]:
            kinds[t["type"]] = kinds.get(t["type"], 0) + 1
        print(f"{path.name}: {sidecar['n']} trials {kinds}, {path.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
