from types import SimpleNamespace

import numpy as np
import pytest

import itertools

from agents import REGISTRY, Agent, GreedyAgent, NearestAgent, PlannerAgent
from sim import run_episode, run_n
from world import World, load_session, make_world


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
    assert r.walk_time + r.harvest_time + r.idle_time == pytest.approx(load_session("S1").session_duration)


def test_nearest_agent_visits_by_walking_time_and_exhausts():
    # From the start: bush 0 center 30 away (walk 22), bush 1 center 20 away (walk 12). Then bush 0 is the only one left.
    w = tiny_world([[30, 0], [0, 20]], [[1, 1], [2, 2]])
    r = run_episode(NearestAgent(), w)
    assert [t[0] for t in r.trace] == [1, 0] and r.total == 6 and r.n_fruits == 4
    assert REGISTRY["nearest"] is NearestAgent


def test_nearest_agent_stops_when_everything_is_gone():
    w = tiny_world([[5, 0]], [[1, 1]])
    r = run_episode(NearestAgent(), w)
    assert r.n_visits == 1 and r.idle_time == pytest.approx(59.0)


def _greedy_world():
    # start at origin; speed 5, reach 8. walk times: A (center 20) 2.4 s, B (center 40) 6.4 s, C (center 100) 18.4 s
    return tiny_world([[20, 0], [0, 40], [-100, 0]], [[1, 1], [3, 3], [9, 9]])


def test_greedy_value_picks_best_within_time_and_falls_back():
    w = _greedy_world()
    r = run_episode(GreedyAgent(max_walk_time=10, score="value"), w)
    assert r.trace[0][0] == 1                       # B beats nearer A; C is out of range
    r = run_episode(GreedyAgent(max_walk_time=1, score="value"), _greedy_world())
    assert r.trace[0][0] == 0                       # nothing within 1 s: falls back to the quickest (A)
    r = run_episode(GreedyAgent(max_walk_time=30, score="value"), _greedy_world())
    assert [t[0] for t in r.trace][0] == 2          # everything in range: highest value


def test_greedy_rate_trades_value_against_time():
    # Two bushes, 4 fruits each: far has value 2.0 / near has value 1.5. Walking 30 units more costs 6 s vs 2 s of harvest.
    w = tiny_world([[18, 0], [48, 0]], [[1, 2, 2, 1], [2, 2, 2, 2]])
    w.value = np.array([1.5, 2.0])
    assert run_episode(GreedyAgent(30, "value"), w).trace[0][0] == 1
    w = tiny_world([[18, 0], [48, 0]], [[1, 2, 2, 1], [2, 2, 2, 2]])
    w.value = np.array([1.5, 2.0])
    assert run_episode(GreedyAgent(30, "rate"), w).trace[0][0] == 0


def test_greedy_registry_and_stop():
    assert isinstance(REGISTRY["greedy_value_10"](), GreedyAgent)
    r = run_episode(GreedyAgent(10), tiny_world([[5, 0]], [[1, 1]]))
    assert r.n_visits == 1


def _noise_free_world(seed, n=7, duration=34.0):
    """Random small world whose fruit rewards equal R_bush exactly, so engine totals == planner objective."""
    rng = np.random.default_rng(seed)
    pos = rng.uniform(-60, 60, (n, 2))
    val = rng.integers(1, 10, n)
    w = tiny_world(pos, np.repeat(val[:, None], 4, axis=1), duration=duration)
    w.value = val.astype(float)
    return w


def _brute_force_best(w):
    best = 0.0
    for r in range(1, w.n + 1):
        for perm in itertools.permutations(range(w.n), r):
            best = max(best, run_episode(Fixed(perm), w).total)
    return best


def test_planner_exact_matches_brute_force():
    for seed in range(4):
        w = _noise_free_world(seed, n=6)
        agent = PlannerAgent("exact")
        total = run_episode(agent, w).total
        assert agent.exact
        assert total == pytest.approx(_brute_force_best(w))
        assert agent.plan_value == pytest.approx(total)


def test_planner_beam_is_close_and_never_beats_exact():
    for seed in range(4):
        w = _noise_free_world(seed, n=6)
        exact = run_episode(PlannerAgent("exact"), w).total
        beam = run_episode(PlannerAgent("beam", beam_width=50), w).total
        assert beam <= exact + 1e-9 and beam >= 0.9 * exact


def test_planner_not_worse_than_greedy_on_real_world():
    from sim import get_worlds
    w = get_worlds("S1", [0])[0]
    plan = PlannerAgent("beam", beam_width=100)
    run_episode(plan, w)
    greedy_trace = run_episode(GreedyAgent(15, "rate"), w).trace
    greedy_expected = sum(w.value[j] * n for j, n, _ in greedy_trace)   # expected reward of greedy's own route
    assert plan.plan_value >= greedy_expected - 1e-9
