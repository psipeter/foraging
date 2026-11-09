"""FN, feature number (docs/EXPERIMENTS.md): how learning slows as more features are visible and more of them pay.

Three baseline sessions, simple to complex: one feature pays and one, two or three features are visible. Then weighted sessions, all three features
visible and all able to pay, the three weights summing to one, in a seeded random order. Every mapping is linear; which end of a feature pays and which
feature has which weight are drawn per instance. Moisture is a feature like the other two: where it is not visible the valley is flat and one colour.

PROVISIONAL numbers, all in this module so they can change in one place (docs/EXPERIMENTS.md lists them as open): the weak-weight family (WEIGHT_RATIOS),
durations, Interlude counts, the reward scale. The master seed fixes the draws, so the instance list is the same on every build.
"""

import numpy as np

from design import Instance

CODE = "FN"
TITLE = "Feature Number"
REQUIRES = ("TUT",)
TEMPLATE_SESSION = "FN_S1"          # copied only when an instance has no asset yet
TEMPLATE_INTERLUDE = "FN_I1"

MASTER_SEED = 301
FIRST_WORLD_SEED = 301
FEATURES = ("shape", "color", "moisture")
REWARD_SCALE = 4.0                  # the best bush pays about 4 per fruit when the weights sum to one, as in every earlier session
REWARD_STD = 0.6
# The weighted sessions: weights proportional to (1, r, r^2) over a random ranking of the features; r = 1 is equal weights, small r a strong feature and two weak ones.
WEIGHT_RATIOS = (1.0, 0.7, 0.5, 0.35, 0.2, 0.1)
BASELINE_SECONDS = (60, 75, 90)
WEIGHTED_SECONDS = 150
BASELINE_INTERLUDE = {"interludeTrialCount": 8, "interludeRepeatCount": 0, "interludeFeatureTrials": 1}
WEIGHTED_INTERLUDE = {"interludeTrialCount": 24, "interludeRepeatCount": 2, "interludeFeatureTrials": 2}

NAMES = {"shape": "bush shape", "color": "fruit color", "moisture": "ground moisture"}     # what a participant reads for each feature
HINT_WEIGHTED = "All three features matter, but some matter more than others."


def baseline_hint(visible):
    """The baseline hint names the visible features: one of them determines the points."""
    names = [NAMES[f] for f in FEATURES if f in visible]
    if len(names) == 1:
        subject = f"The {names[0]}"
    elif len(names) == 2:
        subject = f"Either the {names[0]} or the {names[1]}"
    else:
        subject = f"One of the {names[0]}, the {names[1]} or the {names[2]}"
    return f"{subject} determines how many points a fruit gives."


def _cells():
    """The ordered cells of the design: three baselines, then the weighted sessions in a random order."""
    rng = np.random.default_rng(MASTER_SEED)
    paying = [str(f) for f in rng.permutation(FEATURES)]          # which feature pays in the baselines: each feature once
    cells = []
    for k in range(3):
        others = [f for f in FEATURES if f != paying[k]]
        visible = {1: [paying[k]], 2: [paying[k], others[int(rng.integers(2))]], 3: list(FEATURES)}[k + 1]
        cells.append({"kind": "baseline", "n_visible": k + 1, "visible": visible, "weights": {paying[k]: 1.0}})
    order = rng.permutation(len(WEIGHT_RATIOS))
    for idx in order:
        ratio = WEIGHT_RATIOS[idx]
        ranking = [str(f) for f in rng.permutation(FEATURES)]        # strongest first
        raw = np.array([1.0, ratio, ratio ** 2])
        cells.append({"kind": "weighted", "n_visible": 3, "visible": list(FEATURES), "ratio": ratio,
                      "weights": {f: float(w) for f, w in zip(ranking, raw / raw.sum())}})
    for cell in cells:
        cell["direction"] = {f: int(rng.integers(2)) for f in FEATURES}      # 0: higher pays more, 1: lower pays more
    return cells


def _component(cell, feature):
    weight = cell["weights"].get(feature, 0.0)
    return {"basisFunctionType": cell["direction"][feature], "weight": round(REWARD_SCALE * weight, 4), "peak": 0, "width": 0}


def _fields(cell, seed):
    visible = set(cell["visible"])
    f = {"worldSeed": seed, "rewardStd": REWARD_STD, "spatialBalance": 2, "moistureTerraceLevels": 0, "interludeMode": 4,
         "shapeVaries": "shape" in visible, "colorVaries": "color" in visible, "moistureVaries": "moisture" in visible,
         "moistureIsFeature": "moisture" in visible, "rewardFunction.bumps.Array.size": 0, "rewardFunction.products.Array.size": 0}
    for feature in FEATURES:
        for key, value in _component(cell, feature).items():
            f[f"rewardFunction.{feature}Component.{key}"] = value
    return f


def _design(cell, number):
    std = {f: round(REWARD_SCALE * w / REWARD_STD, 3) for f, w in cell["weights"].items()}      # a feature's whole range of reward, in units of the per-fruit noise
    out = {"experiment": CODE, "kind": cell["kind"], "index": number, "n_visible": cell["n_visible"], "visible": cell["visible"],
           "weights": {f: round(w, 4) for f, w in cell["weights"].items()}, "direction": cell["direction"], "noise_units": std,
           "hint": "named" if cell["kind"] == "baseline" else "weighted"}
    if "ratio" in cell:
        out["ratio"] = cell["ratio"]
    return out


def instances():
    out = []
    for number, cell in enumerate(_cells(), start=1):
        baseline = cell["kind"] == "baseline"
        seconds = BASELINE_SECONDS[number - 1] if baseline else WEIGHTED_SECONDS
        text = f"instructions_S{number}.txt" if baseline else "instructions_weighted.txt"
        out.append(Instance(f"{CODE}_S{number}", _fields(cell, FIRST_WORLD_SEED + number - 1),
                            {"sessionDuration": seconds, "instructionsFile": f"Experiments/{CODE}/{text}", "isPractice": False},
                            {"interludeMode": 4, **(BASELINE_INTERLUDE if baseline else WEIGHTED_INTERLUDE)},
                            _design(cell, number), f"Experiments/{CODE}/instructions_interlude.txt"))
    return out


INTERLUDE_TEXT = "Choose the best fruit\n\nChoose the better bush based on what you learned in the last part.\nCorrect choices will earn hidden points.\n\nPress [Enter] to begin\n"


def _page(hint):
    return f"Find the best fruit\n\nThis is a new area.\n{hint}\nCollect as many points as you can.\n\nPress [Enter] to begin"


def texts():
    out = {f"instructions_S{n}.txt": _page(baseline_hint(c["visible"])) for n, c in enumerate(_cells(), start=1) if c["kind"] == "baseline"}
    out["instructions_weighted.txt"] = _page(HINT_WEIGHTED)
    out["instructions_interlude.txt"] = INTERLUDE_TEXT
    return out
