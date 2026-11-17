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


# --------------------------------------------------------------------------------------------------
# Calibration: the Gaussian that has a stated sparsity and complexity, and the gain that equalises the points earnable
# --------------------------------------------------------------------------------------------------

SEARCH_GRID = 41          # the grid of the search (the final map is checked on GRID)
ALIGNED_LOG_MAX = 0.05    # an axis-aligned map has a log interaction at most this (0 up to rounding), a rotated one at least ROTATED_LOG_MIN
ROTATED_LOG_MIN = 0.10
SEARCH = {"de_maxiter": 60, "de_popsize": 12, "nm_maxiter": 150}        # the effort of `calibrate_map` (a test lowers it)


MULTIPLICATIVE_SHARE_OF_CAP = 0.9                       # the multiplicative rung asks for this share of the interaction an axis-aligned Gaussian of that Gini can reach: as interactive as that family gets
ALIGNED_CAP = ((0.2, 0.06), (0.4, 0.12), (0.6, 0.21), (0.8, 0.37))        # what an axis-aligned Gaussian can reach, by Gini (docs/SESSION_FACTORS_PLAN.md, the reachable region)
NONSEPARABLE_INTERACTION = 0.4                          # the interaction asked of the non-separable rung unless a cell says otherwise
CLASS_KLASS = {"additive": "corner", "multiplicative": "aligned", "nonseparable": "rotated"}      # the family each rung of the ladder is searched in


CORNER_STRETCHES = (1.0, 2.0, 3.0)                      # the additive rung's Gaussian is round or stretched 2:1 or 3:1 (PI, 2026-11-17); the long axis (shape or colour) is a nuisance


def corner_aspect(stretch, long_shape):
    """The ratio of the shape width to the colour width of a stretched corner Gaussian: `stretch` times longer along shape when `long_shape`, else along colour."""
    return float(stretch) if long_shape else 1.0 / float(stretch)


def aligned_cap(gini):
    return float(np.interp(gini, [g for g, _ in ALIGNED_CAP], [c for _, c in ALIGNED_CAP]))


def default_interaction(name, gini):
    """The interaction asked of a rung of the ladder at a Gini: additive None (the smallest its corner allows), multiplicative a share of what an aligned map can reach, non-separable 0.4."""
    return {"additive": None, "multiplicative": MULTIPLICATIVE_SHARE_OF_CAP * aligned_cap(gini), "nonseparable": NONSEPARABLE_INTERACTION}[name]


def _gaussian_from(x, rotated, scale, std):
    centre_shape, centre_color, across, aspect = x[:4]
    return gaussian(float(centre_shape), float(centre_color), float(across), float(aspect), float(x[4]) if rotated else 0.0, scale, std)


def calibrate_map(gini, interaction, klass="aligned", scale=4.0, std=0.6, tol=(0.02, 0.02), share=(0.25, 0.75), seed=0, corner=(1.0, 1.0), aspect=1.0):
    """The Gaussian map whose Gini is `gini` and raw interaction `interaction` (each within `tol`), found by a search over the family of `gaussian` (a centre anywhere, a short axis 0.05 to 1.5,
    an aspect 1 to 6, and for `klass` "rotated" an angle of 15 to 75 degrees; "aligned" maps have axes along the features, a log interaction of 0, and are additive or multiplicative according to
    the interaction asked: near 0 additive, larger multiplicative). Both features must pay: the share of the slope on shape lies within `share`. Raises ValueError, naming the closest map found,
    when the pair is not reachable (`map_region.py` shows the region). `klass` "corner" is the additive rung proper: the Gaussian centred exactly on a corner of the plane (`corner`, each coordinate 0 or 1:
    that feature pays more when it is higher (1) or lower (0)), so both features pay monotonically; its widths have the ratio `aspect` (shape over colour; `corner_aspect`) and their size is solved for the Gini; the interaction and the shape share are what that gives (`interaction` is ignored). The gain is not touched: `scale` is the peak and the equaliser (`solve_gain`) sets the level afterwards."""
    from scipy.optimize import differential_evolution, minimize
    rotated = {"aligned": False, "rotated": True, "corner": False}[klass]
    at_corner = klass == "corner"
    if at_corner:
        build = lambda x: ValueMap((Bump(float(corner[0]), float(corner[1]), float(x[0]) * aspect ** 0.5, float(x[0]) / aspect ** 0.5, 0.0, scale),), {"type": "flat", "sd": std})
        bounds = [(0.08, 3.0)]
    else:
        build = lambda x: _gaussian_from(x, rotated, scale, std)
        bounds = [(0.0, 1.0), (0.0, 1.0), (0.05, 1.5), (1.0, 6.0)] + ([(15.0, 75.0)] if rotated else [])
    if at_corner:                                                                 # one width left once the aspect is fixed: the Gini decides it, the interaction and shares follow
        from scipy.optimize import brentq
        best = build([brentq(lambda w: build([w]).descriptors()["gini"] - gini, *bounds[0], xtol=1e-5)])
        d = best.descriptors()
        if abs(d["gini"] - gini) > tol[0]:
            raise ValueError(f"no corner Gaussian of aspect {aspect:.2f} with Gini {gini}: the closest has Gini {d['gini']:.3f}")
        return best

    def loss(x, n):
        d = build(x).descriptors(n)
        penalty = (60.0 * max(0.0, share[0] - d["shape_share"], d["shape_share"] - share[1])) ** 2
        penalty += (10.0 * (max(0.0, ROTATED_LOG_MIN - d["log_interaction"]) if rotated else max(0.0, d["log_interaction"] - ALIGNED_LOG_MAX))) ** 2
        if interaction is None:                                                  # the smallest interaction the Gini allows: the Gini first, then the interaction pushed down
            return 100.0 * ((d["gini"] - gini) / tol[0]) ** 2 + d["interaction"] / tol[1] + penalty
        return ((d["gini"] - gini) / tol[0]) ** 2 + ((d["interaction"] - interaction) / tol[1]) ** 2 + penalty

    found = differential_evolution(loss, bounds, args=(SEARCH_GRID,), seed=seed, maxiter=SEARCH["de_maxiter"], popsize=SEARCH["de_popsize"], tol=1e-6, polish=False)
    found = minimize(loss, found.x, args=(GRID,), method="Nelder-Mead", bounds=bounds, options={"maxiter": SEARCH["nm_maxiter"], "xatol": 1e-4, "fatol": 1e-6})
    best = build(found.x)
    d = best.descriptors()
    if abs(d["gini"] - gini) > tol[0] or (interaction is not None and abs(d["interaction"] - interaction) > tol[1]) or not share[0] - 0.01 <= d["shape_share"] <= share[1] + 0.01:
        raise ValueError(f"no {klass} Gaussian with Gini {gini} and interaction {interaction} (within {tol}, shape share {share}): the closest has Gini {d['gini']:.3f}, interaction {d['interaction']:.3f}, share {d['shape_share']:.2f}")
    return best


