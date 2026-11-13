"""End-to-end tests of the online data server: the real Edge Functions (Deno) over a real PostgreSQL (pgserver, no Docker)
with the migrations applied. Skipped when deno, pgserver or psycopg is missing:

    pip install pgserver "psycopg[binary]"          (into ./venv)
    deno on PATH, or FORAGING_DENO=/path/to/deno    (npm install deno is enough)
"""

import base64
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")
DENO = os.environ.get("FORAGING_DENO") or shutil.which("deno")
if not DENO:
    pytest.skip("deno not found (PATH or FORAGING_DENO)", allow_module_level=True)

import rundata
import server_admin
import server_client
import trajectory_codec as codec
from server_client import Client, ServerError, event_rows

ROOT = Path(__file__).resolve().parent.parent
APIKEY = "test-key"
COMMIT = "abc1234"
MENU_COMMIT = "menu123"
DEV_COMMIT = "dev9999"                                         # registered as a development release: it may start reduced runs
BUILD = {"commit": COMMIT, "dirty": False, "platform": "TestPlatform", "unity_version": "6000.test"}
WORLD = "a" * 64
INTERLUDE = "b" * 64


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    pg = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="delete")
    url = pg.get_uri()
    with psycopg.connect(url, autocommit=True) as c:
        for role in ("anon", "authenticated"):
            c.execute(f"create role {role} nologin")
        for f in sorted(glob.glob(str(ROOT / "supabase" / "migrations" / "*.sql"))):
            c.execute(Path(f).read_text())
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = tmp_path_factory.mktemp("server") / "server.log"      # the functions' console output: read it when a test sees a 500
    proc = subprocess.Popen([DENO, "run", "-A", str(ROOT / "supabase" / "local" / "serve.ts")], stdout=open(log, "w"), stderr=subprocess.STDOUT,
                            env={**os.environ, "PGHOST": url.split("host=")[1], "PGUSER": "postgres", "PGDATABASE": "postgres", "SUPABASE_ANON_KEY": APIKEY, "PORT": str(port)})
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("deno server exited: " + log.read_text())
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("deno server did not start")
    admin = psycopg.connect(url, autocommit=True, row_factory=psycopg.rows.dict_row)
    server_admin.register_experiment(admin, "TEST", "Test experiment")
    server_admin.register_experiment(admin, "ONE", "First", sort_order=1, completion_code="CODE-ONE")
    server_admin.register_experiment(admin, "TWO", "Second", requires=["ONE"], sort_order=2, completion_code="CODE-TWO")
    server_admin.register_release(admin, COMMIT, {"TEST": 2})
    server_admin.register_release(admin, MENU_COMMIT, {"ONE": 1, "TWO": 1})
    server_admin.register_release(admin, DEV_COMMIT, {"TEST": 2}, development=True)
    admin.execute("insert into public.worlds (sha256, name) values (%s, 'S1_seed1.world'), (%s, 'S1_Interlude_seed1.interlude.json')", (WORLD, INTERLUDE))
    yield {"url": f"http://127.0.0.1:{port}", "db": admin, "dburl": url, "log": log}
    proc.terminate()
    proc.wait(10)
    admin.close()
    pg.cleanup()


def client(env, **build):
    return Client(env["url"], APIKEY, {**BUILD, **build})


def frames(n, start=0, seed=0):
    rng = np.random.default_rng(seed)
    t = (start + np.arange(1, n + 1)) * 0.0083333
    return np.c_[t, np.cumsum(rng.normal(0, 0.05, n)) + 100, np.cumsum(rng.normal(0, 0.05, n)) + 50, np.cumsum(rng.normal(0, 0.3, n)),
                 rng.normal(0, 2, n), rng.integers(0, 8, n)]


def session_row(index=0, **extra):
    return {"name": f"S{index}", "config": {"harvestRangeGapBase": 7.0}, "world_file": "S1_seed1.world", "world_sha256": WORLD,
            "world_seed": 1, "camera": {"fieldOfView": 60}, "display": {"width": 1280}, **extra}


def ev(t, type, **kw):
    return {"t": t, "real": t + 0.1, "type": type, **kw}


def count(env, table, run_id):
    return env["db"].execute(f"select count(*) as n from public.{table} where run_id = %s", (run_id,)).fetchone()["n"]


def raises(status, code):
    return pytest.raises(ServerError, match=f"^{status} {code}")


