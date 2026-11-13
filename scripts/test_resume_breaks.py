"""The server's resume state for a session with ranking breaks (migration 20261113000000_ranking_breaks_resume.sql): held_seconds, breaks and sets_played,
read from the events the game logs (rank_break_start, rank_break_end, rank_set). Real PostgreSQL through pgserver with every migration applied; skipped
without pgserver or psycopg. (test_server.py covers the endpoints and needs Deno; the SQL function is called directly here.)"""

import glob
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    pg = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="delete")
    with psycopg.connect(pg.get_uri(), autocommit=True, row_factory=psycopg.rows.dict_row) as c:
        for role in ("anon", "authenticated"):
            c.execute(f"create role {role} nologin")
        for f in sorted(glob.glob(str(ROOT / "supabase" / "migrations" / "*.sql"))):
            c.execute(Path(f).read_text())
        yield c
    pg.cleanup()


def new_run(conn, name):
    conn.execute("insert into public.releases (build_commit) values ('b') on conflict do nothing")
    conn.execute("insert into public.experiments (code, title) values ('T', 'Test') on conflict do nothing")
    participant = conn.execute("insert into public.participants default values returning participant_id").fetchone()["participant_id"]
    run = conn.execute("insert into public.runs (token_hash, build_commit, participant_id, experiment) values ('h', 'b', %s, 'T') returning run_id", (participant,)).fetchone()["run_id"]
    conn.execute("insert into public.sessions (run_id, session_index, name, config) values (%s, 0, %s, '{}')", (run, name))
    return run


def log(conn, run, events):
    for seq, (t, kind) in enumerate(events):
        conn.execute("insert into public.events (run_id, session_index, seq, t, type) values (%s, 0, %s, %s, %s)", (run, seq, t, kind))


def state(conn, run):
    return conn.execute("select server.resume_state(%s) as s", (run,)).fetchone()["s"]


def test_a_session_without_breaks_holds_nothing(conn):
    run = new_run(conn, "S1")
    log(conn, run, [(0.0, "session_start"), (5.0, "fruit")])
    s = state(conn, run)
    assert s["held_seconds"] == 0 and s["breaks"] == 0 and s["sets_played"] == 0 and s["clock"] == 5.0


def test_finished_breaks_are_held_and_counted(conn):
    run = new_run(conn, "S2")
    log(conn, run, [(0.0, "session_start"), (20.0, "rank_break_start"), (20.5, "rank_set"), (26.0, "rank_break_end"), (40.0, "rank_break_start"), (40.5, "rank_set"),
                    (41.0, "rank_set"), (50.0, "rank_break_end"), (60.0, "fruit")])
    s = state(conn, run)
    assert s["held_seconds"] == pytest.approx(6.0 + 10.0) and s["breaks"] == 2 and s["sets_played"] == 3 and s["clock"] == 60.0


def test_a_break_the_data_stops_inside_is_held_until_the_last_thing_heard(conn):
    run = new_run(conn, "S3")
    log(conn, run, [(0.0, "session_start"), (20.0, "rank_break_start"), (26.0, "rank_break_end"), (40.0, "rank_break_start"), (40.5, "rank_set"), (47.0, "rank_pick")])
    s = state(conn, run)
    assert s["held_seconds"] == pytest.approx(6.0 + 7.0) and s["breaks"] == 2 and s["sets_played"] == 1 and s["clock"] == 47.0


def test_the_bonus_of_the_sets_so_far_is_returned(conn):
    run = new_run(conn, "S4")
    log(conn, run, [(0.0, "session_start"), (20.0, "rank_break_start")])
    assert state(conn, run)["break_bonus"] == 0
    for seq, bonus in enumerate((4.0, 6.0)):
        conn.execute("insert into public.ranking_sets (run_id, session_index, seq, set_index, pool_index, bonus) values (%s, 0, %s, %s, %s, %s)", (run, seq, seq, seq, bonus))
    assert state(conn, run)["break_bonus"] == pytest.approx(10.0)


def test_the_points_of_a_run_include_the_bonus_of_a_foraging_sessions_ranking_sets(conn):
    run = new_run(conn, "S5")
    conn.execute("update public.sessions set completed = true, final_score = 10 where run_id = %s", (run,))
    conn.execute("insert into public.ranking_sets (run_id, session_index, seq, set_index, pool_index, bonus) values (%s, 0, 0, 0, 0, 5)", (run,))
    assert conn.execute("select server.run_points(%s) as p", (run,)).fetchone()["p"] == 15
    conn.execute("update public.sessions set is_practice = true where run_id = %s", (run,))
    assert conn.execute("select server.run_points(%s) as p", (run,)).fetchone()["p"] == 0         # a practice session pays nothing, sets included
