"""The FN design (scripts/design/FN.py) and the assets and generated files built from it."""

import re
import json

import numpy as np
import pytest

from design import FN
import ranking
from interlude import generate_interlude, sidecar_path
from ranking import generate_ranking
from world import check_values, export_unity, generate_world, load_session, session_features, unity_world_path


def _of(kind, v=None, r=None):
    return [i for i in FN.instances() if i.design["kind"] == kind and (v is None or i.design["n_visible"] == v) and (r is None or i.design["n_rewarded"] == r)]


def test_the_cells_the_iterations_and_the_order():
    inst = FN.instances()
    n = FN.ITERATIONS * len(FN.BASELINE_CELLS) + len(FN.WEIGHT_RATIOS)
    assert [i.name for i in inst] == [f"FN_S{k}" for k in range(1, n + 1)]
    for v, r in FN.BASELINE_CELLS:
        assert len(_of("baseline", v, r)) == FN.ITERATIONS and r <= v
    assert len(_of("weighted")) == len(FN.WEIGHT_RATIOS)
    first = [(i.design["n_visible"], i.design["n_rewarded"]) for i in inst[:len(FN.BASELINE_CELLS) + 1]]
    assert first == list(FN.BASELINE_CELLS) + [(3, 3)]                                               # one pass: row 1, row 2, then a weighted session
    assert [i.design["iteration"] for i in inst[:6]] == [1] * 6
    rest = [(i.design["n_visible"], i.design["n_rewarded"]) for i in inst[6:]]
    assert rest != sorted(rest)                                                                      # the remainder is shuffled


def test_baselines_are_counterbalanced_over_the_features():
    for v, r in FN.BASELINE_CELLS:
        cell = _of("baseline", v, r)
        for i in cell:
            w = i.design["weights"]
            assert len(w) == r and set(w) <= set(i.design["visible"]) and all(x == pytest.approx(1.0 / r, abs=1e-4) for x in w.values())
            assert i.design["hint"] == ("two" if r == 2 else "named")
        if r == 1:
            assert sorted(next(iter(i.design["weights"])) for i in cell) == sorted(FN.FEATURES)       # each feature pays once
        elif v == 3:
            assert sorted(next(f for f in FN.FEATURES if f not in i.design["weights"]) for i in cell) == sorted(FN.FEATURES)   # each is the idle one once
        if v == 2:
            assert len({tuple(i.design["visible"]) for i in cell}) == FN.ITERATIONS                  # each visible pair once


def test_durations_grow_with_rows_and_columns():
    for i in FN.instances():
        d = i.design
        assert i.session_fields["sessionDuration"] == FN.seconds(d["n_visible"], d["n_rewarded"]) == FN.BASE_SECONDS + FN.VISIBLE_STEP_SECONDS * (d["n_visible"] - 1) + FN.REWARDED_STEP_SECONDS * (d["n_rewarded"] - 1)
    assert {i.session_fields["sessionDuration"] for i in _of("baseline", 1, 1)} == {FN.BASE_SECONDS}


def test_weighted_sessions_have_weights_summing_to_one_over_the_ratio_family_in_a_random_order():
    weighted = _of("weighted")
    ratios = [i.design["ratio"] for i in weighted]
    assert sorted(ratios) == sorted(FN.WEIGHT_RATIOS) and ratios != sorted(ratios, reverse=True)       # all of them, not in the listed order
    for i in weighted:
        w = i.design["weights"]
        assert sum(w.values()) == pytest.approx(1.0, abs=2e-4) and set(w) == set(FN.FEATURES) and i.design["hint"] == "weighted"
        ranked = sorted(w.values(), reverse=True)
        assert ranked[1] / ranked[0] == pytest.approx(i.design["ratio"], abs=1e-3) and ranked[2] / ranked[0] == pytest.approx(i.design["ratio"] ** 2, abs=1e-3)
        assert i.design["noise_units"] == {f: pytest.approx(FN.REWARD_SCALE * x / FN.REWARD_STD, abs=2e-3) for f, x in w.items()}


def test_the_draws_do_not_change_from_build_to_build():
    assert [i.design for i in FN.instances()] == [i.design for i in FN.instances()]


