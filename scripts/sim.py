"""Fast foraging-session simulator and experiment runner.

No 3D and no real-time walking: a session is an event loop over decisions. An agent picks a target bush;
the engine charges straight-line walking time to the edge of the bush's harvest range, then harvests it
one fruit at a time (fruit_harvest_duration each), asking the agent after every fruit whether to stay or
leave. The session clock cuts off mid-walk or mid-fruit (a fruit not finished when time runs out is not
collected). Bushes never regrow. Facing time, collisions with canopies, and terrain slope are ignored.

Per-fruit rewards are pre-drawn in the World (fruit_reward[bush, k]: the k-th fruit taken from that bush),
so every agent faces identical rewards on a given seed, and comparisons between agents are paired.

Usage as a library:
    from sim import run_n, compare, get_worlds
    summary = run_n(lambda: MyAgent(), "S1", seeds=range(100))
    table = compare({"a": lambda: A(), "b": lambda: B()}, "S1", seeds=range(100), baseline="a")

Command line (agents are looked up in agents.REGISTRY):
    python scripts/sim.py S1 --seeds 0-99 --agents nearest,greedy_rate --set tree_spacing=30
"""

import argparse
from dataclasses import dataclass, field

import numpy as np

from world import generate_world, load_session, _parse_seeds

AGENT_STREAM = 99  # SeedSequence child key for agent randomness, kept apart from the world's streams


@dataclass
class Result:
    total: float
    n_visits: int
    n_fruits: int
    walk_time: float
    harvest_time: float
    idle_time: float           # time left unused at the end (agent stopped, or nothing to do)
    trace: list = field(default_factory=list)   # (bush id, fruits taken this visit, reward this visit)


class State:
    """Live session state handed to agents. Read-only by convention; the engine mutates it."""

    def __init__(self, world):
        self.world = world
        self.time_left = world.session_duration
        self.pos = world.start.copy()
        self.depleted = np.zeros(world.n, dtype=bool)
        self.fruits_taken = np.zeros(world.n, dtype=np.int64)
        self.total = 0.0
        self.history = []      # (bush id, [per-fruit rewards]) for each completed visit

    def available(self):
        """Ids of bushes that still have fruit."""
        return np.flatnonzero(~self.depleted)

    def fruits_left(self, j):
        return self.world.fruit_count - int(self.fruits_taken[j])

    def walk_distances(self):
        """(n,) distance to walk from the current position to reach harvest range of each bush."""
        d = np.hypot(*(self.world.pos - self.pos).T)
        return np.maximum(0.0, d - self.world.reach)

    def travel_times(self):
        return self.walk_distances() / self.world.move_speed

    def travel_time(self, j):
        return float(self.travel_times()[j])


def run_episode(agent, world, agent_rng=None):
    """Run one session. Returns a Result."""
    if agent_rng is None:
        agent_rng = np.random.default_rng(np.random.SeedSequence([world.seed, AGENT_STREAM]))
    agent.begin_session(world, agent_rng)
    s = State(world)
    res = Result(0.0, 0, 0, 0.0, 0.0, 0.0)
    speed = world.move_speed
    fd = world.fruit_duration
    F = world.fruit_count

    while s.time_left > 0:
        j = agent.choose_target(s)
        if j is None:
            break
        j = int(j)
        if s.depleted[j]:
            raise ValueError(f"agent chose depleted bush {j}")

        # Walk in a straight line until the bush's harvest range is reached.
        delta = world.pos[j] - s.pos
        dist = float(np.hypot(*delta))
        walk = max(0.0, dist - world.reach[j])
        t_walk = walk / speed
        if t_walk > s.time_left:
            res.walk_time += s.time_left
            s.time_left = 0.0
            break
        if walk > 0.0:
            s.pos = s.pos + delta / dist * walk
        s.time_left -= t_walk
        res.walk_time += t_walk

        # Harvest fruit by fruit.
        rewards = []
        while s.fruits_taken[j] < F and s.time_left >= fd:
            r = float(world.fruit_reward[j, s.fruits_taken[j]])
            s.fruits_taken[j] += 1
            s.time_left -= fd
            res.harvest_time += fd
            s.total += r
            rewards.append(r)
            if s.fruits_taken[j] >= F:
                s.depleted[j] = True
                break
            if not agent.keep_harvesting(s, j, r):
                break
        if s.fruits_taken[j] >= F:
            s.depleted[j] = True
        res.n_visits += 1
        res.n_fruits += len(rewards)
        res.trace.append((j, len(rewards), float(sum(rewards))))
        s.history.append((j, rewards))
        if not rewards:
            break  # arrived with less than one fruit's time left

    res.total = s.total
    res.idle_time = max(0.0, s.time_left)
    agent.end_session(res)
    return res


