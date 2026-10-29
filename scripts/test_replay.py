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


def logged(log, extra=()):
    """Events as the DataLogger writes them: the replayed harvest events plus `extra`, in clock order."""
    ev = [dict(e, real=0.0, k=e.get("k", -1), reward=e.get("reward", float("nan")), note="") for e in replay_harvests(log)]
    ev += [dict(type=t, t=at, real=0.0, k=-1, reward=float("nan"), note="") for t, at in extra]
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
    log.manifest["finalScore"] = 6.0
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
    log.manifest["finalScore"] = 6.0
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
    # old "any logged release is forced" rule accepted. Only a trial_end or the session's last frames may force one.
    frames = [(0, 7.0, 0.0, 4)] * 400
    log = toy_log(frames, n_fruits=10)
    log.events = logged(log)
    fr = [e for e in log.events if e["type"] == "fruit"]
    log.events = [e for e in log.events if e["t"] <= fr[2]["t"] and e["type"] != "fruit" or e["type"] == "fruit" and e["t"] <= fr[2]["t"]]
    log.events.append(dict(type="harvest_release", t=fr[2]["t"], tree_id=0, real=0.0, k=-1, reward=float("nan"), note=""))
    assert verify(log)[0]
    # The same release is accepted when a trial_end coincides with it (the Interlude cancelling the bout).
    log.events.append(dict(type="trial_end", t=fr[2]["t"], real=0.0, tree_id=-1, k=-1, reward=float("nan"), note=""))
    log.manifest.pop("finalScore", None)
    assert not [p for p in verify(log)[0] if p.startswith(("harvest_release", "fruit", "harvest_press"))]


def test_steps_holds_the_old_pose_until_the_row_after_a_teleport():
    # The teleport is logged at the row that still has the old pose; the jump shows in the next row. Steps between
    # those two rows must not be interpolated across the jump.
    bushes = Bushes(pos=np.array([[0.0, 10.0]]), canopy_radius=np.array([1.0]),
                    fruit_reward=np.ones((1, 3)), value=np.array([1.0]))
    t = np.arange(1, 6) / 2.0                       # rows every 0.5 s
    traj = np.array([[ti, x, 0.0, 0.0, 0.0, 0] for ti, x in zip(t, [0, 0, 0, 300, 300])])
    log = SessionLog(Path("."), {"config": CFG}, traj, [dict(type="teleport", t=1.5, real=0.0, tree_id=-1, k=-1,
                     reward=float("nan"), note="")], bushes)
    s = steps(log, 0.1)
    between = (s["t"] > 1.5 + 1e-9) & (s["t"] < 2.0 - 1e-9)
    assert between.any() and (s["x"][between] == 0.0).all()


def two_bush_log(frames, events=()):
    """Two bushes of radius 1 at (-6, 10) and (6, 10); the player stands at (0, 10), in range of both. Facing yaw -90 looks at
    the first, +90 at the second. `frames` are (yaw, keys)."""
    bushes = Bushes(pos=np.array([[-6.0, 10.0], [6.0, 10.0]]), canopy_radius=np.array([1.0, 1.0]),
                    fruit_reward=np.tile(np.arange(1, 11), (2, 1)), value=np.array([3.0, 3.0]))
    traj = np.array([[(i + 1) / HZ, 0.0, 10.0, yaw, 0.0, keys] for i, (yaw, keys) in enumerate(frames)])
    return SessionLog(Path("."), {"config": CFG}, traj, list(events), bushes)


def choice_lock(t, committed, locked, policy="Hide"):
    return {"type": "choice_lock", "t": t, "real": 0.0, "tree_id": committed, "k": -1, "reward": float("nan"),
            "running_total": float("nan"), "note": f"committed={committed};locked={locked};policy={policy}"}


def presses(replayed):
    return [e["tree_id"] for e in replayed if e["type"] == "harvest_press"]


SWITCHING = [(-90.0, 4)] * 100 + [(-90.0, 0)] * 10 + [(90.0, 4)] * 100


def test_without_a_lock_the_player_can_switch_bushes():
    out = replay_harvests(two_bush_log(SWITCHING))
    assert presses(out) == [0, 1]


