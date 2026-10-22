"""Reconstruct which bushes the participant could see along a logged trajectory, with egocentric coordinates.

The logs do not store visibility (it is derived data). It is a deterministic function of the trajectory, the world and
the camera, so it is recomputed here from `replay.SessionLog`:

* Camera: eye at (x, terrain(x, z) + eyeHeight, z), looking along yaw/pitch (Unity convention: pitch positive = down,
  yaw about +Y from +Z toward +X), vertical field of view and clip planes from the manifest, aspect from the logged
  display size (override with `aspect=`).
* Bush geometry (Tree.ApplyAttributes): a half-buried ellipsoid centred on the ground at the bush's (x, z), horizontal
  radius = the canopy radius, vertical radius = half the canopy height, which follows the shape attribute through the
  config's `shapeRange` and `canopyHeightRange`.
* A bush is visible when at least one of a handful of points on the camera-facing part of its upper canopy surface lies
  inside the view frustum and the straight line from the eye to it clears the terrain (a heightfield march over the
  world file's elevation grid). `visible_fraction` is the share of those points that qualify, a graded measure of how
  much of the bush is in view.
* In an Interlude only the trial's two bushes exist (the rest are inactive objects), taken from the `trial_start` events. Under
  the Hide switch policy the unchosen bush is gone HIDE_SECONDS after the `choice_lock` event (under Exhaust and Lock it stays
  visible).

Not modelled: bushes hiding other bushes (a tall canopy can partly hide one behind it), fruit visibility, fog, and any
limit on how far away attributes can be resolved. Use the returned `distance` and angular `width`/`height` to threshold
on resolvability (`min_angular_deg=`) rather than baking in a cutoff.

Egocentric coordinates per visible bush: `azimuth` (degrees right of the view centre, + = right, matching
HarvestManager's signed bearing), `elevation` (degrees above the view centre of the middle of the visible canopy,
+ = up), `distance` (eye to that point), `width` / `height` (angular size of the canopy, degrees).

    ./venv/bin/python scripts/visibility.py <session folder or id> [--dt 0.1] [--csv visible.csv]
"""

import argparse
import csv
import math
from dataclasses import dataclass

import numpy as np

from replay import load_session_log, parse_note

# Directions of the canopy surface sample points: (elevation above the horizon in degrees, azimuth in degrees); the crown
# is the first point. Points on the far side of the canopy are dropped per frame (they face away from the eye).
SURFACE_RINGS = ((90.0, (0.0,)), (50.0, (0.0, 90.0, 180.0, 270.0)), (15.0, (0.0, 60.0, 120.0, 180.0, 240.0, 300.0)))
RAY_STEP = 3.0          # world units between terrain samples along a line of sight (the mesh cell is about 1.6)
HIDE_SECONDS = 0.4      # InterludeManager.hideSeconds: how long the unchosen bush takes to shrink away under policy Hide


# --------------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------------

