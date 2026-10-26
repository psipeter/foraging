"""The assessment battery: one fixed way to run an agent through every session and its Interlude, so agents are comparable.

(Called a battery, as in psychology, because "test suite" already means the pytest files here.)

    ./venv/bin/python scripts/battery.py run --population main --tag first-battery [--seeds 0-9] [--agents a,b,...] [--db PATH]
    ./venv/bin/python scripts/battery.py list
    ./venv/bin/python scripts/battery.py scores --tag first-battery --population main
    ./venv/bin/python scripts/battery.py plot --tag first-battery --population main [--kinds reward,advantage,interlude]

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

import numpy as np

import analysis
import results
from agents import (REGISTRY, ComposedAgent, ConstantPrior, DeltaRuleCritic, FullKnowledge, FullMemory, NeutralPrior, OracleCritic, RBFFeatures,
                    Softmax, UtilityActor)
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
    # the same battery with longer sessions (PI): more time to exploit what has been learned
    "long": Battery("long", {"S1": 120, "S2": 120, "S3": 180, "S4": 180}, (0.0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0)),
}
DEFAULT_BATTERY = "long"      # the battery every command uses unless `--battery` names another; `standard` stays for the records made with it


# --------------------------------------------------------------------------------------------------
# Populations of agents (names are labels; an agent's identity is the hash of its spec)
# --------------------------------------------------------------------------------------------------

def _agent(critic, choice=None, whole_map=False):
    """The standard actor (rate, 15 s) with `critic` "oracle" (true values) or "learner" (delta rule on RBF features), a `choice` rule, and
    the map from the view cone unless `whole_map`."""
    memory = FullKnowledge() if whole_map else FullMemory()
    return ComposedAgent(UtilityActor(choice=choice), DeltaRuleCritic() if critic == "learner" else OracleCritic(), memory)


def main_population():
    """The standard agents: the floor, the oracle and the learner, all with the standard actor (rate utility within 15 s) and the view cone.
    (The window x utility grid and the cone-against-whole-map check were run first: docs/DECISIONS.md, "One actor default".)"""
    return {"nearest": REGISTRY["nearest"], "oracle": REGISTRY["oracle"], "learner": REGISTRY["learner"]}


def _scan(label, values, make):
    """A population of the floor, the oracle (the ceiling) and learners that differ in one parameter: `make(value)` is the learner's critic."""
    pop = {"nearest": REGISTRY["nearest"], "oracle": REGISTRY["oracle"]}
    for value in values:
        pop[f"learner_{label}{value:g}"] = lambda v=value: ComposedAgent(UtilityActor(), make(v), FullMemory())
    return pop


def scan_alpha_population():
    """The delta-rule learning rate (the standard learner has 0.5)."""
    return _scan("alpha", (0.1, 0.3, 0.5, 0.8), lambda v: DeltaRuleCritic(alpha=v))


def scan_length_population():
    """The RBF width in attribute units (the standard learner has 0.3)."""
    return _scan("len", (0.1, 0.3, 0.5, 0.7), lambda v: DeltaRuleCritic(features=RBFFeatures(length_scale=v)))


def scan_gain_population():
    """A gain on the learned deviation at read-out (the standard learner has 1): does a larger spread of values, with the same ranking, help?"""
    return _scan("gain", (1, 2, 4, 8), lambda v: DeltaRuleCritic(gain=v))


def scan_window_population():
    """The learner's walking window: the standard 15 s (ring 5 of bushes) against 60 s (past any hop in the valley: effectively no window)."""
    pop = {"nearest": REGISTRY["nearest"], "oracle": REGISTRY["oracle"]}
    for window in (15.0, 60.0):
        pop[f"learner_window{window:g}"] = lambda w=window: ComposedAgent(UtilityActor(max_walk_time=w), DeltaRuleCritic(), FullMemory())
    return pop


def scan_prior_population():
    """The learner's baseline: the standard fixed 0.1 (`learner`) against the running mean of the bush means and larger fixed baselines (1, 2: they
    act as an optimism bonus, which belongs to the actor)."""
    pop = {"nearest": REGISTRY["nearest"], "oracle": REGISTRY["oracle"], "learner": REGISTRY["learner"],
           "learner_meanprior": lambda: ComposedAgent(UtilityActor(), DeltaRuleCritic(prior=NeutralPrior()), FullMemory())}
    for level in (1.0, 2.0):
        pop[f"learner_prior{level:g}"] = lambda v=level: ComposedAgent(UtilityActor(), DeltaRuleCritic(prior=ConstantPrior(v)), FullMemory())
    return pop


def scan_centers_population():
    """The number of RBF centers per attribute (the standard learner has 8)."""
    return _scan("centers", (4, 8, 12, 16), lambda v: DeltaRuleCritic(features=RBFFeatures(n_centers=v)))


