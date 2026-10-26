from types import SimpleNamespace

import numpy as np
import pytest

from agents import (Actor, Argmax, Body, ComposedAgent, Critic, Explore, FullKnowledge, FullMemory, Harvest, Look, OracleCritic,
                    PlannerActor, Softmax, Stop, Task, UtilityActor, View, WorldKnowledge, oracle_agent, utility_rate,
                    REGISTRY, ConstantPrior, DeltaRuleCritic, NeutralPrior, Prior, RBFFeatures)
import costs
from interlude import generate_interlude
from world import load_session
from perception import (ConePercept, NullPercept, Observation, horizontal_fov, percept_for, percept_from_params)
from sim import State, evaluate_interlude, get_interlude, run_episode, run_n
from test_sim import tiny_world


def world_with(pos, rewards=None, attrs=None, **kw):
    pos = np.array(pos, dtype=float)
    rewards = rewards if rewards is not None else [[1, 1]] * len(pos)
    w = tiny_world(pos, rewards, **kw)
    if attrs is not None:
        a = np.asarray(attrs, dtype=float)
        w.shape, w.color, w.moisture = a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy()
    return w


class Script(Actor):
    """Plays a fixed list of actions, then stops."""
    def __init__(self, *actions):
        self.actions = list(actions)

    def act(self, view):
        return self.actions.pop(0) if self.actions else Stop()


class MeanCritic(Critic):
    """Every bush is worth the mean reward received so far (a stand-in learner that records what it was shown)."""
    def __init__(self):
        self.seen = []
        self.mean = 0.0

    def _fit(self, memory):
        attrs, rewards, ids = memory.experiences()
        self.seen.append(len(rewards))
        self.mean = float(rewards.mean()) if len(rewards) else 0.0

    def value(self, attrs, ids=None):
        n = len(attrs)
        return np.full(n, self.mean), np.zeros(n)


class TableCritic(Critic):
    """Values from a fixed per-bush table (to show the actor's utility comes from the critic)."""
    def __init__(self, table):
        self.table = np.asarray(table, dtype=float)

    def value(self, attrs, ids=None):
        return self.table[np.asarray(ids)], np.zeros(len(ids))


def begin_memory(memory, world):
    """What ComposedAgent.begin_session does for a memory: begin with the task, and grant omniscient ones the world's knowledge."""
    memory.begin(Task(world))
    if memory.omniscient:
        memory.grant(WorldKnowledge.from_world(world))
    return memory


# --- memory ------------------------------------------------------------------------------------------------

def test_full_knowledge_preloads_the_map_but_no_rewards():
    w = world_with([[10, 0], [0, 20]], attrs=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    m = begin_memory(FullKnowledge(), w)
    assert m.known.all() and np.array_equal(m.pos, w.pos) and np.allclose(m.attrs, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    assert m.map_version == 0 and (m.taken == 0).all() and len(m.experiences()[1]) == 0


def test_full_memory_accumulates_what_it_sees_and_gets():
    w = world_with([[10, 0], [0, 20], [30, 30]], attrs=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]])
    m = begin_memory(FullMemory(), w)
    assert not m.known.any()
    obs = Observation(np.array([2, 0]), w.pos[[2, 0]], w.canopy_radius[[2, 0]],
                      np.array([[0.7, 0.8, 0.9], [0.1, 0.2, 0.3]]), np.array([False, True]))
    m.observe(obs)
    assert list(np.flatnonzero(m.known)) == [0, 2] and m.map_version == 1
    assert np.allclose(m.pos[2], [30, 30]) and np.allclose(m.attrs[0], [0.1, 0.2, 0.3]) and m.depleted[0] and not m.depleted[2]
    m.observe(obs)
    assert m.map_version == 1                                   # nothing new
    m.record_reward(2, 3)
    m.record_reward(2, 5)
    m.record_reward(0, 1)
    attrs, rewards, ids = m.experiences()
    assert sorted(zip(ids, rewards)) == [(0, 1.0), (2, 3.0), (2, 5.0)]
    assert m.rewards[2] == [3.0, 5.0] and m.taken[2] == 2 and m.fruits_left()[2] == w.fruit_count - 2


# --- percept -----------------------------------------------------------------------------------------------

def test_cone_percept_angle_distance_and_heading():
    w = world_with([[0, 20], [20, 20], [0, -20], [0, 200], [-30, 5]], radius=1.0)
    cone = ConePercept(angle=90.0, distance=100.0)
    dep = np.zeros(w.n, dtype=bool)
    assert sorted(cone.observe(w, np.zeros(2), 0.0, dep).ids) == [0, 1]                 # ahead and 45 deg right
    assert sorted(cone.observe(w, np.zeros(2), 180.0, dep).ids) == [2]                   # turned around
    assert sorted(cone.observe(w, np.zeros(2), 90.0, dep).ids) == [1]                    # facing +x: 45 deg left of the line
    assert 4 in cone.observe(w, np.zeros(2), -90.0, dep).ids                              # facing -x
    # the canopy edge counts: center 105 away with radius 6 is 99 from the edge
    w2 = world_with([[0, 105]], radius=6.0)
    assert len(cone.observe(w2, np.zeros(2), 0.0, np.zeros(1, dtype=bool)).ids) == 1
    assert len(ConePercept(90.0, 90.0).observe(w2, np.zeros(2), 0.0, np.zeros(1, dtype=bool)).ids) == 0
    obs = cone.observe(w, np.zeros(2), 0.0, dep)
    assert np.allclose(obs.pos, w.pos[obs.ids]) and obs.attrs.shape == (2, 3) and not obs.depleted.any()


class Recorder:
    """A percept that sees nothing but records that it was used."""
    observes = True

    def __init__(self):
        self.calls = 0

    def observe(self, world, pos, heading, depleted):
        self.calls += 1
        return NullPercept().observe(world, pos, heading, depleted)


def test_default_percept_is_as_wide_as_the_session_camera():
    assert horizontal_fov(75.0, 16 / 9) == pytest.approx(107.5, abs=0.1)
    cone = percept_from_params(SimpleNamespace(camera_field_of_view=60.0))
    assert isinstance(cone, ConePercept) and cone.angle == pytest.approx(horizontal_fov(60.0)) and cone.distance == 1000.0
    assert percept_from_params(SimpleNamespace()).angle == pytest.approx(horizontal_fov(75.0))     # a toy world: the game's FOV
    w = world_with([[0, 20]])
    assert percept_for(w).angle == pytest.approx(horizontal_fov(75.0))
    w.percept = ConePercept(30.0, 50.0)
    assert percept_for(w).angle == 30.0                                       # the world's own percept wins


def test_percept_resolution_agent_override_then_run_then_world():
    w = world_with([[0, 20]])
    agent_pc, run_pc, world_pc = Recorder(), Recorder(), Recorder()
    w.percept = world_pc
    run_episode(ComposedAgent(Script(), OracleCritic(), FullMemory(), agent_pc), w, percept=run_pc)
    assert (agent_pc.calls, run_pc.calls, world_pc.calls) == (1, 0, 0)       # the agent's own sensor first
    agent_pc, run_pc, world_pc = Recorder(), Recorder(), Recorder()
    w.percept = world_pc
    run_episode(ComposedAgent(Script(), OracleCritic(), FullMemory()), w, percept=run_pc)
    assert (run_pc.calls, world_pc.calls) == (1, 0)                          # then the run's
    run_episode(ComposedAgent(Script(), OracleCritic(), FullMemory()), w)
    assert world_pc.calls == 1                                               # then the world's
    w2 = world_with([[0, 20]])
    agent = ComposedAgent(Script(), OracleCritic(), FullMemory())
    run_episode(agent, w2)
    assert agent.memory.known[0]                                             # the default cone (107.5 deg, far) sees it


def test_run_n_passes_the_run_percept_to_every_world():
    worlds = [world_with([[0, 20]]), world_with([[0, 30]])]
    rec = Recorder()
    run_n(lambda: ComposedAgent(Script(), OracleCritic(), FullMemory()), worlds=worlds, percept=rec)
    assert rec.calls == 2


def test_oracle_agents_are_unaffected_by_the_sensor():
    from agents import GreedyAgent, NearestAgent
    rng = np.random.default_rng(3)
    w = world_with(rng.uniform(-80, 80, (12, 2)), rewards=rng.integers(0, 6, (12, 4)).tolist(), duration=40.0)
    w.value = np.array([np.mean(r) for r in w.fruit_reward])
    for make in (lambda: NearestAgent(whole_map=True), lambda: GreedyAgent(15, "rate", whole_map=True)):
        runs = [run_episode(make(), w, percept=p) for p in (None, NullPercept(), ConePercept(20.0, 30.0), ConePercept(360.0, 1e4))]
        assert all(r.trace == runs[0].trace and r.total == runs[0].total for r in runs)


# --- engine actions ----------------------------------------------------------------------------------------

def percept_agent(actions, percept, memory=None):
    return ComposedAgent(Script(*actions), OracleCritic(), memory or FullMemory(), percept)


@pytest.mark.motor_costs
def test_look_costs_time_turns_the_view_and_reveals():
    w = world_with([[40, 0]], speed=5.0)
    agent = percept_agent([Look(90.0)], ConePercept(60.0, 100.0))
    r = run_episode(agent, w)
    turn = costs.TURN_OVERHEAD + 90.0 / costs.TURN_RATE
    assert r.look_time == pytest.approx(turn) and r.idle_time == pytest.approx(w.session_duration - turn)
    assert agent.memory.known[0]                               # facing +x now, the bush is in the cone
    agent2 = percept_agent([], ConePercept(60.0, 100.0))
    run_episode(agent2, w)
    assert not agent2.memory.known[0]                          # heading 0: the bush is off to the side


