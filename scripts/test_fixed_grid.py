"""fixed_grid: the schedule is history-free, broad first and finer after, and inside the map."""
import numpy as np

import adaptive_grid_sim as ag
import fixed_grid


def test_schedule_zooms_and_stays_inside():
    world = ag.World("PSC_S1")
    direction, jit = fixed_grid.draw_participant(np.random.default_rng(1))
    grids = fixed_grid.schedule(world, 6, direction, jit)
    spacings = [g["s"] for g in grids]
    assert spacings[0] == ag.S_MAX and spacings[-1] == world.s_min
    assert all(a > b for a, b in zip(spacings, spacings[1:]))
    assert all(((g["cells"] >= 0) & (g["cells"] <= 1)).all() for g in grids)
    again = fixed_grid.schedule(world, 6, direction, jit)
    assert all(np.array_equal(a["cells"], b["cells"]) for a, b in zip(grids, again))
