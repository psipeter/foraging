"""Administration of the online data server: register releases and worlds, list runs, and pull a run's data into the local
layout (rundata.py) so replay.py, visibility.py and the analyses read it like a local log. Talks to Postgres directly (the
service connection string from the Supabase dashboard, in FORAGING_DB_URL or, so that nothing has to be exported, on the first line of
~/.config/foraging/db_url (mode 600); never put it in the repo).

    ./venv/bin/python scripts/server_admin.py publish --build Builds/web [--dry-run] [--completion-code FN=XXXX]   # everything below, from the catalog and the build
    ./venv/bin/python scripts/server_admin.py register-experiment --code CF --title "Complex Features" [--requires TUT] [--order 2] [--completion-code XXXX] [--payout '{"..."}']
    ./venv/bin/python scripts/server_admin.py register-release --commit <git hash> --experiment TUT --experiment CF [--note "..."]
    ./venv/bin/python scripts/server_admin.py register-worlds            # hashes Assets/StreamingAssets/Experiments/*/*
    ./venv/bin/python scripts/server_admin.py runs
    ./venv/bin/python scripts/server_admin.py pull --run <run_id> --out ForagingData
"""

import argparse
import hashlib
import json
import os
import subprocess
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import rundata
import trajectory_codec as codec
from replay import WORLD_DIR
from world import PROJECT_ROOT


def register_experiment(conn, code, title, requires=(), sort_order=0, completion_code=None, payout=None):
    """Create or update an experiment: the menu title, the experiments a participant must have finished first, the order in the menu, its
    Prolific completion code (none: a dummy is shown, or the one already registered is kept) and payout settings (stored for the analysis, not read by the server;
    none keeps the registered ones)."""
    for required in requires:
        if conn.execute("select 1 from public.experiments where code = %s", (required,)).fetchone() is None and required != code:
            raise ValueError(f"{code} requires {required}, which is not registered (register it first: a prerequisite that does not exist locks {code} for everyone)")
    conn.execute("insert into public.experiments (code, title, requires, sort_order, completion_code, payout) values (%s, %s, %s, %s, %s, %s) "
                 "on conflict (code) do update set title = excluded.title, requires = excluded.requires, sort_order = excluded.sort_order, "
                 "completion_code = coalesce(excluded.completion_code, experiments.completion_code), payout = coalesce(excluded.payout, experiments.payout)",
                 (code, title, list(requires), sort_order, completion_code, None if payout is None else json.dumps(payout)))


def register_release(conn, commit, experiments, note=None, development=False):
    """Register a build and the experiments it offers: `experiments` maps an experiment code to its number of sessions in this build. The experiments must be registered (`register_experiment`); run-start refuses a build
    that is not listed or an experiment it does not offer. `development` marks a release made from a development build: only such a release may start a
    reduced run (a development build playing fewer sessions; migration 20261110000000_reduced_runs.sql)."""
    with conn.transaction():                                  # run-finish reads these rows: never see them half replaced
        conn.execute("insert into public.releases (build_commit, note, development) values (%s, %s, %s) "
                     "on conflict (build_commit) do update set note = excluded.note, development = excluded.development", (commit, note, bool(development)))
        conn.execute("delete from public.release_experiments where build_commit = %s", (commit,))
        for code, n in experiments.items():
            conn.execute("insert into public.release_experiments (build_commit, experiment, n_sessions) values (%s, %s, %s)", (commit, code, n))


def sessions_in_build(commit, code, repo=PROJECT_ROOT):
    """How many sessions the experiment `code` lists in its asset at `commit`: the count `register_release`
    registers, read from git so it cannot be mistyped."""
    asset = subprocess.run(["git", "show", f"{commit}:Assets/ScriptableObjects/Experiments/{code}/{code}.asset"], cwd=repo, capture_output=True, text=True)
    if asset.returncode != 0:
        raise ValueError(f"no experiment asset for {code} at {commit}: {asset.stderr.strip()}")
    listed = asset.stdout.split("\n  sessions:\n", 1)[1]
    return sum(1 for line in listed.split("\n") if line.startswith("  - "))


def register_worlds(conn, directory=WORLD_DIR):
    """Register every world and ranking pool file one folder under `directory` by sha256; returns the names registered."""
    names = []
    for path in sorted(Path(directory).glob("*/*")):                                          # <experiment code>/<file>
        if path.suffix in (".world", ".json"):
            conn.execute("insert into public.worlds (sha256, name) values (%s, %s) on conflict (sha256) do nothing",
                         (hashlib.sha256(path.read_bytes()).hexdigest(), path.name))
            names.append(path.name)
    return names


