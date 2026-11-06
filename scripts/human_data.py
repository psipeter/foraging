"""Participant data from the online database, as files and tables for analysis (docs/ONLINE_DATA_PLAN.md, sections 1 and 3).

    ./venv/bin/python scripts/human_data.py download [--out ForagingData] [--all]
    ./venv/bin/python scripts/human_data.py list [--exclude peter] [--status finished]

`download` reads the database through the Supabase CLI (`supabase db query --remote`, read-only; the CLI must be logged in to the
project) and writes, under `ForagingData/` (gitignored; it holds participant names):

    <run_id>/<session:02d>/...   the raw local layout of rundata.py (events, decoded trajectory, Interlude trials, world files in
                                 _worlds/), so replay.py and visibility.py read a participant like a local log; run.json also
                                 carries the participant ID, the name they signed with and their feedback text
    humans.sqlite                tidy tables, one row per participant / session / event / Interlude trial:
        participants      one row per run (a participant has one run per experiment): run_id, participant (the Prolific ID typed on the
                          login screen), signature (the name typed on the consent screen), status, started_at, finished_at, minutes,
                          build_commit, n_sessions, n_completed, feedback, on_server, ..., and at the end participant_id (the server's
                          identifier of the person, the same in every run of theirs) and experiment (the experiment's code: CF, TUT, ...)
        sessions          run_id, session_index, name, block (the session's own name, which its Interlude shares: CF_S1 for CF_S1 and CF_I1;
                          the practice names before experiments, P, S1, ..., work the old way), kind ('session' or 'interlude'),
                          practice, started_at, ended_at, wall_s, duration_s (configured length; sessions only),
                          final_score (as logged), n_fruits, n_trials, n_correct, bonus (Interludes), frames, mean_frame_ms, max_frame_ms,
                          config and display (JSON text), and at the end experiment (the run's)
        events            the `events` table (payload as JSON text); the view `fruits` is its type = 'fruit' rows
        interlude_trials  the `interlude_trials` table, as in rundata.INTERLUDE_COLUMNS, plus run_id and session_index

A run is downloaded again only when it is new or its status, last upload or session count changed (`--all` downloads every run again).
A run the server no longer has (the participant tables were cleared) stays here with `on_server` = 0.

`load(exclude=("peter",))` returns the tables as DataFrames without the participants whose ID or signed name contains any of the
strings (case-insensitive); `Humans.trajectory(run_id, session_index)` reads one session's frames.
"""

import argparse
import base64
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import rundata
import server_admin
from world import PROJECT_ROOT

DATA_DIR = PROJECT_ROOT / "ForagingData"
DB_NAME = "humans.sqlite"
PAGE = 2000     # rows per query: the largest (trajectory chunks) is about 1 MB of JSON

RUNS_SQL = """
select r.run_id, r.participant_id, r.experiment, r.status, r.platform, r.build_commit, r.build_commits, r.build_dirty, r.unity_version, r.started_at, r.finished_at,
       (select prolific_pid from public.pid_registry p where p.participant_id = r.participant_id) as participant,
       (select signature from public.consents c where c.participant_id = r.participant_id order by consent_id desc limit 1) as signature,
       (select version from public.consents c where c.participant_id = r.participant_id order by consent_id desc limit 1) as consent_version,
       (select text from public.feedback f where f.run_id = r.run_id) as feedback,
       (select count(*) from public.sessions s where s.run_id = r.run_id) as n_sessions,
       greatest((select max(received_at) from public.events e where e.run_id = r.run_id),
                (select max(received_at) from public.trajectory t where t.run_id = r.run_id)) as last_event
from public.runs r order by r.started_at"""

TABLES = (   # name, select, order: one query per page, restricted to the runs being downloaded
    ("sessions", "select * from public.sessions", "run_id, session_index"),
    ("events", "select * from public.events", "run_id, session_index, seq"),
    ("trajectory", "select run_id, session_index, first_seq, encode(data, 'base64') as data from public.trajectory", "run_id, session_index, first_seq"),
    ("plans", "select * from public.interlude_plan", "run_id, session_index"),
    ("trials", "select * from public.interlude_trials", "run_id, session_index, seq"),
)

