import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import replay
import rundata
import world as world_mod
from replay import Bushes, SessionLog, load_session_log, replay_harvests, steps, verify


CFG = {"harvestRangeGapBase": 7.0, "harvestRangeGapPerRadius": 0.0, "harvestMaxAngle": 35.0, "fruitHarvestDuration": 0.8}
HZ = 100.0


def multi_log(bushes, frames, events=(), n_fruits=10):
    """`bushes` is [(x, z, radius)]; bush i pays 100*(i+1) + k for its k-th fruit. `frames` is a list of (x, z, yaw, keys) at HZ."""
    bush = Bushes(pos=np.array([[b[0], b[1]] for b in bushes], dtype=float), canopy_radius=np.array([b[2] for b in bushes], dtype=float),
                  fruit_reward=np.array([[100 * (i + 1) + k for k in range(n_fruits)] for i in range(len(bushes))]))
    traj = np.array([[(i + 1) / HZ, x, z, yaw, 0.0, keys] for i, (x, z, yaw, keys) in enumerate(frames)])
    return SessionLog(Path("."), {"config": CFG}, traj, list(events), bush)


def toy_log(frames, events=(), n_fruits=10):
    """One bush of radius 1 at (0, 10); rewards 1, 2, ..., n_fruits."""
    log = multi_log([(0.0, 10.0, 1.0)], frames, events, n_fruits)
    log.bushes.fruit_reward = np.arange(1, n_fruits + 1)[None, :]
    return log


def fruits(replayed):
    return [e for e in replayed if e["type"] == "fruit"]


def test_fruit_times_and_rewards():
    # Standing 3 from the center (edge 2 <= 7) facing it: Space pressed on frame 1, held 2.5 s -> fruits at 0.8, 1.6, 2.4 s.
    frames = [(0, 7.0, 0.0, 4)] * 250 + [(0, 7.0, 0.0, 0)] * 10
    got = fruits(replay_harvests(toy_log(frames)))
    assert [e["reward"] for e in got] == [1, 2, 3]
    assert np.allclose([e["t"] for e in got], [0.80, 1.60, 2.40], atol=1 / HZ) and abs(got[0]["t"] - 0.80) < 0.5 / HZ


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


def logged(log, extra=()):
    """Events as the DataLogger writes them: the replayed harvest events plus `extra`, in clock order."""
    ev = [dict(e, real=0.0, k=e.get("k", -1), reward=e.get("reward", float("nan")), payload={}) for e in replay_harvests(log)]
    ev += [dict(type=t, t=at, real=0.0, k=-1, reward=float("nan"), payload={}) for t, at in extra]
    return sorted(ev, key=lambda e: e["t"])


def test_a_screen_opening_on_the_exhausting_fruit_still_verifies():
    # The practice message opens in the frame the 3rd (last) fruit exhausts the bush: Space stays held through the
    # screen and Enter. The logger writes that frame's row, then the pause; the clock stands still while paused, so
    # rows stay contiguous and the held key gives no new press edge on resume.
    frames = [(0, 7.0, 0.0, 4)] * 400
    log = toy_log(frames, n_fruits=3)
    t_last = [e["t"] for e in fruits(replay_harvests(log))][-1]
    assert abs(t_last - 2.4) < 2 / HZ
    log.events = logged(log, extra=[("pause", t_last), ("resume", t_last)])
    log.manifest["final_score"] = 6.0
    assert verify(log)[0] == []
    assert [e["type"] for e in log.events].count("harvest_press") == 1
    # Every fruit lands on a trajectory row's time (the frame has a row), in non-decreasing event order.
    row_t = set(np.round(log.traj[:, 0], 6))
    assert all(round(e["t"], 6) in row_t for e in log.events if e["type"] == "fruit")
    assert all(a["t"] <= b["t"] for a, b in zip(log.events, log.events[1:]))


def test_verify_flags_a_fruit_whose_frame_has_no_row():
    # The old logger lost the frame's row when a screen opened mid-frame: the last fruit has no row, replay can't see it.
    frames = [(0, 7.0, 0.0, 4)] * 400
    log = toy_log(frames, n_fruits=3)
    log.events = logged(log)
    t_last = [e["t"] for e in log.events if e["type"] == "fruit"][-1]
    log.traj = log.traj[np.abs(log.traj[:, 0] - t_last) > 1e-9]
    log.traj[log.traj[:, 0] > t_last, 5] = 0
    log.manifest["final_score"] = 6.0
    assert verify(log)[0]


