"""The reward rules of the feature-interaction experiment (FI, docs/EXPERIMENTS.md), the way `rw_peaks.py` is the peak model of RW.

One family: a single Gaussian over the (shape, colour) plane, drawn in three kinds that differ in how separable it is:

    corner      round, centred at a corner of the plane: monotone in both features, close to additive (a ramp with curved contours)
    middle      round, centred near the middle: a product of two Gaussians, separable in the shape and colour axes (and in every rotated basis)
    elongated   stretched along one axis and turned by `tilt` degrees from the shape axis: separable only in its own rotated basis; at 0 or 90 degrees it is a product again (the control)

The best bush pays REWARD_SCALE. **Sparsity is matched across the kinds**: each draw solves the spread so that the share of the plane whose reward is in the top `x`% of the reward range is the target
(`rw_peaks.sparsity`, the measure RW uses), within TOLERANCE of it. An instance has the interface of `rw_peaks.Peaks` that the screens and the world checks use (`value`, `dims`, `paying`,
`reward_function`, `session_fields`). `regions` says which bushes are on the high, middle and low parts of the reward (and, for an elongated Gaussian, along and across its long axis; the Interlude's
classes), `check_regions` that each is populated.
"""

import math
from dataclasses import dataclass

import numpy as np

import rw_peaks
import world

REWARD_SCALE = rw_peaks.REWARD_SCALE
KINDS = ("corner", "middle", "elongated")
FEATURES = ("shape", "color")
HIGH, LOW = 0.7, 0.25                     # a bush is high when it pays at least HIGH of the best, low when it pays at most LOW of it, middle otherwise
SPARSITY_X = (30, 40, 50)                 # the top-x% regions reported in an instance's record
TOLERANCE = 0.10                          # the realised sparsity is within this fraction of the target
MIDDLE_CENTER = (0.40, 0.60)              # where the centre of a middle or elongated Gaussian lies along each feature
ELONGATION = 3.5                          # the long spread over the short one of an elongated Gaussian
TILT_DEGREES = 45.0                       # how far its long axis is turned from the shape axis (the sign is drawn)
SOLVE_GRID, CHECK_GRID = 161, 501         # points per axis when solving for the sparsity, and when confirming it
MAX_DRAWS = 60
SPREAD_BOUNDS = {"corner": (0.05, 1.6), "middle": (0.02, 0.5), "elongated": (0.01, 0.5)}      # the short spread's search range
GUARANTEE = {"high": 10, "mid": 8, "low": 10}           # bushes a world must put on each part of the reward


@dataclass(frozen=True)
class Instance:
    kind: str
    factors: tuple         # the `factors` terms of the reward function (none for a Gaussian; a session built before keeps its field sized to 0)
    bumps: tuple           # its `bumps`
    record: dict           # what was drawn, for the design record

    dims = 2
    paying = FEATURES

    def reward_function(self):
        zero = {"basisFunctionType": 0, "weight": 0.0, "peak": 0.0, "width": 0.0}
        return {"shapeComponent": dict(zero), "colorComponent": dict(zero), "moistureComponent": dict(zero), "bumps": [dict(b) for b in self.bumps], "products": [],
                "factors": [{**t, "shapeFactor": dict(t["shapeFactor"]), "colorFactor": dict(t["colorFactor"])} for t in self.factors]}

    def session_fields(self):
        """The reward function as the dotted-path fields `build_experiment.py` sets on a session asset (a list is sized first; every feature's own component pays nothing)."""
        fields = {"rewardFunction.bumps.Array.size": len(self.bumps), "rewardFunction.products.Array.size": 0, "rewardFunction.factors.Array.size": len(self.factors)}
        for feature in FEATURES + ("moisture",):
            for key, value in (("basisFunctionType", 0), ("weight", 0.0), ("peak", 0.0), ("width", 0.0)):
                fields[f"rewardFunction.{feature}Component.{key}"] = value
        for i, b in enumerate(self.bumps):
            for key, value in b.items():
                fields[f"rewardFunction.bumps.Array.data[{i}].{key}"] = value
        return fields

    def value(self, shape, color):
        """The expected reward of a bush with these features (arrays broadcast)."""
        return world.bush_value(self.reward_function(), shape, color, 0.5)


