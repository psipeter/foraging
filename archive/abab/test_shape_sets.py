"""The alternative shape sets: one canopy dimension varies, the other is fixed, and the fruit radius follows the varying one."""

import numpy as np

import shape_sets
import world


def test_a_session_where_the_shape_is_fixed_gets_the_sets_smallest_bush():
    for name, expected in (("height_only", (3.0, 3.0)), ("width_only", (2.5, 4.0))):
        s = shape_sets.SETS[name]
        w, h = shape_sets.canopy_size(s, s["shapeWhenFixed"])
        assert (float(w), float(h)) == expected


def test_height_only_fixes_the_width_and_the_fruit_follows_the_height():
    s = shape_sets.SETS["height_only"]
    shape = np.array([0.0, 0.5, 1.0])
    width, height = shape_sets.canopy_size(s, shape)
    assert np.allclose(width, 3.0) and np.allclose(height, [3.0, 11.5, 20.0])
    assert np.allclose(shape_sets.fruit_radius(s, shape), [0.49, 0.70, 0.91])


def test_width_only_fixes_the_height_and_the_fruit_follows_the_width():
    s = shape_sets.SETS["width_only"]
    shape = np.array([0.0, 0.5, 1.0])
    width, height = shape_sets.canopy_size(s, shape)
    assert np.allclose(height, 4.0) and np.allclose(width, [8.0, 5.25, 2.5])       # the assets' convention: width falls as the shape rises
    assert np.allclose(shape_sets.fruit_radius(s, shape), [0.91, 0.70, 0.49])


def test_fruit_radius_is_linear_in_the_dimension_and_unchanged_when_nothing_is_followed():
    s = dict(shape_sets.SETS["height_only"])
    width, height = shape_sets.canopy_size(s, np.linspace(0, 1, 11))
    radius = shape_sets.fruit_radius(s, np.linspace(0, 1, 11))
    assert np.allclose(np.polyfit(height, radius, 1)[0] * 4.0, 0.7 * 0.3 * 4.0 / 8.5)   # slope: base * 0.3 / half range
    s["fruitSizeFollows"] = "Nothing"
    assert np.allclose(shape_sets.fruit_radius(s, np.linspace(0, 1, 11)), 0.7)


def test_generated_canopy_radius_matches_each_set():
    for name, s in shape_sets.SETS.items():
        params = world.load_session("S1", shape_varies=True, canopy_width_range=s["canopyWidthRange"], canopy_height_range=s["canopyHeightRange"])
        w = world.generate_world(params, 1)
        width, _ = shape_sets.canopy_size(s, w.shape, params.shape_range)
        assert np.allclose(w.canopy_radius, width / 2)                            # world.py's radius is the one the game renders
        if name == "height_only":
            assert np.allclose(w.canopy_radius, 1.5)                              # a constant radius: spacing and harvest range do not depend on the shape


def test_unity_commands_set_every_field():
    lines = shape_sets.unity_commands("width_only", "Assets/x.asset")
    assert len(lines) == 7 and all("Assets/x.asset" in line for line in lines)
    assert any('"x": 2.5, "y": 8.0' in line for line in lines) and any("fruitSizeFollows" in line and "Width" in line for line in lines)