def test_a_press_latched_during_a_pause_acts_on_the_first_frame_with_time():
    # Space pressed and held during a screen: no row exists then, so the replay sees the key edge on the first row
    # after it (keys 0 -> 4), which is where HarvestManager now consumes the latched press.
    frames = [(0, 7.0, 0.0, 0)] * 20 + [(0, 7.0, 0.0, 4)] * 100
    out = replay_harvests(toy_log(frames))
    presses = [e for e in out if e["type"] == "harvest_press"]
    assert len(presses) == 1 and abs(presses[0]["t"] - 0.21) < 2 / HZ


def test_verify_flags_a_release_the_keys_do_not_explain():
    # Space stays held and the bush has fruit left, yet the log ends the bout after the 3rd fruit: a game bug that the
    # old "any logged release is forced" rule accepted. Only a rank_set_end or the session's last frames may force one.
    frames = [(0, 7.0, 0.0, 4)] * 400
    log = toy_log(frames, n_fruits=10)
    log.events = logged(log)
    fr = [e for e in log.events if e["type"] == "fruit"]
    log.events = [e for e in log.events if e["t"] <= fr[2]["t"] and e["type"] != "fruit" or e["type"] == "fruit" and e["t"] <= fr[2]["t"]]
    log.events.append(dict(type="harvest_release", t=fr[2]["t"], tree_id=0, real=0.0, k=-1, reward=float("nan"), payload={}))
    assert verify(log)[0]
    # The same release is accepted when a rank_set_end coincides with it (a ranking set cancelling the bout).
    log.events.append(dict(type="rank_set_end", t=fr[2]["t"], real=0.0, tree_id=-1, k=-1, reward=float("nan"), payload={}))
    log.manifest.pop("final_score", None)
    assert not [p for p in verify(log)[0] if p.startswith(("harvest_release", "fruit", "harvest_press"))]


def test_steps_holds_the_old_pose_until_the_row_after_a_teleport():
    # The teleport is logged at the row that still has the old pose; the jump shows in the next row. Steps between
    # those two rows must not be interpolated across the jump.
    bushes = Bushes(pos=np.array([[0.0, 10.0]]), canopy_radius=np.array([1.0]),
                    fruit_reward=np.ones((1, 3)))
    t = np.arange(1, 6) / 2.0                       # rows every 0.5 s
    traj = np.array([[ti, x, 0.0, 0.0, 0.0, 0] for ti, x in zip(t, [0, 0, 0, 300, 300])])
    log = SessionLog(Path("."), {"config": CFG}, traj, [dict(type="teleport", t=1.5, real=0.0, tree_id=-1, k=-1,
                     reward=float("nan"), payload={})], bushes)
    s = steps(log, 0.1)
    between = (s["t"] > 1.5 + 1e-9) & (s["t"] < 2.0 - 1e-9)
    assert between.any() and (s["x"][between] == 0.0).all()


def two_bush_log(frames, events=()):
    """Two bushes of radius 1 at (-6, 10) and (6, 10); the player stands at (0, 10), in range of both. Facing yaw -90 looks at
    the first, +90 at the second. `frames` are (yaw, keys)."""
    return multi_log([(-6.0, 10.0, 1.0), (6.0, 10.0, 1.0)], [(0.0, 10.0, yaw, keys) for yaw, keys in frames], events)


def presses(replayed):
    return [e["tree_id"] for e in replayed if e["type"] == "harvest_press"]


SWITCHING = [(-90.0, 4)] * 100 + [(-90.0, 0)] * 10 + [(90.0, 4)] * 100


def test_without_a_lock_the_player_can_switch_bushes():
    out = replay_harvests(two_bush_log(SWITCHING))
    assert presses(out) == [0, 1]


def _ev(kind, t, **payload):
    return dict(type=kind, t=t, real=0.0, tree_id=-1, k=-1, reward=float("nan"), payload=payload)


# --- geometry of the cone, focus choice and range (HarvestManager.Measure) -----------------------------------------

def press_events(out):
    return [e for e in out if e["type"] == "harvest_press"]


def test_the_cone_uses_the_signed_yaw():
    # Bush at azimuth +45 degrees (x=3, z=3 from the player at the origin... player at (0, 7), bush at (3, 10)).
    bushes = [(3.0, 10.0, 1.0)]
    assert press_events(replay_harvests(multi_log(bushes, [(0, 7.0, 45.0, 4)] * 5)))        # facing it
    assert not press_events(replay_harvests(multi_log(bushes, [(0, 7.0, -45.0, 4)] * 5)))   # facing the mirror image
    assert not press_events(replay_harvests(multi_log(bushes, [(0, 7.0, 135.0, 4)] * 5)))   # facing away