DB_URL_FILE = Path.home() / ".config" / "foraging" / "db_url"


def db_url(environ=os.environ, path=DB_URL_FILE):
    """The database connection string: FORAGING_DB_URL, else the first line of `path` (refused unless only its owner can read it). None when neither is there."""
    if environ.get("FORAGING_DB_URL"):
        return environ["FORAGING_DB_URL"]
    if path.is_file():
        if path.stat().st_mode & 0o077:
            raise PermissionError(f"{path} can be read by others: chmod 600 it (it holds the database password)")
        lines = path.read_text().strip().splitlines()
        return lines[0].strip() if lines else None
    return None


def _guid_paths(root):
    """{guid: asset path} of every .asset under `root` (from the .meta files)."""
    found = {}
    for meta in Path(root).rglob("*.asset.meta"):
        for line in meta.read_text().splitlines():
            if line.startswith("guid:"):
                found[line.split(":", 1)[1].strip()] = meta.with_suffix("")
    return found


def catalog_experiments(repo=PROJECT_ROOT):
    """The experiments of the game, in the catalog's order (the menu's order when there is no server): [{code, title, requires, order}], read from the assets,
    so adding an experiment to the catalog (build_experiment.py does) is all that registering it needs."""
    import yaml
    from world import _UnityLoader

    def fields(path):
        return yaml.load(Path(path).read_text(), Loader=_UnityLoader)["MonoBehaviour"]

    root = Path(repo) / "Assets"
    by_guid = _guid_paths(root / "ScriptableObjects" / "Experiments")
    catalog = fields(root / "Resources" / "ExperimentCatalog.asset")
    out = []
    for number, ref in enumerate(catalog["experiments"], start=1):
        f = fields(by_guid[ref["guid"]])
        out.append({"code": f["code"], "title": f["title"], "requires": list(f.get("requires") or []), "order": number})
    return out


def build_plan(build_dir=None, commit=None, repo=PROJECT_ROOT):
    """What `publish` registers: the experiments (those the build holds when `build_dir` is given, else every catalog experiment), the commit (the build's own, from its
    build_info.json, else `commit` or HEAD) with each experiment's session count read from git, the folder whose world and ranking pool files are registered (the build's,
    so the hashes are of the files the participant downloads), and the notes a human should see (a dirty build, a commit that is not HEAD)."""
    repo = Path(repo)
    notes = []
    development = False
    root = repo / "Assets" / "StreamingAssets" / "Experiments"
    if build_dir:
        build_dir = Path(build_dir)
        info = json.loads((build_dir / "StreamingAssets" / "build_info.json").read_text())
        commit = commit or info["commit"]
        root = build_dir / "StreamingAssets" / "Experiments"
        if info.get("dirty"):
            notes.append("the build was made from a dirty tree: registered, and flagged by the server")
        development = bool(info.get("development"))
        if development:
            notes.append("a development build: registered as a development release, which may start reduced runs (short and repeats)")
    if commit is None:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    elif len(commit) < 40:
        commit = subprocess.run(["git", "rev-parse", commit], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    held = {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()
    experiments = [e for e in catalog_experiments(repo) if e["code"] in held]
    if not experiments:
        raise ValueError(f"no experiment of the catalog has files in {root}")
    for e in experiments:
        missing = [r for r in e["requires"] if r not in {x["code"] for x in experiments}]
        if missing:
            notes.append(f"{e['code']} requires {', '.join(missing)}, which this build does not offer: it stays locked unless the server already has a finished run of it")
    sessions = {e["code"]: sessions_in_build(commit, e["code"], repo) for e in experiments}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    if head != commit:
        notes.append(f"the commit is not HEAD ({head[:7]}): fine for a build made earlier")
    return {"commit": commit, "experiments": experiments, "sessions": sessions, "worlds": root, "notes": notes, "development": development}


def build_description(build_dir, reason=None, repo=PROJECT_ROOT, now=None):
    """(subject, body) describing a WebGL build, for the deploy commit in the Pages repository (`deploy_webgl.sh`) and for the release's note (`publish`): its kind,
    the commit of this repository it was made from (and whether the tree was dirty), its size and what it holds. The Pages repository keeps only its latest commit, so
    the registered release is where the record of each deploy lives. `reason` is a free line: what this deploy is for."""
    build_dir = Path(build_dir)
    plan = build_plan(build_dir, repo=repo)
    info = json.loads((build_dir / "StreamingAssets" / "build_info.json").read_text())
    size = sum(f.stat().st_size for f in build_dir.rglob("*") if f.is_file()) / 1e6
    kind = "Development" if plan["development"] else "Release"
    dirty = bool(info.get("dirty"))
    holds = ", ".join(f"{code} {n}" for code, n in plan["sessions"].items())
    subject = f"{kind} build {plan['commit'][:7]}{' (dirty)' if dirty else ''}: {size:.0f} MB, parts {holds}"
    when = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"Reason: {reason}"] if reason else []
    lines += [f"Made from the foraging commit {plan['commit']}" + (", with uncommitted changes to files that shape the game." if dirty else "."),
              f"Holds (sessions): {holds}.", f"Prepared {when}."]
    return subject, "\n".join(lines)


def release_note(subject, reason=None):
    """The one-line note a release is registered with: the build's subject line and the reason, if any."""
    return subject + (f" | {reason}" if reason else "")


def publish(conn, plan, completion_codes=None, note=None):
    """Register what `build_plan` found: each experiment (keeping a completion code already registered unless one is given), the build's files, the release.
    Safe to repeat. Returns a one-line summary per step."""
    completion_codes = completion_codes or {}
    done = []
    for e in plan["experiments"]:
        register_experiment(conn, e["code"], e["title"], e["requires"], e["order"], completion_codes.get(e["code"]))
        done.append(f"experiment {e['code']} ({e['title']}, order {e['order']}, requires {e['requires'] or 'nothing'})")
    names = register_worlds(conn, plan["worlds"])
    done.append(f"{len(names)} world and ranking pool files from {plan['worlds']}")
    register_release(conn, plan["commit"], plan["sessions"], note, plan.get("development", False))
    done.append(f"release {plan['commit'][:12]} with {plan['sessions']}")
    return done


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, uuid.UUID) else value


