"""FI, feature interactions (docs/EXPERIMENTS.md, "Implementation plan, proposal v1"): how learning changes as the reward depends on the combination of shape and colour rather than on each feature alone.

The reward is one of four rules over the (shape, colour) plane (`fi_terms.py`): a sum of sigmoids (each feature adds its own part: the separable baseline), a product of sigmoids (both must be high), a sigmoid
of one feature times a Gaussian of the other (a high gate and an interior value), and a tilted, elongated Gaussian (not separable). Both features are always visible and dealt over the plane evenly
(`featureCoverage`); the ground varies and pays nothing. The sparsity, the share of the plane in the top X_PERCENT of the reward range, is matched to TARGET_SPARSITY across all the rules (each draw solves
its free parameter for it). The sigmoid rules come at two steepnesses (shallow, nearly linear over the range; steep, nearly a step), the bump at one elongation, ITERATIONS instances of each cell:

  SUM  sum of sigmoids, shallow and steep          PRD  product of sigmoids, shallow and steep
  SGA  sigmoid x Gaussian, shallow and steep       BMP  tilted bump

Every number a pilot may move (the target sparsity and its region, the steepnesses, the lengths, the iterations) is a named constant here (`build_experiment.py FI` rebuilds). Order: the first
iteration of each cell from simple to complex (the shallow sum first), then the later iterations in a seeded random order, so the complexity jumps around. Hints: the first iteration of a sum says the
features add up, of the other rules that the combination matters; later iterations have none. An instance is a world seed and the draw of its roles, directions and positions, taken from the
first world seed whose world puts at least `fi_terms.GUARANTEE` bushes on the high, middle and low parts of the reward. The master seed fixes everything, so the instance list is the same on every build.
"""

from functools import lru_cache

import numpy as np

import fi_terms
import rw_screen
import world
from design import Instance
from design.common import find_world, instruction_page
from design.FN import TERRACE

CODE = "FI"
TITLE = "Feature Interactions"
REQUIRES = ("TUT",)
TEMPLATE_SESSION = "FN_S1"          # copied only when an instance has no asset yet (the terrain, lighting and so on come from it)
TEMPLATE_INTERLUDE = "FN_I1"

MASTER_SEED = 501
FIRST_WORLD_SEED = 3001
REWARD_STD = 0.6
MAX_ATTEMPTS = 20                    # world seeds tried for an instance (they are 100 apart per instance)

TARGET_SPARSITY = 0.30               # the share of the plane in the top X_PERCENT% of the reward range, matched across the rules (PI: to be tuned by playing)
X_PERCENT = 40
ITERATIONS = 3
SHALLOW, STEEP = 4.0, 30.0           # sigmoid steepness per unit of the feature (fi_terms jitters it a little per instance)
SUM_SECONDS, OTHER_SECONDS = 120, 150
# The cells in play order of the first pass (simple to complex): (id, rule kind, level name, steepness or None, seconds).
CELLS = (("SUM-shallow", "sum", "shallow", SHALLOW, SUM_SECONDS), ("SUM-steep", "sum", "steep", STEEP, SUM_SECONDS),
         ("PRD-shallow", "product", "shallow", SHALLOW, OTHER_SECONDS), ("PRD-steep", "product", "steep", STEEP, OTHER_SECONDS),
         ("SGA-shallow", "sigmoid_gaussian", "shallow", SHALLOW, OTHER_SECONDS), ("SGA-steep", "sigmoid_gaussian", "steep", STEEP, OTHER_SECONDS),
         ("BMP", "bump", "", None, OTHER_SECONDS))
INTERLUDE_TRIALS = 20                # every session alike, so the count gives nothing away
INTERACTION_TRIALS = 17              # distinct pairs of the rule's classes (`interlude.INTERACTION_PLANS`) ...
REPEATS = 3                          # ... and exact repeats

HINT_SUM = "**Bush shape** and **fruit color** each add their own part to the reward."
HINT_COMBINATION = "The reward depends on the **combination** of **bush shape** and **fruit color**, not on each alone."