def test_explore_walks_a_bearing_observing_along_the_way():
    w = world_with([[60, 0]], speed=5.0)
    agent = percept_agent([Explore(90.0, 20.0)], ConePercept(60.0, 45.0))
    r = run_episode(agent, w)
    assert r.walk_time == pytest.approx(4.0) and r.idle_time == pytest.approx(w.session_duration - 4.0)
    assert agent.memory.known[0]                               # facing +x, within 45 of its edge once x >= 15
    short = percept_agent([Explore(90.0, 10.0)], ConePercept(60.0, 45.0))
    run_episode(short, w)
    assert not short.memory.known[0]                           # 49 from the edge at the end of a 10-unit walk


def test_explore_stops_at_the_clock():
    w = world_with([[500, 500]], speed=5.0, duration=3.0)
    r = run_episode(percept_agent([Explore(90.0, 100.0)], NullPercept()), w)
    assert r.walk_time == pytest.approx(3.0) and r.idle_time == 0.0


@pytest.mark.motor_costs
def test_explore_stops_at_unwalkable_ground():
    w = world_with([[500, 500]], speed=5.0)
    # mountains beyond x = 50 and a map edge at 100: exploring east from the origin stops at the foot of the mountains
    w = world_with([[500, 500]], speed=5.0)
    w.params.world_half_extent, w.params.mountain_block_threshold = 100.0, 0.5
    w._terrain = SimpleNamespace(mountain_ramp=lambda x, z: 1.0 if x > 50.0 else 0.0)
    r = run_episode(percept_agent([Explore(90.0, 100.0), Explore(90.0, 10.0)], NullPercept()), w)
    assert 48.0 <= r.walk_time * 5.0 <= 50.5                     # reached about x = 50 and no further
    w._terrain = SimpleNamespace(mountain_ramp=lambda x, z: 0.0)
    r = run_episode(percept_agent([Explore(90.0, 300.0)], NullPercept()), w)
    assert 98.0 <= r.walk_time * 5.0 <= 99.5                      # the map edge (half extent - 1)


def test_a_null_percept_learns_nothing_new_by_walking():
    w = world_with([[60, 0]])
    agent = percept_agent([Explore(90.0, 40.0)], NullPercept())
    run_episode(agent, w)
    assert not agent.memory.known.any()


class SpyCone(ConePercept):
    """A view cone that records where and facing which way it was used: (position, heading) per observation."""
    def __init__(self, fov=60.0, distance=100.0):
        super().__init__(fov, distance)
        self.calls = []

    def observe(self, world, pos, heading, depleted):
        self.calls.append((np.array(pos, dtype=float), float(heading)))
        return super().observe(world, pos, heading, depleted)


def spied_harvest(bush_xy):
    """Harvest bush 0 (the only one) with an agent that never needs the sensor (FullKnowledge); returns (result, spy)."""
    spy = SpyCone()
    agent = ComposedAgent(Script(Harvest(0)), OracleCritic(), FullKnowledge(), spy)
    return run_episode(agent, world_with([bush_xy], speed=5.0)), spy


def test_harvest_range_is_walked_to_and_heading_faces_the_bush():
    r, spy = spied_harvest([48, 0])
    assert r.n_fruits == 2
    headings = [h for _, h in spy.calls]
    assert headings[0] == 0.0 and all(h == pytest.approx(90.0) for h in headings[1:])    # turned east, then walked east
    assert spy.calls[-1][0][0] == pytest.approx(40.0)                                    # to the edge of its range (8 away)


def test_the_view_is_observed_along_a_harvest_walk_every_few_units():
    _, spy = spied_harvest([0, 60])
    z = [p[1] for p, _ in spy.calls]
    assert z[:3] == [0.0, 0.0, 5.0] and z[-1] == pytest.approx(52.0) and len(z) == 13   # start, after the turn, then every 5 units


def test_an_in_range_harvest_turns_the_view_toward_the_bush_only_to_the_edge_of_the_cone():
    edge = 90.0 - np.degrees(np.arcsin(1.0 / 6.0)) - 35.0                                  # canopy radius 1, 6 away, cone 35
    for side in (1, -1):
        r, spy = spied_harvest([6 * side, 0])
        assert [h for _, h in spy.calls] == [0.0, pytest.approx(side * edge)]


@pytest.mark.motor_costs
def test_turning_before_a_walk_is_observed_at_the_new_heading_like_a_look():
    w = world_with([[-1, -3]], speed=5.0)
    for action in (Explore(180.0, 6.0), Look(180.0)):
        agent = percept_agent([action], ConePercept(60.0, 100.0))
        run_episode(agent, w)
        assert agent.memory.known[0], action                   # the bush behind is in view as soon as the view turns


def test_the_tasks_reach_is_the_engines_reach():
    w = world_with([[10, 0], [0, 20]], speed=5.0)
    w.canopy_radius = np.array([1.0, 3.0])
    w.params.harvest_range_gap_per_radius = 0.5               # the toy worlds' default of 0 would hide this term
    assert np.allclose(Task(w).reach(w.canopy_radius), w.reach)


# --- critic ------------------------------------------------------------------------------------------------

def test_the_critic_is_fed_per_fruit_and_stops_when_frozen():
    w = world_with([[5, 0]], rewards=[[2, 4, 6, 8]])
    critic = MeanCritic()
    agent = ComposedAgent(UtilityActor("value"), critic, FullKnowledge())
    run_episode(agent, w)
    assert critic.seen == [0, 1, 2, 3, 4]                       # refit after every fruit, from memory
    assert critic.mean == pytest.approx(5.0)
    critic2 = MeanCritic()
    agent2 = ComposedAgent(UtilityActor("value"), critic2, FullKnowledge())
    agent2.begin_session(w, np.random.default_rng(0))
    critic2.freeze()
    agent2.record_reward(0, 9.0)
    assert critic2.seen == [0] and critic2.version == 1          # nothing more learned after the freeze


def test_memory_limits_what_the_critic_can_learn_from():
    class Amnesic(FullKnowledge):
        def record_reward(self, bush, reward):
            self.taken[bush] += 1                                # the fruit is taken but its reward is not kept

    w = world_with([[5, 0]], rewards=[[2, 4, 6, 8]])
    critic = MeanCritic()
    run_episode(ComposedAgent(UtilityActor("value"), critic, Amnesic()), w)
    assert max(critic.seen) == 0


def test_value_utilities_come_from_the_critic_not_the_world():
    w = world_with([[20, 0], [0, 20]], rewards=[[9, 9], [1, 1]])        # the world says bush 0 is best
    w.value = np.array([9.0, 1.0])
    liar = ComposedAgent(UtilityActor("value", 100), TableCritic([1.0, 9.0]), FullKnowledge())
    assert run_episode(liar, w).trace[0][0] == 1                         # the critic says bush 1: the actor follows the critic
    honest = oracle_agent(UtilityActor("value", 100))
    assert run_episode(honest, w).trace[0][0] == 0


def test_rate_utility_is_value_over_walk_plus_harvest_time():
    w = world_with([[20, 0]], rewards=[[3, 3, 3, 3]], speed=5.0, fd=0.5)
    agent = ComposedAgent(UtilityActor("rate"), TableCritic([3.0]), FullKnowledge())
    agent.begin_session(w, np.random.default_rng(0))
    view = agent.view(State(w).body())
    walk = (20 - 8.0) / 5.0
    assert utility_rate(view)[0] == pytest.approx(3.0 * 4 / (walk + 4 * 0.5))


# --- choice rules ------------------------------------------------------------------------------------------

def test_argmax_and_softmax_probabilities():
    rng = np.random.default_rng(0)
    u = np.array([1.0, 3.0, 3.0, -np.inf])
    assert Argmax().pick(u, rng) == 1                                    # first of the ties
    assert np.allclose(Argmax().probs(u), [0, 1, 0, 0])
    assert np.allclose(Argmax().probs(u, random_ties=True), [0, 0.5, 0.5, 0])
    assert Argmax().pick(np.array([-np.inf, -np.inf]), rng) is None
    sm = Softmax(1.0)
    p = sm.probs(u)
    assert p.sum() == pytest.approx(1.0) and p[3] == 0 and p[1] == pytest.approx(p[2]) and p[0] < p[1]
    assert p[1] / p[0] == pytest.approx(np.exp(2.0))
    assert Softmax(0.01).probs(np.array([1.0, 2.0]))[1] > 0.999
    assert Softmax(100.0).probs(np.array([1.0, 2.0]))[1] == pytest.approx(0.5, abs=0.01)
    with pytest.raises(ValueError):
        Softmax(0.0)
    picks = [sm.pick(np.array([0.0, np.log(3.0)]), rng) for _ in range(4000)]
    assert abs(np.mean(picks) - 0.75) < 0.03


def test_a_softmax_actor_is_reproducible_per_rng_and_varies_across_rngs():
    w = world_with([[20, 0], [0, 20], [-20, 0], [0, -20]], rewards=[[1, 1]] * 4)

    def trace(seed):
        agent = ComposedAgent(UtilityActor("nearest", choice=Softmax(1000.0)), OracleCritic(), FullKnowledge())
        return [t[0] for t in run_episode(agent, w, np.random.default_rng(seed)).trace]
    assert trace(1) == trace(1)
    assert len({tuple(trace(s)) for s in range(12)}) > 1                  # near-uniform choice: different orders


# --- planner -----------------------------------------------------------------------------------------------

