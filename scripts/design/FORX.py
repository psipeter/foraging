"""FORX, the foraging task with sessions made from knob settings (docs/SESSION_FACTORS_PLAN.md, milestone 5): the table `design/tables/FORX.json` lists the cells, `cells.py realize` turns them
into `design/realized/FORX.json`, and this module builds one session of FOR's kind from each realised cell (`design/tabled.py`). The cells of the table now are examples, not a design."""

from design import tabled
from design.common import instruction_page

CODE = "FORX"
TITLE = "Foraging task (sessions from knobs)"
REQUIRES = ("TUT",)
TEMPLATE_SESSION = "FOR_S1"


def instances():
    return tabled.instances_of(CODE)


def texts():
    return {f"instructions_S{n}.txt": instruction_page() for n in range(1, len(instances()) + 1)}
