import math
from pathlib import Path

import numpy as np

from replay import Bushes, SessionLog
from visibility import camera_axes, canopy_height, sample_grid, visible_bushes

HALF = 200.0
RES = 201                       # one grid cell per world unit
CFG = {"shapeRange": {"x": 0.0, "y": 1.0}, "canopyHeightRange": {"x": 1.0, "y": 15.0}, "eyeHeight": 5.1,
       "cameraNearClip": 0.3}
MANIFEST = {"camera": {"fieldOfView": 75.0, "farClipPlane": 1000.0}, "display": {"width": 1600, "height": 900}, "config": CFG}


def make_log(bush_xz, yaw=0.0, pitch=0.0, ground=lambda x, z: 0.0 * x, shape=0.0, radius=1.0, events=(), at=(0.0, 0.0)):
    axis = np.linspace(-HALF, HALF, RES)
    gx, gz = np.meshgrid(axis, axis, indexing="ij")
    grids = {"elevation": ground(gx, gz).astype(np.float32)}
    xz = np.array(bush_xz, dtype=float).reshape(-1, 2)
    n = len(xz)
    bushes = Bushes(pos=xz, canopy_radius=np.broadcast_to(np.asarray(radius, dtype=float), (n,)).copy(),
                    fruit_reward=np.zeros((n, 1), dtype=int), value=np.zeros(n),
                    shape=np.broadcast_to(np.asarray(shape, dtype=float), (n,)).copy())
    traj = np.array([[0.1, at[0], at[1], yaw, pitch, 0]])
    return SessionLog(Path("."), MANIFEST, traj, list(events), bushes, grids, HALF)


def seen(log, **kw):
    v = visible_bushes(log, dt=None, frames=[0], **kw)
    return v.at(0)


def test_helpers():
    assert abs(canopy_height(CFG, 0.0) - 1.0) < 1e-12 and abs(canopy_height(CFG, 1.0) - 15.0) < 1e-12
    grid = np.arange(25, dtype=float).reshape(5, 5)         # value 5 i + j
    assert abs(float(sample_grid(grid, 2.0, 0.5, -1.5)) - (5 * 2.5 + 0.5)) < 1e-9
    f, r, u = camera_axes(90.0, 0.0)
    assert np.allclose(f, [1, 0, 0]) and np.allclose(r, [0, 0, -1]) and np.allclose(u, [0, 1, 0])
    f, r, u = camera_axes(0.0, 90.0)                        # looking straight down: screen-up is world +Z
    assert np.allclose(f, [0, -1, 0]) and np.allclose(u, [0, 0, 1])


def test_bush_ahead_is_visible_with_egocentric_coordinates():
    s = seen(make_log([[0.0, 40.0]]))
    assert list(s["tree_id"]) == [0]
    assert abs(s["azimuth"][0]) < 1e-6 and s["visible_fraction"][0] > 0.5
    assert abs(s["distance"][0] - math.hypot(40.0, 5.1 - 0.25)) < 0.05
    assert s["elevation"][0] < 0                              # the bush's middle is below eye level
    assert abs(s["width"][0] - math.degrees(2 * math.atan(1.0 / s["distance"][0]))) < 0.05


def test_sides_and_behind():
    # hfov = 2 atan(tan(37.5 deg) * 16/9) ~ 107.5 deg: +-54 deg is the edge
    log = make_log([[40 * math.sin(math.radians(a)), 40 * math.cos(math.radians(a))] for a in (30, -30, 70, -70, 180)])
    s = seen(log)
    assert sorted(s["tree_id"]) == [0, 1]
    by_id = dict(zip(s["tree_id"], s["azimuth"]))
    assert 29 < by_id[0] < 31 and -31 < by_id[1] < -29        # + = right of the view centre


def test_yaw_and_pitch_move_the_view():
    ahead_east = [[40.0, 0.0]]
    assert len(seen(make_log(ahead_east, yaw=0.0))["tree_id"]) == 0
    s = seen(make_log(ahead_east, yaw=90.0))
    assert len(s["tree_id"]) == 1 and abs(s["azimuth"][0]) < 1e-6
    assert len(seen(make_log([[0.0, 40.0]], pitch=80.0))["tree_id"]) == 0      # looking at the ground at your feet
    assert len(seen(make_log([[0.0, 40.0]], pitch=-80.0))["tree_id"]) == 0     # looking at the sky


def test_a_ridge_hides_a_bush_behind_it():
    ridge = lambda x, z: 40.0 * np.exp(-((z - 20.0) ** 2) / 20.0) + 0.0 * x
    assert len(seen(make_log([[0.0, 60.0]], ground=ridge))["tree_id"]) == 0
    assert len(seen(make_log([[0.0, 60.0]]))["tree_id"]) == 1                 # flat ground: visible
    # a bush on the near side of the ridge is not hidden by it
    assert len(seen(make_log([[0.0, 10.0]], ground=ridge))["tree_id"]) == 1


