"""Sessions from a table of knob settings (cells.py, design/tabled.py): the nuisance draws, the inaccessible cells, the world seed, and the instances built from a realised cell. The expensive part
(factors.realize, the simulator) is replaced by a stub; its own tests are test_factors.py."""

import json
from types import SimpleNamespace

import pytest

import cells
import factors
import value_maps
from build_experiment import build_spec
from design import tabled


def stub_realize(fail_draws=()):
    calls = []

    def realize(session, gini, interaction, klass, travel_time, corner=None, seed=0, **overrides):
        calls.append({"klass": klass, "interaction": interaction, "corner": corner, "seed": seed})
        if seed in fail_draws:
            raise ValueError("the best bush would be worth 11.0 points, over the cap")
        valuemap = value_maps.wide_corner(corner or (1.0, 1.0), 0.5, 0.7, scale=5.0)
        settings = {"tile_radius": 69.3, "tile_placement": "random"}
        return {"map": valuemap, "settings": settings, "fields": {}, "achieved": {"factors": {}, "points": {"learner": (752.0, 18.0), "nearest": (650.0, 9.0), "oracle": (1000.0, 9.0)}}, "within_tolerance": True, "rounds": 2}
    return realize, calls


CELL = {"id": 3, "class": "additive", "gini": 0.4, "travel_time": 6.0}


def realize_with(monkeypatch, fail_draws=(), draws=4):
    realize, calls = stub_realize(fail_draws)
    monkeypatch.setattr(factors, "realize", realize)
    return cells.realize_cell(CELL, draws=draws, duration=180.0), calls


def test_the_first_draw_that_holds_is_kept_and_the_failed_ones_are_recorded(monkeypatch):
    record, calls = realize_with(monkeypatch, fail_draws=(0, 1))
    assert record["status"] == "ok" and record["draw"] == 2 and [f["draw"] for f in record["failed_draws"]] == [0, 1] and len(calls) == 3
    assert calls[0]["klass"] == "corner" and calls[0]["interaction"] is None and [c["seed"] for c in calls] == [0, 1, 2]


def test_a_cell_no_draw_can_hold_is_inaccessible_with_its_reasons(monkeypatch):
    record, calls = realize_with(monkeypatch, fail_draws=(0, 1, 2, 3))
    assert record["status"] == "inaccessible" and len(record["failed_draws"]) == 4 and "over the cap" in record["failed_draws"][0]["error"] and "map" not in record


def test_the_world_is_the_cells_first_seed_unless_the_cell_gives_one_and_the_feedback_maximum_follows_the_peak(monkeypatch):
    record, _ = realize_with(monkeypatch)
    assert record["world_seed"] == cells.FIRST_WORLD_SEED + 100 * 3 and record["anchor_points"] == factors.anchor_points(180.0) and record["duration"] == 180.0
    assert "candidate_points" not in record and "own_world_points" not in record
    assert record["feedback_max"] == 5 and record["peak"] == pytest.approx(5.0)                     # a map of peak 5 (gain 1): the best bush, rounded up
    realize, _ = stub_realize(())
    monkeypatch.setattr(factors, "realize", realize)
    assert cells.realize_cell({**CELL, "world_seed": 12345}, draws=1, duration=180.0)["world_seed"] == 12345


def test_the_corner_of_an_additive_cell_is_a_function_of_the_cell_and_the_draw():
    assert cells.corner_of(3, 0) == cells.corner_of(3, 0) and {cells.corner_of(i, d) for i in range(6) for d in range(6)} <= {(a, b) for a in (0.0, 1.0) for b in (0.0, 1.0)}
    assert len({cells.corner_of(1, d) for d in range(12)}) > 1


def test_the_default_interactions_of_the_three_rungs():
    assert value_maps.default_interaction("additive", 0.5) is None
    assert value_maps.default_interaction("multiplicative", 0.5) == pytest.approx(0.9 * value_maps.aligned_cap(0.5)) and value_maps.default_interaction("nonseparable", 0.5) == 0.4


def realised_data(monkeypatch):
    record, _ = realize_with(monkeypatch)
    inaccessible = {"id": 4, "status": "inaccessible", "knobs": {}, "failed_draws": []}
    return {"cells": [record, inaccessible, {**record, "id": 5}]}


def test_the_instances_are_the_realised_cells_in_order_with_the_realised_map_layout_world_and_feedback(monkeypatch):
    data = realised_data(monkeypatch)
    inst = tabled.instances_of("ZZ", data)
    assert [i.name for i in inst] == ["ZZ_S1", "ZZ_S2"]                                         # the inaccessible cell has no session
    f, s, d = inst[0].fields, inst[0].session_fields, inst[0].design
    assert f["worldSeed"] == data["cells"][0]["world_seed"] and f["tileRadius"] == 69.3 and f["tilePlacement"] == "balanced" and f["tileSumTol"] == 1.0
    assert f["rewardFunction.bumps.Array.size"] == 1 and f["rewardStd"] == 0.6
    assert s["rewardFeedbackMax"] == 5.0 and s["pitchSemitoneRange"] == 12.0 and s["instructionsFile"] == "Experiments/ZZ/instructions_S1.txt" and s["sessionDuration"] == 180.0
    assert d["cell"] == 3 and d["nuisance_draw"] == 0 and d["anchor"]["points"] == factors.anchor_points(180.0) and d["anchor"]["rate"] == factors.ANCHOR_RATE and d["anchor"]["check_points"]["learner"] == 752 and d["value_map"]["bumps"] and "gini" in d["value_map_descriptors"]


def test_a_design_module_over_realised_cells_builds_a_spec(monkeypatch):
    data = realised_data(monkeypatch)
    module = SimpleNamespace(CODE="ZZ", TITLE="Test", TEMPLATE_SESSION="FOR_S1", instances=lambda: tabled.instances_of("ZZ", data))
    spec = build_spec(module)
    assert [x["name"] for x in spec["sessions"]] == ["ZZ_S1", "ZZ_S2"]
    fields = {p["p"]: p["v"] for p in spec["sessions"][0]["fields"]}
    assert json.loads(fields["designJson"])["instance"] == "ZZ_S1" and fields["rewardFeedbackMax"] == "5.0"


def test_a_design_with_no_realised_file_has_no_sessions():
    assert tabled.instances_of("NOFILE_XX") == []
