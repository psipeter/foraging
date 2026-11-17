"""The design of the independence test (independence.py): the knob settings stay inside the ranges, the classes are balanced, the design is reproducible, and a rerun skips what is done."""

import json

import independence as ind


def test_the_design_is_reproducible_stays_in_the_ranges_and_has_all_three_classes():
    d = ind.design(30, seed=1)
    assert d == ind.design(30, seed=1) and d != ind.design(30, seed=2)
    for k in d:
        for name, (lo, hi) in ind.RANGES.items():
            assert lo <= k[name] <= hi
        assert (k["klass"] == "rotated") == (k["class"] == "nonseparable")
    assert {k["class"] for k in d} == set(ind.CLASSES) and min(sum(k["class"] == c for k in d) for c in ind.CLASSES) >= 8


def test_the_multiplicative_interaction_is_inside_what_an_aligned_map_of_that_gini_can_reach():
    for k in ind.design(60, seed=3):
        if k["class"] == "multiplicative":
            assert abs(k["interaction"] - 0.6 * ind.aligned_cap(k["gini"])) < 1e-3 and k["interaction"] <= ind.aligned_cap(k["gini"])
        if k["class"] == "additive":
            assert k["interaction"] == ind.ADDITIVE_INTERACTION


def test_done_reads_the_knobs_of_the_finished_rows(tmp_path):
    path = tmp_path / "x.jsonl"
    assert ind.done(path) == set()
    knobs = ind.design(2)[0]
    path.write_text(json.dumps({"knobs": knobs, "ok": False}) + "\n")
    assert ind.done(path) == {json.dumps(knobs, sort_keys=True)}
