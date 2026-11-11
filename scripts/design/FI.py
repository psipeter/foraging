"""FI, feature interactions (docs/EXPERIMENTS.md, FI): how learning changes as the reward goes from nearly separable in the shape and colour axes to not separable in them.

The reward is one Gaussian over the (shape, colour) plane (`fi_terms.py`), in three kinds, always with one optimum and the same sparsity (the share of the plane in the top X_PERCENT% of the reward range is
TARGET_SPARSITY, matched by solving each Gaussian's spread):

  CORNER   round, centred at a corner: monotone in both features, close to additive
  MIDDLE   round, centred near the middle: a product of two Gaussians, separable in the axes
  ROTATED  stretched (ELONGATION) and turned (TILT_DEGREES): separable only in its own rotated basis

Both features are always visible and dealt over the plane evenly (`featureCoverage`); the ground varies and pays nothing. The cells have different numbers of iterations (ITERATIONS in CELLS): the rotated
Gaussian, the hardest and most variable, has the most. Every number a pilot may move (the target sparsity and its region, the elongation, the tilt, the length, the iterations) is a named constant here
(`build_experiment.py FI` rebuilds). Order: the first iteration of each cell in the order of CELLS (simple to complex), then the later iterations in a seeded random order. Hint: the first iteration of each
cell says there is one best combination; later iterations have none. An instance is a world seed and the draw of its position and tilt, taken from the first world seed whose world puts at least
`fi_terms.GUARANTEE` bushes on the high, middle and low parts of the reward. The master seed fixes everything, so the instance list is the same on every build.
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

TARGET_SPARSITY = 0.20               # the share of the plane in the top X_PERCENT% of the reward range, matched across the cells (PI: to be tuned by playing)
X_PERCENT = 40
ELONGATION = fi_terms.ELONGATION     # of the rotated Gaussian: its long spread over the short one
TILT_DEGREES = fi_terms.TILT_DEGREES
SECONDS = 150
# The cells in the order of the first pass (simple to complex): (id, kind, iterations). The hardest cell has the most iterations, for better statistics where the sessions vary most.
CELLS = (("CORNER", "corner", 3), ("MIDDLE", "middle", 3), ("ROTATED", "elongated", 6))
INTERLUDE_TRIALS = 20                # every session alike, so the count gives nothing away
INTERACTION_TRIALS = 17              # distinct pairs of the rule's classes (`interlude.INTERACTION_PLANS`) ...
REPEATS = 3                          # ... and exact repeats

HINT = "There is one best **combination** of bush shape and fruit color."


def cells():
    """Every session cell: dicts with the id, the kind, the length and the iteration, the first iterations in the order of CELLS."""
    return [{"id": cid, "kind": kind, "seconds": SECONDS, "iteration": it + 1, "iterations": n} for it in range(max(n for _, _, n in CELLS)) for cid, kind, n in CELLS if it < n]


def play_order():
    """The first iteration of each cell in the order of CELLS, then the later iterations shuffled by the master seed."""
    cs = cells()
    first = [c for c in cs if c["iteration"] == 1]
    later = [c for c in cs if c["iteration"] > 1]
    rng = np.random.default_rng(MASTER_SEED)
    return first + [later[i] for i in rng.permutation(len(later))]


def hint(cell):
    """The hint of a session: the first iteration of a cell says there is one best combination; later iterations have none."""
    return HINT if cell["iteration"] == 1 else ""


CORNERS = ((0, 0), (1, 1), (0, 1), (1, 0))


def _balance(cell):
    """What a design fixes so that it is balanced over the sessions of a cell instead of drawn: the corner of a corner session (the four corners in a seeded order) and the sign of the tilt of a rotated
    one (alternating)."""
    order = np.random.default_rng(MASTER_SEED + 1).permutation(len(CORNERS))
    return {"corner": CORNERS[order[(cell["iteration"] - 1) % len(CORNERS)]] if cell["kind"] == "corner" else None, "tilt_sign": (1.0 if cell["iteration"] % 2 else -1.0) if cell["kind"] == "elongated" else None}


@lru_cache(maxsize=None)
def _instances_built():
    """(cell, number, world seed, attempt, instance) for every session in play order: the first world seed whose world puts enough bushes on every part of the reward."""
    out = []
    for number, cell in enumerate(play_order(), start=1):
        def build(seed):
            rng = np.random.default_rng([seed, 11])
            inst = fi_terms.draw_instance(rng, cell["kind"], target=TARGET_SPARSITY, x=X_PERCENT, elongation=ELONGATION, tilt=TILT_DEGREES, **_balance(cell))
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
    return {"experiment": CODE, "kind": cell["kind"], "index": number, "cell": cell["id"], "iteration": cell["iteration"], "iterations": cell["iterations"],
            "target_sparsity": TARGET_SPARSITY, "x_percent": X_PERCENT, "world_attempts": attempt + 1, "hint": "combination" if hint(cell) else "none", "rule": inst.record}


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
