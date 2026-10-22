"""Fast foraging-session simulator and experiment runner.

No 3D and no real-time walking: a session is an event loop over decisions. An agent (agents.ComposedAgent: actor, critic,
memory) returns an action; the engine charges its time and tells the agent what it then sees:

    Harvest(j)             walk in a straight line to the edge of bush j's harvest range, then harvest it one fruit at a
                           time (fruit_harvest_duration each), asking the actor after every fruit whether to stay or leave
    Explore(bearing, d)    walk d units along a bearing (stopping at the map edge or the mountains), looking as it goes
    Look(angle)            turn the view; costs TURN_OVERHEAD + |angle| / TURN_RATE seconds (an angle of 0 is refused)
    Stop                   do nothing for the rest of the session

Every action costs time (costs.py): turning the view with the mouse (before a walk to face the way, before a harvest to bring
the bush into the harvest cone), pressing W to start walking, pressing Space to start harvesting, then the walking and the
fruits. An action that would consume no time is an error, so a session always advances.

The session clock cuts off mid-turn, mid-press, mid-walk, mid-look or mid-fruit (a fruit not finished when time runs out is not
collected). Bushes never regrow. Collisions with canopies and terrain slope are ignored. The heading is the direction of the last
walk (toward the bush at a harvest) and starts at yaw 0 (+Z), as in the game. A bush is harvested only if the agent's memory
knows it (the engine refuses an id the agent never perceived).

What the agent sees is the environment's job, not the agent's (perception.py): by default a view cone as wide as the session's
camera, observed every OBS_STEP units of walking and after every look. A run can pass its own `percept=` (a sensitivity sweep over
the sensor) and an agent may carry its own override; NullPercept sees nothing and leaves an agent to what its memory was given.

Per-fruit rewards are pre-drawn in the World (fruit_reward[bush, k]: the k-th fruit taken from that bush),
so every agent faces identical rewards on a given seed, and comparisons between agents are paired.

An Interlude is evaluated after a session (evaluate_interlude): the critic is frozen and carried over, the agent starts a fresh
memory for the Interlude's own bushes, both bushes of each trial are shown to it as observed (whatever its sensor), and the actor's
choice rule picks between them, on the very trials the game shows (interlude.generate_interlude for the same world seed).

Usage as a library:
    from sim import run_n, compare, get_worlds
    summary = run_n(lambda: MyAgent(), "S1", seeds=range(100))
    table = compare({"a": lambda: A(), "b": lambda: B()}, "S1", seeds=range(100), baseline="a")

Command line (agents are looked up in agents.REGISTRY):
    python scripts/sim.py S1 --seeds 0-99 --agents nearest,greedy_rate --set tree_spacing=30
"""

import argparse
import copy
import functools
import math
from dataclasses import dataclass, field

import numpy as np

import costs
from agents import Body, Explore, Harvest, Look, Stop, WorldKnowledge
from perception import ConePercept, NullPercept, Observation, percept_for  # noqa: F401  (re-exported)
from world import generate_world, load_session, _parse_seeds

AGENT_STREAM = 99  # SeedSequence child key for agent randomness, kept apart from the world's streams
OBS_STEP = 5.0     # world units of walking between looks
WALK_STEP = 2.0    # resolution of the map-edge / mountain check while exploring


@dataclass
class Result:
    total: float
    n_visits: int
    n_fruits: int
    walk_time: float           # includes exploring
    harvest_time: float
    idle_time: float           # time left unused at the end (agent stopped, or nothing to do)
    trace: list = field(default_factory=list)   # (bush id, fruits taken this visit, reward this visit)
    look_time: float = 0.0     # turning the view
    press_time: float = 0.0    # pressing W (to walk) and Space (to harvest)


class State:
    """Live session state, owned by the engine. Agents read it through agents.View; they never see the world's bush table."""

    def __init__(self, world):
        self.world = world
        self.time_left = world.session_duration
        self.pos = world.start.copy()
        self.heading = 0.0
        self.depleted = np.zeros(world.n, dtype=bool)
        self.fruits_taken = np.zeros(world.n, dtype=np.int64)
        self.total = 0.0
        self.history = []      # (bush id, [per-fruit rewards]) for each completed visit

    def body(self):
        """The part of the state an agent may read: a snapshot (the position is copied)."""
        return Body(self.pos.copy(), self.heading, self.time_left, self.total)


# --------------------------------------------------------------------------------------------------
# Perception (the sensor model lives in perception.py)
# --------------------------------------------------------------------------------------------------

def _resolve_percept(agent, world, percept):
    """agent.percept, else the run's `percept`, else the world's default (see perception.py)."""
    if getattr(agent, "percept", None) is not None:
        return agent.percept
    return percept if percept is not None else percept_for(world)


