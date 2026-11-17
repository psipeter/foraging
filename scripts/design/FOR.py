"""FOR, foraging in tiles (2026-11-12): the experiment that varies the reward function and the spatial arrangement together, in a world of hexagonal tiles with a cluster of bushes
in the middle of each (`tiles.py`). One instance at a time (the combination of a between-tile mode and a within-tile mode being tried), with ranking breaks in the session (`RANKING_FIELDS`;
the ranking pools come from `ranking.py`). The reward is a value map (`value_maps.py`): the additive rung, a wide Gaussian in the corner where both features pay more when higher, both alike. An empty mode ("" and "") means the features ignore the tiles (`none` between, `pool` within).
"""

import value_maps
from design import Instance
from design.common import instruction_page

CODE = "FOR"
TITLE = "Foraging task"
REQUIRES = ("TUT",)                 # the tutorial experiment (design/TUT.py) must be finished first
TEMPLATE_SESSION = "FOR_S1"         # copied only when an instance has no asset yet (the lighting, camera and so on come from it)

REWARD_STD = 0.6
REWARD_SCALE = 4.0                  # the best bush pays about this much, as in every built experiment
VALUE_MAP = value_maps.wide_corner((1.0, 1.0), shape_share=0.5, base=0.7, scale=REWARD_SCALE, std=REWARD_STD)       # the additive rung: both features pay more when higher, both alike
SECONDS = 180                    # 180 s (PI, 2026-11-17); the learner earns 1132 points at gain 1 on 40 worlds, the anchor 1125 (6.25 per second)
FIRST_WORLD_SEED = 7001
TILE_FIELDS = {"tileRadius": 45.0, "tileRampWidth": 14.0, "tileMoistureLevels": 4, "tileBushes": 9, "tileClusterRadius": 15.0, "tileClusterSpacing": 10.0}
FEEDBACK_FIELDS = {"rewardFeedbackMax": REWARD_SCALE, "pitchSemitoneRange": 12.0}      # popup size and pick pitch rise with the points up to the session's maximum (here the map's peak); the pitch spans an octave from 440 Hz in every session
CROSSHAIR_RING_DEG = 3.5            # the harvest ring the crosshair becomes on a bush (SessionConfig.crosshairRingSizeDeg)
CROSSHAIR_RADIUS = 7.0              # the hidden hit circle of the crosshair (degrees; SessionConfig.crosshairRadius)
# a ranking set in place after the patch leavings of `rankingLeavings` (1, 2, 4, 8; `SessionConfig.ranking*`; the arc fields: 5 bushes, 16 units, 84 degrees): 20 s a set, one set per break
RANKING_FIELDS = {"rankingEvery": 1, "rankingLeavings.Array.size": 4, "rankingLeavings.Array.data[0]": 1, "rankingLeavings.Array.data[1]": 2, "rankingLeavings.Array.data[2]": 4, "rankingLeavings.Array.data[3]": 8, "rankingSets": 1, "rankingSeconds": 20.0, "rankingCooldown": 10.0, "rankingPoolSets": 12, "rankingMinBushes": 1, "rankingSettleDepth": 0.0, "rankingBonusPerPair": 4.0, "rankingCrosshairRadius": 1.0, "rankingStageDrop": 3.0, "rankingStageMargin": 4.0, "rankingStageWorldGray": 0.6, "rankingText": "Rank these bushes from most to least valuable"}



def _fields(extra, seed, valuemap=VALUE_MAP):
    return {"worldSeed": seed, "layout": "tiles", "assignment": "tiles", "tilePlacement": "random", "tileArrangement": "random", **{**TILE_FIELDS, **extra}, "terrainMaxElevation": 9.0, "shapeVaries": True, "colorVaries": True, "moistureVaries": True,
            **valuemap.fields()}


def instances():
    """FOR's one session is the realised cell of `design/tables/FOR.json` (`cells.py realize design/tables/FOR.json`): the additive rung, a round Gaussian in the corner where both features pay more when higher, at the baseline knobs (PI, 2026-11-17)."""
    from design import tabled
    return tabled.instances_of(CODE)


def texts():
    return {f"instructions_S{n}.txt": instruction_page() for n in range(1, len(instances()) + 1)}