def canopy_height(config, shape):
    """Full canopy height (Tree.ApplyAttributes): squat/wide at shape 0, tall/narrow at 1."""
    lo, hi = config["shapeRange"]["x"], config["shapeRange"]["y"]
    t = np.clip((np.asarray(shape, dtype=float) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    h = config["canopyHeightRange"]
    return h["x"] + (h["y"] - h["x"]) * t


def sample_grid(grid, half, x, z):
    """Bilinear sample of a (res, res) grid indexed [x, z] spanning [-half, half] (WorldData.Sample); clamped at the edge."""
    res = grid.shape[0]
    u = np.clip((np.asarray(x, dtype=float) + half) / (2.0 * half) * (res - 1), 0.0, res - 1 - 1e-9)
    v = np.clip((np.asarray(z, dtype=float) + half) / (2.0 * half) * (res - 1), 0.0, res - 1 - 1e-9)
    i, j = u.astype(int), v.astype(int)
    fu, fv = u - i, v - j
    return ((1 - fu) * (1 - fv) * grid[i, j] + fu * (1 - fv) * grid[i + 1, j]
            + (1 - fu) * fv * grid[i, j + 1] + fu * fv * grid[i + 1, j + 1])


def camera_axes(yaw_deg, pitch_deg):
    """(forward, right, up) unit vectors for Unity's Quaternion.Euler(pitch, yaw, 0) (pitch positive looks down)."""
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    forward = np.array([math.sin(y) * math.cos(p), -math.sin(p), math.cos(y) * math.cos(p)])
    right = np.array([math.cos(y), 0.0, -math.sin(y)])
    up = np.array([math.sin(y) * math.sin(p), math.cos(p), math.cos(y) * math.sin(p)])
    return forward, right, up


def _unit_directions():
    out = []
    for elev, azimuths in SURFACE_RINGS:
        e = math.radians(elev)
        for a in azimuths:
            a = math.radians(a)
            out.append((math.cos(e) * math.sin(a), math.sin(e), math.cos(e) * math.cos(a)))
    return np.array(out)        # (P, 3) as (x, up, z) on the unit sphere


@dataclass
class Visibility:
    """Sparse per-step visibility: step s owns rows offsets[s]:offsets[s + 1] of the flat arrays."""
    t: np.ndarray               # (steps,) session seconds of each step
    frame: np.ndarray           # (steps,) trajectory frame each step was computed from
    offsets: np.ndarray         # (steps + 1,)
    tree_id: np.ndarray
    azimuth: np.ndarray
    elevation: np.ndarray
    distance: np.ndarray
    width: np.ndarray
    height: np.ndarray
    visible_fraction: np.ndarray

    FIELDS = ("tree_id", "azimuth", "elevation", "distance", "width", "height", "visible_fraction")

    def at(self, step):
        """Dict of arrays for the bushes visible at `step`."""
        sl = slice(self.offsets[step], self.offsets[step + 1])
        return {name: getattr(self, name)[sl] for name in self.FIELDS}

    def counts(self):
        return np.diff(self.offsets)


# --------------------------------------------------------------------------------------------------
# Visibility along a trajectory
# --------------------------------------------------------------------------------------------------

def visible_bushes(log, dt=0.1, aspect=None, max_distance=None, min_angular_deg=0.0, frames=None):
    """Visible bushes at every `dt` seconds of the session (the logged state at the start of each step), or at the given
    trajectory `frames` (indices) when `dt` is None. See the module docstring for the model."""
    cfg, man = log.config, log.manifest
    b = log.bushes
    elevation = log.grids["elevation"]
    half = log.half_extent
    cam = man["camera"]
    vfov = math.radians(cam["fieldOfView"])
    near, far = float(cfg.get("cameraNearClip", cam.get("nearClipPlane", 0.3))), float(cam["farClipPlane"])
    if aspect is None:
        d = man.get("display", {})
        aspect = d["width"] / d["height"] if d.get("width") and d.get("height") else 16.0 / 9.0
    tan_v = math.tan(vfov / 2.0)
    tan_h = tan_v * aspect
    max_distance = far if max_distance is None else min(max_distance, far)
    eye_height = float(cfg["eyeHeight"])

    n = len(b.pos)
    rx = b.canopy_radius
    ry = canopy_height(cfg, b.shape) * 0.5
    ground = sample_grid(elevation, half, b.pos[:, 0], b.pos[:, 1])
    dirs = _unit_directions()
    # Sample points (n, P, 3) in world coordinates and their outward normals.
    pts = np.empty((n, len(dirs), 3))
    pts[:, :, 0] = b.pos[:, None, 0] + rx[:, None] * dirs[None, :, 0]
    pts[:, :, 1] = ground[:, None] + ry[:, None] * dirs[None, :, 1]
    pts[:, :, 2] = b.pos[:, None, 1] + rx[:, None] * dirs[None, :, 2]
    normals = np.stack([dirs[None, :, 0] / rx[:, None], dirs[None, :, 1] / ry[:, None], dirs[None, :, 2] / rx[:, None]], axis=-1)
    mid = np.stack([b.pos[:, 0], ground + ry * 0.5, b.pos[:, 1]], axis=-1)       # middle of the visible canopy

    # Which bushes exist when (an Interlude shows only the trial's pair).
    trials = [e for e in log.events if e["type"] == "trial_start"]
    trial_t = np.array([e["t"] for e in trials])
    trial_pair = [(int(parse_note(e["note"])["left"]), int(parse_note(e["note"])["right"])) for e in trials]

    hide_locks = []
    for e in log.events:
        if e["type"] == "choice_lock":
            note = parse_note(e["note"])
            if note.get("policy") == "Hide":
                hide_locks.append((e["t"], int(note["locked"])))

    tr = log.traj
    if dt is None:
        idx = np.arange(len(tr)) if frames is None else np.asarray(frames)
        times = tr[idx, 0]
    else:
        times = np.arange(0.0, tr[-1, 0], dt)
        idx = np.clip(np.searchsorted(tr[:, 0], times, side="right") - 1, 0, len(tr) - 1)

    rows = {name: [] for name in Visibility.FIELDS}
    offsets = [0]
    for s, f in enumerate(idx):
        t, x, z, yaw, pitch, _ = tr[f]
        eye = np.array([x, float(sample_grid(elevation, half, x, z)) + eye_height, z])
        fwd, right, up = camera_axes(yaw, pitch)

        candidates = np.arange(n)
        if trials:
            k = max(int(np.searchsorted(trial_t, t + 1e-4, side="right")) - 1, 0)
            candidates = np.array(trial_pair[k], dtype=int)
            gone = [locked for t_lock, locked in hide_locks if t >= t_lock + HIDE_SECONDS]
            candidates = np.array([c for c in candidates if c not in gone], dtype=int)
        near_enough = np.hypot(*(b.pos[candidates] - eye[[0, 2]]).T) <= max_distance + rx[candidates]
        candidates = candidates[near_enough]

        v = pts[candidates] - eye                                         # (m, P, 3) eye -> point
        dist = np.linalg.norm(v, axis=-1)
        zc, xc, yc = v @ fwd, v @ right, v @ up
        in_view = (zc > near) & (np.abs(xc) <= zc * tan_h) & (np.abs(yc) <= zc * tan_v) & (dist <= max_distance)
        facing = np.einsum("mpk,mpk->mp", normals[candidates], -v) > 0
        ok = in_view & facing

        # Terrain occlusion, only for the points that passed the cheap tests.
        mi, pi = np.nonzero(ok)
        if len(mi):
            target = pts[candidates[mi], pi]                              # (r, 3)
            length = np.linalg.norm(target - eye, axis=-1)
            steps = max(2, int(math.ceil(length.max() / RAY_STEP)))
            frac = (np.arange(steps) + 0.5) / steps                       # (S,)
            along = eye[None, None, :] + (target - eye)[:, None, :] * frac[None, :, None]    # (r, S, 3)
            blocked = (sample_grid(elevation, half, along[..., 0], along[..., 2]) > along[..., 1]).any(axis=1)
            ok[mi[blocked], pi[blocked]] = False

        frac_visible = ok.mean(axis=1)
        seen = frac_visible > 0
        for c, i in enumerate(candidates):
            if not seen[c]:
                continue
            d = mid[i] - eye
            dd = float(np.linalg.norm(d))
            width = math.degrees(2.0 * math.atan2(rx[i], dd))
            height = math.degrees(math.atan2(ry[i], dd))
            if max(width, height) < min_angular_deg:
                continue
            zc_m = float(d @ fwd)
            rows["tree_id"].append(int(i))
            rows["azimuth"].append(math.degrees(math.atan2(float(d @ right), zc_m)))
            rows["elevation"].append(math.degrees(math.atan2(float(d @ up), math.hypot(zc_m, float(d @ right)))))
            rows["distance"].append(dd)
            rows["width"].append(width)
            rows["height"].append(height)
            rows["visible_fraction"].append(float(frac_visible[c]))
        offsets.append(len(rows["tree_id"]))

    arrays = {k: np.array(v, dtype=int if k == "tree_id" else float) for k, v in rows.items()}
    return Visibility(times, np.asarray(idx), np.array(offsets), **arrays)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("session", help="session folder or session id under ForagingData/")
    parser.add_argument("--dt", type=float, default=0.1, help="seconds between steps (default 0.1)")
    parser.add_argument("--min-angular", type=float, default=0.0, help="drop bushes whose angular size is below this (degrees)")
    parser.add_argument("--csv", default=None, help="write step,t,tree_id,azimuth,... rows to this file")
    args = parser.parse_args()

    log = load_session_log(args.session)
    vis = visible_bushes(log, dt=args.dt, min_angular_deg=args.min_angular)
    counts = vis.counts()
    print(f"{log.manifest['sessionName']} ({log.manifest['sessionId']}): {len(vis.t)} steps of {args.dt} s; "
          f"visible bushes per step: mean {counts.mean():.1f}, min {counts.min()}, max {counts.max()}")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["step", "t", *Visibility.FIELDS])
            for s in range(len(vis.t)):
                row = vis.at(s)
                for r in range(len(row["tree_id"])):
                    w.writerow([s, f"{vis.t[s]:.4f}", *[f"{row[k][r]:.4f}" if k != "tree_id" else int(row[k][r]) for k in Visibility.FIELDS]])
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
