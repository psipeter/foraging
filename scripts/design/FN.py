"""FN, feature number (docs/EXPERIMENTS.md): how learning slows as more features are visible (V) and more of them pay (R).

Baseline cells with R <= V (PI, 2026-11-09), each played ITERATIONS times: row R=1 (V = 1, 2, 3), row R=2 (V = 2, 3; the paying features weigh equally, the hint says only two
matter). Then the weighted sessions, all three features visible and paying (R = 3), the weights summing to one over the WEIGHT_RATIOS family. Order: one pass through row 1, then
row 2, then the first weighted session, then every remaining session in a seeded random order. Within a cell the iterations are counterbalanced over the features (each feature pays,
or is the one that does not, once). Duration: BASE_SECONDS at (V1, R1) plus 15 s per extra visible feature and 30 s per extra rewarded one. Every mapping is linear; which end of a feature pays is drawn per
instance. Moisture is a feature like the other two: where it is not visible the valley is flat and one colour.

PROVISIONAL numbers, all in this module so they can change in one place (docs/EXPERIMENTS.md lists them as open): the weight family, durations, Interlude counts, the reward
scale, the iteration counts. The master seed fixes the draws, so the instance list is the same on every build.
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
# Each visible feature (shape, colour) balanced over the map on its own, the same way for each (PI, 2026-11-09): reward balancing (spatialBalance) made the rewarded feature much
# more regular than the others, a layout cue to which feature pays, and coupled shape and colour to the moisture patches. Scales 40 to 240 world units, target 0.7 (a local spread of
# about 0.8 of chance: even, not conspicuously regular).
FEATURE_BALANCE = {"featureBalance": 2, "featureBalanceTarget": 0.7, "featureBalanceScales.Array.size": 4, "featureBalanceScales.Array.data[0]": 40.0,
                   "featureBalanceScales.Array.data[1]": 60.0, "featureBalanceScales.Array.data[2]": 120.0, "featureBalanceScales.Array.data[3]": 240.0}
TERRACE = {"moistureTerraceMode": 2, "moistureTerraceLevels": 0, "moistureTerraceSharpness": 0.7, "moistureTerraceResidual": 0.03, "moistureTerraceUnevenness": 0.0,
           "terrainNoiseFrequency": 3.0,
           "terraceMeanWidth": 0.14, "terraceWidthSpread": 0.7, "terraceMaxBand": 0.3, "terraceMinStep": 0.08, "terracePhaseShift": 0.4, "terracePhaseFrequency": 0.6,
           "terraceStrength": 1.0, "terraceDiffusionIterations": 500, "terraceDiffusionEdge": 0.1}      # the ground (PI, 2026-11-09): the Diffusion mode (edge-preserving diffusion of a smooth field: flat regions with soft slopes and steps), noise frequency 3 (PI, 2026-11-09; small regions of one to three bushes, steep edges), the other terrace fields at their defaults (the Staircase ones unused here)
# The weighted sessions: weights proportional to (1, r, r^2) over a random ranking of the features; r = 1 is equal weights, small r a strong feature and two weak ones.
WEIGHT_RATIOS = (1.0, 0.7, 0.5, 0.35, 0.2, 0.1)
ITERATIONS = 3                      # of each baseline cell (the weighted sessions are WEIGHT_RATIOS, one each)
BASE_SECONDS = 60                   # the (V1, R1) cell
VISIBLE_STEP_SECONDS = 15           # per extra visible feature (column V)
REWARDED_STEP_SECONDS = 30          # per extra rewarded feature (row R)
BASELINE_CELLS = ((1, 1), (2, 1), (3, 1), (2, 2), (3, 2))        # (V, R), in the order of the first pass
BASELINE_INTERLUDE = {1: {"interludeTrialCount": 5, "interludeRepeatCount": 0, "interludeFeatureTrials": 1},
                      2: {"interludeTrialCount": 10, "interludeRepeatCount": 0, "interludeFeatureTrials": 1}}      # by R
WEIGHTED_INTERLUDE = {"interludeTrialCount": 20, "interludeRepeatCount": 2, "interludeFeatureTrials": 2}


# The sessions whose Interlude is a ranking (docs/DECISIONS.md, "The ranking Interlude"): a set of bushes on a flat stage with one moisture, so only sessions in which shape and colour
# are the only features that pay can have one. The others are still pairs until the design moves off moisture (PI, 2026-11-12: a later task).
RANKING_INTERLUDES = (1,)
RANKING_INTERLUDE = {"interludeFormat": 1, "interludeTrialSeconds": 30, "interludeSetSize": 5, "interludeSetCount": 3, "interludeArcSpan": 84.0, "interludeRankingDistance": 16.0}


def seconds(n_visible, n_rewarded):
    return BASE_SECONDS + VISIBLE_STEP_SECONDS * (n_visible - 1) + REWARDED_STEP_SECONDS * (n_rewarded - 1)


NAMES = {"shape": "bush shape", "color": "fruit color", "moisture": "elevation"}     # what a participant reads for each feature
HINT_WEIGHTED = "**All three features** matter, but some matter more than others."


def baseline_hint(visible, n_rewarded):
    """What the baseline hint says: one visible feature pays (named); two are visible and both pay; all three are visible and one, or two, pay.
    The essential words (the quantifier and the named features) are marked **bold**; the game shows them in bold teal (UiStyle.Chips)."""
    names = [f"**{NAMES[f]}**" for f in FEATURES if f in visible]
    if n_rewarded == 2:
        return f"**Both** the {names[0]} and the {names[1]} determine how many points a fruit gives." if len(names) == 2 else "**Two** of the **three features** determine how many points a fruit gives."
    if len(names) == 1:
        subject = f"The {names[0]}"
    elif len(names) == 2:
        subject = f"**Either** the {names[0]} or the {names[1]}"
    else:
        subject = f"**One** of the {names[0]}, the {names[1]} or the {names[2]}"
    return f"{subject} determines how many points a fruit gives."


def _cells():
    """The ordered cells of the design (see the module docstring)."""
    rng = np.random.default_rng(MASTER_SEED)
    base = {}                                                     # (V, R) -> its ITERATIONS cells
    for v, r in BASELINE_CELLS:
        perm = [str(f) for f in rng.permutation(FEATURES)]        # iteration k: perm[k] pays (R=1) or is the feature left out of the paying pair (R=2)
        cells = []
        for k in range(ITERATIONS):
            if r == 1:
                paying = [perm[k]]
                visible = {1: paying, 2: paying + [perm[(k + 1) % 3]], 3: list(FEATURES)}[v]     # the pairs of V=2 are each used once
            else:
                paying = [f for f in FEATURES if f != perm[k]]
                visible = paying if v == 2 else list(FEATURES)
            cells.append({"kind": "baseline", "n_visible": v, "n_rewarded": r, "iteration": k + 1, "visible": [f for f in FEATURES if f in visible],
                          "weights": {f: 1.0 / r for f in paying}})
        base[(v, r)] = cells
    weighted = []
    for idx in rng.permutation(len(WEIGHT_RATIOS)):
        ratio = WEIGHT_RATIOS[idx]
        ranking = [str(f) for f in rng.permutation(FEATURES)]        # strongest first
        raw = np.array([1.0, ratio, ratio ** 2])
        weighted.append({"kind": "weighted", "n_visible": 3, "n_rewarded": 3, "iteration": len(weighted) + 1, "visible": list(FEATURES), "ratio": ratio,
                         "weights": {f: float(w) for f, w in zip(ranking, raw / raw.sum())}})
    first = [base[c][0] for c in BASELINE_CELLS] + [weighted[0]]
    rest = [c for cells in base.values() for c in cells[1:]] + weighted[1:]
    cells = first + [rest[i] for i in rng.permutation(len(rest))]
    for cell in cells:
        cell["direction"] = {f: int(rng.integers(2)) for f in FEATURES}      # 0: higher pays more, 1: lower pays more
    return cells


def _component(cell, feature):
    weight = cell["weights"].get(feature, 0.0)
    return {"basisFunctionType": cell["direction"][feature], "weight": round(REWARD_SCALE * weight, 4), "peak": 0, "width": 0}


def _fields(cell, seed):
    visible = set(cell["visible"])
    f = {"worldSeed": seed, "rewardStd": REWARD_STD, "spatialBalance": 0, **FEATURE_BALANCE, **TERRACE, "interludeMode": 4,
         "shapeVaries": "shape" in visible, "colorVaries": "color" in visible, "moistureVaries": "moisture" in visible,
         "moistureIsFeature": "moisture" in visible, "rewardFunction.bumps.Array.size": 0, "rewardFunction.products.Array.size": 0}
    for feature in FEATURES:
        for key, value in _component(cell, feature).items():
            f[f"rewardFunction.{feature}Component.{key}"] = value
    return f


def _design(cell, number):
    std = {f: round(REWARD_SCALE * w / REWARD_STD, 3) for f, w in cell["weights"].items()}      # a feature's whole range of reward, in units of the per-fruit noise
    out = {"experiment": CODE, "kind": cell["kind"], "index": number, "n_visible": cell["n_visible"], "n_rewarded": cell["n_rewarded"], "iteration": cell["iteration"], "visible": cell["visible"],
           "weights": {f: round(w, 4) for f, w in cell["weights"].items()}, "direction": cell["direction"], "noise_units": std,
           "hint": "weighted" if cell["kind"] == "weighted" else ("two" if cell["n_rewarded"] == 2 else "named")}
    if "ratio" in cell:
        out["ratio"] = cell["ratio"]
    return out


def instances():
    out = []
    for number, cell in enumerate(_cells(), start=1):
        baseline = cell["kind"] == "baseline"
        duration = seconds(cell["n_visible"], cell["n_rewarded"])
        text = f"instructions_S{number}.txt" if baseline else "instructions_weighted.txt"
        ranked = number in RANKING_INTERLUDES
        out.append(Instance(f"{CODE}_S{number}", _fields(cell, FIRST_WORLD_SEED + number - 1),
                            {"sessionDuration": duration, "instructionsFile": f"Experiments/{CODE}/{text}", "isPractice": False},
                            {"interludeMode": 4, **(BASELINE_INTERLUDE[cell["n_rewarded"]] if baseline else WEIGHTED_INTERLUDE), **(RANKING_INTERLUDE if ranked else {})},
                            _design(cell, number), f"Experiments/{CODE}/instructions_{'ranking' if ranked else 'interlude'}.txt"))
    return out


INTERLUDE_TEXT = "Choose the best fruit\n\nChoose the better bush based on what you learned in the last part.\nCorrect choices will earn hidden points.\n\nPress [Enter] to begin\n"


RANKING_TEXT = "Ranking phase\n\nHarvest the bushes in order from most to least points, based on what you learned in the last part.\n\nPress [Enter] to begin\n"


def _page(hint):
    return f"Find the best fruit\n\nThis is a new area.\n{hint}\nCollect as many points as you can.\n\nPress [Enter] to begin"


def texts():
    out = {f"instructions_S{n}.txt": _page(baseline_hint(c["visible"], c["n_rewarded"])) for n, c in enumerate(_cells(), start=1) if c["kind"] == "baseline"}
    out["instructions_weighted.txt"] = _page(HINT_WEIGHTED)
    out["instructions_interlude.txt"] = INTERLUDE_TEXT
    out["instructions_ranking.txt"] = RANKING_TEXT
    return out
