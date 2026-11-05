"""Show a simulated agent what one participant did in one session, and let it learn from it.

The agents' protocol (`agents.ComposedAgent`: `observe`, `record_reward`, `mark_depleted`, `end_visit`) already separates learning from
acting: `sim.run_episode` calls it because the actor chose something, and this module calls it because the participant did. The
participant's logged trajectory is stepped through on a grid; at each step the agent is shown the bushes its sensor would see from the
participant's pose, and each logged fruit, bout end and exhaustion is passed on as the game's own events. The actor is never asked for
anything, so the result is what a critic and a memory learn from that participant's experience (the actor matters only afterwards, in
the Interlude).

    fed = replay_into_agent(agent, log)            # log from replay.load_session_log; fed.agent is the agent after the session
    check = compare_with_visibility(log, dt=0.1)   # does the agent's sensor see what the participant saw?

The sensor is `perception.OccludedConePercept` with the participant's own field of view (the logged camera and display aspect), whose
geometry is the one `visibility.py` uses to reconstruct what a participant saw; it models the horizontal field of view only, while
`visibility.py` also has the pitch, so the two differ a little where the participant looked up or down (`compare_with_visibility`
measures how much). A harvested bush the sensor missed is shown to the agent anyway (the participant was at it) and counted in
`Fed.unseen_harvests`.

    ./venv/bin/python scripts/human_agents.py <session folder or id> [--agent learner] [--dt 0.1] [--fast]

Checked so far: `fast` on every finished session of every participant (the replayed total equals the logged score). The full replay
only on one S1 session (score matched, sensor overlap 0.986 with visibility.py; no harvest at an unseen bush). TODO: check the full
replay on all sessions (the skipped test in test_human_agents.py) when the choice-set or memory analyses need it.
"""

import argparse
import json
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np

import agents
import perception
import rundata
import replay
import visibility
import world as worldmod
from agents import Body, WorldKnowledge
from perception import Observation

CAMERA_ASPECT = 16.0 / 9.0      # when the session row did not log a display size


def _value(v):
    """A logged config value as the Python parameter holds it: a Vector2 (x, y) becomes a tuple."""
    if isinstance(v, dict) and set(v) == {"x", "y"}:
        return (v["x"], v["y"])
    return v


def session_params(log):
    """The session's parameters as the simulator reads them: the asset of the same name, with every simple value the participant's
    build logged (`session.json` config) written over it, so a later edit of the asset does not change what is replayed."""
    params = worldmod.load_session(log.name)
    for key, value in log.config.items():
        field_name = worldmod._snake(key)
        if hasattr(params, field_name) and isinstance(_value(value), (int, float, bool, tuple)):
            setattr(params, field_name, _value(value))
    return params


class _Terrain:
    """The elevation grid of a logged world file, where `World.terrain` would rebuild it from the seed (the percept reads only the grids)."""

    def __init__(self, grids):
        self._grids = grids

    def grids(self):
        return self._grids


def session_world(log):
    """A `world.World` of the session the participant played: bushes, attributes and per-fruit rewards from the world file (found by
    the sha256 in the session row), terrain from its grids, the start where the trajectory begins."""
    row = log.manifest
    header, grids = worldmod.read_unity_world(replay.find_world_file(row["world_file"], row["world_sha256"],
                                                                     log.folder.resolve().parent.parent / "_worlds"))
    n, fruits = int(header["treeCount"]), int(header["fruitCount"])
    w = worldmod.World(params=session_params(log), seed=int(header["seed"]), pos=np.asarray(header["treePos"], dtype=float).reshape(n, 2),
                       shape=np.asarray(header["shape"], dtype=float), color=np.asarray(header["color"], dtype=float),
                       moisture=np.asarray(header["moisture"], dtype=float), canopy_radius=np.asarray(header["canopyRadius"], dtype=float),
                       value=np.asarray(header["value"], dtype=float),
                       fruit_reward=np.asarray(header["fruitRewards"], dtype=int).reshape(n, fruits), start=np.asarray(log.traj[0, 1:3]))
    w._terrain = _Terrain(grids)
    return w


def participant_percept(log):
    """The occluded view cone with the participant's own horizontal field of view (logged camera and display aspect)."""
    display = log.manifest.get("display", {})
    aspect = display["width"] / display["height"] if display.get("width") and display.get("height") else CAMERA_ASPECT
    return perception.OccludedConePercept(perception.horizontal_fov(log.manifest["camera"]["fieldOfView"], aspect), 1000.0)


@dataclass
class Fed:
    agent: object
    world: object
    n_steps: int
    n_fruits: int
    total: float                                        # the participant's reward over the session, from the logged fruit events
    unseen_harvests: list = field(default_factory=list)  # (t, bush) of each harvest at a bush the sensor had not shown the agent yet


def _one(world, j):
    """An Observation of bush j alone (not spent)."""
    return Observation(np.array([j]), world.pos[[j]], world.canopy_radius[[j]],
                       np.column_stack([world.shape[[j]], world.color[[j]], world.moisture[[j]]]), np.zeros(1, dtype=bool))


