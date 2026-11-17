"""Value maps: a session's reward function as a specification over the (shape, colour) plane (docs/SESSION_FACTORS_PLAN.md, milestone 2).

A `ValueMap` is a list of primitives (a ramp, a placeable, stretchable, rotatable Gaussian bump (the core primitive)), a noise map (flat: the fixed per-fruit SD) and an equaliser
(a gain on the whole map). It serialises to JSON, evaluates on arrays, is described by continuous descriptors (sparsity, effective weights, interaction, nonlinearity,
range), and compiles to the reward fields `world.py` already reads, so the world generator is unchanged. The ladder (additive, multiplicative, non-separable) has one
constructor each; the seed draws what a knob does not fix (which feature, which direction, where the peak lies, the rotation).

The value map is the expected bush reward before per-fruit noise, at any moisture (moisture never pays here). Descriptors are computed on a uniform grid over the unit plane.
"""

import json
from dataclasses import asdict, dataclass, field

import numpy as np

from world import bush_value

GRID = 101
MOISTURE = 0.5          # moisture pays nothing here; the value passed to the evaluator
FEATURE_COMPONENT = {"shape": "shapeComponent", "color": "colorComponent"}


@dataclass(frozen=True)
class Ramp:
    """`weight` * x (`direction` 0) or `weight` * (1 - x) (`direction` 1) in one feature."""
    feature: str
    weight: float = 1.0
    direction: int = 0


@dataclass(frozen=True)
class Bump:
    """A Gaussian bump (`world.bush_value`'s `bumps`): `width` along the axis turned `angle` degrees from the shape axis, `width_color` along the other (0 = round)."""
    center_shape: float = 0.5
    center_color: float = 0.5
    width: float = 0.2
    width_color: float = 0.0
    angle: float = 0.0
    height: float = 1.0


PRIMITIVES = {cls.__name__: cls for cls in (Ramp, Bump)}


def _term_to_dict(term):
    return {"type": type(term).__name__, **asdict(term)}


def _term_from_dict(d):
    d = dict(d)
    return PRIMITIVES[d.pop("type")](**d)


@dataclass(frozen=True)
class ValueMap:
    terms: tuple
    noise: dict = field(default_factory=lambda: {"type": "flat", "sd": 0.6})      # the fixed per-fruit SD; no other type is compiled yet (path B)
    equaliser: dict = field(default_factory=lambda: {"type": "gain", "value": 1.0})  # a transform of the map: only a gain so far (docs/SESSION_FACTORS_PLAN.md, 7.3)

    def to_json(self):
        return json.dumps({"terms": [_term_to_dict(t) for t in self.terms], "noise": self.noise, "equaliser": self.equaliser}, sort_keys=True)

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        return cls(tuple(_term_from_dict(t) for t in d["terms"]), d["noise"], d["equaliser"])

    def gain(self):
        if self.equaliser["type"] != "gain":
            raise NotImplementedError(f"equaliser {self.equaliser['type']!r} is not built")
        return float(self.equaliser["value"])

    def compile(self):
        """The `load_session` overrides that make `world.py` generate this map: {"reward_function": ..., "reward_std": ...}."""
        if self.noise["type"] != "flat":
            raise NotImplementedError(f"noise {self.noise['type']!r} needs path B (the world generator draws a flat SD)")
        gain = self.gain()
        zero = {"basisFunctionType": 0, "weight": 0.0, "peak": 0.0, "width": 0.0}
        rf = {"shapeComponent": dict(zero), "colorComponent": dict(zero), "moistureComponent": dict(zero), "bumps": [], "products": []}
        seen = set()
        for t in self.terms:
            if isinstance(t, Ramp):
                if t.feature not in FEATURE_COMPONENT or t.feature in seen:
                    raise ValueError(f"a ramp needs its own feature of shape/color, got {t.feature!r} again or unknown")
                seen.add(t.feature)
                rf[FEATURE_COMPONENT[t.feature]].update(basisFunctionType=int(t.direction), weight=gain * t.weight)
            elif isinstance(t, Bump):
                rf["bumps"].append({"centerShape": t.center_shape, "centerColor": t.center_color, "width": t.width, "widthColor": t.width_color, "angle": t.angle, "height": gain * t.height})
            else:
                raise TypeError(t)
        return {"reward_function": rf, "reward_std": float(self.noise["sd"])}

    def evaluate(self, shape, color):
        """The map at (shape, colour) (arrays broadcast), by the same function the generator calls."""
        return bush_value(self.compile()["reward_function"], np.asarray(shape, float), np.asarray(color, float), MOISTURE)

    def grid(self, n=GRID):
        """(axis, R) with R[i, j] = the map at shape axis[i], colour axis[j]."""
        axis = np.linspace(0.0, 1.0, n)
        return axis, self.evaluate(axis[:, None], axis[None, :])

    def descriptors(self, n=GRID):
        return descriptors(*self.grid(n))


