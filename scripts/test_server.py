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
    server_admin.register_release(admin, COMMIT, 2)
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
        c._post("run-start", {"build": {"commit": COMMIT}, "prolific_pid": "has space"})


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


def test_an_anonymous_run_resumes_with_its_token_and_the_token_rotates(env):
    c = client(env)
    c.start()
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    first = c.token
    state = c.resume()["resume"]
    assert state["events_next"] == 1 and c.token != first
    other = client(env)
    with raises(401, "unauthorized"):
        other.resume(run_id=c.run_id, token=first)


def test_a_resume_on_a_newer_build_is_recorded(env):
    server_admin.register_release(env["db"], "newer99", 2)
    c = client(env)
    c.start(prolific_pid="PID_build")
    newer = client(env, commit="newer99")
    newer.start(prolific_pid="PID_build")
    row = env["db"].execute("select build_commit, build_commits from public.runs where run_id = %s", (c.run_id,)).fetchone()
    assert row["build_commit"] == COMMIT and row["build_commits"] == [COMMIT, "newer99"]


def test_interludes_carry_a_plan_and_trials_and_the_resume_state_has_them(env):
    c = client(env)
    c.start()
    c.append(0, session=session_row(), events=event_rows([ev(0.0, "session_start")]))
    interlude = session_row(1, is_interlude=True, interlude_file="S1_Interlude_seed1.interlude.json", interlude_sha256=INTERLUDE)
    trials = [{"seq": i, "presented_order": i, "trial_index": [4, 2, 0][i], "type": "t", "choice": "left", "choice_correct": 1, "timed_out": 0,
               "left_id": 1, "right_id": 2, "response_time": 1.5} for i in range(2)]
    ack = c.append(1, session=interlude, events=event_rows([ev(0.0, "session_start")]), plan=[4, 2, 0], trials=trials)
    assert ack["trials_next"] == 2
    state = c.resume()["resume"]
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
    assert any("not complete" in p for p in result["problems"]) and any("no session_end" in p for p in result["problems"])
    c.append(0, session=session_row(ended_at="2026-10-29T12:00:00Z", completed=True, final_score=0.0),
             events=event_rows([ev(1.0, "session_end", running_total=0.0)], first_seq=1))
    c.append(1, session=session_row(1, completed=True, ended_at="2026-10-29T12:05:00Z", final_score=3.0),
             events=event_rows([ev(0.0, "session_start"), ev(1.0, "session_end")]), frames=frames(20))
    assert c.finish() == {"ok": True, "problems": []}
    with raises(401, "unauthorized"):
        c.append(1, events=event_rows([ev(2.0, "late")], first_seq=2))
    again = client(env).start(prolific_pid="PID_finish")
    assert again["status"] == "finished" and "token" not in again


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


def test_a_session_uploaded_in_batches_and_pulled_back_equals_the_original(env, tmp_path):
    original = tmp_path / "orig"
    traj = frames(1500)
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


def test_a_small_session_uploaded_in_one_batch_ends_complete(env, tmp_path):
    row = session_row(0, completed=True, ended_at="2026-10-29T12:00:00+00:00", final_score=5.0)
    run = "22222222-2222-2222-2222-222222222222"
    rundata.write_session(tmp_path, run, 0, row, frames(30), [ev(0.0, "session_start"), ev(0.5, "session_end", running_total=5.0)])
    c = client(env)
    c.start()
    server_client.upload_session(c, 0, rundata.read_session(tmp_path / run / "00"))
    got = env["db"].execute("select completed, final_score from public.sessions where run_id = %s", (c.run_id,)).fetchone()
    assert got == {"completed": True, "final_score": 5.0}


def test_preflight_and_cors_headers(env):
    import urllib.request
    request = urllib.request.Request(env["url"] + "/append", method="OPTIONS")
    with urllib.request.urlopen(request) as response:
        assert response.status == 200 and response.headers["Access-Control-Allow-Origin"] == "*"
    with pytest.raises(ServerError) as e:
        Client(env["url"], "wrong", BUILD).start()
    assert e.value.status == 401


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_the_public_roles_can_read_nothing_and_call_nothing(env, role):
    with psycopg.connect(env["dburl"], autocommit=True) as conn:
        conn.execute(f"set role {role}")
        for statement in ("select * from public.runs", "select * from public.events", "insert into public.releases (build_commit) values ('x')",
                          "select server.stream_state('00000000-0000-0000-0000-000000000000', 0)"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)


def trial(seq, correct, bonus):
    return {"seq": seq, "presented_order": seq, "trial_index": seq, "choice_correct": correct, "bonus": bonus}


def test_resume_state_carries_the_totals_of_finished_sessions(env):
    c = client(env)
    c.start()
    done = {"completed": True, "ended_at": "2026-10-29T12:00:00Z"}
    c.append(0, session=session_row(0, is_practice=True, final_score=58.0, **done), events=event_rows([ev(0.0, "session_start")]))
    c.append(1, session=session_row(1, is_interlude=True, is_practice=True, final_score=0.0, **done), events=event_rows([ev(0.0, "session_start")]),
             trials=[trial(0, 1, 5.0)])
    c.append(2, session=session_row(2, final_score=33.0, **done), events=event_rows([ev(0.0, "session_start")]))
    c.append(3, session=session_row(3, is_interlude=True, final_score=0.0, **done), events=event_rows([ev(0.0, "session_start")]),
             trials=[trial(0, 1, 5.0), trial(1, 0, 0.0)])
    c.append(4, session=session_row(4, is_interlude=True), events=event_rows([ev(0.0, "session_start")]), plan=[1, 0],
             trials=[trial(0, 1, 5.0)])
    state = c.resume()["resume"]
    assert state["session_index"] == 4 and state["completed"] is False
    assert [(p["index"], p["is_practice"], p["is_interlude"], p["score"]) for p in state["previous"]] == [
        (0, True, False, 58.0), (1, True, True, 0.0), (2, False, False, 33.0), (3, False, True, 0.0)]
    assert state["previous_interlude"] == {"trials": 2, "correct": 1, "bonus": 5.0}     # finished, non-practice Interludes only
    assert state["trial_rows"] == [{"correct": 1, "bonus": 5.0}]
    assert state["has_pose"] is False and state["pose"]["t"] == 0 and state["open_bout_tree"] == -1 and state["running_total"] == 0


def test_a_completed_latest_session_is_reported_as_completed(env):
    c = client(env)
    c.start()
    c.append(0, session=session_row(0, completed=True, final_score=7.0, ended_at="2026-10-29T12:00:00Z"), events=event_rows([ev(0.0, "session_end")]))
    state = c.resume()["resume"]
    assert state["completed"] is True and state["final_score"] == 7.0 and [p["index"] for p in state["previous"]] == [0]
