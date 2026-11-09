"""Sessions built from a stated configuration, for tests that ask whether what a design intends is what the generators produce.

A test names the configuration (which features are visible, what each pays and in which direction, the noise) and gets the `load_session` overrides
or the session itself, built on a template asset (`TUT_S1`, the one session of a built experiment that does not go away) with every other field made
neutral: no random per-bush value, independent attributes, continuous terrain. Nothing here is a particular shipped session, so a test written with it
keeps working when sessions are added, changed or removed.
"""

from world import FEATURES, load_session

TEMPLATE = "TUT_S1"
REWARD_SCALE = 4.0        # the best bush pays about this much when the weights sum to one, as in every built experiment


def reward_function(weights, direction=None, scale=REWARD_SCALE):
    """A linear reward over the three features: `weights` {feature: share} (absent = 0), `direction` {feature: 0 (higher pays) or 1 (lower pays)}."""
    direction = direction or {}
    zero = {"basisFunctionType": 0, "weight": 0.0, "peak": 0.0, "width": 0.0}
    rf = {f"{f}Component": {**zero, "basisFunctionType": int(direction.get(f, 0)), "weight": scale * float(weights.get(f, 0.0))} for f in FEATURES}
    return {**rf, "bumps": [], "products": []}


def overrides(visible=FEATURES, weights=None, direction=None, std=0.6, scale=REWARD_SCALE, **extra):
    """`load_session` overrides for a session in which `visible` features vary and `weights` pay (default: the first visible feature pays everything)."""
    visible = tuple(visible)
    weights = {visible[0]: 1.0} if weights is None else weights
    if not set(weights) <= set(visible):
        raise ValueError("a feature that pays must be visible")
    return {"reward_function": reward_function(weights, direction, scale), "reward_std": std, "shape_varies": "shape" in visible, "color_varies": "color" in visible,
            "moisture_varies": "moisture" in visible, "moisture_is_feature": "moisture" in visible, "random_bush_value_range": (0.0, 0.0), "spatial_balance": 0,
            "moisture_terrace_levels": 0, "is_practice": False, **extra}


def session(visible=FEATURES, weights=None, direction=None, base=TEMPLATE, **extra):
    return load_session(base, **overrides(visible, weights, direction, **extra))
