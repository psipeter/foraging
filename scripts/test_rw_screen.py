"""The RW screening script (scripts/rw_screen.py): the cells, one instance, the outcomes read from an episode, resuming, and that one long run gives the shorter lengths."""

import csv
import math
import gzip
import json

import numpy as np
import pytest

import agents
import rw_peaks
import rw_screen
import sim
import synthetic
import world

BASE = synthetic.TEMPLATE                           # the screen's base session is a parameter: the tests name the template, not a shipped experiment
SMALL = {"1p1f_s1", "2p1f_s1_d3_r0.6"}


def test_the_cells_are_possible_unique_and_cover_the_four_types():
    table = rw_screen.cells()
    assert len({c["id"] for c in table}) == len(table) and [c["index"] for c in table] == list(range(len(table)))
    assert {(c["n_peaks"], c["dims"]) for c in table} == set(rw_screen.TYPES)
    for c in table:
        assert c["spread"] >= rw_peaks.narrowest_spread(rw_screen.N_TYPICAL, c["dims"], rw_peaks.NARROWEST_EXPECTED) - 1e-9
        assert c["spread"] <= 0.9 * rw_peaks.MAX_SPREAD + 1e-9
        if c["n_peaks"] == 2:
            assert rw_peaks.fits(c["spread"], c["dims"], c["separation"]) and c["separation"] in rw_screen.SEPARATIONS and c["ratio"] in rw_screen.HEIGHT_RATIOS
        else:
            assert c["separation"] is None and c["ratio"] is None
    assert [c["spread"] for c in table if c["id"].startswith("1p1f")] == sorted(c["spread"] for c in table if c["id"].startswith("1p1f"))


def test_an_instance_is_the_same_each_time_and_every_peak_has_its_bushes():
    cell = next(c for c in rw_screen.cells() if c["id"] == "2p2f_s0_d3_r0.6")
    a, b = rw_screen.build_instance(cell, 3, BASE), rw_screen.build_instance(cell, 3, BASE)
    assert a[0] == b[0] and a[2] == b[2] and np.array_equal(a[3].shape, b[3].shape)
    assert min(rw_peaks.bush_counts(a[2], a[3].shape, a[3].color)) >= rw_peaks.MIN_PEAK_BUSHES
    assert a[2].heights[1] == pytest.approx(0.6 * a[2].heights[0])


def test_an_instance_that_cannot_have_its_bushes_is_given_up_and_reported(monkeypatch):
    monkeypatch.setattr(rw_screen, "MAX_ATTEMPTS", 2)
    monkeypatch.setattr(rw_peaks, "MIN_PEAK_BUSHES", 10_000)
    cell = next(c for c in rw_screen.cells() if c["id"] == "1p1f_s1")
    assert rw_screen.build_instance(cell, 0, BASE) is None
    info, rows, logs = rw_screen.run_instance((cell, 0, ("nearest",), BASE))
    assert info["status"].startswith("no world") and rows == [] and logs == []


def test_a_run_writes_the_three_files_and_each_row_agrees_with_its_fruit_log(tmp_path):
    played = rw_screen.run("t", worlds=2, agent_names=("nearest", "learner"), cell_ids=SMALL, directory=tmp_path, base=BASE, log=lambda *_: None)
    assert played == 4
    paths = rw_screen.files("t", tmp_path)
    episodes = list(csv.DictReader(open(paths["episodes.csv"])))
    instances = list(csv.DictReader(open(paths["instances.csv"])))
    logs = [json.loads(line) for line in gzip.open(paths["fruits.jsonl.gz"], "rt")]
    assert len(episodes) == 8 and len(instances) == 4 and len(logs) == 8 and all(i["status"] == "ok" for i in instances)
    by_key = {(e["instance"], e["agent"]): e for e in logs}
    for row in episodes:
        scores = [float(row[f"score_{d}"]) for d in rw_screen.DURATIONS]
        assert scores == sorted(scores)                                                       # a score only grows with the session's length
        log = by_key[(row["instance"], row["agent"])]
        assert sum(log["reward"]) == pytest.approx(scores[-1])
        assert sum(1 for r in log["region"] if r == 1) == int(row["n30_global"])
        if row["first30_global"] != "":
            assert 0.0 <= float(row["first30_global"]) <= max(rw_screen.DURATIONS) and int(row["n30_global"]) >= 1
        else:
            assert int(row["n30_global"]) == 0
        assert (row["n30_local"] == "") == (row["n_peaks"] == "1")                              # one-peak rows have the local peak's columns empty


