"""build_sessions.py: the CLI calls that make the variant assets (pure; no Unity needed)."""

import build_sessions as b


def test_plan_makes_both_variants_of_a_session_and_its_interlude():
    calls = b.plan(["S1"])
    copies = [c for c in calls if c[0] == "copy_asset"]
    assert [(c[2], c[4]) for c in copies] == [
        ("Assets/ScriptableObjects/SessionConfig/S1.asset", "Assets/ScriptableObjects/SessionConfig/S1_A.asset"),
        ("Assets/ScriptableObjects/SessionConfig/S1_Interlude.asset", "Assets/ScriptableObjects/SessionConfig/S1_A_Interlude.asset"),
        ("Assets/ScriptableObjects/SessionConfig/S1.asset", "Assets/ScriptableObjects/SessionConfig/S1_B.asset"),
        ("Assets/ScriptableObjects/SessionConfig/S1_Interlude.asset", "Assets/ScriptableObjects/SessionConfig/S1_B_Interlude.asset")]


def test_every_asset_gets_the_set_fields_and_interludes_point_at_their_variant():
    calls = b.plan(["S1"])
    sets = {(c[2], c[4]): c[6] for c in calls if c[0] == "set_serialized_field"}
    for dest in ("S1_A", "S1_B", "S1_A_Interlude", "S1_B_Interlude"):
        target = f"Assets/ScriptableObjects/SessionConfig/{dest}.asset"
        assert all((target, f) in sets for f in ("fruitColorRamp", "canopyWidthRange", "canopyHeightRange", "fruitSizeFollows", "fruitSizeSlope"))
    assert sets[("Assets/ScriptableObjects/SessionConfig/S1_B_Interlude.asset", "interludeFor")] == "S1_B"
    assert ("Assets/ScriptableObjects/SessionConfig/S1_A.asset", "interludeFor") not in sets


def test_existing_variants_are_not_copied_again_and_a_session_without_interlude_makes_two_assets():
    calls = b.plan(["P"], exists=lambda path: path.endswith("P_A.asset"), has_interlude=lambda base: False)
    assert [c[4] for c in calls if c[0] == "copy_asset"] == ["Assets/ScriptableObjects/SessionConfig/P_B.asset"]
    assert {c[2] for c in calls if c[0] == "set_serialized_field"} == {"Assets/ScriptableObjects/SessionConfig/P_A.asset", "Assets/ScriptableObjects/SessionConfig/P_B.asset"}


def test_wiring_fills_the_default_list_and_both_sequences_in_play_order():
    w = b.wiring(["P", "S1"])
    assert w["sessionConfigs"] == ["P", "P_Interlude", "S1", "S1_Interlude"]
    assert w["sequenceA"][2] == "S1_B" and w["sequenceB"][2] == "S1_A"
    calls = b.list_calls("sequenceA", w["sequenceA"])
    assert calls[0][2] == b.ABAB_ASSET and calls[0][-3:] == ["--field", "sequenceA.Array.size", "--value", "4"][-3:] and len(calls) == 5     # the generated Resources asset
    assert calls[3][-1] == '{"path": "Assets/ScriptableObjects/SessionConfig/S1_B.asset"}'
    assert "hierarchyPath" in b.list_calls("sessionConfigs", w["sessionConfigs"])[0][2]                                                   # the default list: the scene
