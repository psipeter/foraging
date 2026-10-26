"""What the simulated observer perceives: the sensor model the engine applies.

Perception belongs to the environment, not to an agent: it models the participant's body and screen (field of view, how far
attributes can be resolved, eventually terrain occlusion), which are the same for every agent playing a session. It is applied
by sim.run_episode, and resolved in this order:

    1. `agent.percept`, if the agent sets one (a deliberately different observer),
    2. the `percept=` argument of the run (a sensitivity sweep over the sensor),
    3. the world's own default: `world.percept` if set, else `percept_from_params(world.params)`, a cone as wide as the
       session's camera field of view, with no distance limit.

A percept has `observe(world, pos, heading, depleted) -> Observation` and `observes` (False when it never sees anything, so
the engine can skip it). Heading is a yaw in degrees (about +Y from +Z toward +X), the game's convention.

Later constraints (a resolvability threshold on angular size, attribute noise,
different ranges per attribute) are new percept classes here, calibrated against participants' logged visible sets.
"""

import math
from dataclasses import dataclass

import numpy as np

from specs import Component


@dataclass
class Observation:
    """The bushes in view at one moment: ids into the world's bush table, positions, canopy radii, attributes (n, 3: shape,
    color, moisture) and whether each looks spent."""
    ids: np.ndarray
    pos: np.ndarray
    radius: np.ndarray
    attrs: np.ndarray
    depleted: np.ndarray


# Directions of the canopy surface sample points: (elevation above the horizon in degrees, azimuth in degrees); the crown
# is the first point. Points on the far side of the canopy are dropped per frame (they face away from the eye).
SURFACE_RINGS = ((90.0, (0.0,)), (50.0, (0.0, 90.0, 180.0, 270.0)), (15.0, (0.0, 60.0, 120.0, 180.0, 240.0, 300.0)))

