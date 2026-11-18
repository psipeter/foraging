"""The pilot report (pilot_report.py): the span-and-hold check on stated numbers, and the metrics of a synthetic tiles world."""

import numpy as np

import pilot_report as pr
import synthetic
import value_maps
import world

SPEC = {"vary": {"interaction": 0.3}, "hold": {"gini": ("abs", 0.03), "mean_bush_value": ("rel", 0.1), "tile_sum_dev": ("max", 1.0)}, "limit": {"max": 8.0}}


def sessions(**each):
    base = {"interaction": 0.05, "gini": 0.4, "mean_bush_value": 2.2, "tile_sum_dev": 0.2, "max": 6.0}
    return [{**base, **{k: v[i] for k, v in each.items()}} for i in range(3)]


def flags(rows):
    return {(k, role) for k, role, _, _, flag in rows if flag}


def test_a_knob_that_rises_by_its_span_with_everything_else_held_passes():
    assert flags(pr.span_and_hold(SPEC, sessions(interaction=(0.05, 0.3, 0.6)))) == set()


def test_a_knob_that_does_not_rise_or_spans_too_little_is_flagged():
    assert flags(pr.span_and_hold(SPEC, sessions(interaction=(0.05, 0.4, 0.3)))) == {("interaction", "vary")}
    assert flags(pr.span_and_hold(SPEC, sessions(interaction=(0.05, 0.1, 0.2)))) == {("interaction", "vary")}


def test_a_held_metric_that_moves_and_a_peak_over_the_cap_are_flagged():
    rows = pr.span_and_hold(SPEC, sessions(interaction=(0.05, 0.3, 0.6), gini=(0.4, 0.45, 0.5), mean_bush_value=(2.0, 2.2, 2.6), tile_sum_dev=(0.1, 0.2, 1.5), max=(6.0, 7.0, 9.0)))
    assert flags(rows) == {("gini", "hold"), ("mean_bush_value", "hold"), ("tile_sum_dev", "hold"), ("max", "limit")}


def test_a_metric_some_session_lacks_is_not_checked():
    rows = pr.span_and_hold({"hold": {"learner": ("rel", 0.2)}}, [{"learner": 700.0}, {}, {"learner": 100.0}])
    assert rows == []


def test_the_metrics_of_a_balanced_tiles_world_describe_its_map_and_patches():
    valuemap = value_maps.ValueMap(value_maps.wide_corner().bumps, {"type": "flat", "sd": 0.6}, {"type": "gain", "value": 1.5})
    params = synthetic.session(visible=("shape", "color"), valuemap=valuemap, layout="tiles", assignment="tiles", tile_placement="balanced", tile_sum_tol=1.0)
    w = world.generate_world(params, 1)
    m = pr.session_metrics(valuemap, w)
    assert m["gain"] == 1.5 and 0.0 < m["gini"] < 1.0 and m["tile_sum_dev"] <= 1.0 and m["n_tiles"] > 10
    assert abs(m["mean_bush_value"] - w.value.mean()) < 1e-9 and m["contrast"] < 0.1 and m["diversity"] > 0.5
    assert np.isclose(m["travel_time"], (w.terrain.tiles.pitch - 2.0 * w.terrain.tiles.cluster_radius) / float(w.params.player_move_speed))