# --------------------------------------------------------------------------------------------------
# Descriptors
# --------------------------------------------------------------------------------------------------

def gini(values):
    """Gini coefficient of the non-negative `values` (0 = all equal, towards 1 = everything in one place); 0 for an all-zero array."""
    v = np.sort(np.clip(np.ravel(values), 0.0, None))
    total = v.sum()
    if total <= 0.0:
        return 0.0
    n = len(v)
    return float(2.0 * np.sum(np.arange(1, n + 1) * v) / (n * total) - (n + 1.0) / n)


def _unexplained(r, fit):
    """The share of R's variance a fit leaves unexplained (1 - R^2); 0 for a constant map."""
    total = float(np.sum((r - r.mean()) ** 2))
    return 0.0 if total <= 1e-12 else float(np.sum((r - fit) ** 2) / total)


LOG_FLOOR = 0.01        # the log is taken where the map is at least this share of its maximum (a Gaussian's tail has no information left)


def log_interaction(r):
    """1 - R^2 of the best f(shape) + g(colour) fit to log R, over the cells where R >= LOG_FLOOR * max: 0 for a map that is a product of a function of each feature
    (a Gaussian whose axes are the features' axes), above 0 when the features are coupled in the product too (a turned Gaussian). A ramp is additive, not
    multiplicative, so it has a log interaction above 0 and a raw `interaction` of 0: the two together say which kind of separable a map is. 0 for a map with no positive cells."""
    n = r.shape[0]
    rows, cols = np.nonzero(r >= LOG_FLOOR * r.max()) if r.max() > 0 else (np.array([], int), np.array([], int))
    if len(rows) < 3:
        return 0.0
    y = np.log(r[rows, cols])
    design = np.zeros((len(y), 2 * n))
    design[np.arange(len(y)), rows] = 1.0
    design[np.arange(len(y)), n + cols] = 1.0
    return _unexplained(y, design @ np.linalg.lstsq(design, y, rcond=None)[0])


def descriptors(axis, r):
    """The continuous descriptors of the map `r` on the grid `axis` x `axis` (docs/SESSION_FACTORS_PLAN.md, 3)."""
    gs, gc = np.gradient(r, axis, axis)
    ms, mc = float(np.mean(np.abs(gs))), float(np.mean(np.abs(gc)))
    additive = r.mean(axis=1, keepdims=True) + r.mean(axis=0, keepdims=True) - r.mean()            # the least-squares f(shape) + g(colour) on a full grid
    s, c = np.meshgrid(axis, axis, indexing="ij")
    design = np.column_stack([np.ones(r.size), s.ravel(), c.ravel()])
    plane = (design @ np.linalg.lstsq(design, r.ravel(), rcond=None)[0]).reshape(r.shape)
    return {"gini": gini(r), "fraction_above_half_max": float(np.mean(r >= 0.5 * r.max())) if r.max() > 0 else 0.0,
            "effective_weight_shape": ms, "effective_weight_color": mc, "effective_weight_total": ms + mc, "shape_share": ms / (ms + mc) if ms + mc > 0 else 0.5,
            "interaction": _unexplained(r, additive), "log_interaction": log_interaction(r), "nonlinearity": _unexplained(r, plane),
            "min": float(r.min()), "max": float(r.max()), "mean": float(r.mean()), "range": float(r.max() - r.min())}