def _look(agent, world, s, percept):
    if percept.observes:
        agent.observe(percept.observe(world, s.pos, s.heading, s.depleted))


class _Walkable:
    """Map edge and mountains stop an exploring walk, as in the game (TerrainManager.IsWalkable). Built lazily: it needs the
    world's terrain, which a toy world does not have (then nothing blocks)."""

    def __init__(self, world):
        self.world = world
        self.terrain = None
        self.ok = None

    def __call__(self, x, z):
        if self.ok is None:
            try:
                self.terrain = self.world.terrain
                p = self.world.params
                self.half, self.threshold = float(p.world_half_extent), float(p.mountain_block_threshold)
                self.ok = True
            except AttributeError:
                self.ok = False
        if not self.ok:
            return True
        if abs(x) > self.half - 1.0 or abs(z) > self.half - 1.0:
            return False
        return float(self.terrain.mountain_ramp(x, z)) < self.threshold


# --------------------------------------------------------------------------------------------------
# One session
# --------------------------------------------------------------------------------------------------

def _spend(s, res, field, seconds):
    """Charge `seconds` to `res.<field>`. Returns False (the clock now at 0, the remainder charged) when time ran out first."""
    seconds = float(seconds)
    if seconds > s.time_left:
        setattr(res, field, getattr(res, field) + s.time_left)
        s.time_left = 0.0
        return False
    setattr(res, field, getattr(res, field) + seconds)
    s.time_left -= seconds
    return True


def _walk(agent, world, s, res, direction, distance, percept, walkable=None):
    """Turn to face `direction` (x, z), press W, then walk up to `distance` along it, looking every OBS_STEP units; stops early
    when the clock runs out or `walkable` refuses the next point. Returns False if the clock ran out."""
    heading = math.degrees(math.atan2(direction[0], direction[1]))
    if not _spend(s, res, "look_time", costs.turn_time(costs.wrap(heading - s.heading), costs.TURN_DEADBAND)):
        return False
    s.heading = heading
    if not _spend(s, res, "press_time", costs.WALK_PRESS_TIME):
        return False
    speed = world.move_speed
    done = 0.0
    while done < distance - 1e-12:
        chunk = min(OBS_STEP, distance - done)
        if chunk / speed > s.time_left:
            chunk = s.time_left * speed
            blocked_by_clock = True
        else:
            blocked_by_clock = False
        if walkable is not None:
            steps = max(1, int(math.ceil(chunk / WALK_STEP)))
            for i in range(1, steps + 1):
                f = chunk * i / steps          # s.pos already includes what was walked before this chunk
                if not walkable(s.pos[0] + direction[0] * f, s.pos[1] + direction[1] * f):
                    chunk = chunk * (i - 1) / steps
                    done = distance                      # blocked: stop after this partial chunk
                    blocked_by_clock = False             # the wall comes first: the time not walked stays on the clock
                    break
        s.pos = s.pos + np.asarray(direction) * chunk
        s.time_left -= chunk / speed
        res.walk_time += chunk / speed
        _look(agent, world, s, percept)
        if blocked_by_clock:
            s.time_left = 0.0
            return False
        done += chunk
    return True


def _harvest(agent, world, s, res, j, percept):
    """Walk to bush j and harvest it. Returns False when the session should end (clock out, or no fruit taken)."""
    if s.depleted[j]:
        raise ValueError(f"agent chose depleted bush {j}")
    speed = world.move_speed
    fd = world.fruit_duration
    F = world.fruit_count

    # Turn to face the bush, then (if it is out of range) press W and walk in a straight line to its harvest range.
    max_angle = float(getattr(world.params, "harvest_max_angle", 35.0))
    dist, walk, turn, _, walking, brg = costs.approach(s.pos, s.heading, world.pos[j][None], world.canopy_radius[j:j + 1],
                                                       world.reach[j:j + 1], speed, max_angle)
    dist, walk, turn, t_walk, brg = float(dist[0]), float(walk[0]), float(turn[0]), float(walking[0]), float(brg[0])
    delta = world.pos[j] - s.pos
    if not _spend(s, res, "look_time", turn):
        return False
    if dist > 0.0:
        s.heading = brg
    if walk > 0.0 and not _spend(s, res, "press_time", costs.WALK_PRESS_TIME):
        return False
    if t_walk > s.time_left:
        res.walk_time += s.time_left
        s.time_left = 0.0
        return False
    if walk > 0.0:
        direction = delta / dist
        if not percept.observes:
            s.pos = s.pos + direction * walk
        else:
            # Look every OBS_STEP units from the walk's start, then end at exactly start + direction * walk, so the final
            # position (and everything that follows from it) does not depend on how often the sensor is applied.
            start = s.pos.copy()
            done = 0.0
            while done < walk - 1e-12:
                done = min(done + OBS_STEP, walk)
                s.pos = start + direction * done
                _look(agent, world, s, percept)
            s.pos = start + direction * walk
    s.time_left -= t_walk
    res.walk_time += t_walk
    if not _spend(s, res, "press_time", costs.HARVEST_PRESS_TIME):
        return False

    # Harvest fruit by fruit.
    rewards = []
    while s.fruits_taken[j] < F and s.time_left >= fd - 1e-9:      # (repeated subtraction drifts by ~1e-13)
        r = float(world.fruit_reward[j, s.fruits_taken[j]])
        s.fruits_taken[j] += 1
        s.time_left = max(0.0, s.time_left - fd)
        res.harvest_time += fd
        s.total += r
        rewards.append(r)
        agent.record_reward(j, r)
        if s.fruits_taken[j] >= F:
            s.depleted[j] = True
            agent.mark_depleted(j)
            break
        if not agent.keep_harvesting(s.body(), j, r):
            break
    if s.fruits_taken[j] >= F:
        s.depleted[j] = True
    res.n_visits += 1
    res.n_fruits += len(rewards)
    res.trace.append((j, len(rewards), float(sum(rewards))))
    s.history.append((j, rewards))
    return bool(rewards)           # arrived with less than one fruit's time left: nothing more to do


