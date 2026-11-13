"""`server_admin.publish` against a real PostgreSQL (pgserver) with the project's migrations; no Deno or Edge Functions needed."""

import glob
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

import server_admin

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    pg = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="delete")
    with psycopg.connect(pg.get_uri(), autocommit=True) as c:
        for role in ("anon", "authenticated"):
            c.execute(f"create role {role} nologin")
        for f in sorted(glob.glob(str(ROOT / "supabase" / "migrations" / "*.sql"))):
            c.execute(Path(f).read_text())
    conn = psycopg.connect(pg.get_uri(), autocommit=True, row_factory=psycopg.rows.dict_row)
    yield conn
    conn.close()


def test_publish_registers_experiments_files_and_release_and_can_be_repeated_without_losing_a_completion_code(db, tmp_path):
    plan = {**server_admin.build_plan(None, "HEAD"), "worlds": tmp_path}                 # the catalog of this repository, at HEAD
    (tmp_path / "FOR").mkdir()
    (tmp_path / "FOR" / "x_seed1.world").write_bytes(b"world bytes")
    first = server_admin.publish(db, plan, {"FOR": "KEEP-ME"})
    assert any("release" in line for line in first) and any(line.startswith("1 world") for line in first)
    row = db.execute("select title, requires, sort_order, completion_code from public.experiments where code = 'FOR'").fetchone()
    assert row["title"] == "Foraging in Tiles" and row["requires"] == [] and row["completion_code"] == "KEEP-ME"
    server_admin.publish(db, plan)                                                        # again, no code given: the registered one stays
    assert db.execute("select completion_code from public.experiments where code = 'FOR'").fetchone()["completion_code"] == "KEEP-ME"
    offered = {r["experiment"]: r["n_sessions"] for r in db.execute("select experiment, n_sessions from public.release_experiments where build_commit = %s", (plan["commit"],))}
    assert offered == plan["sessions"]
    assert db.execute("select count(*) as n from public.worlds where name = 'x_seed1.world'").fetchone()["n"] == 1
    server_admin.register_experiment(db, "FOR", "Foraging in Tiles", [], 2, "NEW-CODE")  # a code given later replaces it
    assert db.execute("select completion_code from public.experiments where code = 'FOR'").fetchone()["completion_code"] == "NEW-CODE"
