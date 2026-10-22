from types import SimpleNamespace

import numpy as np
import pytest

import itertools

from agents import (REGISTRY, Actor, ComposedAgent, GreedyAgent, Harvest, NearestAgent, PlannerAgent, UtilityActor,
                    oracle_agent)
import sim
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


class FixedActor(Actor):
    """Visits a fixed list of bushes; leaves each after `take` fruits (None = exhaust)."""
    def __init__(self, order, take=None):
        self.order, self.take = list(order), take

    def act(self, view):
        return Harvest(self.order.pop(0)) if self.order else None

    def keep_harvesting(self, view, bush, reward):
        return self.take is None or view.memory.taken[bush] < self.take


def Fixed(order, take=None):
    return oracle_agent(FixedActor(order, take))


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


@pytest.mark.slow
def test_real_world_runs_and_is_paired_reproducible():
    a = run_n(NearestAgent, "S1", seeds=range(5))
    b = run_n(NearestAgent, "S1", seeds=range(5))
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
    agent = REGISTRY["greedy_value_10"]()
    assert isinstance(agent, ComposedAgent) and isinstance(agent.actor, UtilityActor) and agent.actor.max_walk_time == 10
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


@pytest.mark.slow
def test_planner_exact_matches_brute_force():
    for seed in range(2):
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


def test_a_fruit_that_exactly_fits_the_remaining_time_is_taken():
    # walk 8 s (bush 48 away, reach 8, speed 5) then two 0.5 s fruits: a 9.0 s session fits both to the last instant.
    w = tiny_world([[48, 0]], [[1, 2, 3, 4]], duration=9.0)
    r = run_episode(Fixed([0]), w)
    assert r.n_fruits == 2 and r.total == 3 and r.idle_time == pytest.approx(0.0) and r.harvest_time == pytest.approx(1.0)
    r = run_episode(Fixed([0]), tiny_world([[48, 0]], [[1, 2, 3, 4]], duration=8.99))
    assert r.n_fruits == 1                                    # the second fruit would end after the clock


def test_a_walk_that_exactly_fits_arrives_but_one_that_does_not_stops_short():
    w = tiny_world([[48, 0]], [[1, 2, 3, 4]], duration=8.0)
    r = run_episode(Fixed([0]), w)
    assert r.walk_time == pytest.approx(8.0) and r.n_fruits == 0 and r.trace and r.trace[0][0] == 0     # arrived, no time left
    r = run_episode(Fixed([0]), tiny_world([[48, 0]], [[1, 2, 3, 4]], duration=7.9))
    assert r.walk_time == pytest.approx(7.9) and r.n_fruits == 0 and not r.trace                         # ran out on the way


# --- the motor costs: turning the view and pressing keys (costs.py) ------------------------------------------------

import costs
from agents import Explore, FullKnowledge, Look, OracleCritic, Stop


class Sequence(Actor):
    """Plays a fixed list of actions, then stops."""
    def __init__(self, *actions):
        self.actions = list(actions)

    def act(self, view):
        return self.actions.pop(0) if self.actions else Stop()


def seq_agent(*actions):
    return oracle_agent(Sequence(*actions))


@pytest.mark.motor_costs
def test_a_harvest_straight_ahead_costs_the_two_presses_and_the_walk():
    # bush dead ahead (+Z), 48 away: reach 8 -> walk 40 (8 s); no turn; W press then Space press; 4 fruits
    r = run_episode(Fixed([0]), tiny_world([[0, 48]], [[1, 2, 3, 4]]))
    assert r.look_time == 0.0 and r.press_time == pytest.approx(costs.WALK_PRESS_TIME + costs.HARVEST_PRESS_TIME)
    assert r.walk_time == pytest.approx(8.0) and r.harvest_time == pytest.approx(2.0)
    assert r.idle_time == pytest.approx(60.0 - 8.0 - 2.0 - r.press_time)


@pytest.mark.motor_costs
def test_a_bush_to_the_side_costs_a_turn():
    r = run_episode(Fixed([0]), tiny_world([[48, 0]], [[1, 2, 3, 4]]))             # 90 degrees to the right
    assert r.look_time == pytest.approx(costs.TURN_OVERHEAD + 90.0 / costs.TURN_RATE)
    r = run_episode(Fixed([0]), tiny_world([[40 * np.sin(np.radians(3)), 40 * np.cos(np.radians(3))]], [[1, 2]]))
    assert r.look_time == 0.0                                                       # 3 degrees is inside the deadband


@pytest.mark.motor_costs
def test_a_bush_in_range_but_behind_needs_only_enough_turn_to_bring_it_into_the_cone():
    w = tiny_world([[0, -5]], [[1, 2]])                    # 5 behind: in range, no walk, so no W press
    r = run_episode(Fixed([0]), w)
    ang_r = np.degrees(np.arcsin(1.0 / 5.0))
    assert r.walk_time == 0.0 and r.press_time == pytest.approx(costs.HARVEST_PRESS_TIME)
    assert r.look_time == pytest.approx(costs.TURN_OVERHEAD + (180.0 - ang_r - 35.0) / costs.TURN_RATE)
    r = run_episode(Fixed([0]), tiny_world([[0, 5]], [[1, 2]]))
    assert r.look_time == 0.0                              # in range and already in view: no turn