def test_a_second_run_plays_nothing_again_and_adds_no_rows(tmp_path):
    kwargs = dict(worlds=2, agent_names=("nearest",), cell_ids={"1p1f_s1"}, directory=tmp_path, base=BASE, log=lambda *_: None)
    assert rw_screen.run("t", **kwargs) == 2
    before = open(rw_screen.files("t", tmp_path)["episodes.csv"]).read()
    assert rw_screen.run("t", **kwargs) == 0
    assert open(rw_screen.files("t", tmp_path)["episodes.csv"]).read() == before
    assert rw_screen.run("t", **{**kwargs, "worlds": 3}) == 1                              # a larger count plays only the new one


@pytest.mark.parametrize("name", rw_screen.AGENTS)
def test_the_score_read_from_the_long_run_equals_a_session_of_that_length(name):
    cell = next(c for c in rw_screen.cells() if c["id"] == "1p1f_s1")
    seed, _, peaks, long_world = rw_screen.build_instance(cell, 1, BASE)
    long_result = sim.run_episode(agents.REGISTRY[name](), long_world)
    fruits = np.array(long_result.fruits, dtype=float).reshape(-1, 5)
    for length in (60, 120):
        params = synthetic.session(visible=("shape", "color"), weights={"shape": 1.0}, base=BASE, std=rw_screen.REWARD_STD, reward_function=peaks.reward_function(), spatial_balance=0,
                                   feature_balance=0, feature_coverage=1, session_duration=float(length))
        short = sim.run_episode(agents.REGISTRY[name](), world.generate_world(params, seed))
        assert fruits[fruits[:, 0] <= length, 3].sum() == pytest.approx(short.total)


def test_an_agent_that_depends_on_the_sessions_length_is_refused(tmp_path):
    with pytest.raises(ValueError, match="depends on the session's length"):
        rw_screen.run("t", worlds=1, agent_names=("softmax_horizon",), directory=tmp_path, base=BASE, log=lambda *_: None)


def test_a_failing_instance_is_recorded_and_does_not_end_the_run(monkeypatch):
    monkeypatch.setattr(rw_screen, "build_instance", lambda *a, **k: 1 / 0)
    cell = rw_screen.cells()[0]
    info, rows, logs = rw_screen.run_instance((cell, 0, ("nearest",), BASE))
    assert info["status"].startswith("error: ZeroDivisionError") and rows == [] and logs == []


def test_the_instances_are_played_world_by_world_across_the_cells_so_an_early_stop_is_balanced(tmp_path):
    seen = []
    rw_screen.run("t", worlds=2, agent_names=("nearest",), cell_ids={"1p1f_s0", "1p1f_s1", "1p1f_s2"}, directory=tmp_path, base=BASE, log=lambda *_: None)
    with open(rw_screen.files("t", tmp_path)["instances.csv"]) as f:
        seen = [row["instance"] for row in csv.DictReader(f)]
    assert [name.rsplit("_w", 1)[1] for name in seen] == ["0", "0", "0", "1", "1", "1"]


def test_a_finer_grid_has_more_cells_and_the_levels_are_a_parameter():
    coarse = rw_screen.cells(levels=3, separations=(3.0, 4.5, 6.0), ratios=(0.4, 0.6, 0.8))
    fine = rw_screen.cells(levels=6, separations=(3.0, 4.0, 5.0, 6.0, 8.0), ratios=(0.3, 0.45, 0.6, 0.75, 0.9))
    assert len(fine) > 3 * len(coarse) and len(coarse) == 39


def test_the_summary_has_a_row_for_each_cell_agent_and_length_with_trapped_only_for_two_peaks(tmp_path):
    rw_screen.run("t", worlds=2, agent_names=("nearest", "learner"), cell_ids=SMALL, directory=tmp_path, base=BASE, log=lambda *_: None)
    table = rw_screen.summary("t", tmp_path, durations=(60, 120, 240))
    assert len(table) == 2 * 2 * 3 and table["found_global"].between(0, 1).all() and table["n"].eq(2).all()
    one = table[table["n_peaks"] == 1]
    assert (one["trapped"] == 0).all() and (one["found_local"] == 0).all()
    assert table.groupby(["cell", "agent"])["score"].apply(lambda s: s.is_monotonic_increasing or s.nunique() == 1).all()


