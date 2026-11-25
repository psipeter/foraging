"""dense_grid: the table agrees with a direct count, and every session's plans meet the hard constraints, quickly."""
import numpy as np
import pytest

import dense_grid as d

SESSIONS = [f"{c}_S{k}" for c in ("PCX", "PSC", "PSP") for k in (1, 2, 3)]


def test_the_table_agrees_with_a_direct_count_and_fit():
    world, _ = d.load_world("PSC_S1")
    ratio = 1.3
    table = d.build_table(world, ratio)
    rng = np.random.default_rng(1)
    for _ in range(25):
        si, i, j = int(rng.integers(len(d.S_GRID))), int(rng.integers(d.N)), int(rng.integers(d.N))
        s = float(d.S_GRID[si])
        cells = d.grid_cells(world.peak, i, j, s, ratio)
        assert table["count"][si, i, j] == d.count_inside(world, cells)
        inside = bool(((cells >= d.MARGIN - 1e-9) & (cells <= 1 - d.MARGIN + 1e-9)).all())
        assert table["fit"][si, i, j] == inside                                                      # (this peak is not on the map's edge)


@pytest.mark.parametrize("session", SESSIONS)
def test_every_preset_gives_a_plan_that_fits_rises_and_keeps_the_sessions_rules(session):
    world, _ = d.load_world(session)
    for name, grids in d.plans(session).items():
        assert len(grids) == 5
        counts = [g["inside"] for g in grids]
        assert all(b >= a for a, b in zip(counts, counts[1:])) and counts[-1] - counts[0] >= 2, (name, counts)
        for g in grids:
            cells = g["cells"]
            assert ((cells >= -1e-9) & (cells <= 1 + 1e-9)).all()                                   # inside the unit plane
            assert np.allclose(cells[g["index"][0] * d.N + g["index"][1]], world.peak)                # the peak is the (i, j)-th point
        geo = [g["s"] * np.sqrt(g["ratio"]) for g in grids]
        assert geo[0] >= d.DEFAULT_SPEC["first_geo_min"] - 1e-9 or grids[0]["relaxed"]          # a broad first grid
        assert all(b <= a + 1e-9 for a, b in zip(geo, geo[1:]))
