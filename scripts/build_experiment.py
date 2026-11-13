"""Build an experiment from its design module (`scripts/design/<code>.py`): its session assets, the ExperimentConfig and its catalog
entry (through the open Unity Editor and Assets/Editor/ExperimentBuilder.cs), the instruction texts, the worlds and the ranking pools.

    ./venv/bin/python scripts/build_experiment.py <code> [--remove-stale] [--no-generate] [--dry-run]

--remove-stale   delete the experiment's session assets that the design no longer lists (generated files of those names are removed too)
--no-generate    write assets and texts only; skip the worlds and pools (regenerate them with world.py / ranking.py)
--dry-run        print what would be built and write nothing

An open Editor in the `ready` state is needed for the assets (see CLAUDE.md, "Driving the Unity Editor"); nothing falls back to editing YAML.
"""

import argparse
import importlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from world import EXPERIMENTS_DIR, PROJECT_ROOT, STREAMING_EXPERIMENTS

UNITY = [str(Path.home() / ".local/bin/unity"), "--no-banner", "--no-pager", "command"]
ASSET_ROOT = "Assets/ScriptableObjects/Experiments"


def _text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (tuple, list)):
        return ",".join(repr(float(v)) for v in value)
    return str(value)


def _fields(mapping):
    return [{"p": path, "v": _text(value)} for path, value in mapping.items()]


def load_design(code):
    module = importlib.import_module(f"design.{code}")
    if module.CODE != code:
        raise ValueError(f"design/{code}.py declares CODE = {module.CODE!r}")
    return module


def asset_path(name, code):
    return f"{ASSET_ROOT}/{code}/{name}.asset"


def build_spec(module, remove_stale=False):
    """The spec the Editor builder reads: sessions in play order, each with its template and its fields as text."""
    code = module.CODE
    sessions = []
    for inst in module.instances():
        design = {**inst.design, "instance": inst.name}
        shared = {**inst.fields, "designJson": json.dumps(design, sort_keys=True)}
        sessions.append({"name": inst.name, "template": f"{ASSET_ROOT}/{module.TEMPLATE_SESSION.split('_')[0]}/{module.TEMPLATE_SESSION}.asset",
                         "fields": _fields({**shared, **inst.session_fields})})
    return {"code": code, "title": module.TITLE, "requires": list(getattr(module, "REQUIRES", ())),
            "countsTowardTotal": bool(getattr(module, "COUNTS_TOWARD_TOTAL", True)), "removeStale": bool(remove_stale), "sessions": sessions}


def run_editor_builder(spec, attempts=4):
    """Run the Editor builder. The pipeline server gives an Editor call 5 s on the main thread, and creating a batch of assets can take longer: the Editor then
    finishes the work anyway, and the builder is idempotent, so a timeout is answered by calling it again (the second call only finds the assets done)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{spec['code']}_spec.json"
        path.write_text(json.dumps(spec, indent=1))
        for attempt in range(attempts):
            out = subprocess.run(UNITY + ["eval", "--timeout", "180000", "--code", f'return ExperimentBuilder.Build(@"{path}");'], capture_output=True, text=True)
            if out.returncode == 0 and "Success\tfalse" not in out.stdout and "timed out" not in out.stdout + out.stderr:
                print(out.stdout.strip())
                return
            print(f"Editor call {attempt + 1} did not finish in time; calling again")
            time.sleep(10)
    raise RuntimeError(f"the Editor builder failed:\n{out.stdout}\n{out.stderr}")


def write_texts(module):
    texts = module.texts() if hasattr(module, "texts") else {}
    folder = STREAMING_EXPERIMENTS / module.CODE
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (folder / name).write_text(text)
    return sorted(texts)


def generate(module):
    """Worlds and ranking pools of every instance (what `world.py --unity` and `ranking.py pool` do), in this process."""
    import ranking
    import world
    for inst in module.instances():
        params = world.load_session(inst.name)
        path = world.unity_world_path(inst.name, int(params.world_seed))
        world.export_unity(world.generate_world(params, int(params.world_seed)), path)
        print(f"{path.name}")
        if int(getattr(params, "ranking_every", 0) or 0) > 0:
            print(ranking.export_pool(inst.name)[0].name)


def remove_stale_files(module):
    """Generated files in the experiment's StreamingAssets folder that no instance owns (worlds and ranking pools; texts are left alone)."""
    keep = {inst.name for inst in module.instances()}
    removed = []
    for path in (STREAMING_EXPERIMENTS / module.CODE).glob("*_seed*.*"):
        if path.name.split("_seed")[0] not in keep:
            path.unlink()
            removed.append(path.name)
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("code")
    ap.add_argument("--remove-stale", action="store_true")
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    module = load_design(args.code)
    spec = build_spec(module, args.remove_stale)
    if args.dry_run:
        print(json.dumps(spec, indent=1))
        return 0
    run_editor_builder(spec)
    print("texts:", write_texts(module))
    if args.remove_stale:
        print("stale generated files removed:", remove_stale_files(module))
    if not args.no_generate:
        generate(module)
    return 0


if __name__ == "__main__":
    sys.exit(main())