def test_no_cell_asks_for_two_peaks_that_merge_or_do_not_fit():
    for c in rw_screen.cells(levels=12, separations=(3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 9, 10), ratios=(0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95)):
        if c["n_peaks"] == 2:
            assert rw_peaks.separable(c["separation"], c["ratio"]) and rw_peaks.fits(c["spread"], c["dims"], c["separation"])


def test_every_two_peak_instance_of_the_finest_grid_can_be_drawn_at_the_cells_edge_of_what_fits():
    for c in rw_screen.cells(levels=12, separations=(3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 9, 10), ratios=(0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95)):
        if c["n_peaks"] == 2:
            for seed in range(3):
                rw_peaks.draw_peaks(np.random.default_rng(seed), ("shape",) if c["dims"] == 1 else ("shape", "color"), 2, c["spread"], c["separation"], c["ratio"])


def test_the_files_have_fixed_columns_even_when_the_first_instance_failed_and_a_failed_one_is_played_again(tmp_path, monkeypatch):
    real = rw_screen.run_instance
    calls = []

    def flaky(task):
        calls.append(task[1])
        if len(calls) == 1:
            return {"instance": f"{task[0]['id']}_w{task[1]}", "cell": task[0]["id"], "k": task[1], "status": "error: ValueError: made up"}, [], []
        return real(task)
    monkeypatch.setattr(rw_screen, "run_instance", flaky)
    kwargs = dict(worlds=2, agent_names=("nearest",), cell_ids={"1p1f_s1"}, directory=tmp_path, base=BASE, log=lambda *_: None)
    rw_screen.run("t", **kwargs)
    rows = list(csv.DictReader(open(rw_screen.files("t", tmp_path)["instances.csv"])))
    assert list(rows[0]) == rw_screen.INSTANCE_FIELDS and [r["status"] for r in rows][0].startswith("error") and rows[1]["status"] == "ok" and rows[1]["attempts"] != ""
    monkeypatch.setattr(rw_screen, "run_instance", real)
    assert rw_screen.run("t", **kwargs) == 1                                               # only the one that failed
    import pandas as pd
    assert len(pd.read_csv(rw_screen.files("t", tmp_path)["episodes.csv"])) == 2


def test_a_run_in_which_many_instances_fail_stops_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(rw_screen, "run_instance", lambda task: ({"instance": f"{task[0]['id']}_w{task[1]}", "cell": task[0]["id"], "k": task[1], "status": "error: ValueError: x"}, [], []))
    with pytest.raises(RuntimeError, match="stopping"):
        rw_screen.run("t", worlds=3, agent_names=("nearest",), directory=tmp_path, base=BASE, log=lambda *_: None)


def test_the_analysis_questions_run_on_a_small_run_and_trapped_needs_two_peaks(tmp_path):
    import rw_screen_analysis as analysis
    rw_screen.run("t", worlds=3, agent_names=("nearest", "learner"), cell_ids=SMALL, directory=tmp_path, base=BASE, log=lambda *_: None)
    episodes = analysis.load("t", tmp_path)
    assert set(analysis.agent_differences(episodes, lengths=(60, 240)).index) == {"nearest", "learner"}
    assert set(analysis.time_to_find(episodes, bins=2)) == {"1p1f", "2p1f"}
    assert set(analysis.trapped_grid(episodes)) == {"2p1f"}
    assert set(analysis.trapping_cost(episodes).index.get_level_values("dims")) == {1}
    late = analysis.settled("t", tmp_path)
    assert len(late) == 6 and late["settled_local_240"].isin([0.0, 1.0]).all() and (late["late_local_240"] >= 0).all()


