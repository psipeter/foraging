"""FOR, foraging in tiles (prototype, 2026-11-12): the merged experiment that varies the reward function and the spatial arrangement together, in a world of hexagonal tiles with a cluster of bushes
in the middle of each (`tiles.py`). Phases 1 and 2 of the plan only: one instance at a time to see the world in the Editor (the combination of a between-tile mode and a within-tile mode being tried); no Interludes yet (the injected
rankings are a later phase), no difficulty sampling and no spec system (the next phase). Both pay through shape and colour equally (a linear reward over the two).
"""

import world
from design import Instance
from design.common import instruction_page

CODE = "FOR"
TITLE = "Foraging in Tiles"
REQUIRES = ()
TEMPLATE_SESSION = "FOR_S1"         # copied only when an instance has no asset yet (the lighting, camera and so on come from it)

REWARD_STD = 0.6
REWARD_SCALE = 4.0                  # the best bush pays about this much when the weights sum to one, as in every built experiment
SECONDS = 180
FIRST_WORLD_SEED = 7001
TILE_FIELDS = {"tileRadius": 45.0, "tileRampWidth": 14.0, "tileMoistureLevels": 4, "tileBushes": 9, "tileClusterRadius": 15.0, "tileClusterSpacing": 10.0, "tileSpread": 0.12}
# (id, between mode, within mode, other tile fields): one session, whatever is being tested now; "" leaves the mode to the default (`none` and `pool`: no pattern anywhere). Every combination is a pair
# of table entries (tiles.py BETWEEN_MODES, WITHIN_MODES); tried so far: random-scatter, bimodal-smooth, none-gradient.
CROSSHAIR_RADIUS = 7.0              # the hidden hit circle of the crosshair (degrees; SessionConfig.crosshairRadius)
# a ranking set in place after every patch switch (`SessionConfig.ranking*`; the arc fields: 5 bushes, 16 units, 84 degrees): 20 s a set, one set per break
RANKING_FIELDS = {"rankingEvery": 1, "rankingSets": 1, "rankingSeconds": 20.0, "rankingCooldown": 10.0, "rankingPoolSets": 12, "rankingMinBushes": 1, "rankingSettleDepth": 0.0, "rankingBonusPerPair": 4.0}
CELLS = (("default", "", "", {}),)

# The tutorial (practice) session: the same tiles world as the real sessions, in its own seed, played first. It is not timed to pay (`isPractice`), pays through colour alone so
# it does not teach the real sessions' rule, and its popups come from a hints file (`SessionConfig.hintsFile`, UI/TutorialHints.cs). TUTORIAL_TILES / TUTORIAL_REWARD are the
# knobs for what the bushes of a cluster look like and pay; the instruction text and the hints are placeholders to be written.
TUTORIAL_SECONDS = 240
TUTORIAL_SEED = 6001
TUTORIAL_TILES = {}                                    # tile fields that differ from TILE_FIELDS (for example tileBushes, tileSpread)
TUTORIAL_BETWEEN, TUTORIAL_WITHIN = "", ""             # the layers of tiles.py (default none + pool)
TUTORIAL_REWARD = {"shape": 0.0, "color": 1.0}         # each feature's share of the reward scale
HINT_TRIGGERS = ("harvest_available", "harvest_paused", "fruit", "bout", "exhausted", "patch_switch", "ranking_start", "ranking_end")


def _fields(between, within, extra, seed, weights=(("shape", 0.5), ("color", 0.5), ("moisture", 0.0))):
    f = {"worldSeed": seed, "rewardStd": REWARD_STD, "layout": "tiles", "assignment": "tiles", "tileValueMode": between,
         "tileWithinMode": within, "tileArrangement": "random", **{**TILE_FIELDS, **extra}, "terrainMaxElevation": 9.0, "shapeVaries": True, "colorVaries": True, "moistureVaries": True, "moistureIsFeature": False,
         "rewardFunction.bumps.Array.size": 0, "rewardFunction.products.Array.size": 0}
    for feature, weight in weights:
        f.update({f"rewardFunction.{feature}Component.basisFunctionType": 0, f"rewardFunction.{feature}Component.weight": REWARD_SCALE * weight,
                  f"rewardFunction.{feature}Component.peak": 0, f"rewardFunction.{feature}Component.width": 0})
    return f


def tutorial_instance():
    weights = (("shape", TUTORIAL_REWARD["shape"]), ("color", TUTORIAL_REWARD["color"]), ("moisture", 0.0))
    return Instance(f"{CODE}_T1", _fields(TUTORIAL_BETWEEN, TUTORIAL_WITHIN, TUTORIAL_TILES, TUTORIAL_SEED, weights),
                    {"sessionDuration": TUTORIAL_SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_T1.txt", "hintsFile": f"Experiments/{CODE}/hints_T1.txt", "isPractice": True,
                     "crosshairRadius": CROSSHAIR_RADIUS, **RANKING_FIELDS},
                    {"experiment": CODE, "index": 0, "cell": "tutorial", "tutorial": True})


def instances():
    return [tutorial_instance()] + [
        Instance(f"{CODE}_S{n}", _fields(between, within, extra, FIRST_WORLD_SEED + 100 * n), {"sessionDuration": SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_S{n}.txt", "isPractice": False, "crosshairRadius": CROSSHAIR_RADIUS, **RANKING_FIELDS},
                 {"experiment": CODE, "index": n, "cell": cid, "tile_value_mode": between, "tile_within_mode": within, "prototype": True})
        for n, (cid, between, within, extra) in enumerate(CELLS, start=1)]


def hints_text():
    """Placeholder hints, one per trigger, so the mechanism can be tried before the text is written (replace with the real hints)."""
    return "# Tutorial hints (placeholders). Format: @trigger [n], then title, text, prompt; see Assets/Scripts/UI/TutorialHints.cs.\n\n" + "\n\n".join(
        f"@{t}\n[hint: {t}]\n\nPlaceholder for the {t.replace('_', ' ')} hint. {{points}}\n\nPress [Enter] to continue" for t in HINT_TRIGGERS) + "\n"


def texts():
    return {"instructions_T1.txt": instruction_page("[practice instructions: to be written]"), "hints_T1.txt": hints_text(),
            **{f"instructions_S{n}.txt": instruction_page("") for n in range(1, len(CELLS) + 1)}}
