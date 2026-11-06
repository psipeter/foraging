"""Optional alternative shape sets: the canopy varies in one dimension (height or width) and the fruit radius follows it.

    ./venv/bin/python scripts/shape_sets.py                                  # list the sets and the sizes they give
    ./venv/bin/python scripts/shape_sets.py height_only Assets/ScriptableObjects/SessionConfig/S1.asset   # CLI commands that apply one

The shared shape axis (the sessions' current one) scales the canopy's width down while its height goes up (`canopyWidthRange`,
`canopyHeightRange` on the assets, `fruitSizeFollows` Nothing). A set here fixes one dimension and varies the other, so two sessions
can alternate between them (docs/DECISIONS.md, "Height-only and width-only shape sets"). Only SessionConfig fields differ, so the
generators need no change: `world.py` takes the canopy radius from `canopyWidthRange` (a collapsed range gives a constant radius),
and `fruitSizeFollows` / `fruitSizeSlope` act on the rendered fruit only (Tree.cs, SessionConfig.FruitRadiusFor).
Both sets use the **capsule** canopy form (`canopyForm`, `canopyEdgeRadius` 1.5): a half-buried cylinder with a rounded top edge of a constant radius, so the
crown looks the same at every height or width (a stretched ellipsoid sharpens its crown as it gets taller, which reads as a change of shape, not of size). For
height-only (width 3) the top is a hemisphere on a cylinder that gets longer; for width-only (height 4) a flat top of growing radius with the same rounded edge.
`visibility.py` and `perception.py` still model every canopy as an ellipsoid, so their occlusion of these bushes is approximate.
The attribute-to-size direction is the assets' convention (width falls and height rises as the shape value rises); which end pays
more comes from the reward function, not from here.
"""

import argparse
import json

import numpy as np

# set name: SessionConfig fields. Sizes are world units; the canopy is a half-buried capsule (or ellipsoid), so its visible height is half the height.
# `shapeWhenFixed` is the shape value of every bush in a session where the shape does not vary: the set's smallest bush (3 x 3 and 2.5 x 4), not the middle of the range.
SETS = {
    "height_only": {"canopyWidthRange": (3.0, 3.0), "canopyHeightRange": (3.0, 20.0), "fruitSizeFollows": "Height", "fruitSizeSlope": 0.3, "shapeWhenFixed": 0.0,
                    "canopyForm": "Capsule", "canopyEdgeRadius": 1.5},
    "width_only": {"canopyWidthRange": (2.5, 8.0), "canopyHeightRange": (4.0, 4.0), "fruitSizeFollows": "Width", "fruitSizeSlope": 0.3, "shapeWhenFixed": 1.0,
                  "canopyForm": "Capsule", "canopyEdgeRadius": 1.5},
}


def canopy_size(shape_set, shape, shape_range=(0.0, 1.0)):
    """(width, height) of the canopy at a shape value (mirrors Tree.ApplyAttributes: width runs from the range's y to its x, height from x to y)."""
    t = np.clip((np.asarray(shape, float) - shape_range[0]) / (shape_range[1] - shape_range[0]), 0.0, 1.0)
    (wx, wy), (hx, hy) = shape_set["canopyWidthRange"], shape_set["canopyHeightRange"]
    return wy + (wx - wy) * t, hx + (hy - hx) * t


def fruit_radius(shape_set, shape, base=0.7, shape_range=(0.0, 1.0)):
    """The fruit radius at a shape value (mirrors SessionConfig.FruitRadiusFor): linear in the followed dimension, `slope` of `base` per half range."""
    follows = shape_set["fruitSizeFollows"]
    if follows == "Nothing":
        return np.full_like(np.asarray(shape, float), base)
    width, height = canopy_size(shape_set, shape, shape_range)
    rng = shape_set["canopyHeightRange"] if follows == "Height" else shape_set["canopyWidthRange"]
    half = abs(rng[1] - rng[0]) / 2
    if half < 1e-4:
        return np.full_like(np.asarray(shape, float), base)
    size = height if follows == "Height" else width
    return base * (1 + shape_set["fruitSizeSlope"] * (size - (rng[0] + rng[1]) / 2) / half)


def unity_commands(name, asset):
    """`unity command set_serialized_field` lines that set a set's fields on an asset (the session's world is unaffected for height_only,
    but `world.py` must be re-run for width_only since the canopy radius follows the width range)."""
    lines = []
    for field, value in SETS[name].items():
        if isinstance(value, tuple):
            value = json.dumps({"x": value[0], "y": value[1]})
        lines.append(f"unity command set_serialized_field --target {asset} --field {field} --value '{value}'")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("name", nargs="?", choices=sorted(SETS))
    parser.add_argument("asset", nargs="?")
    args = parser.parse_args()
    if args.name and args.asset:
        print("\n".join(unity_commands(args.name, args.asset)))
        return
    for name, s in SETS.items():
        print(name)
        for v in (0.0, 0.5, 1.0):
            w, h = canopy_size(s, v)
            print(f"  shape {v:.1f}: width {w:.1f}, height {h:.1f}, fruit radius {float(fruit_radius(s, v)):.2f}")


if __name__ == "__main__":
    main()
