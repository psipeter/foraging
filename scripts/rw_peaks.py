"""The peak model of the sparse-reward experiment (RW, docs/EXPERIMENTS.md): the reward is one Gaussian peak, or two (a local and a global maximum), over the one or two
features that pay.

A peak is a `bump` of the reward function (`world.bush_value`: a centre in (shape, color), a height and a spread along each axis). A peak over one feature is a bump with a very
wide spread (DECORATION_SPREAD) along the other axis, which then does not change the reward: the other feature is decoration. Features run from 0 to 1, so a spread is a fraction
of the feature's range.

    spread          the standard deviation of a peak along each paying feature (the same for every peak of an instance)
    separation      the distance between the two peaks' centres, in spreads (at least MIN_SEPARATION: nearer, the two hills merge into one)
    height_ratio    the local peak's height over the global peak's (strictly between 0 and 1)
    margin          a peak's centre is at least MARGIN_SPREADS spreads from each end of a feature's range, so the reward at the nearer extreme is at most a third of the peak's
                    height: a visible decline between the peak and the extreme (a peak at an edge behaves like a linear mapping)
    sparsity(x)     the fraction of the feature interval (one feature pays) or plane (two) whose reward is in the top x% of the reward range; reported at x = 10, 20 and 30 (SPARSITY_X)

`draw_peaks` draws an instance from a seeded generator, `Peaks.reward_function()` and `Peaks.session_fields()` give what goes into a session, `describe` the record of what an instance
is (sparsity, realised separation and height ratio), `spread_for_sparsity` the spread that gives a stated sparsity, so that one-feature and two-feature instances can be put on one
scale. Plane coverage of the bushes and the typed Interlude trials are the next phases.
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

import world

REWARD_SCALE = 4.0                                   # the global peak's height: the best bush pays about this per fruit, as in every built experiment
DECORATION_SPREAD = 1000.0                           # the spread along a feature that does not pay: the reward is flat along it
MARGIN_SPREADS = math.sqrt(2.0 * math.log(3.0))      # exp(-MARGIN_SPREADS ** 2 / 2) = 1/3
MAX_SPREAD = 1.0 / (2.0 * MARGIN_SPREADS)            # a wider peak leaves no allowed box for its centre (and so caps how sparse-free an instance can be: see max_sparsity)
MIN_SEPARATION = 3.0                                 # in spreads
MIN_PEAK_BUSHES = 5                                  # every peak of a built world holds at least this many bushes in its top-10% region (checked by `check_peak_bushes`)
NARROWEST_EXPECTED = 10                              # the narrowest peak is expected to hold this many: with the plane-coverage draw, over 300 placements the fewest was 7 (an independent draw: 2)
SPARSITY_X = (10, 20, 30)
FEATURES = ("shape", "color")
_GRID = {1: 2001, 2: 501}                            # points per axis of the grid the measures use


@dataclass(frozen=True)
class Peaks:
    paying: tuple          # ("shape",), ("color",) or ("shape", "color"): the features that pay
    spread: float          # of each peak along each paying feature
    centers: tuple         # one tuple per peak (a position for each paying feature, in the order of `paying`), the global peak first
    heights: tuple         # each peak's height (the reward at its centre when no other peak is near), the global first

    @property
    def dims(self):
        return len(self.paying)

    def terms(self):
        """The reward function's `bumps`, one per peak."""
        out = []
        for center, height in zip(self.centers, self.heights):
            position = {feature: 0.5 for feature in FEATURES}                     # a feature that does not pay: any centre, the spread makes it irrelevant
            position.update(dict(zip(self.paying, center)))
            spread = {feature: (self.spread if feature in self.paying else DECORATION_SPREAD) for feature in FEATURES}
            out.append({"centerShape": position["shape"], "centerColor": position["color"], "width": spread["shape"], "widthColor": spread["color"], "height": height})
        return out

    def reward_function(self):
        """The session's reward function: only the peaks (every feature's own component pays nothing)."""
        zero = {"basisFunctionType": 0, "weight": 0.0, "peak": 0.0, "width": 0.0}
        return {"shapeComponent": dict(zero), "colorComponent": dict(zero), "moistureComponent": dict(zero), "bumps": self.terms(), "products": []}

    def session_fields(self):
        """The reward function as the dotted-path fields `build_experiment.py` sets on a session asset (a list is sized first)."""
        fields = {"rewardFunction.bumps.Array.size": len(self.centers), "rewardFunction.products.Array.size": 0}
        for feature in FEATURES + ("moisture",):
            for key, value in (("basisFunctionType", 0), ("weight", 0.0), ("peak", 0.0), ("width", 0.0)):
                fields[f"rewardFunction.{feature}Component.{key}"] = value
        for i, term in enumerate(self.terms()):
            for key, value in term.items():
                fields[f"rewardFunction.bumps.Array.data[{i}].{key}"] = value
        return fields

    def value(self, shape, color):
        """The expected reward of a bush with these features (arrays broadcast)."""
        return world.bush_value(self.reward_function(), shape, color, 0.5)