def test_a_choice_lock_stops_a_switch_but_not_resuming_the_chosen_bush():
    # the lock is logged on the press frame (t = 0.01); it applies from the next frame on
    events = [choice_lock(0.01, committed=0, locked=1)]
    assert presses(replay_harvests(two_bush_log(SWITCHING, events))) == [0]
    back = [(-90.0, 4)] * 100 + [(-90.0, 0)] * 10 + [(90.0, 4)] * 50 + [(90.0, 0)] * 5 + [(-90.0, 4)] * 50
    out = replay_harvests(two_bush_log(back, events))
    assert presses(out) == [0, 0]                                       # pressing the chosen bush again resumes it
    assert all(e["tree_id"] == 0 for e in out if e["type"] == "fruit")


def test_the_lock_does_not_change_the_press_that_causes_it():
    events = [choice_lock(0.01, committed=1, locked=0)]
    out = replay_harvests(two_bush_log([(90.0, 4)] * 100, events))        # first press is on bush 1, whose lock partner is 0
    assert presses(out) == [1] and len(fruits(out)) == 1


def _ev(kind, t, note=""):
    return dict(type=kind, t=t, real=0.0, tree_id=-1, k=-1, reward=float("nan"), note=note)


def test_a_press_between_trials_starts_no_bout():
    # Space pressed during the fade after trial_end (and held through trial_go) must not start a bout on the old bush:
    # HarvestManager discards presses until the block lifts, so replay sees no press edge at trial_go either.
    frames = [(0, 7.0, 0.0, 0)] * 50 + [(0, 7.0, 0.0, 4)] * 100
    log = toy_log(frames)
    log.events = [_ev("trial_end", 0.50), _ev("trial_go", 1.00)]
    assert replay_harvests(log) == []
    # Without the block (a log from before it existed) the same keys start a bout at 0.51.
    log.events = []
    assert [e["type"] for e in replay_harvests(log)][:1] == ["harvest_press"]
    # A fresh press after trial_go works.
    frames = [(0, 7.0, 0.0, 0)] * 10 + [(0, 7.0, 0.0, 4)] * 50 + [(0, 7.0, 0.0, 0)] * 10 + [(0, 7.0, 0.0, 4)] * 60
    log = toy_log(frames)
    log.events = [_ev("trial_end", 0.10), _ev("trial_go", 0.50)]
    out = [e for e in replay_harvests(log) if e["type"] == "harvest_press"]
    assert len(out) == 1 and abs(out[0]["t"] - 0.71) < 2 / HZ


# --- geometry of the cone, focus choice and range (HarvestManager.Measure) -----------------------------------------

def multi_log(bushes, frames, events=(), n_fruits=10, per_bush_rewards=None):
    """`bushes` is [(x, z, radius)]; bush i pays 100*(i+1) + k for its k-th fruit unless `per_bush_rewards` is given."""
    pos = np.array([[b[0], b[1]] for b in bushes], dtype=float)
    rew = np.array([[100 * (i + 1) + k for k in range(n_fruits)] for i in range(len(bushes))])
    bush = Bushes(pos=pos, canopy_radius=np.array([b[2] for b in bushes], dtype=float), fruit_reward=rew,
                  value=np.zeros(len(bushes)))
    traj = np.array([[(i + 1) / HZ, x, z, yaw, 0.0, keys] for i, (x, z, yaw, keys) in enumerate(frames)])
    return SessionLog(Path("."), {"config": CFG}, traj, list(events), bush)


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


# --- Interlude trial activation -------------------------------------------------------------------------------------

def test_a_trials_pair_is_active_from_the_trial_start_frame():
    # Two bushes; only the trial's pair may be harvested, and from the frame of the trial_start event itself.
    bushes = [(0.0, 10.0, 1.0), (30.0, 10.0, 1.0), (60.0, 10.0, 1.0)]
    frames = [(0, 7.0, 0.0, 0)] * 49 + [(0, 7.0, 0.0, 4)] * 60                   # Space down on the row at t = 0.50
    ev = [_ev("trial_start", 0.50, "order=0;trial=0;left=0;right=1")]
    out = replay_harvests(multi_log(bushes, frames, ev))
    assert len(press_events(out)) == 1 and abs(press_events(out)[0]["t"] - 0.50) < 1e-6
    ev = [_ev("trial_start", 0.80, "order=0;trial=0;left=1;right=2")]            # bush 0 is not in the pair
    assert not press_events(replay_harvests(multi_log(bushes, frames, ev)))


