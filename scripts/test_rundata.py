import hashlib
import json
import math

import numpy as np
import pytest

import convert_legacy
import replay
import rundata
import trajectory_codec as codec
import world as world_mod

CFG = {"harvestRangeGapBase": 7.0, "harvestRangeGapPerRadius": 0.0, "harvestMaxAngle": 35.0, "fruitHarvestDuration": 0.8}
RUN = "11111111-2222-3333-4444-555555555555"


def traj(n=50):
    t = np.arange(1, n + 1) * 0.0083333
    return np.c_[t, 0.5 * t + 1.23456, np.zeros(n) + 7.0, np.linspace(0, 20.0004, n), np.zeros(n), np.arange(n) % 5]


EVENTS = [
    {"t": 0.0, "real": 0.0, "type": "session_start", "payload": {"x": 1.5, "yaw": 20.0}},
    {"t": 0.8, "real": 0.9, "type": "fruit", "tree_id": 3, "k": 0, "reward": 2.0, "running_total": 2.0},
    {"t": 1.0, "real": 1.1, "type": "trial_start", "payload": {"order": 0, "left": 1, "right": 2}},
]
SESSION = {"name": "S1", "config": CFG, "world_file": "S1_seed1.world", "world_sha256": "0" * 64, "completed": True, "final_score": 2.0}


def test_write_then_read_round_trips_every_stream(tmp_path):
    trials = [{"presented_order": 0, "trial_index": 4, "type": "t", "varied_feature": "shape", "stage_x": 1.5, "choice": "left",
               "choice_correct": 1, "timed_out": 0, "response_time": 2.25, "first_harvest_time": None, "left_fruits": 10}]
    folder = rundata.write_session(tmp_path, RUN, 3, SESSION, traj(), EVENTS, plan=[4, 2, 0], trials=trials)
    assert folder == tmp_path / RUN / "03"
    got = rundata.read_session(folder)
    assert got["session"]["name"] == "S1" and got["session"]["run_id"] == RUN and got["session"]["session_index"] == 3
    assert np.allclose(got["traj"], codec.quantize(traj()), atol=1e-9) and got["truncated"] == []
    e = got["events"]
    assert [x["seq"] for x in e] == [0, 1, 2] and e[0]["payload"] == {"x": 1.5, "yaw": 20.0} and e[0]["tree_id"] == -1
    assert e[1]["tree_id"] == 3 and e[1]["k"] == 0 and e[1]["reward"] == 2.0 and e[1]["payload"] == {}
    assert math.isnan(e[0]["reward"]) and math.isnan(e[2]["running_total"])
    assert got["plan"] == [4, 2, 0]
    assert got["trials"][0]["trial_index"] == 4 and got["trials"][0]["first_harvest_time"] is None and got["trials"][0]["seq"] == 0
    assert got["trials"][0]["choice"] == "left" and got["trials"][0]["left_fruits"] == 10


def test_a_session_without_interlude_files_has_none(tmp_path):
    got = rundata.read_session(rundata.write_session(tmp_path, RUN, 0, SESSION, traj(), EVENTS))
    assert got["plan"] is None and got["trials"] is None


def test_an_empty_session_reads_back(tmp_path):
    got = rundata.read_session(rundata.write_session(tmp_path, RUN, 0, SESSION, np.empty((0, 6)), []))
    assert got["traj"].shape == (0, 6) and got["events"] == []


@pytest.mark.parametrize("name,cut", [("trajectory.csv", "50,1.0,2"), ("events.csv", "3,2.0,fru")])
def test_a_file_cut_mid_line_loses_only_that_line(tmp_path, name, cut):
    folder = rundata.write_session(tmp_path, RUN, 0, SESSION, traj(), EVENTS)
    with open(folder / name, "a") as f:
        f.write(cut)
    got = rundata.read_session(folder)
    assert got["truncated"] == [name] and len(got["traj"]) == 50 and len(got["events"]) == 3


def test_a_bad_row_in_the_middle_is_an_error(tmp_path):
    folder = rundata.write_session(tmp_path, RUN, 0, SESSION, traj(), EVENTS)
    lines = (folder / "events.csv").read_text().splitlines()
    lines[2] = "1,oops"
    (folder / "events.csv").write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        rundata.read_session(folder)


def test_a_wrong_header_or_a_gap_in_the_trajectory_seq_is_an_error(tmp_path):
    folder = rundata.write_session(tmp_path, RUN, 0, SESSION, traj(), EVENTS)
    text = (folder / "trajectory.csv").read_text()
    (folder / "trajectory.csv").write_text(text.replace("\n5,", "\n6,", 1))
    with pytest.raises(ValueError):
        rundata.read_session(folder)
    (folder / "trajectory.csv").write_text(text.replace("seq,t", "t,seq", 1))
    with pytest.raises(ValueError):
        rundata.read_session(folder)


