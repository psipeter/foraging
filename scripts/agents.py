"""Foraging agents. All agents live in this file; add new ones with REGISTRY.

An agent is three components plus a sensor, composed by `ComposedAgent` and run by sim.run_episode:

    Memory  what the agent keeps about the bushes it has seen and the rewards it has received. It is the constraint on
            the other two: the actor may only use `memory` (the map: positions, attributes, spent or not, the fruits
            taken), and the critic may only learn from `memory.experiences()` (attributes and reward, one per fruit).
            FullKnowledge is preloaded with the whole map; FullMemory accumulates everything it sees and receives.
    Critic  the value representation and its learning rule: value(attributes) -> (mean reward per fruit, uncertainty),
            fit from memory, freezable. OracleCritic is "full knowledge": the true reward function.
    Actor   the policy: what to do next (Harvest a known bush, Explore, Look, Stop) and whether to leave a bush after a
            fruit. Its choices go through a ChoiceRule (hard-max or softmax) and any value it uses (value, rate) is
            derived from the critic, never read from the world.
    Percept the sensor: which bushes are in view. It belongs to the environment, not the agent: perception.py defines it and the
            engine applies it (by default a cone as wide as the session camera), so every agent senses the same world the
            same way; an agent may carry its own `percept` as an override. Walking, exploring and looking are actions of the
            actor, not part of the percept.

`nearest`, `greedy_*` and `plan_*` are actors with the oracle critic and full-knowledge memory. A learning agent swaps
the critic and memory; the actor code is the same. Agents are built by zero-argument factories in
REGISTRY (a fresh agent per world).
"""

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from world import bush_value

REGISTRY = {}   # name -> zero-argument agent factory


# --------------------------------------------------------------------------------------------------
# Actions (what an actor returns; the engine executes them and charges time)
# --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Harvest:
    """Walk to the edge of this bush's harvest range and harvest it, fruit by fruit, until the actor leaves or it is empty."""
    bush: int


@dataclass(frozen=True)
class Explore:
    """Walk `distance` units along `bearing` (degrees about +Y from +Z toward +X; the game's yaw), looking where it goes."""
    bearing: float
    distance: float


@dataclass(frozen=True)
class Look:
    """Turn the view by `angle` degrees (+ = right); costs |angle| / turn rate seconds."""
    angle: float


@dataclass(frozen=True)
class Stop:
    """End the session's activity (the remaining time is idle)."""


# --------------------------------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------------------------------

class Memory:
    """Dense per-bush records indexed by bush id (arrays of length n; `known` says which are in memory) plus the reward
    list of every fruit taken from each bush. This base class starts empty and does not forget; subclasses set what is
    known at the start or apply limits.

    Readers: `known`, `pos` (n, 2), `radius`, `attrs` (n, 3: shape, color, moisture), `depleted` (seen spent or emptied
    by the agent), `taken` (fruits the agent took from each bush), `rewards[j]` (list, one per fruit taken from bush j),
    `experiences()`. `map_version` increases whenever a bush is added to the map; `experience_version` whenever a reward
    is recorded (a critic refits when it changes).
    """
    world_ids = True      # ids index the session world's bush table (False for an Interlude pair, see sim.evaluate_interlude)

    def begin(self, world):
        n = len(world.pos)
        self.n = n
        self.fruit_count = world.fruit_count
        self.known = np.zeros(n, dtype=bool)
        self.pos = np.zeros((n, 2))
        self.radius = np.zeros(n)
        self.attrs = np.zeros((n, 3))
        self.depleted = np.zeros(n, dtype=bool)
        self.taken = np.zeros(n, dtype=int)
        self.rewards = [[] for _ in range(n)]
        self.map_version = 0
        self.experience_version = 0

    def _learn(self, ids, world_like):
        self.known[ids] = True
        self.pos[ids] = world_like.pos[ids]
        self.radius[ids] = world_like.canopy_radius[ids]
        self.attrs[ids] = np.column_stack([world_like.shape[ids], world_like.color[ids], world_like.moisture[ids]])
        self.map_version += 1

    def observe(self, obs):
        """Take in an Observation (perception.Observation): the bushes in view this moment, with their attributes and whether each
        looks spent."""
        if len(obs.ids) == 0:
            return
        new = obs.ids[~self.known[obs.ids]]
        if len(new):
            self.known[new] = True
            sel = np.isin(obs.ids, new)
            self.pos[obs.ids[sel]] = obs.pos[sel]
            self.radius[obs.ids[sel]] = obs.radius[sel]
            self.attrs[obs.ids[sel]] = obs.attrs[sel]
            self.map_version += 1
        self.depleted[obs.ids[obs.depleted]] = True

    def record_reward(self, bush, reward):
        self.rewards[bush].append(float(reward))
        self.taken[bush] += 1
        self.experience_version += 1

    def mark_depleted(self, bush):
        self.depleted[bush] = True

    def experiences(self):
        """(attrs (m, 3), rewards (m,), ids (m,)): one row per fruit the agent has taken (and still remembers)."""
        ids = np.array([j for j in range(self.n) for _ in self.rewards[j]], dtype=int)
        rewards = np.array([r for j in range(self.n) for r in self.rewards[j]], dtype=float)
        return self.attrs[ids], rewards, ids

    def fruits_left(self):
        return self.fruit_count - self.taken


