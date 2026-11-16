"""TUT, the tutorial: its own experiment of one practice session that must be finished before FOR unlocks (FOR.REQUIRES). The world is the tiles world of FOR in its own seed, played for practice
(`isPractice`: not paid, not counted in the menu's total), with popup hints fired by what the participant does (`SessionConfig.hintsFile`, `UI/TutorialHints.cs`). Shape and colour both pay, in a different mix (3:1) and shape pays more when LOWER (`TUTORIAL_INVERTED`)
from FOR's equal, both-increasing rule, so the practice does not teach FOR's rule. TUTORIAL_TILES / TUTORIAL_BETWEEN / TUTORIAL_WITHIN / TUTORIAL_REWARD are the knobs for what the bushes of a cluster look like and pay.
The instruction page and the hints are `instructions_S1.txt` and `hints_S1.txt`, written here; edit the text in this file and rebuild (`build_experiment.py TUT`).
"""

from design import Instance
from design.FOR import CROSSHAIR_RADIUS, RANKING_FIELDS, _fields

CODE = "TUT"
TITLE = "Tutorial"
REQUIRES = ()
COUNTS_TOWARD_TOTAL = False
TEMPLATE_SESSION = "FOR_S1"             # copied only when the session has no asset yet (the lighting, camera and so on come from it)

SECONDS = 240
WORLD_SEED = 6001
TUTORIAL_TILES = {}                     # tile fields that differ from FOR's (for example tileBushes, tileSpread)
TUTORIAL_BETWEEN, TUTORIAL_WITHIN = "", ""      # the layers of tiles.py (default none + pool)
TUTORIAL_REWARD = {"shape": 0.75, "color": 0.25}  # each feature's share of the reward scale: both pay (the hints say so), in a different mix from FOR's equal one
TUTORIAL_INVERTED = ("shape",)          # features that pay more when LOWER (InvertedLinear); FOR pays both more when higher, so the practice does not teach its direction
LABEL = "Tutorial"                      # the small blue line over every instruction screen and popup, and on the end screen

INSTRUCTIONS = """Controls

In this study, you gather **points** by harvesting fruit from bushes.
Walk up to a bush and hold [Space] to harvest it

Press [Enter] to begin
"""

# The hints: none yet. The file keeps the format and the list of triggers as comments; add blocks here (or in the design) when they are chosen.
HINTS = """# Tutorial hints. A block is a trigger line, then the popup: title, text, and a "Press [Enter] to ..." prompt. Each block is shown once.
#
#     @fruit 1
#     Your first fruit
#     You earned {points} points.
#
#     Press [Enter] to continue
#
# Triggers (Assets/Scripts/UI/TutorialHints.cs): harvest_available, harvest_paused, fruit n, bout n, exhausted n, patch_switch n, ranking_start n, ranking_end n,
# seconds n (foraging seconds into the session), idle n (seconds standing still without harvesting), after <trigger>:<n> <seconds> (that many foraging seconds after that hint was shown).
# {points} is the fruit or harvest that fired it.

@bout 1
Harvesting

Harvesting this bush earned {points} points.
You can **stop** harvesting a bush anytime, or **return** to a bush later

Try harvesting a different bush

Press [Enter] to continue

@bout 2
Features

Harvesting this bush earned {points} points.
A bush's **shape** and/or **color** determine how many points you get

Try harvesting a few more bushes, then move to a new area

Press [Enter] to continue

@ranking_start 1
Ranking

**Rank** these imaginary bushes based on what you learned
Do this by harvesting bushes from most to least valuable

Press [Enter] to continue

@ranking_end 1
Ranking

You earn **points** for ranking bushes correctly
These **hidden** points are added at session end

Press [Enter] to continue

@after ranking_start:1 30
Scoring

You have a limited **time** in each session
Try to learn and harvest efficiently

Press [Enter] to continue
"""


def hints_text():
    return HINTS


def instances():
    weights = (("shape", TUTORIAL_REWARD["shape"]), ("color", TUTORIAL_REWARD["color"]), ("moisture", 0.0))
    fields = _fields(TUTORIAL_BETWEEN, TUTORIAL_WITHIN, TUTORIAL_TILES, WORLD_SEED, weights)
    for feature in TUTORIAL_INVERTED:
        fields[f"rewardFunction.{feature}Component.basisFunctionType"] = 1
    return [Instance(f"{CODE}_S1", fields,
                     {"sessionDuration": SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_S1.txt", "hintsFile": f"Experiments/{CODE}/hints_S1.txt", "sessionLabel": LABEL,
                      "scoreCaptionForaging": "points earned from harvesting bushes", "scoreCaptionRanking": "points earned from ranking bushes",
                      "scoreNote": "**Payment** is based on total points earned",
                      "isPractice": True, "crosshairRadius": CROSSHAIR_RADIUS, **RANKING_FIELDS},
                     {"experiment": CODE, "index": 1, "cell": "tutorial", "tutorial": True})]


def texts():
    return {"instructions_S1.txt": INSTRUCTIONS, "hints_S1.txt": hints_text()}