def archive_worlds(commit, sessions, out_root, repo=PROJECT_ROOT):
    """Write the world files the `sessions` rows name into `out_root`/_worlds/<sha8>_<name> (where replay looks), taking
    them from git at the run's build commit: a browser never archives its worlds, and the working tree's files get regenerated.
    A file already archived is kept; one git does not hold with the logged sha256 is reported, not written."""
    archive = Path(out_root) / "_worlds"
    for s in sessions:
        for name, sha in ((s["world_file"], s["world_sha256"]),):
            target = archive / f"{sha[:8]}_{name}" if name else None
            if target is None or target.exists():
                continue
            # an experiment's folder, or (a build from before experiments) the flat Worlds folder
            blob = b""
            for place in (f"Experiments/{name.split('_')[0]}", "Worlds"):
                blob = subprocess.run(["git", "show", f"{commit}:Assets/StreamingAssets/{place}/{name}"], cwd=repo, capture_output=True).stdout
                if blob:
                    break
            if hashlib.sha256(blob).hexdigest() != sha:
                print(f"warning: {name} (sha256 {sha[:12]}) is not in git at {commit}; replay needs that file from elsewhere", file=sys.stderr)
                continue
            archive.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)


def write_session_rows(out_root, run_id, s, events, chunks, sets):
    """Write one session's database rows as the local layout: `s` the `sessions` row, `events` its rows in seq order, `chunks` its
    trajectory rows (first_seq, data as bytes) in order, `sets` its `ranking_sets` rows."""
    index = s["session_index"]
    events = [{"t": e["t"], "real": np.nan if e["real"] is None else e["real"], "type": e["type"],
               "tree_id": -1 if e["tree_id"] is None else e["tree_id"], "k": -1 if e["k"] is None else e["k"],
               "reward": np.nan if e["reward"] is None else e["reward"],
               "running_total": np.nan if e["running_total"] is None else e["running_total"], "payload": e["payload"] or {}}
              for e in events]
    frames, expect = [], 0
    for c in chunks:
        first, _, f = codec.decode(bytes(c["data"]))
        if first != expect:
            raise ValueError(f"run {run_id} session {index}: trajectory chunks do not tile (expected frame {expect}, got {first})")
        frames.append(f)
        expect += len(f)
    traj = np.concatenate(frames) if frames else np.empty((0, 6))
    sets = [{k: v for k, v in t.items() if k not in ("run_id", "session_index")} for t in sets]
    row = {k: _iso(v) for k, v in s.items() if k not in ("run_id", "session_index")}
    rundata.write_session(out_root, run_id, index, row, traj, events, sets=sets or None)


