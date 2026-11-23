"""The patch-foraging benchmarks (patch_foraging.py): the DP and the marginal value rule against brute force on stated patches, the end of the session, and the agents on a synthetic tiles world."""

import numpy as np
import pytest

import patch_foraging as pf
import synthetic
import tile_calibration as tc
import world

FRUITS, HARVEST, C_IN, C_TRAVEL = 1, 1.0, 0.0, 3.0


def model(values, tiles=3, horizon=60.0, dt=0.25, c_in=C_IN, c_travel=C_TRAVEL):
    return pf.PatchModel([values] * tiles, FRUITS, HARVEST, c_in, c_travel, horizon, dt)


def best_fixed_number_rate(values, c_in=C_IN, c_travel=C_TRAVEL):
    """max over k of the points of the k best bushes over the seconds of reaching the patch and harvesting them (identical patches: the optimum of the stationary problem)."""
    v = np.sort(values)[::-1]
    rates = [FRUITS * v[:k].sum() / (c_travel + k * HARVEST + (k - 1) * c_in) for k in range(1, len(v) + 1)]
    return max(rates), 1 + int(np.argmax(rates))


@pytest.mark.parametrize("values", [[4.0, 2.0, 1.0], [5.0, 0.5], [3.0, 3.0, 3.0, 0.1], [1.0, 1.0]])
def test_the_stationary_rate_is_the_best_fixed_number_rate_on_identical_patches(values):
    rho, cont = model(values).stationary()
    best, k = best_fixed_number_rate(values)
    assert rho == pytest.approx(best, rel=1e-6)
    assert int(cont[0, :len(values)].sum()) == k and cont[0, :k].all()             # it takes the first k and no more


def test_the_marginal_value_rule_takes_the_bushes_whose_rate_reaches_the_long_run_rate():
    values = [4.0, 2.0, 0.5]
    rho = model(values).stationary()[0]
    marginal = [FRUITS * v / HARVEST >= rho for v in values]
    assert marginal == [True, True, False] and rho == pytest.approx(best_fixed_number_rate(values)[0], rel=1e-6)


def test_a_long_horizon_earns_the_stationary_rate_and_never_takes_what_the_rate_leaves():
    m = model([4.0, 2.0, 1.0], horizon=600.0, dt=0.5)
    V, cont = m.finite_horizon()
    rho, stationary = m.stationary()
    assert V[-1] / 600.0 == pytest.approx(rho, rel=0.03)
    k = int(300.0 / m.dt)
    assert cont[:, k, 0].all() and not cont[:, k, 2].any() and not (cont[:, k, :] & ~stationary).any()     # the staircase of a finite horizon leaves ties, never a bush the rate would leave


def test_near_the_end_of_the_session_the_finite_horizon_takes_a_bush_the_rate_would_leave():
    m = model([5.0, 0.5], horizon=30.0, dt=0.25)
    _, cont = m.finite_horizon()
    assert not m.stationary()[1][0, 1]                                             # in the middle of the session the second bush is left
    assert cont[0, int(2.0 / m.dt), 1]                                             # with 2 s left no fresh patch can be reached: it is taken
    assert not cont[0, int(20.0 / m.dt), 1]


def test_the_average_costs_of_a_tiles_world_are_a_step_in_a_patch_and_a_longer_one_between():
    params = synthetic.session(visible=("shape", "color"), layout="tiles", assignment="tiles")
    w = world.generate_world(params, 1)
    tile_of, _ = tc.tile_of_world(w)
    reach = w.canopy_radius + params.harvest_range_gap_base + params.harvest_range_gap_per_radius * w.canopy_radius
    c = pf.average_costs(w.pos, w.canopy_radius, reach, tile_of, w.move_speed, 35.0, w.fruit_count, w.fruit_duration)
    assert c["harvest"] == pytest.approx(w.fruit_count * w.fruit_duration)
    assert 0.0 < c["c_in"] < c["c_travel"] < 40.0


def test_the_agents_play_a_tiles_world_and_the_marginal_value_rule_takes_what_the_optimal_rate_does():
    params = synthetic.session(visible=("shape", "color"), layout="tiles", assignment="tiles", tile_placement="balanced", tile_sum_tol=1.0, session_duration=90.0)
    w = world.generate_world(params, 2)
    totals = {n: pf.run(n, w).total for n in pf.FACTORIES}
    assert all(t > 0 for t in totals.values()) and totals["mvt"] == totals["dp_average"]
    tile_of, _ = tc.tile_of_world(w)
    simple = max(tc.calibrate_world(w, [1, 2, 3, 4, 9])[n][0] for n in ("top-1", "top-2", "top-3", "top-4", "top-9"))
    assert totals["dp_average"] > 0.85 * simple and totals["dp_finite"] > 0.85 * simple


def test_a_faster_believed_step_inside_a_patch_makes_the_benchmark_stay_longer_and_the_default_is_unchanged():
    params = synthetic.session(visible=("shape", "color"), layout="tiles", assignment="tiles", tile_placement="balanced", tile_sum_tol=1.0, session_duration=90.0)
    w = world.generate_world(params, 2)
    tile_of, _ = tc.tile_of_world(w)
    per_visit = lambda c_in: tc.route_stats(pf.run("mvt", w, c_in), tile_of, w.value)["per_visit"]
    assert pf.run("mvt", w).total == pf.run("mvt", w, None).total
    assert per_visit(0.2) >= per_visit(None)                      # believing a cheaper step cannot make it leave sooner
