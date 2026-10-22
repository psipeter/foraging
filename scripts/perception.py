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

Later constraints (terrain occlusion from scripts/visibility.py, a resolvability threshold on angular size, attribute noise,
different ranges per attribute) are new percept classes here, calibrated against participants' logged visible sets.
"""

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Observation:
    """The bushes in view at one moment: ids into the world's bush table, positions, canopy radii, attributes (n, 3: shape,
    color, moisture) and whether each looks spent."""
    ids: np.ndarray
    pos: np.ndarray
    radius: np.ndarray
    attrs: np.ndarray
    depleted: np.ndarray


class NullPercept:
    """Sees nothing (an agent that relies entirely on what its memory was given)."""
    observes = False

    def observe(self, world, pos, heading, depleted):
        return Observation(np.zeros(0, dtype=int), np.zeros((0, 2)), np.zeros(0), np.zeros((0, 3)), np.zeros(0, dtype=bool))


class ConePercept:
    """A view cone: a bush is seen when the edge of its canopy is within `distance` of the viewer and any part of it lies
    within `angle` degrees (total, horizontal) centered on the heading. Attributes are seen exactly; terrain does not hide
    anything (see scripts/visibility.py for a model that does)."""
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