def margin(spread, margin_spreads=None):
    """How far from each end of a feature's range a peak's centre must be (`margin_spreads` spreads, MARGIN_SPREADS by default)."""
    return (MARGIN_SPREADS if margin_spreads is None else margin_spreads) * spread


def two_hills(separation, ratio):
    """Whether two peaks of this spacing (in spreads) and height ratio are two hills along the line through their centres (and not one merged hill)."""
    t = np.linspace(-6.0, separation + 6.0, 4001)
    g = np.exp(-t * t / 2.0) + ratio * np.exp(-(t - separation) ** 2 / 2.0)
    return int(((g[1:-1] > g[:-2]) & (g[1:-1] > g[2:])).sum()) == 2


def separable(separation, height_ratio):
    """Whether two peaks this far apart (in spreads) and of this height ratio are two hills (a small ratio at a small separation is a shoulder of the global peak, not a peak)."""
    return separation >= MIN_SEPARATION and two_hills(separation, height_ratio)


def fits(spread, dims, separation, margin_spreads=None):
    """Whether two peaks `separation` spreads apart fit inside the allowed box of a peak of this spread (the box is `margin` from each end; the diagonal of a plane is sqrt 2 longer)."""
    return separation * spread <= (1.0 - 2.0 * margin(spread, margin_spreads)) * (1.0 if dims == 1 else math.sqrt(2.0))


def draw_peaks(rng, paying, n_peaks, spread, separation=None, height_ratio=None, scale=REWARD_SCALE, margin_spreads=None):
    """An instance: where the peak (or the two peaks) are, drawn from `rng`. The global peak is uniform in the allowed box (`margin` from each end); the local one is `separation`
    spreads away in a random direction, inside the box too. Raises ValueError for a spread so wide that there is no allowed box, two peaks that merge, or no room for the two."""
    paying = tuple(paying)
    if not paying or not set(paying) <= set(FEATURES) or len(set(paying)) != len(paying):
        raise ValueError(f"the features that pay must be shape, color or both, not {paying}")
    if n_peaks not in (1, 2):
        raise ValueError("an instance has one or two peaks")
    lo, hi = margin(spread, margin_spreads), 1.0 - margin(spread, margin_spreads)
    if not hi > lo:
        raise ValueError(f"a spread of {spread} leaves no room for a peak at {MARGIN_SPREADS:.2f} spreads from each end")
    dims = len(paying)
    if n_peaks == 1:
        first = rng.uniform(lo, hi, dims)
        return Peaks(paying, float(spread), (tuple(float(v) for v in first),), (float(scale),))
    if separation is None or height_ratio is None or not 0.0 < height_ratio < 1.0:
        raise ValueError("two peaks need a separation (in spreads) and a height ratio strictly between 0 and 1")
    if separation < MIN_SEPARATION or not two_hills(separation, height_ratio):
        raise ValueError(f"two peaks {separation} spreads apart with a height ratio of {height_ratio} merge into one hill (the least separation is {MIN_SEPARATION})")
    distance = separation * spread
    if not fits(spread, dims, separation, margin_spreads):
        raise ValueError(f"no room for two peaks {distance:.3f} apart inside the allowed box [{lo:.3f}, {hi:.3f}]")
    first, second = _place_two(rng, dims, lo, hi, distance)
    return Peaks(paying, float(spread), (tuple(float(v) for v in first), tuple(float(v) for v in second)), (float(scale), float(scale * height_ratio)))


def _place_two(rng, dims, lo, hi, distance):
    """Two centres `distance` apart, both inside [lo, hi] on every axis, uniform over all such pairs. A direction is drawn with the weight of the room it leaves (the area of the
    positions from which the second centre is still inside), then the first centre uniformly in that room: this never fails, however close `distance` is to the largest that fits
    (drawing a position and trying a direction, as an earlier version did, almost never succeeded there)."""
    width = hi - lo
    if dims == 1:
        sign = rng.choice([-1.0, 1.0])
        start, stop = lo + max(0.0, -sign * distance), hi - max(0.0, sign * distance)
        first = rng.uniform(start, max(start, stop))                                  # (rounding can put the stop a hair below the start when the distance is exactly the largest)
        return np.array([first]), np.array([first + sign * distance])
    angle = math.pi / 4.0 + (math.pi / 2.0) * int(rng.integers(4))             # the diagonal: all that fits when the distance is the largest there is
    for _ in range(100):
        trial = rng.uniform(0.0, 2.0 * math.pi, 20000)
        room = np.maximum(width - distance * np.abs(np.cos(trial)), 0.0) * np.maximum(width - distance * np.abs(np.sin(trial)), 0.0)
        accepted = np.nonzero(rng.uniform(0.0, width * width, trial.shape) < room)[0]
        if len(accepted):
            angle = float(trial[accepted[0]])
            break
    direction = np.array([math.cos(angle), math.sin(angle)])
    start, stop = lo + np.maximum(0.0, -distance * direction), hi - np.maximum(0.0, distance * direction)
    first = rng.uniform(start, np.maximum(start, stop))
    return first, first + distance * direction