def pull_run(conn, run_id, out_root):
    """Write a run's tables as the local layout under `out_root`/<run_id>/, and its worlds under `out_root`/_worlds; returns the run folder."""
    run = conn.execute("select * from public.runs where run_id = %s", (run_id,)).fetchone()
    if run is None:
        raise KeyError(f"no run {run_id}")
    rundata.write_run(out_root, run_id, {k: _iso(v) for k, v in run.items() if k not in ("run_id", "token_hash")})
    sessions = conn.execute("select * from public.sessions where run_id = %s order by session_index", (run_id,)).fetchall()
    for s in sessions:
        where = (run_id, s["session_index"])
        write_session_rows(
            out_root, run_id, s,
            conn.execute("select * from public.events where run_id = %s and session_index = %s order by seq", where),
            conn.execute("select first_seq, data from public.trajectory where run_id = %s and session_index = %s order by first_seq", where),
            conn.execute("select * from public.ranking_sets where run_id = %s and session_index = %s order by seq", where))
    archive_worlds(run["build_commit"], sessions, out_root)
    return Path(out_root) / str(run_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("register-experiment")
    e.add_argument("--code", required=True)
    e.add_argument("--title", required=True)
    e.add_argument("--requires", action="append", default=[])
    e.add_argument("--order", type=int, default=0)
    e.add_argument("--completion-code")
    e.add_argument("--payout", help="JSON")
    r = sub.add_parser("register-release")
    r.add_argument("--commit", required=True)
    r.add_argument("--experiment", action="append", required=True, metavar="CODE", help="an experiment of the build (its session count is read from the asset at --commit)")
    r.add_argument("--note")
    sub.add_parser("register-worlds")
    pub = sub.add_parser("publish", help="register the experiments, the build's world files and the release in one go")
    pub.add_argument("--build", help="the WebGL build directory (its build_info.json names the commit, its StreamingAssets the experiments and files); default: the catalog and HEAD")
    pub.add_argument("--commit", help="override the build's commit")
    pub.add_argument("--completion-code", action="append", default=[], metavar="CODE=VALUE", help="a Prolific completion code for an experiment (kept if already registered)")
    pub.add_argument("--note", help="what this deploy is for; the release's note is the build's description (kind, commit, size, parts) followed by this")
    pub.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing and connect to nothing")
    sub.add_parser("runs")
    d = sub.add_parser("describe", help="print the commit message for a build's deploy (subject line, blank line, body); connects to nothing")
    d.add_argument("--build", required=True)
    d.add_argument("--reason")
    p = sub.add_parser("pull")
    p.add_argument("--run", required=True)
    p.add_argument("--out", default="ForagingData")
    args = parser.parse_args()
    if args.command == "describe":
        subject, body = build_description(args.build, args.reason)
        print(subject + "\n\n" + body)
        return
    if args.command == "publish":
        plan = build_plan(args.build, args.commit)
        print(f"commit {plan['commit']}; experiments {[(e['code'], e['order']) for e in plan['experiments']]}; sessions {plan['sessions']}; files from {plan['worlds']}")
        for line in plan["notes"]:
            print("note:", line)
        if args.dry_run:
            return
    import psycopg
    url = db_url()
    if not url:
        sys.exit(f"no database connection string: set FORAGING_DB_URL or put it on the first line of {DB_URL_FILE} (chmod 600)")
    conn = psycopg.connect(url, row_factory=psycopg.rows.dict_row, autocommit=True, prepare_threshold=None)      # (no server-side prepared statements: the pooler hands queries to different server connections)
    if args.command == "publish":
        codes = dict(item.split("=", 1) for item in args.completion_code)
        note = release_note(build_description(args.build)[0], args.note) if args.build else args.note
        for line in publish(conn, plan, codes, note):
            print("registered", line)
        return
    if args.command == "register-experiment":
        register_experiment(conn, args.code, args.title, args.requires, args.order, args.completion_code, json.loads(args.payout) if args.payout else None)
        print(f"registered {args.code}: {args.title}")
    elif args.command == "register-release":
        experiments = {code: sessions_in_build(args.commit, code) for code in args.experiment}
        register_release(conn, args.commit, experiments, args.note)
        print(f"registered {args.commit} with {experiments}")
    elif args.command == "register-worlds":
        names = register_worlds(conn)
        print(f"registered {len(names)} files: {', '.join(names)}")
    elif args.command == "runs":
        for run in conn.execute("select r.run_id, r.experiment, r.status, r.started_at, r.build_commit, r.build_dirty, count(s.*) as sessions "
                                "from public.runs r left join public.sessions s using (run_id) group by r.run_id order by r.started_at"):
            print(json.dumps({k: _iso(v) if not isinstance(v, (int, bool, type(None))) else v for k, v in run.items()}, default=str))
    else:
        print(pull_run(conn, args.run, args.out))


if __name__ == "__main__":
    main()