def test_the_deno_chunk_decoder_matches_the_python_golden_chunk():
    done = subprocess.run([DENO, "test", str(ROOT / "supabase" / "functions" / "_shared" / "chunk_test.ts")], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_run_starts_and_an_unknown_build_is_refused(env):
    c = client(env)
    started = c.start()
    assert started["status"] == "in_progress" and started["token"] and started["resume"] is None and started["has_resume"] is False
    with raises(403, "unknown_build"):
        client(env, commit="nope").start()


def test_requests_without_the_api_key_or_with_a_bad_token_or_body_are_refused(env):
    c = client(env)
    c.start()
    with raises(401, "unauthorized"):
        Client(env["url"], "wrong", BUILD).start()
    good = c.token
    c.token = "not-the-token"
    with raises(401, "unauthorized"):
        c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    c.token = good
    with raises(400, "invalid"):
        c._post("append", {"run_id": c.run_id, "token": good, "session_index": "zero"})
    with raises(400, "invalid"):
        c._post("participant-start", {"build": {"commit": COMMIT}, "prolific_pid": "has space"})


def test_append_stores_rows_and_a_repeat_changes_nothing(env):
    c = client(env)
    c.start()
    f = frames(300)
    events = event_rows([ev(0.0, "session_start", payload={"x": 1.5}), ev(1.0, "fruit", tree_id=4, k=0, reward=2.0, running_total=2.0)])
    ack = c.append(0, session=session_row(), events=events, frames=f, first_seq=0)
    assert ack["events_next"] == 2 and ack["trajectory_next"] == 300 and ack["trials_next"] == 0
    again = c.append(0, session=session_row(), events=events, frames=f, first_seq=0)      # a lost response, resent
    assert again == ack
    assert count(env, "events", c.run_id) == 2 and count(env, "trajectory", c.run_id) == 1 and count(env, "sessions", c.run_id) == 1
    row = env["db"].execute("select * from public.trajectory where run_id = %s", (c.run_id,)).fetchone()
    assert row["n_frames"] == 300 and row["t_end"] == pytest.approx(codec.quantize(f)[-1, 0])
    assert row["last_frame"]["x"] == pytest.approx(codec.quantize(f)[-1, 1])     # decoded by the TypeScript decoder
    assert codec.decode(bytes(row["data"]))[0] == 0


def test_gaps_overlaps_and_unknown_worlds_are_refused_and_change_nothing(env):
    c = client(env)
    c.start()
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]), frames=frames(100), first_seq=0)
    with raises(409, "gap_events"):
        c.append(0, events=event_rows([ev(1.0, "pause")], first_seq=5))
    with raises(409, "gap_trajectory"):
        c.append(0, frames=frames(10, 200), first_seq=150)
    with raises(409, "overlap_trajectory"):
        c.append(0, frames=frames(100, 0, seed=9), first_seq=0)              # the same place with different data
    with raises(409, "session_gap"):
        c.append(2, session=session_row(2))
    with raises(409, "no_session"):
        c.append(1, events=event_rows([ev(0.0, "x")]))
    with raises(403, "unknown_world"):
        c.append(1, session=session_row(1, world_sha256="c" * 64))
    assert count(env, "events", c.run_id) == 1 and count(env, "trajectory", c.run_id) == 1 and count(env, "sessions", c.run_id) == 1


def test_a_failed_request_is_all_or_nothing(env):
    c = client(env)
    c.start()
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    bad_batch = event_rows([ev(1.0, "fruit", tree_id=1, k=0, reward=1.0)], first_seq=1)
    with raises(409, "gap_trajectory"):
        c.append(0, events=bad_batch, frames=frames(10), first_seq=99)         # events are valid, the chunk is not
    assert count(env, "events", c.run_id) == 1


@pytest.mark.parametrize("damage", ["flip", "truncate", "garbage"])
def test_a_damaged_chunk_is_refused(env, damage):
    c = client(env)
    c.start()
    c.append(0, session=session_row())
    chunk = bytearray(codec.encode(frames(200)))
    if damage == "flip":
        chunk[60] ^= 4
    elif damage == "truncate":
        chunk = chunk[:-3]
    else:
        chunk = bytearray(b"hello world, this is not a chunk" * 3)
    with raises(400, "invalid_chunk"):
        c.append_chunks(0, chunks=[base64.b64encode(bytes(chunk)).decode()])
    assert count(env, "trajectory", c.run_id) == 0