def replay_into_agent(agent, log, world=None, percept=None, dt=0.1, seed=0, fast=False):
    """Begin a session for `agent` in the participant's world and feed it what the participant did. Returns a `Fed`; the agent is
    changed in place. `percept` defaults to `participant_percept(log)` (the agent's own, if it has one, is used instead).

    `fast=True` skips the trajectory: the agent is shown each bush only when the participant first takes fruit from it, so it knows
    just the bushes that were harvested. A critic that learns only from harvested bushes (everything built so far) ends exactly as
    after the full replay (`test_human_agents.py` checks it), in a fraction of the time; an actor or memory that depends on
    what else was in view, or on the sensor, needs the full replay."""
    world = world or session_world(log)
    percept = agent.percept or percept or participant_percept(log)
    agent.begin_session(world, np.random.default_rng(seed))
    grid = {"t": []} if fast else replay.steps(log, dt)
    events = [e for e in log.events if e["type"] in ("fruit", "harvest_release")]
    fruits = world.fruit_count
    depleted = np.zeros(world.n, dtype=bool)
    in_bout = {}                                        # bush -> fruits taken in the open bout
    out = Fed(agent, world, len(grid["t"]), 0, 0.0)
    nxt = 0

    def feed(e):
        nonlocal nxt
        j = int(e["tree_id"])
        if e["type"] == "fruit":
            if not agent.active_memory.known[j]:
                if not fast:
                    out.unseen_harvests.append((e["t"], j))
                agent.observe(_one(world, j))
            agent.record_reward(j, e["reward"])
            in_bout[j] = in_bout.get(j, 0) + 1
            out.n_fruits += 1
            out.total += e["reward"]
            if int(e["k"]) + 1 >= fruits:
                depleted[j] = True
                agent.mark_depleted(j)
        elif in_bout.pop(j, 0):
            agent.end_visit(j)

    for i, t in enumerate(grid["t"]):
        if percept.observes:
            agent.observe(percept.observe(world, np.array([grid["x"][i], grid["z"][i]]), float(grid["yaw"][i]), depleted))
        t_next = grid["t"][i + 1] if i + 1 < len(grid["t"]) else np.inf
        while nxt < len(events) and events[nxt]["t"] < t_next:
            feed(events[nxt])
            nxt += 1
    while nxt < len(events):                            # (all of them when fast; the rest after the last step otherwise)
        feed(events[nxt])
        nxt += 1
    for j in list(in_bout):                             # a bout still open when the trajectory ends (the session's last frames)
        agent.end_visit(j)
    return out


def compare_with_visibility(log, world=None, percept=None, dt=0.1):
    """How far the agent's sensor agrees with `visibility.py` on the participant's poses: per step the bushes each says are in view.
    Returns the mean Jaccard overlap over the steps where either sees something, the share of the participant's visible bushes that the
    sensor also sees (`recall`) and the share of the sensor's bushes the participant also saw (`precision`), and the number of steps."""
    world = world or session_world(log)
    percept = percept or participant_percept(log)
    vis = visibility.visible_bushes(log, dt=dt)
    grid = replay.steps(log, dt)
    n = min(len(grid["t"]), len(vis.t))
    depleted = np.zeros(world.n, dtype=bool)
    jaccard, hit, seen_by_participant, seen_by_agent = [], 0, 0, 0
    for i in range(n):
        mine = set(percept.observe(world, np.array([grid["x"][i], grid["z"][i]]), float(grid["yaw"][i]), depleted).ids.tolist())
        theirs = set(vis.at(i)["tree_id"].tolist())
        if mine or theirs:
            jaccard.append(len(mine & theirs) / len(mine | theirs))
        hit += len(mine & theirs)
        seen_by_participant += len(theirs)
        seen_by_agent += len(mine)
    return {"steps": n, "jaccard": float(np.mean(jaccard)) if jaccard else float("nan"),
            "recall": hit / seen_by_participant if seen_by_participant else float("nan"),
            "precision": hit / seen_by_agent if seen_by_agent else float("nan")}


# --------------------------------------------------------------------------------------------------
# The Interlude that follows a session
# --------------------------------------------------------------------------------------------------

def interlude_folder(folder):
    """The folder of the Interlude that follows the session in `folder` (the next session index of the same run)."""
    folder = Path(folder)
    return folder.with_name(f"{int(folder.name) + 1:02d}")


def interlude_trials(folder):
    """(trials, sidecar) of the Interlude in `folder`: the participant's logged trials in the order shown (their choice, side, response)
    and the Interlude's bush table with each trial's stage (`interlude.py`'s file, found by its sha256 in the session row)."""
    folder = Path(folder)
    data = rundata.read_session(folder)
    row = data["session"]
    if not row.get("is_interlude") or not data["trials"]:
        raise ValueError(f"{folder} is not an Interlude with logged trials")
    path = replay.find_world_file(row["interlude_file"], row["interlude_sha256"], folder.resolve().parent.parent / "_worlds")
    return sorted(data["trials"], key=lambda t: t["presented_order"]), json.loads(path.read_text())


