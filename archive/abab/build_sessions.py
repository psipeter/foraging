"""Build the per-variant session assets of the ABAB design from template assets, and generate their worlds and Interludes.

    ./venv/bin/python scripts/build_sessions.py S1 S2 [--dry-run] [--no-generate]

For each template session `<base>` (an asset `<base>.asset`, optionally with `<base>_Interlude.asset`) this makes, for each set letter,
`<base>_<A|B>.asset` and `<base>_<A|B>_Interlude.asset`: a copy of the template with the set's colour ramp and shape fields
(`feature_sets.fields`) and, for the Interlude, `interludeFor` pointing at the variant. Then it runs `world.py` for each variant and
`interlude.py` for each Interlude variant, so the files in `Assets/StreamingAssets/Worlds` exist. The template and its world seed are
the same for both variants, so the positions, the attributes and the per-fruit rewards are identical; only the canopy radius follows the
shape set. Re-running overwrites the fields of existing variants (a copy that already exists is kept, not re-copied).

Needs the Unity Editor open (the assets are made with the Unity CLI: `copy_asset`, `set_serialized_field`) and nothing else editing
the templates. The templates are not part of any played sequence once the variants exist; GameManager's `sequenceA` and `sequenceB`
lists name the variants. `--wire` fills the session lists in the open Editor, in the order the bases are given (the practice session first): the
default `sessionConfigs` list on the scene's GameManager (from the templates, committed) and `sequenceA` and `sequenceB` on the generated
`Assets/Resources/AbabSequences.asset` (from the variants). The variant assets, their worlds and Interludes and that asset are generated files
that are not committed (.gitignore); rebuild them with this script. The toggle that picks a design is GameManager's `design`, online.json "design",
`-design default|abab|baba|counterbalanced`, or `?design=` in a development build.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import feature_sets

ROOT = Path(__file__).resolve().parent.parent
FOLDER = "Assets/ScriptableObjects/SessionConfig"
UNITY = [str(Path.home() / ".local/bin/unity"), "--no-banner", "--no-pager", "command"]


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value) if isinstance(value, (dict, list)) else str(value)


def asset_path(name):
    return f"{FOLDER}/{name}.asset"


def commands(base, letter, interlude=False, exists=lambda path: False):
    """The CLI argument lists that make one variant asset (copy unless it exists, then set its fields)."""
    source = f"{base}_Interlude" if interlude else base
    dest = feature_sets.interlude_name(base, letter) if interlude else feature_sets.variant_name(base, letter)
    out = []
    if not exists(asset_path(dest)):
        out.append(["copy_asset", "--asset", asset_path(source), "--destination", asset_path(dest), "--confirm", "true"])
    values = dict(feature_sets.fields(letter))
    if interlude:
        values["interludeFor"] = feature_sets.variant_name(base, letter)
    for field, value in values.items():
        out.append(["set_serialized_field", "--target", asset_path(dest), "--field", field, "--value", _value(value)])
    return out


def plan(bases, exists=lambda path: False, has_interlude=lambda base: True):
    """Every CLI call, in order, for the template sessions `bases`."""
    calls = []
    for base in bases:
        for letter in feature_sets.LETTERS:
            calls += commands(base, letter, False, exists)
            if has_interlude(base):
                calls += commands(base, letter, True, exists)
    return calls


ABAB_ASSET = "Assets/Resources/AbabSequences.asset"


def list_calls(field, names):
    """The CLI argument lists that set one of the session lists to `names`: `sessionConfigs` on the scene's GameManager (the default design, committed),
    `sequenceA` and `sequenceB` on the generated Resources/AbabSequences asset (the ABAB design, not committed)."""
    if field == "sessionConfigs":
        base = ["set_serialized_field", "--target", json.dumps({"hierarchyPath": "/GameManager"}), "--component", "GameManager"]
    else:
        base = ["set_serialized_field", "--target", ABAB_ASSET]
    calls = [base + ["--field", f"{field}.Array.size", "--value", str(len(names))]]
    for i, name in enumerate(names):
        calls.append(base + ["--field", f"{field}.Array.data[{i}]", "--value", json.dumps({"path": asset_path(name)})])
    return calls


def wiring(bases, has_interlude=lambda base: True):
    """field -> asset names for GameManager's three lists."""
    return {"sessionConfigs": feature_sets.default_sequence(bases, has_interlude),
            "sequenceA": feature_sets.sequence(bases, 0, has_interlude),
            "sequenceB": feature_sets.sequence(bases, 1, has_interlude)}


