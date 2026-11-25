"""The dense selection design's pool (selection.generate_pool with selectionDesign 'dense') and its scoring."""
import numpy as np
import pytest

import selection


def pool():
    return selection.generate_pool("PSC_S1", selection_design="dense", selection_times=[30, 60, 90, 120, 150])[0]


def test_the_pool_has_one_25_bush_grid_per_selection_on_one_lattice():
    sc = pool()
    assert sc["n"] == 5 and sc["setSize"] == 25 and sc["layout"] == "grid" and sc["pickCount"] == 5
    pos = np.array(sc["treePos"]).reshape(-1, 2)
    assert pos.shape == (125, 2)
    assert np.allclose(pos[:25], pos[25:50]) and np.allclose(pos[:25].mean(axis=0), [0.0, sc["bushDistance"]])
    for s, st in enumerate(sc["sets"]):
        assert [b["id"] for b in st["bushes"]] == list(range(s * 25, s * 25 + 25)) and [b["slot"] for b in st["bushes"]] == list(range(25))
        assert all(0.0 <= b["shape"] <= 1.0 and 0.0 <= b["color"] <= 1.0 for b in st["bushes"])
        peak = st["grid"]["peakIndex"]
        assert max(b["value"] for b in st["bushes"]) == pytest.approx(max(st["grid"]["best"]), abs=1e-9)           # the peak is on the grid
        assert st["bushes"][peak[0] * 5 + peak[1]]["value"] == pytest.approx(max(b["value"] for b in st["bushes"]))


def test_the_top_k_score_is_100_for_the_best_k_about_0_for_a_random_pick_and_never_negative():
    values = list(np.linspace(0, 10, 25))
    assert selection.top_k_score(sorted(values)[-5:], values) == pytest.approx(100.0)
    assert selection.top_k_score(values[10:15], values) == pytest.approx(0.0, abs=25)
    assert selection.top_k_score(sorted(values)[:5], values) == 0.0
    assert selection.top_k_score(sorted(values)[-3:], values) < 100.0                       # fewer picks than k (a timed-out selection)
    assert selection.top_k_hits([24, 23, 0], {i: v for i, v in enumerate(values)}) == 2


def test_the_paid_selection_is_a_fixed_function_of_the_seed():
    assert [selection.paid_set_index(s, 5) for s in (9201, 9202, 9610)] == [selection.paid_set_index(s, 5) for s in (9201, 9202, 9610)]
    assert all(0 <= selection.paid_set_index(s, 5) < 5 for s in range(9000, 9100))
    assert len({selection.paid_set_index(s, 5) for s in range(9000, 9100)}) == 5