# --- verify: tolerances and the ignored tail -----------------------------------------------------------------------

def test_verify_flags_a_fruit_logged_50_ms_off():
    frames = [(0, 7.0, 0.0, 4)] * 250
    log = toy_log(frames)
    log.events = logged(log)
    log.manifest["finalScore"] = 6.0
    assert verify(log)[0] == []
    for e in log.events:
        if e["type"] == "fruit":
            e["t"] += 0.05
    assert verify(log)[0]


def test_verify_ignores_events_on_the_last_frame_only():
    frames = [(0, 7.0, 0.0, 4)] * 150
    log = toy_log(frames)
    log.events = logged(log)
    log.manifest["finalScore"] = 1.0
    last = float(log.traj[-1, 0])
    log.events.append(dict(type="harvest_release", t=last, tree_id=0, real=0.0, k=-1, reward=float("nan"), note=""))
    assert verify(log)[0] == []                       # the session-end release on the last frame is not compared
    log.events[-1]["t"] = last - 0.5
    assert verify(log)[0]                             # ...but an early extra release is


def test_first_fruit_time_is_exact_to_half_a_frame():
    frames = [(0, 7.0, 0.0, 4)] * 100
    assert abs(fruits(replay_harvests(toy_log(frames)))[0]["t"] - 0.80) < 0.5 / HZ


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


# --- loading: hash checks and the Interlude's own bush table --------------------------------------------------------

def _archive(tmp_path, name, content):
    import hashlib
    d = tmp_path / "_worlds"
    d.mkdir(exist_ok=True)
    sha = hashlib.sha256(content).hexdigest()
    (d / f"{sha[:8]}_{name}").write_bytes(content)
    return sha


def test_find_world_file_rejects_a_file_with_the_wrong_hash(tmp_path, monkeypatch):
    import pytest
    import replay
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    monkeypatch.setattr("replay.WORLD_DIR", tmp_path / "none")
    sha = _archive(tmp_path, "x.world", b"original")
    assert replay.find_world_file("x.world", sha).read_bytes() == b"original"
    (tmp_path / "_worlds" / f"{sha[:8]}_x.world").write_bytes(b"tampered")
    with pytest.raises(FileNotFoundError):
        replay.find_world_file("x.world", sha)


def test_an_interlude_log_uses_the_interludes_bush_table(tmp_path, monkeypatch):
    w = world_mod.make_world("S1", 1)
    wfile = tmp_path / "S1_seed1.world"
    world_mod.export_unity(w, wfile)
    wsha = _archive(tmp_path, "S1_seed1.world", wfile.read_bytes())
    table = {"treePos": [1.0, 2.0, 3.0, 4.0], "canopyRadius": [1.5, 2.5], "fruitCount": 2, "fruitRewards": [5, 6, 7, 8],
             "value": [1.0, 2.0], "shape": [0.1, 0.9], "n": 5}
    isha = _archive(tmp_path, "S1_Interlude_seed1.interlude.json", json.dumps(table).encode())
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    folder = tmp_path / "abcd1234"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps({"sessionId": "abcd1234", "config": CFG, "world": {
        "file": "S1_seed1.world", "sha256": wsha, "interludeFile": "S1_Interlude_seed1.interlude.json", "interludeSha256": isha}}))
    (folder / "trajectory.csv").write_text("t,x,z,yaw,pitch,keys\n0.016667,0.0,0.0,0.0,0.0,0\n")
    (folder / "events.csv").write_text("t,real,type,tree_id,k,reward,running_total,note\n")
    log = load_session_log("abcd1234")
    assert log.bushes.pos.tolist() == [[1.0, 2.0], [3.0, 4.0]] and log.bushes.canopy_radius.tolist() == [1.5, 2.5]
    assert log.bushes.fruit_reward.tolist() == [[5, 6], [7, 8]] and len(log.grids) == 5     # the terrain is the session's


