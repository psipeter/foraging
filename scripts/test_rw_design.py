"""The RW design module (design/RW.py): the instance list, its order, the peaks and their bushes, the hints; and the Interlude's peak trials."""
import numpy as np
import pytest

import interlude
import rw_peaks
import world
from design import RW


@pytest.fixture(scope="module")
def built():
    return RW._instances_built()


def test_the_design_has_every_cell_the_stated_number_of_times(built):
    cells = [c["id"] for c, *_ in built]
    assert len(cells) == 4 + 3 * 3 * 2
    for cid in ("B1", "B2", "B3", "B4"):
        assert cells.count(cid) == 1
    for level in RW.S_LEVELS:
        assert cells.count(f"S2F-{level}") == RW.ITERATIONS
    for level in RW.T_LEVELS:
        assert cells.count(f"T2F-{level}") == RW.ITERATIONS


def test_the_baseline_comes_first_then_one_pass_through_the_cells(built):
    stages = [c["stage"] for c, *_ in built]
    assert stages[:4] == ["B"] * 4 and "B" not in stages[4:]
    first_pass = [c["id"] for c, *_ in built[4:4 + 6]]
    assert sorted(first_pass) == sorted([f"S2F-{s}" for s in RW.S_LEVELS] + [f"T2F-{t}" for t in RW.T_LEVELS])
    assert all(c["iteration"] == 1 for c, *_ in built[:4 + 6])
    assert all(c["iteration"] > 1 for c, *_ in built[4 + 6:])


def test_each_peak_keeps_its_bushes_and_the_sparsity_is_the_stated_one(built):
    for cell, number, seed, attempt, peaks, spread in built:
        assert len(peaks.centers) == cell["n_peaks"] and peaks.dims == cell["dims"]
        stated = rw_peaks.sparsity_for_spread(spread, cell["dims"], 30) * cell["n_peaks"]
        assert stated == pytest.approx(cell["total"], rel=0.02)
        if cell["n_peaks"] == 2:
            assert peaks.heights[1] / peaks.heights[0] == pytest.approx(cell["ratio"], abs=1e-3)
            assert RW.rw_peaks.fits(spread, cell["dims"], cell["separation"], cell["margin"])


def test_one_feature_peaks_alternate_between_the_features(built):
    paying = [peaks.paying[0] for cell, _, _, _, peaks, _ in built if cell["dims"] == 1]
    assert paying == ["shape", "color"]


def test_instances_carry_a_design_record_and_the_iteration_for_reduced_runs():
    for inst in RW.instances():
        d = inst.design
        assert d["experiment"] == "RW" and d["iteration"] >= 1 and d["cell"] and "centers" in d and "heights" in d
        assert inst.session_fields["sessionDuration"] in (120, 180)


def test_every_session_has_twenty_trials_seventeen_peak_pairs_and_three_repeats():
    for inst in RW.instances():
        f = inst.interlude_fields
        assert (f["interludeTrialCount"], f["interludePeakTrials"], f["interludeRepeatCount"], f["interludeFeatureTrials"]) == (20, 17, 3, 0)


def test_hints_name_the_features_and_only_the_first_two_peak_sessions_say_two_kinds():
    texts = RW.texts()
    by_cell = {inst.design["cell"]: inst.name.split("_S")[1] for inst in RW.instances()}
    assert "two kinds" in texts[f"instructions_S{by_cell['B3']}.txt"] and "two kinds" in texts[f"instructions_S{by_cell['B4']}.txt"]
    assert not any("two kinds" in text for name, text in texts.items() if name not in (f"instructions_S{by_cell['B3']}.txt", f"instructions_S{by_cell['B4']}.txt"))
    assert "Only **one**" in texts[f"instructions_S{by_cell['B1']}.txt"]


class FakeDesigner:
    """Just what `peak_trial` reads: parameters with a reward function, a random stream, bush construction and value."""
    def __init__(self, peaks):
        self.p = type("P", (), {"reward_function": peaks.reward_function()})()
        self.rng = np.random.default_rng(3)
        self._used = 0

    def bush(self, i, side, shape, color):
        return {"shape": shape, "color": color, "moisture": 0.5, "side": side}

    def value(self, bush):
        return float(world.bush_value(self.p.reward_function, bush["shape"], bush["color"], bush["moisture"]))

    def attempt(self, builder, dm=None):
        for _ in range(50):
            pair = builder(0)
            if pair is not None:
                return 0, pair[0], pair[1]
        raise RuntimeError("no trial")