def test_the_cone_is_widened_by_the_canopys_angular_radius():
    # Distance 3 (canopy radius 1): angular radius asin(1/3) = 19.5 degrees, so the cone reaches 35 + 19.5 = 54.5.
    bushes = [(0.0, 10.0, 1.0)]
    for yaw, expected in ((50.0, True), (54.0, True), (56.0, False), (-50.0, True), (-56.0, False)):
        assert bool(press_events(replay_harvests(multi_log(bushes, [(0, 7.0, yaw, 4)] * 5)))) is expected, yaw


def test_focus_prefers_the_smaller_bearing_over_the_smaller_edge_distance():
    # A is dead ahead (bearing 0, edge 2); B is nearer (edge 1.5) but 40 degrees off (bearing 16): A wins.
    a = (0.0, 10.0, 1.0)
    b = (2.5 * np.sin(np.radians(40)), 7.0 + 2.5 * np.cos(np.radians(40)), 1.0)
    out = replay_harvests(multi_log([a, b], [(0, 7.0, 0.0, 4)] * 90))
    assert press_events(out)[0]["tree_id"] == 0 and fruits(out)[0]["reward"] == 100
    out = replay_harvests(multi_log([b, a], [(0, 7.0, 0.0, 4)] * 90))      # the order of the table does not matter
    assert press_events(out)[0]["tree_id"] == 1 and fruits(out)[0]["reward"] == 200


def test_equal_bearings_are_broken_by_the_edge_distance():
    near, far = (0.0, 9.0, 1.0), (0.0, 12.0, 1.0)
    out = replay_harvests(multi_log([far, near], [(0, 7.0, 0.0, 4)] * 90))
    assert press_events(out)[0]["tree_id"] == 1


def test_a_bout_pauses_when_the_player_walks_out_of_range():
    # Start harvesting in range, then walk back (still facing the bush): the timer pauses with no fruit.
    frames = [(0, 7.0, 0.0, 4)] * 40 + [(0, 0.0, 0.0, 4)] * 200 + [(0, 7.0, 0.0, 4)] * 45
    out = replay_harvests(multi_log([(0.0, 10.0, 1.0)], frames))
    kinds = [e["type"] for e in out]
    assert kinds == ["harvest_press", "harvest_pause", "harvest_resume", "fruit"], kinds
    assert abs(fruits(out)[0]["t"] - (0.40 + 2.00 + 0.40)) < 2 / HZ      # 0.4 s before + 0.4 s after the 2 s outside


def test_range_grows_with_the_canopy_radius_term():
    cfg = dict(CFG, harvestRangeGapPerRadius=2.0)      # gap = 7 + 2 * radius
    bush = [(0.0, 10.0, 3.0)]                           # radius 3: reach edge 13, i.e. the player may stand 3 + 13 = 16 away
    log = multi_log(bush, [(0, -5.0, 0.0, 4)] * 5)      # dist 15, edge 12
    log.manifest = {"config": cfg}
    assert press_events(replay_harvests(log))
    log.manifest = {"config": CFG}                      # gap 7: edge 12 is out of range
    assert not press_events(replay_harvests(log))


# --- verify: tolerances and the ignored tail -----------------------------------------------------------------------

def test_verify_flags_a_fruit_logged_50_ms_off():
    frames = [(0, 7.0, 0.0, 4)] * 250
    log = toy_log(frames)
    log.events = logged(log)
    log.manifest["final_score"] = 6.0
    assert verify(log)[0] == []
    for e in log.events:
        if e["type"] == "fruit":
            e["t"] += 0.05
    assert verify(log)[0]


def test_verify_ignores_events_on_the_last_frame_only():
    frames = [(0, 7.0, 0.0, 4)] * 150
    log = toy_log(frames)
    log.events = logged(log)
    log.manifest["final_score"] = 1.0
    last = float(log.traj[-1, 0])
    log.events.append(dict(type="harvest_release", t=last, tree_id=0, real=0.0, k=-1, reward=float("nan"), payload={}))
    assert verify(log)[0] == []                       # the session-end release on the last frame is not compared
    log.events[-1]["t"] = last - 0.5
    assert verify(log)[0]                             # ...but an early extra release is
    # The game ends the bout on the second-to-last frame (the sun's clock reaches the duration there), however long the last frame is.
    log.traj[-1, 0] += 0.05
    log.events[-1]["t"] = float(log.traj[-2, 0])
    assert verify(log)[0] == []


# --- steps: per-step reward and harvesting flags --------------------------------------------------------------------

