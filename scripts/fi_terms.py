"""The reward rules of the feature-interaction experiment (FI, docs/EXPERIMENTS.md), the way `rw_peaks.py` is the peak model of RW.

Four kinds of rule over the (shape, colour) plane, each one a reward function of terms the game knows (`RewardFactors`, `RewardBump` with its `angle`):

    sum                 height * (f(x) + g(y)) / 2, f and g sigmoids: each feature adds its own part (the separable baseline, the same factors as `product`)
    product             height * f(x) * g(y), sigmoids: both features must be high (the optimum is a corner of the plane)
    sigmoid_gaussian    height * f(gate) * g(other), a sigmoid of one feature and a Gaussian of the other: a high gate and an interior value of the other
    bump                a Gaussian elongated and turned by an angle: not separable, the optimum is interior

A sigmoid is 1 at its paying end (`inverted` draws which end), so the best bush pays `height` (REWARD_SCALE) in every kind. Its inflection point is measured from the paying end. `steepness` is per unit of the
feature (about 4 is nearly linear over the range, 30 nearly a step). The roles (which feature gates, which way each pays), the positions and the tilt are drawn per instance from a seeded generator.

**Sparsity is matched across the kinds.** Each draw solves its one free parameter (the sigmoids' inflection point, the Gaussian's width, the bump's spread) so that the share of the plane whose reward is in the top
`x`% of the reward range is the target (`rw_peaks.sparsity`, the measure RW uses), within TOLERANCE of it. An instance has the interface of `rw_peaks.Peaks` that the screens and the world checks use
(`value`, `dims`, `paying`, `reward_function`, `session_fields`). `regions` says which bushes are on the high, middle and low parts of the reward (the Interlude's classes), `check_regions` that each is populated.
"""

import math
from dataclasses import dataclass

import numpy as np

import rw_peaks
import world

REWARD_SCALE = rw_peaks.REWARD_SCALE
KINDS = ("sum", "product", "sigmoid_gaussian", "bump")
FEATURES = ("shape", "color")
HIGH, LOW = 0.7, 0.25                     # a bush is high when it pays at least HIGH of the best, low when it pays at most LOW of it, middle otherwise
SPARSITY_X = (30, 40, 50)                 # the top-x% regions reported in an instance's record
TOLERANCE = 0.10                          # the realised sparsity is within this fraction of the target
STEEPNESS_JITTER = 0.2                    # each sigmoid's steepness is the stated one times exp(+-this): the instances of a level differ a little
INFLECTION_RATIO = 0.2                    # the two inflection points of a sum or product differ by up to exp(+-this)
GATE_CENTER = (0.25, 0.5)                 # where the gating sigmoid of sigmoid_gaussian turns, from its paying end
PEAK_CENTER = (0.25, 0.75)                # where the Gaussian factor (sigmoid_gaussian) or the bump is centred along each feature it lies on
TILT_DEGREES = (20.0, 70.0)               # the bump's long axis is this far from a feature axis (either side)
ELONGATION = 3.5                          # the bump's spread along its long axis over the one across it
SOLVE_GRID, CHECK_GRID = 161, 501         # points per axis when solving for the sparsity, and when confirming it
MAX_DRAWS = 60
GUARANTEE = {"high": 10, "mid": 8, "low": 10}           # bushes a world must put on each part of the reward


@dataclass(frozen=True)
class Instance:
    kind: str
    factors: tuple         # the `factors` terms of the reward function
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
        for i, t in enumerate(self.factors):
            for key in ("combine", "height"):
                fields[f"rewardFunction.factors.Array.data[{i}].{key}"] = t[key]
            for side in ("shapeFactor", "colorFactor"):
                for key, value in t[side].items():
                    fields[f"rewardFunction.factors.Array.data[{i}].{side}.{key}"] = value
        return fields

    def value(self, shape, color):
        """The expected reward of a bush with these features (arrays broadcast)."""
        return world.bush_value(self.reward_function(), shape, color, 0.5)


def sigmoid(center, steepness, inverted):
    return {"kind": 0, "center": round(float(center), 4), "scale": round(float(steepness), 3), "inverted": bool(inverted)}


def gaussian(center, spread):
    return {"kind": 1, "center": round(float(center), 4), "scale": round(float(spread), 4), "inverted": False}


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


def _steepness(rng, steepness):
    return float(steepness * math.exp(rng.uniform(-STEEPNESS_JITTER, STEEPNESS_JITTER)))


