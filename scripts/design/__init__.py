"""Experiment designs: one module per experiment code (`design/<code>.py`), the single place a design table is edited.

A design module defines

    CODE, TITLE            the experiment's key (the asset prefix) and the name the menu shows
    REQUIRES               codes a participant must have finished first (default none)
    COUNTS_TOWARD_TOTAL    whether its points join the menu's total (default True)
    TEMPLATE_SESSION       an existing session asset (e.g. "FOR_S1") copied when an instance has no asset yet
    instances() -> list of Instance, in play order
    texts() -> {file name: text} instruction texts, written to Assets/StreamingAssets/Experiments/<code>/ (optional)

`build_experiment.py <code>` turns that into assets (through the Editor), worlds, ranking pools and texts. An instance's `design` dict is stored as
JSON in the session asset's `designJson`, which the logger records with the rest of the config: the instance id, its cell parameters, its hint
arm. A design gives a session's reward as a `value_maps.ValueMap` and passes its `fields()` (the bumps and the noise); a design's `ValueMap.describe()` puts the map and its descriptors in the logged design. Field names are SessionConfig's serialized names; nested ones use a dotted path (`rewardFunction.bumps.Array.data[0].height`), and a list is sized
first by `<path>.Array.size`.
"""

from dataclasses import dataclass, field


@dataclass
class Instance:
    name: str                                 # the session asset's name, <code>_S<n>
    fields: dict                              # fields of the session (the world: seed, terrain, reward function, ...)
    session_fields: dict = field(default_factory=dict)       # fields of the session only (duration, instruction file, ...)
    design: dict = field(default_factory=dict)               # the logged description of this instance