def test_steps_reward_and_harvesting_are_placed_in_the_right_steps():
    # Space down on rows 1.00..2.60 (press at t = 1.0), fruits at 1.8 and 2.6; steps of 0.5 s.
    frames = [(0, 7.0, 0.0, 0)] * 99 + [(0, 7.0, 0.0, 4)] * 161 + [(0, 7.0, 0.0, 0)] * 40
    log = toy_log(frames)
    log.events = replay_harvests(log)
    s = steps(log, 0.5)
    assert list(s["reward"]) == [0, 0, 0, 1, 0, 2], list(s["reward"])
    assert list(s["harvesting"]) == [0, 1, 1, 1, 1, 1]     # a bout flags the step before its press too (dt of lead)
    assert (s["tree"][s["harvesting"] == 1] == 0).all() and (s["tree"][s["harvesting"] == 0] == -1).all()


# --- loading: hash checks ---------------------------------------------------------------------------------------------------------------

def _archive(tmp_path, name, content):
    d = tmp_path / "_worlds"
    d.mkdir(exist_ok=True)
    sha = hashlib.sha256(content).hexdigest()
    (d / f"{sha[:8]}_{name}").write_bytes(content)
    return sha


def _session(tmp_path, monkeypatch, **row):
    """An S1 session folder of the online layout, its world archived under tmp_path/_worlds."""
    wfile = tmp_path / "S1_seed1.world"
    world_mod.export_unity(world_mod.make_world("S1", 1), wfile)
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    row = {"name": "S1", "config": CFG, "world_file": "S1_seed1.world", "world_sha256": _archive(tmp_path, "S1_seed1.world", wfile.read_bytes()), **row}
    traj = np.array([[0.01, 0.0, 0.0, 0.0, 0.0, 0], [0.02, 0.0, 0.0, 0.0, 0.0, 0]])
    return rundata.write_session(tmp_path, "run", 0, row, traj, [{"t": 0.01, "real": 0.1, "type": "session_start"}])


def test_find_world_file_rejects_a_file_with_the_wrong_hash(tmp_path, monkeypatch):
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    monkeypatch.setattr("replay.WORLD_DIR", tmp_path / "none")
    sha = _archive(tmp_path, "x.world", b"original")
    assert replay.find_world_file("x.world", sha).read_bytes() == b"original"
    (tmp_path / "_worlds" / f"{sha[:8]}_x.world").write_bytes(b"tampered")
    with pytest.raises(FileNotFoundError):
        replay.find_world_file("x.world", sha)


def test_verify_reports_a_file_that_was_cut_mid_line(tmp_path, monkeypatch):
    folder = _session(tmp_path, monkeypatch)
    with open(folder / "trajectory.csv", "a") as f:
        f.write("2,0.03,1.0")                                      # no trailing newline: the write was interrupted
    log = load_session_log(folder)
    assert len(log.traj) == 2 and log.truncated == ["trajectory.csv"]
    assert any("trajectory.csv ended mid-line" in p for p in verify(log)[0])


def test_each_verify_score_check_stands_on_its_own():
    frames = [(0, 7.0, 0.0, 4)] * 250
    log = toy_log(frames)
    log.events = logged(log)
    log.manifest["final_score"] = 6.0
    assert verify(log)[0] == []
    fr = [e for e in log.events if e["type"] == "fruit"]
    fr[0]["reward"] += 1.0
    fr[1]["reward"] -= 1.0                       # the per-fruit rewards are wrong but still sum to final_score
    assert any(p.startswith("fruit") for p in verify(log)[0])
    fr[0]["reward"] -= 1.0
    fr[1]["reward"] += 1.0
    log.manifest["final_score"] = 7.0             # the fruits are right but final_score is not their sum
    assert any("final_score" in p for p in verify(log)[0])


# --- a session continued after an interruption (session_resume) ------------------------------------------------------

def test_a_resume_forgets_the_open_bout_and_the_progress_on_the_fruit_being_picked():
    # 0.5 s harvested, then the game restarts at t = 1.0 and Space is held from the first frame after: progress on the first fruit
    # starts again from zero, so the fruit arrives 0.8 s after the resume, not 0.3 s.
    frames = [(0, 7.0, 0.0, 4)] * 50
    log = toy_log(frames)
    after = np.array([[1.0 + (i + 1) / HZ, 0.0, 7.0, 0.0, 0.0, 4] for i in range(100)])
    log.traj = np.vstack([log.traj, after])
    log.events = [dict(type="session_resume", t=1.0, real=0.0, tree_id=-1, k=-1, reward=float("nan"), running_total=float("nan"), payload={})]
    got = fruits(replay_harvests(log))
    assert len(got) == 1 and abs(got[0]["t"] - (1.0 + 0.8)) < 2 / HZ and got[0]["k"] == 0


