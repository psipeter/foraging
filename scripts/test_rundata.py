import hashlib
from pathlib import Path
import math

import numpy as np
import pytest

import replay
import rundata
import trajectory_codec as codec
import world as world_mod


CFG = {"harvestRangeGapBase": 7.0, "harvestRangeGapPerRadius": 0.0, "harvestMaxAngle": 35.0, "fruitHarvestDuration": 0.8}
RUN = "11111111-2222-3333-4444-555555555555"


def traj(n=50):
    t = np.arange(1, n + 1) * 0.0083333
    return codec.quantize(np.c_[t, 0.5 * t + 1.23456, np.zeros(n) + 7.0, np.linspace(0, 20.0004, n), np.zeros(n), np.arange(n) % 5])


EVENTS = [
    {"t": 0.0, "real": 0.0, "type": "session_start", "payload": {"x": 1.5, "yaw": 20.0}},
    {"t": 0.8, "real": 0.9, "type": "fruit", "tree_id": 3, "k": 0, "reward": 2.0, "running_total": 2.0},
    {"t": 1.0, "real": 1.1, "type": "rank_set_start", "payload": {"set": 0}},
]
SESSION = {"name": "FIX_T0", "config": CFG, "world_file": "FIX_T0_seed1.world", "world_sha256": "0" * 64, "completed": True, "final_score": 2.0}


BUSHES = [{"id": 5, "slot": 0, "shape": 0.25, "color": 0.5, "moisture": 0.5, "value": 1.5, "rank": 2, "start_time": 3.0, "finish_time": 5.5, "fruits": 10},
          {"id": 6, "slot": 1, "shape": 0.75, "color": 0.125, "moisture": 0.5, "value": 2.5, "rank": 1, "start_time": 1.0, "finish_time": 2.5, "fruits": 10},
          {"id": 7, "slot": 2, "shape": 0.5, "color": 0.9, "moisture": 0.5, "value": 0.5, "rank": None, "start_time": None, "finish_time": None, "fruits": 0}]


def test_write_then_read_round_trips_every_stream(tmp_path):
    sets = [{"seq": 0, "set_index": 4, "pool_index": 7, "start_x": 1.5, "start_z": 2.5, "timed_out": 0, "response_time": 2.25,
             "first_harvest_time": None, "bonus": 1.0, "paused_seconds": 3.5, "set_size": 3, "correct_pairs": 2, "total_pairs": 3, "bushes": BUSHES}]
    folder = rundata.write_session(tmp_path, RUN, 3, SESSION, traj(), EVENTS, sets=sets)
    assert folder == tmp_path / RUN / "03"
    got = rundata.read_session(folder)
    assert got["session"]["name"] == "FIX_T0" and got["session"]["run_id"] == RUN and got["session"]["session_index"] == 3
    assert np.allclose(got["traj"], traj(), atol=1e-9) and got["truncated"] == []
    e = got["events"]
    assert [x["seq"] for x in e] == [0, 1, 2] and e[0]["payload"] == {"x": 1.5, "yaw": 20.0} and e[0]["tree_id"] == -1
    assert e[1]["tree_id"] == 3 and e[1]["k"] == 0 and e[1]["reward"] == 2.0 and e[1]["payload"] == {}
    assert math.isnan(e[0]["reward"]) and math.isnan(e[2]["running_total"])
    s0 = got["sets"][0]
    assert s0["set_index"] == 4 and s0["pool_index"] == 7 and s0["first_harvest_time"] is None and s0["seq"] == 0
    assert s0["bushes"] == BUSHES and s0["set_size"] == 3 and s0["correct_pairs"] == 2 and s0["total_pairs"] == 3
    assert s0["bonus"] == 1.0 and s0["paused_seconds"] == 3.5 and s0["start_x"] == 1.5
    assert (folder / "ranking_sets.csv").exists()


def test_a_session_without_ranking_sets_has_none(tmp_path):
    got = rundata.read_session(rundata.write_session(tmp_path, RUN, 0, SESSION, traj(), EVENTS))
    assert got["sets"] is None


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