def test_the_oracle_planner_plans_once_and_replans_only_when_the_map_changes():
    w = world_with([[20, 0], [0, 40], [-40, 0]], rewards=[[2, 2], [3, 3], [4, 4]])
    w.value = np.array([2.0, 3.0, 4.0])
    agent = ComposedAgent(PlannerActor("exact"), OracleCritic(), FullKnowledge())
    run_episode(agent, w)
    nodes_after_session = agent.nodes
    assert agent.exact and nodes_after_session > 0
    # act again at the same versions: no new plan
    agent2 = ComposedAgent(PlannerActor("exact"), OracleCritic(), FullKnowledge())
    agent2.begin_session(w, np.random.default_rng(0))
    state = State(w)
    agent2.act(state.body())
    n1 = agent2.nodes
    agent2.act(state.body())
    assert agent2.nodes == n1
    # a limited-memory planner replans when it learns a new bush, starting from where it is
    mem = FullMemory()
    agent3 = ComposedAgent(PlannerActor("exact"), OracleCritic(), mem)
    agent3.begin_session(w, np.random.default_rng(0))
    attrs = np.zeros((1, 3))
    agent3.observe(Observation(np.array([0]), w.pos[[0]], w.canopy_radius[[0]], attrs, np.zeros(1, dtype=bool)))
    first = agent3.act(state.body())
    assert first == Harvest(0) and agent3.plan == [0]
    agent3.observe(Observation(np.array([2]), w.pos[[2]], w.canopy_radius[[2]], attrs, np.zeros(1, dtype=bool)))
    state.pos = np.array([12.0, 0.0])
    agent3.act(state.body())
    assert set(agent3.plan) == {0, 2} or set(agent3.plan) == {2}         # the new bush is now in the plan


# --- Interlude evaluation ----------------------------------------------------------------------------------

def toy_interlude():
    """Three trials over six bushes; the critic below scores a bush by its color attribute."""
    colors = [0.9, 0.1, 0.2, 0.8, 0.5, 0.5]
    pos = [[10, 30], [-10, 30]] * 3
    trials = [
        {"type": "contrast", "correct": "left", "left": {"id": 0}, "right": {"id": 1}, "start": [0.0, 0.0], "yaw": 0.0},
        {"type": "contrast", "correct": "right", "left": {"id": 2}, "right": {"id": 3}, "start": [0.0, 0.0], "yaw": 0.0},
        {"type": "graded", "correct": "either", "left": {"id": 4}, "right": {"id": 5}, "start": [0.0, 0.0], "yaw": 0.0},
    ]
    return {"seed": 7, "fruitCount": 2, "treePos": np.array(pos, dtype=float).reshape(-1).tolist(), "canopyRadius": [1.0] * 6,
            "shape": [0.0] * 6, "color": colors, "moisture": [0.0] * 6, "trials": trials}


class ColorCritic(Critic):
    def value(self, attrs, ids=None):
        return np.asarray(attrs)[:, 1].copy(), np.zeros(len(attrs))


def session_agent(actor):
    agent = ComposedAgent(actor, ColorCritic(), FullKnowledge())
    agent.begin_session(world_with([[20, 0]]), np.random.default_rng(0))
    return agent


def test_interlude_scoring_with_a_value_based_actor():
    agent = session_agent(UtilityActor("value"))
    score = evaluate_interlude(agent, toy_interlude(), bonus_per_correct=5.0, n_samples=50)
    assert agent.critic.frozen
    assert score.accuracy == 1.0 and score.by_type == {"contrast": 1.0, "graded": 1.0} and score.n_trials == 3
    assert score.p_left == [1.0, 0.0, pytest.approx(score.p_left[2])] and score.bonus == pytest.approx(15.0)
    practice = evaluate_interlude(session_agent(UtilityActor("value")), toy_interlude(), practice=True, n_samples=10)
    assert practice.bonus == 0.0


def test_interlude_scoring_chance_and_a_softmax_actor_is_greedy_there():
    nearest = evaluate_interlude(session_agent(UtilityActor("nearest")), toy_interlude(), n_samples=2000)
    assert abs(nearest.by_type["contrast"] - 0.5) < 0.05                  # equal distances, random ties: chance
    for temperature in (100.0, 0.02):                                     # the Interlude is greedy whatever the actor's choice rule (PI decision)
        soft = evaluate_interlude(session_agent(UtilityActor("value", choice=Softmax(temperature))), toy_interlude(), n_samples=200)
        assert soft.by_type["contrast"] == 1.0


@pytest.mark.slow
def test_a_real_interlude_is_solved_by_the_oracle_and_not_by_nearest():
    sidecar, params, terrain = generate_interlude("S3_Interlude", pool_samples=120_000, seed=3)
    from sim import get_worlds
    w = get_worlds("S3", [3])[0]
    oracle = oracle_agent(UtilityActor("value"))
    oracle.begin_session(w, np.random.default_rng(0))
    best = evaluate_interlude(oracle, sidecar, n_samples=20)
    assert best.accuracy == 1.0
    blind = oracle_agent(UtilityActor("nearest"))
    blind.begin_session(w, np.random.default_rng(0))
    chance = evaluate_interlude(blind, sidecar, n_samples=400)
    assert 0.3 < chance.accuracy < 0.8


@pytest.mark.slow
def test_seeded_generation_matches_the_assets_own_seed_and_applies_overrides():
    a, _, _ = generate_interlude("S3_Interlude", pool_samples=60_000)
    b, _, _ = generate_interlude("S3_Interlude", pool_samples=60_000, seed=3)
    assert a == b                                                         # S3's own seed is 3
    c, _, _ = generate_interlude("S3_Interlude", pool_samples=60_000, seed=4)
    assert c["seed"] == 4 and c["treePos"] != a["treePos"]


# --- boundaries: what an agent may know ----------------------------------------------------------------------

def test_state_body_is_a_snapshot_of_what_an_actor_may_read():
    w = world_with([[20, 0]])
    s = State(w)
    s.total = 7.0
    b = s.body()
    assert isinstance(b, Body) and b.total == 7.0 and b.time_left == w.session_duration and b.heading == 0.0
    b.pos[0] = 99.0
    assert s.pos[0] == 0.0                                              # a copy: the actor cannot move the agent
    assert not hasattr(b, "world") and not hasattr(b, "depleted")


class GrantRecorder:
    """Mixin for a spy component: records what begin() and grant() were given."""
    def begin(self, task):
        self.begun_with = task
        super().begin(task)

    def grant(self, knowledge):
        self.granted = knowledge


class SpyMemory(GrantRecorder, FullMemory):
    pass


class OmniscientSpyMemory(SpyMemory):
    omniscient = True


class SpyCritic(GrantRecorder, MeanCritic):
    pass


def test_only_omniscient_components_are_granted_the_worlds_knowledge():
    w = world_with([[20, 0], [0, 20]])
    plain = ComposedAgent(UtilityActor("value"), SpyCritic(), SpyMemory())
    plain.begin_session(w, np.random.default_rng(0))
    assert not hasattr(plain.memory, "granted") and not hasattr(plain.critic, "granted")
    flagged = ComposedAgent(UtilityActor("value"), OracleCritic(), OmniscientSpyMemory())
    flagged.begin_session(w, np.random.default_rng(0))
    assert isinstance(flagged.memory.granted, WorldKnowledge) and flagged.memory.granted.n == 2
    assert flagged.critic.values is not None


def test_components_begin_with_a_task_and_the_agent_keeps_no_world():
    w = world_with([[20, 0], [0, 20]])
    agent = ComposedAgent(UtilityActor("value"), SpyCritic(), SpyMemory())
    agent.begin_session(w, np.random.default_rng(0))
    task = agent.memory.begun_with
    assert isinstance(task, Task) and task.n_bushes == 2 and not hasattr(task, "pos")
    assert not hasattr(agent, "world") and agent.task is agent.memory.begun_with


# --- the Interlude through the agent --------------------------------------------------------------------------

def test_interlude_shows_both_bushes_to_every_agent_whatever_its_sensor():
    for percept in (NullPercept(), ConePercept(5.0, 1.0)):
        agent = ComposedAgent(UtilityActor("value"), ColorCritic(), FullMemory(), percept)
        agent.begin_session(world_with([[20, 0]]), np.random.default_rng(0))
        score = evaluate_interlude(agent, toy_interlude(), n_samples=20)
        assert score.accuracy == 1.0                                       # blind to the session, still sees the pair


def test_interlude_starts_a_fresh_memory_and_leaves_the_sessions_alone():
    w = world_with([[20, 0]], attrs=[[0.0, 0.1, 0.0]])                    # session bush 0 has color 0.1
    agent = ComposedAgent(UtilityActor("value"), ColorCritic(), FullMemory())
    agent.begin_session(w, np.random.default_rng(0))
    agent.observe(Observation(np.array([0]), w.pos, w.canopy_radius, np.array([[0.0, 0.1, 0.0]]), np.zeros(1, dtype=bool)))
    session_memory = agent.memory
    score = evaluate_interlude(agent, toy_interlude(), n_samples=20)      # Interlude bush 0 has color 0.9 (same id)
    assert score.accuracy == 1.0
    assert agent.memory is session_memory and agent.memory.attrs[0, 1] == 0.1 and agent.memory.n == 1
    assert agent.interlude_memory is not agent.memory and agent.interlude_memory.n == 6
    assert agent.interlude_memory.attrs[0, 1] == 0.9 and agent.active_memory is agent.interlude_memory


def test_interlude_freezes_and_carries_over_the_critic():
    w = world_with([[5, 0]], rewards=[[2, 4]])
    critic = MeanCritic()
    agent = ComposedAgent(UtilityActor("value"), critic, FullKnowledge())
    run_episode(agent, w)
    seen, version, mean = list(critic.seen), critic.version, critic.mean
    evaluate_interlude(agent, toy_interlude(), n_samples=10)
    assert critic.frozen and critic.seen == seen and critic.version == version and critic.mean == mean   # carried, not refit


def test_an_oracle_is_granted_the_interludes_table_not_the_sessions():
    w = world_with([[20, 0]], rewards=[[9, 9]])                           # the session's only bush is worth 9
    sidecar = toy_interlude()
    sidecar["value"] = list(sidecar["color"])                             # the Interlude's true values: its colors
    agent = oracle_agent(UtilityActor("value"))
    agent.begin_session(w, np.random.default_rng(0))
    score = evaluate_interlude(agent, sidecar, n_samples=20)
    assert score.accuracy == 1.0 and agent.critic.values[0] == pytest.approx(0.9)


