"""The two alternating feature sets of the ABAB design (set A, set B), one colour set and one shape set each.

    ./venv/bin/python scripts/feature_sets.py                  # list the sets and the sessions' sequence for both start variants
    ./venv/bin/python scripts/feature_sets.py pid <id> ...     # which start variant a participant ID gets

The sessions alternate between the two sets so that what a participant learned about one mapping (a colour, a canopy shape) cannot
carry over into the next session. `colour` sets are the ramps of `fruit_ramp.py` (`warm_arc`, `cool_arc`), `shape` sets those of
`shape_sets.py` (`height_only`, `width_only`). The two channels change together: set A is warm colours with height-only shapes, set B
cool colours with width-only shapes.

A participant's **start variant** (0 or 1) decides the set of the practice session (session 0); session n then uses set
`LETTERS[(start + n) % 2]`, so the first analysed session already looks different from the practice. The variant is a hash of the
participant ID (`variant_for_pid`, mirrored in `Assets/Scripts/Session/DesignVariant.cs`: change both and `test_feature_sets.py`
together), so a participant who returns to an unfinished run gets the same sequence. Which variant a session ran is in its name
(`S1_A`, `S1_B`), not in a data column. `build_sessions.py` builds the per-variant session assets.
"""

import argparse

import fruit_ramp
import shape_sets

LETTERS = ("A", "B")
FEATURE_SETS = {
    "A": {"color": "warm_arc", "shape": "height_only"},
    "B": {"color": "cool_arc", "shape": "width_only"},
}


def set_for(session_number, start):
    """The set letter a session uses: `start` is the participant's start variant (0 or 1), the practice session is number 0."""
    return LETTERS[(start + session_number) % 2]


def variant_name(base, letter):
    """Name of the variant of session asset `base` that uses set `letter` (S1 -> S1_A)."""
    return f"{base}_{letter}"


def interlude_name(base, letter):
    """Name of the Interlude asset of that variant (S1 -> S1_A_Interlude)."""
    return f"{base}_{letter}_Interlude"


def fields(letter):
    """The SessionConfig fields that make a session use set `letter` (field name -> JSON-able value)."""
    chosen = FEATURE_SETS[letter]
    stops = fruit_ramp.to_srgb(fruit_ramp.ramp(chosen["color"]))
    out = {"fruitColorRamp": [{"r": round(float(c[0]), 4), "g": round(float(c[1]), 4), "b": round(float(c[2]), 4), "a": 1} for c in stops]}
    for key, value in shape_sets.SETS[chosen["shape"]].items():
        out[key] = {"x": value[0], "y": value[1]} if isinstance(value, tuple) else value
    return out


def sequence(bases, start, has_interlude=lambda base: True):
    """The ordered asset names of one start variant: `bases` are the template sessions in play order, the practice session first
    (number 0), each followed by its Interlude when it has one. Session n uses `set_for(n, start)`."""
    names = []
    for n, base in enumerate(bases):
        letter = set_for(n, start)
        names.append(variant_name(base, letter))
        if has_interlude(base):
            names.append(interlude_name(base, letter))
    return names


def default_sequence(bases, has_interlude=lambda base: True):
    """The default design's list: the template assets themselves, each followed by its Interlude."""
    names = []
    for base in bases:
        names.append(base)
        if has_interlude(base):
            names.append(f"{base}_Interlude")
    return names


def variant_for_pid(pid):
    """0 or 1 from a participant ID: FNV-1a (32 bit) of the trimmed, lower-cased UTF-8 text, bit 16 (mirrors DesignVariant.cs)."""
    h = 2166136261
    for byte in pid.strip().lower().encode("utf-8"):
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return (h >> 16) & 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("what", nargs="?", choices=("pid",))
    parser.add_argument("ids", nargs="*")
    args = parser.parse_args()
    if args.what == "pid":
        for pid in args.ids:
            print(f"{pid}: start variant {LETTERS[variant_for_pid(pid)]}")
        return
    for letter, chosen in FEATURE_SETS.items():
        print(f"set {letter}: colour {chosen['color']}, shape {chosen['shape']}")
    for start in (0, 1):
        print(f"start {LETTERS[start]}: " + " ".join(f"{'P' if n == 0 else 'S%d' % n}={set_for(n, start)}" for n in range(8)))


if __name__ == "__main__":
    main()