class FullKnowledge(Memory):
    """Preloaded with every bush's position, size and attributes (no rewards): what the oracle agents start with."""

    def begin(self, world):
        super().begin(world)
        self._learn(np.arange(self.n), world)
        self.map_version = 0


class FullMemory(Memory):
    """Starts empty; remembers every bush it has seen and every reward it has received, perfectly and forever."""


# --------------------------------------------------------------------------------------------------
# Critic
# --------------------------------------------------------------------------------------------------

class Critic:
    """Value representation and learning rule. `value(attrs, ids=None) -> (mean, sd)` per bush: expected reward per fruit
    and the critic's uncertainty about it. `ids` are session-world bush ids when the attributes belong to the session's
    bushes (an oracle may look them up); learned critics use the attributes only. `version` changes whenever the
    value function does."""
    version = 0
    frozen = False

    def begin(self, world):
        pass

    def update(self, memory):
        """Learn from what memory now holds, unless frozen."""
        if not self.frozen:
            self._fit(memory)

    def _fit(self, memory):
        pass

    def freeze(self):
        """Stop learning (the Interlude shows no outcomes, so humans do not learn there either)."""
        self.frozen = True

    def value(self, attrs, ids=None):
        raise NotImplementedError


class OracleCritic(Critic):
    """Full knowledge of the reward function: R_bush for any attributes, with no uncertainty."""

    def begin(self, world):
        self.world = world

    def value(self, attrs, ids=None):
        attrs = np.asarray(attrs, dtype=float)
        if ids is not None and getattr(self.world, "value", None) is not None:
            mean = np.asarray(self.world.value, dtype=float)[np.asarray(ids)]
        else:
            mean = np.asarray(bush_value(self.world.params.reward_function, attrs[:, 0], attrs[:, 1], attrs[:, 2]), dtype=float)
        return mean, np.zeros(len(mean))


# --------------------------------------------------------------------------------------------------
# Choice rules (part of the actor)
# --------------------------------------------------------------------------------------------------

class ChoiceRule:
    """Maps a utility vector (-inf = not a candidate) to a pick. `probs` is the distribution the rule samples from, so
    likelihoods of observed choices can be computed later."""

    def probs(self, utilities, random_ties=False):
        raise NotImplementedError

    def pick(self, utilities, rng, random_ties=False):
        """Index of the pick, or None when nothing is a candidate."""
        u = np.asarray(utilities, dtype=float)
        if not np.isfinite(u).any():
            return None
        return self._pick(u, rng, random_ties)

    def _pick(self, u, rng, random_ties):
        return int(rng.choice(len(u), p=self.probs(u, random_ties)))


class Argmax(ChoiceRule):
    """Hard-max. Ties go to the lowest index (as the original agents did) unless `random_ties`."""

    def probs(self, utilities, random_ties=False):
        u = np.asarray(utilities, dtype=float)
        p = np.zeros(len(u))
        if not np.isfinite(u).any():
            return p
        if random_ties:
            top = np.flatnonzero(u >= u.max() - 1e-12)
            p[top] = 1.0 / len(top)
        else:
            p[int(np.argmax(u))] = 1.0
        return p

    def _pick(self, u, rng, random_ties):
        if random_ties:
            return int(rng.choice(np.flatnonzero(u >= u.max() - 1e-12)))
        return int(np.argmax(u))


