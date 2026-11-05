"""human_data.py against a fake database: the tidy tables, the raw layout, incremental downloads and the participant filter."""

import base64
import re

import numpy as np
import pandas as pd
import pytest

import human_data as hd
import rundata
import trajectory_codec as codec

RUN_A, RUN_B, RUN_C = ("%08d-0000-4000-8000-000000000000" % i for i in (1, 2, 3))


def run_row(run_id, participant, signature, status="finished", n_sessions=2, last="2026-11-03 10:20:00+00", feedback=None):
    return {"run_id": run_id, "status": status, "platform": "WebGLPlayer", "build_commit": "abc", "build_commits": ["abc"], "build_dirty": False,
            "unity_version": "6000", "started_at": "2026-11-03 10:00:00+00", "finished_at": "2026-11-03 10:18:30+00" if status == "finished" else None,
            "participant": participant, "signature": signature, "consent_version": "v1", "feedback": feedback, "n_sessions": n_sessions,
            "last_event": last}


def session_row(run_id, index, name, interlude=False):
    return {"run_id": run_id, "session_index": index, "name": name, "is_practice": False, "is_interlude": interlude, "world_seed": 1,
            "world_file": None, "world_sha256": None, "interlude_file": None, "interlude_sha256": None,
            "config": {"sessionDuration": 90}, "camera": {}, "display": {"width": 1920}, "frame_stats": {"count": 100, "meanMs": 9.5, "maxMs": 30},
            "started_at": "2026-11-03 10:00:00+00", "ended_at": "2026-11-03 10:01:30.5+00", "completed": True, "final_score": 12.0}


def event_row(run_id, index, seq, type_, reward=None, total=None, payload=None):
    return {"run_id": run_id, "session_index": index, "seq": seq, "t": seq * 1.5, "real": seq * 1.5, "type": type_, "tree_id": 3 if reward is not None else None,
            "k": 0 if reward is not None else None, "reward": reward, "running_total": total, "payload": payload, "received_at": "2026-11-03 10:00:05+00"}


def trial_row(run_id, index, seq, correct):
    row = {c: None for c in rundata.INTERLUDE_COLUMNS}
    row.update(run_id=run_id, session_index=index, seq=seq, type="gap", choice="left", choice_correct=int(correct), bonus=10.0 if correct else 0.0)
    return row


class FakeServer:
    """What `human_data.query` returns for the queries the download makes; counts the data queries."""

    def __init__(self):
        self.runs, self.tables, self.calls = [], {name: [] for name, _, _ in hd.TABLES}, []

    def add(self, run, session_rows, events, trials=()):
        self.runs.append(run)
        self.tables["sessions"] += session_rows
        self.tables["events"] += events
        self.tables["trials"] += list(trials)
        for s in session_rows:
            frames = np.column_stack([np.arange(1, 6) * 0.1, np.arange(5), np.zeros(5), np.zeros(5), np.zeros(5), np.zeros(5)])
            self.tables["trajectory"].append({"run_id": run["run_id"], "session_index": s["session_index"], "first_seq": 0,
                                              "data": base64.b64encode(codec.encode(frames, 0)).decode()})

    def __call__(self, sql):
        if "from public.runs" in sql:
            return list(self.runs)
        self.calls.append(sql)
        name = next(n for n, select, _ in hd.TABLES if sql.startswith(select))
        page = [r for r in self.tables[name] if r["run_id"] in sql]
        limit, offset = map(int, re.search(r"limit (\d+) offset (\d+)", sql).groups())
        return page[offset:offset + limit]


@pytest.fixture
def server(monkeypatch):
    fake = FakeServer()
    monkeypatch.setattr(hd, "query", fake)
    monkeypatch.setattr(hd, "PAGE", 3)      # pages of 3 rows: every table is read in several queries
    fake.add(run_row(RUN_A, "Peter_test", "Peter D", feedback="fun"),
             [session_row(RUN_A, 0, "S1"), session_row(RUN_A, 1, "S1_Interlude", interlude=True)],
             [event_row(RUN_A, 0, 0, "session_start"), event_row(RUN_A, 0, 1, "fruit", 5.0, 5.0), event_row(RUN_A, 0, 2, "fruit", 0.0, 5.0),
              event_row(RUN_A, 0, 3, "teleport", payload={"x": 1}), event_row(RUN_A, 1, 0, "trial_end")],
             [trial_row(RUN_A, 1, 0, True), trial_row(RUN_A, 1, 1, False)])
    fake.add(run_row(RUN_B, "p7788", "Alice Smith"), [session_row(RUN_B, 0, "S1"), session_row(RUN_B, 1, "S1_Interlude", interlude=True)],
             [event_row(RUN_B, 0, 0, "fruit", 3.0, 3.0)], [trial_row(RUN_B, 1, 0, True)])
    fake.add(run_row(RUN_C, "someone", "xx PETER xx", status="in_progress", n_sessions=1), [session_row(RUN_C, 0, "S1")], [])
    return fake


