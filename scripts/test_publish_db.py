"""`database.publish` against a real PostgreSQL (pgserver) with the project's migrations; no Deno or Edge Functions needed."""

import glob
import json
import urllib.parse
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

import database

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def uri(tmp_path_factory):
    pg = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="delete")
    with psycopg.connect(pg.get_uri(), autocommit=True) as c:
        for role in ("anon", "authenticated"):
            c.execute(f"create role {role} nologin")
        for f in sorted(glob.glob(str(ROOT / "supabase" / "migrations" / "*.sql"))):
            c.execute(Path(f).read_text())
    return pg.get_uri()


@pytest.fixture(scope="module")
def db(uri):
    conn = psycopg.connect(uri, autocommit=True, row_factory=psycopg.rows.dict_row)
    yield conn
    conn.close()


def test_publish_registers_experiments_files_and_release_and_can_be_repeated_without_losing_a_completion_code(db, tmp_path):
    plan = {**database.build_plan(None, "HEAD"), "worlds": tmp_path}                 # the catalog of this repository, at HEAD
    (tmp_path / "PCX").mkdir()
    (tmp_path / "PCX" / "x_seed1.world").write_bytes(b"world bytes")
    first = database.publish(db, plan, {"PCX": "KEEP-ME"})
    assert any("release" in line for line in first) and any(line.startswith("1 world") for line in first)
    row = db.execute("select title, requires, sort_order, completion_code from public.experiments where code = 'PCX'").fetchone()
    assert row["title"] == next(e["title"] for e in plan["experiments"] if e["code"] == "PCX") and row["requires"] == ["TUT"] and row["completion_code"] == "KEEP-ME"
    database.publish(db, plan)                                                        # again, no code given: the registered one stays
    assert db.execute("select completion_code from public.experiments where code = 'PCX'").fetchone()["completion_code"] == "KEEP-ME"
    offered = {r["experiment"]: r["n_sessions"] for r in db.execute("select experiment, n_sessions from public.release_experiments where build_commit = %s", (plan["commit"],))}
    assert offered == plan["sessions"]
    assert db.execute("select count(*) as n from public.worlds where name = 'x_seed1.world'").fetchone()["n"] == 1
    database.register_experiment(db, "PCX", "Pilot: Complexity", ["TUT"], 2, "NEW-CODE")  # a code given later replaces it
    assert db.execute("select completion_code from public.experiments where code = 'PCX'").fetchone()["completion_code"] == "NEW-CODE"


def test_a_read_only_operation_cannot_write(db):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with database.read_only(db):
            db.execute("insert into public.experiments (code, title) values ('NOPE', 'x')")
    assert db.execute("select count(*) as n from public.experiments where code = 'NOPE'").fetchone()["n"] == 0


def run_main(argv, uri, tmp_path):
    database.main(argv, secret=lambda: uri, expected="local", log_dir=tmp_path)
    return sorted(tmp_path.glob("db_*.log"))


def test_a_write_through_main_registers_in_one_transaction_and_leaves_a_log_without_the_secret(uri, db, tmp_path):
    logs = run_main(["register-experiment", "--code", "ZZ", "--title", "Zed"], uri, tmp_path)
    assert db.execute("select title from public.experiments where code = 'ZZ'").fetchone()["title"] == "Zed"
    text = logs[-1].read_text()
    assert "outcome: done" in text and "registered ZZ: Zed" in text and "project: local" in text and uri not in text
    password = psycopg.conninfo.conninfo_to_dict(uri).get("password")
    assert not password or password not in text


def test_a_failed_write_changes_nothing_and_a_read_runs_in_a_read_only_transaction(uri, db, tmp_path):
    with pytest.raises(SystemExit, match="requires NOPE"):
        run_main(["register-experiment", "--code", "YY", "--title", "Why", "--requires", "NOPE"], uri, tmp_path)
    assert db.execute("select count(*) as n from public.experiments where code = 'YY'").fetchone()["n"] == 0
    assert "outcome: failed" in sorted(tmp_path.glob("db_*.log"))[-1].read_text()
    logs = run_main(["runs"], uri, tmp_path)                                  # a read asks for no confirmation
    assert "outcome: done" in logs[-1].read_text()


