"""The factors realised in a world (factors.py): each measure against a case whose answer is known. Sessions are stated configurations (synthetic.py), not shipped ones."""

import math

import numpy as np
import pytest

import factors
import synthetic
import value_maps
from world import generate_world


def session(**extra):
    return synthetic.session(visible=("shape", "color"), layout="tiles", assignment="tiles", **extra)


def measured(seed=1, **extra):
    return factors.measure(generate_world(session(**extra), seed))


def test_travel_time_is_the_gap_between_neighbouring_clusters_over_the_walking_speed():
    p = session(tile_radius=70.0, tile_cluster_radius=22.0)
    m = factors.measure(generate_world(p, 1))
    pitch = math.sqrt(3.0) * 70.0
    assert m["travel_time"] == pytest.approx((pitch - 44.0) / p.player_move_speed)
    assert m["travel_time_centres"] == pytest.approx(pitch / p.player_move_speed)
    assert m["travel_time"] <= m["travel_time_nearest_bush"] < m["travel_time_centres"]       # bushes stand inside the cluster disc: the nearest pair is no closer than the cluster edges
    assert m["walk_visits"] == pytest.approx(p.session_duration / m["travel_time"])


def test_a_larger_tile_means_a_longer_walk():
    assert measured(tile_radius=60.0)["travel_time"] < measured(tile_radius=80.0)["travel_time"]


def test_a_flat_map_has_no_contrast_and_no_diversity_and_a_constant_value():
    flat = value_maps.ValueMap((value_maps.Bump(0.5, 0.5, 1e4, 0.0, 0.0, 3.0),))
    w = generate_world(synthetic.session(visible=("shape", "color"), valuemap=flat, layout="tiles", assignment="tiles"), 1)
    m = factors.measure(w)
    assert m["contrast"] < 1e-6 and m["diversity"] < 1e-6 and m["neighbour_difference"] < 1e-6
    assert m["mean_bush_value"] == pytest.approx(3.0, abs=1e-6) and m["bush_gini"] < 1e-6


def test_tiles_of_a_single_point_each_have_no_diversity_but_do_differ_from_one_another():
    m = measured(tile_value_mode="random", tile_within_mode="scatter", tile_spread=0.0)
    assert m["diversity"] < 1e-9 and m["contrast"] > 0.2 and m["neighbour_difference"] > 0.2


def test_the_gain_scales_the_reward_measures_and_leaves_the_walk_alone():
    base = synthetic.DEFAULT_MAP
    doubled = value_maps.ValueMap(base.bumps, base.noise, {"type": "gain", "value": 2.0})
    a, b = (factors.measure(generate_world(synthetic.session(visible=("shape", "color"), valuemap=m, layout="tiles", assignment="tiles"), 1)) for m in (base, doubled))
    for key in ("contrast", "neighbour_difference", "diversity", "mean_bush_value", "max_bush_value"):
        assert b[key] == pytest.approx(2.0 * a[key], rel=1e-6), key
    assert b["bush_gini"] == pytest.approx(a["bush_gini"]) and b["travel_time"] == a["travel_time"]


def test_the_mean_value_and_the_noise_are_those_of_the_world():
    w = generate_world(session(), 2)
    m = factors.measure(w)
    assert m["mean_bush_value"] == pytest.approx(w.value.mean()) and m["n_bushes"] == w.n
    assert m["noise_sd"] == pytest.approx(math.sqrt(0.6 ** 2 + 1.0 / 12.0), abs=0.03)          # the stated SD plus the rounding of a fruit to whole points
    assert factors.measure(generate_world(session(), 2)) == m                                  # deterministic


def test_the_map_descriptors_are_those_of_the_value_map():
    p = session()
    assert factors.map_descriptors(p) == pytest.approx(synthetic.DEFAULT_MAP.descriptors())


def test_the_travel_time_settings_give_the_target_walk_exactly_and_refuse_a_gap_narrower_than_the_ramp():
    p = session()
    radius = factors.travel_time_settings(p, 8.0)["tile_radius"]
    assert factors.measure(generate_world(session(tile_radius=radius), 1))["travel_time"] == pytest.approx(8.0, abs=1e-9)
    with pytest.raises(ValueError, match="ramp"):
        factors.travel_time_settings(p, 0.5 * p.tile_ramp_width / p.player_move_speed)


def test_the_diversity_settings_give_the_target_within_patch_sd_on_average_and_refuse_what_the_map_cannot_give():
    p = session()
    settings = factors.diversity_settings(p, 0.5)
    assert settings["tile_value_mode"] == "random" and settings["tile_within_mode"] == "scatter"
    got = np.mean([factors.measure(generate_world(session(**settings), s))["diversity"] for s in range(6)])
    assert got == pytest.approx(0.5, rel=0.08)
    with pytest.raises(ValueError, match="outside"):
        factors.diversity_settings(p, 5.0)


def test_under_the_default_modes_the_diversity_is_the_maps_own_and_the_spread_is_not_a_knob():
    assert measured(tile_spread=0.05)["diversity"] == measured(tile_spread=0.3)["diversity"]


def test_calibrate_merges_the_targets_and_fields_gives_the_serialized_names():
    p = session()
    settings = factors.calibrate(p, travel_time=6.0, diversity=0.4)
    assert set(settings) == {"tile_radius", "tile_value_mode", "tile_within_mode", "tile_spread"} and factors.calibrate(p) == {}
    assert factors.fields({"tile_radius": 1.0, "tile_spread": 0.2}) == {"tileRadius": 1.0, "tileSpread": 0.2}


def test_check_reports_the_factors_and_the_points_of_a_session_on_fresh_worlds():
    from world import load_session
    p = load_session("FIX_T0")
    out = factors.check("FIX_T0", synthetic.DEFAULT_MAP, {"tile_radius": 70.0}, range(3), session_duration=30.0)
    assert out["factors"]["travel_time"][0] == pytest.approx((math.sqrt(3.0) * 70.0 - 2.0 * p.tile_cluster_radius) / p.player_move_speed)
    assert set(out["points"]) == {"nearest", "oracle"} and out["points"]["oracle"][0] >= out["points"]["nearest"][0] > 0


def test_the_anchor_is_a_rate_so_a_longer_session_has_proportionally_more_points():
    assert factors.anchor_points(120.0) == pytest.approx(750.0) and factors.anchor_points(180.0) == pytest.approx(1.5 * factors.anchor_points(120.0))
