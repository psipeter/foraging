"""TUT, the tutorial: its own experiment of one practice session that must be finished before FOR unlocks (FOR.REQUIRES). The world is the tiles world of FOR in its own seed, played for practice
(`isPractice`: not paid, not counted in the menu's total), with popup hints fired by what the participant does (`SessionConfig.hintsFile`, `UI/TutorialHints.cs`). The reward pays through colour alone so
the practice does not teach FOR's rule (shape and colour equally). TUTORIAL_TILES / TUTORIAL_BETWEEN / TUTORIAL_WITHIN / TUTORIAL_REWARD are the knobs for what the bushes of a cluster look like and pay.
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
TUTORIAL_REWARD = {"shape": 0.0, "color": 1.0}  # each feature's share of the reward scale
LABEL = "Tutorial"                      # the small blue line over every instruction screen and popup, and on the end screen

INSTRUCTIONS = """Controls

In this study, you gather **points** by harvesting fruit from bushes.
Walk up to a bush and hold [Space] to harvest it

Press [Enter] to begin
"""

# One placeholder per trigger so the mechanism can be tried before the text is written; replace with the real hints (format: UI/TutorialHints.cs).
HINT_TRIGGERS = ("harvest_available", "harvest_paused", "fruit", "bout", "exhausted", "patch_switch", "ranking_start", "ranking_end")


def hints_text():
    return "# Tutorial hints (placeholders). Format: @trigger [n], then title, text, prompt; see Assets/Scripts/UI/TutorialHints.cs.\n\n" + "\n\n".join(
        f"@{t}\n[hint: {t}]\n\nPlaceholder for the {t.replace('_', ' ')} hint. {{points}}\n\nPress [Enter] to continue" for t in HINT_TRIGGERS) + "\n"


def instances():
    weights = (("shape", TUTORIAL_REWARD["shape"]), ("color", TUTORIAL_REWARD["color"]), ("moisture", 0.0))
    return [Instance(f"{CODE}_S1", _fields(TUTORIAL_BETWEEN, TUTORIAL_WITHIN, TUTORIAL_TILES, WORLD_SEED, weights),
                     {"sessionDuration": SECONDS, "instructionsFile": f"Experiments/{CODE}/instructions_S1.txt", "hintsFile": f"Experiments/{CODE}/hints_S1.txt", "sessionLabel": LABEL,
                      "isPractice": True, "crosshairRadius": CROSSHAIR_RADIUS, **RANKING_FIELDS},
                     {"experiment": CODE, "index": 1, "cell": "tutorial", "tutorial": True})]


def texts():
    return {"instructions_S1.txt": INSTRUCTIONS, "hints_S1.txt": hints_text()}
