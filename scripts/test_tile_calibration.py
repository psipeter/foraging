"""The tiles calibration (tile_calibration.py): the top-k policy does what it says, the route statistics count what they should, and the verdict reads the two conditions right.

Worlds are built from a stated configuration (`synthetic.session`: a tiles layout on the tutorial's terrain), not from a shipped session.
"""

import itertools

import numpy as np
import pytest

import sim
import synthetic
import tile_calibration as tc
import world


def tile_world(seed=0, **extra):
    p = synthetic.session(visible=("shape", "color"), layout="tiles", assignment="tiles", session_duration=120.0, **extra)
    return world.generate_world(p, seed)


def runs_of(w, k):
    tile_of, _ = tc.tile_of_world(w)
    r = sim.run_episode(tc.oracle(tc.TileTopK(k).bind(tile_of)), w)
    bushes = [int(b) for b, fruits, _ in r.trace if fruits > 0]
    return [(t, len(list(g))) for t, g in itertools.groupby(tile_of[bushes])], r


def test_top_k_takes_k_bushes_in_every_tile_it_leaves_and_visits_each_tile_once():
    w = tile_world(1)
    runs, _ = runs_of(w, 2)
    assert all(n == 2 for _, n in runs[:-1]) and 1 <= runs[-1][1] <= 2
    tiles_seen = [t for t, _ in runs]
    assert len(tiles_seen) == len(set(tiles_seen))             # no tile is visited twice while others are untouched


def test_exhaust_takes_the_whole_tile_before_it_leaves():
    w = tile_world(2)
    runs, _ = runs_of(w, int(w.params.tile_bushes))
    assert all(n == int(w.params.tile_bushes) for _, n in runs[:-1])


def test_top_k_takes_the_best_bushes_of_each_tile():
    w = tile_world(3)
    tile_of, _ = tc.tile_of_world(w)
    r = sim.run_episode(tc.oracle(tc.TileTopK(3).bind(tile_of)), w)
    taken = [int(b) for b, fruits, _ in r.trace if fruits > 0]
    first_tile = tile_of[taken[0]]
    best = set(np.flatnonzero(tile_of == first_tile)[np.argsort(-w.value[tile_of == first_tile])[:3]].tolist())
    assert set(taken[:3]) == best


def test_route_statistics_count_visits_tiles_and_the_top_half():
    tile_of = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    value = np.array([4.0, 3.0, 2.0, 1.0, 1.0, 2.0, 3.0, 4.0])
    result = sim.Result(0.0, 3, 30, 10.0, 6.0, 0.0, trace=[(0, 10, 40.0), (1, 10, 30.0), (7, 10, 40.0)], look_time=2.0, press_time=2.0)
    s = tc.route_stats(result, tile_of, value)
    assert (s["bushes"], s["visits"], s["tiles"]) == (3, 2, 2)
    assert s["per_visit"] == 1.5 and s["tile_share"] == pytest.approx(3 / 8) and s["top_half"] == 1.0
    assert s["walk_share"] == pytest.approx(10.0 / 20.0)
    assert tc.route_stats(sim.Result(0.0, 0, 0, 0.0, 0.0, 10.0), tile_of, value)["bushes"] == 0


def totals(per_policy, seeds=8):
    return {name: np.full(seeds, 100.0 * m) for name, m in per_policy.items()}


def test_the_threshold_policy_harvests_only_bushes_worth_the_threshold_while_such_bushes_last():
    w = tile_world(5)
    tile_of, _ = tc.tile_of_world(w)
    theta = float(np.percentile(w.value, 60))
    r = sim.run_episode(tc.oracle(tc.TileThreshold(theta).bind(tile_of)), w)
    taken = [int(b) for b, fruits, _ in r.trace if fruits > 0]
    assert len(taken) > 5 and all(w.value[b] >= theta for b in taken[:5])
    assert r.total > 0


def test_a_threshold_above_every_bush_falls_back_to_the_greedy_order():
    w = tile_world(6)
    tile_of, _ = tc.tile_of_world(w)
    r = sim.run_episode(tc.oracle(tc.TileThreshold(1e9).bind(tile_of)), w)
    assert r.total > 0 and r.n_visits > 3