def test_fruits_taken_before_the_resume_count_even_when_their_frames_were_never_uploaded():
    # Fruits 0 and 1 were taken at t = 0.8 and 1.6, but the last uploaded frame is at 0.5: they are only in the log. After the
    # resume the next fruit is number 2 and the running total continues.
    log = toy_log([(0, 7.0, 0.0, 4)] * 50)
    log.traj = np.vstack([log.traj, np.array([[2.0 + (i + 1) / HZ, 0.0, 7.0, 0.0, 0.0, 4] for i in range(100)])])
    nan = float("nan")
    log.events = [dict(type="fruit", t=0.8, real=0.0, tree_id=0, k=0, reward=1.0, running_total=1.0, payload={}),
                  dict(type="fruit", t=1.6, real=0.0, tree_id=0, k=1, reward=2.0, running_total=3.0, payload={}),
                  dict(type="session_resume", t=2.0, real=0.0, tree_id=-1, k=-1, reward=nan, running_total=nan, payload={})]
    got = fruits(replay_harvests(log))
    assert [(e["k"], e["reward"], e["running_total"]) for e in got] == [(2, 3.0, 6.0)]


def test_verify_leaves_out_the_events_of_the_gap_and_still_checks_the_rest():
    log = toy_log([(0, 7.0, 0.0, 4)] * 50)
    log.traj = np.vstack([log.traj, np.array([[2.0 + (i + 1) / HZ, 0.0, 7.0, 0.0, 0.0, 4] for i in range(100)])])
    nan = float("nan")
    gap = [dict(type="fruit", t=0.8, real=0.0, tree_id=0, k=0, reward=1.0, running_total=1.0, payload={}),
           dict(type="fruit", t=1.6, real=0.0, tree_id=0, k=1, reward=2.0, running_total=3.0, payload={}),
           dict(type="session_resume", t=2.0, real=0.0, tree_id=-1, k=-1, reward=nan, running_total=nan, payload={})]
    after = [dict(e, real=0.0, k=e.get("k", -1), reward=e.get("reward", nan), running_total=e.get("running_total", nan), payload={})
             for e in replay_harvests(dataclasses.replace(log, events=gap))]
    log.events = sorted(gap + after, key=lambda e: e["t"])
    log.manifest["final_score"] = 6.0
    assert verify(log)[0] == []
    after[-1]["reward"] += 1.0                          # a wrong reward after the resume is still caught
    log.manifest["final_score"] = 7.0
    assert any(p.startswith("fruit") for p in verify(log)[0])



def test_a_resume_does_not_double_count_the_fruits_replayed_before_it():
    # The fruit before the resume is replayed from frames (total 1) and logged without a running_total: the rebuild at the resume
    # starts from zero, so the next fruit (k = 1, reward 2) brings the total to 3, not 4.
    nan = float("nan")
    log = toy_log([(0, 7.0, 0.0, 4)] * 100)
    log.traj = np.vstack([log.traj, np.array([[1.0 + (i + 1) / HZ, 0.0, 7.0, 0.0, 0.0, 4] for i in range(100)])])
    log.events = [dict(type="fruit", t=0.8, real=0.0, tree_id=0, k=0, reward=1.0, running_total=nan, payload={}),
                  dict(type="session_resume", t=1.0, real=0.0, tree_id=-1, k=-1, reward=nan, running_total=nan, payload={})]
    assert [e["running_total"] for e in fruits(replay_harvests(log))] == [1.0, 3.0]


def test_a_logged_fruit_decides_a_tie_between_frame_sums_and_the_fruit_time():
    # Browser frame times are whole milliseconds (here a 0.2 s fruit, press on the row at 2.818 after one at 2.817), so the
    # frames sum to the fruit time exactly and double arithmetic fires one frame after the game's float32 did.
    ts = [round(2.805 + i * 0.001, 3) for i in range(400)]
    log = toy_log([(0, 7.0, 0.0, 0)] * 400)
    log.traj = np.array([[t, 0.0, 7.0, 0.0, 0.0, 4 if i >= 13 else 0] for i, t in enumerate(ts)])
    log.manifest["config"] = dict(CFG, fruitHarvestDuration=0.2)
    log.manifest["final_score"] = 1.0
    assert abs(fruits(replay_harvests(log))[0]["t"] - 3.018) < 1e-9       # without a logged fruit: the plain comparison
    log.events = [dict(e, real=0.0, payload={}) for e in replay_harvests(log)]
    fruit = [e for e in log.events if e["type"] == "fruit"][0]
    fruit["t"] = 3.017                                                    # the game's fruit, on the tied frame
    assert verify(log)[0] == [] and abs(fruits(replay_harvests(log))[0]["t"] - 3.017) < 1e-9
    fruit["t"] = 3.015                                                    # two frames early is not a tie: still caught
    assert any(p.startswith("fruit") for p in verify(log)[0])