def canopy_height_of(shape, shape_range, height_range):
    """Full canopy height (Tree.ApplyAttributes): squat/wide at the low end of `shape_range`, tall/narrow at the high end."""
    lo, hi = shape_range
    t = np.clip((np.asarray(shape, dtype=float) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return height_range[0] + (height_range[1] - height_range[0]) * t



def sample_grid(grid, half, x, z):
    """Bilinear sample of a (res, res) grid indexed [x, z] spanning [-half, half] (WorldData.Sample); clamped at the edge."""
    res = grid.shape[0]
    u = np.clip((np.asarray(x, dtype=float) + half) / (2.0 * half) * (res - 1), 0.0, res - 1 - 1e-9)
    v = np.clip((np.asarray(z, dtype=float) + half) / (2.0 * half) * (res - 1), 0.0, res - 1 - 1e-9)
    i, j = u.astype(int), v.astype(int)
    fu, fv = u - i, v - j
    return ((1 - fu) * (1 - fv) * grid[i, j] + fu * (1 - fv) * grid[i + 1, j]
            + (1 - fu) * fv * grid[i, j + 1] + fu * fv * grid[i + 1, j + 1])



def unit_directions():
    """(P, 3) unit vectors (x, up, z) of the canopy surface sample points."""
    out = []
    for elev, azimuths in SURFACE_RINGS:
        e = math.radians(elev)
        for a in azimuths:
            a = math.radians(a)
            out.append((math.cos(e) * math.sin(a), math.sin(e), math.cos(e) * math.cos(a)))
    return np.array(out)        # (P, 3) as (x, up, z) on the unit sphere


RAY_STEP = 3.0          # world units between terrain samples along a line of sight (the mesh cell is about 1.6)


def hidden_by_terrain(eye, target, grid, half):
    """(r,) True where the straight line from `eye` to each `target` point ((r, 3)) dips below the elevation `grid` (a heightfield
    march every RAY_STEP units)."""
    length = np.linalg.norm(target - eye, axis=-1)
    steps = max(2, int(math.ceil(length.max() / RAY_STEP)))
    frac = (np.arange(steps) + 0.5) / steps
    along = eye[None, None, :] + (target - eye)[:, None, :] * frac[None, :, None]
    return (sample_grid(grid, half, along[..., 0], along[..., 2]) > along[..., 1]).any(axis=1)


def hidden_by_bushes(eye, target, own, occluders, pos, ground, rx, ry, chunk=256):
    """(r,) True where the straight line from `eye` to each `target` point ((r, 3)) passes through the canopy of a bush other than
    `own` ((r,) the target's bush). A canopy is the upper half of an ellipsoid centred on the ground at the bush's (x, z) with
    horizontal radius `rx` and vertical radius `ry` (as Tree.ApplyAttributes builds it); `occluders` are the ids of the bushes that
    can hide something. Only the part of the ray inside an ellipsoid that is above the ground counts."""
    hidden = np.zeros(len(target), dtype=bool)
    if len(occluders) == 0 or len(target) == 0:
        return hidden
    centre = np.stack([pos[occluders, 0], ground[occluders], pos[occluders, 1]], axis=1)          # (O, 3)
    scale = np.stack([rx[occluders], ry[occluders], rx[occluders]], axis=1)                       # (O, 3)
    q0 = (eye[None, :] - centre) / scale
    c = (q0 * q0).sum(-1) - 1.0                                                                   # (O,)
    for s in range(0, len(target), chunk):
        d = target[s:s + chunk] - eye                                                             # (k, 3)
        dq = d[:, None, :] / scale[None]                                                          # (k, O, 3)
        a = (dq * dq).sum(-1)
        b = 2.0 * (q0[None] * dq).sum(-1)
        disc = b * b - 4.0 * a * c[None]
        root = np.sqrt(np.maximum(disc, 0.0))
        t_in, t_out = (-b - root) / (2.0 * a), (-b + root) / (2.0 * a)
        lo, hi = np.maximum(t_in, 0.0), np.minimum(t_out, 1.0 - 1e-4)
        above_ground = np.maximum(eye[1] + lo * d[:, None, 1], eye[1] + hi * d[:, None, 1]) >= centre[None, :, 1]
        hit = (disc > 0.0) & (lo < hi) & above_ground & (occluders[None, :] != own[s:s + chunk, None])
        hidden[s:s + chunk] = hit.any(axis=1)
    return hidden


class NullPercept(Component):
    """Sees nothing (an agent that relies entirely on what its memory was given)."""
    observes = False

    def observe(self, world, pos, heading, depleted):
        return Observation(np.zeros(0, dtype=int), np.zeros((0, 2)), np.zeros(0), np.zeros((0, 3)), np.zeros(0, dtype=bool))


class ConePercept(Component):
    """A view cone: a bush is seen when the edge of its canopy is within `distance` of the viewer and any part of it lies
    within `angle` degrees (total, horizontal) centered on the heading. Attributes are seen exactly; terrain does not hide
    anything (`OccludedConePercept` below does)."""
    observes = True

    def __init__(self, angle, distance):
        self.angle = float(angle)
        self.distance = float(distance)

    def __repr__(self):
        return f"ConePercept(angle={self.angle:g}, distance={self.distance:g})"

    def observe(self, world, pos, heading, depleted):
        dx = world.pos[:, 0] - pos[0]
        dz = world.pos[:, 1] - pos[1]
        dist = np.hypot(dx, dz)
        r = world.canopy_radius
        with np.errstate(divide="ignore", invalid="ignore"):
            ang_r = np.where(dist > 1e-9, np.degrees(np.arcsin(np.clip(r / dist, 0.0, 1.0))), 90.0)
        delta = (np.degrees(np.arctan2(dx, dz)) - heading + 180.0) % 360.0 - 180.0
        seen = (dist - r <= self.distance) & (np.abs(delta) - ang_r <= self.angle / 2.0)
        ids = np.flatnonzero(seen)
        return Observation(ids, world.pos[ids], r[ids],
                           np.column_stack([world.shape[ids], world.color[ids], world.moisture[ids]]), depleted[ids].copy())


class OccludedConePercept(ConePercept):
    """The view cone with line-of-sight occlusion, the same geometry as scripts/visibility.py (which reconstructs what a participant
    saw): a bush is seen when at least one of the sample points on the camera-facing part of its canopy lies inside the horizontal
    cone and the straight line from the eye (at the session's eye height above the terrain) reaches it over the terrain and
    through no other bush's canopy (an opaque half-ellipsoid, canopy height from the session's shape and canopy-height ranges).
    The viewer's pitch is not simulated, so there is no vertical field of view. Attributes are seen exactly."""

    def __repr__(self):
        return f"OccludedConePercept(angle={self.angle:g}, distance={self.distance:g})"

    def _geometry(self, world):
        cached = getattr(world, "_occlusion_geometry", None)
        if cached is None:
            p = world.params
            grid = world.terrain.grids()["elevation"]
            half = float(p.world_half_extent)
            rx = world.canopy_radius
            ry = canopy_height_of(world.shape, p.shape_range, p.canopy_height_range) * 0.5
            ground = sample_grid(grid, half, world.pos[:, 0], world.pos[:, 1])
            dirs = unit_directions()
            pts = np.stack([world.pos[:, None, 0] + rx[:, None] * dirs[None, :, 0],
                            ground[:, None] + ry[:, None] * dirs[None, :, 1],
                            world.pos[:, None, 1] + rx[:, None] * dirs[None, :, 2]], axis=-1)       # (n, P, 3)
            normals = np.stack([dirs[None, :, 0] / rx[:, None], dirs[None, :, 1] / ry[:, None], dirs[None, :, 2] / rx[:, None]], axis=-1)
            cached = world._occlusion_geometry = (grid, half, rx, ry, ground, pts, normals, float(p.eye_height))
        return cached

    def observe(self, world, pos, heading, depleted):
        cone = super().observe(world, pos, heading, depleted)
        if len(cone.ids) == 0:
            return cone
        grid, half, rx, ry, ground, pts, normals, eye_height = self._geometry(world)
        eye = np.array([pos[0], float(sample_grid(grid, half, pos[0], pos[1])) + eye_height, pos[1]])
        ids = cone.ids
        v = pts[ids] - eye                                                                         # (m, P, 3)
        azimuth = (np.degrees(np.arctan2(v[..., 0], v[..., 2])) - heading + 180.0) % 360.0 - 180.0
        ok = (np.abs(azimuth) <= self.angle / 2.0) & (np.einsum("mpk,mpk->mp", normals[ids], -v) > 0)
        mi, pi = np.nonzero(ok)
        if len(mi):
            target = pts[ids[mi], pi]
            blocked = hidden_by_terrain(eye, target, grid, half)
            ok[mi[blocked], pi[blocked]] = False
            mi, pi = np.nonzero(ok)
            if len(mi):
                reach = np.hypot(*(world.pos - eye[[0, 2]]).T) <= np.linalg.norm(pts[ids[mi], pi] - eye, axis=-1).max() + rx
                behind = hidden_by_bushes(eye, pts[ids[mi], pi], ids[mi], np.flatnonzero(reach), world.pos, ground, rx, ry)
                ok[mi[behind], pi[behind]] = False
        keep = ok.any(axis=1)
        return Observation(ids[keep], cone.pos[keep], cone.radius[keep], cone.attrs[keep], cone.depleted[keep])


def horizontal_fov(vertical_fov_deg, aspect=16.0 / 9.0):
    """Horizontal field of view (degrees) of a camera with this vertical FOV and width / height aspect."""
    return math.degrees(2.0 * math.atan(math.tan(math.radians(vertical_fov_deg) / 2.0) * aspect))


def percept_from_params(params, aspect=16.0 / 9.0, distance=1000.0):
    """The default observer for a session: a cone as wide as the camera's horizontal field of view (from the session's vertical
    FOV and a screen `aspect`; 75 deg vertical at 16:9 is about 107.5 deg), with no practical distance limit (the camera's far
    clip is 1000). A toy world without camera parameters gets the same 75 deg vertical FOV."""
    vfov = float(getattr(params, "camera_field_of_view", 75.0))
    return ConePercept(horizontal_fov(vfov, aspect), distance)


def percept_for(world):
    """The world's own percept: `world.percept` if set, else the default for its session parameters."""
    own = getattr(world, "percept", None)
    return own if own is not None else percept_from_params(world.params)
