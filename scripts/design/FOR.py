"""FOR, foraging in tiles (prototype, 2026-11-12): the merged experiment that varies the reward function and the spatial arrangement together, in a world of hexagonal tiles with a cluster of bushes
in the middle of each (`tiles.py`). Phases 1 and 2 of the plan only: one instance at a time to see the world in the Editor (the combination of a between-tile mode and a within-tile mode being tried); no Interludes yet (the injected
rankings are a later phase), no difficulty sampling and no spec system (the next phase). Both pay through shape and colour equally (a linear reward over the two).
"""

import world
from design import Instance
from design.common import instruction_page

CODE = "FOR"
TITLE = "Foraging in Tiles"
REQUIRES = ("TUT",)
TEMPLATE_SESSION = "FN_S1"          # copied only when an instance has no asset yet (the lighting, camera and so on come from it)
TEMPLATE_INTERLUDE = "FN_I1"

REWARD_STD = 0.6
REWARD_SCALE = 4.0                  # the best bush pays about this much when the weights sum to one, as in every built experiment
SECONDS = 180
FIRST_WORLD_SEED = 7001
TILE_FIELDS = {"tileRadius": 45.0, "tileRampWidth": 14.0, "tileMoistureLevels": 4, "tileBushes": 9, "tileClusterRadius": 15.0, "tileClusterSpacing": 10.0, "tileSpread": 0.12}
# (id, between mode, within mode, other tile fields): one session, whatever is being tested now; "" leaves the mode to the default (`none` and `pool`: no pattern anywhere). Every combination is a pair
# of table entries (tiles.py BETWEEN_MODES, WITHIN_MODES); tried so far: random-scatter, bimodal-smooth, none-gradient.
CROSSHAIR_RADIUS = 7.0              # the hidden hit circle of the crosshair (degrees; SessionConfig.crosshairRadius)
# a ranking set in place after every patch switch (`SessionConfig.rankingBreak*`; the arc is the interlude* fields: 5 bushes, 16 units, 84 degrees): 20 s a set, one set per break
BREAK_FIELDS = {"rankingBreakEvery": 1, "rankingBreakSets": 1, "rankingBreakSeconds": 20.0, "rankingBreakCooldown": 10.0, "rankingBreakPoolSets": 12, "rankingBreakMinBushes": 1, "rankingBreakSettleDepth": 0.0}
CELLS = (("default", "", "", {}),)


def _fields(between, within, extra, seed):
    f = {"worldSeed": seed, "rewardStd": REWARD_STD, "spatialBalance": 0, "featureBalance": 0, "featureCoverage": 0, "layout": "tiles", "assignment": "tiles", "tileValueMode": between,
         "tileWithinMode": within, "tileArrangement": "random", **{**TILE_FIELDS, **extra}, "terrainMaxElevation": 9.0, "shapeVaries": True, "colorVaries": True, "moistureVaries": True, "moistureIsFeature": False,
         "rewardFunction.bumps.Array.size": 0, "rewardFunction.products.Array.size": 0}
    for feature, weight in (("shape", 0.5), ("color", 0.5), ("moisture", 0.0)):
        f.update({f"rewardFunction.{feature}Component.basisFunctionType": 0, f"rewardFunction.{feature}Component.weight": REWARD_SCALE * weight,
                  f"rewardFunction.{feature}Component.peak": 0, f"rewardFunction.{feature}Component.width": 0})
    return f


def instances():
    return [Instance(f"{CODE}_S{n}", _fields(between, within, extra, FIRST_WORLD_SEED + 100 * n), {"sessionDuration": SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_S{n}.txt", "isPractice": False, "crosshairRadius": CROSSHAIR_RADIUS, **BREAK_FIELDS},
                     None, {"experiment": CODE, "index": n, "cell": cid, "tile_value_mode": between, "tile_within_mode": within, "prototype": True})
            for n, (cid, between, within, extra) in enumerate(CELLS, start=1)]


def texts():
    return {f"instructions_S{n}.txt": instruction_page("") for n in range(1, len(CELLS) + 1)}
