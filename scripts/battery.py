"""The assessment battery: one fixed way to run an agent through every session and its Interlude, so agents are comparable.

(Called a battery, as in psychology, because "test suite" already means the pytest files here.)

    ./venv/bin/python scripts/battery.py run --population main --tag first-battery [--seeds 0-9] [--agents a,b,...] [--db PATH]
    ./venv/bin/python scripts/battery.py list
    ./venv/bin/python scripts/battery.py plot --tag first-battery [--groups knowledge,...] [--kinds cumulative,advantage,learning]

For each session the battery plays the agent for the session's design duration (passed as an override: the assets may carry a temporary
shorter one), then scores a copy of the agent on the session's Interlude at several times (checkpoints, as fractions of the session)
and once more at the end. Everything is an ordinary `results.record_run` (kind "interlude") under the tag `<tag>/<session>`, so reuse of
what is already recorded, the environment and code fingerprints, and every query in analysis.py work unchanged.

The Interlude is the random mode with `interlude_trial_count` trials, and each trial is answered ONCE per evaluation (n_samples 1), so the
spread between seeds has the same source as a person's: a single run of that many forced choices, not a repeated-sampling estimate.
Each agent starts fresh in every session (no carry-over). Scores and plots are not part of the battery: they are computed later from the
database (scripts/analysis.py).

Agents run in one process, session by session, so each Interlude (about a second to generate) is built once per (session, seed) and shared
by every agent through sim's cache. Agents that plan for the end of the session cannot be checkpointed and are refused.
"""

import argparse
from dataclasses import dataclass

import analysis
import results
from agents import (REGISTRY, ComposedAgent, DeltaRuleCritic, FullKnowledge, FullMemory, OracleCritic, RBFFeatures, Softmax, UtilityActor)
from world import _parse_seeds


@dataclass(frozen=True)
class Battery:
    name: str
    sessions: dict               # session name -> duration in seconds (the design duration; the assets may carry a temporary one)
    checkpoint_fractions: tuple  # fractions of each session's length at which a copy of the agent is scored on the Interlude
    seeds: tuple = tuple(range(10))
    interlude_trials: int = 50
    n_samples: int = 1           # picks per trial: one, like a participant
    interlude_mode: str = "random"

    def checkpoints(self, session):
        return [round(f * self.sessions[session], 6) for f in self.checkpoint_fractions]

    def overrides(self, session):
        return {"session_duration": self.sessions[session], "interlude_trial_count": self.interlude_trials}


BATTERIES = {
    "standard": Battery("standard", {"S1": 90, "S2": 120, "S3": 120, "S4": 150}, (0.0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0)),
}


# --------------------------------------------------------------------------------------------------
# Populations of agents (names are labels; an agent's identity is the hash of its spec)
# --------------------------------------------------------------------------------------------------

def _agent(critic, utility="rate", window=15.0, choice=None, memory=None):
    """An agent from its parts: `critic` "oracle" (with the whole map) or "learner" (delta rule on RBF features, map from the view cone)."""
    learner = critic == "learner"
    return ComposedAgent(UtilityActor(utility, window, choice), DeltaRuleCritic() if learner else OracleCritic(),
                         memory if memory is not None else (FullMemory() if learner else FullKnowledge()))


def main_population():
    """The 24 agents of the first battery: the floor, a window x utility grid on both critics, cone against whole map, learner
    parameters and choice noise. Windows are travel times to rings 2, 5 and 10 of bushes (6, 15, 30 s; bushes are 23 units apart)."""
    pop = {"nearest": REGISTRY["nearest"]}
    for critic in ("oracle", "learner"):
        for utility in ("rate", "value"):
            for window in (6.0, 15.0, 30.0):
                pop[f"{critic}_{utility}_w{window:g}"] = lambda c=critic, u=utility, w=window: _agent(c, u, w)
    pop["oracle_cone_rate_w15"] = lambda: _agent("oracle", memory=FullMemory())
    pop["learner_fullmap_rate_w15"] = lambda: _agent("learner", memory=FullKnowledge())
    for alpha in (0.2, 1.0):
        pop[f"learner_alpha{alpha:g}"] = lambda a=alpha: ComposedAgent(UtilityActor("rate", 15.0), DeltaRuleCritic(alpha=a), FullMemory())
    for length in (0.15, 0.5):
        pop[f"learner_len{length:g}"] = lambda n=length: ComposedAgent(UtilityActor("rate", 15.0), DeltaRuleCritic(features=RBFFeatures(n)), FullMemory())
    pop["learner_joint"] = lambda: ComposedAgent(UtilityActor("rate", 15.0), DeltaRuleCritic(features=RBFFeatures(0.3, 4, additive=False)), FullMemory())
    for critic in ("learner", "oracle"):
        for temperature in (0.3, 1.0):
            pop[f"{critic}_softmax{temperature:g}"] = lambda c=critic, t=temperature: _agent(c, choice=Softmax(t))
    return pop