def test_backup_copies_every_table_with_its_counts_and_download_reads_a_database_without_runs(uri, db, tmp_path):
    out = tmp_path / "data"
    out.mkdir()
    run_main(["backup", "--out", str(out), "--label", "t"], uri, tmp_path)
    folder = next(out.glob("_db_backup_t_*"))
    counts = json.loads((folder / "counts.json").read_text())
    assert counts["experiments"] == db.execute("select count(*) as n from public.experiments").fetchone()["n"] > 0
    assert len((folder / "experiments.jsonl").read_text().splitlines()) == counts["experiments"]
    assert "experiments" in json.loads((folder / "schema.json").read_text())["tables"]
    logs = run_main(["download", "--out", str(out)], uri, tmp_path)
    assert "0 run(s) downloaded" in logs[-1].read_text() and (out / "humans.sqlite").exists()


def _insert(db, table, **given):
    """A row with `given` columns and a dummy value for every other required column."""
    dummy = {"uuid": lambda: str(uuid.uuid4()), "text": "x", "integer": 0, "bigint": 0, "boolean": False, "jsonb": "{}", "bytea": b"ab", "double precision": 0.0,
             "timestamp with time zone": "2026-11-18T10:00:00Z"}
    row = dict(given)
    for c in db.execute("select column_name, data_type from information_schema.columns where table_schema = 'public' and table_name = %s and is_nullable = 'NO' and column_default is null", (table,)):
        if c["column_name"] not in row:
            d = dummy[c["data_type"]]
            row[c["column_name"]] = d() if callable(d) else d
    db.execute(f"insert into public.{table} ({', '.join(row)}) values ({', '.join(['%s'] * len(row))})", [psycopg.types.json.Jsonb(v) if isinstance(v, dict) else v for v in row.values()])


def test_download_reads_a_run_with_its_session_events_and_trajectory_from_the_database(db, tmp_path):
    import numpy as np
    import human_data
    import trajectory_codec as codec
    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute("insert into public.experiments (code, title) values ('DL', 'Download test') on conflict do nothing")
    _insert(db, "participants", participant_id=pid)
    _insert(db, "runs", run_id=rid, participant_id=pid, experiment="DL")
    _insert(db, "sessions", run_id=rid, session_index=0)
    _insert(db, "events", run_id=rid, session_index=0, seq=0, type="fruit")
    _insert(db, "trajectory", run_id=rid, session_index=0, first_seq=0, n_frames=5, data=codec.encode(np.column_stack([np.arange(1, 6) * 0.1] + [np.zeros(5)] * 5), 0))
    with database.read_only(db):
        assert human_data.download(database.make_query(db), tmp_path, log=lambda *_: None) == (1, 0)
    h = human_data.load(tmp_path)
    assert rid in set(h.participants["run_id"]) and len(h.events[h.events.run_id == rid]) == 1 and len(h.trajectory(rid, 0)) == 5


@pytest.fixture
def fresh_uri(uri):
    """An empty database in the same server (the roles exist cluster-wide), where no migration is applied or recorded."""
    name = "fresh_" + uuid.uuid4().hex[:8]
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute(f"create database {name}")
    parts = urllib.parse.urlsplit(uri)
    return urllib.parse.urlunsplit(parts._replace(path="/" + name))


