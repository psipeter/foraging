from types import SimpleNamespace

import numpy as np
import pytest

from agents import (Actor, Argmax, ComposedAgent, Critic, Explore, FullKnowledge, FullMemory, Harvest, Look, OracleCritic,
                    PlannerActor, Softmax, Stop, UtilityActor, View, oracle_agent, utility_rate)
from interlude import generate_interlude
from perception import (ConePercept, NullPercept, Observation, horizontal_fov, percept_for, percept_from_params)
from sim import State, evaluate_interlude, run_episode, run_n
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
        self.version += 1

    def value(self, attrs, ids=None):
        n = len(attrs)
        return np.full(n, self.mean), np.zeros(n)


class TableCritic(Critic):
    """Values from a fixed per-bush table (to show the actor's utility comes from the critic)."""
    def __init__(self, table):
        self.table = np.asarray(table, dtype=float)

    def value(self, attrs, ids=None):
        return self.table[np.asarray(ids)], np.zeros(len(ids))


# --- memory ------------------------------------------------------------------------------------------------

def test_full_knowledge_preloads_the_map_but_no_rewards():
    w = world_with([[10, 0], [0, 20]], attrs=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    m = FullKnowledge()
    m.begin(w)
    assert m.known.all() and np.array_equal(m.pos, w.pos) and np.allclose(m.attrs, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    assert m.map_version == 0 and (m.taken == 0).all() and len(m.experiences()[1]) == 0


def test_full_memory_accumulates_what_it_sees_and_gets():
    w = world_with([[10, 0], [0, 20], [30, 30]], attrs=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]])
    m = FullMemory()
    m.begin(w)
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
    for make in (NearestAgent, lambda: GreedyAgent(15, "rate")):
        runs = [run_episode(make(), w, percept=p) for p in (None, NullPercept(), ConePercept(20.0, 30.0), ConePercept(360.0, 1e4))]
        assert all(r.trace == runs[0].trace and r.total == runs[0].total for r in runs)


# --- engine actions ----------------------------------------------------------------------------------------

def percept_agent(actions, percept, memory=None):
    return ComposedAgent(Script(*actions), OracleCritic(), memory or FullMemory(), percept)


def test_look_costs_time_turns_the_view_and_reveals():
    w = world_with([[40, 0]], speed=5.0)
    agent = percept_agent([Look(90.0)], ConePercept(60.0, 100.0))
    r = run_episode(agent, w)
    assert r.look_time == pytest.approx(0.5) and r.idle_time == pytest.approx(w.session_duration - 0.5)
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


def test_explore_stops_at_the_clock_and_at_unwalkable_ground():
    w = world_with([[500, 500]], speed=5.0, duration=3.0)
    r = run_episode(percept_agent([Explore(90.0, 100.0)], NullPercept()), w)
    assert r.walk_time == pytest.approx(3.0) and r.idle_time == 0.0
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


def test_harvest_range_is_walked_to_and_heading_faces_the_bush():
    w = world_with([[0, 60]], speed=5.0)
    agent = ComposedAgent(Script(Harvest(0)), OracleCritic(), FullKnowledge(), ConePercept(10.0, 200.0))
    # FullKnowledge never needs the percept; Script above harvests bush 0 directly.
    r = run_episode(agent, w)
    assert r.n_fruits == 2 and agent.memory.taken[0] == 2 and agent.memory.depleted[0]


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
    view = agent.view(State(w))
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
    agent2.act(state)
    n1 = agent2.nodes
    agent2.act(state)
    assert agent2.nodes == n1
    # a limited-memory planner replans when it learns a new bush, starting from where it is
    mem = FullMemory()
    agent3 = ComposedAgent(PlannerActor("exact"), OracleCritic(), mem)
    agent3.begin_session(w, np.random.default_rng(0))
    attrs = np.zeros((1, 3))
    agent3.observe(Observation(np.array([0]), w.pos[[0]], w.canopy_radius[[0]], attrs, np.zeros(1, dtype=bool)))
    first = agent3.act(state)
    assert first == Harvest(0) and agent3.plan == [0]
    agent3.observe(Observation(np.array([2]), w.pos[[2]], w.canopy_radius[[2]], attrs, np.zeros(1, dtype=bool)))
    state.pos = np.array([12.0, 0.0])
    agent3.act(state)
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


def test_interlude_scoring_chance_and_softmax():
    nearest = evaluate_interlude(session_agent(UtilityActor("nearest")), toy_interlude(), n_samples=2000)
    assert abs(nearest.by_type["contrast"] - 0.5) < 0.05                  # equal distances, random ties: chance
    soft_hot = evaluate_interlude(session_agent(UtilityActor("value", choice=Softmax(100.0))), toy_interlude(), n_samples=2000)
    soft_cold = evaluate_interlude(session_agent(UtilityActor("value", choice=Softmax(0.02))), toy_interlude(), n_samples=2000)
    assert abs(soft_hot.by_type["contrast"] - 0.5) < 0.06 and soft_cold.by_type["contrast"] > 0.98


def test_interlude_uses_the_critic_not_the_world_and_is_frozen():
    agent = session_agent(UtilityActor("value"))
    agent.critic.mean = None
    before = agent.critic.version
    evaluate_interlude(agent, toy_interlude(), n_samples=5)
    assert agent.critic.version == before


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


def test_seeded_generation_matches_the_assets_own_seed_and_applies_overrides():
    a, _, _ = generate_interlude("S3_Interlude", pool_samples=60_000)
    b, _, _ = generate_interlude("S3_Interlude", pool_samples=60_000, seed=3)
    assert a == b                                                         # S3's own seed is 3
    c, _, _ = generate_interlude("S3_Interlude", pool_samples=60_000, seed=4)
    assert c["seed"] == 4 and c["treePos"] != a["treePos"]
