"""Administration of the online data server: register releases and worlds, list runs, and pull a run's data into the local
layout (rundata.py) so replay.py, visibility.py and the analyses read it like a local log. Talks to Postgres directly (the
service connection string from the Supabase dashboard, in FORAGING_DB_URL; never put it in the repo).

    ./venv/bin/python scripts/server_admin.py register-experiment --code CF --title "Complex Features" [--requires TUT] [--order 2] [--completion-code XXXX] [--payout '{"..."}']
    ./venv/bin/python scripts/server_admin.py register-release --commit <git hash> --experiment TUT=2 --experiment CF=14 [--note "..."]
    ./venv/bin/python scripts/server_admin.py register-worlds            # hashes Assets/StreamingAssets/Experiments/*/*
    ./venv/bin/python scripts/server_admin.py runs
    ./venv/bin/python scripts/server_admin.py pull --run <run_id> --out ForagingData
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

import rundata
import trajectory_codec as codec
from replay import WORLD_DIR
from world import PROJECT_ROOT


def register_experiment(conn, code, title, requires=(), sort_order=0, completion_code=None, payout=None):
    """Create or update an experiment: the menu title, the experiments a participant must have finished first, the order in the menu, its
    Prolific completion code (none: a dummy is shown) and payout settings (stored for the analysis, not read by the server)."""
    conn.execute("insert into public.experiments (code, title, requires, sort_order, completion_code, payout) values (%s, %s, %s, %s, %s, %s) "
                 "on conflict (code) do update set title = excluded.title, requires = excluded.requires, sort_order = excluded.sort_order, "
                 "completion_code = excluded.completion_code, payout = excluded.payout",
                 (code, title, list(requires), sort_order, completion_code, None if payout is None else json.dumps(payout)))


def register_release(conn, commit, experiments, note=None):
    """Register a build and the experiments it offers: `experiments` maps an experiment code to its number of sessions (practice,
    sessions and Interludes alike) in this build. The experiments must be registered (`register_experiment`); run-start refuses a build
    that is not listed or an experiment it does not offer."""
    conn.execute("insert into public.releases (build_commit, note) values (%s, %s) on conflict (build_commit) do update set note = excluded.note",
                 (commit, note))
    conn.execute("delete from public.release_experiments where build_commit = %s", (commit,))
    for code, n in experiments.items():
        conn.execute("insert into public.release_experiments (build_commit, experiment, n_sessions) values (%s, %s, %s)", (commit, code, n))


def register_worlds(conn, directory=WORLD_DIR):
    """Register every world and Interlude file one folder under `directory` by sha256; returns the names registered."""
    names = []
    for path in sorted(Path(directory).glob("*/*")):                                          # <experiment code>/<file>
        if path.suffix in (".world", ".json"):
            conn.execute("insert into public.worlds (sha256, name) values (%s, %s) on conflict (sha256) do nothing",
                         (hashlib.sha256(path.read_bytes()).hexdigest(), path.name))
            names.append(path.name)
    return names


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def archive_worlds(commit, sessions, out_root, repo=PROJECT_ROOT):
    """Write the world and Interlude files the `sessions` rows name into `out_root`/_worlds/<sha8>_<name> (where replay looks), taking
    them from git at the run's build commit: a browser never archives its worlds, and the working tree's files get regenerated.
    A file already archived is kept; one git does not hold with the logged sha256 is reported, not written."""
    archive = Path(out_root) / "_worlds"
    for s in sessions:
        for name, sha in ((s["world_file"], s["world_sha256"]), (s.get("interlude_file"), s.get("interlude_sha256"))):
            target = archive / f"{sha[:8]}_{name}" if name else None
            if target is None or target.exists():
                continue
            blob = subprocess.run(["git", "show", f"{commit}:Assets/StreamingAssets/Experiments/{name.split('_')[0]}/{name}"], cwd=repo, capture_output=True).stdout
            if hashlib.sha256(blob).hexdigest() != sha:
                print(f"warning: {name} (sha256 {sha[:12]}) is not in git at {commit}; replay needs that file from elsewhere", file=sys.stderr)
                continue
            archive.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)


def write_session_rows(out_root, run_id, s, events, chunks, plan, trials):
    """Write one session's database rows as the local layout: `s` the `sessions` row, `events` its rows in seq order, `chunks` its
    trajectory rows (first_seq, data as bytes) in order, `plan` the `interlude_plan` row or None, `trials` its Interlude trial rows."""
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
    trials = [{k: v for k, v in t.items() if k not in ("run_id", "session_index")} for t in trials]
    row = {k: _iso(v) for k, v in s.items() if k not in ("run_id", "session_index")}
    rundata.write_session(out_root, run_id, index, row, traj, events, plan=plan["trial_order"] if plan else None,
                          trials=trials or None)


def pull_run(conn, run_id, out_root):
    """Write a run's tables as the local layout under `out_root`/<run_id>/, and its worlds under `out_root`/_worlds; returns the run folder."""
    run = conn.execute("select * from public.runs where run_id = %s", (run_id,)).fetchone()
    if run is None:
        raise KeyError(f"no run {run_id}")
    rundata.write_run(out_root, run_id, {k: _iso(v) if k != "participant_id" else str(v) for k, v in run.items() if k not in ("run_id", "token_hash")})
    sessions = conn.execute("select * from public.sessions where run_id = %s order by session_index", (run_id,)).fetchall()
    for s in sessions:
        where = (run_id, s["session_index"])
        write_session_rows(
            out_root, run_id, s,
            conn.execute("select * from public.events where run_id = %s and session_index = %s order by seq", where),
            conn.execute("select first_seq, data from public.trajectory where run_id = %s and session_index = %s order by first_seq", where),
            conn.execute("select trial_order from public.interlude_plan where run_id = %s and session_index = %s", where).fetchone(),
            conn.execute("select * from public.interlude_trials where run_id = %s and session_index = %s order by seq", where))
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
    r.add_argument("--experiment", action="append", required=True, metavar="CODE=N", help="an experiment of the build and its session count")
    r.add_argument("--note")
    sub.add_parser("register-worlds")
    sub.add_parser("runs")
    p = sub.add_parser("pull")
    p.add_argument("--run", required=True)
    p.add_argument("--out", default="ForagingData")
    args = parser.parse_args()
    import psycopg
    if not os.environ.get("FORAGING_DB_URL"):
        sys.exit("set FORAGING_DB_URL to the database connection string")
    conn = psycopg.connect(os.environ["FORAGING_DB_URL"], row_factory=psycopg.rows.dict_row, autocommit=True)
    if args.command == "register-experiment":
        register_experiment(conn, args.code, args.title, args.requires, args.order, args.completion_code, json.loads(args.payout) if args.payout else None)
        print(f"registered {args.code}: {args.title}")
    elif args.command == "register-release":
        experiments = {code: int(n) for code, n in (item.split("=") for item in args.experiment)}
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
