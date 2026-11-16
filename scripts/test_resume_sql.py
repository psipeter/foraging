"""server.resume_state of a session that stopped inside a ranking break (migration 20261116000000): the SQL function alone over a real PostgreSQL (pgserver) with the
migrations applied, no Edge Functions (test_server.py runs those and needs deno). Skipped without pgserver or psycopg."""

import glob
import json
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    pg = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="delete")
    with psycopg.connect(pg.get_uri(), autocommit=True) as c:
        for role in ("anon", "authenticated"):
            c.execute(f"create role {role} nologin")
        for f in sorted(glob.glob(str(ROOT / "supabase" / "migrations" / "*.sql"))):
            c.execute(Path(f).read_text())
    conn = psycopg.connect(pg.get_uri(), autocommit=True)
    yield conn
    conn.close()


def make_run(db, events):
    """A run with one session holding `events`, a list of (t, type, payload)."""
    run, person = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute("insert into public.experiments (code, title) values ('T', 'T') on conflict do nothing")
    db.execute("insert into public.participants (participant_id) values (%s)", (person,))
    db.execute("insert into public.runs (run_id, token_hash, participant_id, experiment) values (%s, 'x', %s, 'T')", (run, person))
    db.execute("insert into public.sessions (run_id, session_index, name, config) values (%s, 0, 'S', '{}')", (run,))
    for seq, (t, kind, payload) in enumerate(events):
        db.execute("insert into public.events (run_id, session_index, seq, t, type, payload) values (%s, 0, %s, %s, %s, %s)",
                   (run, seq, t, kind, json.dumps(payload) if payload is not None else None))
    return run


def state(db, run):
    return db.execute("select server.resume_state(%s)", (run,)).fetchone()[0]


def test_a_session_that_stopped_inside_a_set_reports_the_open_break(db):
    s = state(db, make_run(db, [(0, "session_start", None), (10, "rank_break_start", {"break": 1, "leaving": 2, "pool_index": 0}),
                                (10.5, "rank_set", {"break": 1}), (11, "rank_set_start", {"break": 1})]))
    assert (s["open_break"], s["open_break_leaving"], s["open_break_sets_done"], s["breaks"]) == (1, 2, 0, 1)
    assert s["held_seconds"] == pytest.approx(1.0) and s["clock"] == pytest.approx(11.0)


def test_a_scored_set_in_the_open_break_is_counted(db):
    s = state(db, make_run(db, [(10, "rank_break_start", {"break": 3, "leaving": 4}), (10.5, "rank_set", {}), (14, "rank_set_end", {})]))
    assert (s["open_break"], s["open_break_sets_done"], s["breaks"]) == (3, 1, 3)


def test_no_break_open_means_zero(db):
    s = state(db, make_run(db, [(10, "rank_break_start", {"break": 1}), (14, "rank_break_end", {"break": 1}), (15, "fruit", None)]))
    assert (s["open_break"], s["open_break_leaving"], s["open_break_sets_done"]) == (0, 0, 0)
    assert s["held_seconds"] == pytest.approx(4.0)


def test_a_break_played_again_keeps_its_number_and_the_held_time_adds_up(db):
    run = make_run(db, [(10, "rank_break_start", {"break": 1, "leaving": 1}), (10.5, "rank_set", {}), (11, "rank_set_start", {}),
                        (11, "session_resume", {}), (11, "rank_break_end", {"break": 1, "aborted": True}),
                        (12, "rank_break_start", {"break": 1, "leaving": 1, "resumed": True}), (12.5, "rank_set", {}), (14, "rank_set_end", {}), (14.5, "rank_break_end", {"break": 1})])
    s = state(db, run)
    assert s["breaks"] == 1 and s["open_break"] == 0                                      # two starts, one break
    assert s["held_seconds"] == pytest.approx(1.0 + 2.5)                                  # the interrupted try up to the resume, then the second try


def test_a_second_interruption_inside_the_replayed_break_is_open_again(db):
    run = make_run(db, [(10, "rank_break_start", {"break": 1, "leaving": 1}), (11, "session_resume", {}), (11, "rank_break_end", {"break": 1, "aborted": True}),
                        (12, "rank_break_start", {"break": 1, "leaving": 1, "resumed": True}), (12.5, "rank_set", {})])
    s = state(db, run)
    assert (s["open_break"], s["breaks"]) == (1, 1) and s["held_seconds"] == pytest.approx(1.0 + 0.5)
