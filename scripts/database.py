"""The one script for the online database: every operation that needs the database owner's connection string goes through here, and the database password is pasted at a hidden prompt each time.
It is held in this process's memory only: no environment variable, no file, nothing in the command line or the shell history, and the script refuses to run unless it has a terminal, so
nothing can pipe it in. It never prints the string (errors are scrubbed of it), shows the project it connects to, reads in a read-only transaction, and for a write prints what it will
do and asks you to type the project ref. Each run leaves `results/db_<operation>_<time>.log` (what was done, no secrets) for whoever you tell about it.

    ./venv/bin/python scripts/database.py publish --build Builds/web [--dry-run] [--completion-code FN=XXXX] [--note why]   # write: experiments, the build's world files, the release
    ./venv/bin/python scripts/database.py register-experiment --code CF --title "Complex Features" [--requires TUT] [--order 2] [--completion-code XXXX] [--payout '{"..."}']   # write
    ./venv/bin/python scripts/database.py register-release --commit <git hash> --experiment TUT --experiment CF [--note "..."]   # write
    ./venv/bin/python scripts/database.py register-worlds            # write: hashes Assets/StreamingAssets/Experiments/*/*
    ./venv/bin/python scripts/database.py runs                       # read
    ./venv/bin/python scripts/database.py pull --run <run_id> --out ForagingData   # read: one run as the local layout (participant data: ForagingData is gitignored)
    ./venv/bin/python scripts/database.py download [--out ForagingData] [--all]   # read: new or changed runs into ForagingData/<run>/ and humans.sqlite (human_data.py reads them)
    ./venv/bin/python scripts/database.py backup [--out ForagingData] [--label why]   # read: every table of `public` as JSON lines, before a migration
    ./venv/bin/python scripts/database.py describe --build Builds/web [--reason why]   # connects to nothing: the commit message of a build's deploy

    ./venv/bin/python scripts/database.py migrate                    # write: apply the files of supabase/migrations/ the database has not applied (all in one transaction), recorded in the CLI's own table; back up first
    ./venv/bin/python scripts/database.py cleanup --commit smoke-test   # write: the runs, participants and release the smoke and load tests left under a throwaway build name (a git hash is refused)
    ./venv/bin/python scripts/database.py set-secret --name FORAGING_POOLER_URL   # asks the Supabase access token, then the database password (the transaction-pooler string is built from it); no database connection
    ./venv/bin/python scripts/database.py set-secret --name ALLOWED_ORIGIN         # asks the token, then the value
    ./venv/bin/python scripts/database.py deploy-functions           # the Supabase CLI as a child process with the token in its environment only; no database connection

`set-secret` and `deploy-functions` use the Supabase access token (Account > Access Tokens), pasted at a hidden prompt the same way as the password; the secret value goes to the Management API in
the request body, never in argv or a file. Secrets reach the functions on their next start; redeploy only after a change of code.
"""

import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
import sys
from contextlib import contextmanager
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


def build_description(build_dir, reason=None, repo=PROJECT_ROOT, now=None, commit=None):
    """(subject, body) describing a WebGL build, for the deploy commit in the Pages repository (`deploy_webgl.sh`) and for the release's note (`publish`): its kind,
    the commit of this repository it was made from (and whether the tree was dirty), its size and what it holds. The Pages repository keeps only its latest commit, so
    the registered release is where the record of each deploy lives. `reason` is a free line: what this deploy is for."""
    build_dir = Path(build_dir)
    plan = build_plan(build_dir, commit, repo=repo)
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


# --------------------------------------------------------------------------------------------------
# The connection: pasted, checked, scrubbed, logged
# --------------------------------------------------------------------------------------------------

ONLINE_JSON = PROJECT_ROOT / "Assets" / "StreamingAssets" / "online.json"
LOG_DIR = PROJECT_ROOT / "results"
WRITES = {"publish", "register-experiment", "register-release", "register-worlds", "cleanup", "migrate"}      # the operations that change the database
TOKEN_OPERATIONS = {"set-secret", "deploy-functions"}        # no database connection: they use the Supabase access token, pasted the same way