def test_download_writes_the_tidy_tables_and_the_raw_layout(server, tmp_path):
    assert hd.download(tmp_path, log=lambda *_: None) == (3, 0)
    h = hd.load(tmp_path)
    assert set(h.participants["participant"]) == {"Peter_test", "p7788", "someone"}
    a = h.participants.set_index("run_id").loc[RUN_A]
    assert (a.signature, a.status, a.n_sessions, a.n_completed, a.feedback, a.on_server) == ("Peter D", "finished", 2, 2, "fun", 1)
    assert a.minutes == pytest.approx(18.5)
    s = h.sessions.set_index(["run_id", "session_index"])
    assert s.loc[(RUN_A, 0), ["kind", "block", "duration_s", "n_fruits", "wall_s"]].tolist() == ["session", "S1", 90.0, 2, 90.5]
    assert s.loc[(RUN_A, 1), ["kind", "block", "n_trials", "n_correct", "bonus"]].tolist() == ["interlude", "S1", 2, 1, 10.0]
    assert pd.isna(s.loc[(RUN_A, 1), "duration_s"]) and s.loc[(RUN_A, 0), "mean_frame_ms"] == 9.5
    assert len(h.events) == 6 and list(h.fruits["reward"][h.fruits.run_id == RUN_A]) == [5.0, 0.0]
    assert h.events.set_index(["run_id", "session_index", "seq"]).loc[(RUN_A, 0, 3), "payload"] == '{"x": 1}'
    assert len(h.interlude_trials) == 3 and h.interlude_trials["choice_correct"].sum() == 2
    traj = h.trajectory(RUN_A, 0)
    assert len(traj) == 5 and list(traj.columns) == ["t", "x", "z", "yaw", "pitch", "keys"] and traj["t"].iloc[-1] == pytest.approx(0.5)
    log = rundata.read_session(tmp_path / RUN_A / "00")                  # the raw layout reads like a local log
    assert log["session"]["name"] == "S1" and [e["type"] for e in log["events"]][:2] == ["session_start", "fruit"] and len(log["traj"]) == 5
    run_json = rundata.json.loads((tmp_path / RUN_A / "run.json").read_text())
    assert run_json["participant"] == "Peter_test" and run_json["signature"] == "Peter D" and "token_hash" not in run_json


def test_exclude_matches_the_id_or_the_signed_name_in_any_case_and_leaves_every_table(server, tmp_path):
    hd.download(tmp_path, log=lambda *_: None)
    h = hd.load(tmp_path, exclude=["peter"])
    assert list(h.participants["participant"]) == ["p7788"]             # "Peter_test" by ID, "xx PETER xx" by signature
    for table in (h.sessions, h.events, h.fruits, h.interlude_trials):
        assert set(table["run_id"]) <= {RUN_B}
    assert list(hd.load(tmp_path, status="finished").participants["participant"]) == ["Peter_test", "p7788"]
    assert hd.load(tmp_path, exclude=["peter", "alice", "SOME"]).participants.empty


def test_a_second_download_reads_only_the_run_list_and_a_changed_run_replaces_its_rows(server, tmp_path):
    hd.download(tmp_path, log=lambda *_: None)
    server.calls.clear()
    assert hd.download(tmp_path, log=lambda *_: None) == (0, 0) and server.calls == []
    # the in-progress run uploaded more and finished
    server.runs[2] = run_row(RUN_C, "someone", "xx PETER xx", n_sessions=1, last="2026-11-03 10:30:00+00")
    server.tables["events"] += [event_row(RUN_C, 0, 0, "fruit", 1.0, 1.0), event_row(RUN_C, 0, 1, "fruit", 2.0, 3.0)]
    assert hd.download(tmp_path, log=lambda *_: None) == (1, 0)
    assert all(RUN_C in q and RUN_A not in q for q in server.calls)
    assert hd.download(tmp_path, log=lambda *_: None) == (0, 0)
    assert hd.download(tmp_path, everything=True, log=lambda *_: None) == (3, 0)
    h = hd.load(tmp_path)
    assert h.fruits.groupby("run_id").size().to_dict() == {RUN_A: 2, RUN_B: 1, RUN_C: 2} and len(h.events) == 8
    assert h.participants.set_index("run_id").loc[RUN_C, "status"] == "finished"


def test_a_run_the_server_no_longer_has_is_kept_and_marked(server, tmp_path):
    hd.download(tmp_path, log=lambda *_: None)
    server.runs = server.runs[:1]
    assert hd.download(tmp_path, log=lambda *_: None) == (0, 2)
    h = hd.load(tmp_path)
    assert h.participants.set_index("run_id")["on_server"].to_dict() == {RUN_A: 1, RUN_B: 0, RUN_C: 0} and RUN_B in set(h.sessions["run_id"])


def test_load_before_a_download_says_what_to_do(tmp_path):
    with pytest.raises(FileNotFoundError, match="download"):
        hd.load(tmp_path)


def test_a_failing_query_raises_with_the_cli_message(monkeypatch):
    class Done:
        returncode, stdout, stderr = 1, "", "not logged in"
    monkeypatch.setattr(hd.subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(RuntimeError, match="not logged in"):
        hd.query("select 1")