def test_each_verify_score_check_stands_on_its_own():
    frames = [(0, 7.0, 0.0, 4)] * 250
    log = toy_log(frames)
    log.events = logged(log)
    log.manifest["finalScore"] = 6.0
    assert verify(log)[0] == []
    fr = [e for e in log.events if e["type"] == "fruit"]
    fr[0]["reward"] += 1.0
    fr[1]["reward"] -= 1.0                       # the per-fruit rewards are wrong but still sum to finalScore
    assert any(p.startswith("fruit") for p in verify(log)[0])
    fr[0]["reward"] -= 1.0
    fr[1]["reward"] += 1.0
    log.manifest["finalScore"] = 7.0             # the fruits are right but finalScore is not their sum
    assert any("finalScore" in p for p in verify(log)[0])


# --- logs from a session that did not finish writing ----------------------------------------------------------------

def _folder(tmp_path, monkeypatch, traj_text, events_text):
    w = world_mod.make_world("S1", 1)
    wfile = tmp_path / "S1_seed1.world"
    world_mod.export_unity(w, wfile)
    sha = _archive(tmp_path, "S1_seed1.world", wfile.read_bytes())
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    folder = tmp_path / "abcd1234"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps({"sessionId": "abcd1234", "sessionName": "S1", "config": CFG,
                                                      "world": {"file": "S1_seed1.world", "sha256": sha}}))
    (folder / "trajectory.csv").write_text(traj_text)
    (folder / "events.csv").write_text(events_text)
    return load_session_log("abcd1234")


TRAJ = "t,x,z,yaw,pitch,keys\n0.010000,0.0000,0.0000,0.0000,0.000,0\n0.020000,0.0000,0.0000,0.0000,0.000,0\n"
EVENTS = "t,real,type,tree_id,k,reward,running_total,note\n0.010000,0.100,session_start,,,,,x=0\n"


def test_a_clean_log_is_not_marked_truncated(tmp_path, monkeypatch):
    log = _folder(tmp_path, monkeypatch, TRAJ, EVENTS)
    assert log.truncated == [] and len(log.traj) == 2 and len(log.events) == 1


import pytest


@pytest.mark.parametrize("cut", ["0.030000,1.0", "0.030000,1.0000,2.0000,3.0000,4.000,0", "0.030000,1.0000,2.0000,3.0000,4.0"])
def test_a_trajectory_cut_mid_line_loses_only_that_line_and_verify_says_so(tmp_path, monkeypatch, cut):
    log = _folder(tmp_path, monkeypatch, TRAJ + cut, EVENTS)       # no trailing newline: the write was interrupted
    assert len(log.traj) == 2 and log.truncated == ["trajectory.csv"]
    assert any("trajectory.csv ended mid-line" in p for p in verify(log)[0])


def test_an_events_file_cut_mid_line_loses_only_that_line(tmp_path, monkeypatch):
    log = _folder(tmp_path, monkeypatch, TRAJ, EVENTS + "0.020000,0.2")
    assert len(log.events) == 1 and log.truncated == ["events.csv"]


def test_a_bad_line_in_the_middle_is_still_an_error(tmp_path, monkeypatch):
    bad = "t,x,z,yaw,pitch,keys\n0.01,0,0,0,0,0\n0.02,oops\n0.03,0,0,0,0,0\n"
    with pytest.raises(ValueError):
        _folder(tmp_path, monkeypatch, bad, EVENTS)


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
             for e in replay_harvests(dict_log(log, gap))]
    log.events = sorted(gap + after, key=lambda e: e["t"])
    log.manifest["finalScore"] = 6.0
    assert verify(log)[0] == []
    after[-1]["reward"] += 1.0                          # a wrong reward after the resume is still caught
    log.manifest["finalScore"] = 7.0
    assert any(p.startswith("fruit") for p in verify(log)[0])


def dict_log(log, events):
    import copy
    other = copy.copy(log)
    other.events = list(events)
    return other