_TRIAL_TYPES = {c: "text" if c in rundata._TEXT else "integer" if c in rundata._INTEGER else "real" for c in rundata.INTERLUDE_COLUMNS}
SCHEMA = f"""
create table if not exists participants (run_id text primary key, participant text, signature text, consent_version text, status text,
    started_at text, finished_at text, minutes real, build_commit text, build_dirty integer, platform text, unity_version text,
    n_sessions integer, n_completed integer, feedback text, last_event text, on_server integer, participant_id text, experiment text);
create table if not exists sessions (run_id text, session_index integer, name text, block text, kind text, practice integer,
    world_seed integer, world_file text, started_at text, ended_at text, wall_s real, duration_s real, completed integer, final_score real,
    n_fruits integer, n_trials integer, n_correct integer, bonus real, frames integer, mean_frame_ms real, max_frame_ms real,
    config text, display text, experiment text, primary key (run_id, session_index));
create table if not exists events (run_id text, session_index integer, seq integer, t real, real real, type text, tree_id integer, k integer,
    reward real, running_total real, payload text, received_at text, primary key (run_id, session_index, seq));
create table if not exists interlude_trials (run_id text, session_index integer,
    {", ".join(f"{c} {t}" for c, t in _TRIAL_TYPES.items())}, primary key (run_id, session_index, seq));
create view if not exists fruits as
    select run_id, session_index, seq, t, tree_id, k, reward, running_total from events where type = 'fruit';
"""


def query(sql):
    """The rows (dicts) of a read-only query on the linked Supabase project, through the CLI."""
    cli = [shutil.which("supabase")] if shutil.which("supabase") else ["npx", "--yes", "supabase@latest"]
    done = subprocess.run(cli + ["db", "query", "--remote", "--read-only", "--output-format", "json", sql], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"supabase db query failed ({done.returncode}): {done.stderr.strip() or done.stdout.strip()}")
    return json.loads(done.stdout)["rows"]


def _fetch(select, order, run_ids):
    ids = ",".join(f"'{uuid.UUID(r)}'" for r in run_ids)      # ids come from the server; the parse makes sure nothing else is pasted in
    rows = []
    while True:
        page = query(f"{select} where run_id = any(array[{ids}]::uuid[]) order by {order} limit {PAGE} offset {len(rows)}")
        rows += page
        if len(page) < PAGE:
            return rows


def _utc(value):
    return pd.Timestamp(value).tz_convert("UTC").isoformat() if value else None


def _stamp(run):
    return (run["status"], _utc(run["finished_at"]), _utc(run["last_event"]), run["n_sessions"])


def _block(s, config):
    """The name a session and its Interlude share: the session's own (an Interlude names it in its config, `interludeFor`; the names before experiments end in _Interlude)."""
    if not s["is_interlude"]:
        return s["name"]
    return config.get("interludeFor") or s["name"].removesuffix("_Interlude")


def _add_missing_columns(con):
    """A humans.sqlite made before the experiments lacks the experiment columns: add them (the rows keep NULL there until downloaded again)."""
    for table, column in (("participants", "participant_id"), ("participants", "experiment"), ("sessions", "experiment")):
        if column not in {row[1] for row in con.execute(f"pragma table_info({table})")}:
            con.execute(f"alter table {table} add column {column} text")