def wire(bases, has_interlude, dry_run=False, default_only=False):
    if not dry_run and not default_only and not (ROOT / ABAB_ASSET).exists():
        subprocess.run(UNITY + ["create_asset", "--path", ABAB_ASSET, "--type", "AbabSequences", "--confirm", "true"], capture_output=True, text=True)
    for field, names in wiring(bases, has_interlude).items():
        if default_only and field != "sessionConfigs":
            continue
        print(f"{field}: {', '.join(names)}")
        for call in list_calls(field, names):
            if not dry_run:
                result = subprocess.run(UNITY + call, capture_output=True, text=True)
                if result.returncode != 0 or "\tfalse\t" in result.stdout:
                    sys.exit(f"unity command failed: {' '.join(call[:6])}\n{result.stdout[-400:]}{result.stderr[-400:]}")
    if not dry_run:
        subprocess.run(UNITY + ["save_all"], capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("bases", nargs="+", help="template session names, e.g. P S1 S2")
    parser.add_argument("--dry-run", action="store_true", help="print the CLI calls and the generator commands, run nothing")
    parser.add_argument("--no-generate", action="store_true", help="make the assets only; skip world.py and interlude.py")
    parser.add_argument("--no-templates", action="store_true", help="do not generate the templates' own worlds and Interludes (the default design's)")
    parser.add_argument("--no-variants", action="store_true", help="the default design only: no ABAB variants, generate the templates' worlds and Interludes, and --wire fills only the default list")
    parser.add_argument("--wire", action="store_true", help="also fill GameManager's sessionConfigs, sequenceA and sequenceB lists (overwrites them)")
    parser.add_argument("--wire-only", action="store_true", help="only fill the lists (the variant assets must exist)")
    args = parser.parse_args()

    exists = lambda path: (ROOT / path).exists()
    has_interlude = lambda base: exists(asset_path(f"{base}_Interlude"))
    if args.wire_only:
        wire(args.bases, has_interlude, args.dry_run, default_only=args.no_variants)
        return
    for call in ([] if args.no_variants else plan(args.bases, exists, has_interlude)):
        if args.dry_run:
            print(" ".join(UNITY[:4] + [call[0]] + [json.dumps(a) if " " in a or "{" in a or "[" in a else a for a in call[1:]]))
        else:
            result = subprocess.run(UNITY + call, capture_output=True, text=True)
            if result.returncode != 0 or "\tfalse\t" in result.stdout:
                sys.exit(f"unity command failed: {' '.join(call[:4])}\n{result.stdout[-400:]}{result.stderr[-400:]}")
    if not args.dry_run:
        subprocess.run(UNITY + ["save_all"], capture_output=True, text=True)      # the generators read the assets from disk
    variants = [feature_sets.variant_name(b, letter) for b in args.bases for letter in feature_sets.LETTERS]
    interludes = [feature_sets.interlude_name(b, letter) for b in args.bases if has_interlude(b) for letter in feature_sets.LETTERS]
    if args.no_variants:
        variants, interludes = [], []
    if not args.no_templates:                       # the default design plays the templates themselves
        variants = list(args.bases) + variants
        interludes = [f"{b}_Interlude" for b in args.bases if has_interlude(b)] + interludes
    steps = [[sys.executable, "scripts/world.py", *variants, "--unity"]] + ([[sys.executable, "scripts/interlude.py", *interludes]] if interludes else [])
    for step in steps:
        if args.dry_run or args.no_generate:
            print(" ".join(step))
        else:
            subprocess.run(step, cwd=ROOT, check=True)
    if args.wire:
        wire(args.bases, has_interlude, args.dry_run, default_only=args.no_variants)


if __name__ == "__main__":
    main()
