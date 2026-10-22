"""Run only the Python tests that the files you changed could affect.

The suite has several test files with different dependencies; a change to Unity C#, docs or Unity assets that the
Python code never reads cannot break them, so there is no reason to run them. This compares the working tree with a git
ref (default HEAD; uncommitted and untracked files count) and runs the test files whose inputs changed.

    ./venv/bin/python scripts/run_tests.py              # tests affected by changes since HEAD
    ./venv/bin/python scripts/run_tests.py --since main # ... since another ref
    ./venv/bin/python scripts/run_tests.py --all        # everything (do this before committing a release)
    ./venv/bin/python scripts/run_tests.py --fast       # affected tests, skipping those marked slow (freshness checks, long searches)
    ./venv/bin/python scripts/run_tests.py --dry-run    # show the decision, run nothing
    ./venv/bin/python scripts/run_tests.py --files scripts/world.py docs/SCIENCE.md   # decide for these paths instead
    ./venv/bin/python scripts/run_tests.py -- -k hump   # arguments after -- go to pytest

When a new Python module or test file is added, add it to DEPENDENCIES below.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION_CONFIGS = "Assets/ScriptableObjects/SessionConfig/"


def _is_interlude_asset(path):
    return path.startswith(SESSION_CONFIGS) and path.endswith("_Interlude.asset")


def _is_session_asset(path):
    return path.startswith(SESSION_CONFIGS) and path.endswith(".asset") and not _is_interlude_asset(path)


def _is_interlude_file(path):
    # the committed Interlude trial files are compared with a fresh generation (test_committed_interlude_file_is_fresh)
    return path.startswith("Assets/StreamingAssets/Worlds/") and path.endswith(".interlude.json")


def _is_world_file(path):
    # the committed session worlds are compared with a fresh generation (test_committed_world_files_are_fresh)
    return path.startswith("Assets/StreamingAssets/Worlds/") and path.endswith(".world")


# test file -> what it depends on: exact paths, and predicates over a repo-relative path.
# (The Python code reads the SessionConfig .asset YAML; test_world also reads WorldData.cs and the generated .world files.)
DEPENDENCIES = {
    "scripts/test_world.py": {
        "paths": {"scripts/world.py", "Assets/Scripts/World/WorldData.cs"},   # (the C# check names are mirrored)
        "match": [_is_session_asset, _is_world_file],
    },
    "scripts/test_sim.py": {
        "paths": {"scripts/sim.py", "scripts/agents.py", "scripts/perception.py", "scripts/world.py", "scripts/costs.py", "scripts/conftest.py"},
        "match": [_is_session_asset],
    },
    "scripts/test_agents.py": {
        "paths": {"scripts/agents.py", "scripts/sim.py", "scripts/perception.py", "scripts/world.py", "scripts/interlude.py", "scripts/costs.py", "scripts/conftest.py",
                  "scripts/test_sim.py"},
        "match": [_is_session_asset, _is_interlude_asset],
    },
    "scripts/test_specs.py": {
        "paths": {"scripts/specs.py", "scripts/agents.py", "scripts/perception.py", "scripts/sim.py", "scripts/world.py",
                  "scripts/costs.py", "scripts/conftest.py", "scripts/test_agents.py", "scripts/test_sim.py"},
        "match": [_is_session_asset],
    },
    "scripts/test_fingerprint.py": {
        "paths": {"scripts/fingerprint.py", "scripts/specs.py", "scripts/agents.py", "scripts/perception.py", "scripts/sim.py",
                  "scripts/world.py", "scripts/interlude.py", "scripts/costs.py", "scripts/conftest.py", "scripts/test_agents.py"},
        "match": [_is_session_asset, _is_interlude_asset],
    },
    "scripts/test_results.py": {
        "paths": {"scripts/results.py", "scripts/fingerprint.py", "scripts/specs.py", "scripts/agents.py", "scripts/perception.py",
                  "scripts/sim.py", "scripts/world.py", "scripts/interlude.py", "scripts/costs.py", "scripts/conftest.py"},
        "match": [_is_session_asset, _is_interlude_asset],
    },
    "scripts/test_analysis.py": {
        "paths": {"scripts/analysis.py", "scripts/plots.py", "scripts/results.py", "scripts/fingerprint.py", "scripts/specs.py", "scripts/agents.py",
                  "scripts/perception.py", "scripts/sim.py", "scripts/world.py", "scripts/costs.py", "scripts/conftest.py"},
        "match": [_is_session_asset],
    },
    "scripts/test_replay.py": {
        "paths": {"scripts/replay.py", "scripts/world.py"},
        "match": [_is_session_asset],
    },
    "scripts/test_visibility.py": {
        "paths": {"scripts/visibility.py", "scripts/replay.py", "scripts/world.py"},
        "match": [],
    },
    "scripts/test_interlude.py": {
        "paths": {"scripts/interlude.py", "scripts/world.py"},
        "match": [_is_session_asset, _is_interlude_asset, _is_interlude_file],
    },
}


def changed_files(since):
    def git(*args):
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [line for line in out.splitlines() if line]

    files = set(git("diff", "--name-only", since)) | set(git("ls-files", "--others", "--exclude-standard"))
    return {f for f in files if not f.endswith(".meta")}


def affected(test, files):
    dep = DEPENDENCIES[test]
    reasons = []
    for f in sorted(files):
        if f == test or f in dep["paths"] or any(m(f) for m in dep["match"]):
            reasons.append(f)
    return reasons


def main():
    argv = sys.argv[1:]
    passthrough = []
    if "--" in argv:
        i = argv.index("--")
        argv, passthrough = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="run every test file")
    ap.add_argument("--since", default="HEAD", help="git ref to compare the working tree with (default HEAD)")
    ap.add_argument("--fast", action="store_true", help="skip tests marked slow (freshness checks, long searches); run the full set before committing")
    ap.add_argument("--dry-run", action="store_true", help="show which test files would run, then stop")
    ap.add_argument("--files", nargs="+", help="decide from these repo-relative paths instead of from git")
    args = ap.parse_args(argv)

    files = set(args.files) if args.files else changed_files(args.since)
    selected = []
    print(f"{len(files)} changed file(s) {'given' if args.files else 'since ' + args.since}")
    for test in DEPENDENCIES:
        reasons = affected(test, files)
        run = args.all or bool(reasons)
        shown = ", ".join(reasons[:3]) + (f" (+{len(reasons) - 3} more)" if len(reasons) > 3 else "")
        print(f"  {'RUN ' if run else 'skip'}  {test}" + (f"   <- {shown}" if reasons else ("   (--all)" if args.all else "")))
        if run:
            selected.append(test)

    if not selected:
        print("No Python test depends on the changed files; nothing to run (use --all to run everything).")
        return 0
    if args.dry_run:
        return 0
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *[str(ROOT / t) for t in selected], *(["-m", "not slow"] if args.fast else []), *passthrough]
    return subprocess.call(cmd, cwd=ROOT / "scripts")


if __name__ == "__main__":
    sys.exit(main())
