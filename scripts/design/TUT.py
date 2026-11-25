"""TUT, the tutorial: its own experiment of one practice session that must be finished before FOR unlocks (FOR.REQUIRES). The world is the tiles world of FOR in its own seed, played for practice
(`isPractice`: not paid, not counted in the menu's total), with popup hints fired by what the participant does (`SessionConfig.hintsFile`, `UI/TutorialHints.cs`). Shape and colour both pay (the additive rung): a round Gaussian in a corner, at FOR's baseline knobs (`design/tables/TUT.json`, realised by `cells.py realize design/tables/TUT.json`),
but in the corner where shape pays more when LOWER, so the practice does not teach FOR's both-increasing rule.
The instruction page and the hints are `instructions_S1.txt` and `hints_S1.txt`, written here; edit the text in this file and rebuild (`build_experiment.py TUT`).
"""

import value_maps
from design import Instance
from design.FOR import DENSE_RANKING_FIELDS, RANKING_TEXT, CROSSHAIR_RADIUS, CROSSHAIR_RING_DEG, FEEDBACK_FIELDS, RANKING_FIELDS, _fields

CODE = "TUT"
TITLE = "Tutorial"
REQUIRES = ()
COUNTS_TOWARD_TOTAL = False
TEMPLATE_SESSION = "FOR_S1"             # copied only when the session has no asset yet (the lighting, camera and so on come from it)

SECONDS = 150
TUT_SCHEDULE = {"rankingTimes.Array.size": 2, "rankingTimes.Array.data[0]": 30.0, "rankingTimes.Array.data[1]": 90.0, "rankingPoolSets": 2}      # the pilots' dense selection (design/FOR.py) played twice, at 30 s and 90 s of the 150 (the time popups sit at 60 s and 120 s)
CONTROLS_REMINDER = "Mouse: look. W / S: walk. Space: hold to harvest. Escape: pause"      # the bar at the bottom of the screen for the whole tutorial ("Key: action" pairs, `InstructionsPanel.FormatControls`)
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
# selection_start n, selection_end n, time_left s (the first moment s foraging seconds or fewer are left; the clock pulses yellow while the hint is up). A waiting foraging hint holds back a ranking hint behind it; after a resume, counts carry on from the highest hint of a trigger already shown.
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

@selection_start 1
Selection

**Select** the most valuable bushes based on what you learned

Press [Enter] to continue

@selection_end 1
Selection

You earn up to **100 points** for selecting better bushes
These **hidden** points are added at the end of the session

Press [Enter] to continue

@time_left 90
Scoring

You have a limited **time** in each session
Learn and harvest **efficiently** to earn more **points**

Press [Enter] to continue

@time_left 30
Pausing

You can **pause** the game at any time
The timer stops while you are paused

Press [Escape] to pause
"""


def instances():
    """The one session is the realised cell of `design/tables/TUT.json`: the map, tile layout, world seed and feedback maximum come from it, the texts and hints from this file."""
    from design import tabled
    c = next(c for c in tabled.realized(CODE)["cells"] if c["status"] == "ok")
    m, s = c["map"], c["settings"]
    valuemap = value_maps.ValueMap(tuple(value_maps.Bump(**b) for b in m["bumps"]), m["noise"], m["equaliser"])
    fields = _fields({"tileRadius": s["tile_radius"]}, c["world_seed"], valuemap)
    return [Instance(f"{CODE}_S1", fields,
                     {"sessionDuration": SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_S1.txt", "hintsFile": f"Experiments/{CODE}/hints_S1.txt", "sessionLabel": LABEL, "controlsReminder": CONTROLS_REMINDER,
                      "scoreCaptionForaging": "Points earned from harvesting bushes", "scoreCaptionRanking": "Points earned from selecting bushes",
                      "scoreNote": "**Payment** is based on total points earned",
                      "isPractice": True, "crosshairRadius": CROSSHAIR_RADIUS, "crosshairRingSizeDeg": CROSSHAIR_RING_DEG, **FEEDBACK_FIELDS, "rewardFeedbackMax": float(c["feedback_max"]), **RANKING_FIELDS, **{k: v for k, v in DENSE_RANKING_FIELDS.items() if not k.startswith("rankingTimes")}, **TUT_SCHEDULE},
                     {"experiment": CODE, "index": 1, "cell": "tutorial", "tutorial": True, "knobs": c["knobs"], "world_seed": c["world_seed"], "calibrator": c["calibrator"], **valuemap.describe()})]


def texts():
    return {"instructions_S1.txt": INSTRUCTIONS, "hints_S1.txt": HINTS}
