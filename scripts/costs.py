"""Time costs of the participant's body: turning the view with the mouse and pressing keys, plus the arithmetic of getting
from where the agent stands to the first fruit of a bush.

Shared by the engine (sim.py) and by the actors' own time models (agents.View.travel_times, PlannerActor), so that what an
agent expects an action to cost is what the engine charges. Every action therefore costs time somewhere: a turn costs
TURN_OVERHEAD plus the angle over TURN_RATE, a walk costs a W press plus the walking, a harvest costs a Space press plus its
fruits.

The constants are provisional, fitted to the developer's own debug sessions (ForagingData holds no participant data yet):
over 91 turns of 20 degrees or more, turn time was about 0.17 s + angle / 477 deg/s; the median wait between a bush becoming
harvestable and the Space press was 0.32 s over 58 presses. The W-press time is a guess (no log isolates it). Recalibrate all
of them from participants' logs (scripts/replay.py).
"""

import math

import numpy as np

TURN_RATE = 480.0        # degrees per second of turning the view with the mouse
TURN_OVERHEAD = 0.17     # seconds to start and settle a turn, whatever its size
TURN_DEADBAND = 5.0      # degrees: an implicit turn (before a walk) smaller than this is not needed
WALK_PRESS_TIME = 0.2    # seconds to press W and start moving
HARVEST_PRESS_TIME = 0.3  # seconds to press Space once the bush is in reach and in view


def wrap(angle):
    """Signed shortest angle in degrees, in [-180, 180)."""
    return (np.asarray(angle, dtype=float) + 180.0) % 360.0 - 180.0


def bearing(dx, dz):
    """Yaw in degrees (about +Y, from +Z toward +X: the game's convention) of the direction (dx, dz)."""
    return np.degrees(np.arctan2(dx, dz))


def turn_time(angle, deadband=0.0):
    """Seconds to turn the view by `angle` degrees (the amount turned, not wrapped); 0 when it is within `deadband`."""
    a = np.abs(np.asarray(angle, dtype=float))
    return np.where(a <= deadband, 0.0, TURN_OVERHEAD + a / TURN_RATE)


def approach(pos, heading, targets, radius, reach, speed, max_angle):
    """What it takes to start harvesting each of `targets` ((n, 2) positions) from `pos` facing `heading`.

    Returns (dist, walk, turn, press, walking, new_heading), each (n,):
      dist         center distance
      walk         distance to walk to enter harvest range (0 when already in range)
      turn         seconds of turning: to face the bush when there is a walk (movement follows the view), else just enough to
                   bring it inside the harvest cone (`max_angle` beyond the canopy's angular radius)
      press        seconds of key presses: W when there is a walk, then Space
      walking      seconds of walking
      new_heading  the heading after: toward the bush when there is a walk (movement follows the view); otherwise the heading
                   turned only by the amount charged (so none when the bush is already inside the harvest cone)
    The seconds before the first fruit are turn + press + walking."""
    d = np.asarray(targets, dtype=float) - np.asarray(pos, dtype=float)
    dist = np.hypot(d[..., 0], d[..., 1])
    walk = np.maximum(0.0, dist - reach)
    brg = np.where(dist > 0.0, bearing(d[..., 0], d[..., 1]), heading)
    delta = np.abs(wrap(brg - heading))
    with np.errstate(divide="ignore", invalid="ignore"):
        ang_r = np.where(dist > 1e-9, np.degrees(np.arcsin(np.clip(radius / np.where(dist > 1e-9, dist, 1.0), 0.0, 1.0))), 90.0)
    turn = np.where(walk > 0.0, turn_time(delta, TURN_DEADBAND), turn_time(np.maximum(0.0, delta - ang_r - max_angle)))
    press = np.where(walk > 0.0, WALK_PRESS_TIME, 0.0) + HARVEST_PRESS_TIME
    signed = wrap(brg - heading)
    in_range_turn = np.sign(signed) * np.maximum(0.0, delta - ang_r - max_angle)
    new_heading = np.where(walk > 0.0, brg, wrap(heading + in_range_turn))
    return dist, walk, turn, press, walk / speed, new_heading
