"""The sessions S3, S4 and S5 as they were before the new ladder (2026-11-05), for the generator tests.

The old S3 (moisture and one other feature paid, terraced terrain), S4 (all three features additive, one inverted) and S5 (one Gaussian bump over shape and
colour plus linear moisture) exercised parts of the generators (moisture as a reward feature, terraces, extrapolation trials, bumps) that the new sessions do
not. Their asset files are kept in `fixtures/` (copied from git, commit d6f3576); `legacy(name)` returns the fields that make S2 behave like them, as overrides for
`load_session`, `generate_world` and `generate_interlude`.
"""

from pathlib import Path

from world import load_session

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIELDS = ("reward_function", "world_seed", "moisture_terrace_levels", "moisture_terrace_sharpness", "moisture_terrace_residual", "terrain_noise_frequency",
          "terrain_max_elevation", "interlude_min_elevation_difference", "shape_varies", "color_varies", "random_bush_value_range")


def legacy(name):
    """Overrides that make the S2 template behave like the old session `name` ("S3", "S4" or "S5")."""
    old = load_session(str(FIXTURES / f"legacy_{name}.asset"))
    return {**{f: getattr(old, f) for f in FIELDS}, "spatial_balance": 0}      # (the old sessions drew every bush independently; the ladder's assets balance')
