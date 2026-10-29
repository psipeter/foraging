"""Administration of the online data server: register releases and worlds, list runs, and pull a run's data into the local
layout (rundata.py) so replay.py, visibility.py and the analyses read it like a local log. Talks to Postgres directly (the
service connection string from the Supabase dashboard, in FORAGING_DB_URL; never put it in the repo).

    ./venv/bin/python scripts/server_admin.py register-release --commit <git hash> --sessions 10 [--note "..."]
    ./venv/bin/python scripts/server_admin.py register-worlds            # hashes Assets/StreamingAssets/Worlds/*
    ./venv/bin/python scripts/server_admin.py runs
    ./venv/bin/python scripts/server_admin.py pull --run <run_id> --out ForagingData
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

import rundata
import trajectory_codec as codec
from replay import WORLD_DIR


def connect(url=None):
    import psycopg
    from psycopg.rows import dict_row
    url = url or os.environ.get("FORAGING_DB_URL")
    if not url:
        sys.exit("set FORAGING_DB_URL to the database connection string")
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def register_release(conn, commit, n_sessions, note=None):
    conn.execute("insert into public.releases (build_commit, n_sessions, note) values (%s, %s, %s) "
                 "on conflict (build_commit) do update set n_sessions = excluded.n_sessions, note = excluded.note", (commit, n_sessions, note))


def register_worlds(conn, directory=WORLD_DIR):
    """Register every world and Interlude file under `directory` by sha256; returns the names registered."""
    names = []
    for path in sorted(Path(directory).iterdir()):
        if path.suffix in (".world", ".json") and not path.name.endswith(".meta"):
            conn.execute("insert into public.worlds (sha256, name) values (%s, %s) on conflict (sha256) do nothing",
                         (hashlib.sha256(path.read_bytes()).hexdigest(), path.name))
            names.append(path.name)
    return names


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def pull_run(conn, run_id, out_root):
    """Write a run's tables as the local layout under `out_root`/<run_id>/; returns the run folder."""
    run = conn.execute("select * from public.runs where run_id = %s", (run_id,)).fetchone()
    if run is None:
        raise KeyError(f"no run {run_id}")
    rundata.write_run(out_root, run_id, {k: _iso(v) for k, v in run.items() if k not in ("run_id", "token_hash")})
    for s in conn.execute("select * from public.sessions where run_id = %s order by session_index", (run_id,)).fetchall():
        index = s["session_index"]
        where = (run_id, index)
        events = [{"t": e["t"], "real": np.nan if e["real"] is None else e["real"], "type": e["type"],
                   "tree_id": -1 if e["tree_id"] is None else e["tree_id"], "k": -1 if e["k"] is None else e["k"],
                   "reward": np.nan if e["reward"] is None else e["reward"],
                   "running_total": np.nan if e["running_total"] is None else e["running_total"], "payload": e["payload"] or {}}
                  for e in conn.execute("select * from public.events where run_id = %s and session_index = %s order by seq", where)]
        frames, steps, expect = [], codec.DEFAULT_STEPS, 0
        for c in conn.execute("select first_seq, data from public.trajectory where run_id = %s and session_index = %s order by first_seq", where):
            first, steps, f = codec.decode(bytes(c["data"]))
            if first != expect:
                raise ValueError(f"run {run_id} session {index}: trajectory chunks do not tile (expected frame {expect}, got {first})")
            frames.append(f)
            expect += len(f)
        traj = np.concatenate(frames) if frames else np.empty((0, 6))
        plan = conn.execute("select trial_order from public.interlude_plan where run_id = %s and session_index = %s", where).fetchone()
        trials = [{k: v for k, v in t.items() if k not in ("run_id", "session_index")}
                  for t in conn.execute("select * from public.interlude_trials where run_id = %s and session_index = %s order by seq", where)]
        row = {k: _iso(v) for k, v in s.items() if k not in ("run_id", "session_index")}
        rundata.write_session(out_root, run_id, index, row, traj, events, plan=plan["trial_order"] if plan else None,
                              trials=trials or None, steps=steps)
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
    conn = connect()
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