def run_episode(agent, world, agent_rng=None, percept=None):
    """Run one session. Returns a Result. `percept` is the sensor for this run (see perception.py for how it is resolved)."""
    if agent_rng is None:
        agent_rng = np.random.default_rng(np.random.SeedSequence([world.seed, AGENT_STREAM]))
    agent.begin_session(world, agent_rng)
    s = State(world)
    res = Result(0.0, 0, 0, 0.0, 0.0, 0.0)
    walkable = _Walkable(world)
    percept = _resolve_percept(agent, world, percept)
    _look(agent, world, s, percept)

    memory = getattr(agent, "active_memory", None)
    while s.time_left > 0:
        action = agent.act(s.body())
        if action is None or isinstance(action, Stop):
            break
        before = s.time_left
        if isinstance(action, Harvest):
            j = int(action.bush)
            if not 0 <= j < world.n:
                raise ValueError(f"agent chose bush {j}, which does not exist ({world.n} bushes)")
            if memory is not None and not memory.known[j]:
                raise ValueError(f"agent chose bush {j}, which it has never seen or been told about")
            if not _harvest(agent, world, s, res, j, percept):
                break
        elif isinstance(action, Explore):
            if not float(action.distance) > 0.0:
                raise ValueError(f"{action!r} walks nowhere: a distance must be positive")
            rad = math.radians(action.bearing)
            if not _walk(agent, world, s, res, (math.sin(rad), math.cos(rad)), float(action.distance), percept, walkable):
                break
        elif isinstance(action, Look):
            if not abs(float(action.angle)) > 0.0:
                raise ValueError(f"{action!r} turns nowhere: an angle must be non-zero")
            if not _spend(s, res, "look_time", costs.turn_time(action.angle)):
                break
            s.heading = (s.heading + action.angle) % 360.0
            _look(agent, world, s, percept)
        else:
            raise TypeError(f"agent returned {action!r}, not an action")
        if not s.time_left < before:
            raise RuntimeError(f"{action!r} took no time (check the constants in costs.py): the session would never end")

    res.total = s.total
    res.idle_time = max(0.0, s.time_left)
    agent.end_session(res)
    return res


# --------------------------------------------------------------------------------------------------
# Interlude evaluation
# --------------------------------------------------------------------------------------------------

@dataclass
class InterludeScore:
    n_trials: int
    n_samples: int
    accuracy: float                 # mean over trials and samples of "chose the better bush" (ties count as right)
    by_type: dict                   # trial type -> accuracy
    p_left: list                    # per trial: fraction of samples that chose the left bush
    bonus: float                    # expected hidden bonus (accuracy * trials * bonus per correct; 0 in a practice Interlude)


def _freeze(value):
    """A hashable form of an override value (lists become tuples)."""
    return tuple(_freeze(v) for v in value) if isinstance(value, (list, tuple)) else value


@functools.lru_cache(maxsize=None)
def _interlude_for(session, seed, overrides):
    from interlude import generate_interlude
    sidecar, params, _ = generate_interlude(f"{session}_Interlude", seed=seed, **dict(overrides))
    return sidecar, float(params.interlude_bonus_per_correct), bool(params.is_practice)


def get_interlude(session, seed, **overrides):
    """The Interlude the game shows for this session at this world seed (the same generator and search the human files come
    from; seconds per call, so cached). `overrides` as for get_worlds. The caller gets its own copy of the sidecar, so editing
    it cannot change what later calls (or other agents) are scored on."""
    sidecar, bonus, practice = _interlude_for(session, seed, tuple(sorted((k, _freeze(v)) for k, v in overrides.items())))
    return copy.deepcopy(sidecar), bonus, practice