def _session_row(s, events, trials, experiment=None):
    config, frames = s["config"] or {}, s["frame_stats"] or {}
    started, ended = _utc(s["started_at"]), _utc(s["ended_at"])
    interlude = bool(s["is_interlude"])
    return (s["run_id"], s["session_index"], s["name"], _block(s, config), "interlude" if interlude else "session",
            int(s["is_practice"]), s["world_seed"], s["world_file"], started, ended,
            (pd.Timestamp(ended) - pd.Timestamp(started)).total_seconds() if started and ended else None,
            None if interlude else config.get("sessionDuration"), int(s["completed"]), s["final_score"],
            sum(e["type"] == "fruit" for e in events),
            len(trials) if interlude else None, sum(t["choice_correct"] == 1 for t in trials) if interlude else None,
            sum(t["bonus"] or 0 for t in trials) if interlude else None,
            frames.get("count"), frames.get("meanMs"), frames.get("maxMs"),
            json.dumps(config, sort_keys=True), json.dumps(s["display"], sort_keys=True), experiment)


def _store_run(con, out, run, sessions, events, chunks, plans, trials):
    """Write one run as the local layout and replace its rows in the tidy tables."""
    run_id = run["run_id"]
    meta = {k: (_utc(v) if k in ("started_at", "finished_at") else v) for k, v in run.items() if k not in ("run_id", "last_event", "n_sessions")}
    rundata.write_run(out, run_id, meta)
    for table in ("sessions", "events", "interlude_trials"):
        con.execute(f"delete from {table} where run_id = ?", (run_id,))
    columns = rundata.INTERLUDE_COLUMNS
    for s in sessions:
        index = s["session_index"]
        ev = events[index]
        server_admin.write_session_rows(out, run_id, s, ev, [dict(c, data=base64.b64decode(c["data"])) for c in chunks[index]],
                                        plans.get(index), trials[index])
        con.execute("insert into sessions values (" + ",".join("?" * 24) + ")", _session_row(s, ev, trials[index], run.get("experiment")))
        con.executemany("insert into events values (?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(run_id, index, e["seq"], e["t"], e["real"], e["type"], e["tree_id"], e["k"], e["reward"], e["running_total"],
                          json.dumps(e["payload"], sort_keys=True) if e["payload"] else None, _utc(e["received_at"])) for e in ev])
        con.executemany(f"insert into interlude_trials values (?,?,{','.join('?' * len(columns))})",
                        [(run_id, index) + tuple(t[c] for c in columns) for t in trials[index]])
    server_admin.archive_worlds(run["build_commit"], sessions, out)
    minutes = ((pd.Timestamp(_utc(run["finished_at"])) - pd.Timestamp(_utc(run["started_at"]))).total_seconds() / 60) if run["finished_at"] else None
    con.execute("insert or replace into participants values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (run_id, run["participant"], run["signature"], run["consent_version"], run["status"], _utc(run["started_at"]),
                 _utc(run["finished_at"]), minutes, run["build_commit"], int(run["build_dirty"] or 0), run["platform"], run["unity_version"],
                 run["n_sessions"], sum(bool(s["completed"]) for s in sessions), run["feedback"], _utc(run["last_event"]),
                 run.get("participant_id"), run.get("experiment")))