def _draw_once(rng, kind, steepness, elongation, target, x):
    """One draw of an instance of `kind` with its free parameter solved for the target sparsity, or None when the draw cannot reach it."""
    solve = lambda inst: rw_peaks.sparsity(inst, x, SOLVE_GRID)
    height = REWARD_SCALE
    if kind in ("sum", "product"):
        inverted, ratio = [bool(rng.integers(2)) for _ in FEATURES], math.exp(rng.uniform(-INFLECTION_RATIO, INFLECTION_RATIO))
        k = [_steepness(rng, steepness) for _ in FEATURES]
        combine = 1 if kind == "sum" else 0
        def make(c):
            centers = (min(c, 0.95), min(c * ratio, 0.95))
            terms = ({"combine": combine, "height": height, "shapeFactor": sigmoid(centers[0], k[0], inverted[0]), "colorFactor": sigmoid(centers[1], k[1], inverted[1])},)
            return Instance(kind, terms, (), {})
        c = _bisect(lambda c: solve(make(c)), target, 0.03, 0.9, increasing=False)
        record = {"steepness": [round(v, 3) for v in k], "inverted": {"shape": inverted[0], "color": inverted[1]}}
        return None if c is None else (make(c), {**record, "inflection": [round(min(c, 0.95), 4), round(min(c * ratio, 0.95), 4)]})
    if kind == "sigmoid_gaussian":
        gate = FEATURES[int(rng.integers(2))]
        k, inverted = _steepness(rng, steepness), bool(rng.integers(2))
        c, m = rng.uniform(*GATE_CENTER), rng.uniform(*PEAK_CENTER)
        def make(w):
            gate_factor, other_factor = sigmoid(c, k, inverted), gaussian(m, w)
            shape_factor, color_factor = (gate_factor, other_factor) if gate == "shape" else (other_factor, gate_factor)
            return Instance(kind, ({"combine": 0, "height": height, "shapeFactor": shape_factor, "colorFactor": color_factor},), (), {})
        w = _bisect(lambda w: solve(make(w)), target, 0.02, 0.6, increasing=True)
        record = {"gate": gate, "steepness": round(k, 3), "inverted": inverted, "inflection": round(c, 4), "peak_center": round(m, 4)}
        return None if w is None else (make(w), {**record, "peak_spread": round(w, 4)})
    if kind == "bump":
        tilt = float(rng.uniform(*TILT_DEGREES)) * (1.0 if rng.integers(2) else -1.0)
        center = (float(rng.uniform(*PEAK_CENTER)), float(rng.uniform(*PEAK_CENTER)))
        def make(s):
            return Instance(kind, (), ({"centerShape": round(center[0], 4), "centerColor": round(center[1], 4), "width": round(s * elongation, 5), "widthColor": round(s, 5),
                                        "angle": round(tilt, 2), "height": height},), {})
        s = _bisect(lambda s: solve(make(s)), target, 0.01, 0.5, increasing=True)
        return None if s is None else (make(s), {"center": [round(v, 4) for v in center], "tilt": round(tilt, 2), "elongation": elongation, "short_spread": round(s, 5)})
    raise ValueError(f"unknown kind '{kind}' (expected one of {KINDS})")


def draw_instance(rng, kind, steepness=10.0, elongation=ELONGATION, target=0.30, x=40):
    """An instance of `kind` drawn from `rng`: its roles, positions and tilt at random, its free parameter solved so that the share of the plane in the top x% of the reward range is `target`
    (within TOLERANCE). `steepness` is for the sigmoids, `elongation` for the bump. Raises RuntimeError when no draw reaches the target (the target is out of reach of the kind)."""
    for _ in range(MAX_DRAWS):
        drawn = _draw_once(rng, kind, steepness, elongation, target, x)
        if drawn is None:
            continue
        inst, record = drawn
        realised = rw_peaks.sparsity(inst, x, CHECK_GRID)
        if abs(realised / target - 1.0) <= TOLERANCE:
            return Instance(kind, inst.factors, inst.bumps, {"kind": kind, **record, "target": target, "x": x, **describe(inst)})
    raise RuntimeError(f"no draw of '{kind}' (steepness {steepness}, elongation {elongation}) reached a sparsity of {target} at x = {x} in {MAX_DRAWS} tries")


def nonzero_share(inst, fraction=0.1, n=CHECK_GRID):
    """The share of the plane whose reward is at least `fraction` of the best: how much of the plane pays something."""
    v = rw_peaks.reward_on_grid(inst, n)
    return float((v >= fraction * v.max()).mean())


def describe(inst):
    """The sparsity at each x of SPARSITY_X, the share of the plane that pays at least 10% of the best, and the best reward on the grid."""
    v = rw_peaks.reward_on_grid(inst, CHECK_GRID)
    return {"sparsity": {str(x): round(rw_peaks.sparsity(inst, x, CHECK_GRID), 4) for x in SPARSITY_X}, "nonzero": round(float((v >= 0.1 * v.max()).mean()), 4), "max_reward": round(float(v.max()), 3)}


def regions(inst, shape, color):
    """For the bushes (their shape and colour arrays), boolean arrays by where their reward lies: `high` (at least HIGH of the best), `low` (at most LOW of it), `mid` (between). A bump also has
    `along` (away from the centre, at least half a long spread, within one short spread of the long axis) and `across` (near the centre in the long direction, between one and two short spreads
    off the long axis): the two directions of its Interlude pairs. At the matched sparsity the long spread is wider than the plane, so the bump is a tilted ridge and has no ends inside it."""
    v = np.asarray(inst.value(shape, color), dtype=float)
    top = float(rw_peaks.reward_on_grid(inst, SOLVE_GRID).max())
    out = {"high": v >= HIGH * top, "low": v <= LOW * top}
    out["mid"] = ~(out["high"] | out["low"])
    if inst.kind == "bump":
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
    """True when the world's bushes populate every part of the reward the Interlude and the sessions rely on (GUARANTEE, and for a bump the `along` and `across` parts at the `mid` count)."""
    need = dict(GUARANTEE if minimum is None else minimum)
    if inst.kind == "bump":
        need.update({"along": need["mid"], "across": need["mid"]})
    counts = region_counts(inst, shape, color)
    return all(counts[name] >= count for name, count in need.items())