def test_a_pulled_runs_world_archive_next_to_its_folder_is_found(tmp_path, monkeypatch):
    # server_admin pull writes <out>/<run>/<session> and <out>/_worlds: replay finds the worlds from the session folder alone.
    folder = _session(tmp_path, monkeypatch)
    monkeypatch.setattr("replay.DATA_DIR", tmp_path / "elsewhere")
    monkeypatch.setattr("replay.WORLD_DIR", tmp_path / "none")
    assert len(load_session_log(folder).bushes.pos) > 0


# --- a ranking break inside a foraging session (RankingBreak) -------------------------------------------------------------------------

# --- a ranking break inside a foraging session (RankingBreak) -----------------------------------------------------

BREAK = {"config": dict(CFG, rankingFruitSeconds=0.05, rankingAimTolerance=1.5)}
SET_ID = 101


def keyed(spans, total=400, x=0.0, z=7.0):
    """Frames at HZ standing at (x, z) facing +z with Space held over each (from, to) span in seconds."""
    keys = [0] * total
    for lo, hi in spans:
        for i in range(int(round(lo * HZ)), int(round(hi * HZ))):
            keys[i] = 4
    return [(x, z, 0.0, k) for k in keys]


def break_events(start=1.0, rank_set=1.3, go=1.5, set_end=2.5, end=2.7, z=67.0):
    """One real bush (radius 1, at (0, 10)) and one ranking set of one bush 60 units from the player, as RankingBreak logs them."""
    both = {"break": 1}
    return [_ev("rank_break_start", start, **both),
            _ev("rank_set", rank_set, **{"break": 1, "set": 0, "fruits": 10, "bushes": [{"id": SET_ID, "x": 0.0, "z": z, "radius": 1.0, "shape": 0.5}]}),
            _ev("rank_go", go, **both), _ev("rank_set_end", set_end, **both), _ev("rank_break_end", end, **both)]


def break_log(spans=((1.05, 1.6), (1.7, 2.6), (3.0, 4.0)), **kwargs):
    log = toy_log(keyed(spans), n_fruits=10)
    log.manifest = BREAK
    log.events = break_events(**kwargs)
    return log


def test_a_break_harvest_is_aimed_quick_and_pays_nothing_and_the_foraging_harvest_resumes_after_it():
    out = replay_harvests(break_log())
    got = fruits(out)
    ranked = [e for e in got if e["tree_id"] == SET_ID]
    assert len(ranked) == 10 and all(e["reward"] == 0.0 for e in ranked)
    assert np.allclose(np.diff([e["t"] for e in ranked]), 0.05, atol=2 / HZ)       # quick: rankingFruitSeconds a fruit, not the session's 0.8
    real = [e for e in got if e["tree_id"] == 0]
    assert len(real) == 1 and real[0]["reward"] == 1.0 and abs(real[0]["t"] - 3.81) < 3 / HZ         # the main task's rules again: in range, 0.8 s a fruit
    assert real[0]["running_total"] == 1.0
    assert [e["tree_id"] for e in press_events(out)] == [SET_ID, 0]


def test_a_press_before_the_set_goes_live_starts_no_bout():
    # Space was pressed at 1.05 s (the break had started: presses are discarded until rank_go at 1.5) and is still held at 1.5: no press edge at the go
    out = replay_harvests(break_log(spans=((1.05, 1.6),)))
    assert press_events(out) == []


def test_the_real_bush_cannot_be_harvested_during_a_break_and_the_set_bush_not_after_it():
    # standing at the real bush through the whole break pressing: nothing starts until the set is live, and only the set's bush can (the real bush is hidden)
    out = replay_harvests(break_log(spans=((1.7, 2.6), (2.8, 3.0))))
    assert [e["tree_id"] for e in press_events(out)] == [SET_ID, 0]
    assert all(e["tree_id"] == SET_ID for e in fruits(out) if e["t"] < 2.7)


