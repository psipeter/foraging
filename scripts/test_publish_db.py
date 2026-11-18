"""`database.publish` against a real PostgreSQL (pgserver) with the project's migrations; no Deno or Edge Functions needed."""

import glob
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
    (tmp_path / "FOR").mkdir()
    (tmp_path / "FOR" / "x_seed1.world").write_bytes(b"world bytes")
    first = database.publish(db, plan, {"FOR": "KEEP-ME"})
    assert any("release" in line for line in first) and any(line.startswith("1 world") for line in first)
    row = db.execute("select title, requires, sort_order, completion_code from public.experiments where code = 'FOR'").fetchone()
    assert row["title"] == next(e["title"] for e in plan["experiments"] if e["code"] == "FOR") and row["requires"] == ["TUT"] and row["completion_code"] == "KEEP-ME"
    database.publish(db, plan)                                                        # again, no code given: the registered one stays
    assert db.execute("select completion_code from public.experiments where code = 'FOR'").fetchone()["completion_code"] == "KEEP-ME"
    offered = {r["experiment"]: r["n_sessions"] for r in db.execute("select experiment, n_sessions from public.release_experiments where build_commit = %s", (plan["commit"],))}
    assert offered == plan["sessions"]
    assert db.execute("select count(*) as n from public.worlds where name = 'x_seed1.world'").fetchone()["n"] == 1
    database.register_experiment(db, "FOR", "Foraging in Tiles", ["TUT"], 2, "NEW-CODE")  # a code given later replaces it
    assert db.execute("select completion_code from public.experiments where code = 'FOR'").fetchone()["completion_code"] == "NEW-CODE"


def test_a_read_only_operation_cannot_write(db):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with database.read_only(db):
            db.execute("insert into public.experiments (code, title) values ('NOPE', 'x')")
    assert db.execute("select count(*) as n from public.experiments where code = 'NOPE'").fetchone()["n"] == 0


def run_main(argv, uri, tmp_path, answer):
    database.main(argv, secret=lambda: uri, ask=lambda prompt: answer, expected="local", log_dir=tmp_path)
    return sorted(tmp_path.glob("db_*.log"))


def test_a_write_through_main_needs_the_typed_ref_registers_in_one_transaction_and_leaves_a_log_without_the_secret(uri, db, tmp_path):
    with pytest.raises(SystemExit, match="nothing written"):
        run_main(["register-experiment", "--code", "ZZ", "--title", "Zed"], uri, tmp_path, "no")
    assert db.execute("select count(*) as n from public.experiments where code = 'ZZ'").fetchone()["n"] == 0
    logs = run_main(["register-experiment", "--code", "ZZ", "--title", "Zed"], uri, tmp_path, "local")
    assert db.execute("select title from public.experiments where code = 'ZZ'").fetchone()["title"] == "Zed"
    text = logs[-1].read_text()
    assert "outcome: done" in text and "registered ZZ: Zed" in text and "project: local" in text and uri not in text
    password = psycopg.conninfo.conninfo_to_dict(uri).get("password")
    assert not password or password not in text


def test_a_failed_write_changes_nothing_and_a_read_runs_in_a_read_only_transaction(uri, db, tmp_path):
    with pytest.raises(SystemExit, match="requires NOPE"):
        run_main(["register-experiment", "--code", "YY", "--title", "Why", "--requires", "NOPE"], uri, tmp_path, "local")
    assert db.execute("select count(*) as n from public.experiments where code = 'YY'").fetchone()["n"] == 0
    assert "outcome: failed" in sorted(tmp_path.glob("db_*.log"))[-1].read_text()
    logs = run_main(["runs"], uri, tmp_path, "unused")                                  # a read asks for no confirmation
    assert "outcome: done" in logs[-1].read_text()
