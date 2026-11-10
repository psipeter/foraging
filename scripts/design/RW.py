"""RW, sparse rewards (docs/EXPERIMENTS.md, "Session plan, draft v9"): how learning, finding and settling change as the good bushes get rarer and a second, lower peak appears.

The reward is a sum of Gaussian peaks over the (shape, colour) plane (`rw_peaks.py`); both features are always visible and dealt over the plane evenly (`featureCoverage`), moisture is flat. A
peak's spread follows from its sparsity, the share of all the bushes that pay at least 70% of the best; with two peaks the total is split equally. Stages:

  B  baseline, once each (the teaching sessions, fixed order): one and two paying features by one and two peaks at 15%
  S  one peak, two paying features, S_LEVELS sparsities, ITERATIONS each
  T  two peaks, two paying features, T_LEVELS sparsities, ITERATIONS each, the height ratio and the separation fixed (T_RATIO, T_SEPARATION)

Every number a pilot may move (the sparsity levels, the session lengths, the ratio, the separation, the iterations) is a named constant here: the pilot measures how much slower people are than the
agents, and the ladder is then fixed in advance and rebuilt (`build_experiment.py RW`). Order: B in order, then one pass through the six S and T cells, then the remaining sessions, both passes in a seeded
random order. An instance is a world seed and the draw of its peaks (their centres, a one-feature session alternating which feature pays), taken from the first world seed whose world holds at least
GUARANTEE_BUSHES bushes in every peak's top-30% region. The master seed fixes everything, so the instance list is the same on every build.
"""

from functools import lru_cache

import numpy as np

import rw_peaks
import rw_screen
import world
from design import Instance
from design.FN import TERRACE

CODE = "RW"
TITLE = "Sparse Rewards"
REQUIRES = ("TUT",)
TEMPLATE_SESSION = "FN_S1"          # copied only when an instance has no asset yet (the terrain, lighting and so on come from it)
TEMPLATE_INTERLUDE = "FN_I1"

MASTER_SEED = 401
FIRST_WORLD_SEED = 401
REWARD_STD = 0.6
MAX_ATTEMPTS = 20                    # world seeds tried for an instance (they are 100 apart per instance)
GUARANTEE_BUSHES = 3                 # in each peak's top-30% region; `rw_screen.DESIGN_GUARANTEE`
GUARANTEE_REGION = 30

ITERATIONS = 3                       # of each S and T cell
S_LEVELS = (15, 10, 5)               # total sparsity, percent
T_LEVELS = (15, 11, 7)
S_SECONDS = T_SECONDS = 180
T_RATIO = 0.5                        # local peak height over the global peak's
T_SEPARATION = 4.5                   # in spreads
T_MARGIN = 1.0                       # how far from the end of a feature a peak's centre is, in spreads (the default 1.48 does not fit two features at 15%)
# The baseline: (id, paying features, peaks, total sparsity %, seconds, separation in spreads or None, margin in spreads or None for the default).
BASELINE = (("B1", 1, 1, 15, 120, None, None), ("B2", 2, 1, 15, 120, None, None),
            ("B3", 1, 2, 15, 120, 3.0, None), ("B4", 2, 2, 15, 120, 3.0, None))
INTERLUDE_TRIALS = {(1, 1): 5, (2, 1): 10}        # one-peak sessions: (paying features, peaks) -> trials (the hybrid mode); two-peak sessions are all peak trials
PEAK_TRIALS = 20

HINT_ONE = "Only **one** of the **bush shape** or the **fruit color** matters."
HINT_TWO = "**Both** the **bush shape** and the **fruit color** matter."
HINT_PEAKS = "There are **two kinds** of valuable bush, and one is better than the other."
HINT_SPARSE = "Most bushes give few points: look for the **valuable ones**."


def cells():
    """Every session cell of the design, in the order of the tables: dicts with the id, stage, paying features, peaks, total sparsity, length, separation, ratio, margin and iteration."""
    out = []
    for cid, dims, peaks, total, seconds, separation, margin in BASELINE:
        out.append({"id": cid, "stage": "B", "dims": dims, "n_peaks": peaks, "total": total / 100, "seconds": seconds, "separation": separation,
                    "ratio": T_RATIO if peaks == 2 else None, "margin": margin, "iteration": 1})
    for stage, levels, peaks, seconds in (("S", S_LEVELS, 1, S_SECONDS), ("T", T_LEVELS, 2, T_SECONDS)):
        for level in levels:
            for k in range(ITERATIONS):
                out.append({"id": f"{stage}2F-{level}", "stage": stage, "dims": 2, "n_peaks": peaks, "total": level / 100, "seconds": seconds,
                            "separation": T_SEPARATION if peaks == 2 else None, "ratio": T_RATIO if peaks == 2 else None, "margin": T_MARGIN if peaks == 2 else None,
                            "iteration": k + 1})
    return out


def play_order():
    """The cells in play order: B as listed, one pass through the S and T cells (their first iterations), then the rest, both passes shuffled by the master seed."""
    rng = np.random.default_rng(MASTER_SEED)
    cs = cells()
    base = [c for c in cs if c["stage"] == "B"]
    rest = [c for c in cs if c["stage"] != "B"]
    first = [c for c in rest if c["iteration"] == 1]
    later = [c for c in rest if c["iteration"] > 1]
    return base + [first[i] for i in rng.permutation(len(first))] + [later[i] for i in rng.permutation(len(later))]


