"""A feature that does not vary, and moisture as decoration (it pays nothing; out of what the simulated agents sense)."""

import numpy as np

import synthetic
import world
from world import generate_world
from world import load_session as _load_session


def load_session(name=synthetic.TEMPLATE, **overrides):
    """A session of a stated plain configuration (shape and colour vary, the wide corner Gaussian pays) on the template asset, unless overridden; the tests are about the flags,
    not about a shipped session."""
    return _load_session(name, **{**synthetic.overrides(synthetic.FEATURES), **overrides})


def test_old_assets_get_the_new_fields_by_default(tmp_path):
    text = world.session_asset_path(synthetic.TEMPLATE).read_text()
    old = "\n".join(line for line in text.split("\n") if not line.strip().startswith(("shapeVaries", "colorVaries", "shapeWhenFixed", "colorWhenFixed")))
    path = tmp_path / "Old.asset"                              # an asset file saved before the fields existed
    path.write_text(old)
    p = _load_session(str(path))
    assert p.shape_varies is True and p.color_varies is True and p.shape_when_fixed == 0.5


def test_a_feature_that_does_not_vary_is_constant_and_nothing_else_moves():
    base = generate_world(load_session(), 1)
    flat = generate_world(load_session(shape_varies=False, color_varies=False), 1)
    assert np.all(flat.shape == 0.5) and np.all(flat.color == 0.5)
    assert np.array_equal(base.pos, flat.pos) and np.array_equal(base.moisture, flat.moisture)         # the other streams did not move
    assert np.allclose(flat.canopy_radius, flat.canopy_radius[0])                                    # identical canopies
    only_color = generate_world(load_session(shape_varies=False), 1)
    assert np.array_equal(only_color.color, base.color)                                              # the colour draws are the same ones


def test_check_values_carry_the_new_fields_only_when_they_differ_from_the_default():
    default = world.check_values(load_session())
    assert not any(k in default for k in ("shapeVaries", "colorVaries"))   # old world files stay identical
    v = world.check_values(load_session(shape_varies=False))
    assert v["shapeVaries"] == 0.0 and "colorVaries" not in v


def test_a_flat_moisture_gives_a_flat_valley_and_leaves_the_other_worlds_alone():
    flat = generate_world(load_session(moisture_varies=False, moisture_when_fixed=0.3), 5)
    assert set(flat.moisture) == {0.3}
    assert np.allclose(flat.terrain.elevation(np.array([-100.0, 0.0, 80.0]), np.array([30.0, -60.0, 10.0])), (1 - 0.3) * flat.params.terrain_max_elevation)
    varied = generate_world(load_session(), 5)
    assert varied.moisture.std() > 0.05 and world.check_values(load_session()).keys() == world.check_values(load_session(moisture_varies=True)).keys()
    assert world.check_values(load_session(moisture_varies=False))["moistureVaries"] == 0.0