def test_the_ladder_cells_are_possible_and_their_spreads_follow_each_peaks_own_share():
    table = rw_screen.design_cells("ladder")
    assert [c["id"] for c in table][:4] == ["B1", "B2", "B3", "B4"] and len({c["id"] for c in table}) == len(table) == 10
    for c in table:
        per_peak = c["total"] / c["n_peaks"]
        assert c["spread"] == pytest.approx(rw_peaks.spread_for_sparsity(per_peak, c["dims"], 30))
        assert rw_peaks.sparsity_for_spread(c["spread"], c["dims"], 30) == pytest.approx(per_peak)
        if c["n_peaks"] == 2:
            assert rw_peaks.fits(c["spread"], c["dims"], c["separation"]) and rw_peaks.separable(c["separation"], c["ratio"])
        assert c["guarantee"] == (30, 3) and c["length"] in (120, 180)


def test_a_ladder_instance_holds_the_planned_bushes_in_each_peaks_top_30_percent_region():
    for cell_id in ("T2F-5-far", "B3"):
        cell = next(c for c in rw_screen.design_cells("ladder") if c["id"] == cell_id)
        seed, attempts, peaks, w = rw_screen.build_instance(cell, 0, BASE)
        assert min(rw_peaks.bush_counts(peaks, w.shape, w.color, 30)) >= 3


def test_a_design_run_writes_the_stage_sparsity_and_length_and_the_design_report_reads_them(tmp_path, capsys):
    ids = {"B1", "T2F-5-far"}
    rw_screen.run("t", worlds=3, agent_names=("nearest", "learner"), cell_ids=ids, directory=tmp_path, base=BASE, log=lambda *_: None, design="ladder")
    rows = list(csv.DictReader(open(rw_screen.files("t", tmp_path)["episodes.csv"])))
    assert {r["id"] for r in rows} == ids and {r["stage"] for r in rows} == {"B", "T"} and {r["length"] for r in rows} == {"120", "180"} and {r["total"] for r in rows} == {"0.15", "0.05"}
    table = rw_screen.design_report("t", tmp_path)
    assert set(table["cell"]) == ids and table["found"].between(0, 1).all() and table["model"].between(0, 1).all()
    assert (table[table.peaks == 1]["trapped"] == 0).all() and "strict" in capsys.readouterr().out


def test_the_model_matches_the_screen_at_the_one_peak_levels_it_was_fitted_on():
    assert rw_screen.model_found(1, 0.0258, 120, 30) == pytest.approx(0.66, abs=0.05)        # rw2: the sparsest one-feature level, found by 120 s
    assert rw_screen.model_found(2, 0.05, 180, 30) > rw_screen.model_found(2, 0.05, 180, 10)       # the strict region is the harder one
    assert rw_screen.model_found(1, 0.1, 60, 10) < rw_screen.model_found(1, 0.1, 180, 10) < 1.0


def test_the_human_proxy_reads_discovery_at_a_shorter_length_and_never_exceeds_the_full_length(tmp_path):
    import rw_screen_analysis as analysis
    rw_screen.run("t", worlds=4, agent_names=("learner", "softmax"), cell_ids={"B1", "T2F-5-far"}, directory=tmp_path, base=BASE, log=lambda *_: None, design="ladder")
    t = analysis.human_proxy(analysis.load("t", tmp_path), ks=(2, 3))
    assert set(t.index) == {"B1", "T2F-5-far"} and (t["found_k3"] <= t["found_k2"] + 1e-12).all() and (t["found_k2"] <= t["found_agent"] + 1e-12).all()
    assert (t.loc["B1", ["trapped_agent", "trapped_k2", "trapped_k3"]] == 0).all() and t.loc["T2F-5-far", "length"] == 180


def test_the_crossing_design_has_both_crossing_factors_at_two_sparsities_with_the_smaller_margin():
    table = rw_screen.design_cells("crossing")
    assert len(table) == 8 and {c["total"] for c in table} == {0.15, 0.10} and all(c["margin"] == 1.0 and c["n_peaks"] == 2 and c["dims"] == 2 for c in table)
    for total in (0.15, 0.10):
        cells_ = [c for c in table if c["total"] == total]
        assert sorted((c["separation"], c["ratio"]) for c in cells_) == [(3.0, 0.75), (4.5, 0.3), (4.5, 0.75), (4.5, 0.9)]
    cell = next(c for c in table if c["id"] == "T15-sep4.5-r0.9")
    seed, attempts, peaks, w = rw_screen.build_instance(cell, 0, BASE)
    assert math.dist(*peaks.centers) / peaks.spread == pytest.approx(4.5) and peaks.heights[1] == pytest.approx(0.9 * peaks.heights[0])
