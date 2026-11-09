import json
from types import SimpleNamespace

import pytest

from build_experiment import build_spec, load_design
from design import Instance


def fake_design(**extra):
    instances = [
        Instance("ZZ_S1", {"worldSeed": 7, "rewardFunction.bumps.Array.size": 0}, {"sessionDuration": 60, "instructionsFile": "Experiments/ZZ/a.txt"},
                 {"interludeTrialCount": 10}, {"cell": "A", "hint": True}),
        Instance("ZZ_S2", {"worldSeed": 8}, {"sessionDuration": 90}, None, {"cell": "B"}),
    ]
    return SimpleNamespace(CODE="ZZ", TITLE="Test", TEMPLATE_SESSION="TUT_S1", TEMPLATE_INTERLUDE="TUT_I1", instances=lambda: instances, **extra)


def by_name(spec):
    return {s["name"]: {f["p"]: f["v"] for f in s["fields"]} for s in spec["sessions"]}


def test_a_spec_lists_each_session_followed_by_its_interlude_in_play_order():
    spec = build_spec(fake_design())
    assert [s["name"] for s in spec["sessions"]] == ["ZZ_S1", "ZZ_I1", "ZZ_S2"]      # S2 has no Interlude
    assert spec["code"] == "ZZ" and spec["title"] == "Test" and spec["requires"] == [] and spec["countsTowardTotal"] and not spec["removeStale"]
    assert spec["sessions"][0]["template"].endswith("TUT/TUT_S1.asset") and spec["sessions"][1]["template"].endswith("TUT/TUT_I1.asset")


def test_world_fields_go_to_both_assets_and_session_only_fields_to_the_session():
    fields = by_name(build_spec(fake_design()))
    assert fields["ZZ_S1"]["worldSeed"] == fields["ZZ_I1"]["worldSeed"] == "7"                       # an Interlude copies its session's world
    assert fields["ZZ_S1"]["sessionDuration"] == "60" and "sessionDuration" not in fields["ZZ_I1"]
    assert fields["ZZ_I1"]["isInterlude"] == "true" and fields["ZZ_I1"]["interludeFor"] == "ZZ_S1" and fields["ZZ_I1"]["interludeTrialCount"] == "10"
    assert "isInterlude" not in fields["ZZ_S1"]


def test_the_design_is_stored_as_json_with_the_instance_name():
    fields = by_name(build_spec(fake_design()))
    assert json.loads(fields["ZZ_S1"]["designJson"]) == {"cell": "A", "hint": True, "instance": "ZZ_S1"}
    assert json.loads(fields["ZZ_S2"]["designJson"])["cell"] == "B"


def test_array_sizes_come_before_their_items_and_values_are_text():
    spec = build_spec(fake_design())
    paths = [f["p"] for f in spec["sessions"][0]["fields"]]
    assert paths.index("rewardFunction.bumps.Array.size") < paths.index("designJson")
    assert all(isinstance(f["v"], str) for s in spec["sessions"] for f in s["fields"])


def test_remove_stale_and_experiment_options_pass_through():
    spec = build_spec(fake_design(REQUIRES=("TUT",), COUNTS_TOWARD_TOTAL=False), remove_stale=True)
    assert spec["removeStale"] and spec["requires"] == ["TUT"] and not spec["countsTowardTotal"]


def test_a_design_module_must_declare_the_code_it_is_named_for(tmp_path, monkeypatch):
    import design
    (tmp_path / "ZY.py").write_text("CODE = 'ZZ'\n")
    monkeypatch.setattr(design, "__path__", [str(tmp_path)] + list(design.__path__))
    with pytest.raises(ValueError):
        load_design("ZY")