def test_the_trajectory_mirror_holds_the_quantized_values(tmp_path):
    folder = rundata.write_session(tmp_path, RUN, 0, SESSION, traj(), EVENTS)
    first = (folder / "trajectory.csv").read_text().splitlines()[1].split(",")
    assert first[0] == "0" and float(first[2]) == pytest.approx(round(traj()[0, 1] / 0.01) * 0.01) and first[-1] == "0"


# --- the online layout through replay --------------------------------------------------------------------------------

def _world(tmp_path, monkeypatch):
    w = world_mod.make_world("S1", 1)
    wfile = tmp_path / "S1_seed1.world"
    world_mod.export_unity(w, wfile)
    sha = hashlib.sha256(wfile.read_bytes()).hexdigest()
    (tmp_path / "_worlds").mkdir()
    (tmp_path / "_worlds" / f"{sha[:8]}_S1_seed1.world").write_bytes(wfile.read_bytes())
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    return w, sha


def test_load_session_log_reads_the_online_layout(tmp_path, monkeypatch):
    w, sha = _world(tmp_path, monkeypatch)
    session = dict(SESSION, world_sha256=sha)
    rundata.write_session(tmp_path, RUN, 1, session, traj(), EVENTS)
    log = replay.load_session_log(tmp_path / RUN / "01")
    assert log.online and log.name == "S1" and log.session_id == f"{RUN[:8]}/1" and log.final_score == 2.0
    assert len(log.bushes.pos) == w.n and log.traj.shape == (50, 6) and log.events[1]["type"] == "fruit"
    assert replay.fields(log.events[0]) == {"x": 1.5, "yaw": 20.0}


def test_replay_verifies_a_converted_legacy_log(tmp_path, monkeypatch):
    """A session played at the bush, written as the legacy DataLogger does, converts and still replays exactly."""
    w, sha = _world(tmp_path, monkeypatch)
    x, z = (float(v) for v in w.pos[0])
    r = float(w.canopy_radius[0])
    frames = [(x, z - r - 3.0, 0.0, 4)] * 300
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    rows = "\n".join(f"{(i + 1) / 100:.6f},{fx:.4f},{fz:.4f},{yaw:.4f},0.000,{k}" for i, (fx, fz, yaw, k) in enumerate(frames))
    (legacy / "trajectory.csv").write_text("t,x,z,yaw,pitch,keys\n" + rows + "\n")
    (legacy / "events.csv").write_text("t,real,type,tree_id,k,reward,running_total,note\n0.010000,0.100,session_start,,,,,x=1.5;policy=Hide\n")
    manifest = {"sessionId": "abcd1234", "sessionName": "S1", "isPractice": False, "isInterlude": False, "config": CFG,
                "world": {"seed": 1, "file": "S1_seed1.world", "sha256": sha}, "camera": {}, "display": {}, "frames": {},
                "startedAtUtc": "a", "endedAtUtc": "b", "completed": True, "finalScore": 0.0,
                "build": {"platform": "LinuxPlayer", "commit": "c", "dirty": False, "unityVersion": "6000"}}
    (legacy / "manifest.json").write_text(json.dumps(manifest))
    old = replay.load_session_log(legacy)
    # The legacy events do not list the harvest; use the replayed ones as the "logged" events, as test_replay does.
    legacy_events = [{"t": e["t"], "real": 0.0, "type": e["type"], "tree_id": e["tree_id"], "k": e.get("k", -1),
                      "reward": e.get("reward", float("nan")), "running_total": float("nan"), "note": ""} for e in replay.replay_harvests(old)]
    folder = convert_legacy.convert(legacy, tmp_path / "out", RUN, 0)
    new = replay.load_session_log(folder)
    new.events = [dict(e, payload={}) for e in legacy_events]
    new.manifest["final_score"] = sum(e["reward"] for e in legacy_events if e["type"] == "fruit")
    assert new.events and replay.verify(new)[0] == []


def test_note_strings_become_typed_payloads():
    assert convert_legacy.note_to_payload("x=1;z=2.5;policy=Hide;empty") == {"x": 1, "z": 2.5, "policy": "Hide"}
    assert convert_legacy.note_to_payload("") == {}


def test_a_local_copy_of_a_session_continued_elsewhere_may_start_after_seq_zero(tmp_path):
    folder = rundata.write_session(tmp_path, RUN, 0, SESSION, traj(), EVENTS)
    lines = (folder / "trajectory.csv").read_text().splitlines()
    shifted = [lines[0]] + [f"{int(l.split(',')[0]) + 40},{l.split(',', 1)[1]}" for l in lines[1:]]
    (folder / "trajectory.csv").write_text("\n".join(shifted) + "\n")
    assert len(rundata.read_session(folder)["traj"]) == 50
    shifted[10] = shifted[10].replace(shifted[10].split(",")[0], "99", 1)
    (folder / "trajectory.csv").write_text("\n".join(shifted) + "\n")
    with pytest.raises(ValueError):
        rundata.read_session(folder)
