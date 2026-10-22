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
    bushes = Bushes(pos=xz, canopy_radius=np.full(n, radius), fruit_reward=np.zeros((n, 1), dtype=int),
                    value=np.zeros(n), shape=np.full(n, shape))
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
    # hfov = 2 atan(tan(37.5 deg) * 16/9) ~ 110 deg: +-55 deg is the edge
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
