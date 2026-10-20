"""Foraging agents. All agents live in this file; add new ones with @register.

An agent is run by sim.run_episode with this protocol:

    begin_session(world, rng)      once per session; `world` is the full World (positions, attributes, values,
                                   canopy radii) and `rng` a numpy Generator seeded per world seed. Agents
                                   currently get full information; restrict what they read to model a percept.
    choose_target(state) -> id|None  pick the next bush (must not be depleted) or None to stop. `state` is
                                   sim.State: time_left, pos, depleted, fruits_taken, history, travel_times().
    keep_harvesting(state, id, reward) -> bool   called after each fruit except the last; False leaves the bush.
    end_session(result)            hook for learning across sessions.
"""

import numpy as np

REGISTRY = {}   # name -> zero-argument agent factory


def register(name):
    """Class decorator: make the agent available to the sim.py command line by `name`."""
    def deco(cls):
        REGISTRY[name] = cls
        return cls
    return deco


class Agent:
    def begin_session(self, world, rng):
        self.world = world
        self.rng = rng

    def choose_target(self, state):
        raise NotImplementedError

    def keep_harvesting(self, state, bush, reward):
        return True

    def end_session(self, result):
        pass


@register("nearest")
class NearestAgent(Agent):
    """Walk to the bush that is quickest to reach, harvest it until exhausted, repeat.

    "Closest" is by walking time from the current position to the edge of the bush's harvest range (so a
    wide canopy counts as nearer than its center distance suggests). Ignores bush value entirely.
    """

    def choose_target(self, state):
        t = state.travel_times()
        t[state.depleted] = float("inf")
        j = int(t.argmin())
        return None if t[j] == float("inf") else j


class GreedyAgent(Agent):
    """Full-information, one-step greedy: among bushes reachable within `max_walk_time` seconds of walking,
    go to the best one, harvest it until exhausted, repeat. No path planning.

    score="value": highest expected reward remaining on the bush (true R_bush * fruits left).
    score="rate":  highest expected reward remaining per second of (walk + harvest) time.
    If nothing is within range, falls back to the quickest-to-reach bush so the agent keeps moving.
    """

    def __init__(self, max_walk_time=10.0, score="value"):
        if score not in ("value", "rate"):
            raise ValueError(f"unknown score '{score}'")
        self.max_walk_time = max_walk_time
        self.score = score

    def choose_target(self, state):
        w = self.world
        t = state.travel_times()
        t[state.depleted] = float("inf")
        if not np.isfinite(t).any():
            return None
        in_range = t <= self.max_walk_time
        if not in_range.any():
            return int(t.argmin())
        left = w.fruit_count - state.fruits_taken
        expected = w.value * left
        if self.score == "rate":
            utility = expected / (t + left * w.fruit_duration)
        else:
            utility = expected
        utility = np.where(in_range, utility, -np.inf)
        return int(utility.argmax())


def _greedy(max_walk_time, score):
    return lambda: GreedyAgent(max_walk_time, score)


for _score in ("value", "rate"):
    for _t in (5, 10, 15, 20, 30):
        REGISTRY[f"greedy_{_score}_{_t}"] = _greedy(_t, _score)


class PlannerAgent(Agent):
    """Full information and the whole map: plans one route for the session at the start, then follows it.

    Objective: expected reward, sum of (true R_bush * fruits taken), with whole-bush harvesting (no early
    leaving) and no reward noise. The last bush may be partly harvested if the clock runs out. Walking is
    simulated exactly as the engine does it (straight line to the edge of the target's harvest range, position
    tracked), so the plan's value equals what the engine pays when rewards equal R_bush.

    method="exact": depth-first branch-and-bound, pruned by a fractional-knapsack upper bound and started from a
        beam-search incumbent. Optimal for this objective unless `max_nodes` is hit (then `self.exact` is False
        and the result is the best route found).
    method="beam":  beam search keeping the `beam_width` best partial routes per depth. Fast, near-optimal, no proof.

    After planning: `plan` (bush ids in visiting order), `plan_value` (expected reward), `exact` (proven optimal),
    `nodes` (search nodes expanded).
    """

    def __init__(self, method="exact", beam_width=300, max_nodes=2_000_000, incumbent_width=150):
        if method not in ("exact", "beam"):
            raise ValueError(f"unknown method '{method}'")
        self.method = method
        self.beam_width = beam_width
        self.max_nodes = max_nodes
        self.incumbent_width = incumbent_width

    # ---- planning ------------------------------------------------------------------------------

    def begin_session(self, world, rng):
        super().begin_session(world, rng)
        self.F = world.fruit_count
        self.fd = world.fruit_duration
        self.T = world.session_duration
        self.P = world.pos
        self.reach = world.reach
        self.value = world.value
        self.speed = world.move_speed
        self._prepare_bound()
        self.nodes = 0
        self.exact = False
        if self.method == "beam":
            self.plan, self.plan_value = self._beam(self.beam_width)
        else:
            plan, value = self._beam(self.incumbent_width)
            self.plan, self.plan_value, self.exact = self._branch_and_bound(plan, value)
        self._next = 0

    def choose_target(self, state):
        if self._next >= len(self.plan):
            return None
        j = self.plan[self._next]
        self._next += 1
        return j

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
        w = self.world
        n = w.n
        D = w.center_distances()
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
        n = self.world.n
        # state: (score, reward, t, pos, last, visited bool array, plan list)
        start_vis = np.zeros(n, dtype=bool)
        beam = [(0.0, 0.0, 0.0, self.world.start.copy(), -1, start_vis, [])]
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
        n = self.world.n
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

        recurse(self.world.start.copy(), 0.0, 0.0, [])
        return best["plan"], best["value"], not capped["hit"]


REGISTRY["plan_exact"] = lambda: PlannerAgent("exact")
REGISTRY["plan_beam"] = lambda: PlannerAgent("beam")