def reward_on_grid(peaks, n=None):
    """The expected reward over the feature interval (one feature pays: along that feature) or the plane (an (n, n) array, shape along the first axis)."""
    n = n or _GRID[peaks.dims]
    axis = np.linspace(0.0, 1.0, n)
    if peaks.dims == 1:
        return peaks.value(*((axis, 0.5) if peaks.paying == ("shape",) else (0.5, axis)))
    s, c = np.meshgrid(axis, axis, indexing="ij")
    return peaks.value(s, c)


def sparsity(peaks, x, n=None):
    """The fraction of the feature interval or plane whose reward is in the top x% of the reward range (x in percent)."""
    v = reward_on_grid(peaks, n)
    threshold = v.min() + (1.0 - x / 100.0) * (v.max() - v.min())
    return float((v >= threshold).mean())


def spread_for_sparsity(target, dims, x=20):
    """The spread of a single peak that has sparsity `target` at x (closed form, exact when the reward range starts at zero, which a narrow peak's does to a good approximation):
    the region above the threshold is a segment (one feature) or a disc (two) of half-width spread * sqrt(-2 ln(1 - x/100))."""
    k = math.sqrt(-2.0 * math.log(1.0 - x / 100.0))
    return target / (2.0 * k) if dims == 1 else math.sqrt(target / math.pi) / k


def sparsity_for_spread(spread, dims, x=20):
    """The sparsity at x of a single peak of this spread (the inverse of `spread_for_sparsity`)."""
    k = math.sqrt(-2.0 * math.log(1.0 - x / 100.0))
    return 2.0 * spread * k if dims == 1 else math.pi * (spread * k) ** 2


def max_sparsity(dims, x=20):
    """The largest sparsity at x that the margin allows a single peak: at x = 10, 0.31 of an interval and 0.075 of a plane (at x = 30, 0.57 and 0.25)."""
    return sparsity_for_spread(MAX_SPREAD, dims, x)


def realized(peaks):
    """The hills the reward really has: [(height, position tuple)] of the (at most) two highest local maxima, highest first, found on the grid. A sum of two near peaks is a little
    higher than either alone, so these differ slightly from `heights` and `centers`."""
    v = reward_on_grid(peaks)
    is_max = ndimage.maximum_filter(v, size=3, mode="nearest") == v
    is_max &= v > v.min() + 0.05 * (v.max() - v.min())
    n = v.shape[0]
    found = sorted(((float(v[idx]), tuple(float(i) / (n - 1) for i in idx)) for idx in zip(*np.nonzero(is_max))), reverse=True)
    out = []
    for value, position in found:                                            # a flat top is several adjacent points: keep one per hill
        if all(math.dist(position, p) > peaks.spread for _, p in out):
            out.append((value, position))
        if len(out) == 2:
            break
    return out


def describe(peaks):
    """The record of an instance for its `design` dict: where the peaks are, the sparsity at each x, and for two peaks the realised separation (in spreads) and height ratio."""
    out = {"paying": list(peaks.paying), "spread": peaks.spread, "centers": [list(c) for c in peaks.centers], "heights": list(peaks.heights),
           "sparsity": {str(x): round(sparsity(peaks, x), 4) for x in SPARSITY_X}}
    if len(peaks.centers) == 2:
        (top, p_top), (low, p_low) = realized(peaks)
        out["separation"] = round(math.dist(p_top, p_low) / peaks.spread, 3)
        out["height_ratio"] = round(low / top, 4)
    return out


def peak_regions(peaks, shape, color, x=10):
    """For each peak, a boolean array over the bushes (their shape and colour arrays): the bush lies in the region where that peak alone is within the top x% of its own height,
    a segment around its centre (one feature pays) or a disc (two). These are the bushes that show a participant the peak is there."""
    half_width = peaks.spread * math.sqrt(-2.0 * math.log(1.0 - x / 100.0))
    out = []
    for center in peaks.centers:
        if peaks.dims == 1:
            coordinate = shape if peaks.paying == ("shape",) else color
            out.append(np.abs(coordinate - center[0]) <= half_width)
        else:
            out.append(np.hypot(shape - center[0], color - center[1]) <= half_width)
    return out


def bush_counts(peaks, shape, color, x=10):
    """For each peak, how many bushes lie in its top-x% region (`peak_regions`)."""
    return [int(region.sum()) for region in peak_regions(peaks, shape, color, x)]


def narrowest_spread(n_bushes, dims, minimum, x=10):
    """The narrowest spread whose peak is expected to hold `minimum` bushes at x out of `n_bushes` spread evenly over the feature space (expected = n_bushes * sparsity)."""
    return spread_for_sparsity(minimum / n_bushes, dims, x)


def check_peak_bushes(shape, color, peaks, minimum=MIN_PEAK_BUSHES, x=10):
    """Raises ValueError if a peak holds fewer than `minimum` bushes in its top-x% region (the design module builds the world and tries another seed); returns the counts."""
    counts = bush_counts(peaks, shape, color, x)
    if min(counts) < minimum:
        raise ValueError(f"a peak holds only {min(counts)} bushes in its top-{x}% region (at least {minimum} are needed): choose another world seed or a wider spread")
    return counts
