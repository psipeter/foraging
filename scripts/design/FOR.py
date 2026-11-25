"""FOR, foraging in tiles (2026-11-12): the experiment that varies the reward function and the spatial arrangement together, in a world of hexagonal tiles with a cluster of bushes
in the middle of each (`tiles.py`). One instance at a time (the combination of a between-tile mode and a within-tile mode being tried), with selection breaks in the session (`SELECTION_FIELDS`;
the selection pools come from `selection.py`). The reward is a value map (`value_maps.py`): the additive rung, a wide Gaussian in the corner where both features pay more when higher, both alike. An empty mode ("" and "") means the features ignore the tiles (`none` between, `pool` within).
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
TILE_FIELDS = {"tilePlacement": "balanced", "tileSumTol": 1.0, "tileRadius": 45.0, "tileRampWidth": 14.0, "tileMoistureLevels": 4, "tileBushes": 9, "tileClusterRadius": 15.0, "tileClusterSpacing": 10.0}
FEEDBACK_FIELDS = {"rewardFeedbackMax": REWARD_SCALE, "pitchSemitoneRange": 12.0}      # popup size and pick pitch rise with the points up to the session's maximum (here the map's peak); the pitch spans an octave from 440 Hz in every session
CROSSHAIR_RING_DEG = 3.5            # the harvest ring the crosshair becomes on a bush (SessionConfig.crosshairRingSizeDeg)
CROSSHAIR_RADIUS = 7.0              # the hidden hit circle of the crosshair (degrees; SessionConfig.crosshairRadius)
# a selection set in place after every patch leaving that follows a harvested bush (`selectionEvery` 1, no `selectionLeavings` schedule, no cooldown, `selectionMinBushes` 1 since the last selection; `SessionConfig.selection*`; the arc fields: 5 bushes, 16 units, 84 degrees): 20 s a set, one set per break
SELECTION_TEXT = "Select the 5 most valuable bushes. 100 points available."           # the banner of a selection (a "selection" to participants), pilots and tutorial
SELECTION_FIELDS = {"selectionEvery": 1, "selectionLeavings.Array.size": 0, "selectionMinBushes": 1, "selectionSets": 1, "selectionSeconds": 20.0, "selectionCooldown": 0.0, "selectionPoolSets": 30, "selectionSettleDepth": 0.0, "selectionBonusPerPair": 4.0, "selectionPointsMode": "pair_mean_value", "selectionCrosshairRadius": 1.0, "selectionStageDrop": 3.0, "selectionStageMargin": 4.0, "selectionStageWorldGray": 0.6, "selectionText": SELECTION_TEXT}


# The dense selection of the pilots (2026-11-25, DECISIONS "Dense 5x5 selection grid" and "Build of the dense selection"): a selection at 30, 60, 90, 120 and 150 s of the session clock (soft: it waits for a harvest bout to end, 10 s at most),
# the best 5 of a 5x5 grid of bushes picked in 45 s from a stage camera of its own (the player's camera does not move), scored 0 to 100 (one selection, drawn from the world seed, pays). The grids are planned by `scripts/dense_grid.py` (preset balanced).
SELECTION_TIMES = (30.0, 60.0, 90.0, 120.0, 150.0)
DENSE_SELECTION_FIELDS = {"selectionDesign": "dense", "selectionTimes.Array.size": len(SELECTION_TIMES), **{f"selectionTimes.Array.data[{i}]": t for i, t in enumerate(SELECTION_TIMES)},
                        "selectionMaxWait": 10.0, "selectionSeconds": 45.0, "selectionPoolSets": len(SELECTION_TIMES), "selectionPicks": 5, "selectionGridSpacing": 7.0, "selectionGridDistance": 22.0, "selectionStageTilt": 30.0, "selectionStageDrop": 2.0,
                        "selectionGridPreset": "balanced", "selectionTopKPoints": 100.0, "selectionPaid": "all",
                        "selectionPointsMode": "top_k", "selectionStageMargin": 5.5, "selectionText": SELECTION_TEXT}


def _fields(extra, seed, valuemap=VALUE_MAP):
    return {"worldSeed": seed, "layout": "tiles", "assignment": "tiles", "tileArrangement": "random", **{**TILE_FIELDS, **extra}, "terrainMaxElevation": 9.0, "shapeVaries": True, "colorVaries": True, "moistureVaries": True,
            **valuemap.fields()}


def instances():
    """FOR's one session is the realised cell of `design/tables/FOR.json` (`cells.py realize design/tables/FOR.json`): the additive rung, a round Gaussian in the corner where both features pay more when higher, at the baseline knobs (PI, 2026-11-17)."""
    from design import tabled
    return tabled.instances_of(CODE)


def texts():
    return {f"instructions_S{n}.txt": instruction_page() for n in range(1, len(instances()) + 1)}