def download(out=DATA_DIR, everything=False, log=print):
    """Download the runs that are new or changed since the last download into `out`; returns (runs downloaded, runs not on the server)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out / DB_NAME)
    con.executescript(SCHEMA)
    _add_missing_columns(con)
    runs = query(RUNS_SQL)
    have = {r[0]: r[1:] for r in con.execute("select run_id, status, finished_at, last_event, n_sessions from participants")}
    todo = [r for r in runs if everything or have.get(r["run_id"]) != _stamp(r) or not (out / r["run_id"]).is_dir()]
    if todo:
        ids = [r["run_id"] for r in todo]
        rows = {name: _fetch(select, order, ids) for name, select, order in TABLES}
        by_run = {name: defaultdict(lambda: defaultdict(list)) for name in ("events", "trajectory", "trials")}
        for name in by_run:
            for row in rows[name]:
                by_run[name][row["run_id"]][row["session_index"]].append(row)
        plans = defaultdict(dict)
        for row in rows["plans"]:
            plans[row["run_id"]][row["session_index"]] = row
        sessions = defaultdict(list)
        for row in rows["sessions"]:
            sessions[row["run_id"]].append(row)
        for run in todo:
            rid = run["run_id"]
            with con:
                _store_run(con, out, run, sessions[rid], by_run["events"][rid], by_run["trajectory"][rid], plans[rid], by_run["trials"][rid])
            log(f"  {rid[:8]}  {run['participant'] or '-':<14} {run['status']:<11} {run['n_sessions']} sessions")
    with con:
        con.execute("update participants set on_server = 0")
        con.executemany("update participants set on_server = 1 where run_id = ?", [(r["run_id"],) for r in runs])
    gone = con.execute("select count(*) from participants where on_server = 0").fetchone()[0]
    con.close()
    return len(todo), gone


@dataclass
class Humans:
    participants: pd.DataFrame
    sessions: pd.DataFrame
    events: pd.DataFrame
    fruits: pd.DataFrame
    interlude_trials: pd.DataFrame
    root: Path

    def trajectory(self, run_id, session_index):
        """The frames of one session (t, x, z, yaw, pitch, keys; the quantized values the server holds)."""
        return pd.read_csv(self.root / run_id / f"{session_index:02d}" / "trajectory.csv", usecols=list(rundata.TRAJECTORY_COLUMNS[1:]))


def load(root=DATA_DIR, exclude=(), status=None):
    """The downloaded tables as DataFrames. `exclude`: strings (case-insensitive); a participant whose ID or signed name contains one is
    left out of every table. `status`: keep only runs with this status ('finished')."""
    root = Path(root)
    if not (root / DB_NAME).exists():
        raise FileNotFoundError(f"{root / DB_NAME} does not exist: run `human_data.py download` first")
    con = sqlite3.connect(root / DB_NAME)
    people = pd.read_sql("select * from participants order by started_at", con)
    text = (people["participant"].fillna("") + "\n" + people["signature"].fillna("")).str.lower()
    keep = pd.Series(True, index=people.index)
    for s in exclude:
        keep &= ~text.str.contains(s.lower(), regex=False)
    if status is not None:
        keep &= people["status"] == status
    people = people[keep].reset_index(drop=True)
    for column in ("started_at", "finished_at"):
        people[column] = pd.to_datetime(people[column], utc=True)
    ids = list(people["run_id"])

    def table(name):
        df = pd.read_sql(f"select * from {name} where run_id in ({','.join('?' * len(ids))})", con, params=ids)
        return df

    sessions = table("sessions")
    for column in ("started_at", "ended_at"):
        sessions[column] = pd.to_datetime(sessions[column], utc=True)
    out = Humans(people, sessions, table("events"), table("fruits"), table("interlude_trials"), root)
    con.close()
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("download", help="download new or changed runs")
    d.add_argument("--out", default=str(DATA_DIR))
    d.add_argument("--all", action="store_true", help="download every run again")
    ls = sub.add_parser("list", help="list the downloaded participants")
    ls.add_argument("--out", default=str(DATA_DIR))
    ls.add_argument("--exclude", nargs="*", default=[], help="leave out participants whose ID or signed name contains any of these")
    ls.add_argument("--status")
    args = parser.parse_args(argv)
    if args.command == "download":
        print("downloading...")
        n, gone = download(args.out, args.all)
        print(f"{n} run(s) downloaded into {args.out}" + (f"; {gone} run(s) downloaded earlier are no longer on the server (kept)" if gone else ""))
        return
    h = load(args.out, args.exclude, args.status)
    p = h.participants.assign(date=h.participants["started_at"].dt.strftime("%m-%d %H:%M"), build=h.participants["build_commit"].str[:7])
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(p[["participant", "experiment", "signature", "status", "date", "minutes", "n_sessions", "n_completed", "build", "on_server"]].round(1).to_string())
    print(f"{len(p)} participant(s) shown" + (f", excluding '{', '.join(args.exclude)}'" if args.exclude else ""))


if __name__ == "__main__":
    sys.exit(main())