# --- gaps found by mutation testing ----------------------------------------------------------------------------

class ResettingCritic(Critic):
    """A critic that (re)initialises what it learns in `begin`, as Memory does: weights for color only."""
    def begin(self, task):
        self.w = 0.0

    def _fit(self, memory):
        attrs, rewards, ids = memory.experiences()
        self.w = float(rewards.mean() / max(attrs[:, 1].mean(), 1e-9)) if len(rewards) else 0.0

    def value(self, attrs, ids=None):
        return self.w * np.asarray(attrs)[:, 1], np.zeros(len(attrs))


def test_a_critic_that_resets_in_begin_keeps_what_it_learned_through_the_interlude():
    w = world_with([[5, 0]], rewards=[[4, 4]], attrs=[[0.0, 0.5, 0.0]])
    critic = ResettingCritic()
    agent = ComposedAgent(UtilityActor("value"), critic, FullKnowledge())
    run_episode(agent, w)
    learned = critic.w
    assert learned > 0
    score = evaluate_interlude(agent, toy_interlude(), n_samples=10)
    assert critic.w == learned and score.accuracy == 1.0       # w == 0 would tie every trial: chance, not 1.0


def reachable(root, skip=()):
    """Every object reachable from `root` through attributes, dict values and sequence items (numpy arrays are leaves)."""
    seen, stack = set(), [root]
    while stack:
        o = stack.pop()
        if id(o) in seen or isinstance(o, (str, bytes, int, float, bool, type(None), np.random.Generator)):
            continue
        seen.add(id(o))
        yield o
        if isinstance(o, np.ndarray):
            continue
        if isinstance(o, dict):
            stack.extend(o.values())
        elif isinstance(o, (list, tuple, set)):
            stack.extend(o)
        elif hasattr(o, "__dict__") and not isinstance(o, type):
            stack.extend(vars(o).values())