class Softmax(ChoiceRule):
    """P(i) proportional to exp(u_i / temperature) over the candidates."""

    def __init__(self, temperature=1.0):
        if temperature <= 0:
            raise ValueError("softmax temperature must be positive")
        self.temperature = temperature

    def probs(self, utilities, random_ties=False):
        u = np.asarray(utilities, dtype=float)
        p = np.zeros(len(u))
        ok = np.isfinite(u)
        if not ok.any():
            return p
        z = (u[ok] - u[ok].max()) / self.temperature
        e = np.exp(z)
        p[ok] = e / e.sum()
        return p


# --------------------------------------------------------------------------------------------------
# What an actor sees
# --------------------------------------------------------------------------------------------------

class Task:
    """What the participant is told or can learn about the task itself: speeds, durations, the harvest range and how many
    fruits a bush has."""

    def __init__(self, world):
        p = world.params
        self.speed = world.move_speed
        self.fruit_duration = world.fruit_duration
        self.fruit_count = world.fruit_count
        self.session_duration = world.session_duration
        self.gap_base = p.harvest_range_gap_base
        self.gap_per_radius = p.harvest_range_gap_per_radius

    def reach(self, radius):
        """Center distance within which a bush of this canopy radius can be harvested."""
        return radius + self.gap_base + self.gap_per_radius * radius


class View:
    """Read-only view for the actor: the engine's state (time left, position, heading), memory, critic and task. Value
    and rate utilities are computed from the critic here, so an actor cannot see the true rewards."""

    def __init__(self, state, memory, critic, task):
        self.state, self.memory, self.critic, self.task = state, memory, critic, task

    @property
    def time_elapsed(self):
        return self.task.session_duration - self.state.time_left

    def candidates(self):
        """Mask of bushes the agent knows about and has not seen spent."""
        return self.memory.known & ~self.memory.depleted

    def reach(self):
        return self.task.reach(self.memory.radius)

    def travel_times(self):
        """(n,) seconds of walking from here to harvest range of each bush; inf for bushes not available."""
        m = self.memory
        d = np.hypot(*(m.pos - self.state.pos).T)
        t = np.maximum(0.0, d - self.reach()) / self.task.speed
        t[~self.candidates()] = float("inf")
        return t

    def values(self):
        """(n,) the critic's expected reward per fruit for every bush in memory (and its uncertainty)."""
        m = self.memory
        ids = np.arange(m.n) if m.world_ids else None
        return self.critic.value(m.attrs, ids)


# --------------------------------------------------------------------------------------------------
# Utilities (functions of the view; value-based ones come from the critic)
# --------------------------------------------------------------------------------------------------

def utility_nearest(view):
    """Negative walking time: ignores value entirely."""
    return -view.travel_times()


def utility_value(view):
    """Expected reward remaining on the bush: critic mean per fruit times fruits left."""
    mean, _ = view.values()
    return mean * view.memory.fruits_left()


def utility_rate(view):
    """Expected reward remaining per second of (walk + harvest) time."""
    mean, _ = view.values()
    left = view.memory.fruits_left()
    return mean * left / (view.travel_times() + left * view.task.fruit_duration)


UTILITIES = {"nearest": utility_nearest, "value": utility_value, "rate": utility_rate}


# --------------------------------------------------------------------------------------------------
# Actors
# --------------------------------------------------------------------------------------------------

class Actor:
    """The policy. `act(view)` returns an action (or None to stop), `keep_harvesting(view, bush, reward)` is asked after
    every fruit but the last, and `choose_between(view, candidates, rng)` picks one of a few bushes (used by the
    Interlude evaluation). The default leaves a bush only when it is empty."""

    choice = Argmax()

    def begin(self, task, rng):
        self.task = task
        self.rng = rng

    def act(self, view):
        raise NotImplementedError

    def keep_harvesting(self, view, bush, reward):
        return True

    def choose_between(self, view, candidates, rng):
        """Index into `candidates` of the bush the actor prefers, from the critic's value (ties broken at random)."""
        u = utility_value(view)[np.asarray(candidates)]
        return self.choice.pick(u, rng, random_ties=True)