def _bisect(sparsity_of, target, lo, hi, increasing, iterations=28):
    """The parameter in [lo, hi] at which `sparsity_of` equals `target` (geometric bisection), or None when the target is not between its values at the two ends."""
    a, b = sparsity_of(lo), sparsity_of(hi)
    if not (min(a, b) <= target <= max(a, b)):
        return None
    for _ in range(iterations):
        mid = math.sqrt(lo * hi)
        if (sparsity_of(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def _draw_once(rng, kind, elongation, tilt, target, x, corner=None, tilt_sign=None):
    """One draw of an instance of `kind` with its spread solved for the target sparsity, or None when the draw cannot reach it."""
    if kind == "corner":
        center, long_over_short, angle = (tuple(float(v) for v in corner) if corner is not None else (float(rng.integers(2)), float(rng.integers(2)))), 1.0, 0.0
    else:
        center = (float(rng.uniform(*MIDDLE_CENTER)), float(rng.uniform(*MIDDLE_CENTER)))
        long_over_short, angle = (1.0, 0.0) if kind == "middle" else (elongation, tilt * (tilt_sign if tilt_sign is not None else (1.0 if rng.integers(2) else -1.0)))
    def make(s):
        bump = {"centerShape": round(center[0], 4), "centerColor": round(center[1], 4), "width": round(s * long_over_short, 5), "widthColor": round(s, 5), "angle": round(angle, 2),
                "height": REWARD_SCALE}
        return Instance(kind, (), (bump,), {})
    s = _bisect(lambda s: rw_peaks.sparsity(make(s), x, SOLVE_GRID), target, *SPREAD_BOUNDS[kind], increasing=True)
    if s is None:
        return None
    return make(s), {"center": [round(v, 4) for v in center], "elongation": long_over_short, "tilt": round(angle, 2), "short_spread": round(s, 5)}


def draw_instance(rng, kind, target=0.20, x=40, elongation=ELONGATION, tilt=TILT_DEGREES, corner=None, tilt_sign=None):
    """An instance of `kind` drawn from `rng`: its position (a random corner, or near the middle) and the sign of its tilt at random, its spread solved so that the share of the plane in the top x%
    of the reward range is `target` (within TOLERANCE). `elongation` and `tilt` (degrees from the shape axis; 0 or 90 is the axis-aligned control) are for the elongated kind. Raises RuntimeError
    when no draw reaches the target. `corner` ((0 or 1, 0 or 1)) and `tilt_sign` (+1 or -1) fix what is otherwise drawn, so a design can balance them over its sessions."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind '{kind}' (expected one of {KINDS})")
    for _ in range(MAX_DRAWS):
        drawn = _draw_once(rng, kind, elongation, tilt, target, x, corner, tilt_sign)
        if drawn is None:
            continue
        inst, record = drawn
        realised = rw_peaks.sparsity(inst, x, CHECK_GRID)
        if abs(realised / target - 1.0) <= TOLERANCE:
            return Instance(kind, inst.factors, inst.bumps, {"kind": kind, **record, "target": target, "x": x, **describe(inst)})
    raise RuntimeError(f"no draw of '{kind}' reached a sparsity of {target} at x = {x} in {MAX_DRAWS} tries")


def nonzero_share(inst, fraction=0.1, n=CHECK_GRID):
    """The share of the plane whose reward is at least `fraction` of the best: how much of the plane pays something."""
    v = rw_peaks.reward_on_grid(inst, n)
    return float((v >= fraction * v.max()).mean())


def describe(inst):
    """The sparsity at each x of SPARSITY_X, the share of the plane that pays at least 10% of the best, and the best reward on the grid."""
    v = rw_peaks.reward_on_grid(inst, CHECK_GRID)
    return {"sparsity": {str(x): round(rw_peaks.sparsity(inst, x, CHECK_GRID), 4) for x in SPARSITY_X}, "nonzero": round(float((v >= 0.1 * v.max()).mean()), 4), "max_reward": round(float(v.max()), 3)}


def regions(inst, shape, color):
    """For the bushes (their shape and colour arrays), boolean arrays by where their reward lies: `high` (at least HIGH of the best), `low` (at most LOW of it), `mid` (between). An elongated
    Gaussian also has `along` (away from the centre, at least half a long spread, within one short spread of the long axis) and `across` (near the centre in the long direction, between one and
    two short spreads off the long axis): the two directions of its Interlude pairs."""
    v = np.asarray(inst.value(shape, color), dtype=float)
    top = float(rw_peaks.reward_on_grid(inst, SOLVE_GRID).max())
    out = {"high": v >= HIGH * top, "low": v <= LOW * top}
    out["mid"] = ~(out["high"] | out["low"])
    if inst.kind == "elongated":
        b = inst.bumps[0]
        angle = math.radians(float(b["angle"]))
        ds, dc = shape - b["centerShape"], color - b["centerColor"]
        along, cross = ds * math.cos(angle) + dc * math.sin(angle), -ds * math.sin(angle) + dc * math.cos(angle)
        out["along"] = (np.abs(along) >= 0.5 * b["width"]) & (np.abs(cross) <= b["widthColor"])
        out["across"] = (np.abs(along) <= 0.5 * b["width"]) & (np.abs(cross) >= b["widthColor"]) & (np.abs(cross) <= 2.0 * b["widthColor"])
    return out


def region_counts(inst, shape, color):
    return {name: int(mask.sum()) for name, mask in regions(inst, shape, color).items()}


def check_regions(inst, shape, color, minimum=None):
    """True when the world's bushes populate every part of the reward the Interlude and the sessions rely on (GUARANTEE, and for an elongated Gaussian the `along` and `across` parts at the `mid` count)."""
    need = dict(GUARANTEE if minimum is None else minimum)
    if inst.kind == "elongated":
        need.update({"along": need["mid"], "across": need["mid"]})
    counts = region_counts(inst, shape, color)
    return all(counts[name] >= count for name, count in need.items())