def test_resume_state_describes_where_the_session_stopped(env):
    c = client(env)
    c.start(prolific_pid="PID_resume")
    f = frames(250)
    events = [ev(0.0, "session_start"), ev(1.0, "harvest_press", tree_id=7), ev(1.8, "fruit", tree_id=7, k=0, reward=3.0, running_total=3.0),
              ev(2.6, "fruit", tree_id=7, k=1, reward=1.0, running_total=4.0), ev(2.6, "harvest_release", tree_id=7),
              ev(2.9, "harvest_press", tree_id=9), ev(3.7, "fruit", tree_id=9, k=0, reward=5.0, running_total=9.0)]
    c.append(0, session=session_row(), events=event_rows(events), frames=f, first_seq=0)
    old_token = c.token
    back = c.start(prolific_pid="PID_resume")                                         # the same person comes back
    state = back["resume"]
    assert back["has_resume"] is True and state["session_index"] == 0 and state["completed"] is False
    assert state["fruits_taken"] == [{"tree": 7, "n": 2}, {"tree": 9, "n": 1}] and state["running_total"] == 9.0
    assert state["open_bout_tree"] == 9 and state["has_pose"] is True
    assert state["events_next"] == 7 and state["trajectory_next"] == 250 and state["last_event_t"] == 3.7
    assert state["clock"] == pytest.approx(max(3.7, codec.quantize(f)[-1, 0])) and 0 <= state["gap_seconds"] < 60
    q = codec.quantize(f)[-1]
    assert [state["pose"][k] for k in ("t", "x", "z", "yaw", "pitch", "keys")] == pytest.approx(q.tolist())
    assert c.token != old_token
    stale = Client(env["url"], APIKEY, BUILD)
    stale.run_id, stale.token = c.run_id, old_token
    with raises(401, "unauthorized"):
        stale.append(0, events=event_rows([ev(9.0, "pause")], first_seq=7))
    c.append(0, events=event_rows([ev(9.0, "resume")], first_seq=7))                  # the new token works


def test_a_resume_on_a_newer_build_is_recorded(env):
    server_admin.register_release(env["db"], "newer99", {"TEST": 2})
    c = client(env)
    c.start(prolific_pid="PID_build")
    newer = client(env, commit="newer99")
    newer.start(prolific_pid="PID_build")
    row = env["db"].execute("select build_commit, build_commits from public.runs where run_id = %s", (c.run_id,)).fetchone()
    assert row["build_commit"] == COMMIT and row["build_commits"] == [COMMIT, "newer99"]


def test_an_experiment_cannot_require_one_that_is_not_registered(env):
    with pytest.raises(ValueError, match="not registered"):
        server_admin.register_experiment(env["db"], "BAD", "Bad", requires=["NOPE"])


def test_a_run_whose_build_no_longer_lists_the_experiment_does_not_finish(env):
    c = client(env)
    c.start(prolific_pid="PID_unlisted")
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]), frames=frames(20))
    env["db"].execute("delete from public.release_experiments where build_commit = %s and experiment = 'TEST'", (COMMIT,))
    result = c.finish()
    server_admin.register_release(env["db"], COMMIT, {"TEST": 2})             # the database is shared by the tests
    assert result["ok"] is False and result["completion_code"] is None and any("no longer lists" in p for p in result["problems"])
    assert env["db"].execute("select status from public.runs where run_id = %s", (c.run_id,)).fetchone()["status"] != "finished"


def test_interludes_carry_a_plan_and_trials_and_the_resume_state_has_them(env):
    c = client(env)
    c.start(prolific_pid="PID_interlude")
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    interlude = session_row(1, is_interlude=True, interlude_file="S1_Interlude_seed1.interlude.json", interlude_sha256=INTERLUDE)
    trials = [{"seq": i, "presented_order": i, "trial_index": [4, 2, 0][i], "type": "t", "choice": "left", "choice_correct": 1, "timed_out": 0,
               "left_id": 1, "right_id": 2, "response_time": 1.5, "paused_seconds": 2.5} for i in range(2)]
    ack = c.append(1, session=interlude, events=event_rows([ev(0.0, "session_start")]), plan=[4, 2, 0], trials=trials)
    assert ack["trials_next"] == 2
    assert env["db"].execute("select paused_seconds from public.interlude_trials where run_id = %s order by seq", (c.run_id,)).fetchall() == [
        {"paused_seconds": 2.5}, {"paused_seconds": 2.5}]
    state = c.start(prolific_pid="PID_interlude")["resume"]
    assert state["session_index"] == 1 and state["is_interlude"] is True and state["interlude_plan"] == [4, 2, 0]
    assert state["trial_rows"] == [{"correct": 1, "bonus": 0}, {"correct": 1, "bonus": 0}] and state["trials_next"] == 2
    with raises(409, "gap_trials"):
        c.append(1, trials=[{**trials[0], "seq": 5}])