class UtilityActor(Actor):
    """Pick the known, unharvested bush with the best utility and harvest it until it is empty.

    `utility` is one of UTILITIES (or a function of the view); `max_walk_time` limits the candidates to bushes within that
    many seconds of walking (falling back to the quickest-to-reach bush when none is, so the agent keeps moving); `choice`
    is the ChoiceRule. With utility "nearest" and Argmax this is the nearest-bush forager."""

    def __init__(self, utility="value", max_walk_time=None, choice=None):
        self.utility = UTILITIES[utility] if isinstance(utility, str) else utility
        self.max_walk_time = max_walk_time
        if choice is not None:
            self.choice = choice

    def act(self, view):
        t = view.travel_times()
        if not np.isfinite(t).any():
            return None
        u = np.asarray(self.utility(view), dtype=float)
        if self.max_walk_time is not None:
            in_range = t <= self.max_walk_time
            if not in_range.any():
                return Harvest(int(t.argmin()))
            u = np.where(in_range, u, -np.inf)
        else:
            u = np.where(np.isfinite(t), u, -np.inf)
        j = self.choice.pick(u, self.rng)
        return None if j is None else Harvest(j)

    def choose_between(self, view, candidates, rng):
        u = np.asarray(self.utility(view), dtype=float)[np.asarray(candidates)]
        return self.choice.pick(u, rng, random_ties=True)