def cells():
    """Every session cell: dicts with the id, the rule kind, the level, the steepness, the length and the iteration, the first iterations in the order of CELLS."""
    return [{"id": cid, "kind": kind, "level": level, "steepness": k, "seconds": seconds, "iteration": it + 1}
            for it in range(ITERATIONS) for cid, kind, level, k, seconds in CELLS]


def play_order():
    """The first iteration of each cell in the order of CELLS, then the later iterations shuffled by the master seed."""
    cs = cells()
    first = [c for c in cs if c["iteration"] == 1]
    later = [c for c in cs if c["iteration"] > 1]
    rng = np.random.default_rng(MASTER_SEED)
    return first + [later[i] for i in rng.permutation(len(later))]


def hint(cell):
    """The hint of a session: the first iteration of a sum says the features add up, of the other rules that the combination matters; later iterations have none."""
    if cell["iteration"] > 1:
        return ""
    return HINT_SUM if cell["kind"] == "sum" else HINT_COMBINATION


@lru_cache(maxsize=None)
def _instances_built():
    """(cell, number, world seed, attempt, instance) for every session in play order: the first world seed whose world puts enough bushes on every part of the reward."""
    out = []
    for number, cell in enumerate(play_order(), start=1):
        def build(seed):
            rng = np.random.default_rng([seed, 11])
            inst = fi_terms.draw_instance(rng, cell["kind"], steepness=cell["steepness"] or SHALLOW, elongation=fi_terms.ELONGATION, target=TARGET_SPARSITY, x=X_PERCENT)
            params = rw_screen.session_params(inst, TEMPLATE_SESSION)
            params.moisture_varies = True
            w = world.generate_world(params, seed)
            return inst if fi_terms.check_regions(inst, w.shape, w.color) else None
        seed, attempt, inst = find_world(number, FIRST_WORLD_SEED, MAX_ATTEMPTS, build, cell["id"])
        out.append((cell, number, seed, attempt, inst))
    return tuple(out)


def _fields(inst, seed):
    return {"worldSeed": seed, "rewardStd": REWARD_STD, "spatialBalance": 0, "featureBalance": 0, "featureCoverage": 1, **TERRACE, "interludeMode": 4,
            "shapeVaries": True, "colorVaries": True, "moistureVaries": True, "moistureIsFeature": False, **inst.session_fields()}


def _design(cell, number, attempt, inst):
    return {"experiment": CODE, "kind": cell["kind"], "index": number, "cell": cell["id"], "iteration": cell["iteration"], "level": cell["level"], "steepness": cell["steepness"],
            "target_sparsity": TARGET_SPARSITY, "x_percent": X_PERCENT, "world_attempts": attempt + 1, "hint": "none" if not hint(cell) else ("sum" if cell["kind"] == "sum" else "combination"),
            "rule": inst.record}


def instances():
    out = []
    for cell, number, seed, attempt, inst in _instances_built():
        interlude = {"interludeMode": 4, "interludeTrialCount": INTERLUDE_TRIALS, "interludeRepeatCount": REPEATS, "interludeFeatureTrials": 0, "interludePeakTrials": 0,
                     "interludeInteractionTrials": INTERACTION_TRIALS}
        out.append(Instance(f"{CODE}_S{number}", _fields(inst, seed),
                            {"sessionDuration": cell["seconds"], "instructionsFile": f"Experiments/{CODE}/instructions_S{number}.txt", "isPractice": False},
                            interlude, _design(cell, number, attempt, inst), f"Experiments/{CODE}/instructions_interlude.txt"))
    return out


INTERLUDE_TEXT = "Choose the best fruit\n\nChoose the better bush based on what you learned in the last part.\nCorrect choices will earn hidden points.\n\nPress [Enter] to begin\n"


def texts():
    out = {f"instructions_S{number}.txt": instruction_page(hint(cell)) for cell, number, *_ in _instances_built()}
    out["instructions_interlude.txt"] = INTERLUDE_TEXT
    return out
