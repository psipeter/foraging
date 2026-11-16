"""Pieces the table-driven designs share: the seeded play order, the search for a world seed whose world passes a check, and the instruction page."""

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


def instruction_page():
    """The instruction text of a session of the foraging task (centred like every popup; one-line sentences end without a period)."""
    return "Foraging task\n\nHarvest bushes to collect **points**\n**Rank** bushes when prompted\nNote: this is a **new** area with new **rules**\n\nPress [Enter] to begin"
