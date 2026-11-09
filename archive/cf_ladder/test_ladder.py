"""The session ladder table: every session sets the same fields, the features that vary are the ones the design says, and the reward is what the design says."""

import numpy as np

import ladder
import world
from world import generate_world, load_session


def test_every_session_sets_the_same_fields_and_its_interlude_gets_them_too():
    keys = {frozenset(k for k in v if ".Array.data[" not in k) for v in ladder.LADDER.values()}      # (the items of a bump or product list differ)
    assert len(keys) == 1
    calls = ladder.calls("CF_S1")
    assert {c[2] for c in calls} == {"Assets/ScriptableObjects/Experiments/CF/CF_S1.asset", "Assets/ScriptableObjects/Experiments/CF/CF_I1.asset"}


def overrides(name):
    """The ladder's fields as load_session overrides (snake_case params) on top of a real asset."""
    values = ladder.LADDER[world.canonical(name)]
    rf = load_session("S1").reward_function
    rf = {k: (dict(v) if isinstance(v, dict) else v) for k, v in rf.items()}
    rf["bumps"], rf["products"] = [], []
    for key, value in values.items():
        if not key.startswith("rewardFunction."):
            continue
        parts = key.split(".")
        if parts[1] in ("bumps", "products"):
            if parts[2] == "Array" and parts[3] == "size":
                continue
            index = int(parts[3].split("[")[1].rstrip("]"))
            while len(rf[parts[1]]) <= index:
                rf[parts[1]].append({})
            rf[parts[1]][index][parts[4]] = value
        else:
            rf[parts[1]][parts[2]] = value
    out = {"world_seed": values["worldSeed"], "shape_varies": values["shapeVaries"], "color_varies": values["colorVaries"],
           "random_bush_value_range": (values["randomBushValueRange"]["x"], values["randomBushValueRange"]["y"]), "reward_function": rf}
    return out


def test_practice_reward_is_random_s1_depends_on_colour_only_and_s2_peaks_on_shape():
    p = generate_world(load_session("S1", **overrides("P")), 200)
    assert abs(np.corrcoef(p.value, p.color)[0, 1]) < 0.15 and abs(np.corrcoef(p.value, p.shape)[0, 1]) < 0.15 and p.value.std() > 0.8
    s1 = generate_world(load_session("S1", **overrides("S1")), 201)
    assert np.all(s1.shape == 0.5) and np.allclose(s1.value, 4.0 * s1.color)                         # linear in colour, identical canopies
    s2 = generate_world(load_session("S1", **overrides("S2")), 202)
    assert np.all(s2.color == 0.5) and abs(s2.value.max() - 4.0) < 0.1                            # a peak that pays about 4
    assert abs(s2.shape[np.argmax(s2.value)] - 0.65) < 0.05 and s2.value[s2.shape < 0.1].max() < 0.5   # off the centre, near zero at the ends


def test_s3_s4_s5_reward_depends_on_what_the_design_says():
    s3 = generate_world(load_session("S2", **overrides("S3")), 203)
    assert np.allclose(s3.value, 4.0 * (1.0 - s3.color))                                                # colour only, reversed linear; shape is a distractor
    s4 = generate_world(load_session("S2", **overrides("S4")), 204)
    assert abs(s4.shape[np.argmax(s4.value)] - 0.30) < 0.05 and abs(np.corrcoef(s4.value, s4.color)[0, 1]) < 0.1   # a shape peak at 0.30
    s5 = generate_world(load_session("S2", **overrides("S5")), 205)
    assert np.allclose(s5.value, 2.4 * s5.shape + 1.6 * (1.0 - s5.color)) and s5.value.max() > 3.7           # a weighted mixture, best bush about 4


def test_session_only_fields_go_to_the_session_asset_and_recreate_copies_the_template():
    calls = {c[2]: [] for c in ladder.calls("CF_S3")}
    for c in ladder.calls("CF_S3"):
        calls[c[2]].append(c[4])
    assert "sessionDuration" in calls["Assets/ScriptableObjects/Experiments/CF/CF_S3.asset"]
    assert "sessionDuration" not in calls["Assets/ScriptableObjects/Experiments/CF/CF_I3.asset"]
    assert "interludeFor" in calls["Assets/ScriptableObjects/Experiments/CF/CF_I3.asset"] and "interludeFor" not in calls["Assets/ScriptableObjects/Experiments/CF/CF_S3.asset"]
    copies = [c for c in ladder.recreate_calls("CF_S3") if c[0] == "copy_asset"]
    assert [(c[2], c[4]) for c in copies] == [("Assets/ScriptableObjects/Experiments/CF/CF_S2.asset", "Assets/ScriptableObjects/Experiments/CF/CF_S3.asset"),
                                              ("Assets/ScriptableObjects/Experiments/CF/CF_I2.asset", "Assets/ScriptableObjects/Experiments/CF/CF_I3.asset")]


def test_s6_is_one_feature_linear_times_a_gaussian_of_the_other_and_s7_an_anisotropic_gaussian():
    s6 = generate_world(load_session("S2", **overrides("S6")), 206)
    expected = 4.0 * s6.shape * np.exp(-((s6.color - 0.6) ** 2) / (2 * 0.25 ** 2))
    assert np.allclose(s6.value, expected) and s6.value.max() > 3.6
    s7 = generate_world(load_session("S2", **overrides("S7")), 207)
    expected = 4.0 * np.exp(-((s7.shape - 0.30) ** 2 / (2 * 0.25 ** 2) + (s7.color - 0.70) ** 2 / (2 * 0.15 ** 2)))
    assert np.allclose(s7.value, expected) and s7.value.max() > 3.6
    assert 0.10 < np.mean(s7.value > 2.0) < 0.25                  # the share of bushes above half the best: a peak that trial and error can find (the old S5 had about 17%)


def test_every_session_has_light_linear_fog_that_starts_before_it_ends():
    for name, values in ladder.LADDER.items():
        assert values["fogEnabled"] is True and 0 < values["fogStartDistance"] < values["fogEndDistance"], name


def test_every_session_has_the_terraced_terrain_and_the_planned_duration():
    for name, values in ladder.LADDER.items():
        assert values["moistureTerraceLevels"] == 4 and values["terrainMaxElevation"] == 6.0, name
    assert {n: ladder.SESSION_ONLY[n]["sessionDuration"] for n in ladder.LADDER} == {"TUT_S1": 30, "CF_S1": 90, "CF_S2": 90, "CF_S3": 120, "CF_S4": 120, "CF_S5": 180, "CF_S6": 180, "CF_S7": 180}