def interlude_comparison(agent, folder, seed=0):
    """Put `agent` (which has just learned from the participant's session) through the participant's own Interlude, trial by trial in
    the order they saw them, and set its pick beside theirs. As in `sim.evaluate_interlude` the critic is frozen, a fresh memory holds
    the two bushes of the trial, and the pick is the actor's greedy choice by its own utility. One row per trial: the trial's type, the
    side the participant chose (None if the trial timed out), the agent's pick, whether each was right, the two bushes' ids, attributes and
    critic values (`ids`, `attrs`, `mean`: left then right), `margin` (the critic's value of the
    left bush minus the right, per fruit, so its sign is the agent's preference and its size the strength) and the true values."""
    trials, sidecar = interlude_trials(folder)
    knowledge = WorldKnowledge.from_sidecar(sidecar)
    agent.begin_interlude(knowledge)
    rng = np.random.default_rng(seed)
    rows = []
    for t in trials:
        stage = sidecar["trials"][t["trial_index"]]
        ids = np.array([stage["left"]["id"], stage["right"]["id"]])
        agent.observe(Observation(ids, knowledge.pos[ids], knowledge.radius[ids], knowledge.attrs[ids], np.zeros(2, dtype=bool)))
        body = Body(np.array(stage["start"], dtype=float), stage["yaw"], agent.task.session_duration, 0.0)
        pick = ("left", "right")[int(agent.choose_between(body, ids, rng))]
        mean = agent.view(body).values()[0][ids]
        correct = stage["correct"]
        mine = t["choice"] if t["choice"] in ("left", "right") and not t["timed_out"] else None
        rows.append({"order": t["presented_order"], "trial": t["trial_index"], "type": t["type"], "correct_side": correct,
                     "ids": ids.tolist(), "attrs": knowledge.attrs[ids].tolist(), "mean": mean.tolist(),
                     "participant": mine, "participant_correct": None if mine is None else correct in (mine, "either"),
                     "agent": pick, "agent_correct": correct in (pick, "either"), "margin": float(mean[0] - mean[1]),
                     "value_left": stage["left"]["value"], "value_right": stage["right"]["value"]})
    return rows


def summarize_interlude(rows):
    """Accuracy of the participant and the agent over the trials the participant answered, and how often they picked the same side
    (overall, and where the participant was right or wrong: an agent that has learned what they learned agrees with them even when they err)."""
    answered = [r for r in rows if r["participant"] is not None]
    same = [r["participant"] == r["agent"] for r in answered]
    wrong = [r["participant"] == r["agent"] for r in answered if not r["participant_correct"]]
    right = [r["participant"] == r["agent"] for r in answered if r["participant_correct"]]
    mean = lambda v: float(np.mean(v)) if len(v) else float("nan")
    return {"trials": len(rows), "answered": len(answered), "participant_accuracy": mean([r["participant_correct"] for r in answered]),
            "agent_accuracy": mean([r["agent_correct"] for r in answered]), "agreement": mean(same),
            "agreement_when_participant_right": mean(right), "agreement_when_participant_wrong": mean(wrong)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Feed a participant's session to an agent and report what it saw and learned.")
    ap.add_argument("session", help="a session folder, or an id under ForagingData/")
    ap.add_argument("--agent", default="learner", help="registry name of the agent (default learner)")
    ap.add_argument("--dt", type=float, default=0.1)
    ap.add_argument("--interlude", action="store_true", help="then put the agent through the participant's Interlude and compare picks")
    ap.add_argument("--fast", action="store_true", help="feed only the harvest events (see replay_into_agent)")
    args = ap.parse_args(argv)
    log = replay.load_session_log(args.session)
    world = session_world(log)
    fed = replay_into_agent(agents.REGISTRY[args.agent](), log, world=world, dt=args.dt, fast=args.fast)
    mem = fed.agent.memory
    print(f"{log.name}: {fed.n_steps} steps, {fed.n_fruits} fruits, participant total {fed.total:g} "
          f"(logged final score {log.final_score}); agent knows {int(mem.known.sum())} of {world.n} bushes, "
          f"took fruit from {int((mem.taken > 0).sum())}, {len(fed.unseen_harvests)} harvest(s) at a bush its sensor had not shown it")
    if args.interlude:
        print(summarize_interlude(interlude_comparison(fed.agent, interlude_folder(log.folder))))
    if args.fast:
        return
    c = compare_with_visibility(log, world=world, dt=args.dt)
    print(f"sensor against visibility.py over {c['steps']} steps: overlap {c['jaccard']:.3f}, recall {c['recall']:.3f}, precision {c['precision']:.3f}")


if __name__ == "__main__":
    main()