def two_peaks():
    return rw_peaks.Peaks(("shape", "color"), 0.15, ((0.25, 0.25), (0.75, 0.75)), (4.0, 2.0))


def test_peak_trials_pair_the_stated_classes_and_the_better_side_is_correct():
    des = FakeDesigner(two_peaks())
    trials = interlude.peak_trials(des, 17, np.random.default_rng(1))
    kinds = [t["varied"] for t in trials]
    assert (kinds.count("0>1"), kinds.count("0>off"), kinds.count("1>off")) == (6, 6, 5)
    for t in trials:
        better, worse = (int(x) if x != "off" else x for x in t["varied"].split(">"))
        left_is_better = des.value(t["left"]) > des.value(t["right"])
        high, low = (t["left"], t["right"]) if left_is_better else (t["right"], t["left"])
        assert interlude._in_class(interlude.peak_shares(des.p.reward_function, high["shape"], high["color"]), better)
        assert interlude._in_class(interlude.peak_shares(des.p.reward_function, low["shape"], low["color"]), worse)
        assert abs(des.value(t["left"]) - des.value(t["right"])) >= interlude.PEAK_MIN_GAP
    sides = [des.value(t["left"]) > des.value(t["right"]) for t in trials]
    assert 0.3 < np.mean(sides) < 0.7


def test_the_reward_gaps_of_a_pair_type_are_spread_not_bunched():
    des = FakeDesigner(two_peaks())
    trials = interlude.peak_trials(des, 17, np.random.default_rng(1))
    for kind in ("0>1", "0>off", "1>off"):
        gaps = sorted(abs(des.value(t["left"]) - des.value(t["right"])) for t in trials if t["varied"] == kind)
        assert gaps[-1] - gaps[0] > 0.3 and len(set(np.round(gaps, 3))) == len(gaps)


def test_no_two_trials_look_alike():
    des = FakeDesigner(two_peaks())
    trials = interlude.peak_trials(des, 17, np.random.default_rng(1))
    pts = [(t["left"]["shape"], t["left"]["color"], t["right"]["shape"], t["right"]["color"]) for t in trials]
    near = lambda a, b: abs(a[0] - b[0]) <= 0.05 and abs(a[1] - b[1]) <= 0.05
    alike = [(i, j) for i in range(len(pts)) for j in range(i + 1, len(pts))
             if (near(pts[i][:2], pts[j][:2]) and near(pts[i][2:], pts[j][2:])) or (near(pts[i][:2], pts[j][2:]) and near(pts[i][2:], pts[j][:2]))]
    assert not alike


def test_one_peak_trials_are_peak_against_off():
    peaks = rw_peaks.Peaks(("shape", "color"), 0.2, ((0.5, 0.5),), (4.0,))
    trials = interlude.peak_trials(FakeDesigner(peaks), 17, np.random.default_rng(1))
    assert {t["varied"] for t in trials} == {"0>off"} and len(trials) == 17


def test_repeats_go_one_to_each_pair_type_with_the_sides_alternating():
    des = FakeDesigner(two_peaks())
    trials = interlude.peak_trials(des, 17, np.random.default_rng(1))
    copies = interlude.pick_repeats(trials, 3, des, by_group=True)
    assert sorted(c["varied"] for c in copies) == ["0>1", "0>off", "1>off"]
    assert all(c["repeat_source"]["left"] is c["left"] for c in copies)
    left_correct = [des.value(c["left"]) > des.value(c["right"]) for c in copies]
    assert left_correct == [True, False, True]


def test_the_hash_of_a_session_without_peak_trials_is_unchanged_by_the_new_field():
    import fingerprint
    assert "interlude_peak_trials" in fingerprint.SIM_FIELDS and fingerprint.OMITTED_AT_DEFAULT == {"interlude_peak_trials": 0}