def test_a_timed_out_set_ends_its_bout_at_the_set_end():
    log = break_log(spans=((1.7, 2.6),), set_end=1.9)
    log.events.append(dict(type="harvest_release", t=1.9, real=0.0, tree_id=SET_ID, k=-1, reward=float("nan"), payload={}))
    out = replay_harvests(log)
    assert [e["type"] for e in out if e["type"] == "harvest_release"] == ["harvest_release"] and out[-1]["forced"]
    assert len(fruits(out)) < 10


def test_a_harvest_started_in_a_break_is_finished_whatever_the_key_and_the_crosshair_do():
    # a 0.1 s tap on the set's bush, then the key up and the view turned away: the aimed bout runs to the bush's last fruit, no pause, no release
    frames = [(0.0, 7.0, 0.0, 4 if 1.55 <= (i + 1) / HZ < 1.65 else 0) for i in range(400)]
    frames = [(x, z, 90.0 if (i + 1) / HZ >= 1.65 else yaw, k) for i, (x, z, yaw, k) in enumerate(frames)]
    log = toy_log(frames, n_fruits=10)
    log.manifest = BREAK
    log.events = break_events()
    out = replay_harvests(log)
    assert len([e for e in fruits(out) if e["tree_id"] == SET_ID]) == 10
    assert [e["type"] for e in out if e["type"] in ("harvest_pause", "harvest_resume")] == []
    assert len(press_events(out)) == 1


def test_a_break_replay_verifies_against_its_own_events():
    log = break_log()
    log.events = sorted(break_events() + logged(log), key=lambda e: e["t"])
    log.manifest["final_score"] = 1.0
    assert verify(log)[0] == []


def test_steps_marks_the_break():
    s = steps(break_log(), 0.1)
    in_break = s["t"][s["ranking"] == 1]
    assert 1.0 < in_break.min() <= 1.1 and 2.6 <= in_break.max() <= 2.7 and s["ranking"].sum() == len(in_break)


def test_two_sets_with_the_same_ids_are_separate_bushes():
    # a pool that wraps gives a later set the ids of an earlier one (at other places): replay keeps them apart
    log = break_log(spans=((1.7, 2.6), (3.2, 3.9)), set_end=2.8, end=3.9)
    second = _ev("rank_set", 3.0, **{"break": 1, "set": 1, "fruits": 10, "bushes": [{"id": SET_ID, "x": 20.0, "z": 27.0, "radius": 1.0, "shape": 0.5}]})
    log.events = sorted(log.events + [second, _ev("rank_go", 3.1, **{"break": 1}), _ev("rank_set_end", 3.85, **{"break": 1})], key=lambda e: e["t"])
    bushes, sets, ids = replay.with_ranking_bushes(log)
    assert len(sets) == 2 and len(bushes.pos) == 3 and list(ids) == [0, SET_ID, SET_ID] and np.allclose(bushes.pos[2], [20.0, 27.0])


# --- the crosshair rule (crosshairRadius > 0: the view ray must touch the canopy, pitch included) ------------------

CROSS = dict(CFG, harvestRangeGapBase=100.0, crosshairRadius=1.5, crosshairReleaseScale=2.0, eyeHeight=5.0,
             shapeRange={"x": 0.0, "y": 1.0}, canopyHeightRange={"x": 1.0, "y": 15.0})


def look(x, z, bx, bz, eye=5.0, aim_height=0.25):
    """(yaw, pitch) in degrees that point the view at a bush's middle from (x, z)."""
    dx, dz = bx - x, bz - z
    return float(np.degrees(np.arctan2(dx, dz))), float(np.degrees(np.arctan2(eye - aim_height, np.hypot(dx, dz))))


def cross_log(rows, bushes=((0.0, 10.0, 1.0),), shape=0.0, cfg=None, n_fruits=3):
    """`rows` are (x, z, yaw, pitch, keys) at HZ; every bush has the given shape (0 = squat, half a unit high), flat ground, eye height 5."""
    log = multi_log(list(bushes), [(r[0], r[1], r[2], r[4]) for r in rows], n_fruits=n_fruits)
    log.traj[:, 4] = [r[3] for r in rows]
    log.manifest = {"config": cfg or CROSS}
    log.bushes.shape = np.full(len(bushes), shape)
    log.grids = {"elevation": np.zeros((11, 11), dtype=np.float32)}
    log.half_extent = 100.0
    return log


def hold(x, z, yaw, pitch, seconds=0.3, keys=4):
    return [(x, z, yaw, pitch, keys)] * int(seconds * HZ)