def test_a_tall_bush_peeks_over_a_low_rise():
    rise = lambda x, z: 5.5 * np.exp(-((z - 20.0) ** 2) / 20.0) + 0.0 * x     # just above eye level (5.1)
    squat = seen(make_log([[0.0, 60.0]], ground=rise, shape=0.0))
    tall = seen(make_log([[0.0, 60.0]], ground=rise, shape=1.0))
    assert len(squat["tree_id"]) == 0
    assert len(tall["tree_id"]) == 1 and 0 < tall["visible_fraction"][0] < 1


def test_distance_and_angular_size_limits():
    log = make_log([[0.0, 150.0]])
    assert len(seen(log)["tree_id"]) == 1
    assert len(seen(log, max_distance=100.0)["tree_id"]) == 0
    assert len(seen(log, min_angular_deg=5.0)["tree_id"]) == 0               # 1-unit radius at 150: under 1 degree wide


def test_eye_height_follows_the_terrain():
    slope = lambda x, z: 0.1 * z + 0.0 * x
    low = seen(make_log([[0.0, 40.0]], ground=slope, at=(0.0, 0.0)))
    high = seen(make_log([[0.0, 40.0]], ground=slope, at=(0.0, 20.0)))
    assert abs(low["elevation"][0] - high["elevation"][0]) > 1.0 or abs(low["distance"][0] - high["distance"][0]) > 1.0


def test_interlude_shows_only_the_trials_pair():
    xz = [[0.0, 40.0], [5.0, 40.0], [-5.0, 40.0]]
    ev = [{"type": "trial_start", "t": 0.0, "note": "order=0;trial=0;left=1;right=2"}]
    s = seen(make_log(xz, events=ev))
    assert sorted(s["tree_id"]) == [1, 2]
    assert sorted(seen(make_log(xz))["tree_id"]) == [0, 1, 2]


def test_a_hidden_bush_disappears_after_the_fade_but_a_spent_or_locked_one_stays():
    xz = [[5.0, 40.0], [-5.0, 40.0]]
    pair = {"type": "trial_start", "t": 0.0, "note": "order=0;trial=0;left=0;right=1"}

    def lock(t, policy):
        return {"type": "choice_lock", "t": t, "note": f"committed=0;locked=1;policy={policy}"}

    def visible(events):
        log = make_log(xz, events=events)
        log.traj[0, 0] = 1.0                                                  # the frame is at t = 1 s
        return sorted(seen(log)["tree_id"])
    assert visible([pair]) == [0, 1]
    assert visible([pair, lock(0.2, "Hide")]) == [0]                          # 0.8 s after the lock: fade over, bush 1 gone
    assert visible([pair, lock(0.8, "Hide")]) == [0, 1]                       # only 0.2 s after: still shrinking
    assert visible([pair, lock(0.2, "Exhaust")]) == [0, 1]
    assert visible([pair, lock(0.2, "Lock")]) == [0, 1]


def _at_azimuth(deg, dist=40.0, **kw):
    a = math.radians(deg)
    return make_log([[dist * math.sin(a), dist * math.cos(a)]], **kw)


def test_the_view_edges_follow_the_vertical_fov_and_the_aspect_ratio():
    # vfov 75 at 1600x900: horizontal half-angle atan(tan 37.5 * 16/9) = 53.75 degrees, vertical half-angle 37.5.
    for az in (50.0, -50.0):
        assert len(seen(_at_azimuth(az))["tree_id"]) == 1, az
    for az in (58.0, -58.0):                          # a 1-unit canopy at 40 spans +-1.4 degrees: still outside
        assert len(seen(_at_azimuth(az))["tree_id"]) == 0, az
    # the bush sits ~7 degrees below the horizon, so a pitch of 40 (down) puts it 33 from the view centre, 50 puts it 43
    assert len(seen(make_log([[0.0, 40.0]], pitch=40.0))["tree_id"]) == 1
    assert len(seen(make_log([[0.0, 40.0]], pitch=50.0))["tree_id"]) == 0
    assert len(seen(make_log([[0.0, 40.0]], pitch=-30.0))["tree_id"]) == 1       # 23 degrees from the centre, looking up
    assert len(seen(make_log([[0.0, 40.0]], pitch=-50.0))["tree_id"]) == 0
    # a different window shape changes the horizontal edge only
    a = math.radians(50.0)
    log = make_log([[40 * math.sin(a), 40 * math.cos(a)]])
    log.manifest = {**MANIFEST, "display": {"width": 900, "height": 900}}          # hfov = vfov = 75: edge at 37.5
    assert len(seen(log)["tree_id"]) == 0


def test_only_the_surface_facing_the_viewer_counts_toward_the_visible_fraction():
    # A low bush seen from 40 units away at eye height: the far side of the canopy faces away, so well under all of the
    # sample points are visible (but more than none).
    frac = seen(make_log([[0.0, 40.0]]))["visible_fraction"][0]
    assert 0.5 < frac < 0.75, frac