def choice_noise_population():
    """The oracle and the learner with a softmax choice rule at two temperatures, against the floor (to be investigated)."""
    pop = {"nearest": REGISTRY["nearest"], "oracle": REGISTRY["oracle"], "learner": REGISTRY["learner"]}
    for critic in ("oracle", "learner"):
        for temperature in (0.3, 1.0):
            pop[f"{critic}_softmax{temperature:g}"] = lambda c=critic, t=temperature: _agent(c, Softmax(t))
    return pop


def knowledge_population():
    """Cone against whole map for both critics (the check that set the cone as the default)."""
    return {"nearest": REGISTRY["nearest"], "oracle": REGISTRY["oracle"], "oracle_fullmap": lambda: _agent("oracle", whole_map=True),
            "learner": REGISTRY["learner"], "learner_fullmap": lambda: _agent("learner", whole_map=True)}


# Each population is also one figure group (5 agents or fewer to avoid the `plots.MAX_DISTINCT` warning; 8 is the palette's limit) and includes the floor, so the panels share a reference.
POPULATIONS = {"main": main_population, "scan-alpha": scan_alpha_population, "scan-length": scan_length_population,
               "scan-centers": scan_centers_population, "scan-gain": scan_gain_population, "scan-prior": scan_prior_population, "scan-window": scan_window_population, "choice-noise": choice_noise_population, "knowledge": knowledge_population}
# Agents a population records but its figures leave out: the scans compare their learners with one another, so the floor and the ceiling
# (still in the population for `scores`) would only crowd the plots.
FIGURE_OMITS = {name: ("nearest", "oracle") for name in ("scan-alpha", "scan-length", "scan-centers")}
KINDS = ("reward", "advantage", "interlude")


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


def plot_battery(store, tag, battery, population="main", kinds=KINDS, out_dir=None, mode="paper"):
    """Save one figure per kind for a population: a 2 x 2 grid of the battery's sessions, one line per agent. `kinds`: "reward" (cumulative reward so
    far), "advantage" (lead over the lowest-performing agent of each session) and "interlude" (Interlude accuracy against training time).
    Returns the paths, `<out_dir>/<tag>_<population>_<kind>.png`."""
    import plots
    out_dir = out_dir if out_dir is not None else results.DEFAULT_PATH.parent
    members = {name: factory for name, factory in POPULATIONS[population]().items() if name not in FIGURE_OMITS.get(population, ())}
    names = {factory().spec_hash(): name for name, factory in members.items()}
    specs_of = [factory().spec() for factory in members.values()]
    titles = {"reward": "cumulative reward", "advantage": "lead over the lowest-performing agent in cumulative reward",
              "interlude": "Interlude accuracy against training time"}
    paths = []
    for kind in kinds:
        panels = {}
        for session in battery.sessions:
            sel = analysis.select(store, tag=f"{tag}/{session}", kind="interlude", agents=specs_of)
            if kind == "interlude":
                panels[session] = analysis.checkpoint_curve(store, sel)
            else:
                panels[session] = analysis.cumulative_curve(store, sel, baseline="lowest" if kind == "advantage" else None)
        draw = plots.plot_learning_curve if kind == "interlude" else plots.plot_cumulative_reward
        paths.append(draw(panels, f"{out_dir}/{tag}_{population}_{kind}.png", names=names, order=list(members), title=f"{population}: {titles[kind]}", mode=mode))
    return paths


