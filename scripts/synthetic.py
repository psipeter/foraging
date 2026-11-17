"""Sessions built from a stated configuration, for tests that ask whether what a design intends is what the generators produce.

A test names the configuration (which features are visible, the value map that pays, the noise) and gets the `load_session` overrides or the session itself, built on the frozen
tiles session `FIX_T0` (a copy of the FOR session) with every other field neutral: the plain tiles of `TILES` (random arrangement, the default value mode). The reward is a
`value_maps.ValueMap` (default: the additive rung's wide corner Gaussian, shape and colour paying alike). Nothing here is a particular shipped session, so a test written with it
keeps working when sessions are added, changed or removed.
"""

import value_maps
from world import FEATURES, load_session

TEMPLATE = "FIX_T0"
TILES = {"layout": "tiles", "assignment": "tiles", "tile_radius": 70.0, "tile_ramp_width": 14.0, "tile_moisture_levels": 4, "tile_bushes": 9, "tile_cluster_radius": 22.0,
         "tile_cluster_spacing": 12.0, "tile_spread": 0.12, "tile_arrangement": None, "tile_value_mode": None, "tile_within_mode": None, "tile_good_fraction": 0.25,
         "tile_smoothness": 0, "tile_gradient": 0.3, "tile_gradient_angle": -1.0, "tile_coverage_min": 0.0, "tile_start_spread_min": 0.0}       # the tiles, stated (not FIX_T0's own)
DEFAULT_MAP = value_maps.wide_corner()          # the additive rung, both features alike, the best bush pays 4 as in every built experiment


def feature_only(feature, high=True):
    """A value map that depends on one feature only: a Gaussian wide (1000) along the other feature, 0.7 along `feature`, centred on its high (or low) end."""
    centre = 1.0 if high else 0.0
    if feature == "shape":
        bump = value_maps.Bump(centre, 0.5, 0.7, 1000.0, 0.0, 4.0)
    elif feature == "color":
        bump = value_maps.Bump(0.5, centre, 1000.0, 0.7, 0.0, 4.0)
    else:
        raise ValueError(feature)
    return value_maps.ValueMap((bump,))


def overrides(visible=FEATURES, valuemap=DEFAULT_MAP, **extra):
    """`load_session` overrides for a session in which `visible` features vary and `valuemap` pays (default: the wide corner Gaussian, both features alike)."""
    return {**valuemap.compile(), "shape_varies": "shape" in visible, "color_varies": "color" in visible, "moisture_varies": "moisture" in visible, "is_practice": False, **TILES, **extra}


def session(visible=FEATURES, valuemap=DEFAULT_MAP, base=TEMPLATE, **extra):
    return load_session(base, **overrides(visible, valuemap, **extra))
