"""Administration of the online data server: register releases and worlds, list runs, and pull a run's data into the local
layout (rundata.py) so replay.py, visibility.py and the analyses read it like a local log. Talks to Postgres directly (the
service connection string from the Supabase dashboard, in FORAGING_DB_URL; never put it in the repo).

    ./venv/bin/python scripts/server_admin.py register-release --commit <git hash> --sessions 12 [--note "..."]
    ./venv/bin/python scripts/server_admin.py register-worlds            # hashes Assets/StreamingAssets/Worlds/*
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


def register_release(conn, commit, n_sessions, note=None):
    conn.execute("insert into public.releases (build_commit, n_sessions, note) values (%s, %s, %s) "
                 "on conflict (build_commit) do update set n_sessions = excluded.n_sessions, note = excluded.note", (commit, n_sessions, note))


def register_worlds(conn, directory=WORLD_DIR):
    """Register every world and Interlude file under `directory` by sha256; returns the names registered."""
    names = []
    for path in sorted(Path(directory).iterdir()):
        if path.suffix in (".world", ".json"):
            conn.execute("insert into public.worlds (sha256, name) values (%s, %s) on conflict (sha256) do nothing",
                         (hashlib.sha256(path.read_bytes()).hexdigest(), path.name))
            names.append(path.name)
    return names


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def archive_worlds(commit, sessions, out_root):
    """Write the world and Interlude files the `sessions` rows name into `out_root`/_worlds/<sha8>_<name> (where replay looks), taking
    them from git at the run's build commit: a browser never archives its worlds, and the working tree's files get regenerated.
    A file already archived is kept; one git does not hold with the logged sha256 is reported, not written."""
    archive = Path(out_root) / "_worlds"
    for s in sessions:
        for name, sha in ((s["world_file"], s["world_sha256"]), (s.get("interlude_file"), s.get("interlude_sha256"))):
            target = archive / f"{sha[:8]}_{name}" if name else None
            if target is None or target.exists():
                continue
            blob = subprocess.run(["git", "show", f"{commit}:Assets/StreamingAssets/Worlds/{name}"], cwd=PROJECT_ROOT, capture_output=True).stdout
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
    rundata.write_run(out_root, run_id, {k: _iso(v) for k, v in run.items() if k not in ("run_id", "token_hash")})
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
    r = sub.add_parser("register-release")
    r.add_argument("--commit", required=True)
    r.add_argument("--sessions", type=int, required=True)
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
    if args.command == "register-release":
        register_release(conn, args.commit, args.sessions, args.note)
        print(f"registered {args.commit} with {args.sessions} sessions")
    elif args.command == "register-worlds":
        names = register_worlds(conn)
        print(f"registered {len(names)} files: {', '.join(names)}")
    elif args.command == "runs":
        for run in conn.execute("select r.run_id, r.status, r.started_at, r.build_commit, r.build_dirty, count(s.*) as sessions "
                                "from public.runs r left join public.sessions s using (run_id) group by r.run_id order by r.started_at"):
            print(json.dumps({k: _iso(v) if not isinstance(v, (int, bool, type(None))) else v for k, v in run.items()}, default=str))
    else:
        print(pull_run(conn, args.run, args.out))


if __name__ == "__main__":
    main()
