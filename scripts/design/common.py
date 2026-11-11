"""Pieces the table-driven designs share (RW, FI): the seeded play order, the search for a world seed whose world passes a check, and the instruction page.

FN predates these and keeps its own (its cells and order are built differently); it may adopt them later.
"""

import numpy as np


def play_order(cells, master_seed, baseline_stage="B"):
    """The cells in play order: those of `baseline_stage` as listed, then the first iteration of every other cell, then the later iterations, both groups shuffled by `master_seed`."""
    rng = np.random.default_rng(master_seed)
    base = [c for c in cells if c["stage"] == baseline_stage]
    rest = [c for c in cells if c["stage"] != baseline_stage]
    first = [c for c in rest if c["iteration"] == 1]
    later = [c for c in rest if c["iteration"] > 1]
    return base + [first[i] for i in rng.permutation(len(first))] + [later[i] for i in rng.permutation(len(later))]


def find_world(number, first_world_seed, max_attempts, build, label):
    """The first world seed (`first_world_seed` + 100 * number + attempt, attempts 0 to max_attempts - 1) for which `build(seed)` returns a result: it returns None when the draw or its world fails
    the instance's checks. Returns (seed, attempt, result); raises RuntimeError naming `label` when no seed passes."""
    for attempt in range(max_attempts):
        seed = first_world_seed + 100 * number + attempt
        result = build(seed)
        if result is not None:
            return seed, attempt, result
    raise RuntimeError(f"{label} (session {number}): no world seed in {max_attempts} passed its checks")


def instruction_page(hint_text):
    """The instruction text of a session: the hint (one or more lines; none when it is empty) between the fixed lines."""
    hint = f"{hint_text}\n" if hint_text else ""
    return f"Find the best fruit\n\nThis is a new area.\n{hint}Collect as many points as you can.\n\nPress [Enter] to begin"