@pytest.mark.motor_costs
def test_the_clock_can_run_out_during_a_turn_or_a_press():
    w = tiny_world([[48, 0]], [[1, 2]], duration=0.2)       # the 90 degree turn takes 0.36 s
    r = run_episode(Fixed([0]), w)
    assert r.look_time == pytest.approx(0.2) and r.press_time == 0.0 and r.idle_time == 0.0 and r.n_fruits == 0
    w = tiny_world([[0, 48]], [[1, 2]], duration=0.3)       # no turn; the W press takes 0.2, then walking
    r = run_episode(Fixed([0]), w)
    assert r.press_time == pytest.approx(0.2) and r.walk_time == pytest.approx(0.1) and r.idle_time == 0.0


@pytest.mark.motor_costs
def test_every_action_costs_time_and_a_no_op_is_refused():
    w = tiny_world([[500, 500]], [[1, 1]])
    with pytest.raises(ValueError):
        run_episode(seq_agent(Look(0.0)), w)
    with pytest.raises(ValueError):
        run_episode(seq_agent(Explore(0.0, 0.0)), w)
    with pytest.raises(ValueError):
        run_episode(seq_agent(Explore(0.0, -5.0)), w)
    r = run_episode(seq_agent(Look(1.0)), w)                  # even one degree costs the turn overhead
    assert r.look_time == pytest.approx(costs.TURN_OVERHEAD + 1.0 / costs.TURN_RATE)
    r = run_episode(seq_agent(Explore(0.0, 1.0)), w)          # a walk costs the press even if it goes nowhere useful
    assert r.press_time == pytest.approx(costs.WALK_PRESS_TIME)


def test_an_engine_that_would_never_advance_says_so():
    # with every motor cost zero, exploring into a wall takes no time at all: refuse rather than loop forever
    from types import SimpleNamespace
    w = tiny_world([[500, 500]], [[1, 1]])
    w.params.world_half_extent, w.params.mountain_block_threshold = 100.0, 0.5
    w._terrain = SimpleNamespace(mountain_ramp=lambda x, z: 1.0)
    with pytest.raises(RuntimeError):
        run_episode(seq_agent(Explore(90.0, 10.0)), w)


def test_an_agent_cannot_harvest_a_bush_it_has_never_seen():
    from agents import ComposedAgent, FullMemory, OracleCritic
    from perception import NullPercept
    w = tiny_world([[5, 0]], [[1, 2]])
    blind = ComposedAgent(Sequence(Harvest(0)), OracleCritic(), FullMemory(), NullPercept())
    with pytest.raises(ValueError, match="never seen"):
        run_episode(blind, w)
    for bad in (-1, 1, 7):
        with pytest.raises(ValueError, match="does not exist"):
            run_episode(Fixed([bad]), w)


@pytest.mark.motor_costs
def test_time_is_conserved_under_random_actions():
    # walk + look + press + harvest + idle == the session, whatever the actor does and wherever the clock cuts in
    from types import SimpleNamespace

    class Random(Actor):
        def act(self, view):
            u = self.rng.random()
            if u < 0.35:
                known = np.flatnonzero(view.candidates())
                return Harvest(int(self.rng.choice(known))) if len(known) else Explore(float(self.rng.uniform(0, 360)), 20.0)
            if u < 0.75:
                return Explore(float(self.rng.uniform(0, 360)), float(self.rng.uniform(0.5, 60.0)))
            return Look(float(self.rng.uniform(-300, 300)) or 1.0)

    for seed in range(40):
        rng = np.random.default_rng(seed)
        w = tiny_world(rng.uniform(-60, 60, (8, 2)), rng.integers(0, 5, (8, 6)), duration=float(rng.uniform(1, 40)),
                       fd=float(rng.choice([0.2, 0.5])))
        w.params.world_half_extent, w.params.mountain_block_threshold = 70.0, 0.5
        w._terrain = SimpleNamespace(mountain_ramp=lambda x, z: 1.0 if abs(x) > 45.0 else 0.0)
        agent = oracle_agent(Random())
        r = run_episode(agent, w)
        used = r.walk_time + r.look_time + r.press_time + r.harvest_time + r.idle_time
        assert used == pytest.approx(w.session_duration, abs=1e-9), (seed, used, w.session_duration)
        assert min(r.walk_time, r.look_time, r.press_time, r.harvest_time, r.idle_time) >= 0.0


def test_a_wall_and_the_clock_cutting_the_same_chunk_keep_the_time_on_the_clock():
    from types import SimpleNamespace
    # 5-unit chunks at 5 units/s; the wall (x > 22) falls inside the 5th chunk, which the 4.5 s clock would also cut half-way.
    w = tiny_world([[500, 500]], [[1, 1]], duration=4.5, speed=5.0)
    w.params.world_half_extent, w.params.mountain_block_threshold = 100.0, 0.5
    w._terrain = SimpleNamespace(mountain_ramp=lambda x, z: 1.0 if x > 22.0 else 0.0)
    r = run_episode(seq_agent(Explore(90.0, 1000.0)), w)
    assert r.walk_time == pytest.approx(4.25) and r.idle_time == pytest.approx(0.25)     # stopped at the wall, not at the clock