POPULATIONS = {"main": main_population}

# Figures hold at most 8 agents (the palette), so the main population is plotted as groups that each answer one question; every group
# includes the floor so the panels share a reference.
GROUPS = {
    "grid-oracle": ["nearest"] + [f"oracle_{u}_w{w}" for u in ("rate", "value") for w in (6, 15, 30)],
    "grid-learner": ["nearest"] + [f"learner_{u}_w{w}" for u in ("rate", "value") for w in (6, 15, 30)],
    "knowledge": ["nearest", "oracle_rate_w15", "oracle_cone_rate_w15", "learner_fullmap_rate_w15", "learner_rate_w15"],
    "learner-parameters": ["nearest", "learner_rate_w15", "learner_alpha0.2", "learner_alpha1", "learner_len0.15", "learner_len0.5", "learner_joint"],
    "choice-noise": ["nearest", "oracle_rate_w15", "oracle_softmax0.3", "oracle_softmax1", "learner_rate_w15", "learner_softmax0.3", "learner_softmax1"],
}
KINDS = ("cumulative", "advantage", "learning")


def resolve(names, population=None):
    """{label: factory} for agent names: those of `population` (a name in POPULATIONS), else registry names."""
    available = dict(POPULATIONS[population]()) if population else {}
    chosen = {}
    for name in names if names else list(available):
        if name in available:
            chosen[name] = available[name]
        elif name in REGISTRY:
            chosen[name] = REGISTRY[name]
        else:
            raise KeyError(f"unknown agent '{name}'" + (f" (not in population '{population}' or the registry)" if population else " (not in the registry)"))
    return chosen


# --------------------------------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------------------------------

def run_battery(agents, battery, tag, seeds=None, store=None, progress=print):
    """Run `agents` ({label: factory}) through every session of `battery`, recording each (agent, session) under the tag
    `<tag>/<session>`. Sessions are the outer loop so each Interlude is generated once per seed and shared by all agents. Returns
    {session: [RunReport per agent]}."""
    for label, factory in agents.items():
        if getattr(getattr(factory(), "actor", None), "deadline_dependent", False):
            raise ValueError(f"agent '{label}' plans for the end of the session, so it cannot be checkpointed (see CLAUDE.md, checkpoint Interludes)")
    seeds = list(battery.seeds if seeds is None else seeds)
    if store is None:
        with results.Store() as own:
            return run_battery(agents, battery, tag, seeds, own, progress)
    reports = {}
    for session in battery.sessions:
        reports[session] = []
        for label, factory in agents.items():
            report = results.record_run(factory, session, seeds, f"{tag}/{session}", kind="interlude", n_samples=battery.n_samples,
                                        interlude_mode=battery.interlude_mode, overrides=battery.overrides(session),
                                        checkpoints=battery.checkpoints(session), store=store,
                                        note=f"battery {battery.name}; agent {label}")
            reports[session].append(report)
            if progress:
                progress(f"{session} {label}: computed {report.n_computed}, reused {report.n_reused}")
    return reports