# --- the online layout through replay --------------------------------------------------------------------------------

def _world(tmp_path, monkeypatch):
    w = world_mod.make_world("FIX_T0", 1)
    wfile = tmp_path / "FIX_T0_seed1.world"
    world_mod.export_unity(w, wfile)
    sha = hashlib.sha256(wfile.read_bytes()).hexdigest()
    (tmp_path / "_worlds").mkdir()
    (tmp_path / "_worlds" / f"{sha[:8]}_FIX_T0_seed1.world").write_bytes(wfile.read_bytes())
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    return w, sha


def test_load_session_log_reads_the_online_layout(tmp_path, monkeypatch):
    w, sha = _world(tmp_path, monkeypatch)
    session = dict(SESSION, world_sha256=sha)
    rundata.write_session(tmp_path, RUN, 1, session, traj(), EVENTS)
    log = replay.load_session_log(tmp_path / RUN / "01")
    assert log.name == "FIX_T0" and log.session_id == f"{RUN[:8]}/1" and log.final_score == 2.0
    assert len(log.bushes.pos) == w.n and log.traj.shape == (50, 6) and log.events[1]["type"] == "fruit"
    assert log.events[0]["payload"] == {"x": 1.5, "yaw": 20.0}


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


def test_archive_worlds_takes_the_files_from_git_at_the_build_commit(tmp_path, capsys):
    import subprocess
    import server_admin
    repo = tmp_path / "repo"
    folder = repo / "Assets" / "StreamingAssets" / "Experiments" / "CF"
    folder.mkdir(parents=True)
    name, blob = "CF_S1_seed201.world", b"FWLD fake world bytes"
    (folder / name).write_bytes(blob)
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, capture_output=True, check=True)
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "worlds")
    sha = hashlib.sha256(blob).hexdigest()
    out = tmp_path / "out"
    server_admin.archive_worlds("HEAD", [{"world_file": name, "world_sha256": sha}, {"world_file": name, "world_sha256": "0" * 64}], out, repo=repo)
    assert (out / "_worlds" / f"{sha[:8]}_{name}").read_bytes() == blob
    assert [p.name for p in (out / "_worlds").iterdir()] == [f"{sha[:8]}_{name}"]          # the file with a wrong sha is not written
    assert "not in git" in capsys.readouterr().err
    old = repo / "Assets" / "StreamingAssets" / "Worlds"                     # a build from before experiments kept its worlds in one folder
    old.mkdir(parents=True)
    (old / "FIX_T0_seed1.world").write_bytes(b"old world")
    git("add", ".")
    git("commit", "-q", "-m", "old layout")
    old_sha = hashlib.sha256(b"old world").hexdigest()
    server_admin.archive_worlds("HEAD", [{"world_file": "FIX_T0_seed1.world", "world_sha256": old_sha}], out, repo=repo)
    assert (out / "_worlds" / f"{old_sha[:8]}_FIX_T0_seed1.world").read_bytes() == b"old world"


def test_a_release_counts_the_sessions_of_the_experiment_asset_at_its_commit(tmp_path):
    import subprocess
    import server_admin
    folder = tmp_path / "Assets" / "ScriptableObjects" / "Experiments" / "XX"
    folder.mkdir(parents=True)
    entry = "  - {fileID: 11400000, guid: a2c1af91c6840f167b2e2427d351cbd4, type: 2}\n"
    (folder / "XX.asset").write_text("  requires:\n  - TUT\n  sessions:\n" + entry * 3 + "  countsTowardTotal: 1\n  downloadPerSession: 0\n")
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, capture_output=True, check=True)
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "asset")
    assert server_admin.sessions_in_build("HEAD", "XX", repo=tmp_path) == 3            # the requires entry and the later fields are not sessions
    with pytest.raises(ValueError):
        server_admin.sessions_in_build("HEAD", "NOPE", repo=tmp_path)