def evaluate_interlude(agent, sidecar, bonus_per_correct=5.0, practice=False, n_samples=200, rng=None):
    """Score an agent on an Interlude, after its session. The critic is frozen and the agent starts a fresh memory for the
    Interlude's own bushes (`ComposedAgent.begin_interlude`; an omniscient component is granted that table). At each trial the
    agent stands at the spawn point facing the pair and is shown both bushes as observed, whatever its sensor (the trials are
    built so both are in view); the actor then picks one with its own utility and choice rule, `n_samples` times from `rng`, and
    a pick is correct when it is the higher-reward bush (or the pair is a tie). No outcome is shown or learned from."""
    if rng is None:
        rng = np.random.default_rng(np.random.SeedSequence([int(sidecar["seed"]), AGENT_STREAM, 1]))
    knowledge = WorldKnowledge.from_sidecar(sidecar)
    agent.begin_interlude(knowledge)
    hits, by_type, p_left = [], {}, []
    for t in sidecar["trials"]:
        ids = np.array([t["left"]["id"], t["right"]["id"]])
        agent.observe(Observation(ids, knowledge.pos[ids], knowledge.radius[ids], knowledge.attrs[ids], np.zeros(2, dtype=bool)))
        body = Body(np.array(t["start"], dtype=float), t["yaw"], agent.task.session_duration, 0.0)
        picks = np.array([agent.choose_between(body, ids, rng) for _ in range(n_samples)])
        p_left.append(float((picks == 0).mean()))
        right = {"left": picks == 0, "right": picks == 1, "either": np.ones(n_samples, dtype=bool)}[t["correct"]]
        hits.append(right.mean())
        by_type.setdefault(t["type"], []).append(right.mean())
    acc = float(np.mean(hits)) if hits else float("nan")
    bonus = 0.0 if practice else acc * len(hits) * bonus_per_correct
    return InterludeScore(len(hits), n_samples, acc, {k: float(np.mean(v)) for k, v in by_type.items()}, p_left, bonus)


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


def run_n(agent_factory, session="S1", seeds=range(100), worlds=None, percept=None, **overrides):
    """Run `agent_factory()` (a fresh agent per seed) on one world per seed; the variance is across seeds
    (world layout, attributes and fruit noise all derive from the one seed). Pass `worlds` to reuse a list and `percept` to
    replace the sensor for the whole run (see perception.py)."""
    if worlds is None:
        worlds = get_worlds(session, seeds, **overrides)
    results = [run_episode(agent_factory(), w, percept=percept) for w in worlds]
    return Summary(np.array([r.total for r in results], dtype=float), results)


def evaluate_n(agent_factory, session="S1", seeds=range(10), n_samples=200, percept=None, **overrides):
    """For each world seed: run the session with a fresh agent, then evaluate it on that world's Interlude with the critic
    frozen. Returns (Summary of session totals, list of InterludeScore). Generating the Interludes takes seconds per seed."""
    worlds = get_worlds(session, seeds, **overrides)
    results, scores = [], []
    for seed, w in zip(seeds, worlds):
        agent = agent_factory()
        results.append(run_episode(agent, w, percept=percept))
        sidecar, bonus, practice = get_interlude(session, seed, **overrides)
        scores.append(evaluate_interlude(agent, sidecar, bonus, practice, n_samples=n_samples))
    return Summary(np.array([r.total for r in results], dtype=float), results), scores


def compare(factories, session="S1", seeds=range(100), baseline=None, percept=None, **overrides):
    """Run several agents on the same worlds (and the same sensor). Returns {name: Summary} and, if `baseline` is given, prints
    paired differences (mean, standard error) against it."""
    worlds = get_worlds(session, seeds, **overrides)
    out = {name: run_n(f, worlds=worlds, percept=percept) for name, f in factories.items()}
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
    ap.add_argument("--percept", default=None, metavar="ANGLE,DISTANCE",
                    help="replace the sensor with a view cone of this total angle (degrees) and distance, or 'none' to see "
                         "nothing (default: the world's own, as wide as the session camera)")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE",
                    help="session parameter overrides in snake_case, e.g. tree_spacing=30")
    args = ap.parse_args()
    names = [a for a in args.agents.split(",") if a]
    if not names:
        raise SystemExit("no agents registered yet (see scripts/agents.py)")
    overrides = {k: _coerce(v) for k, v in (kv.split("=") for kv in args.set)}
    percept = None
    if args.percept:
        percept = NullPercept() if args.percept == "none" else ConePercept(*[float(v) for v in args.percept.split(",")])
    compare({n: agents.REGISTRY[n] for n in names}, args.session, _parse_seeds(args.seeds),
            baseline=args.baseline or names[0], percept=percept, **overrides)


if __name__ == "__main__":
    main()
