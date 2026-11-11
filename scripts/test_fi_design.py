"""The FI design module (design/FI.py): the instance list and its order, the rules and their matched sparsity, the balance of corners and tilts, the hint, the Interlude settings, and the texts."""
import json

import pytest

import fi_terms
from design import FI, RW


@pytest.fixture(scope="module")
def built():
    return FI._instances_built()


def test_every_cell_has_its_number_of_iterations(built):
    ids = [c["id"] for c, *_ in built]
    assert len(ids) == sum(n for _, _, n in FI.CELLS) == 12
    for cell_id, _, n in FI.CELLS:
        assert ids.count(cell_id) == n
    assert dict((cid, n) for cid, _, n in FI.CELLS) == {"CORNER": 3, "MIDDLE": 3, "ROTATED": 6}


def test_the_first_iterations_come_first_in_the_order_of_the_table_and_the_rest_after(built):
    first = [c for c, *_ in built[:len(FI.CELLS)]]
    assert [c["id"] for c in first] == [cid for cid, *_ in FI.CELLS] and all(c["iteration"] == 1 for c in first)
    assert all(c["iteration"] > 1 for c, *_ in built[len(FI.CELLS):])


def test_the_sparsity_is_the_target_in_every_instance(built):
    for cell, _, _, _, inst in built:
        assert abs(inst.record["sparsity"][str(FI.X_PERCENT)] / FI.TARGET_SPARSITY - 1.0) <= fi_terms.TOLERANCE, cell["id"]
        assert inst.record["max_reward"] == pytest.approx(fi_terms.REWARD_SCALE, abs=0.01)


def test_the_kind_of_each_instance_is_the_one_of_its_cell(built):
    import interlude
    expected = {"corner": "round", "middle": "round", "elongated": "bump"}
    for cell, _, _, _, inst in built:
        assert inst.kind == cell["kind"] and interlude.interaction_kind(inst.reward_function()) == expected[cell["kind"]]


def test_the_corners_are_distinct_and_the_tilt_signs_are_balanced(built):
    corners = [tuple(inst.record["center"]) for cell, _, _, _, inst in built if cell["kind"] == "corner"]
    assert len(set(corners)) == len(corners) == 3 and all(c in {(0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)} for c in corners)
    tilts = [inst.record["tilt"] for cell, _, _, _, inst in built if cell["kind"] == "elongated"]
    assert sum(t > 0 for t in tilts) == sum(t < 0 for t in tilts) == 3


def test_the_world_seeds_are_distinct_and_do_not_meet_rw(built):
    seeds = [seed for _, _, seed, _, _ in built]
    assert len(set(seeds)) == len(seeds)
    rw_seeds = {seed for _, _, seed, *_ in RW._instances_built()}
    assert not set(seeds) & rw_seeds and min(seeds) > max(rw_seeds)


def test_instances_carry_a_design_record_the_interlude_settings_and_a_length():
    for inst in FI.instances():
        d = inst.design
        assert d["experiment"] == "FI" and d["iteration"] >= 1 and d["cell"] and d["rule"]["kind"] == d["kind"]
        json.dumps(d)                                                              # (it is stored as JSON in the asset)
        assert inst.session_fields["sessionDuration"] == FI.SECONDS
        f = inst.interlude_fields
        assert (f["interludeTrialCount"], f["interludeInteractionTrials"], f["interludeRepeatCount"], f["interludePeakTrials"], f["interludeFeatureTrials"]) == (20, 17, 3, 0, 0)
        assert inst.fields["moistureVaries"] is True and inst.fields["moistureIsFeature"] is False
        assert inst.fields["rewardFunction.factors.Array.size"] == 0 and inst.fields["rewardFunction.bumps.Array.size"] == 1


def test_only_the_first_iteration_has_a_hint_and_only_combination_is_bold():
    texts = FI.texts()
    by_cell = {inst.name.split("_S")[1]: inst.design for inst in FI.instances()}
    for number, d in by_cell.items():
        text = texts[f"instructions_S{number}.txt"]
        if d["iteration"] > 1:
            assert text == "Find the best fruit\n\nThis is a new area.\nCollect as many points as you can.\n\nPress [Enter] to begin"
        else:
            assert FI.HINT in text
    assert FI.HINT.count("**") == 2 and FI.HINT.split("**")[1] == "combination"
    assert texts["instructions_interlude.txt"].startswith("Choose the best fruit")