class PlannerActor(Actor):
    """Plans one route over the bushes in memory, then follows it. The objective is expected reward: the sum over the route of
    (the critic's mean per fruit * fruits taken), with whole-bush harvesting (no early leaving) and no reward noise. The last
    bush may be partly harvested if the clock runs out. Walking is simulated exactly as the engine does it (straight line to
    the edge of the target's harvest range, position tracked), so the plan's value equals what the engine pays when rewards
    equal the critic's values.

    The plan is made at the first decision and made again only when the map in memory or the critic has changed since (a
    full-knowledge oracle therefore plans once); a re-plan starts from the current position and time and treats bushes that
    are partly harvested or spent as gone.

    method="exact": depth-first branch-and-bound, pruned by a fractional-knapsack upper bound and started from a
        beam-search incumbent. Optimal for this objective unless `max_nodes` is hit (then `self.exact` is False
        and the result is the best route found).
    method="beam":  beam search keeping the `beam_width` best partial routes per depth. Fast, near-optimal, no proof.

    After planning: `plan` (bush ids in visiting order), `plan_value` (expected reward), `exact` (proven optimal),
    `nodes` (search nodes expanded, summed over plans).
    """

    def __init__(self, method="exact", beam_width=300, max_nodes=2_000_000, incumbent_width=150):
        if method not in ("exact", "beam"):
            raise ValueError(f"unknown method '{method}'")
        self.method = method
        self.beam_width = beam_width
        self.max_nodes = max_nodes
        self.incumbent_width = incumbent_width

    def begin(self, task, rng):
        super().begin(task, rng)
        self.nodes = 0
        self.exact = False
        self.plan = []
        self.plan_value = 0.0
        self._next = 0
        self._planned_at = None

    def act(self, view):
        key = (view.memory.map_version, view.critic.version)
        if self._planned_at != key:
            self._make_plan(view)
            self._planned_at = key
        if self._next >= len(self.plan):
            return Stop()
        j = self.plan[self._next]
        self._next += 1
        return Harvest(j)

    # ---- planning ------------------------------------------------------------------------------

    def _make_plan(self, view):
        m = view.memory
        task = self.task
        mean, _ = view.values()
        self._ids = np.flatnonzero(m.known & ~m.depleted & (m.taken == 0))
        self.F = task.fruit_count
        self.fd = task.fruit_duration
        self.T = task.session_duration
        self.P = m.pos[self._ids]
        self.reach = view.reach()[self._ids]
        self.value = mean[self._ids]
        self.speed = task.speed
        self.start = np.array(view.state.pos, dtype=float)
        self.t0 = view.time_elapsed
        if len(self._ids) == 0:
            self.plan, self.plan_value, self.exact = [], 0.0, True
            self._next = 0
            return
        self._prepare_bound()
        if self.method == "beam":
            plan, self.plan_value = self._beam(self.beam_width)
            self.plan = [int(self._ids[j]) for j in plan]
        else:
            plan, value = self._beam(self.incumbent_width)
            plan, self.plan_value, self.exact = self._branch_and_bound(plan, value)
            self.plan = [int(self._ids[j]) for j in plan]
        self._next = 0

    # ---- shared primitives (same arithmetic as sim.run_episode) -----------------------------------

    def _step_all(self, pos, t, visited):
        """For every bush: (walk time, harvestable fruits k, new time) from `pos` at time `t`. k == 0 where
        the bush is visited, or cannot be reached with time for one fruit."""
        dist = np.hypot(self.P[:, 0] - pos[0], self.P[:, 1] - pos[1])
        walk = np.maximum(0.0, dist - self.reach)
        arrive = t + walk / self.speed
        k = np.minimum(self.F, np.floor((self.T - arrive) / self.fd + 1e-9)).astype(int)
        k[visited] = 0
        k = np.maximum(k, 0)
        return dist, walk, arrive, k

    def _move(self, pos, dist, walk, j):
        if walk[j] > 0.0:
            return pos + (self.P[j] - pos) / dist[j] * walk[j]
        return pos

    # ---- upper bound: fractional knapsack over unvisited bushes ---------------------------------

    def _prepare_bound(self):
        n = len(self.P)
        pts = np.vstack([self.P, self.start[None, :]])
        d = pts[:, None, :] - pts[None, :, :]
        D = np.sqrt((d ** 2).sum(-1))              # (n+1, n+1) center distances; row/column n is the start
        # cheapest possible walk into each bush from any other bush's stop or from the start (lower bound)
        into = np.maximum(0.0, D[:n, :n] - self.reach[:, None] - self.reach[None, :]) / self.speed
        np.fill_diagonal(into, np.inf)
        from_start = np.maximum(0.0, D[n, :n] - self.reach) / self.speed
        m = np.minimum(into.min(axis=0), from_start)
        cost = self.F * self.fd + m
        val = self.value * self.F
        order = np.argsort(-(val / cost))
        self._order = order
        self._rank = np.empty(n, dtype=int)
        self._rank[order] = np.arange(n)
        self._cost_s = cost[order]
        self._val_s = val[order]

    def _bound(self, visited_sorted, remaining):
        """Upper bound on additional reward from `remaining` seconds, given visited flags in bound order."""
        free = ~visited_sorted
        cs = np.cumsum(self._cost_s * free)
        cv = np.cumsum(self._val_s * free)
        k = int(np.searchsorted(cs, remaining, side="right"))
        total = cv[k - 1] if k > 0 else 0.0
        if k < len(cs):
            prev = cs[k - 1] if k > 0 else 0.0
            total += self._val_s[k] * (remaining - prev) / self._cost_s[k]
        return float(total)

    # ---- beam search ------------------------------------------------------------------------------

    def _beam(self, width):
        n = len(self.P)
        # state: (score, reward, t, pos, last, visited bool array, plan list)
        start_vis = np.zeros(n, dtype=bool)
        beam = [(0.0, 0.0, self.t0, self.start.copy(), -1, start_vis, [])]
        best_reward, best_plan = 0.0, []
        while beam:
            children = {}
            for _, reward, t, pos, last, visited, plan in beam:
                dist, walk, arrive, k = self._step_all(pos, t, visited)
                for j in np.flatnonzero(k > 0):
                    new_reward = reward + self.value[j] * k[j]
                    t_new = arrive[j] + k[j] * self.fd
                    vis = visited.copy()
                    vis[j] = True
                    new_plan = plan + [int(j)]
                    if new_reward > best_reward + 1e-12:
                        best_reward, best_plan = new_reward, new_plan
                    if k[j] < self.F:
                        continue            # partly harvested: clock is out, nothing follows
                    self.nodes += 1
                    score = new_reward + self._bound(vis[self._order], self.T - t_new)
                    key = (j, vis.tobytes())
                    old = children.get(key)
                    if old is None or t_new < old[2]:
                        children[key] = (score, new_reward, t_new, self._move(pos, dist, walk, j), j, vis, new_plan)
            beam = sorted(children.values(), key=lambda s: -s[0])[:width]
        return best_plan, best_reward

    # ---- branch and bound -------------------------------------------------------------------------

    def _branch_and_bound(self, incumbent_plan, incumbent_value):
        n = len(self.P)
        best = {"value": incumbent_value, "plan": list(incumbent_plan)}
        visited = np.zeros(n, dtype=bool)
        capped = {"hit": False}

        def recurse(pos, t, reward, plan):
            if capped["hit"]:
                return
            self.nodes += 1
            if self.nodes > self.max_nodes:
                capped["hit"] = True
                return
            if reward > best["value"] + 1e-12:
                best["value"], best["plan"] = reward, list(plan)
            bound = reward + self._bound(visited[self._order], self.T - t)
            if bound <= best["value"] + 1e-9:
                return
            dist, walk, arrive, k = self._step_all(pos, t, visited)
            cand = np.flatnonzero(k > 0)
            if len(cand) == 0:
                return
            gain = self.value[cand] * k[cand]
            rate = gain / (arrive[cand] - t + k[cand] * self.fd)
            for idx in np.argsort(-rate):
                j = int(cand[idx])
                new_reward = reward + gain[idx]
                if k[j] < self.F:
                    if new_reward > best["value"] + 1e-12:
                        best["value"], best["plan"] = new_reward, plan + [j]
                    continue
                visited[j] = True
                plan.append(j)
                recurse(self._move(pos, dist, walk, j), arrive[j] + k[j] * self.fd, new_reward, plan)
                plan.pop()
                visited[j] = False

        recurse(self.start.copy(), self.t0, 0.0, [])
        return best["plan"], best["value"], not capped["hit"]