def test_the_assets_say_what_the_design_says():
    for i in FN.instances():
        p = load_session(i.name)
        feats = session_features(p)
        assert {f: d["visible"] for f, d in feats.items()} == {f: f in i.design["visible"] for f in FN.FEATURES}
        assert {f for f, d in feats.items() if d["rewarded"]} == {f for f, w in i.design["weights"].items() if w > 0}
        for f in FN.FEATURES:
            comp = p.reward_function[f"{f}Component"]
            assert comp["weight"] == pytest.approx(FN.REWARD_SCALE * i.design["weights"].get(f, 0.0), abs=5e-4)
            assert comp["basisFunctionType"] == i.design["direction"][f] and not p.reward_function.get("bumps") and not p.reward_function.get("products")
        assert int(p.spatial_balance) == 0 and int(p.feature_balance) == 2 and int(p.moisture_terrace_mode) == FN.TERRACE["moistureTerraceMode"] and float(p.terrain_noise_frequency) == FN.TERRACE["terrainNoiseFrequency"] and int(p.terrace_diffusion_iterations) == 500 and float(p.terrace_diffusion_edge) == 0.1 and float(p.reward_std) == FN.REWARD_STD
        assert json.loads(p.design_json)["instance"] == i.name
        interlude = load_session(i.name.replace("_S", "_I"))
        assert interlude.is_interlude and interlude.interlude_for == i.name and interlude.reward_function == p.reward_function
        assert check_values(interlude) == check_values(p) and int(interlude.world_seed) == int(p.world_seed)


def test_a_session_with_hidden_features_has_identical_bushes_and_a_flat_valley_where_moisture_is_hidden():
    first, second = (generate_world(load_session(n), 301 + k) for k, n in enumerate(("FN_S1", "FN_S2")))
    for w, visible in ((first, FN.instances()[0].design["visible"]), (second, FN.instances()[1].design["visible"])):
        assert (len(set(w.shape)) > 1) == ("shape" in visible) and (len(set(w.color)) > 1) == ("color" in visible)
        assert (len(set(w.moisture)) > 1) == ("moisture" in visible)    # a flat valley unless moisture is visible


@pytest.mark.slow
def test_committed_fn_files_are_fresh(tmp_path):
    for i in FN.instances():
        p = load_session(i.name)
        seed = int(p.world_seed)
        committed = unity_world_path(i.name, seed)
        assert committed.exists(), f"{committed} is missing: run scripts/build_experiment.py FN"
        export_unity(generate_world(p, seed), tmp_path / committed.name)
        assert (tmp_path / committed.name).read_bytes() == committed.read_bytes(), f"{committed.name} is stale: re-run scripts/build_experiment.py FN"
        name = i.name.replace("_S", "_I")
        ranked = int(i.interlude_fields.get("interludeFormat", 0)) == 1
        sidecar = (generate_ranking if ranked else generate_interlude)(name)[0]
        on_disk = json.load(open(ranking.sidecar_path(name, sidecar["seed"]) if ranked else sidecar_path(name, sidecar["seed"])))
        assert on_disk == json.loads(json.dumps(sidecar)), f"{name} Interlude file is stale: re-run scripts/build_experiment.py FN"


def test_baseline_hints_name_the_visible_features_and_the_weighted_hint_is_shared():
    texts = FN.texts()
    for k, i in enumerate(FN.instances(), start=1):
        if i.design["kind"] != "baseline":
            continue
        hint = texts[f"instructions_S{k}.txt"].replace("**", "")
        if i.design["n_rewarded"] == 2 and i.design["n_visible"] == 3:
            assert "Two of the three features" in hint
        else:
            assert all(FN.NAMES[f] in hint for f in i.design["visible"]) and all(FN.NAMES[f] not in hint for f in FN.FEATURES if f not in i.design["visible"])
    weighted = _of("weighted")
    assert {i.design["hint"] for i in weighted} == {"weighted"} and len({i.session_fields["instructionsFile"] for i in weighted}) == 1


def test_the_hints_mark_their_essential_words_in_bold():
    """Every baseline hint bolds its quantifier and the features it names ("three features" in the two-of-three hint); the weighted hint bolds "All three features";
    the Interlude text has no emphasis. The markers are balanced."""
    texts = FN.texts()
    for k, i in enumerate(FN.instances(), start=1):
        if i.design["kind"] != "baseline":
            continue
        raw = texts[f"instructions_S{k}.txt"]
        assert raw.count("**") % 2 == 0
        bold = re.findall(r"\*\*(.+?)\*\*", raw)
        assert bold[0] in ("Both", "Either", "One", "Two") or bold[0] in FN.NAMES.values()
        if i.design["n_visible"] < 3 or i.design["n_rewarded"] == 1:
            assert all(FN.NAMES[f] in bold for f in i.design["visible"])
    assert re.findall(r"\*\*(.+?)\*\*", FN.HINT_WEIGHTED) == ["All three features"]
    assert "**" not in texts["instructions_interlude.txt"]
