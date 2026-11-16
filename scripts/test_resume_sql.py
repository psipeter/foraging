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


def make_run(db, events, config=None, completed=False, person=None):
    """A run with one session holding `events`, a list of (t, type, payload)."""
    run, person = str(uuid.uuid4()), person or str(uuid.uuid4())
    db.execute("insert into public.experiments (code, title) values ('T', 'T') on conflict do nothing")
    db.execute("insert into public.participants (participant_id) values (%s) on conflict do nothing", (person,))
    db.execute("insert into public.runs (run_id, token_hash, participant_id, experiment) values (%s, 'x', %s, 'T')", (run, person))
    db.execute("insert into public.sessions (run_id, session_index, name, config, completed) values (%s, 0, 'S', %s, %s)", (run, json.dumps(config or {}), completed))
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


def test_the_hints_shown_come_back_in_the_order_they_were_shown_without_repeats(db):
    s = state(db, make_run(db, [(1, "hint_shown", {"id": "bout:1"}), (2, "hint_dismissed", {"id": "bout:1"}), (5, "hint_shown", {"id": "bout:2"}),
                                (9, "session_resume", {}), (12, "hint_shown", {"id": "bout:2"}), (13, "hint_shown", {"id": "patch_switch:3"})]))
    assert s["hints_shown"] == ["bout:1", "bout:2", "patch_switch:3"]
    assert state(db, make_run(db, [(1, "fruit", None)]))["hints_shown"] == []


def test_the_progress_through_a_session_is_the_foraging_clock_over_its_duration(db):
    cfg = {"sessionDuration": 120.0}
    run = make_run(db, [(0, "session_start", None), (10, "rank_break_start", {"break": 1}), (30, "rank_break_end", {"break": 1}), (70, "fruit", None)], config=cfg)
    assert db.execute("select server.session_progress(%s)", (run,)).fetchone()[0] == pytest.approx((70 - 20) / 120.0)       # 70 s on the clock, 20 of them held in the ranking
    over = make_run(db, [(0, "session_start", None), (130, "fruit", None)], config=cfg)
    assert db.execute("select server.session_progress(%s)", (over,)).fetchone()[0] == pytest.approx(1.0)
    done = make_run(db, [(0, "session_start", None), (100, "session_end", None)], config=cfg, completed=True)
    assert db.execute("select server.session_progress(%s)", (done,)).fetchone()[0] == 0


def test_the_menu_reports_the_progress_of_an_experiment_in_progress(db):
    person = str(uuid.uuid4())
    make_run(db, [(0, "session_start", None), (60, "fruit", None)], config={"sessionDuration": 120.0}, person=person)
    db.execute("insert into public.releases (build_commit) values ('abc') on conflict do nothing")
    db.execute("insert into public.release_experiments (build_commit, experiment, n_sessions) values ('abc', 'T', 2) on conflict do nothing")
    entry = db.execute("select server.menu(%s, 'abc')", (person,)).fetchone()[0][0]
    assert entry["code"] == "T" and entry["sessions_done"] == 0 and entry["session_progress"] == pytest.approx(0.5)
    assert entry["session_foraging_seconds"] == pytest.approx(60.0) and entry["session_rankings"] == 0


def test_the_standing_counts_the_foraging_seconds_and_the_rankings_ended_not_aborted(db):
    run = make_run(db, [(0, "session_start", None), (10, "rank_break_start", {"break": 1}), (30, "rank_break_end", {"break": 1}), (31, "session_resume", {}),
                        (31, "rank_break_start", {"break": 2}), (35, "rank_break_end", {"break": 2, "aborted": True}), (70, "fruit", None)])
    standing = db.execute("select server.session_standing(%s)", (run,)).fetchone()[0]
    assert standing["rankings"] == 1 and standing["foraging_seconds"] == pytest.approx(70 - 20 - 4)       # 20 s and 4 s held in the two breaks
    done = make_run(db, [(0, "session_start", None), (100, "session_end", None)], completed=True)
    assert db.execute("select server.session_standing(%s)", (done,)).fetchone()[0] == {"foraging_seconds": 0, "rankings": 0}