def test_finish_lists_what_is_missing_and_a_finished_run_accepts_no_more(env):
    c = client(env)
    c.start(prolific_pid="PID_finish")
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]), frames=frames(20))
    result = c.finish()
    assert result["ok"] is False and any("1 sessions present, 2 expected" in p for p in result["problems"])
    assert result["completion_code"] is None                                  # the code goes only to a run the database confirms finished
    assert any("not complete" in p for p in result["problems"]) and any("no session_end" in p for p in result["problems"])
    c.append(0, session=session_row(ended_at="2026-10-29T12:00:00Z", completed=True, final_score=0.0),
             events=event_rows([ev(1.0, "session_end", running_total=0.0)], first_seq=1))
    c.append(1, session=session_row(1, completed=True, ended_at="2026-10-29T12:05:00Z", final_score=3.0),
             events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end")]), frames=frames(20))
    assert c.finish() == {"ok": True, "problems": [], "completion_code": "DUMMY-COMPLETION-CODE", "points": 3}
    with raises(401, "unauthorized"):
        c.append(1, events=event_rows([ev(2.0, "late")], first_seq=2))
    again = client(env).start(prolific_pid="PID_finish")
    assert again["status"] == "finished" and "token" not in again and again["completion_code"] == "DUMMY-COMPLETION-CODE"


def test_feedback_is_stored_after_finish_replaced_by_a_second_one_and_needs_the_run_token(env):
    c = client(env)
    c.start(prolific_pid="PID_feedback")
    c.append(0, session=session_row(ended_at="2026-10-29T12:00:00Z", completed=True, final_score=0.0),
             events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end", running_total=0.0)]), frames=frames(20))
    c.append(1, session=session_row(1, completed=True, ended_at="2026-10-29T12:05:00Z", final_score=3.0),
             events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end")]), frames=frames(20))
    assert c.finish()["ok"] is True
    assert c.feedback("The second session was confusing.") == {"ok": True}
    row = env["db"].execute("select text from public.feedback where run_id = %s", (c.run_id,)).fetchone()
    assert row["text"] == "The second session was confusing."
    c.feedback("Unicode ok: kiitos \u00e4\u00f6")
    assert count(env, "feedback", c.run_id) == 1
    assert env["db"].execute("select text from public.feedback where run_id = %s", (c.run_id,)).fetchone()["text"].startswith("Unicode ok")
    other = client(env)
    other.run_id, other.token = c.run_id, "not-the-token"
    with raises(401, "unauthorized"):
        other.feedback("hijack")
    for bad in ("", "x" * 5001):
        with raises(400, "invalid"):
            c.feedback(bad)
    assert env["db"].execute("select text from public.feedback where run_id = %s", (c.run_id,)).fetchone()["text"].startswith("Unicode ok")


def test_feedback_is_also_accepted_while_a_run_is_in_progress(env):
    c = client(env)
    c.start()
    assert c.feedback("early") == {"ok": True} and count(env, "feedback", c.run_id) == 1


def test_concurrent_identical_uploads_store_each_row_once(env):
    c = client(env)
    c.start()
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    events = event_rows([ev(i * 0.1, "pause") for i in range(1, 30)], first_seq=1)
    chunk = [base64.b64encode(codec.encode(frames(200), 0)).decode()]
    errors, acks = [], []

    def go():
        try:
            acks.append(c.append_chunks(0, events=events, chunks=chunk))
        except Exception as e:                      # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len({json.dumps(a, sort_keys=True) for a in acks}) == 1
    assert count(env, "events", c.run_id) == 30 and count(env, "trajectory", c.run_id) == 1


def test_a_returning_start_waits_for_an_upload_that_is_still_committing(env):
    c = client(env)
    c.start(prolific_pid="PID_race")
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    done = []
    with psycopg.connect(env["dburl"]) as holder:           # stands for the other tab's append_batch, holding the run's lock
        holder.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (c.run_id,))
        thread = threading.Thread(target=lambda: done.append(client(env).start(prolific_pid="PID_race")))
        thread.start()
        thread.join(1.0)
        assert thread.is_alive(), "run-start did not wait for the lock"
        holder.commit()
    thread.join(10)
    assert done and done[0]["status"] == "in_progress"


def test_a_session_uploaded_in_batches_and_pulled_back_equals_the_original(env, tmp_path):
    original = tmp_path / "orig"
    traj = codec.quantize(frames(1500))
    events = [ev(0.0, "session_start", payload={"x": 1.5}), *[ev(0.5 + 0.8 * i, "fruit", tree_id=i % 3, k=i // 3, reward=float(i % 4),
                                                                running_total=float(i)) for i in range(40)], ev(12.0, "session_end", running_total=39.0)]
    row = session_row(0, completed=True, ended_at="2026-10-29T12:00:00+00:00", final_score=39.0, frame_stats={"count": 1500})
    run = "11111111-1111-1111-1111-111111111111"
    rundata.write_session(original, run, 0, row, traj, events)
    data = rundata.read_session(original / run / "00")
    c = client(env)
    c.start()
    ack = server_client.upload_session(c, 0, data, frames_per_chunk=400, events_per_batch=15)
    assert ack["trajectory_next"] == 1500 and ack["events_next"] == len(events)
    out = server_admin.pull_run(env["db"], c.run_id, tmp_path / "pulled")
    got = rundata.read_session(out / "00")
    assert np.array_equal(got["traj"], data["traj"]) and len(got["events"]) == len(events)
    assert [e["reward"] for e in got["events"] if e["type"] == "fruit"] == [e["reward"] for e in data["events"] if e["type"] == "fruit"]
    assert got["events"][0]["payload"] == {"x": 1.5}
    assert got["session"]["final_score"] == 39.0 and got["session"]["completed"] is True and got["session"]["config"] == row["config"]
    assert (out / "run.json").exists() and "token_hash" not in json.loads((out / "run.json").read_text())


def test_preflight_has_the_cors_headers(env):
    import urllib.request
    request = urllib.request.Request(env["url"] + "/append", method="OPTIONS")
    with urllib.request.urlopen(request) as response:
        assert response.status == 200 and response.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_the_public_roles_can_read_nothing_and_call_nothing(env, role):
    with psycopg.connect(env["dburl"], autocommit=True) as conn:
        conn.execute(f"set role {role}")
        for statement in ("select * from public.runs", "select * from public.events", "select * from public.consents", "insert into public.releases (build_commit) values ('x')",
                          "select * from public.participants", "select * from public.experiments", "select * from public.release_experiments",
                          "select server.stream_state('00000000-0000-0000-0000-000000000000', 0)",
                          "select server.menu('00000000-0000-0000-0000-000000000000', 'x')"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)


def trial(seq, correct, bonus):
    return {"seq": seq, "presented_order": seq, "trial_index": seq, "choice_correct": correct, "bonus": bonus}


def test_resume_state_carries_the_totals_of_finished_sessions(env):
    c = client(env)
    c.start(prolific_pid="PID_totals")
    done = {"completed": True, "ended_at": "2026-10-29T12:00:00Z"}
    c.append(0, session=session_row(0, is_practice=True, final_score=58.0, **done), events=event_rows([ev(0.0, "session_start")]))
    c.append(1, session=session_row(1, is_interlude=True, is_practice=True, final_score=0.0, **done), events=event_rows([ev(0.0, "session_start")]),
             trials=[trial(0, 1, 5.0)])
    c.append(2, session=session_row(2, final_score=33.0, **done), events=event_rows([ev(0.0, "session_start")]))
    c.append(3, session=session_row(3, is_interlude=True, final_score=0.0, **done), events=event_rows([ev(0.0, "session_start")]),
             trials=[trial(0, 1, 5.0), trial(1, 0, 0.0)])
    c.append(4, session=session_row(4, is_interlude=True), events=event_rows([ev(0.0, "session_start")]), plan=[1, 0],
             trials=[trial(0, 1, 5.0)])
    state = c.start(prolific_pid="PID_totals")["resume"]
    assert state["session_index"] == 4 and state["completed"] is False
    assert [(p["index"], p["is_practice"], p["is_interlude"], p["score"]) for p in state["previous"]] == [
        (0, True, False, 58.0), (1, True, True, 0.0), (2, False, False, 33.0), (3, False, True, 0.0)]
    assert state["previous_interlude"] == {"trials": 2, "correct": 1, "bonus": 5.0}     # finished, non-practice Interludes only
    assert state["trial_rows"] == [{"correct": 1, "bonus": 5.0}]
    assert state["has_pose"] is False and state["pose"]["t"] == 0 and state["open_bout_tree"] == -1 and state["running_total"] == 0


def test_a_completed_latest_session_is_reported_as_completed(env):
    c = client(env)
    c.start(prolific_pid="PID_completed")
    c.append(0, session=session_row(0, completed=True, final_score=7.0, ended_at="2026-10-29T12:00:00Z"), events=event_rows([ev(0.0, "session_end")]))
    state = c.start(prolific_pid="PID_completed")["resume"]
    assert state["completed"] is True and state["final_score"] == 7.0 and [p["index"] for p in state["previous"]] == [0]


def test_consent_is_asked_once_per_participant_and_version(env):
    consent = {"version": "v1", "signature": "Ada Lovelace", "at": "2026-10-31T12:00:00Z"}
    c = client(env)
    assert c.login("PID_consent", consent_version="v1") == {"needs_consent": True} and c.participant_token is None      # nothing is issued or created
    assert env["db"].execute("select count(*) as n from public.pid_registry where prolific_pid = 'PID_consent'").fetchone()["n"] == 0
    first = c.login("PID_consent", consent=consent)
    again = client(env).login("PID_consent", consent_version="v1")                                  # a returning participant: no signature
    assert first["participant_id"] == again["participant_id"] and again["token"] != first["token"]
    assert client(env).login("PID_consent", consent=dict(consent, at="2026-10-31T13:00:00Z"))["participant_id"] == first["participant_id"]
    rows = env["db"].execute("select version, signature from public.consents where participant_id = %s", (first["participant_id"],)).fetchall()
    assert [(r["version"], r["signature"]) for r in rows] == [("v1", "Ada Lovelace")]              # one row per version, not per visit
    assert client(env).login("PID_consent", consent_version="v2") == {"needs_consent": True}      # a new text asks again
    assert "token" in client(env).login("PID_nothing_asked")                                       # no version: a development build asks nothing
    with pytest.raises(ServerError):
        client(env)._post("participant-start", {"build": BUILD, "prolific_pid": "PID_bad", "consent": {"version": "v1"}})


def test_an_old_participant_token_stops_working_at_the_next_login(env):
    c = client(env)
    c.login("PID_tokens")
    old = c.participant_token
    c.login("PID_tokens")
    stale = client(env)
    stale.participant_id, stale.participant_token = c.participant_id, old
    with raises(401, "unauthorized"):
        stale.start(login=False)
    with raises(401, "unauthorized"):
        client(env)._post("run-start", {"build": BUILD, "participant_id": c.participant_id, "participant_token": "nope", "experiment": "TEST"})


def finished_session():
    return session_row(0, completed=True, ended_at="2026-11-06T12:00:00Z", final_score=4.0)


def play_one_session(c):
    c.append(0, session=finished_session(), events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end", running_total=4.0)]), frames=frames(20))
    return c.finish()


def test_the_menu_lists_the_experiments_with_the_participants_standing_and_locks_the_ones_with_unmet_prerequisites(env):
    c = client(env, commit=MENU_COMMIT)
    menu = {m["code"]: m for m in c.login("PID_menu")["experiments"]}
    assert list(menu) == ["ONE", "TWO"]                                                    # in sort order; TEST is not offered by this build
    assert (menu["ONE"]["title"], menu["ONE"]["n_sessions"], menu["ONE"]["status"], menu["ONE"]["unlocked"]) == ("First", 1, "none", True)
    assert menu["TWO"]["unlocked"] is False and menu["TWO"]["status"] == "none"
    with raises(403, "prerequisite_unmet"):
        c.start("TWO", login=False)
    with raises(403, "unknown_experiment"):
        c.start("TEST", login=False)                                                       # registered, but not offered by this build
    started = c.start("ONE", login=False)
    assert started["status"] == "in_progress" and started["experiment"] == "ONE" and started["resume"] is None
    assert {m["code"]: m["status"] for m in c.login("PID_menu")["experiments"]} == {"ONE": "in_progress", "TWO": "none"}
    assert play_one_session(c)["completion_code"] == "CODE-ONE"
    after = {m["code"]: m for m in c.login("PID_menu")["experiments"]}
    assert after["ONE"]["status"] == "finished" and after["ONE"]["sessions_done"] == 1 and after["TWO"]["unlocked"] is True
    assert after["ONE"]["points"] == 4.0 and after["TWO"]["points"] == 0 and menu["ONE"]["points"] == 0          # the finished session's score; nothing before play
    two = c.start("TWO", login=False)
    assert two["status"] == "in_progress" and two["run_id"] != started["run_id"]
    assert env["db"].execute("select experiment, build_commit from public.runs where run_id = %s", (two["run_id"],)).fetchone() == {"experiment": "TWO", "build_commit": MENU_COMMIT}


def test_menu_points_are_completed_session_scores_plus_interlude_bonuses_without_the_practice_ones(env):
    c = client(env)
    c.login("PID_points")
    c.start(login=False)
    done = {"completed": True, "ended_at": "2026-11-07T12:00:00Z"}
    c.append(0, session=session_row(0, is_practice=True, final_score=58.0, **done), events=event_rows([ev(0.0, "session_start")]))         # practice: not counted
    c.append(1, session=session_row(1, is_interlude=True, **done), events=event_rows([ev(0.0, "session_start")]), trials=[trial(0, 1, 5.0), trial(1, 0, 0.0)])
    standing = {m["code"]: m for m in c.login("PID_points")["experiments"]}["TEST"]
    assert standing["points"] == 5.0 and standing["sessions_done"] == 2


def test_a_finished_experiment_is_not_rerun_but_shows_its_completion_code_and_takes_feedback(env):
    c = client(env, commit=MENU_COMMIT)
    c.login("PID_done")
    c.start("ONE", login=False)
    play_one_session(c)
    run = c.run_id
    again = client(env, commit=MENU_COMMIT)
    again.login("PID_done")
    back = again.start("ONE", login=False)
    assert back["status"] == "finished" and back["run_id"] == run and back["completion_code"] == "CODE-ONE" and "token" not in back
    assert count(env, "sessions", run) == 1 and env["db"].execute("select count(*) as n from public.runs where participant_id = %s", (again.participant_id,)).fetchone()["n"] == 1
    again.run_id, again.token = run, again.participant_token                               # the menu has no run token: the participant's does
    assert again.feedback("seen again from the menu") == {"ok": True}
    assert env["db"].execute("select text from public.feedback where run_id = %s", (run,)).fetchone()["text"] == "seen again from the menu"
    other = client(env, commit=MENU_COMMIT)
    other.login("PID_done_other")
    other.run_id, other.token = run, other.participant_token
    with raises(401, "unauthorized"):
        other.feedback("someone else's participant token")


def test_the_completion_code_is_the_experiments_own_and_a_dummy_until_one_is_set(env):
    assert client(env).start()["experiment"] == "TEST"
    c = client(env)
    c.start(prolific_pid="PID_dummy")
    assert play_two_sessions(c)["completion_code"] == "DUMMY-COMPLETION-CODE"


def play_two_sessions(c):
    c.append(0, session=finished_session(), events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end", running_total=4.0)]), frames=frames(20))
    c.append(1, session=session_row(1, completed=True, ended_at="2026-11-06T12:05:00Z", final_score=1.0),
             events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end")]), frames=frames(20))
    return c.finish()


def test_the_migration_turns_existing_runs_into_participants_of_a_legacy_experiment(tmp_path):
    pg = pgserver.get_server(tmp_path / "pg", cleanup_mode="delete")
    try:
        with psycopg.connect(pg.get_uri(), autocommit=True, row_factory=psycopg.rows.dict_row) as c:
            for role in ("anon", "authenticated"):
                c.execute(f"create role {role} nologin")
            files = sorted(glob.glob(str(ROOT / "supabase" / "migrations" / "*.sql")))
            migration = [f for f in files if f.endswith("_experiments.sql")][0]
            for f in files[:files.index(migration)]:                           # the schema before the experiments
                c.execute(Path(f).read_text())
            c.execute("insert into public.releases (build_commit, n_sessions) values ('old', 3)")
            run_a = c.execute("insert into public.runs (token_hash, build_commit, status) values ('h', 'old', 'finished') returning run_id").fetchone()["run_id"]
            run_b = c.execute("insert into public.runs (token_hash, build_commit) values ('h', 'old') returning run_id").fetchone()["run_id"]
            c.execute("insert into public.pid_registry (prolific_pid, run_id) values ('OLD_PID', %s)", (run_a,))
            c.execute("insert into public.consents (run_id, version, signature) values (%s, 'v0', 'Old Name')", (run_a,))
            c.execute(Path(migration).read_text())
            runs = c.execute("select run_id, participant_id, experiment, status from public.runs order by started_at, run_id").fetchall()
            assert {r["experiment"] for r in runs} == {"legacy"} and len({r["participant_id"] for r in runs}) == 2
            pid = c.execute("select participant_id from public.pid_registry where prolific_pid = 'OLD_PID'").fetchone()["participant_id"]
            assert c.execute("select participant_id from public.runs where run_id = %s", (run_a,)).fetchone()["participant_id"] == pid
            assert c.execute("select participant_id, version from public.consents").fetchall() == [{"participant_id": pid, "version": "v0"}]
            assert c.execute("select n_sessions from public.release_experiments where build_commit = 'old' and experiment = 'legacy'").fetchone()["n_sessions"] == 3
            assert [m["code"] for m in c.execute("select jsonb_array_elements(server.menu(%s, 'old')) as m", (pid,)).fetchall() for m in [m["m"]]] == ["legacy"]
    finally:
        pg.cleanup()


def test_the_load_test_script_runs_clean_against_the_local_server(env):
    import hashlib
    world = ROOT / "Assets" / "StreamingAssets" / "Experiments" / "FOR" / "FOR_S1_seed7101.world"
    env["db"].execute("insert into public.worlds (sha256, name) values (%s, 'FOR_S1_seed7101.world') on conflict do nothing", (hashlib.sha256(world.read_bytes()).hexdigest(),))
    server_admin.register_release(env["db"], "load-test", {"TEST": 1})
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "load_test.py"), "--url", env["url"], "--participants", "3", "--seconds", "6",
                           "--ramp", "1"], capture_output=True, text=True, env={**os.environ, "FORAGING_API_KEY": APIKEY}, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert env["db"].execute("select count(*) as n from public.runs where build_commit = 'load-test' and status = 'finished'").fetchone()["n"] == 3


def two_sessions(c):
    c.append(0, session=finished_session(), events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end", running_total=4.0)]), frames=frames(20))
    c.append(1, session=session_row(1, completed=True, ended_at="2026-11-10T12:05:00Z", final_score=1.0),
             events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end")]), frames=frames(20))


def test_only_a_development_release_may_start_a_reduced_run_and_never_one_longer_than_the_experiment(env):
    with raises(403, "reduced_run_not_allowed"):
        client(env).start(prolific_pid="PID_reduced_release", expected_sessions=1)               # a release build: refused, nothing created
    assert env["db"].execute("select count(*) as n from public.runs r join public.pid_registry p using (participant_id) where p.prolific_pid = 'PID_reduced_release'").fetchone()["n"] == 0
    with raises(403, "reduced_run_not_allowed"):
        client(env, commit=DEV_COMMIT).start(prolific_pid="PID_reduced_long", expected_sessions=3)        # more than the 2 sessions the experiment has
    with raises(400, "invalid"):
        client(env, commit=DEV_COMMIT).start(prolific_pid="PID_reduced_zero", expected_sessions=0)
    with raises(400, "invalid"):
        client(env, commit=DEV_COMMIT).start(prolific_pid="PID_reduced_text", expected_sessions="one")
    assert client(env, commit=DEV_COMMIT).start(prolific_pid="PID_reduced_ok", expected_sessions=1)["status"] == "in_progress"


def test_a_reduced_run_finishes_with_its_declared_count_and_the_menu_follows_it(env):
    c = client(env, commit=DEV_COMMIT)
    c.start(prolific_pid="PID_reduced_finish", expected_sessions=1)
    menu = {m["code"]: m for m in c.login("PID_reduced_finish")["experiments"]}
    assert menu["TEST"]["n_sessions"] == 1                                                    # the run's own count, so the menu's progress is the run's
    c.start("TEST", login=False, expected_sessions=1)
    play_one_session(c)                                                                     # (finishes: one session present, one expected)
    done = client(env, commit=DEV_COMMIT).start(prolific_pid="PID_reduced_finish")
    assert done["status"] == "finished" and done["completion_code"] == "DUMMY-COMPLETION-CODE"


def test_a_full_run_of_a_development_release_still_needs_every_session_and_a_resume_can_drop_the_reduction(env):
    c = client(env, commit=DEV_COMMIT)
    c.start(prolific_pid="PID_reduced_full")
    c.append(0, session=finished_session(), events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end", running_total=4.0)]), frames=frames(20))
    result = c.finish()
    assert result["ok"] is False and any("1 sessions present, 2 expected" in p for p in result["problems"])
    r = client(env, commit=DEV_COMMIT)
    r.start(prolific_pid="PID_reduced_resume", expected_sessions=1)
    back = client(env, commit=DEV_COMMIT)
    back.start(prolific_pid="PID_reduced_resume")                                             # returns without a reduction: the full count applies again
    two_sessions_ok = back.finish()
    assert two_sessions_ok["ok"] is False and any("0 sessions present, 2 expected" in p for p in two_sessions_ok["problems"])


def test_a_ranking_set_is_a_trial_row_with_bushes_and_counts_in_the_tallies_and_the_long_view(env):
    c = client(env)
    c.start(prolific_pid="PID_ranking")
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    bushes = [{"id": 5, "slot": 0, "shape": 0.25, "color": 0.5, "moisture": 0.5, "value": 1.5, "rank": 1, "start_time": 1.0, "finish_time": 2.5, "fruits": 10},
              {"id": 6, "slot": 1, "shape": 0.75, "color": 0.1, "moisture": 0.5, "value": 0.5, "rank": None, "start_time": None, "finish_time": None, "fruits": 0}]
    row = {"seq": 0, "presented_order": 0, "trial_index": 2, "type": "ranking", "timed_out": 1, "response_time": 30.0, "bonus": 3.5, "set_size": 2,
           "correct_pairs": 1, "total_pairs": 1, "bushes": bushes}
    ack = c.append(1, session=session_row(1, is_interlude=True), events=event_rows([ev(0.0, "session_start")]), plan=[2], trials=[row])
    assert ack["trials_next"] == 1
    state = c.start(prolific_pid="PID_ranking")["resume"]
    assert state["trial_rows"] == [{"correct": 0, "bonus": 3.5}] and state["trials_next"] == 1
    picks = env["db"].execute("select bush_id, slot, rank, finish_time, fruits from public.interlude_picks where run_id = %s order by bush_id", (c.run_id,)).fetchall()
    assert picks == [{"bush_id": 5, "slot": 0, "rank": 1, "finish_time": 2.5, "fruits": 10}, {"bush_id": 6, "slot": 1, "rank": None, "finish_time": None, "fruits": 0}]