def map_proxies(valuemap, quantile=0.9):
    """The proxies for the points earnable that need nothing but the map (uniform feature plane): the mean and the median bush value, the mean per-fruit pay (the rounding and the clamp at 0 of
    `max(0, round(N(R, sd)))` included, the sum over the whole points the noise can give) and the `quantile` of the bush values (what a good forager collects)."""
    _, r = valuemap.grid()
    sd = float(valuemap.noise["sd"])
    z = np.arange(0, int(np.ceil(r.max() + 6.0 * sd)) + 2)
    from math import erf, sqrt
    cdf = np.vectorize(erf)((z[None, :] + 0.5 - r.reshape(-1, 1)) / (sd * sqrt(2.0))) * 0.5 + 0.5        # P(rounded draw <= z), the clamp at 0 puts the mass below 0.5 on 0
    pmf = np.diff(np.concatenate([np.zeros((cdf.shape[0], 1)), cdf], axis=1), axis=1)
    return {"mean_bush_value": float(r.mean()), "median_bush_value": float(np.median(r)), "mean_fruit_pay": float((pmf * z[None, :]).sum(axis=1).mean()),
            f"q{int(100 * quantile)}_bush_value": float(np.quantile(r, quantile))}


def solve_gain(valuemap, proxy, target, lo=0.05, hi=20.0, rel_tol=0.01, max_steps=15, gain_tol=0.015):
    """The map with an equaliser gain at which `proxy(map)` equals `target` (within `rel_tol`): `proxy` is a function of a ValueMap (a key of `map_proxies` by name, or any callable, for example the
    points a reference policy earns, `factors.policy_points`). The proxy is taken to follow a power of the gain (about the first power: the points rise in proportion), the exponent estimated from the
    last two evaluations, and each step moves the gain to where that law reaches the target. A learning agent's points are a jagged function of the gain, so the steps stop, and the gain with the value
    nearest the target is returned, once the gains on the two sides of the target are within `gain_tol` (a share) of each other, even if the value is not within `rel_tol`: the caller checks.
    Raises ValueError if the gain needed leaves `lo` to `hi`, or the steps do not settle."""
    f = (lambda m: map_proxies(m)[proxy]) if isinstance(proxy, str) else proxy
    with_gain = lambda g: ValueMap(valuemap.bumps, valuemap.noise, {"type": "gain", "value": float(g)})
    gain, history, exponent = valuemap.gain(), [], 1.0
    for _ in range(max_steps):
        value = f(with_gain(gain))
        history.append((gain, value))
        if abs(value - target) <= rel_tol * abs(target):
            return with_gain(gain)
        below = [g for g, v in history if v < target]
        above = [g for g, v in history if v >= target]
        if below and above and min(above) / max(below) - 1.0 <= gain_tol:
            return with_gain(min(history, key=lambda gv: abs(gv[1] - target))[0])
        if len(history) >= 2 and history[-1][1] > 0 and history[-2][1] > 0 and abs(np.log(history[-1][0] / history[-2][0])) > 1e-6:
            exponent = float(np.clip(np.log(history[-1][1] / history[-2][1]) / np.log(history[-1][0] / history[-2][0]), 0.5, 2.0))
        gain *= (target / max(value, 1e-9)) ** (1.0 / exponent)
        if not lo <= gain <= hi:
            raise ValueError(f"a target of {target} needs a gain of about {gain:.3g}, outside {lo} to {hi}")
    raise ValueError(f"the gain did not settle within {max_steps} steps for a target of {target} (last value {value:.4g})")


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