def test_fruit_timing_does_not_drift_over_hundreds_of_fruits():
    # 30 bushes of ten fruits all in range from the start, a 60 s session of 0.2 s fruits: exactly 300 fruits fit
    w = tiny_world([[i * 0.1, 0.0] for i in range(30)], [[1] * 10] * 30, duration=60.0, fd=0.2)
    r = run_episode(Fixed(list(range(30))), w)
    assert r.n_fruits == 300 and r.total == 300


@pytest.mark.slow
def test_an_interlude_is_shared_by_sessions_of_different_lengths():
    sim._interlude_for.cache_clear()
    a, _, _ = sim.get_interlude("P", 0, "random", session_duration=20, interlude_trial_count=4)
    b, _, _ = sim.get_interlude("P", 0, "random", session_duration=90, interlude_trial_count=4)
    assert a == b and sim._interlude_for.cache_info().misses == 1
    sim.get_interlude("P", 0, "random", session_duration=20, interlude_trial_count=5)       # a setting that does change it
    assert sim._interlude_for.cache_info().misses == 2


def test_the_result_lists_every_fruit_with_its_time_bush_and_reward():
    w = tiny_world(np.array([[5.0, 0.0], [-5.0, 0.0]]), [[2, 4, 6], [8, 8, 8]])
    res = run_episode(NearestAgent(), w)
    assert [f[1] for f in res.fruits] == [0, 0, 0, 1, 1, 1] or [f[1] for f in res.fruits] == [1, 1, 1, 0, 0, 0]
    assert len(res.fruits) == res.n_fruits and res.fruits[-1][4] == res.total and sum(f[3] for f in res.fruits) == res.total
    times = [f[0] for f in res.fruits]
    assert times == sorted(times) and times[0] > 0
    ks = {}
    for t, bush, k, reward, total in res.fruits:
        assert k == ks.get(bush, -1) + 1 and reward == w.fruit_reward[bush, k]
        ks[bush] = k


# --- checkpoints ---------------------------------------------------------------------------------------------------

def checkpoint_agent():
    from agents import DeltaRuleCritic, FullKnowledge
    return ComposedAgent(UtilityActor("nearest"), DeltaRuleCritic(), FullKnowledge())


def checkpoint_world(duration=60.0):
    from test_agents import world_with
    return world_with([[5, 0], [-6, 0]], rewards=[[2, 2, 2], [9, 9, 9]], attrs=[[0.1, 0.5, 0.5], [0.9, 0.5, 0.5]], duration=duration, fd=0.5)


def test_a_checkpoint_is_the_agent_as_it_was_then_and_equals_a_shorter_session():
    world = checkpoint_world()
    agent = checkpoint_agent()
    res = run_episode(agent, world, checkpoints=[0, 40, 60])
    first_end = res.fruits[2][0]                                                  # the first bush's last fruit
    mid = first_end + 0.1
    res = run_episode(agent := checkpoint_agent(), world, checkpoints=[0, mid, 60])
    assert sorted(res.snapshots) == [0.0, mid, 60.0]
    assert not res.snapshots[0.0].critic.w.any()                                  # before anything was learned
    assert np.allclose(res.snapshots[60.0].critic.w, agent.critic.w) and agent.critic.w.any()
    shorter = checkpoint_agent()
    run_episode(shorter, checkpoint_world(duration=mid))                          # a session that really ends at `mid`
    assert np.allclose(res.snapshots[mid].critic.w, shorter.critic.w)
    assert not np.allclose(res.snapshots[mid].critic.w, agent.critic.w)           # and it differs from the end: it learned after `mid`
    assert res.snapshots[60.0] is not agent and res.snapshots[60.0].critic is not agent.critic
    before = res.snapshots[mid].critic.w.copy()
    agent.critic.w += 1.0
    assert np.allclose(res.snapshots[mid].critic.w, before)                       # a snapshot is a copy


def test_checkpoints_after_the_agent_stops_get_its_final_state_and_none_means_no_snapshots():
    agent = ComposedAgent(Fixed([0]), OracleCritic(), FullKnowledge())
    res = run_episode(agent, tiny_world([[3, 0]], [[1, 1]], duration=30.0), checkpoints=[5, 30])
    assert sorted(res.snapshots) == [5.0, 30.0]
    assert run_episode(NearestAgent(), tiny_world([[3, 0]], [[1, 1]])).snapshots == {}


def test_checkpoints_must_be_inside_the_session_and_not_for_deadline_planners():
    w = tiny_world([[3, 0]], [[1, 1]], duration=30.0)
    for bad in ([-1], [31]):
        with pytest.raises(ValueError, match="within the session"):
            run_episode(NearestAgent(), w, checkpoints=bad)
    with pytest.raises(ValueError, match="plan for the end"):
        run_episode(PlannerAgent("beam"), w, checkpoints=[10])
    run_episode(PlannerAgent("beam"), w)                                          # fine without checkpoints