def scores(store, tag, battery, population, floor="nearest"):
    """Per agent and session numbers for a recorded population, against the `floor` agent (it must be in the population). Rows are dicts:
    session, agent, total (mean reward), lead (the paired mean difference to the floor in reward points) and lead_se, then the lead's
    split into quality and efficiency, accuracy (final Interlude accuracy), auc and t80 (speed of learning).

    Reward is fruits x reward per fruit, so with F the mean fruits taken and q = total / F (a ratio of means) the lead over the floor is
    exactly F_floor (q - q_floor)  +  (F - F_floor) q: `quality` is the first term (it picks better bushes, at the floor's pace) and
    `efficiency` the second (it takes more fruits, at its own reward per fruit). Both are in reward points and add up to `lead`.
    `auc` is the area under the chance-corrected accuracy curve over the session's normalised time (0: chance throughout, 1: perfect from
    the start; its standard error is across seeds; time is the checkpoint time over the last checkpoint's, the recorded session length) and `t80` the fraction of the session at which the mean accuracy first reaches 0.8
    (interpolated; NaN if it never does). `accuracy`, `auc` and `t80` use all of an agent's seeds, `lead` only the seeds it shares with the floor
    (the same under a complete battery). No normalisation to a ceiling is made: the oracle is just another agent in the population."""
    members = POPULATIONS[population]()
    ids = {name: factory().spec_hash() for name, factory in members.items()}
    rows = []
    for session in battery.sessions:
        sel = analysis.select(store, tag=f"{tag}/{session}", kind="interlude", agents=[f().spec() for f in members.values()])
        curves = analysis.checkpoint_curve(store, sel)
        x = np.asarray(curves.t, dtype=float) / float(curves.t[-1])     # the recorded session length, whichever battery is named
        base = sel.rows[ids[floor]]
        for name, aid in ids.items():
            seeds = sorted(set(sel.rows[aid]) & set(base))
            total = np.array([sel.rows[aid][s]["total"] for s in seeds])
            fruits = np.array([sel.rows[aid][s]["n_fruits"] for s in seeds], dtype=float)
            total0 = np.array([base[s]["total"] for s in seeds])
            fruits0 = np.array([base[s]["n_fruits"] for s in seeds], dtype=float)
            q, q0 = total.mean() / fruits.mean(), total0.mean() / fruits0.mean()
            acc = np.asarray(curves.agents[aid]["per_seed"], dtype=float)
            auc = np.trapezoid((acc - 0.5) / 0.5, x, axis=1)
            mean = acc.mean(axis=0)
            hit = np.flatnonzero(mean >= 0.8)
            if len(hit) == 0:
                t80 = float("nan")
            elif hit[0] == 0:
                t80 = float(x[0])
            else:
                k = hit[0]
                t80 = float(x[k - 1] + (0.8 - mean[k - 1]) / (mean[k] - mean[k - 1]) * (x[k] - x[k - 1]))
            diff = total - total0
            rows.append({"session": session, "agent": name, "total": float(total.mean()), "lead": float(diff.mean()),
                         "lead_se": float(diff.std(ddof=1) / np.sqrt(len(diff))) if len(diff) > 1 else float("nan"),
                         "fruits": float(fruits.mean()), "per_fruit": float(q), "quality": float(fruits0.mean() * (q - q0)),
                         "efficiency": float((fruits.mean() - fruits0.mean()) * q), "accuracy": float(acc[:, -1].mean()),
                         "auc": float(auc.mean()), "auc_se": float(auc.std(ddof=1) / np.sqrt(len(auc))), "t80": t80})
    return rows


def format_scores(rows):
    lines = []
    for session in dict.fromkeys(r["session"] for r in rows):
        lines.append(f"{session}:  {'agent':<20}{'total':>7}{'lead':>15}{'quality':>9}{'effic.':>8}{'fruits':>8}{'/fruit':>7}{'final acc':>10}{'auc':>13}{'t80':>6}")
        for r in (r for r in rows if r["session"] == session):
            lines.append(f"     {r['agent']:<20}{r['total']:>7.0f}{r['lead']:>+9.1f} ±{r['lead_se']:>4.1f}{r['quality']:>+9.1f}{r['efficiency']:>+8.1f}"
                         f"{r['fruits']:>8.1f}{r['per_fruit']:>7.2f}{r['accuracy']:>10.2f}{r['auc']:>8.2f} ±{r['auc_se']:>4.2f}{r['t80']:>6.2f}")
        lines.append("")
    return "\n".join(lines)


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
    p.add_argument("--battery", default=DEFAULT_BATTERY, choices=list(BATTERIES))
    p.add_argument("--population", default="main", choices=list(POPULATIONS))
    p.add_argument("--agents", default=None, help="comma-separated names from the population or the registry (default: the whole population)")
    p.add_argument("--tag", required=True)
    p.add_argument("--seeds", default=None, help="e.g. 0-9 (default: the battery's)")
    p.add_argument("--db", default=None)
    p = sub.add_parser("scores", help="per agent and session scores of a recorded population (reward lead, gap closed, accuracy, learning-curve area)")
    p.add_argument("--battery", default=DEFAULT_BATTERY, choices=list(BATTERIES))
    p.add_argument("--population", default="main", choices=list(POPULATIONS))
    p.add_argument("--tag", required=True)
    p.add_argument("--db", default=None)
    p = sub.add_parser("plot", help="save the 2 x 2 session figures of a recorded battery, one set per agent group")
    p.add_argument("--battery", default=DEFAULT_BATTERY, choices=list(BATTERIES))
    p.add_argument("--population", default="main", choices=list(POPULATIONS))
    p.add_argument("--tag", required=True)
    p.add_argument("--kinds", default=",".join(KINDS), help="reward, advantage, interlude")
    p.add_argument("--out", default=None, help="output directory (default results/)")
    p.add_argument("--mode", default="paper", choices=["paper", "presentation"], help="figure width and font sizes (plots.MODES)")
    p.add_argument("--db", default=None)
    args = ap.parse_args(argv)
    if args.command == "scores":
        with results.Store(args.db, readonly=True) as store:
            print(format_scores(scores(store, args.tag, BATTERIES[args.battery], args.population)))
        return
    if args.command == "plot":
        with results.Store(args.db, readonly=True) as store:
            for path in plot_battery(store, args.tag, BATTERIES[args.battery], args.population, args.kinds.split(","), args.out, args.mode):
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