# --------------------------------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------------------------------

class ComposedAgent:
    """Actor + critic + memory (+ an optional percept override), the protocol sim.run_episode drives. Attributes the agent does not define
    (for the planner: `plan`, `plan_value`, `exact`, `nodes`) are read from the actor."""

    def __init__(self, actor, critic, memory, percept=None):
        self.actor, self.critic, self.memory, self.percept = actor, critic, memory, percept

    def __getattr__(self, name):
        if name in ("actor", "critic", "memory", "percept"):
            raise AttributeError(name)
        return getattr(self.actor, name)

    def begin_session(self, world, rng):
        self.world, self.rng = world, rng
        self.task = Task(world)
        self.memory.begin(world)
        self.critic.begin(world)
        self.actor.begin(self.task, rng)
        self.critic.update(self.memory)

    def view(self, state):
        return View(state, self.memory, self.critic, self.task)

    def observe(self, obs):
        self.memory.observe(obs)

    def record_reward(self, bush, reward):
        self.memory.record_reward(bush, reward)
        self.critic.update(self.memory)

    def mark_depleted(self, bush):
        self.memory.mark_depleted(bush)

    def act(self, state):
        return self.actor.act(self.view(state))

    def keep_harvesting(self, state, bush, reward):
        return self.actor.keep_harvesting(self.view(state), bush, reward)

    def end_session(self, result):
        pass


def oracle_agent(actor, percept=None):
    """An actor with full knowledge: the oracle critic and a map preloaded with every bush."""
    return ComposedAgent(actor, OracleCritic(), FullKnowledge(), percept)


def NearestAgent():
    """Walk to the bush that is quickest to reach, harvest it until exhausted, repeat. "Closest" is by walking time to the
    edge of the bush's harvest range (so a wide canopy counts as nearer than its center distance suggests). Ignores bush
    value entirely."""
    return oracle_agent(UtilityActor("nearest"))


def GreedyAgent(max_walk_time=10.0, score="value"):
    """Full-information, one-step greedy: among bushes reachable within `max_walk_time` seconds of walking, go to the best
    one, harvest it until exhausted, repeat. No path planning. score="value": highest expected reward remaining on the bush
    (critic mean * fruits left); score="rate": highest expected reward remaining per second of (walk + harvest) time. If
    nothing is within range, falls back to the quickest-to-reach bush so the agent keeps moving."""
    if score not in ("value", "rate"):
        raise ValueError(f"unknown score '{score}'")
    return oracle_agent(UtilityActor(score, max_walk_time))


def PlannerAgent(method="exact", **kwargs):
    """Full information and the whole map: plans one route for the session at the start, then follows it (see PlannerActor)."""
    return oracle_agent(PlannerActor(method, **kwargs))


REGISTRY["nearest"] = NearestAgent
for _score in ("value", "rate"):
    for _t in (5, 10, 15, 20, 30):
        REGISTRY[f"greedy_{_score}_{_t}"] = (lambda t, s: lambda: GreedyAgent(t, s))(_t, _score)
REGISTRY["plan_exact"] = lambda: PlannerAgent("exact")
REGISTRY["plan_beam"] = lambda: PlannerAgent("beam")