def test_looking_above_or_below_the_bush_does_not_aim_at_it_but_looking_at_it_does():
    yaw, pitch = look(0.0, 7.0, 0.0, 10.0)                 # a bush 3 away, 2 from the canopy's edge: in range whatever the rule
    assert press_events(replay_harvests(cross_log(hold(0.0, 7.0, yaw, pitch))))
    for off in (-25.0, 25.0):                              # the old cone ignored pitch: both of these started a harvest
        assert not press_events(replay_harvests(cross_log(hold(0.0, 7.0, yaw, pitch + off)))), off


def test_the_circle_widens_the_aim_a_little_beyond_the_canopys_edge():
    # radius 1 at 30: its angular radius is 1.9 degrees; the circle of 1.5 adds about that much more
    yaw, pitch = look(0.0, -20.0, 0.0, 10.0)
    assert press_events(replay_harvests(cross_log(hold(0.0, -20.0, yaw + 3.0, pitch))))
    assert not press_events(replay_harvests(cross_log(hold(0.0, -20.0, yaw + 4.5, pitch))))
    wide = dict(CROSS, crosshairRadius=4.0)                # a larger circle takes the second one
    assert press_events(replay_harvests(cross_log(hold(0.0, -20.0, yaw + 4.5, pitch), cfg=wide)))


def test_a_tall_bush_is_aimed_higher_up_than_a_squat_one():
    yaw, pitch = look(0.0, -20.0, 0.0, 10.0)
    higher = pitch - 12.0                                  # looking 12 degrees above its middle: over a squat bush, into a tall one (up to 15 high)
    assert not press_events(replay_harvests(cross_log(hold(0.0, -20.0, yaw, higher), shape=0.0)))
    assert press_events(replay_harvests(cross_log(hold(0.0, -20.0, yaw, higher), shape=1.0)))


def test_the_range_applies_to_the_crosshair_in_the_main_task_but_not_inside_a_ranking_break():
    near = dict(CROSS, harvestRangeGapBase=7.0)
    yaw, pitch = look(0.0, -20.0, 0.0, 10.0)
    rows = hold(0.0, -20.0, yaw, pitch)
    assert not press_events(replay_harvests(cross_log(rows, cfg=near)))     # 29 from the edge, beyond 7
    log = cross_log(rows, cfg=near)
    log.events = [_ev("rank_break_start", 0.0, **{"break": 1}),
                  _ev("rank_set", 0.0, **{"break": 1, "set": 0, "fruits": 3, "bushes": [{"id": SET_ID, "x": 0.0, "z": 10.0, "radius": 1.0, "shape": 0.0}]}),
                  _ev("rank_go", 0.005, **{"break": 1})]
    assert [e["tree_id"] for e in press_events(replay_harvests(log))] == [SET_ID]            # ranking: no range


def test_of_two_bushes_on_the_ray_the_nearer_is_the_target():
    bushes = ((0.0, 10.0, 1.0), (0.0, 40.0, 1.0))
    yaw, pitch = look(0.0, -20.0, 0.0, 10.0)
    out = press_events(replay_harvests(cross_log(hold(0.0, -20.0, yaw, pitch), bushes=bushes)))
    assert [e["tree_id"] for e in out] == [0]


def test_a_harvest_in_progress_survives_a_small_drift_but_pauses_beyond_the_grown_circle():
    # started on target; the view drifts 4.5 degrees (outside the circle of 1.5 beyond the canopy, inside the released one of 3), then 8
    yaw, pitch = look(0.0, -20.0, 0.0, 10.0)
    rows = hold(0.0, -20.0, yaw, pitch, 0.3) + hold(0.0, -20.0, yaw + 4.5, pitch, 0.3) + hold(0.0, -20.0, yaw + 8.0, pitch, 0.3) + hold(0.0, -20.0, yaw, pitch, 0.3)
    out = replay_harvests(cross_log(rows))
    assert [e["type"] for e in out if e["type"] in ("harvest_pause", "harvest_resume")] == ["harvest_pause", "harvest_resume"]
    pause, resume = [e["t"] for e in out if e["type"] in ("harvest_pause", "harvest_resume")]
    assert 0.6 < pause < 0.7 and 0.9 < resume < 1.0


def test_without_a_crosshair_radius_the_log_is_replayed_by_the_old_cone():
    yaw, pitch = look(0.0, 7.0, 0.0, 10.0)
    old = dict(CFG)                                        # no crosshairRadius in the config: the 35 degree cone of yaw, pitch ignored
    assert press_events(replay_harvests(cross_log(hold(0.0, 7.0, yaw, pitch + 25.0), cfg=old)))