def test_nothing_a_non_omniscient_agent_holds_reaches_the_world():
    from world import World
    w = world_with([[10, 0], [0, 20]], rewards=[[3, 3], [5, 5]], attrs=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    for actor in (UtilityActor("value"), PlannerActor()):
        agent = ComposedAgent(actor, MeanCritic(), FullMemory())
        agent.begin_session(w, np.random.default_rng(0))
        held = list(reachable(agent))
        assert not any(isinstance(o, (World, State)) for o in held), "the agent holds the world"
        secrets = [w.value, w.fruit_reward, w.canopy_radius, w.shape, w.color, w.moisture]
        for o in held:
            if isinstance(o, np.ndarray):
                assert not any(np.shares_memory(o, s) for s in secrets), "the agent holds an array of the world's data"
    # an omniscient memory is the granted exception: it holds a *copy* of the map, still not the world's own arrays
    agent = ComposedAgent(UtilityActor("value"), MeanCritic(), FullKnowledge())
    agent.begin_session(w, np.random.default_rng(0))
    assert not any(isinstance(o, World) for o in reachable(agent))
    assert not any(isinstance(o, np.ndarray) and np.shares_memory(o, w.pos) for o in reachable(agent))


def test_a_cone_sees_a_canopy_whose_edge_is_inside_it_even_if_its_center_is_not():
    # 10 away, radius 3: angular radius 17.5 degrees; a 60-degree cone reaches 30 + 17.5 to the bush's center bearing.
    cone = ConePercept(angle=60.0, distance=100.0)
    for bearing, expected in ((40.0, True), (46.0, True), (49.0, False), (-46.0, True), (-49.0, False)):
        a = np.radians(bearing)
        w = world_with([[10 * np.sin(a), 10 * np.cos(a)]], radius=3.0)
        assert bool(len(cone.observe(w, np.zeros(2), 0.0, np.zeros(1, dtype=bool)).ids)) is expected, bearing


def test_observations_report_which_bushes_look_spent():
    w = world_with([[0, 20], [0, 30], [0, 40]])
    obs = ConePercept(90.0, 100.0).observe(w, np.zeros(2), 0.0, np.array([False, True, False]))
    assert list(obs.ids) == [0, 1, 2] and list(obs.depleted) == [False, True, False]


def test_argmax_tie_window_is_tiny():
    rng = np.random.default_rng(0)
    assert all(Argmax().pick(np.array([1.0, 1.1]), rng, random_ties=True) == 1 for _ in range(50))
    assert np.allclose(Argmax().probs(np.array([1.0, 1.1]), random_ties=True), [0, 1])
    assert {Argmax().pick(np.array([1.0, 1.0 + 1e-14]), rng, random_ties=True) for _ in range(100)} == {0, 1}


class ChoiceSpy(Actor):
    def __init__(self):
        self.bodies = []

    def choose_between(self, view, candidates, rng):
        self.bodies.append(view.body)
        return 0


def test_the_interlude_shows_the_actor_a_fresh_body_at_the_trials_spawn():
    spy = ChoiceSpy()
    agent = ComposedAgent(spy, ColorCritic(), FullMemory())
    w = world_with([[20, 0]])
    agent.begin_session(w, np.random.default_rng(0))
    sidecar = toy_interlude()
    sidecar["trials"][1]["start"], sidecar["trials"][1]["yaw"] = [3.0, 4.0], 30.0
    evaluate_interlude(agent, sidecar, n_samples=1)
    b = spy.bodies[1]
    assert b.total == 0.0 and b.time_left == w.session_duration and b.heading == 30.0 and list(b.pos) == [3.0, 4.0]


def test_accuracy_averages_over_trials_not_over_trial_types():
    sidecar = toy_interlude()                   # two contrast trials (right) + one graded trial; make the graded one wrong
    sidecar["trials"][2]["correct"] = "right"   # ColorCritic picks left for colors 0.5 vs 0.5 at random: 0.5
    sidecar["color"][4], sidecar["color"][5] = 0.9, 0.1       # now it picks left every time, which is wrong
    score = evaluate_interlude(session_agent(UtilityActor("value")), sidecar, n_samples=20)
    assert score.by_type == {"contrast": 1.0, "graded": 0.0}
    assert score.accuracy == pytest.approx(2 / 3)           # 2 of 3 trials, not the mean of the two types (0.5)
    assert score.bonus == pytest.approx(2 / 3 * 3 * 5.0)


def test_interlude_picks_depend_on_the_sidecars_seed_and_are_reproducible():
    def p_left(seed, rng=None):
        sidecar = toy_interlude()
        sidecar["seed"] = seed
        agent = session_agent(UtilityActor("value", choice=Softmax(0.5)))
        return evaluate_interlude(agent, sidecar, n_samples=30, rng=rng).p_left
    assert p_left(7) == p_left(7)
    assert p_left(7) != p_left(8)
    assert p_left(7, np.random.default_rng(1)) == p_left(8, np.random.default_rng(1))      # an explicit rng overrides the seed


def test_the_critic_is_never_updated_during_an_interlude():
    class Counting(ColorCritic):
        updates = 0

        def update(self, memory):
            Counting.updates += 1
            super().update(memory)
    agent = ComposedAgent(UtilityActor("value"), Counting(), FullKnowledge())
    agent.begin_session(world_with([[20, 0]]), np.random.default_rng(0))
    before = Counting.updates
    evaluate_interlude(agent, toy_interlude(), n_samples=5)
    assert Counting.updates == before and agent.critic.frozen


@pytest.mark.slow
def test_interlude_overrides_reach_the_cache():
    from sim import get_interlude
    a = get_interlude("S3", 3, pool_samples=60_000, interlude_trial_count=3)[0]
    b = get_interlude("S3", 3, pool_samples=60_000)[0]
    assert a["n"] == 3 and b["n"] == int(load_session("S3_Interlude").interlude_trial_count) != 3


# --- the planner and the actors under the motor costs; ids in the Interlude; the critic version --------------------

import itertools


class IdSpy(Critic):
    """Records the ids it is asked about (a per-id critic would key on them)."""
    def __init__(self):
        self.asked = []

    def value(self, attrs, ids=None):
        self.asked.append(None if ids is None else np.array(ids))
        return np.asarray(attrs)[:, 1].copy(), np.zeros(len(attrs))


def test_only_an_omniscient_critic_is_given_bush_ids_in_the_interlude():
    spy = IdSpy()
    agent = ComposedAgent(UtilityActor("value"), spy, FullKnowledge())
    agent.begin_session(world_with([[20, 0]]), np.random.default_rng(0))
    agent.act(Body(np.zeros(2), 0.0, 60.0, 0.0))
    assert spy.asked[-1] is not None                                   # in the session ids identify the bushes
    spy.asked.clear()
    evaluate_interlude(agent, toy_interlude(), n_samples=3)
    assert spy.asked and all(a is None for a in spy.asked)             # in the Interlude they are another table's
    oracle = oracle_agent(UtilityActor("value"))
    oracle.begin_session(world_with([[20, 0]]), np.random.default_rng(0))
    assert evaluate_interlude(oracle, dict(toy_interlude(), value=list(toy_interlude()["color"])), n_samples=5).accuracy == 1.0


def test_a_learning_critics_version_is_bumped_by_update_not_by_the_critic():
    class Learner(Critic):
        def _fit(self, memory):
            self.n = len(memory.experiences()[1])           # (no version bookkeeping of its own)

        def value(self, attrs, ids=None):
            return np.zeros(len(attrs)), np.zeros(len(attrs))
    w = world_with([[5, 0]], rewards=[[2, 4, 6]])
    critic = Learner()
    run_episode(ComposedAgent(UtilityActor("value"), critic, FullKnowledge()), w)
    assert critic.version == 4 and critic.n == 3                        # the initial fit + one per fruit
    assert OracleCritic().version == 0
    oracle = oracle_agent(UtilityActor("value"))
    run_episode(oracle, w)
    assert oracle.critic.version == 0                                   # a critic that learns nothing never forces a re-plan


def test_a_softmax_actor_that_finds_nothing_in_range_still_goes_through_its_choice_rule():
    w = world_with([[20, 0], [0, 20], [-20, 0], [0, -20]], rewards=[[1, 1]] * 4)
    picks = set()
    for seed in range(40):
        agent = ComposedAgent(UtilityActor("value", max_walk_time=0.0, choice=Softmax(1e6)), OracleCritic(), FullKnowledge())
        agent.begin_session(w, np.random.default_rng(seed))
        picks.add(agent.act(Body(np.zeros(2), 0.0, 60.0, 0.0)).bush)
    assert len(picks) > 1                                               # not always the nearest


class _Table(Critic):
    def __init__(self, values):
        self.values = np.asarray(values, dtype=float)

    def value(self, attrs, ids=None):
        return self.values[np.asarray(ids)], np.zeros(len(ids))


def _best_by_engine(world, critic_values):
    """The best total over every ordered visiting list, by running the engine (whole bushes, rewards = clipped values)."""
    from test_sim import Fixed
    best = 0.0
    for r in range(1, len(critic_values) + 1):
        for order in itertools.permutations(range(len(critic_values)), r):
            best = max(best, run_episode(Fixed(list(order)), world).total)
    return best


@pytest.mark.motor_costs
@pytest.mark.slow
def test_the_planner_is_optimal_with_negative_critic_values_and_with_the_motor_costs():
    rng = np.random.default_rng(3)
    for trial in range(8):
        n = 5
        values = np.round(rng.uniform(-4, 4, n), 1)
        pos = rng.uniform(-40, 40, (n, 2))
        w = world_with(pos, rewards=[[max(0, int(round(v)))] * 6 for v in values], duration=float(rng.uniform(8, 30)))
        agent = ComposedAgent(PlannerActor("exact", incumbent_width=1), _Table(values), FullKnowledge())
        r = run_episode(agent, w)
        # the plan's objective uses the critic's (positive) values; the engine pays the integer rewards: compare to the best route
        assert agent.exact
        assert r.total == pytest.approx(_best_by_engine(w, values)), (trial, values)


@pytest.mark.motor_costs
def test_the_plans_value_is_what_the_engine_pays_when_rewards_equal_the_values():
    rng = np.random.default_rng(5)
    for trial in range(20):         # heading-tracking mistakes in the plan first show at trial 16
        n = 6
        values = rng.integers(1, 6, n)
        w = world_with(rng.uniform(-50, 50, (n, 2)), rewards=[[int(v)] * 8 for v in values], duration=float(rng.uniform(5, 40)))
        agent = oracle_agent(PlannerActor("exact"))
        r = run_episode(agent, w)
        assert agent.plan_value == pytest.approx(r.total), trial


@pytest.mark.motor_costs
def test_the_plan_starts_from_the_heading_the_agent_has():
    w = world_with([[48, 0]], rewards=[[3, 3]], speed=5.0, duration=9.2)       # one fruit fits only if no 90 degree turn is needed
    for heading, expected in ((90.0, 3.0), (0.0, 0.0)):
        agent = oracle_agent(PlannerActor("exact"))
        agent.begin_session(w, np.random.default_rng(0))
        agent.act(Body(np.zeros(2), heading, 9.2, 0.0))
        assert agent.plan_value == pytest.approx(expected), heading


@pytest.mark.motor_costs
def test_travel_times_include_the_turn_and_the_presses_the_engine_charges():
    w = world_with([[0, 48], [48, 0]], speed=5.0)
    agent = oracle_agent(UtilityActor("nearest"))
    agent.begin_session(w, np.random.default_rng(0))
    t = agent.view(Body(np.zeros(2), 0.0, 60.0, 0.0)).travel_times()
    ahead = costs.WALK_PRESS_TIME + costs.HARVEST_PRESS_TIME + 8.0
    assert t[0] == pytest.approx(ahead) and t[1] == pytest.approx(ahead + costs.TURN_OVERHEAD + 90.0 / costs.TURN_RATE)
    assert agent.act(Body(np.zeros(2), 0.0, 60.0, 0.0)).bush == 0         # straight ahead is quicker than to the side


# --- shared data an agent could otherwise corrupt ------------------------------------------------------------------

def test_a_grant_is_a_read_only_copy_of_the_world():
    w = world_with([[10, 0], [0, 20]], rewards=[[3, 3], [5, 5]], attrs=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    k = WorldKnowledge.from_world(w)
    for name in ("pos", "radius", "attrs", "values"):
        arr = getattr(k, name)
        assert not np.shares_memory(arr, getattr(w, {"values": "value", "attrs": "color", "radius": "canopy_radius"}.get(name, name)))
        assert not arr.flags.writeable
        with pytest.raises(ValueError):
            arr[0] = 99.0
    before = w.value.copy()
    agent = oracle_agent(UtilityActor("value"))
    agent.begin_session(w, np.random.default_rng(0))
    with pytest.raises(ValueError):
        agent.critic.values[0] = 99.0                      # an omniscient critic cannot edit what it was granted
    assert np.array_equal(w.value, before)
    sidecar = toy_interlude()
    sidecar["value"] = list(sidecar["color"])
    assert not WorldKnowledge.from_sidecar(sidecar).values.flags.writeable


def test_get_interlude_hands_out_copies_and_accepts_list_overrides():
    from sim import get_interlude
    a = get_interlude("P", 100, pool_samples=40_000)[0]
    original = a["trials"][0]["correct"]
    a["trials"][0]["correct"] = "poisoned"
    a["treePos"][0] = -999.0
    b = get_interlude("P", 100, pool_samples=40_000)[0]
    assert b["trials"][0]["correct"] == original and b["treePos"][0] != -999.0     # the cache was not edited through `a`
    c = get_interlude("P", 100, pool_samples=40_000, canopy_width_range=[2.0, 5.0])[0]   # unhashable list: no TypeError
    assert c["n"] == b["n"]


# --- the delta-rule learner ------------------------------------------------------------------------------------

def learner_memory(attr_rows, reward_lists):
    """A FullMemory that has seen these bushes and taken these fruits from them."""
    n = len(attr_rows)
    m = FullMemory()
    m.begin(SimpleNamespace(n_bushes=n, fruit_count=10))
    m.known[:] = True
    m.attrs[:] = attr_rows
    for j, rewards in enumerate(reward_lists):
        for r in rewards:
            m.record_reward(j, r)
    return m


def test_bush_stats_summarize_the_fruit_lists():
    m = learner_memory([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]], [[2, 4], [], [5]])
    ids, attrs, n, mean, var = m.bush_stats()
    assert list(ids) == [0, 2] and list(n) == [2, 1]
    assert list(mean) == [3.0, 5.0] and list(var) == [2.0, 0.0]
    assert attrs[1].tolist() == [0.7, 0.8, 0.9]


def test_rbf_features_are_unit_length_and_their_kernel_falls_with_distance():
    for f in (RBFFeatures(), RBFFeatures(additive=False, n_centers=5)):
        x = np.array([[0.5, 0.5, 0.5], [0.55, 0.5, 0.5], [0.9, 0.5, 0.5], [0.9, 0.1, 0.9]])
        phi = f(x)
        assert phi.shape[1] == f.dim
        assert np.allclose(np.linalg.norm(phi, axis=1), 1.0)
        k = phi[1:] @ phi[0]
        assert k[0] > k[1] > k[2] > 0


def test_additive_rbf_kernel_changes_less_when_only_one_attribute_differs():
    f = RBFFeatures()
    phi = f(np.array([[0.5, 0.5, 0.5], [0.5, 0.5, 0.95], [0.95, 0.95, 0.95]]))
    assert phi[0] @ phi[1] > phi[0] @ phi[2]


def test_the_neutral_prior_is_positive_then_the_mean_of_the_bush_means():
    prior = NeutralPrior()
    assert prior.value(learner_memory([[0, 0, 0]], [[]])) > 0.0
    assert prior.value(learner_memory([[0, 0, 0], [1, 1, 1]], [[2, 4], [9]])) == pytest.approx(6.0)   # (3 + 9) / 2, not the fruit mean


def fitted(critic, memory):
    critic.begin(SimpleNamespace(n_bushes=memory.n))
    critic.update(memory)
    return critic


def test_with_the_running_mean_prior_the_first_bush_teaches_the_baseline_and_nothing_else():
    m = learner_memory([[0.2, 0.2, 0.2], [0.8, 0.8, 0.8]], [[5, 5, 5], []])
    critic = fitted(DeltaRuleCritic(prior=NeutralPrior()), m)
    mean, sd = critic.value(m.attrs)
    assert np.allclose(mean, 5.0) and np.all(sd == 0.0)


def test_the_default_prior_is_a_small_fixed_baseline_so_the_first_bush_teaches_its_neighbourhood_and_unseen_regions_stay_low():
    m = learner_memory([[0.2, 0.2, 0.2], [0.95, 0.95, 0.95]], [[5, 5, 5], []])
    critic = fitted(DeltaRuleCritic(), m)
    assert critic.spec()["prior"] == {"type": "ConstantPrior", "level": 0.1}
    near, far = critic.value(m.attrs)[0]
    assert near > 1.0 and 0.1 <= far < near                                               # learned about the harvested bush; the unseen one stays lower


def test_the_delta_rule_generalizes_to_unseen_bushes_in_order_and_falls_back_toward_the_baseline_far_away():
    # reward rises with the first attribute; the unseen bushes sit near the poor bush, near the rich one and between them
    rows = [[0.1, 0.5, 0.5], [0.9, 0.5, 0.5], [0.15, 0.5, 0.5], [0.85, 0.5, 0.5], [0.5, 0.5, 0.5]]
    critic = DeltaRuleCritic(RBFFeatures(length_scale=0.15), alpha=0.5)
    fitted(critic, learner_memory(rows, [[1.0] * 4, [9.0] * 4, [], [], []]))
    mean, _ = critic.value(np.array(rows))
    assert mean[0] < mean[1] and mean[2] < mean[4] < mean[3]           # unseen bushes inherit from their neighbours, in order
    assert mean[2] == pytest.approx(mean[0], abs=0.1) and mean[3] == pytest.approx(mean[1], abs=0.1)


def test_a_smaller_learning_rate_learns_less_from_one_bush():
    rows = [[0.1, 0.5, 0.5], [0.9, 0.5, 0.5]]
    gaps = []
    for alpha in (0.2, 1.0):
        critic = fitted(DeltaRuleCritic(alpha=alpha), learner_memory(rows, [[1.0] * 3, [9.0] * 3]))
        v, _ = critic.value(np.array(rows))
        gaps.append(v[1] - v[0])
    assert 0.0 < gaps[0] < gaps[1]


def test_a_bush_is_learned_from_once_per_update_unless_more_fruit_was_taken():
    m = learner_memory([[0.1, 0.5, 0.5], [0.9, 0.5, 0.5]], [[2.0], [8.0]])
    critic = fitted(DeltaRuleCritic(), m)
    w = critic.w.copy()
    critic.update(m)
    assert np.allclose(critic.w, w)                          # nothing new in memory
    m.record_reward(0, 6.0)
    critic.update(m)
    assert not np.allclose(critic.w, w)


def test_a_swapped_prior_sets_the_baseline():
    class Fixed(Prior):
        def value(self, memory):
            return 42.0
    critic = fitted(DeltaRuleCritic(prior=Fixed()), learner_memory([[0.5, 0.5, 0.5]], [[]]))
    assert critic.value(np.array([[0.1, 0.9, 0.3]]))[0][0] == pytest.approx(42.0)


def test_the_engine_updates_a_per_bush_critic_once_per_visit_and_a_per_fruit_critic_per_fruit():
    w = world_with([[5, 0], [-5, 0]], rewards=[[2, 4, 6], [8, 8, 8]], attrs=[[0.2, 0.5, 0.5], [0.8, 0.5, 0.5]])
    bush_critic = DeltaRuleCritic()
    run_episode(ComposedAgent(UtilityActor("value"), bush_critic, FullKnowledge()), w)
    assert bush_critic.version == 1 + 2                       # the session's start, then once per bush
    fruit_critic = MeanCritic()
    run_episode(ComposedAgent(UtilityActor("value"), fruit_critic, FullKnowledge()), w)
    assert fruit_critic.seen == [0, 1, 2, 3, 4, 5, 6]


def test_the_delta_rule_agent_runs_a_session_and_its_critic_is_frozen_for_the_interlude():
    w = world_with([[5, 0], [-5, 0], [0, 6]], rewards=[[2, 4, 6], [8, 8, 8], [1, 1, 1]],
                   attrs=[[0.2, 0.5, 0.5], [0.8, 0.5, 0.5], [0.5, 0.5, 0.5]])
    agent = REGISTRY["delta_rate_10"]()
    res = run_episode(agent, w)
    assert res.total > 0
    v = agent.critic.version
    agent.begin_interlude(WorldKnowledge.from_world(w))
    agent.record_reward(0, 99.0)
    agent.end_visit(0)
    assert agent.critic.version == v


# --- Interlude pairs: travel times that differ by milliseconds are a tie ----------------------------------------------

def pair_view(gap, critic=None):
    """A view at the origin facing +z of two bushes straight ahead whose travel times differ by `gap` seconds (the second is further
    by gap * speed units; speed 5 in the toy world)."""
    w = world_with([[0.0, 40.0], [0.0, 40.0 + 5.0 * gap]])
    memory = begin_memory(FullKnowledge(), w)
    view = View(Body(np.zeros(2), 0.0, 90.0, 0.0), memory, critic or OracleCritic(), Task(w))
    return view, memory


def picks(actor, view, n=400):
    rng = np.random.default_rng(0)
    return np.array([actor.choose_between(view, [0, 1], rng) for _ in range(n)])


def test_equalize_times_averages_the_times_of_candidates_within_the_tolerance_only():
    view, _ = pair_view(0.004)
    t = view.travel_times()
    assert t[1] - t[0] == pytest.approx(0.004)
    close = view.equalize_times([0, 1], 0.01).travel_times()
    assert close[0] == close[1] == pytest.approx(t[:2].mean())
    far, _ = pair_view(0.04)
    assert np.allclose(far.equalize_times([0, 1], 0.01).travel_times(), far.travel_times())      # 40 ms apart: left alone
    assert view.travel_times()[1] == pytest.approx(t[1])                                           # the original view is unchanged


def test_a_nearest_agent_picks_between_a_pair_at_random_when_the_times_differ_by_milliseconds():
    near_tie, _ = pair_view(0.004)
    p = picks(UtilityActor("nearest"), near_tie)
    assert 0.4 < p.mean() < 0.6                                                                    # not always the quicker bush
    clear, _ = pair_view(0.04)
    assert picks(UtilityActor("nearest"), clear).sum() == 0                                        # 40 ms is a real difference: the nearer one


def test_values_still_decide_a_pair_whose_times_are_a_tie():
    for table, expected in (([5.0, 1.0], 0), ([1.0, 5.0], 1)):
        view, _ = pair_view(0.004, TableCritic(table))
        for utility in ("rate", "value"):
            assert set(picks(UtilityActor(utility), view, 50)) == {expected}


@pytest.mark.slow
def test_nearest_is_at_chance_on_a_random_interlude_where_shape_is_rewarded():
    # S4 rewards shape (inverted); the wider canopy of a pair needs a slightly larger turn, which used to make `nearest` pick the
    # narrower one every time (accuracy 0.27 here): a floor agent that knew nothing about shape was using it
    sidecar, bonus, practice = get_interlude("S4", 0, "random", interlude_trial_count=50, session_duration=150)
    agent = REGISTRY["nearest"]()
    run_episode(agent, world_with([[20, 0]]))
    score = evaluate_interlude(agent, sidecar, bonus, practice, n_samples=200)
    assert abs(score.accuracy - 0.5) < 0.05


def test_a_constant_prior_never_moves_and_the_weights_then_carry_the_whole_level():
    rows = [[0.1, 0.5, 0.5], [0.9, 0.5, 0.5]]
    memory = learner_memory(rows, [[4.0] * 4, [6.0] * 4])
    assert ConstantPrior(0.1).value(memory) == 0.1 and ConstantPrior(0.1).value(learner_memory(rows, [[], []])) == 0.1
    assert NeutralPrior().value(memory) == pytest.approx(5.0)                       # the default follows the mean of the bush means
    critic = fitted(DeltaRuleCritic(prior=ConstantPrior(0.1), alpha=1.0), memory)
    assert critic._baseline == 0.1
    mean = critic.value(np.array(rows))[0]
    assert mean.min() > 3.0                                                       # the weights learned the level (the bushes paid 4 and 6), not only a deviation
    assert DeltaRuleCritic(prior=ConstantPrior(0.1)).spec()["prior"] == {"type": "ConstantPrior", "level": 0.1}


# ---- the GP critic, its kernels and the exploring actors ----------------------------------------------------------------

from agents import (GPAgent, GPCritic, PosteriorActor, RBFKernel, RelativeSoftmax, build_agent)


def memory_with(attrs, rewards):
    """A FullMemory that knows these bushes (attrs (n, 3)) and holds `rewards[j]` (a list of fruit rewards) for each."""
    m = FullMemory()
    m.begin(SimpleNamespace(n_bushes=len(attrs), fruit_count=10))
    m.known[:] = True
    m.attrs[:] = attrs
    for j, rs in enumerate(rewards):
        for r in rs:
            m.record_reward(j, r)
    return m


def gp_fitted(critic, attrs, rewards):
    m = memory_with(attrs, rewards)
    critic.begin(None)
    critic.update(m)
    return critic


def test_kernels_are_one_at_zero_and_additive_shares_what_the_other_attributes_do_not_change():
    a, b = np.array([[0.2, 0.5, 0.5]]), np.array([[0.6, 0.5, 0.5]])
    ell = 0.3
    far = np.exp(-0.4 ** 2 / (2 * ell ** 2))
    assert RBFKernel(ell).matrix(a, a)[0, 0] == pytest.approx(1.0) and RBFKernel(ell, additive=False).matrix(a, a)[0, 0] == pytest.approx(1.0)
    assert RBFKernel(ell).matrix(a, b)[0, 0] == pytest.approx((2 + far) / 3)       # two attributes agree exactly
    assert RBFKernel(ell, additive=False).matrix(a, b)[0, 0] == pytest.approx(far)


def test_gp_posterior_matches_the_closed_form():
    X = np.array([[0.1, 0.2, 0.3], [0.8, 0.7, 0.6]])
    critic = gp_fitted(GPCritic(RBFKernel(0.4, additive=False), prior_mean=0.2, initial_std=0.7, initial_noise_std=0.3), X, [[2.0], [4.0]])
    Z = np.array([[0.15, 0.2, 0.3], [0.5, 0.5, 0.5]])
    k = RBFKernel(0.4, additive=False)
    K = 0.7 ** 2 * k.matrix(X, X) + 0.3 ** 2 * np.eye(2)
    Ks = 0.7 ** 2 * k.matrix(Z, X)
    mean, sd = critic.value(Z)
    assert mean == pytest.approx(0.2 + Ks @ np.linalg.solve(K, np.array([2.0, 4.0]) - 0.2))
    assert sd ** 2 == pytest.approx(0.7 ** 2 - np.einsum("ij,ij->i", Ks, np.linalg.solve(K, Ks.T).T))


def test_gp_is_unsure_far_from_what_it_has_seen_and_sure_near_it():
    X = np.array([[0.1, 0.1, 0.1]])
    critic = gp_fitted(GPCritic(prior_mean=0.5, initial_std=1.0, initial_noise_std=0.05), X, [[3.0, 3.0]])
    (near, far), (sd_near, sd_far) = critic.value(np.array([[0.1, 0.1, 0.1], [0.95, 0.95, 0.95]]))
    assert near > 2.0 and sd_near < 0.2 and sd_far > 0.9 and far < near


def test_gp_estimates_its_prior_and_noise_from_memory_and_falls_back_before_it_can():
    empty = gp_fitted(GPCritic(initial_mean=0.1, initial_std=1.0, initial_noise_std=0.3), np.zeros((3, 3)), [[], [], []])
    assert (empty._m0, empty._s0, empty._noise2) == (0.1, 1.0, pytest.approx(0.09))
    X = np.array([[0.1, 0.1, 0.1], [0.5, 0.5, 0.5], [0.9, 0.9, 0.9]])
    critic = gp_fitted(GPCritic(), X, [[1.0, 3.0], [2.0, 2.0, 2.0], [6.0, 6.0]])      # bush means 2, 2, 6; within-bush variances 2, 0, 0
    assert critic._noise2 == pytest.approx((1 * 2.0 + 2 * 0.0 + 1 * 0.0) / 4)         # pooled over the bushes with two or more fruits
    assert critic._m0 == pytest.approx(10 / 3)
    n = np.array([2, 3, 2])
    assert critic._s0 == pytest.approx(np.sqrt(np.var([2.0, 2.0, 6.0], ddof=1) - np.mean(critic._noise2 / n)))
    assert gp_fitted(GPCritic(prior_mean=0.7), X, [[1.0], [2.0], [6.0]])._m0 == 0.7


def test_gp_sample_is_a_joint_draw_from_the_posterior():
    X = np.array([[0.1, 0.1, 0.1], [0.9, 0.9, 0.9]])
    critic = gp_fitted(GPCritic(RBFKernel(0.3), prior_mean=1.0, initial_std=1.0, initial_noise_std=0.3), X, [[2.0], [0.5]])
    Z = np.array([[0.4, 0.4, 0.4], [0.45, 0.45, 0.45], [0.6, 0.6, 0.6]])
    rng = np.random.default_rng(0)
    draws = np.array([critic.sample(Z, rng) for _ in range(4000)])
    mean, sd = critic.value(Z)
    assert draws.mean(axis=0) == pytest.approx(mean, abs=0.05) and draws.std(axis=0) == pytest.approx(sd, abs=0.05)
    r = np.corrcoef(draws.T)
    assert r[0, 1] > 0.95 and r[0, 1] > r[0, 2]            # neighbouring bushes move together: a draw is one function, not independent guesses


def three_bush_agent(actor, first_reward, seed=0):
    """Bush 0 (depleted, attributes A) and bush 1 (a clone of it) lie 30 away on one side, bush 2 (attributes B, never tried) 30 away on the
    other; the critic has seen bush 0 return `first_reward`. Returns (agent, body)."""
    w = world_with([[30, 0], [0, 30], [-30, 0]], attrs=[[0.1, 0.1, 0.1], [0.1, 0.1, 0.1], [0.9, 0.9, 0.9]])
    agent = GPAgent(actor, prior_mean=1.0, initial_std=1.0)
    agent.begin_session(w, np.random.default_rng(seed))
    agent.observe(Observation(np.arange(3), w.pos, w.canopy_radius, np.column_stack([w.shape, w.color, w.moisture]), np.zeros(3, dtype=bool)))
    agent.record_reward(0, first_reward)
    agent.mark_depleted(0)
    agent.end_visit(0)
    return agent, Body(np.zeros(2), 0.0, 60.0, 0.0)


def test_ucb_goes_for_the_uncertain_bush_only_when_the_bonus_is_large():
    greedy, body = three_bush_agent(PosteriorActor(0.0, temperature=0.001), 9.0)
    bold, body2 = three_bush_agent(PosteriorActor(20.0, temperature=0.001), 9.0)
    assert greedy.act(body) == Harvest(1) and bold.act(body2) == Harvest(2)       # the clone of the rich bush against the unknown one


def test_thompson_sampling_chooses_the_uncertain_bush_in_proportion_to_the_uncertainty():
    agent, body = three_bush_agent(PosteriorActor(0.0, sample=True), 1.2)
    picks = [agent.act(body).bush for _ in range(300)]
    assert 0.25 < np.mean(np.array(picks) == 2) < 0.75
    confident, body = three_bush_agent(PosteriorActor(0.0, sample=True), 9.0)
    assert {confident.act(body).bush for _ in range(100)} == {1}                  # certain and far better: never gambles


def test_the_hybrid_adds_the_bonus_to_the_draw():
    agent, body = three_bush_agent(PosteriorActor(20.0, sample=True), 9.0)
    assert {agent.act(body).bush for _ in range(100)} == {2}


def test_relative_softmax_is_scale_free_and_unscaled_when_nothing_is_positive():
    rule = RelativeSoftmax(0.1)
    u = np.array([1.0, 0.8, 0.2, -np.inf])
    assert rule.probs(u) == pytest.approx(rule.probs(10 * u)) and rule.probs(u)[3] == 0
    assert rule.probs(np.array([1.0, 0.8])) == pytest.approx(np.exp(np.array([0.0, -2.0])) / np.exp(np.array([0.0, -2.0])).sum())
    assert rule.probs(np.array([-1.0, -2.0])) == pytest.approx(Softmax(0.1).probs(np.array([-1.0, -2.0])))


def test_gp_agents_run_and_round_trip_through_their_specs():
    spec = GPAgent(PosteriorActor(0.3, temperature=0.2), kernel=RBFKernel(0.2, additive=False), prior_mean=0.5).spec()
    assert build_agent(spec).spec() == spec and spec["critic"]["kernel"]["additive"] is False
    w = world_with([[30, 0], [0, 30], [-30, 0]], rewards=[[2] * 10, [5] * 10, [1] * 10], attrs=[[0.1] * 3, [0.5] * 3, [0.9] * 3], duration=60.0)
    for name in ("gp_mean", "gp_ucb", "gp_thompson", "gp_hybrid"):
        assert run_episode(REGISTRY[name](), w).total > 0


# ---- softmax with a horizon, curiosity and peek-and-leave, area-restricted search -------------------------------------------

from agents import AreaRestrictedActor, CuriousActor, LearnerAgent, SoftmaxActor


def table_agent(actor, values, attrs, pos=None, duration=60.0):
    """An agent that knows every bush (FullKnowledge) and values them from a table, in a toy world."""
    pos = pos if pos is not None else [[20, 0], [0, 20], [-20, 0], [0, -20]][:len(values)]
    agent = ComposedAgent(actor, TableCritic(values), FullKnowledge())
    agent.begin_session(world_with(pos, attrs=attrs, duration=duration), np.random.default_rng(0))
    return agent


def test_softmax_actor_noise_shrinks_with_the_time_left_only_when_asked():
    values, attrs = [3.0, 2.5, 2.0], [[0.1] * 3, [0.5] * 3, [0.9] * 3]
    share = {}
    for horizon in (True, False):
        for left in (60.0, 0.01):
            agent = table_agent(SoftmaxActor(0.3, horizon=horizon), values, attrs)
            share[horizon, left] = np.mean([agent.act(Body(np.zeros(2), 0.0, left, 0.0)).bush == 0 for _ in range(300)])
    assert share[True, 60.0] < 0.8 and share[True, 0.01] == 1.0       # loose at the start, greedy at the end
    assert share[False, 60.0] < 0.8 and share[False, 0.01] < 0.8      # without a horizon the temperature is constant
    assert SoftmaxActor(horizon=True).deadline_dependent and not SoftmaxActor().deadline_dependent


def test_curiosity_bonus_is_larger_for_unfamiliar_attributes_scales_with_the_mean_reward_and_is_off_at_zero():
    attrs = [[0.1, 0.1, 0.1], [0.1, 0.1, 0.1], [0.9, 0.9, 0.9], [0.5, 0.5, 0.5]]
    bonuses = {}
    for reward in (2.0, 4.0):
        actor = CuriousActor(beta=0.5)
        agent = table_agent(actor, [1.0] * 4, attrs)
        agent.record_reward(0, reward)
        agent.end_visit(0)
        bonuses[reward] = actor._bonus(agent.view(Body(np.zeros(2), 0.0, 30.0, reward)))
    b = bonuses[2.0]
    assert b[2] > b[3] > b[1] and b[1] == pytest.approx(b[0])        # novel > partly familiar > a clone of what was harvested
    assert bonuses[4.0] == pytest.approx(2 * b)                       # in units of the running mean value
    agent = table_agent(CuriousActor(beta=0.0), [1.0] * 4, attrs)
    assert CuriousActor(beta=0.0)._bonus(agent.view(Body(np.zeros(2), 0.0, 30.0, 0.0))) == 0.0


def test_peek_and_leave_leaves_poor_bushes_after_the_peek_and_stays_on_rich_ones():
    def keep(first, peek, margin=1.0):
        actor = CuriousActor(beta=0.0, peek_fruits=peek, margin=margin)
        agent = table_agent(actor, [1.0] * 3, [[0.1] * 3, [0.5] * 3, [0.9] * 3])
        for _ in range(10):
            agent.record_reward(2, 3.0)                  # elsewhere: 30 reward so far, 1 reward per second at 30 s
        for r in first:
            agent.record_reward(0, r)
        return agent.keep_harvesting(Body(np.zeros(2), 0.0, 30.0, 30.0), 0, first[-1])
    assert keep([0.1, 0.1], peek=2) is False                  # 0.2 per fruit-second after two fruits: far below the average rate
    assert keep([0.1], peek=2) is True                        # still peeking
    assert keep([0.1, 0.1], peek=None) is True               # the default harvests to empty
    assert keep([3.0, 3.0], peek=2) is True                  # rich bush: its rate beats the average
    assert keep([1.0, 1.0], peek=2, margin=1.0) is True and keep([1.0, 1.0], peek=2, margin=5.0) is False


def test_area_restricted_search_stays_near_a_hit_and_widens_after_misses():
    attrs = [[0.5, 0.5, 0.5], [0.55, 0.5, 0.5], [0.9, 0.9, 0.9], [0.1, 0.1, 0.1]]
    values = [9.0, 3.0, 6.0, 1.0]
    actor = AreaRestrictedActor(radius=0.3, growth=2.0)
    agent = table_agent(actor, values, attrs)
    body = Body(np.zeros(2), 0.0, 60.0, 0.0)
    agent.record_reward(3, 1.0)
    agent.mark_depleted(3)
    agent.end_visit(3)
    assert agent.act(body) == Harvest(0)                      # no anchor yet: the best by the critic
    agent.record_reward(0, 8.0)
    agent.mark_depleted(0)
    agent.end_visit(0)                                       # 8 beats the mean so far (4.5): a hit
    assert agent.act(body) == Harvest(1)                      # bush 2 is worth more but lies far from the hit in attribute space
    picks = []
    for _ in range(2):                                       # misses: the radius doubles each time (0.3, 0.6, 1.2)
        agent.record_reward(1, 0.1)
        agent.end_visit(1)
        picks.append((agent.act(body), actor._reach))
    assert picks[0] == (Harvest(1), pytest.approx(0.6))       # 0.6 still excludes bush 2 (attribute distance about 0.69 from the hit)
    assert picks[1] == (Harvest(2), pytest.approx(1.2))       # 1.2 includes it, and it is worth more


def test_area_restricted_search_drops_the_restriction_when_nothing_is_inside_it():
    actor = AreaRestrictedActor(radius=0.05, growth=2.0)
    agent = table_agent(actor, [2.0, 5.0], [[0.1] * 3, [0.9] * 3], pos=[[20, 0], [0, 20]])
    body = Body(np.zeros(2), 0.0, 60.0, 0.0)
    agent.mark_depleted(0)
    actor._anchor, actor._reach = np.array([0.1] * 3), 0.05
    assert agent.act(body) == Harvest(1)                      # bush 1 is outside the radius but the only one left: the agent still moves


def test_a_bush_left_by_peek_and_leave_is_not_returned_to():
    w = tiny_world([[0, 20], [3, 23], [0, 60]], [[9] * 4, [0] * 4, [5] * 4], duration=60.0)       # a rich bush, a poor one beside it, a far fair one
    r = run_episode(LearnerAgent(CuriousActor(beta=0.0, peek_fruits=2)), w)
    assert [(v[0], v[1]) for v in r.trace] == [(0, 4), (1, 2), (2, 4)]       # the poor bush is peeked at once, not revisited a fruit at a time


# ---- the matched GP: the feature kernel and the options that switch the GP's estimates off ----------------------------------

from agents import FeatureKernel
from specs import spec_hash


def test_the_feature_kernel_is_the_feature_similarity_and_a_gp_on_it_is_ridge_regression_on_the_features():
    feats = RBFFeatures(0.3, 8, additive=True)
    X = np.array([[0.1, 0.2, 0.3], [0.8, 0.7, 0.6], [0.5, 0.1, 0.9]])
    kernel = FeatureKernel(feats)
    assert kernel.matrix(X, X) == pytest.approx(feats(X) @ feats(X).T) and np.diag(kernel.matrix(X, X)) == pytest.approx(1.0)
    assert kernel.matrix(X[:0], X).shape == (0, 3) and kernel.matrix(X, X[:0]).shape == (3, 0)        # no data yet
    critic = gp_fitted(GPCritic(kernel, prior_mean=0.1, weight_by_count=False, prior_std=1.0, noise_std=0.3), X, [[2.0, 2.0], [4.0], [1.0, 1.0, 1.0]])
    Z = np.array([[0.15, 0.2, 0.3], [0.5, 0.5, 0.5]])
    Phi, y = feats(X), np.array([2.0, 4.0, 1.0])
    w = np.linalg.solve(Phi.T @ Phi + (0.3 / 1.0) ** 2 / 10 * np.eye(Phi.shape[1]), Phi.T @ (y - 0.1))   # weights of the Bayesian linear model (every bush a 10-fruit mean)
    assert critic.value(Z)[0] == pytest.approx(0.1 + feats(Z) @ w)


def test_the_gp_can_use_fixed_hyperparameters_and_weigh_every_bush_alike():
    X = np.array([[0.1] * 3, [0.5] * 3, [0.9] * 3])
    rewards = [[1.0, 3.0], [2.0, 2.0, 2.0], [6.0]]
    fixed = gp_fitted(GPCritic(prior_std=0.8, noise_std=0.25), X, rewards)
    assert (fixed._s0, fixed._noise2) == (0.8, pytest.approx(0.0625))               # not estimated from the memory
    assert (gp_fitted(GPCritic(), X, rewards)._s0, gp_fitted(GPCritic(), X, rewards)._noise2) != (0.8, 0.0625)
    empty = GPCritic(prior_std=0.8, noise_std=0.25)
    empty.begin(None)
    assert (empty._s0, empty._noise2) == (0.8, pytest.approx(0.0625))               # ... nor before any data
    # two bushes at the same attributes, one measured with 1 fruit and one with 10: weighted by count the 10-fruit mean counts more,
    # unweighted they count alike
    same = np.array([[0.5] * 3, [0.5] * 3])
    data = [[0.0], [4.0] * 10]
    weighted = gp_fitted(GPCritic(prior_mean=0.0, prior_std=1.0, noise_std=1.0), same, data).value(same[:1])[0][0]
    alike = gp_fitted(GPCritic(prior_mean=0.0, prior_std=1.0, noise_std=1.0, weight_by_count=False), same, data).value(same[:1])[0][0]
    assert weighted == pytest.approx(40 / 12) and alike == pytest.approx(40 / 21)       # precision-weighted means at one point: (4/0.1) / (1 + 1 + 10) against (4/0.1) / (1 + 10 + 10), every bush a 10-fruit mean


def test_the_ladder_agents_differ_from_the_gp_one_step_at_a_time_and_round_trip():
    ladder = ["gp_mean", "gp_fixmean", "gp_equalw", "gp_fixhyper", "gp_matched"]
    specs = [REGISTRY[n]().spec() for n in ladder]
    assert len({spec_hash(s) for s in specs}) == 5
    assert [s["critic"]["prior_mean"] for s in specs] == [None, 0.1, 0.1, 0.1, 0.1]
    assert [s["critic"]["weight_by_count"] for s in specs] == [True, True, False, False, False]
    assert [s["critic"]["prior_std"] for s in specs] == [None, None, None, 1.0, 1.0]
    assert [s["critic"]["kernel"]["type"] for s in specs] == ["RBFKernel"] * 4 + ["FeatureKernel"]
    assert all(build_agent(s).spec() == s for s in specs)


# ---- replay in the delta-rule critic ------------------------------------------------------------------------------------------

from agents import FullSweeps, PrioritizedReplay, SampledReplay


def test_replay_policies_choose_which_stored_bushes_to_present_again():
    errors = np.array([0.1, -2.0, 0.5, 2.0])
    assert list(FullSweeps(2).indices(errors)) == [0, 1, 2, 3, 0, 1, 2, 3] and len(FullSweeps(0).indices(errors)) == 0
    assert list(PrioritizedReplay(3).indices(errors)) == [1, 3, 2]                  # the largest errors first, ties in stored order
    sampled = SampledReplay(steps=6, seed=4)
    sampled.begin()
    first = sampled.indices(errors)
    sampled.begin()
    assert list(first) == list(sampled.indices(errors)) and len(first) == 6 and first.min() >= 0 and first.max() < 4      # restarted each session
    assert len(SampledReplay().indices(np.zeros(0))) == 0


def test_a_delta_rule_critic_without_replay_has_the_same_spec_as_before_and_with_replay_a_new_one():
    plain = REGISTRY["learner"]().spec()["critic"]
    assert "replay" not in plain
    replayed = LearnerAgent(UtilityActor(), replay=FullSweeps(3)).spec()
    assert replayed["critic"]["replay"] == {"type": "FullSweeps", "epochs": 3}
    assert build_agent(replayed).spec() == replayed and spec_hash(replayed) != spec_hash(REGISTRY["learner"]().spec())


def test_many_sweeps_make_the_delta_rule_converge_to_the_exact_fit_of_the_same_features():
    feats = RBFFeatures(0.3, 8, additive=True)
    X = np.array([[0.1, 0.2, 0.3], [0.8, 0.7, 0.6], [0.5, 0.1, 0.9]])
    rewards = [[2.0, 2.0], [4.0, 4.0], [1.0, 1.0]]
    Z = np.array([[0.15, 0.2, 0.3], [0.5, 0.5, 0.5], [0.7, 0.6, 0.5]])
    exact = gp_fitted(GPCritic(FeatureKernel(feats), prior_mean=0.1, prior_std=1.0, noise_std=1e-3, weight_by_count=False), X, rewards).value(Z)[0]
    def delta(critic):
        critic.begin(SimpleNamespace(n_bushes=3))
        critic.update(memory_with(X, rewards))
        return critic

    online = delta(DeltaRuleCritic(features=feats)).value(Z)[0]
    swept = delta(DeltaRuleCritic(features=feats, replay=FullSweeps(400)))
    assert np.abs(swept.value(Z)[0] - exact).max() < 0.02 < np.abs(online - exact).max()       # one online pass is far from it; many passes are not
    assert swept.value(X)[0] == pytest.approx([2.0, 4.0, 1.0], abs=0.02)                       # and interpolate the bushes it has seen


def test_agents_with_replay_run_a_session():
    w = world_with([[0, 20], [3, 23], [0, 60]], rewards=[[9] * 4, [1] * 4, [5] * 4], attrs=[[0.1] * 3, [0.5] * 3, [0.9] * 3], duration=60.0)
    for replay in (FullSweeps(3), SampledReplay(10), PrioritizedReplay(2)):
        assert run_episode(LearnerAgent(UtilityActor(), replay=replay), w).total > 0