def test_the_verdict_reads_the_two_conditions():
    ks = [1, 2, 3, 4]
    per_visit = {"top-1": 1.0, "top-2": 2.0, "top-3": 3.0, "top-4": 4.0, "thr-50": 2.5, "thr-90": 1.2}
    best, gain, _, favoured, few_good, text = tc.verdict(totals({"top-1": 3, "top-2": 5, "top-3": 6, "top-4": 5.5, "thr-50": 6.4, "thr-90": 4}), ks, per_visit)
    assert (best, favoured, few_good) == ("thr-50", True, True) and gain == pytest.approx(0.1636, abs=0.01) and text.startswith("FEW GOOD")
    always = totals({"top-1": 3, "top-2": 4, "top-3": 5, "top-4": 6, "thr-50": 5.5, "thr-90": 3})
    assert tc.verdict(always, ks, per_visit)[3:5] == (False, False) and tc.verdict(always, ks, per_visit)[5].startswith("EXHAUST")
    eager = totals({"top-1": 7, "top-2": 5, "top-3": 4, "top-4": 3, "thr-50": 4, "thr-90": 5})
    assert tc.verdict(eager, ks, per_visit)[5].startswith("TOO EAGER")
    many = totals({"top-1": 3, "top-2": 4, "top-3": 6.5, "top-4": 5.5, "thr-50": 5, "thr-90": 4})
    assert tc.verdict(many, ks, {**per_visit, "top-3": 6.0})[5].startswith("TOO MANY")


def test_a_gain_below_the_margin_or_within_the_noise_is_not_leaving_favoured():
    ks = [1, 2, 3, 4]
    per_visit = {f"top-{k}": float(k) for k in ks}
    small = totals({"top-1": 4.0, "top-2": 5.0, "top-3": 5.1, "top-4": 5.0})
    assert not tc.verdict(small, ks, per_visit)[3]              # 2% gain, margin 3%
    swing = np.array([400.0, -400.0] * 4)
    noisy = {"top-1": np.full(8, 400.0), "top-2": np.full(8, 500.0), "top-3": 540.0 + swing, "top-4": np.full(8, 500.0)}
    assert not tc.verdict(noisy, ks, per_visit, margin=0.0)[3]  # an 8% gain, but the seeds swing by several standard errors
    assert tc.verdict({**noisy, "top-3": np.full(8, 540.0)}, ks, per_visit, margin=0.0)[3]     # the same gain without the swing counts


def test_a_calibration_of_one_small_world_runs_every_policy_and_the_totals_are_the_engines():
    w = tile_world(4)
    out = tc.calibrate_world(w, [1, 4], quantiles=(50,))
    assert set(out) == {"top-1", "top-4", "thr-50", "greedy"}
    tile_of, _ = tc.tile_of_world(w)
    again = sim.run_episode(tc.oracle(tc.TileTopK(4).bind(tile_of)), w)
    assert out["top-4"][0] == again.total and all(total > 0 for total, _ in out.values())


def curve(values, seeds=12, spread=0.4):
    """Per-seed totals for policies with the stated means: the same swing in every policy, so the paired differences are exact."""
    swing = np.linspace(-spread, spread, seeds)
    return {name: np.array([v + w for w in swing]) for name, v in values.items()}


def test_the_shape_check_wants_the_best_inside_and_both_ends_clearly_worse():
    names = [f"top-{k}" for k in range(1, 6)]
    good = tc.profile_check(curve(dict(zip(names, [60, 90, 100, 98, 80]))), names)
    assert good["ok"] and good["best"] == "top-3" and good["plateau"] == ["top-3", "top-4"] and good["text"].startswith("SHAPE OK")
    assert good["loss"]["top-1"][0] == pytest.approx(0.4, abs=0.01) and good["loss"]["top-5"][0] == pytest.approx(0.2, abs=0.01)


