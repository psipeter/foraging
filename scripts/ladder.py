"""The session ladder (the Tutorial's TUT_S1 and Complex Features' CF_S1 to CF_S7): the SessionConfig fields of each session, applied to its asset and its Interlude asset
(TUT_S1 and TUT_I1, CF_S1 and CF_I1, ...), which live in Assets/ScriptableObjects/Experiments/<code>/.

    ./venv/bin/python scripts/ladder.py CF_S1 CF_S2 [--dry-run]            (the names before experiments, P and S1 to S7, are accepted too)
    ./venv/bin/python scripts/ladder.py CF_S3 CF_S4 --recreate [--from CF_S2]     # replace the old assets by copies of CF_S2 (continuous terrain), then set the fields

`docs/SCIENCE.md` ("Planned session structure") has the design. This module is the table of the reward function of each session (which
features vary, which pays and how); `ladder.py <names>` writes it onto the template assets `<name>.asset` and its Interlude asset
with the Unity CLI (an open Editor is needed), the template's other settings (duration, instruction file, Interlude mode and length,
terrain) being left as they are. `world.py <sessions> --unity` and `interlude.py <the Interludes>` then regenerate their worlds and Interludes.
Reward numbers are provisional: the best bush pays about 4 per fruit (as in every earlier session) and the matching of the spread of the
reward across sessions is tuned separately. Which end of a feature pays more is a draw (a linear weight, or a peak), not a design
requirement; counterbalancing it across participants is later work.

CF_S3 to CF_S7 were made from a copy of CF_S2 (`--recreate`: the old asset and its Interlude are deleted first), so they inherit the continuous low-relief terrain, the hybrid
Interlude (20 trials, 2 repeats) and the other settings of CF_S2; `SESSION_ONLY` sets the duration and instruction file of the session asset alone.

Basis function types (BasisFunctionType): 0 Linear, 1 InvertedLinear, 2 GaussianPeak, 3 InvertedGaussian, 4 Constant.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from world import canonical

FOLDER = "Assets/ScriptableObjects/Experiments"
UNITY = [str(Path.home() / ".local/bin/unity"), "--no-banner", "--no-pager", "command"]


def asset_path(name):
    return f"{FOLDER}/{name.split('_')[0]}/{name}.asset"            # <code>/<code>_S1.asset: the experiment's folder


def interlude_name(name):
    """The Interlude asset of a session: CF_S1 -> CF_I1."""
    code, number = name.split("_")
    return f"{code}_I{number[1:]}"


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value) if isinstance(value, (dict, list)) else str(value)


NO_RANDOM = {"x": 0.0, "y": 0.0}


def terms(bumps=(), products=()):
    """The reward function's bump and product lists (each item a dict of fields) as fields: the list sizes and every item's fields."""
    out = {"rewardFunction.bumps.Array.size": len(bumps), "rewardFunction.products.Array.size": len(products)}
    for kind, items in (("bumps", bumps), ("products", products)):
        for i, item in enumerate(items):
            out.update({f"rewardFunction.{kind}.Array.data[{i}].{k}": v for k, v in item.items()})
    return out


def component(feature, kind=0, weight=0.0, peak=0.0, width=0.0):
    return {f"rewardFunction.{feature}Component.{k}": v for k, v in
            (("basisFunctionType", kind), ("weight", weight), ("peak", peak), ("width", width))}


LADDER = {
    # practice: every bush has a random point value no feature predicts; both features vary
    "TUT_S1": {"worldSeed": 200, "shapeVaries": True, "colorVaries": True, "randomBushValueRange": {"x": 0.0, "y": 4.0},
          **component("shape"), **component("color"), **component("moisture")},
    # S1: fruit colour varies (shapes identical); the points are linear in the colour
    "CF_S1": {"worldSeed": 201, "shapeVaries": False, "colorVaries": True, "randomBushValueRange": NO_RANDOM,
           **component("shape"), **component("color", kind=0, weight=4.0), **component("moisture")},
    # S2: bush shape varies (colours identical); the points peak on the shape spectrum, off the centre
    "CF_S2": {"worldSeed": 202, "shapeVaries": True, "colorVaries": False, "randomBushValueRange": NO_RANDOM,
           **component("shape", kind=2, weight=4.0, peak=0.65, width=0.2), **component("color"), **component("moisture")},
    # S3: both vary, only colour pays, linear: S1's feature and function class with shape as a distractor (the polarity is reversed, so S1's answer does not carry over)
    "CF_S3": {"worldSeed": 203, "shapeVaries": True, "colorVaries": True, "randomBushValueRange": NO_RANDOM,
           **component("shape"), **component("color", kind=1, weight=4.0), **component("moisture")},
    # S4: both vary, only shape pays, a peak: S2's feature and function class with colour as a distractor (the peak is elsewhere, 0.30 against 0.65)
    "CF_S4": {"worldSeed": 204, "shapeVaries": True, "colorVaries": True, "randomBushValueRange": NO_RANDOM,
           **component("shape", kind=2, weight=4.0, peak=0.30, width=0.2), **component("color"), **component("moisture")},
    # S5: both pay, a weighted linear mixture: shape up with weight 2.4, colour down with weight 1.6 (the best bush pays 4)
    "CF_S5": {"worldSeed": 205, "shapeVaries": True, "colorVaries": True, "randomBushValueRange": NO_RANDOM,
           **component("shape", kind=0, weight=2.4), **component("color", kind=1, weight=1.6), **component("moisture")},
    # S6: an interaction, one feature linear times a Gaussian of the other: shape up, times a peak on colour at 0.6 (width 0.25); the best bush pays 4
    "CF_S6": {"worldSeed": 206, "shapeVaries": True, "colorVaries": True, "randomBushValueRange": NO_RANDOM,
           **component("shape"), **component("color"), **component("moisture"),
           **terms(products=[{"linearInShape": True, "linearInverted": False, "center": 0.6, "width": 0.25, "height": 4.0}])},
    # S7: a full interaction, a 2-D Gaussian with its own centre and spread on each axis: shape 0.30 (spread 0.25), colour 0.70 (spread 0.15); the best bush pays 4
    "CF_S7": {"worldSeed": 207, "shapeVaries": True, "colorVaries": True, "randomBushValueRange": NO_RANDOM,
           **component("shape"), **component("color"), **component("moisture"),
           **terms(bumps=[{"centerShape": 0.30, "centerColor": 0.70, "width": 0.25, "widthColor": 0.15, "height": 4.0}])},
}

# The terrain of every session (PI, 2026-11-05): the terraced moisture field of the old S3 and S4 (4 plateau levels, ramps between them, a small undulation), with a lower
# relief. Moisture pays in none of the new sessions, so the plateaus and their ground colours and heights are decoration; `terrainMaxElevation` is half of the old 12.
TERRAIN = {"moistureTerraceLevels": 4, "moistureTerraceSharpness": 0.3, "moistureTerraceResidual": 0.1, "terrainNoiseFrequency": 2.0, "terrainMaxElevation": 6.0}

# Spatial evenness of the reward (scripts/spatial.py): Off, Tiles or TilesAndSwaps for every session (a switch to turn on or off per experiment; Off draws every bush
# independently, as before). Change it here and re-run `ladder.py`, `world.py` and `interlude.py` to regenerate the worlds.
SPATIAL_BALANCE = "TilesAndSwaps"

# Light distance fog in every session and Interlude (PI, 2026-11-06): far bushes are hard to make out anyway; linear, nothing nearer than FogStart is touched and
# everything beyond FogEnd is the scene's fog colour. The PI tuned them by hand (2026-11-06): start 50, end 200, mountains take 0.15 of the fog.
FOG = {"fogEnabled": True, "fogStartDistance": 50.0, "fogEndDistance": 200.0, "mountainFogStrength": 0.15}

# A little brighter (PI, 2026-11-06), to make up for the dullness of the fog: the sun's intensity curve x1.2 (canopy and fruit highlights; the terrain ignores it) and
# +0.3 EV of post-exposure at every elevation (the whole screen; fruit undo it, so a fruit keeps its brightness). The PI tunes both by hand in the Inspector.
LIGHT = {"sunIntensityScale": 1.2, "postExposureOffset": 0.3}

for _fields in LADDER.values():                       # every session sets the reward terms' list sizes (0 for those without bumps or products), the terrain and the spatial switch
    _fields["spatialBalance"] = SPATIAL_BALANCE
    _fields.setdefault("rewardFunction.bumps.Array.size", 0)
    _fields.setdefault("rewardFunction.products.Array.size", 0)
    _fields.update(TERRAIN)
    _fields.update(FOG)
    _fields.update(LIGHT)

# fields of the session asset alone (an Interlude's duration is a cap, and its instruction file is the Interlude's). Durations (PI, 2026-11-05): practice 30 s,
# S1 and S2 90 s, S3 and S4 2 minutes, S5 to S7 3 minutes.
SESSION_ONLY = {
    "TUT_S1": {"sessionDuration": 30.0},
    "CF_S1": {"sessionDuration": 90.0},
    "CF_S2": {"sessionDuration": 90.0},
    "CF_S3": {"sessionDuration": 120.0, "instructionsFile": "Experiments/CF/instructions_S3.txt"},
    "CF_S4": {"sessionDuration": 120.0, "instructionsFile": "Experiments/CF/instructions_S4.txt"},
    "CF_S5": {"sessionDuration": 180.0, "instructionsFile": "Experiments/CF/instructions_S5.txt"},
    "CF_S6": {"sessionDuration": 180.0, "instructionsFile": "Experiments/CF/instructions_S6.txt"},
    "CF_S7": {"sessionDuration": 180.0, "instructionsFile": "Experiments/CF/instructions_S7.txt"},
}


def calls(name):
    """The CLI argument lists that apply a session's fields to its asset and its Interlude asset."""
    out = []
    for asset in (name, interlude_name(name)):
        fields = {**LADDER[name], **(SESSION_ONLY.get(name, {}) if asset == name else {"interludeFor": name})}     # (a copied Interlude still names the session it was copied from)
        for field, value in fields.items():
            out.append(["set_serialized_field", "--target", asset_path(asset), "--field", field, "--value", _value(value)])
    return out