@lru_cache(maxsize=None)
def _instances_built():
    """(cell, number, world seed, peaks) for every session in play order: the first world seed whose world gives every peak its bushes."""
    out, one_feature = [], 0
    for number, cell in enumerate(play_order(), start=1):
        if cell["dims"] == 1:
            paying = ("shape", "color")[one_feature % 2]               # a one-feature peak alternates between the features over the instances
            one_feature += 1
        else:
            paying = None
        spread = rw_peaks.spread_for_sparsity(cell["total"] / cell["n_peaks"], cell["dims"], 30)
        if cell["n_peaks"] == 2 and not (rw_peaks.fits(spread, cell["dims"], cell["separation"], cell["margin"]) and rw_peaks.separable(cell["separation"], cell["ratio"])):
            raise ValueError(f"{cell['id']}: two peaks {cell['separation']} spreads apart at a ratio of {cell['ratio']} do not fit at a spread of {spread:.3f}")
        for attempt in range(MAX_ATTEMPTS):
            seed = FIRST_WORLD_SEED + 100 * number + attempt
            rng = np.random.default_rng([seed, 7])
            peaks = rw_peaks.draw_peaks(rng, ("shape", "color") if paying is None else (paying,), cell["n_peaks"], spread, cell["separation"], cell["ratio"], margin_spreads=cell["margin"])
            w = world.generate_world(rw_screen.session_params(peaks, TEMPLATE_SESSION), seed)
            if min(rw_peaks.bush_counts(peaks, w.shape, w.color, GUARANTEE_REGION)) >= GUARANTEE_BUSHES:
                break
        else:
            raise RuntimeError(f"{cell['id']} (session {number}): no world seed in {MAX_ATTEMPTS} gave every peak {GUARANTEE_BUSHES} bushes")
        out.append((cell, number, seed, attempt, peaks, spread))
    return tuple(out)


def hint(cell, first_two_peak):
    """The hint of a session: the features that matter, and for the first two-peak sessions (B3, B4) that there are two kinds of valuable bush."""
    parts = [HINT_ONE if cell["dims"] == 1 else HINT_TWO]
    if cell["n_peaks"] == 2 and first_two_peak:
        parts.append(HINT_PEAKS)
    elif cell["stage"] == "B":
        parts.append(HINT_SPARSE)
    return " ".join(parts)


def _hints():
    """session number -> (hint key, hint text)."""
    out = {}
    for cell, number, *_ in _instances_built():
        first = cell["stage"] == "B"
        key = "one" if cell["dims"] == 1 else "two"
        if cell["n_peaks"] == 2 and first:
            key += "_peaks"
        elif first:
            key += "_sparse"
        out[number] = (key, hint(cell, first))
    return out


def _fields(peaks, seed):
    return {"worldSeed": seed, "rewardStd": REWARD_STD, "spatialBalance": 0, "featureBalance": 0, "featureCoverage": 1, **TERRACE, "interludeMode": 4,
            "shapeVaries": True, "colorVaries": True, "moistureVaries": False, "moistureIsFeature": False, **peaks.session_fields()}


def _design(cell, number, seed, attempt, peaks, spread, hint_key):
    record = rw_peaks.describe(peaks)
    return {"experiment": CODE, "kind": cell["stage"], "index": number, "cell": cell["id"], "iteration": cell["iteration"], "n_peaks": cell["n_peaks"], "paying": list(peaks.paying),
            "total_sparsity": cell["total"], "spread": round(spread, 5), "centers": record["centers"], "heights": record["heights"], "sparsity": record["sparsity"],
            "separation": cell["separation"], "height_ratio": cell["ratio"], "margin": cell["margin"], "world_attempts": attempt + 1, "hint": hint_key}


def instances():
    hints = _hints()
    out = []
    for cell, number, seed, attempt, peaks, spread in _instances_built():
        two = cell["n_peaks"] == 2
        interlude = {"interludeMode": 4, "interludeTrialCount": PEAK_TRIALS if two else INTERLUDE_TRIALS[(cell["dims"], 1)], "interludeRepeatCount": 0,
                     "interludeFeatureTrials": 0, "interludePeakTrials": PEAK_TRIALS if two else 0}
        out.append(Instance(f"{CODE}_S{number}", _fields(peaks, seed),
                            {"sessionDuration": cell["seconds"], "instructionsFile": f"Experiments/{CODE}/instructions_S{number}.txt", "isPractice": False},
                            interlude, _design(cell, number, seed, attempt, peaks, spread, hints[number][0]), f"Experiments/{CODE}/instructions_interlude.txt"))
    return out


INTERLUDE_TEXT = "Choose the best fruit\n\nChoose the better bush based on what you learned in the last part.\nCorrect choices will earn hidden points.\n\nPress [Enter] to begin\n"


def _page(hint_text):
    return f"Find the best fruit\n\nThis is a new area.\n{hint_text}\nCollect as many points as you can.\n\nPress [Enter] to begin"


def texts():
    out = {f"instructions_S{n}.txt": _page(text) for n, (_, text) in _hints().items()}
    out["instructions_interlude.txt"] = INTERLUDE_TEXT
    return out