def test_the_shape_check_names_a_best_at_an_end_and_an_end_that_barely_loses():
    names = [f"top-{k}" for k in range(1, 6)]
    always = tc.profile_check(curve(dict(zip(names, [60, 70, 80, 90, 100]))), names)
    assert not always["ok"] and not always["interior"] and always["text"].startswith("BEST AT AN END (top-5)") and "harvesting everything" in always["text"]
    eager = tc.profile_check(curve(dict(zip(names, [100, 90, 80, 70, 60]))), names)
    assert not eager["interior"] and "harvesting as little as possible" in eager["text"]
    flat = tc.profile_check(curve(dict(zip(names, [98, 99, 100, 99, 70]))), names)
    assert flat["interior"] and not flat["ok"] and flat["text"].startswith("FLAT ENDS") and "top-1" in flat["text"] and "top-5" not in flat["text"].split(";")[0]


def test_the_shape_check_needs_the_end_loss_to_exceed_the_swing_of_the_seeds():
    names = [f"top-{k}" for k in range(1, 4)]
    totals = {"top-1": np.array([100.0, 60.0, 130.0, 70.0, 95.0, 85.0]), "top-2": np.full(6, 100.0), "top-3": np.array([100.0, 70.0, 140.0, 60.0, 95.0, 85.0])}
    result = tc.profile_check(totals, names, margin=0.0)
    assert result["interior"] and not result["ok"]                                # the two ends average about the best's level and swing by many standard errors


def test_a_leaving_summary_of_small_worlds_is_plain_data():
    summary = tc.leaving_summary([tile_world(4), tile_world(4)], ks=[1, 2, 4], quantiles=(30, 60))
    assert summary["n_worlds"] == 2 and set(summary["means"]) == {"top-1", "top-2", "top-4", "thr-30", "thr-60", "greedy"}
    assert summary["top_k"]["best"] in ("top-1", "top-2", "top-4") and isinstance(summary["top_k"]["ok"], bool) and summary["thr_q"]["best"] in ("thr-30", "thr-60")
    import json
    json.dumps(summary)


def test_the_planner_check_reads_the_bushes_per_visit_against_both_ends_and_flags_a_weak_beam(monkeypatch):
    w = tile_world(4)                                                              # tiles of 9 bushes: the ends are 1 and 9, the edge 1 leaves 2 to 8 in the middle

    class Run:
        total = 100.0

    def check(per_visit, planner_total=100.0, simple=100.0):
        Run.total = planner_total
        monkeypatch.setattr(tc.sim, "run_episode", lambda agent, world: Run)
        monkeypatch.setattr(tc, "route_stats", lambda run, tile_of, value: {"per_visit": per_visit, "tile_share": 0.5, "top_half": 1.0, "bushes": 8, "visits": 2})
        monkeypatch.setattr(tc, "visit_sizes", lambda run, tile_of: [round(per_visit)] * 2)
        monkeypatch.setattr(tc, "calibrate_world", lambda world, ks, **k: {"top-1": (0.5 * simple, {}), "top-2": (simple, {}), "top-9": (0.8 * simple, {}), "thr-90": (0.6 * simple, {}), "thr-10": (0.97 * simple, {}), "greedy": (simple - 1, {})})
        return tc.planner_check(w)
    assert check(1.5)["flag"] == "eager" and "WARNING" in check(1.5)["text"]
    assert check(8.5)["flag"] == "exhaust" and check(5.0)["flag"] is None and check(2.0)["flag"] is None and check(8.0)["flag"] is None
    spectrum = check(5.0, planner_total=100.0, simple=100.0)
    assert spectrum["shares"]["top-1"] == pytest.approx(0.5) and spectrum["shares"]["top-2"] == pytest.approx(1.0) and "greedy" not in spectrum["shares"]
    assert spectrum["ends_near"] == ["thr-10"] and "thr-10 reaches 95% of the planner" in spectrum["text"] and "top-1 50%" in spectrum["text"]     # thr-10 gets within 3 percent of the planner: that extreme is not clearly worse
    weak = check(5.0, planner_total=90.0)
    assert weak["weak"] and weak["heuristic_best"] == "top-2" and "CAUTION" in weak["text"] and not check(5.0, planner_total=98.0)["weak"]


def test_the_planner_check_of_a_small_world_is_plain_data():
    out = tc.planner_check(tile_world(4), beam_width=20)
    assert out["per_visit"] >= 1 and out["visits"] >= 1 and sum(k * v for k, v in out["sizes"].items()) == out["bushes"] and out["flag"] in (None, "eager", "exhaust")
    import json
    json.dumps(out)
