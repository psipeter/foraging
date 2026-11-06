"""The ABAB feature sets: which set a session uses, what a set changes in an asset, and the participant-ID variant."""

import numpy as np

import feature_sets
import fruit_ramp


def test_sets_alternate_every_session_and_the_practice_differs_from_the_first_session():
    for start in (0, 1):
        letters = [feature_sets.set_for(n, start) for n in range(8)]
        assert letters[0] == feature_sets.LETTERS[start]
        assert all(a != b for a, b in zip(letters, letters[1:]))                  # ABAB...


def test_fields_carry_the_ramp_and_the_shape_set():
    a, b = feature_sets.fields("A"), feature_sets.fields("B")
    assert a["fruitColorRamp"] != b["fruitColorRamp"] and len(a["fruitColorRamp"]) == fruit_ramp.STOPS
    first = fruit_ramp.to_srgb(fruit_ramp.ramp("warm_arc"))[0]
    assert np.allclose([a["fruitColorRamp"][0][k] for k in "rgb"], first, atol=1e-3)
    assert a["canopyWidthRange"] == {"x": 3.0, "y": 3.0} and a["fruitSizeFollows"] == "Height"      # height-only
    assert b["canopyHeightRange"] == {"x": 4.0, "y": 4.0} and b["fruitSizeFollows"] == "Width"      # width-only


def test_variant_for_pid_is_stable_normalised_and_balanced():
    assert feature_sets.variant_for_pid("abc") == feature_sets.variant_for_pid("  ABC ")           # trimmed and lower-cased
    # pinned values (the C# mirror, DesignVariant.cs, is not checked against them by any test)
    assert [feature_sets.variant_for_pid(p) for p in ("", "a", "abc", "5f3c9a1b2d4e6f7081920a3b")] == [0, 0, 1, 0]
    ids = [f"{i:024x}" for i in range(0, 2 ** 40, 2 ** 40 // 2000)]
    share = np.mean([feature_sets.variant_for_pid(i) for i in ids])
    assert 0.45 < share < 0.55


def test_sequences_alternate_the_set_and_the_default_list_is_the_templates():
    bases = ["P", "S1", "S2"]
    assert feature_sets.sequence(bases, 0) == ["P_A", "P_A_Interlude", "S1_B", "S1_B_Interlude", "S2_A", "S2_A_Interlude"]
    assert feature_sets.sequence(bases, 1) == ["P_B", "P_B_Interlude", "S1_A", "S1_A_Interlude", "S2_B", "S2_B_Interlude"]
    assert feature_sets.sequence(["P", "S1"], 0, has_interlude=lambda base: base != "P") == ["P_A", "S1_B", "S1_B_Interlude"]
    assert feature_sets.default_sequence(bases) == ["P", "P_Interlude", "S1", "S1_Interlude", "S2", "S2_Interlude"]
