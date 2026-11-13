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
    p = synthetic.session(visible=("shape", "color"), weights={"shape": 0.5, "color": 0.5}, layout="tiles", assignment="tiles", session_duration=120.0, **extra)
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
    out = tc.calibrate_world(w, [1, 4], quantiles=(50,), plan=True, beam_width=20)
    assert set(out) == {"top-1", "top-4", "thr-50", "greedy", "plan"}
    tile_of, _ = tc.tile_of_world(w)
    again = sim.run_episode(tc.oracle(tc.TileTopK(4).bind(tile_of)), w)
    assert out["top-4"][0] == again.total and all(total > 0 for total, _ in out.values())
