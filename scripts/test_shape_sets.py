"""The alternative shape sets: one canopy dimension varies, the other is fixed, and the fruit radius follows the varying one."""

import numpy as np

import shape_sets
import world


def test_height_only_fixes_the_width_and_the_fruit_follows_the_height():
    s = shape_sets.SETS["height_only"]
    shape = np.array([0.0, 0.5, 1.0])
    width, height = shape_sets.canopy_size(s, shape)
    assert np.allclose(width, 4.0) and np.allclose(height, [4.0, 9.5, 15.0])
    assert np.allclose(shape_sets.fruit_radius(s, shape), [0.49, 0.70, 0.91])


def test_width_only_fixes_the_height_and_the_fruit_follows_the_width():
    s = shape_sets.SETS["width_only"]
    shape = np.array([0.0, 0.5, 1.0])
    width, height = shape_sets.canopy_size(s, shape)
    assert np.allclose(height, 4.0) and np.allclose(width, [12.0, 8.0, 4.0])       # the assets' convention: width falls as the shape rises
    assert np.allclose(shape_sets.fruit_radius(s, shape), [0.91, 0.70, 0.49])


def test_fruit_radius_is_linear_in_the_dimension_and_unchanged_when_nothing_is_followed():
    s = dict(shape_sets.SETS["height_only"])
    width, height = shape_sets.canopy_size(s, np.linspace(0, 1, 11))
    radius = shape_sets.fruit_radius(s, np.linspace(0, 1, 11))
    assert np.allclose(np.polyfit(height, radius, 1)[0] * 4.0, 0.7 * 0.3 * 4.0 / 5.5)   # slope: base * 0.3 / half range
    s["fruitSizeFollows"] = "Nothing"
    assert np.allclose(shape_sets.fruit_radius(s, np.linspace(0, 1, 11)), 0.7)


def test_generated_canopy_radius_matches_each_set():
    for name, s in shape_sets.SETS.items():
        params = world.load_session("S1", canopy_width_range=s["canopyWidthRange"], canopy_height_range=s["canopyHeightRange"])
        w = world.generate_world(params, 1)
        width, _ = shape_sets.canopy_size(s, w.shape, params.shape_range)
        assert np.allclose(w.canopy_radius, width / 2)                            # world.py's radius is the one the game renders
        if name == "height_only":
            assert np.allclose(w.canopy_radius, 2.0)                              # a constant radius: spacing and harvest range do not depend on the shape


def test_unity_commands_set_every_field():
    lines = shape_sets.unity_commands("width_only", "Assets/x.asset")
    assert len(lines) == 4 and all("Assets/x.asset" in line for line in lines)
    assert any('"x": 4.0, "y": 12.0' in line for line in lines) and any("fruitSizeFollows" in line and "Width" in line for line in lines)