def recreate_calls(name, source="CF_S2"):
    """The CLI calls that replace a session and its Interlude by copies of `source` and its Interlude (the old assets are deleted first)."""
    out = []
    for asset, src in ((name, source), (interlude_name(name), interlude_name(source))):
        out.append(["delete_asset", "--asset", asset_path(asset), "--confirm", "true"])
        out.append(["copy_asset", "--asset", asset_path(src), "--destination", asset_path(asset), "--confirm", "true"])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("names", nargs="+", type=canonical, choices=sorted(LADDER))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recreate", action="store_true", help="delete the sessions' assets and Interludes and copy them from --from first")
    parser.add_argument("--from", dest="source", default="CF_S2", type=canonical, help="the session to copy for --recreate (default CF_S2)")
    args = parser.parse_args()
    for name in args.names:
        for call in (recreate_calls(name, args.source) if args.recreate else []) + calls(name):
            if args.dry_run:
                print(" ".join(call))
                continue
            result = subprocess.run(UNITY + call, capture_output=True, text=True)
            if call[0] != "delete_asset" and (result.returncode != 0 or "\tfalse\t" in result.stdout):    # (a delete of an asset that is not there is fine)
                sys.exit(f"unity command failed: {' '.join(call[:6])}\n{result.stdout[-300:]}{result.stderr[-300:]}")
        print(f"{name}: {len(calls(name))} fields set")
    if not args.dry_run:
        subprocess.run(UNITY + ["save_all"], capture_output=True, text=True)


if __name__ == "__main__":
    main()
