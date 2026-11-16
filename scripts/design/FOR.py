"""FOR, foraging in tiles (2026-11-12): the experiment that varies the reward function and the spatial arrangement together, in a world of hexagonal tiles with a cluster of bushes
in the middle of each (`tiles.py`). One instance at a time (the combination of a between-tile mode and a within-tile mode being tried), with ranking breaks in the session (`RANKING_FIELDS`;
the ranking pools come from `ranking.py`). Both features pay equally (a linear reward over shape and colour). An empty mode ("" and "") means the features ignore the tiles (`none` between, `pool` within).
"""

from design import Instance
from design.common import instruction_page

CODE = "FOR"
TITLE = "Foraging task"
REQUIRES = ("TUT",)                 # the tutorial experiment (design/TUT.py) must be finished first
TEMPLATE_SESSION = "FOR_S1"         # copied only when an instance has no asset yet (the lighting, camera and so on come from it)

REWARD_STD = 0.6
REWARD_SCALE = 4.0                  # the best bush pays about this much when the weights sum to one, as in every built experiment
SECONDS = 120
FIRST_WORLD_SEED = 7001
TILE_FIELDS = {"tileRadius": 45.0, "tileRampWidth": 14.0, "tileMoistureLevels": 4, "tileBushes": 9, "tileClusterRadius": 15.0, "tileClusterSpacing": 10.0, "tileSpread": 0.12}
# (id, between mode, within mode, other tile fields): one session, whatever is being tested now; "" leaves the mode to the default (`none` and `pool`: no pattern anywhere). Every combination is a pair
# of table entries (tiles.py BETWEEN_MODES, WITHIN_MODES); tried so far: random-scatter, bimodal-smooth, none-gradient.
CROSSHAIR_RING_DEG = 3.5            # the harvest ring the crosshair becomes on a bush (SessionConfig.crosshairRingSizeDeg)
CROSSHAIR_RADIUS = 7.0              # the hidden hit circle of the crosshair (degrees; SessionConfig.crosshairRadius)
# a ranking set in place after the patch leavings of `rankingLeavings` (1, 2, 4, 8; `SessionConfig.ranking*`; the arc fields: 5 bushes, 16 units, 84 degrees): 20 s a set, one set per break
RANKING_FIELDS = {"rankingEvery": 1, "rankingLeavings.Array.size": 4, "rankingLeavings.Array.data[0]": 1, "rankingLeavings.Array.data[1]": 2, "rankingLeavings.Array.data[2]": 4, "rankingLeavings.Array.data[3]": 8, "rankingSets": 1, "rankingSeconds": 20.0, "rankingCooldown": 10.0, "rankingPoolSets": 12, "rankingMinBushes": 1, "rankingSettleDepth": 0.0, "rankingBonusPerPair": 4.0, "rankingCrosshairRadius": 1.0, "rankingStageDrop": 3.0, "rankingStageMargin": 4.0, "rankingStageWorldGray": 0.6, "rankingText": "Rank these bushes from most to least valuable"}
CELLS = (("default", "", "", {}),)



def _fields(between, within, extra, seed, weights=(("shape", 0.5), ("color", 0.5), ("moisture", 0.0))):
    f = {"worldSeed": seed, "rewardStd": REWARD_STD, "layout": "tiles", "assignment": "tiles", "tileValueMode": between,
         "tileWithinMode": within, "tileArrangement": "random", **{**TILE_FIELDS, **extra}, "terrainMaxElevation": 9.0, "shapeVaries": True, "colorVaries": True, "moistureVaries": True, "moistureIsFeature": False,
         "rewardFunction.bumps.Array.size": 0, "rewardFunction.products.Array.size": 0}
    for feature, weight in weights:
        f.update({f"rewardFunction.{feature}Component.basisFunctionType": 0, f"rewardFunction.{feature}Component.weight": REWARD_SCALE * weight,
                  f"rewardFunction.{feature}Component.peak": 0, f"rewardFunction.{feature}Component.width": 0})
    return f


def instances():
    return [
        Instance(f"{CODE}_S{n}", _fields(between, within, extra, FIRST_WORLD_SEED + 100 * n), {"sessionDuration": SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_S{n}.txt", "isPractice": False, "crosshairRadius": CROSSHAIR_RADIUS, "crosshairRingSizeDeg": CROSSHAIR_RING_DEG, **RANKING_FIELDS},
                 {"experiment": CODE, "index": n, "cell": cid, "tile_value_mode": between, "tile_within_mode": within, "prototype": True})
        for n, (cid, between, within, extra) in enumerate(CELLS, start=1)]


def texts():
    return {f"instructions_S{n}.txt": instruction_page() for n in range(1, len(CELLS) + 1)}
