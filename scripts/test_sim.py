from types import SimpleNamespace

import numpy as np
import pytest

from agents import Agent
from sim import run_episode, run_n
from world import World, make_world


def tiny_world(pos, rewards, duration=60.0, speed=5.0, fd=0.5, radius=1.0, gap=7.0):
    pos = np.array(pos, dtype=float)
    n = len(pos)
    params = SimpleNamespace(session_duration=duration, player_move_speed=speed, fruit_harvest_duration=fd,
                             harvest_range_gap_base=gap, harvest_range_gap_per_radius=0.0)
    fr = np.array(rewards, dtype=np.int32)
    return World(params=params, seed=0, pos=pos, shape=np.zeros(n), color=np.zeros(n), moisture=np.zeros(n),
                 canopy_radius=np.full(n, radius), value=fr.mean(1), fruit_reward=fr, start=np.zeros(2))


class Fixed(Agent):
    """Visits a fixed list of bushes; leaves each after `take` fruits (None = exhaust)."""
    def __init__(self, order, take=None):
        self.order, self.take, self.k = list(order), take, 0

    def choose_target(self, state):
        return self.order.pop(0) if self.order else None

    def keep_harvesting(self, state, bush, reward):
        return self.take is None or state.fruits_taken[bush] < self.take


def test_walk_and_harvest_arithmetic():
    # reach = radius 1 + gap 7 = 8; bush at distance 48 -> walk 40 units = 8 s; 4 fruits * 0.5 s = 2 s
    w = tiny_world([[48, 0]], [[1, 2, 3, 4]])
    r = run_episode(Fixed([0]), w)
    assert r.total == 10 and r.n_fruits == 4
    assert r.walk_time == pytest.approx(8.0) and r.harvest_time == pytest.approx(2.0)
    assert r.idle_time == pytest.approx(50.0)


def test_position_tracking_between_bushes():
    # Bush 0 at x=48 -> stop at x=40. Bush 1 at x=48+30: distance from 40 is 38, reach 8 -> walk 30 (6 s).
    w = tiny_world([[48, 0], [78, 0]], [[1, 1], [5, 5]])
    r = run_episode(Fixed([0, 1]), w)
    assert r.walk_time == pytest.approx(8.0 + 6.0) and r.total == 12


def test_already_in_range_costs_no_walking():
    w = tiny_world([[5, 0]], [[2, 2]])
    r = run_episode(Fixed([0]), w)
    assert r.walk_time == 0 and r.total == 4


def test_leaving_early_keeps_remainder_and_resume():
    w = tiny_world([[5, 0], [6, 0]], [[1, 2, 3, 4], [9, 9, 9, 9]])
    r = run_episode(Fixed([0, 1, 0], take=2), w)
    # bush 0: fruits 1,2 (3); bush 1: fruits 9,9 (18); back to bush 0: resumes at fruit index 2 -> 3,4? take=2 total taken
    # so keep_harvesting is False immediately after the first resumed fruit (taken=3 >= 2)
    assert r.trace[0] == (0, 2, 3.0) and r.trace[1] == (1, 2, 18.0) and r.trace[2][0] == 0
    assert r.trace[2][2] == 3.0 and r.total == 24.0


def test_depleted_bush_cannot_be_revisited():
    w = tiny_world([[5, 0]], [[1, 1]])
    with pytest.raises(ValueError):
        run_episode(Fixed([0, 0]), w)


def test_session_clock_cuts_off_mid_fruit_and_mid_walk():
    w = tiny_world([[5, 0]], [[1] * 10], duration=2.2)   # fruits at 0.5 s: only 4 fit in 2.2 s
    r = run_episode(Fixed([0]), w)
    assert r.n_fruits == 4 and r.total == 4
    w2 = tiny_world([[500, 0]], [[1, 1]], duration=10.0)  # too far to reach in time
    r2 = run_episode(Fixed([0]), w2)
    assert r2.total == 0 and r2.walk_time == pytest.approx(10.0)


def test_real_world_runs_and_is_paired_reproducible():
    class Nearest(Agent):
        def choose_target(self, state):
            t = state.travel_times()
            t[state.depleted] = np.inf
            return int(np.argmin(t))
    a = run_n(Nearest, "S1", seeds=range(5))
    b = run_n(Nearest, "S1", seeds=range(5))
    assert np.array_equal(a.totals, b.totals) and a.mean > 0
    r = a.results[0]
    assert r.walk_time + r.harvest_time + r.idle_time == pytest.approx(60.0)
