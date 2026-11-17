"""TUT, the tutorial: its own experiment of one practice session that must be finished before FOR unlocks (FOR.REQUIRES). The world is the tiles world of FOR in its own seed, played for practice
(`isPractice`: not paid, not counted in the menu's total), with popup hints fired by what the participant does (`SessionConfig.hintsFile`, `UI/TutorialHints.cs`). Shape and colour both pay (the additive rung, `TUTORIAL_MAP`: a wide corner Gaussian), in a different mix (about 0.71 of the slope on shape, 0.29 on colour: `wide_corner` asked for 0.75) and shape pays more when LOWER
from FOR's equal, both-increasing rule, so the practice does not teach FOR's rule. TUTORIAL_TILES / TUTORIAL_BETWEEN / TUTORIAL_WITHIN / TUTORIAL_MAP are the knobs for what the bushes of a cluster look like and pay.
The instruction page and the hints are `instructions_S1.txt` and `hints_S1.txt`, written here; edit the text in this file and rebuild (`build_experiment.py TUT`).
"""

import value_maps
from design import Instance
from design.FOR import CROSSHAIR_RADIUS, CROSSHAIR_RING_DEG, FEEDBACK_FIELDS, RANKING_FIELDS, REWARD_SCALE, REWARD_STD, _fields

CODE = "TUT"
TITLE = "Tutorial"
REQUIRES = ()
COUNTS_TOWARD_TOTAL = False
TEMPLATE_SESSION = "FOR_S1"             # copied only when the session has no asset yet (the lighting, camera and so on come from it)

SECONDS = 120
WORLD_SEED = 6001
TUTORIAL_TILES = {}                     # tile fields that differ from FOR's (for example tileBushes, tileSpread)
TUTORIAL_BETWEEN, TUTORIAL_WITHIN = "", ""      # the layers of tiles.py (default none + pool)
TUTORIAL_MAP = value_maps.wide_corner((0.0, 1.0), shape_share=0.75, base=0.7, scale=REWARD_SCALE, std=REWARD_STD)     # the additive rung in another corner: shape pays more when LOWER (FOR pays both more when higher, so the practice does not teach its direction) and carries about 0.71 of the slope, colour 0.29 (a request of 3/4 and 1/4; FOR's equal mix)
CONTROLS_REMINDER = "Mouse: look. W / S: walk. Space: hold to harvest"      # the bar at the bottom of the screen for the whole tutorial ("Key: action" pairs, `InstructionsPanel.FormatControls`)
LABEL = "Tutorial"                      # the small blue line over every instruction screen and popup, and on the end screen

INSTRUCTIONS = """Controls

In this study, you gather **points** by harvesting fruit from bushes
Walk up to a bush and hold [Space] to harvest it

Press [Enter] to begin
"""

# The hints: none yet. The file keeps the format and the list of triggers as comments; add blocks here (or in the design) when they are chosen.
HINTS = """# Tutorial hints. A block is a trigger line, then the popup: title, text, and a "Press [Enter] to ..." prompt. Each block is shown once.
#
#     @bout 1
#     Your first harvest
#     You earned {points} points.
#
#     Press [Enter] to continue
#
# Triggers (Assets/Scripts/UI/TutorialHints.cs; an unknown one is an error): bout n (a harvest that took fruit ends), patch_switch n (the nth qualifying patch leaving, as the rankings count them),
# ranking_start n, ranking_end n. A waiting foraging hint holds back a ranking hint behind it; after a resume, counts carry on from the highest hint of a trigger already shown.
# {points} is what the harvest that fired it earned.

@bout 1
Harvesting

Harvesting this bush earned {points} points
You can **stop** harvesting a bush anytime, or **return** to a bush later

Try harvesting a different bush

Press [Enter] to continue

@bout 2
Features

Harvesting this bush earned {points} points
A bush's **shape** and/or **color** determine how many points you get

Try harvesting a few more bushes, then move to a new area

Press [Enter] to continue

@ranking_start 1
Ranking

**Rank** these imaginary bushes based on what you learned
Do this by harvesting bushes from **most** to **least** valuable

Press [Enter] to continue

@ranking_end 1
Ranking

You earn **points** for ranking bushes correctly
These **hidden** points are added at session end

Press [Enter] to continue

@patch_switch 3
Scoring

You have a limited **time** in each session
Try to learn and harvest efficiently

Press [Enter] to continue
"""


def instances():
    fields = _fields(TUTORIAL_BETWEEN, TUTORIAL_WITHIN, TUTORIAL_TILES, WORLD_SEED, TUTORIAL_MAP)
    return [Instance(f"{CODE}_S1", fields,
                     {"sessionDuration": SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_S1.txt", "hintsFile": f"Experiments/{CODE}/hints_S1.txt", "sessionLabel": LABEL, "controlsReminder": CONTROLS_REMINDER,
                      "scoreCaptionForaging": "points earned from harvesting bushes", "scoreCaptionRanking": "points earned from ranking bushes",
                      "scoreNote": "**Payment** is based on total points earned",
                      "isPractice": True, "crosshairRadius": CROSSHAIR_RADIUS, "crosshairRingSizeDeg": CROSSHAIR_RING_DEG, **FEEDBACK_FIELDS, **RANKING_FIELDS},
                     {"experiment": CODE, "index": 1, "cell": "tutorial", "tutorial": True, **TUTORIAL_MAP.describe()})]


def texts():
    return {"instructions_S1.txt": INSTRUCTIONS, "hints_S1.txt": HINTS}