def expected_ref(path=ONLINE_JSON):
    """The project ref the game's online.json points at (https://<ref>.supabase.co/...): the project this script is meant to reach."""
    return (urllib.parse.urlparse(json.loads(Path(path).read_text())["url"]).hostname or "").split(".")[0]


def project_ref(url):
    """The Supabase project ref a connection string names: the user of a pooler string (postgres.<ref>) or the host of a direct one (db.<ref>.supabase.co); None for any other form."""
    parts = urllib.parse.urlparse(url)
    user = urllib.parse.unquote(parts.username or "")
    if "." in user:
        return user.split(".", 1)[1]
    found = re.fullmatch(r"db\.([a-z0-9]+)\.supabase\.co", parts.hostname or "")
    return found.group(1) if found else None


def secrets_of(url):
    """What must never appear in output: the string and its password (as typed and as decoded)."""
    password = urllib.parse.urlparse(url).password or ""
    return [s for s in (url, password, urllib.parse.unquote(password)) if s]


def scrub(text, *secrets):
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


def require_terminal(stdin=None, stdout=None):
    """The secret is typed at a terminal: refuse to run with input from a pipe or a file, or with output that goes elsewhere (so nothing can feed it in and no log can hold the prompt)."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    if not (stdin.isatty() and stdout.isatty()):
        raise SystemExit("database.py needs a terminal: run it yourself and paste the secret at the hidden prompt")


POOLER_HOST = "aws-1-us-west-2.pooler.supabase.com"      # the project's session pooler (Connect > Session pooler; supabase/.temp/pooler-url): not a secret
POOLER_PORT = 5432


def url_from_password(password, ref, host=POOLER_HOST, port=POOLER_PORT):
    """The connection string of project `ref` for a database password (any characters: it is percent-encoded). A pasted string that is already a full URL is kept."""
    if "://" in password:
        return password
    return f"postgresql://postgres.{ref}:{urllib.parse.quote(password, safe='')}@{host}:{port}/postgres"


def ask_secret(prompt="Database password (Supabase: Database settings; input hidden): "):
    require_terminal()
    value = getpass.getpass(prompt).strip()
    if not value:
        raise SystemExit("nothing entered")
    return value


def connect(url, expected=None):
    """(connection, project ref) for the pasted string. Refuses a string for another project than `expected` (online.json's); a form that names no project is accepted and reported as `expected`.
    Autocommit, no server-side prepared statements (the pooler hands queries to different server connections); a failure is reported without the string."""
    ref = project_ref(url)
    if ref is not None and expected and ref != expected:
        raise SystemExit(f"the connection string is for project {ref}, but online.json points at {expected}: stopped")
    import psycopg
    try:
        conn = psycopg.connect(url, row_factory=psycopg.rows.dict_row, autocommit=True, prepare_threshold=None, connect_timeout=20)
    except Exception as e:
        raise SystemExit("could not connect: " + scrub(str(e), *secrets_of(url)))
    return conn, ref or expected


@contextmanager
def read_only(conn):
    """One transaction in which nothing can be written (the server refuses it): what every read operation runs in."""
    with conn.transaction():
        conn.execute("set transaction read only")
        yield


def confirm_write(ref, ask=input):
    """A write names the project and waits for its ref to be typed."""
    if ask(f"This writes to project {ref}. Type the project ref to go on: ").strip() != ref:
        raise SystemExit("stopped, nothing written")


class Log:
    """Prints what an operation reports and keeps it (scrubbed) for `results/db_<operation>_<time>.log`, which holds the operation, the project, the outcome and no secrets."""

    def __init__(self, operation, argv, directory=LOG_DIR, now=None):
        self.operation, self.argv, self.directory, self.lines, self.secrets, self.project = operation, list(argv), Path(directory), [], [], None
        self.started = now or datetime.now(timezone.utc)

    def __call__(self, *parts):
        text = scrub(" ".join(str(p) for p in parts), *self.secrets)
        print(text)
        self.lines.append(text)

    def save(self, outcome):
        self.directory.mkdir(exist_ok=True)
        path = self.directory / f"db_{self.operation}_{self.started.strftime('%Y%m%d-%H%M%S')}.log"
        header = [f"operation: {self.operation}", f"arguments: {' '.join(self.argv)}", f"project: {self.project}", f"started: {self.started.isoformat()}", f"outcome: {outcome}", ""]
        path.write_text(scrub("\n".join(header + self.lines), *self.secrets) + "\n")
        return path


def make_query(conn):
    """`query(sql)`: the rows of a read query as dicts of JSON values (timestamps and ids as text, as `to_jsonb` gives them), what `human_data.download` and `backup` read."""
    return lambda sql: [r["r"] for r in conn.execute(f"select to_jsonb(q) as r from ({sql}) q").fetchall()]


BACKUP_PAGE = 1000


def backup(query, out, label="legacy", log=print):
    """A local copy of every table of `public` under `<out>/_db_backup_<label>_<UTC time>/` (gitignored: it holds participant names), cut in primary-key order, so run it while no one is playing:
    `<table>.jsonl` (one JSON object per row; a bytea column is its hex text), `schema.json` (tables, columns, the migrations applied) and `counts.json` (rows per table, for checking the copy).
    It takes the tables as it finds them, so it works before and after a migration. To restore a table, insert its rows with `jsonb_populate_recordset`."""
    folder = Path(out) / f"_db_backup_{label}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    folder.mkdir(parents=True)
    tables = [r["table_name"] for r in query("select table_name from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE' order by table_name")]
    columns = query("select table_name, column_name, data_type, is_nullable, ordinal_position from information_schema.columns where table_schema = 'public' order by table_name, ordinal_position")
    has_migrations = query("select to_regclass('supabase_migrations.schema_migrations') is not null as found")[0]["found"]
    migrations = query("select version, name from supabase_migrations.schema_migrations order by version") if has_migrations else []
    (folder / "schema.json").write_text(json.dumps({"tables": tables, "columns": columns, "migrations": migrations}, indent=1, default=str))
    keys = {}
    for r in query("select tc.table_name, kcu.column_name from information_schema.table_constraints tc join information_schema.key_column_usage kcu "
                   "on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema "
                   "where tc.table_schema = 'public' and tc.constraint_type = 'PRIMARY KEY' order by tc.table_name, kcu.ordinal_position"):
        keys.setdefault(r["table_name"], []).append(f'"{r["column_name"]}"')
    counts = {}
    for table in tables:
        n, order = 0, ", ".join(keys.get(table, ["ctid"]))
        with open(folder / f"{table}.jsonl", "w") as f:
            while True:
                rows = query(f'select * from public."{table}" order by {order} limit {BACKUP_PAGE} offset {n}')
                f.writelines(json.dumps(row, default=str) + "\n" for row in rows)
                n += len(rows)
                if len(rows) < BACKUP_PAGE:
                    break
        counts[table] = n
        log(f"  {table}: {n} rows")
    (folder / "counts.json").write_text(json.dumps(counts, indent=1))
    return folder, counts


MIGRATIONS = PROJECT_ROOT / "supabase" / "migrations"
POOLER_TRANSACTION_PORT = 6543          # what the Edge Functions connect through (FORAGING_POOLER_URL)
API = "https://api.supabase.com/v1"
SECRET_NAME = re.compile(r"[A-Z][A-Z0-9_]*")


def migration_files(directory=MIGRATIONS):
    """[(version, name, path)] of the migration files in order: `<version>_<name>.sql`, as the Supabase CLI numbers them."""
    return [(p.name.split("_", 1)[0], p.stem.split("_", 1)[1], p) for p in sorted(Path(directory).glob("*.sql"))]


def pending_migrations(conn, directory=MIGRATIONS):
    """(the files the database has not applied, versions the database has that no file has). The record is the CLI's own table, supabase_migrations.schema_migrations."""
    found = conn.execute("select to_regclass('supabase_migrations.schema_migrations') is not null as found").fetchone()["found"]
    applied = {r["version"] for r in conn.execute("select version from supabase_migrations.schema_migrations")} if found else set()
    local = migration_files(directory)
    return [m for m in local if m[0] not in applied], sorted(applied - {m[0] for m in local})


def apply_migrations(conn, pending, log):
    """Apply the files in order and record each where the CLI does (its `statements` hold the file as one text); inside the caller's transaction, so a failure leaves nothing applied."""
    conn.execute("create schema if not exists supabase_migrations")
    conn.execute("create table if not exists supabase_migrations.schema_migrations (version text not null primary key, statements text[], name text)")
    for version, name, path in pending:
        sql = path.read_text()
        conn.execute(sql)
        conn.execute("insert into supabase_migrations.schema_migrations (version, statements, name) values (%s, %s, %s)", (version, [sql], name))
        log("applied", path.name)


def throwaway_rows(conn, commit):
    """What the smoke and load tests left under a throwaway build name: (run ids, participant ids). A real build's commit (a git hash) is refused."""
    if re.fullmatch(r"[0-9a-f]{7,40}", commit):
        raise SystemExit(f"{commit} looks like a git commit: cleanup is only for the throwaway names of the smoke and load tests (smoke-test, load-test)")
    runs = conn.execute("select run_id, participant_id from public.runs where build_commit = %s", (commit,)).fetchall()
    people = {r["participant_id"] for r in runs}
    people |= {r["participant_id"] for r in conn.execute("select participant_id from public.pid_registry where prolific_pid like %s", (f"LOAD\\_{commit}\\_%",))}
    return [r["run_id"] for r in runs], sorted(people, key=str)


def cleanup(conn, commit, log):
    """Delete the throwaway build's runs (their sessions, events and trajectory go with them), its release, and the participants of those runs that have no other run."""
    runs, people = throwaway_rows(conn, commit)
    conn.execute("delete from public.runs where build_commit = %s", (commit,))
    conn.execute("delete from public.participants p where p.participant_id = any(%s) and not exists (select 1 from public.runs r where r.participant_id = p.participant_id)", (people,))
    released = conn.execute("delete from public.releases where build_commit = %s", (commit,)).rowcount
    log(f"deleted {len(runs)} run(s), the participants of {len(people)} id(s) without other runs, {released} release(s) of {commit}")


def preview(args, conn, log):
    """What a write is about to do, read first (read-only); False when there is nothing to do, so no confirmation is asked."""
    with read_only(conn):
        if args.command == "migrate":
            pending, unknown = pending_migrations(conn)
            for version in unknown:
                log("note: the database has migration", version, "that no file in supabase/migrations/ has")
            for _, _, path in pending:
                log("pending:", path.name)
            if pending:
                log("note: back up first (database.py backup); each file is applied in one transaction with the others, all or none")
            else:
                log("every migration is applied: nothing to do")
            return bool(pending)
        if args.command == "cleanup":
            runs, people = throwaway_rows(conn, args.commit)
            log(f"would delete {len(runs)} run(s) of build {args.commit}, up to {len(people)} participant(s), and its release")
    return True


def ask_token():
    require_terminal()
    value = getpass.getpass("Supabase access token (Account > Access Tokens; input hidden): ").strip()
    if not value.startswith("sbp_"):
        raise SystemExit("that is not a Supabase access token (they start with sbp_)")
    return value


def set_secret(token, ref, name, value, opener=urllib.request.urlopen):
    """Set one Edge Function secret through the Management API (the token goes in a header, nothing in argv or a file)."""
    if not SECRET_NAME.fullmatch(name) or name.startswith("SUPABASE_"):
        raise SystemExit(f"{name} is not a settable secret name (capitals, digits and underscores; SUPABASE_ is reserved)")
    request = urllib.request.Request(f"{API}/projects/{ref}/secrets", data=json.dumps([{"name": name, "value": value}]).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "foraging-database/1"})
    try:
        with opener(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as e:
        raise SystemExit(f"the API refused the secret ({e.code}): {scrub(e.read().decode(errors='replace')[:300], token, value)}")
    except urllib.error.URLError as e:
        raise SystemExit(f"could not reach the Supabase API: {scrub(str(e.reason), token, value)}")


def deploy_functions(token, ref, log, runner=subprocess.run):
    """Deploy supabase/functions with the Supabase CLI as a child process; the token is in the child's environment only (never argv), and the CLI's output is scrubbed of it."""
    cli = [shutil.which("supabase")] if shutil.which("supabase") else ["npx", "--yes", "supabase@latest"]
    env = os.environ.copy()
    env["SUPABASE_ACCESS_TOKEN"] = token
    names = sorted(p.parent.name for p in (PROJECT_ROOT / "supabase" / "functions").glob("*/index.ts"))      # the publishable key is not a JWT: --no-verify-jwt; --use-api bundles on Supabase's side (no Docker)
    done = runner(cli + ["functions", "deploy", *names, "--no-verify-jwt", "--use-api", "--project-ref", ref], cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=900)
    for line in (done.stdout + done.stderr).splitlines():
        log(line)
    if done.returncode != 0:
        raise SystemExit(f"supabase functions deploy failed ({done.returncode})")


def token_operation(args, log, ask, ref, token=None, value=None, opener=urllib.request.urlopen, runner=subprocess.run):
    """`set-secret` and `deploy-functions`: no database connection, the access token pasted at a hidden prompt, the project confirmed by typing its ref.
    `FORAGING_POOLER_URL` is built from the database password (as `url_from_password`, on the transaction pooler's port), anything else is asked as a value."""
    log.project = ref
    log(f"project {ref}")
    token = (token or ask_token)()
    log.secrets.append(token)
    if args.command == "set-secret":
        if args.name == "FORAGING_POOLER_URL":
            secret = url_from_password((value or ask_secret)(), ref, port=POOLER_TRANSACTION_PORT)
            log.secrets += secrets_of(secret)
        else:
            secret = (value or (lambda: ask_secret(f"Value of {args.name} (input hidden): ")))()
            log.secrets.append(secret)
        confirm_write(ref, ask)
        set_secret(token, ref, args.name, secret, opener)
        log(f"secret {args.name} set on project {ref}")
    else:
        confirm_write(ref, ask)
        deploy_functions(token, ref, log, runner)
        log(f"functions deployed to project {ref}")


def build_parser():
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
    dl = sub.add_parser("download", help="new or changed runs into ForagingData/<run>/ and humans.sqlite")
    dl.add_argument("--out", default="ForagingData")
    dl.add_argument("--all", action="store_true", help="download every run again")
    b = sub.add_parser("backup", help="every table of public as JSON lines")
    b.add_argument("--out", default="ForagingData")
    b.add_argument("--label", default="manual")
    c = sub.add_parser("cleanup", help="delete what the smoke and load tests left under a throwaway build name")
    c.add_argument("--commit", required=True, help="the throwaway build name (smoke-test, load-test); a git hash is refused")
    sub.add_parser("migrate", help="apply the migration files the database has not applied, in one transaction")
    sc = sub.add_parser("set-secret", help="set an Edge Function secret (Supabase access token pasted; no database connection)")
    sc.add_argument("--name", required=True, help="FORAGING_POOLER_URL (asks the database password and builds the transaction-pooler string) or another secret (asks its value)")
    sub.add_parser("deploy-functions", help="deploy supabase/functions with the Supabase CLI (access token pasted; no database connection)")
    p = sub.add_parser("pull")
    p.add_argument("--run", required=True)
    p.add_argument("--out", default="ForagingData")
    return parser


def run_operation(args, conn, log, plan=None):
    """One operation on an open connection, in a read-only transaction or, for a write, in one transaction (all of it or none)."""
    if args.command in WRITES:
        with conn.transaction():
            if args.command == "publish":
                codes = dict(item.split("=", 1) for item in args.completion_code)
                note = release_note(build_description(args.build, commit=args.commit)[0], args.note) if args.build else args.note
                for line in publish(conn, plan, codes, note):
                    log("registered", line)
            elif args.command == "register-experiment":
                register_experiment(conn, args.code, args.title, args.requires, args.order, args.completion_code, json.loads(args.payout) if args.payout else None)
                log(f"registered {args.code}: {args.title}")
            elif args.command == "register-release":
                experiments = {code: sessions_in_build(args.commit, code) for code in args.experiment}
                register_release(conn, args.commit, experiments, args.note)
                log(f"registered {args.commit} with {experiments}")
            elif args.command == "cleanup":
                cleanup(conn, args.commit, log)
            elif args.command == "migrate":
                apply_migrations(conn, pending_migrations(conn)[0], log)
            else:
                names = register_worlds(conn)
                log(f"registered {len(names)} files: {', '.join(names)}")
        return
    with read_only(conn):
        if args.command == "runs":
            for run in conn.execute("select r.run_id, r.experiment, r.status, r.started_at, r.build_commit, r.build_dirty, count(s.*) as sessions "
                                    "from public.runs r left join public.sessions s using (run_id) group by r.run_id order by r.started_at").fetchall():
                log(json.dumps({k: _iso(v) if not isinstance(v, (int, bool, type(None))) else v for k, v in run.items()}, default=str))
        elif args.command == "download":
            import human_data
            n, gone = human_data.download(make_query(conn), args.out, args.all)      # progress names participants: terminal only, not the log
            log(f"{n} run(s) downloaded into {args.out}" + (f"; {gone} run(s) downloaded earlier are no longer on the server (kept)" if gone else ""))
        elif args.command == "backup":
            folder, counts = backup(make_query(conn), args.out, args.label, log)
            log(f"{sum(counts.values())} rows in {len(counts)} tables written to {folder}")
        else:
            log("pulled into", pull_run(conn, args.run, args.out))


def main(argv=None, secret=None, ask=input, expected=None, log_dir=LOG_DIR, token=None, value=None, opener=urllib.request.urlopen, runner=subprocess.run):
    """`secret` (default: the hidden prompt for the database password), `ask` (the confirmation), `expected` (the project ref), `token` and `value` (the access token and a secret's value
    for `set-secret`), `opener` (the API) and `runner` (the CLI) are replaced by the tests."""
    args = build_parser().parse_args(argv)
    if args.command == "describe":
        subject, body = build_description(args.build, args.reason)
        print(subject + "\n\n" + body)
        return
    log = Log(args.command, sys.argv[1:] if argv is None else argv, log_dir)
    plan = None
    if args.command == "publish":
        plan = build_plan(args.build, args.commit)
        log(f"commit {plan['commit']}; experiments {[(e['code'], e['order']) for e in plan['experiments']]}; sessions {plan['sessions']}; files from {plan['worlds']}")
        for line in plan["notes"]:
            log("note:", line)
        if args.dry_run:
            log("dry run: nothing connected, nothing written")
            return
    wanted = expected_ref() if expected is None else expected
    conn = None
    outcome = "failed"
    try:
        if args.command in TOKEN_OPERATIONS:
            token_operation(args, log, ask, wanted, token, value or secret, opener, runner)
        else:
            url = url_from_password((secret or ask_secret)(), wanted)
            log.secrets = secrets_of(url)
            conn, ref = connect(url, wanted)
            log.project = ref
            log(f"project {ref}")
            if args.command not in WRITES or preview(args, conn, log):
                if args.command in WRITES:
                    confirm_write(ref, ask)
                run_operation(args, conn, log, plan)
        outcome = "done"
    except SystemExit as e:
        outcome = f"stopped: {e}"
        raise
    except Exception as e:
        outcome = f"failed: {scrub(str(e), *log.secrets)}"
        raise SystemExit(f"{args.command} failed: {scrub(str(e), *log.secrets)}")
    finally:
        if conn is not None:
            conn.close()
        print("log:", log.save(outcome))


if __name__ == "__main__":
    main()