# --------------------------------------------------------------------------------------------------
# The ladder: one constructor per rung. `scale` is about the best bush's pay; the seed draws the nuisance.
# --------------------------------------------------------------------------------------------------

def ramps(seed, scale=4.0, shape_share=0.5, std=0.6):
    """The exact additive map, a sum of one ramp per feature (the shares of `scale` go to shape and colour); the seed draws which feature carries `shape_share` and each ramp's direction."""
    rng = np.random.default_rng(seed)
    swap, dirs = bool(rng.integers(2)), rng.integers(0, 2, size=2)
    shares = (shape_share, 1.0 - shape_share)[::-1] if swap else (shape_share, 1.0 - shape_share)
    return ValueMap((Ramp("shape", scale * shares[0], int(dirs[0])), Ramp("color", scale * shares[1], int(dirs[1]))), {"type": "flat", "sd": std})


def additive(seed, scale=4.0, shape_share=0.5, base=0.7, std=0.6):
    """The additive rung: a wide Gaussian in a corner (the additive proxy of 2026-11-17). Its spreads are `base` at the geometric mean, unequal along the two axes so that
    `shape_share` of the slope lies on shape (as the weights of two ramps would); the seed draws the corner (so each feature's direction) and which feature carries `shape_share`.
    Its raw `interaction` stays below 0.04 over `shape_share` 0.3 to 0.7 (a wider `base` is closer to a plane and lower in range: `ramps` is the exact case, without the falloff)."""
    rng = np.random.default_rng(seed)
    corner, swap = rng.integers(0, 2, size=2).astype(float), bool(rng.integers(2))
    share = 1.0 - shape_share if swap else shape_share
    return ValueMap((Bump(float(corner[0]), float(corner[1]), base * ((1.0 - share) / share) ** 0.25, base * (share / (1.0 - share)) ** 0.25, 0.0, scale),), {"type": "flat", "sd": std})


def gaussian(center_shape=0.5, center_color=0.5, width=0.2, aspect=1.0, angle=0.0, scale=4.0, std=0.6):
    """The core primitive as a map: a Gaussian placed at the centre, `width` across and `aspect` times that along its long axis, turned `angle` degrees from the shape axis,
    `scale` high. Its separability is a matter of its parameters (`descriptors`): axis-aligned (angle 0 or 90) it is multiplicative (`log_interaction` 0, whatever the
    centre and aspect); turned it is not separable (`log_interaction` grows with the angle and the aspect); wide, in a corner or along an edge, it approaches an additive map."""
    return ValueMap((Bump(center_shape, center_color, width * aspect, width, angle, scale),), {"type": "flat", "sd": std})


def multiplicative(seed, scale=4.0, width=0.2, aspect=3.0, std=0.6):
    """A stretched Gaussian whose axes are the features' axes (a product of one bump per feature): the seed draws the centre and which feature has the long axis."""
    rng = np.random.default_rng(seed)
    return gaussian(float(rng.uniform(0.35, 0.65)), float(rng.uniform(0.35, 0.65)), width, aspect, float(rng.choice([0.0, 90.0])), scale, std)


def nonseparable(seed, scale=4.0, width=0.2, aspect=3.0, std=0.6):
    """The same Gaussian turned (25 to 65 degrees either way): rotation alone is the difference to `multiplicative`; the seed draws the centre and the tilt."""
    rng = np.random.default_rng(seed)
    angle = float(rng.uniform(25.0, 65.0) * rng.choice([-1.0, 1.0]))
    return gaussian(float(rng.uniform(0.35, 0.65)), float(rng.uniform(0.35, 0.65)), width, aspect, angle, scale, std)


LADDER = {"additive": additive, "multiplicative": multiplicative, "nonseparable": nonseparable}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Descriptors of the ladder's value maps.")
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    for name, make in LADDER.items():
        rows = [make(seed).descriptors() for seed in range(args.seeds)]
        print(f"{name}: " + ", ".join(f"{k} {np.mean([r[k] for r in rows]):.3f}±{np.std([r[k] for r in rows]):.3f}" for k in ("gini", "interaction", "log_interaction", "nonlinearity", "shape_share", "mean", "max")))


if __name__ == "__main__":
    main()
