"""Value maps: a session's reward function as a specification over the (shape, colour) plane (docs/SESSION_FACTORS_PLAN.md, milestone 2).

A `ValueMap` is a sum of Gaussian bumps (the one primitive: placeable, stretchable, rotatable), a noise map (flat: the fixed per-fruit SD) and an equaliser (a gain on the whole
map). It serialises to JSON, evaluates on arrays, is described by continuous descriptors (sparsity, effective weights, interaction, nonlinearity, range), and compiles to the
reward fields `world.py` reads (`bumps`) and to the field settings `build_experiment.py` writes. The reward complexity ladder (additive, multiplicative, non-separable) has one
constructor each; the seed draws what a knob does not fix (the corner or centre, the tilt, which feature has the long axis).

The value map is the expected bush reward before per-fruit noise; moisture never pays. Descriptors are computed on a uniform grid over the unit plane.
"""

import json
from dataclasses import asdict, dataclass, field

import numpy as np

from world import bush_value

GRID = 101


@dataclass(frozen=True)
class Bump:
    """A Gaussian bump (`world.bush_value`'s `bumps`): `width` along the axis turned `angle` degrees from the shape axis, `width_color` along the other (0 = round)."""
    center_shape: float = 0.5
    center_color: float = 0.5
    width: float = 0.2
    width_color: float = 0.0
    angle: float = 0.0
    height: float = 1.0


@dataclass(frozen=True)
class ValueMap:
    bumps: tuple
    noise: dict = field(default_factory=lambda: {"type": "flat", "sd": 0.6})      # the fixed per-fruit SD; no other type is compiled yet (path B)
    equaliser: dict = field(default_factory=lambda: {"type": "gain", "value": 1.0})  # a transform of the map: only a gain so far (docs/SESSION_FACTORS_PLAN.md, 7.3)

    def to_dict(self):
        return {"bumps": [asdict(b) for b in self.bumps], "noise": self.noise, "equaliser": self.equaliser}

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        return cls(tuple(Bump(**b) for b in d["bumps"]), d["noise"], d["equaliser"])

    def gain(self):
        if self.equaliser["type"] != "gain":
            raise NotImplementedError(f"equaliser {self.equaliser['type']!r} is not built")
        return float(self.equaliser["value"])

    def compile(self):
        """The `load_session` overrides that make `world.py` generate this map: {"reward_function": ..., "reward_std": ...}."""
        if self.noise["type"] != "flat":
            raise NotImplementedError(f"noise {self.noise['type']!r} needs path B (the world generator draws a flat SD)")
        gain = self.gain()
        bumps = [{"centerShape": b.center_shape, "centerColor": b.center_color, "width": b.width, "widthColor": b.width_color, "angle": b.angle, "height": gain * b.height} for b in self.bumps]
        return {"reward_function": {"bumps": bumps}, "reward_std": float(self.noise["sd"])}

    def fields(self):
        """The SessionConfig field settings (serialized names, dotted paths) that give a session this map: what a design module passes on to `build_experiment.py`."""
        compiled = self.compile()
        out = {"rewardStd": compiled["reward_std"], "rewardFunction.bumps.Array.size": len(self.bumps)}
        for i, b in enumerate(compiled["reward_function"]["bumps"]):
            out.update({f"rewardFunction.bumps.Array.data[{i}].{name}": value for name, value in b.items()})
        return out

    def describe(self):
        """What a session's logged design (`designJson`) says of its reward: the map and its descriptors."""
        return {"value_map": self.to_dict(), "value_map_descriptors": {k: round(v, 4) for k, v in self.descriptors().items()}}

    def evaluate(self, shape, color):
        """The map at (shape, colour) (arrays broadcast), by the same function the generator calls."""
        return bush_value(self.compile()["reward_function"], np.asarray(shape, float), np.asarray(color, float))

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
    (a Gaussian whose axes are the features' axes, the wide corner one of the additive rung included), above 0 when the features are coupled in the product too (a turned Gaussian). The additive
    and the multiplicative rung are therefore told apart by the raw `interaction` (near 0 for additive), not by this one. 0 for a map with no positive cells."""
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

def wide_corner(corner=(1.0, 1.0), shape_share=0.5, base=0.7, scale=4.0, std=0.6):
    """The additive rung: a wide Gaussian in a `corner` of the plane (a corner coordinate 1 means that feature pays more when higher, 0 when lower). Its spreads are `base` at the
    geometric mean, unequal along the two axes (spread ratio ((1 - share) / share) ** 0.5, an approximation) so that about `shape_share` of the slope lies on shape: the share the descriptors
    measure is `shape_share` 0.71 for a request of 0.75, 0.58 for 0.6. Its raw `interaction` stays below 0.04 over `shape_share` 0.3 to 0.7; a wider `base` is closer to a plane and lower in range."""
    ws, wc = round(base * ((1.0 - shape_share) / shape_share) ** 0.25, 4), round(base * (shape_share / (1.0 - shape_share)) ** 0.25, 4)       # (rounded: a session asset stores them as float32)
    return ValueMap((Bump(float(corner[0]), float(corner[1]), ws, wc, 0.0, scale),), {"type": "flat", "sd": std})


def additive(seed, scale=4.0, shape_share=0.5, base=0.7, std=0.6):
    """`wide_corner` with the nuisance drawn from the seed: the corner (so each feature's direction) and which feature carries `shape_share`."""
    rng = np.random.default_rng(seed)
    corner, swap = rng.integers(0, 2, size=2), bool(rng.integers(2))
    return wide_corner(corner, 1.0 - shape_share if swap else shape_share, base, scale, std)


def gaussian(center_shape=0.5, center_color=0.5, across=0.2, aspect=1.0, angle=0.0, scale=4.0, std=0.6):
    """The core primitive as a map: a Gaussian placed at the centre, `across` its short axis and `aspect` times that along its long axis (`Bump.width` is the long one), turned `angle` degrees from the shape axis,
    `scale` high. Its separability is a matter of its parameters (`descriptors`): axis-aligned (angle 0 or 90) it is multiplicative (`log_interaction` 0, whatever the
    centre and aspect); turned it is not separable (`log_interaction` grows with the angle and the aspect); wide, in a corner or along an edge, it approaches an additive map."""
    return ValueMap((Bump(center_shape, center_color, across * aspect, across, angle, scale),), {"type": "flat", "sd": std})


def multiplicative(seed, scale=4.0, across=0.2, aspect=3.0, std=0.6):
    """A stretched Gaussian whose axes are the features' axes (a product of one bump per feature): the seed draws the centre and which feature has the long axis."""
    rng = np.random.default_rng(seed)
    return gaussian(float(rng.uniform(0.35, 0.65)), float(rng.uniform(0.35, 0.65)), across, aspect, float(rng.choice([0.0, 90.0])), scale, std)


def nonseparable(seed, scale=4.0, across=0.2, aspect=3.0, std=0.6):
    """The same Gaussian turned (25 to 65 degrees either way): rotation alone is the difference to `multiplicative`; the seed draws the centre and the tilt."""
    rng = np.random.default_rng(seed)
    angle = float(rng.uniform(25.0, 65.0) * rng.choice([-1.0, 1.0]))
    return gaussian(float(rng.uniform(0.35, 0.65)), float(rng.uniform(0.35, 0.65)), across, aspect, angle, scale, std)


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