# --------------------------------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------------------------------

def get_worlds(session, seeds, **overrides):
    """Generate one world per seed (reuse the returned list across agents)."""
    params = load_session(session, **overrides)
    return [generate_world(params, s) for s in seeds]


@dataclass
class Summary:
    totals: np.ndarray         # (n_seeds,) total reward per session
    results: list

    @property
    def mean(self):
        return float(self.totals.mean())

    @property
    def std(self):
        return float(self.totals.std(ddof=1)) if len(self.totals) > 1 else float("nan")

    @property
    def se(self):
        return self.std / np.sqrt(len(self.totals)) if len(self.totals) > 1 else float("nan")

    def __repr__(self):
        return f"Summary(mean={self.mean:.2f}, std={self.std:.2f}, se={self.se:.2f}, n={len(self.totals)})"


def run_n(agent_factory, session="S1", seeds=range(100), worlds=None, **overrides):
    """Run `agent_factory()` (a fresh agent per seed) on one world per seed; the variance is across seeds
    (world layout, attributes and fruit noise all derive from the one seed). Pass `worlds` to reuse a list."""
    if worlds is None:
        worlds = get_worlds(session, seeds, **overrides)
    results = [run_episode(agent_factory(), w) for w in worlds]
    return Summary(np.array([r.total for r in results], dtype=float), results)


def compare(factories, session="S1", seeds=range(100), baseline=None, **overrides):
    """Run several agents on the same worlds. Returns {name: Summary} and, if `baseline` is given, prints
    paired differences (mean, standard error) against it."""
    worlds = get_worlds(session, seeds, **overrides)
    out = {name: run_n(f, worlds=worlds) for name, f in factories.items()}
    lines = [f"{'agent':<20}{'mean':>9}{'std':>9}{'se':>8}" + (f"{'diff vs ' + baseline:>22}" if baseline else "")]
    for name, summ in out.items():
        line = f"{name:<20}{summ.mean:>9.1f}{summ.std:>9.1f}{summ.se:>8.2f}"
        if baseline and name != baseline:
            d = summ.totals - out[baseline].totals
            line += f"{d.mean():>14.1f} ± {d.std(ddof=1) / np.sqrt(len(d)):.1f}"
        lines.append(line)
    print("\n".join(lines))
    return out


def _coerce(text):
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def main():
    import agents
    ap = argparse.ArgumentParser(description="Compare foraging agents over many world seeds.")
    ap.add_argument("session")
    ap.add_argument("--seeds", default="0-99")
    ap.add_argument("--agents", default=",".join(agents.REGISTRY))
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE",
                    help="session parameter overrides in snake_case, e.g. tree_spacing=30")
    args = ap.parse_args()
    names = [a for a in args.agents.split(",") if a]
    if not names:
        raise SystemExit("no agents registered yet (see scripts/agents.py)")
    overrides = {k: _coerce(v) for k, v in (kv.split("=") for kv in args.set)}
    compare({n: agents.REGISTRY[n] for n in names}, args.session, _parse_seeds(args.seeds),
            baseline=args.baseline or names[0], **overrides)


if __name__ == "__main__":
    main()
