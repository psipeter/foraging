"""The FI design module (design/FI.py): the instance list and its order, the rules and their matched sparsity, the hints, the Interlude settings, and the texts."""
import json

import pytest

import fi_terms
from design import FI, RW


@pytest.fixture(scope="module")
def built():
    return FI._instances_built()


def test_every_cell_has_its_iterations(built):
    ids = [c["id"] for c, *_ in built]
    assert len(ids) == len(FI.CELLS) * FI.ITERATIONS == 21
    for cell_id, *_ in FI.CELLS:
        assert ids.count(cell_id) == FI.ITERATIONS


def test_the_first_iterations_come_first_in_the_order_of_the_table_and_the_rest_after(built):
    first = [c for c, *_ in built[:len(FI.CELLS)]]
    assert [c["id"] for c in first] == [cid for cid, *_ in FI.CELLS] and all(c["iteration"] == 1 for c in first)
    assert all(c["iteration"] > 1 for c, *_ in built[len(FI.CELLS):])
    assert built[0][0]["id"] == "SUM-shallow"


def test_the_sparsity_is_the_target_in_every_instance(built):
    for cell, _, _, _, inst in built:
        assert abs(inst.record["sparsity"][str(FI.X_PERCENT)] / FI.TARGET_SPARSITY - 1.0) <= fi_terms.TOLERANCE, cell["id"]
        assert inst.record["max_reward"] == pytest.approx(fi_terms.REWARD_SCALE, abs=0.01)


def test_the_rule_of_each_instance_is_the_one_of_its_cell(built):
    import interlude
    for cell, _, _, _, inst in built:
        assert inst.kind == cell["kind"] and interlude.interaction_kind(inst.reward_function()) == cell["kind"]


def test_steep_cells_have_steeper_sigmoids_than_shallow_ones(built):
    def k(inst):
        steepness = inst.record["steepness"]
        return steepness if isinstance(steepness, float) else min(steepness)
    shallow = [k(i) for c, _, _, _, i in built if c["level"] == "shallow"]
    steep = [k(i) for c, _, _, _, i in built if c["level"] == "steep"]
    assert max(shallow) < min(steep)


def test_the_world_seeds_are_distinct_and_do_not_meet_rw_or_fn(built):
    seeds = [seed for _, _, seed, _, _ in built]
    assert len(set(seeds)) == len(seeds)
    rw_seeds = {seed for _, _, seed, *_ in RW._instances_built()}
    assert not set(seeds) & rw_seeds and min(seeds) > max(rw_seeds)


def test_instances_carry_a_design_record_the_interlude_settings_and_a_length():
    for inst in FI.instances():
        d = inst.design
        assert d["experiment"] == "FI" and d["iteration"] >= 1 and d["cell"] and d["rule"]["kind"] == d["kind"]
        json.dumps(d)                                                              # (it is stored as JSON in the asset)
        assert inst.session_fields["sessionDuration"] in (FI.SUM_SECONDS, FI.OTHER_SECONDS)
        f = inst.interlude_fields
        assert (f["interludeTrialCount"], f["interludeInteractionTrials"], f["interludeRepeatCount"], f["interludePeakTrials"], f["interludeFeatureTrials"]) == (20, 17, 3, 0, 0)
        assert inst.fields["moistureVaries"] is True and inst.fields["moistureIsFeature"] is False


def test_only_the_first_iteration_has_a_hint_and_a_sum_says_add_up():
    texts = FI.texts()
    by_cell = {inst.name.split("_S")[1]: inst.design for inst in FI.instances()}
    for number, d in by_cell.items():
        text = texts[f"instructions_S{number}.txt"]
        if d["iteration"] > 1:
            assert text == "Find the best fruit\n\nThis is a new area.\nCollect as many points as you can.\n\nPress [Enter] to begin"
        elif d["kind"] == "sum":
            assert FI.HINT_SUM in text and "combination" not in text
        else:
            assert FI.HINT_COMBINATION in text and "add their own" not in text
    assert texts["instructions_interlude.txt"].startswith("Choose the best fruit")