def test_the_leaving_count_and_a_due_ranking_that_has_not_begun_come_back(db):
    s = state(db, make_run(db, [(5, "rank_leaving", {"n": 1, "tile": 1, "due": True}), (6, "rank_break_start", {"break": 1, "leaving": 1}), (9, "rank_break_end", {"break": 1}),
                                (20, "rank_leaving", {"n": 2, "tile": 0, "due": True}), (21, "rank_break_start", {"break": 2, "leaving": 2}), (24, "rank_break_end", {"break": 2}),
                                (40, "rank_leaving", {"n": 3, "tile": 1, "due": False})]))
    assert s["leavings"] == 3 and s["leaving_due"] is False                              # leaving 3 was not on the schedule
    s = state(db, make_run(db, [(5, "rank_leaving", {"n": 1, "tile": 1, "due": True}), (6, "rank_break_start", {"break": 1, "leaving": 1}), (9, "rank_break_end", {"break": 1}),
                                (20, "rank_leaving", {"n": 2, "tile": 0, "due": True})]))        # stopped while a harvest delayed the break of leaving 2
    assert s["leavings"] == 2 and s["leaving_due"] is True
    s = state(db, make_run(db, [(1, "fruit", None)]))
    assert s["leavings"] == 0 and s["leaving_due"] is False


def test_the_correct_pairs_of_the_sets_come_back_whatever_was_paid(db):
    run = make_run(db, [(1, "rank_break_start", {"break": 1}), (9, "rank_break_end", {"break": 1})])
    for seq, (pairs, points) in enumerate([(6, 0.0), (4, 0.0)]):                # a practice session: the pairs count, nothing is paid
        db.execute("insert into public.ranking_sets (run_id, session_index, seq, set_index, pool_index, correct_pairs, total_pairs, points) values (%s, 0, %s, %s, %s, %s, 10, %s)",
                   (run, seq, seq, seq, pairs, points))
    s = state(db, run)
    assert s["ranking_pairs"] == 10 and s["ranking_points"] == 0
    assert state(db, make_run(db, [(1, "fruit", None)]))["ranking_pairs"] == 0


def test_a_second_reload_before_the_break_is_played_again_keeps_it_open(db):
    s = state(db, make_run(db, [(10, "rank_break_start", {"break": 1, "leaving": 2}), (11, "session_resume", {}), (11, "rank_break_end", {"break": 1, "aborted": True}),
                                (20, "session_resume", {})]))
    assert (s["open_break"], s["open_break_leaving"], s["open_break_sets_done"], s["open_break_end_logged"], s["breaks"]) == (1, 2, 0, True, 1)
    assert s["held_seconds"] == pytest.approx(1.0)


def test_sets_scored_before_two_reloads_inside_one_break_are_all_counted(db):
    s = state(db, make_run(db, [(10, "rank_break_start", {"break": 1, "leaving": 1}), (14, "rank_set_end", {}), (15, "session_resume", {}), (15, "rank_break_end", {"break": 1, "aborted": True}),
                                (16, "rank_break_start", {"break": 1, "leaving": 1, "resumed": True}), (20, "rank_set_end", {}), (21, "session_resume", {}),
                                (21, "rank_break_end", {"break": 1, "aborted": True})]))
    assert (s["open_break"], s["open_break_sets_done"], s["open_break_end_logged"]) == (1, 2, True)


def test_a_break_ended_normally_after_a_resume_is_not_open(db):
    s = state(db, make_run(db, [(10, "rank_break_start", {"break": 1}), (11, "rank_break_end", {"break": 1, "aborted": True}), (12, "rank_break_start", {"break": 1, "resumed": True}),
                                (16, "rank_break_end", {"break": 1})]))
    assert (s["open_break"], s["open_break_end_logged"]) == (0, False)