def test_canopy_height_sets_the_middle_and_the_angular_height():
    # shape 1 -> height 15 (half-buried ellipsoid: 7.5 above ground, its visible middle at 3.75), eye at 5.1.
    s = seen(make_log([[0.0, 40.0]], shape=1.0))
    dist = math.hypot(40.0, 5.1 - 3.75)
    assert abs(s["distance"][0] - dist) < 0.01
    assert abs(s["elevation"][0] - -math.degrees(math.atan2(5.1 - 3.75, 40.0))) < 0.01
    assert abs(s["height"][0] - math.degrees(math.atan2(7.5, dist))) < 0.01
    assert abs(s["width"][0] - math.degrees(2 * math.atan2(1.0, dist))) < 0.01


def test_each_trial_shows_its_own_pair():
    xz = [[0.0, 40.0], [5.0, 40.0], [-5.0, 40.0]]
    ev = [{"type": "trial_start", "t": 0.0, "note": "order=0;trial=0;left=0;right=1"},
          {"type": "trial_start", "t": 1.0, "note": "order=1;trial=1;left=1;right=2"}]
    log = make_log(xz, events=ev)
    log.traj = np.array([[0.5, 0, 0, 0, 0, 0], [0.999, 0, 0, 0, 0, 0], [1.0, 0, 0, 0, 0, 0], [1.5, 0, 0, 0, 0, 0]])
    v = visible_bushes(log, dt=None, frames=[0, 1, 2, 3])
    assert [sorted(v.at(i)["tree_id"]) for i in range(4)] == [[0, 1], [0, 1], [1, 2], [1, 2]]


# --- bushes hiding each other --------------------------------------------------------------------------------------

def test_a_big_bush_hides_a_small_one_directly_behind_it_but_not_one_beside_it():
    # eye 5.1 above flat ground; the near bush is 8 wide and 15 tall, the far ones are low (shape 0: 1 tall)
    xz = [[0.0, 20.0], [0.0, 60.0], [30.0, 60.0]]
    kw = dict(radius=[8.0, 1.0, 1.0], shape=[1.0, 0.0, 0.0])
    on = seen(make_log(xz, **kw))
    assert sorted(on["tree_id"]) == [0, 2]                                    # the one behind it is hidden, the one beside it is not
    assert sorted(seen(make_log(xz, **kw), bush_occlusion=False)["tree_id"]) == [0, 1, 2]


def test_a_bush_is_partly_hidden_by_a_lower_one_in_front_and_the_crown_still_shows():
    # far: tall (15) and 3 wide; near: 8 tall and 3 wide, straight ahead: the lower canopy points are hidden, the crown is not
    xz = [[0.0, 20.0], [0.0, 50.0]]
    kw = dict(radius=3.0, shape=[0.5, 1.0])
    with_it = dict(zip(seen(make_log(xz, **kw))["tree_id"], seen(make_log(xz, **kw))["visible_fraction"]))
    without = dict(zip(seen(make_log(xz, **kw), bush_occlusion=False)["tree_id"], seen(make_log(xz, **kw), bush_occlusion=False)["visible_fraction"]))
    assert 0.0 < with_it[1] < without[1]
    assert with_it[0] == without[0]                                           # the nearer bush is not affected


def test_only_bushes_that_exist_hide_others_in_an_interlude_and_a_bush_behind_the_target_hides_nothing():
    xz = [[0.0, 20.0], [0.0, 60.0], [0.0, 90.0]]
    kw = dict(radius=[8.0, 1.0, 8.0], shape=[1.0, 0.0, 1.0])
    pair = [{"type": "trial_start", "t": 0.0, "note": "order=0;trial=0;left=1;right=2"}]       # the big bush 0 does not exist in this trial
    assert sorted(seen(make_log(xz, events=pair, **kw))["tree_id"]) == [1, 2]
    assert 1 in seen(make_log([[0.0, 60.0], [0.0, 90.0]], radius=[1.0, 8.0], shape=[0.0, 1.0]))["tree_id"]   # a big bush behind it changes nothing


def test_bush_occlusion_leaves_a_bush_with_nothing_in_front_unchanged():
    xz = [[0.0, 40.0], [30.0, 40.0], [-25.0, 55.0]]
    a, b = seen(make_log(xz)), seen(make_log(xz), bush_occlusion=False)
    assert list(a["tree_id"]) == list(b["tree_id"]) and np.allclose(a["visible_fraction"], b["visible_fraction"])


def test_the_command_line_can_turn_bush_occlusion_off(monkeypatch):
    import visibility
    seen_flags = []
    named = lambda s: __import__("dataclasses").replace(make_log([[0.0, 40.0]]), manifest={**MANIFEST, "sessionName": "T", "sessionId": "t"})
    monkeypatch.setattr(visibility, "load_session_log", named)
    monkeypatch.setattr(visibility, "visible_bushes", lambda log, **kw: seen_flags.append(kw["bush_occlusion"]) or visible_bushes(log, dt=None, frames=[0]))
    for argv, expected in ((["x"], True), (["x", "--no-bush-occlusion"], False)):
        monkeypatch.setattr("sys.argv", ["visibility.py", *argv])
        visibility.main()
        assert seen_flags[-1] is expected
