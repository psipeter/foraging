"""Experiment designs: one module per experiment code (`design/<code>.py`), the single place a design table is edited.

A design module defines

    CODE, TITLE            the experiment's key (the asset prefix) and the name the menu shows
    REQUIRES               codes a participant must have finished first (default none)
    COUNTS_TOWARD_TOTAL    whether its points join the menu's total (default True)
    TEMPLATE_SESSION       an existing session asset (e.g. "TUT_S1") copied when an instance has no asset yet
    TEMPLATE_INTERLUDE     ... and the same for an Interlude asset ("TUT_I1")
    instances() -> list of Instance, in play order
    texts() -> {file name: text} instruction texts, written to Assets/StreamingAssets/Experiments/<code>/ (optional)

`build_experiment.py <code>` turns that into assets (through the Editor), worlds, Interludes and texts. An instance's `design` dict is stored as
JSON in the session asset's `designJson`, which the logger records with the rest of the config: the instance id, its cell parameters, its hint
arm. Field names are SessionConfig's serialized names; nested ones use a dotted path (`rewardFunction.shapeComponent.weight`), and a list is sized
first by `<path>.Array.size`.
"""

from dataclasses import dataclass, field


@dataclass
class Instance:
    name: str                                 # the session asset's name, <code>_S<n>
    fields: dict                              # fields of the session and of its Interlude (the world: seed, terrain, reward function, ...)
    session_fields: dict = field(default_factory=dict)       # fields of the session only (duration, instruction file, ...)
    interlude_fields: dict | None = None      # extra fields of its Interlude (trial count, mode, ...); None: the session has no Interlude
    design: dict = field(default_factory=dict)               # the logged description of this instance
    interlude_instructions: str | None = None    # the Interlude's instruction file, a path under StreamingAssets (None: the template's)