def plot_battery(store, tag, battery, population="main", groups=None, kinds=KINDS, out_dir=None):
    """Save one figure per (group, kind): a 2 x 2 grid of the battery's sessions, one line per agent of the group. `kinds`: "cumulative"
    (reward so far), "advantage" (lead over the lowest-performing agent of each session) and "learning" (Interlude accuracy against training
    time). Returns the paths."""
    import plots
    out_dir = out_dir if out_dir is not None else results.DEFAULT_PATH.parent
    pop = POPULATIONS[population]()
    paths = []
    for group in groups or list(GROUPS):
        members = {name: pop[name] for name in GROUPS[group]}
        names = {factory().spec_hash(): name for name, factory in members.items()}
        specs_of = [factory().spec() for factory in members.values()]
        for kind in kinds:
            panels = {}
            for session in battery.sessions:
                sel = analysis.select(store, tag=f"{tag}/{session}", kind="interlude", agents=specs_of)
                if kind == "learning":
                    panels[session] = analysis.checkpoint_curve(store, sel)
                else:
                    panels[session] = analysis.cumulative_curve(store, sel, baseline="lowest" if kind == "advantage" else None)
            draw = plots.plot_learning_curve if kind == "learning" else plots.plot_cumulative_reward
            paths.append(draw(panels, f"{out_dir}/{tag}_{group}_{kind}.png", names=names, order=list(members), title=f"{group}: "
                              + {"cumulative": "cumulative reward", "advantage": "lead over the lowest-performing agent in cumulative reward",
                                 "learning": "Interlude accuracy against training time"}[kind]))
    return paths


def session_readout(store, tag, battery, aliases=None):
    """A text table per session (mean total reward, then final Interlude accuracy, per agent, with the paired difference to `nearest` when it
    is there) from what is recorded under `tag`. `aliases` maps agent ids to the names to show instead of the generated labels."""
    lines = []
    for session in battery.sessions:
        sel = analysis.select(store, tag=f"{tag}/{session}", kind="interlude")
        baseline = "nearest" if _has(sel, "nearest") else None
        for metric, title in (("total", "total reward"), ("interlude_accuracy", "Interlude accuracy at the end of the session")):
            rows = analysis.table(sel, metric, baseline)
            for row in rows:
                row["label"] = (aliases or {}).get(row["agent_id"], row["label"])
            lines.append(analysis.describe(sel, metric) if metric == "total" else "")
            lines.append(f"{session}: {title}")
            lines.append(analysis.format_table(rows))
        lines.append("")
    return "\n".join(lines)


def _has(sel, name):
    try:
        analysis.resolve_agent_in(sel, name)
        return True
    except KeyError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run agents through the assessment battery.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list batteries and populations")
    p = sub.add_parser("run", help="run a population (or named agents) through a battery and record it")
    p.add_argument("--battery", default="standard", choices=list(BATTERIES))
    p.add_argument("--population", default="main", choices=list(POPULATIONS))
    p.add_argument("--agents", default=None, help="comma-separated names from the population or the registry (default: the whole population)")
    p.add_argument("--tag", required=True)
    p.add_argument("--seeds", default=None, help="e.g. 0-9 (default: the battery's)")
    p.add_argument("--db", default=None)
    p = sub.add_parser("plot", help="save the 2 x 2 session figures of a recorded battery, one set per agent group")
    p.add_argument("--battery", default="standard", choices=list(BATTERIES))
    p.add_argument("--population", default="main", choices=list(POPULATIONS))
    p.add_argument("--tag", required=True)
    p.add_argument("--groups", default=None, help=f"comma-separated from {', '.join(GROUPS)} (default: all)")
    p.add_argument("--kinds", default=",".join(KINDS), help="cumulative, advantage, learning")
    p.add_argument("--out", default=None, help="output directory (default results/)")
    p.add_argument("--db", default=None)
    args = ap.parse_args(argv)
    if args.command == "plot":
        with results.Store(args.db, readonly=True) as store:
            for path in plot_battery(store, args.tag, BATTERIES[args.battery], args.population,
                                     [g for g in args.groups.split(",") if g] if args.groups else None, args.kinds.split(","), args.out):
                print(path)
        return
    if args.command == "list":
        for b in BATTERIES.values():
            print(f"battery {b.name}: sessions {b.sessions}, checkpoints at {b.checkpoint_fractions} of each, {len(b.seeds)} seeds, "
                  f"{b.interlude_trials} {b.interlude_mode} Interlude trials, {b.n_samples} pick per trial")
        for name, make in POPULATIONS.items():
            print(f"population {name}: {len(make())} agents: {', '.join(make())}")
        return
    battery = BATTERIES[args.battery]
    agents = resolve([a for a in args.agents.split(",") if a] if args.agents else None, args.population)
    seeds = _parse_seeds(args.seeds) if args.seeds else None
    with results.Store(args.db) as store:
        run_battery(agents, battery, args.tag, seeds, store)
        print(session_readout(store, args.tag, battery, {factory().spec_hash(): label for label, factory in agents.items()}))


if __name__ == "__main__":
    main()
