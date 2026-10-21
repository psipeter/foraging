import json
from pathlib import Path

import numpy as np

import world as world_mod
from replay import Bushes, SessionLog, load_session_log, replay_harvests, steps, verify

CFG = {"harvestRangeGapBase": 7.0, "harvestRangeGapPerRadius": 0.0, "harvestMaxAngle": 35.0, "fruitHarvestDuration": 0.8}
HZ = 100.0


def toy_log(frames, events=(), n_fruits=10):
    """One bush of radius 1 at (0, 10); rewards 1, 2, ..., n_fruits. `frames` is a list of (x, z, yaw, keys)."""
    bushes = Bushes(pos=np.array([[0.0, 10.0]]), canopy_radius=np.array([1.0]),
                    fruit_reward=np.arange(1, n_fruits + 1)[None, :], value=np.array([3.0]))
    traj = np.array([[(i + 1) / HZ, x, z, yaw, 0.0, keys] for i, (x, z, yaw, keys) in enumerate(frames)])
    return SessionLog(Path("."), {"config": CFG}, traj, list(events), bushes)


def fruits(replayed):
    return [e for e in replayed if e["type"] == "fruit"]


def test_fruit_times_and_rewards():
    # Standing 3 from the center (edge 2 <= 7) facing it: Space pressed on frame 1, held 2.5 s -> fruits at 0.8, 1.6, 2.4 s.
    frames = [(0, 7.0, 0.0, 4)] * 250 + [(0, 7.0, 0.0, 0)] * 10
    got = fruits(replay_harvests(toy_log(frames)))
    assert [e["reward"] for e in got] == [1, 2, 3]
    assert np.allclose([e["t"] for e in got], [0.80, 1.60, 2.40], atol=1 / HZ)


def test_out_of_range_press_does_not_start_a_bout():
    # Edge distance 9 > 7: pressing does nothing, and walking into range with Space already held does not start one.
    frames = [(0, 0.0, 0.0, 4)] * 100 + [(0, 7.0, 0.0, 4)] * 200
    assert replay_harvests(toy_log(frames)) == []


def test_turning_away_pauses_the_timer_and_keeps_progress():
    # 0.5 s facing the bush, 1 s facing away (yaw 90), 0.5 s facing it again: the fruit arrives 0.3 s after the return.
    frames = [(0, 7.0, 0.0, 4)] * 50 + [(0, 7.0, 90.0, 4)] * 100 + [(0, 7.0, 0.0, 4)] * 50
    out = replay_harvests(toy_log(frames))
    assert [e["type"] for e in out if e["type"] != "harvest_press"] == ["harvest_pause", "harvest_resume", "fruit"]
    assert abs(fruits(out)[0]["t"] - 1.8) < 2 / HZ


def test_released_progress_carries_over_to_the_next_bout():
    frames = [(0, 7.0, 0.0, 4)] * 50 + [(0, 7.0, 0.0, 0)] * 20 + [(0, 7.0, 0.0, 4)] * 50
    out = replay_harvests(toy_log(frames))
    assert len(fruits(out)) == 1 and abs(fruits(out)[0]["t"] - 0.50 - 0.20 - 0.30) < 2 / HZ
    assert [e["type"] for e in out].count("harvest_press") == 2


def test_exhaustion_ends_the_bout_and_blocks_a_new_one():
    frames = [(0, 7.0, 0.0, 4)] * 900 + [(0, 7.0, 0.0, 0)] * 5 + [(0, 7.0, 0.0, 4)] * 100
    out = replay_harvests(toy_log(frames, n_fruits=3))
    assert [e["reward"] for e in fruits(out)] == [1, 2, 3]
    assert [e["type"] for e in out].count("harvest_press") == 1


def test_verify_flags_a_wrong_logged_reward():
    frames = [(0, 7.0, 0.0, 4)] * 100
    log = toy_log(frames)
    good = replay_harvests(log)
    log.events = [dict(e, real=0.0, k=e.get("k", -1), reward=e.get("reward", float("nan")), note="") for e in good]
    log.manifest["finalScore"] = 1.0
    assert verify(log)[0] == []
    log.events[-1]["reward"] += 1
    assert verify(log)[0]


def test_steps_resample_and_reward_per_step():
    frames = [(0, 7.0, 0.0, 4)] * 250
    log = toy_log(frames)
    log.events = replay_harvests(log)
    s = steps(log, 0.5)
    assert len(s["t"]) == 5 and s["reward"].sum() == 6 and s["harvesting"].all()


def test_load_session_log_reads_a_session_folder(tmp_path, monkeypatch):
    w = world_mod.make_world("S1", 1)
    wfile = tmp_path / "_worlds" / "S1_seed1.world"
    world_mod.export_unity(w, wfile)
    import hashlib
    sha = hashlib.sha256(wfile.read_bytes()).hexdigest()
    (tmp_path / "_worlds" / f"{sha[:8]}_S1_seed1.world").write_bytes(wfile.read_bytes())
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    folder = tmp_path / "abcd1234"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps({"sessionId": "abcd1234", "config": CFG,
                                                      "world": {"file": "S1_seed1.world", "sha256": sha}}))
    (folder / "trajectory.csv").write_text("t,x,z,yaw,pitch,keys\n0.016667,0.0000,0.0000,10.0000,0.000,0\n")
    (folder / "events.csv").write_text("t,real,type,tree_id,k,reward,running_total,note\n0.000000,0.000,session_start,,,,,x=0\n")
    log = load_session_log("abcd1234")
    assert len(log.bushes.pos) == w.n and np.array_equal(log.bushes.fruit_reward, w.fruit_reward)
    assert log.events[0]["type"] == "session_start" and log.traj.shape == (1, 6)
