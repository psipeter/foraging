"""Pilot: Complexity: three sessions of the foraging task, low, medium and high of one knob, in that order (`design/tables/PCX.json`, realised by `cells.py realize design/tables/PCX.json`; designed with
`pilot_report.py`). The participants are told nothing of what varies. Built like FORX (`design/tabled.py`)."""

from design import tabled
from design.common import instruction_page

CODE = "PCX"
TITLE = "Pilot: Complexity"
REQUIRES = ("TUT",)
TEMPLATE_SESSION = "FOR_S1"


def instances():
    return tabled.instances_of(CODE)


def texts():
    return {f"instructions_S{n}.txt": instruction_page() for n in range(1, len(instances()) + 1)}