def test_migrate_applies_every_file_in_one_transaction_records_them_and_then_has_nothing_to_do(fresh_uri, tmp_path):
    logs = run_main(["migrate"], fresh_uri, tmp_path)
    text = logs[-1].read_text()
    files = [p.name for _, _, p in database.migration_files()]
    assert "outcome: done" in text and all(f"applied {f}" in text for f in files)
    with psycopg.connect(fresh_uri, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
        recorded = c.execute("select version, name from supabase_migrations.schema_migrations order by version").fetchall()
        assert [r["version"] for r in recorded] == [f.split("_")[0] for f in files] and recorded[0]["name"] == files[0].split("_", 1)[1][:-4]
        assert c.execute("select to_regclass('public.runs') is not null as found").fetchone()["found"]
    again = run_main(["migrate"], fresh_uri, tmp_path / "again")     # nothing pending: no confirmation
    assert "every migration is applied" in again[-1].read_text()


def test_a_failing_migration_leaves_nothing_applied(fresh_uri, tmp_path, monkeypatch):
    original_pending = database.pending_migrations
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "20990101000000_good.sql").write_text("create table public.zz_good (a int);")
    (tmp_path / "m" / "20990101000100_bad.sql").write_text("select no_such_column from public.zz_good;")
    monkeypatch.setattr(database, "MIGRATIONS", tmp_path / "m")
    monkeypatch.setattr(database, "pending_migrations", lambda conn, directory=tmp_path / "m": original_pending(conn, directory))
    with pytest.raises(SystemExit, match="migrate failed"):
        run_main(["migrate"], fresh_uri, tmp_path)
    with psycopg.connect(fresh_uri, autocommit=True) as c:
        assert c.execute("select to_regclass('public.zz_good')").fetchone()[0] is None
        assert c.execute("select to_regclass('supabase_migrations.schema_migrations')").fetchone()[0] is None


def test_cleanup_deletes_a_throwaway_builds_runs_participants_and_release_and_nothing_else(uri, db, tmp_path):
    db.execute("insert into public.experiments (code, title) values ('CL', 'Cleanup test') on conflict do nothing")
    database.register_release(db, "smoke-test", {"CL": 1}, None)
    database.register_release(db, "keep-me", {"CL": 1}, None)
    for commit in ("smoke-test", "keep-me"):
        pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        _insert(db, "participants", participant_id=pid)
        _insert(db, "runs", run_id=rid, participant_id=pid, experiment="CL", build_commit=commit)
        _insert(db, "sessions", run_id=rid, session_index=0)
    with pytest.raises(SystemExit, match="git commit"):
        run_main(["cleanup", "--commit", "22f16b46f042459260ad70ceca206e60171d197e"], uri, tmp_path)
    run_main(["cleanup", "--commit", "smoke-test"], uri, tmp_path)
    left = {r["build_commit"] for r in db.execute("select build_commit from public.runs where experiment = 'CL'")}
    assert left == {"keep-me"} and db.execute("select count(*) as n from public.releases where build_commit = 'smoke-test'").fetchone()["n"] == 0
    assert db.execute("select count(*) as n from public.releases where build_commit = 'keep-me'").fetchone()["n"] == 1


def test_clear_runs_deletes_older_runs_and_their_participants_and_keeps_the_rest(uri, db, tmp_path):
    db.execute("insert into public.experiments (code, title) values ('CR', 'Clear test') on conflict do nothing")
    database.register_release(db, "clear-build", {"CR": 1}, None)
    ids = {}
    for label, when in (("old", "2026-11-01T00:00:00Z"), ("new", "2026-11-21T00:00:00Z")):
        pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        _insert(db, "participants", participant_id=pid, created_at=when)
        _insert(db, "runs", run_id=rid, participant_id=pid, experiment="CR", build_commit="clear-build", started_at=when)
        _insert(db, "sessions", run_id=rid, session_index=0)
        ids[label] = (pid, rid)
    run_main(["clear-runs", "--before", "2026-11-20T00:00:00Z"], uri, tmp_path)
    runs = {str(r["run_id"]) for r in db.execute("select run_id from public.runs where experiment = 'CR'")}
    people = {str(r["participant_id"]) for r in db.execute("select participant_id from public.participants")}
    assert runs == {ids["new"][1]} and ids["new"][0] in people and ids["old"][0] not in people
    assert db.execute("select count(*) as n from public.sessions where run_id = %s", (ids["old"][1],)).fetchone()["n"] == 0
    assert db.execute("select count(*) as n from public.releases where build_commit = 'clear-build'").fetchone()["n"] == 1
