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
by every agent through sim's cache. A checkpoint is the agent as it stood at that time of a session of the battery's length (for an agent that
plans for the end of the session, not what a shorter session would give).
"""

import argparse
from dataclasses import dataclass

import numpy as np

import analysis
import results
from agents import (REGISTRY, AreaRestrictedActor, ComposedAgent, ConstantPrior, CuriousActor, DeltaRuleCritic, FeatureKernel, FullKnowledge, FullMemory, FullSweeps, GPAgent,
                    PosteriorActor, LearnerAgent, NeutralPrior, OracleCritic, PrioritizedReplay, RBFFeatures, RBFKernel, SampledReplay, Softmax,
                    SoftmaxActor, UtilityActor)
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


def _named(*names, **extra):
    """The registry agents `names`, then `extra` ({label: factory})."""
    return {**{name: REGISTRY[name] for name in names}, **extra}


def _scan(reference, label, values, make):
    """The registry agents `reference` plus agents that differ in one parameter: `make(value)` builds each, labelled `<label><value>`."""
    return _named(*reference, **{f"{label}{value:g}": (lambda v=value: make(v)) for value in values})


FLOOR = ("nearest", "oracle")              # the floor and the ceiling, in every population so that the panels share a reference
DELTA = FLOOR + ("learner",)               # ... and the delta-rule learner with the standard actor
GP = FLOOR + ("gp_mean",)                  # ... and the GP critic with the standard actor: the reference of every GP scan


def _choice_noise():
    pop = _named(*DELTA)
    for critic in ("oracle", "learner"):
        for temperature in (0.3, 1.0):
            pop[f"{critic}_softmax{temperature:g}"] = lambda c=critic, t=temperature: _agent(c, Softmax(t))
    return pop


def _gp_kernel():
    pop = _named(*GP)
    for additive, label, lengths in ((True, "add", (0.2, 0.5)), (False, "joint", (0.3, 0.5))):
        for length in lengths:
            pop[f"gp_{label}{length:g}"] = lambda a=additive, l=length: GPAgent(kernel=RBFKernel(l, additive=a))
    return pop


# Each population is also one figure group (5 agents or fewer to avoid the `plots.MAX_DISTINCT` warning; 8 is the palette's limit) and includes
# the floor. The comment above each says what it compares (docs/DECISIONS.md: "One actor default", "Exploration policies").
POPULATIONS = {
    # the standard agents: the floor, the oracle and the learner, all with the standard actor and the view cone
    "main": lambda: _named(*DELTA),
    # the delta-rule learner's parameters (the standard learner: alpha 0.5, RBF width 0.3, 8 centers, a 15 s window, a fixed 0.1 baseline)
    "scan-alpha": lambda: _scan(FLOOR, "learner_alpha", (0.1, 0.3, 0.5, 0.8), lambda v: LearnerAgent(UtilityActor(), alpha=v)),
    "scan-length": lambda: _scan(FLOOR, "learner_len", (0.1, 0.3, 0.5, 0.7), lambda v: LearnerAgent(UtilityActor(), features=RBFFeatures(length_scale=v))),
    "scan-centers": lambda: _scan(FLOOR, "learner_centers", (4, 8, 12, 16), lambda v: LearnerAgent(UtilityActor(), features=RBFFeatures(n_centers=v))),
    # the running mean of the bush means and larger fixed baselines (1, 2: they act as an optimism bonus, which belongs to the actor)
    "scan-prior": lambda: _named(*DELTA, learner_meanprior=lambda: LearnerAgent(UtilityActor(), prior=NeutralPrior()),
                                 **_scan((), "learner_prior", (1.0, 2.0), lambda v: LearnerAgent(UtilityActor(), prior=ConstantPrior(v)))),
    # 15 s (ring 5 of bushes) against 60 s (past any hop in the valley: effectively no window)
    "scan-window": lambda: _scan(FLOOR, "learner_window", (15.0, 60.0), lambda v: LearnerAgent(UtilityActor(max_walk_time=v))),
    "choice-noise": _choice_noise,
    # cone against whole map for both critics (the check that set the cone as the default)
    "knowledge": lambda: _named("nearest", "oracle", oracle_fullmap=lambda: _agent("oracle", whole_map=True), learner=REGISTRY["learner"],
                                learner_fullmap=lambda: _agent("learner", whole_map=True)),
    # the exploration policies, each on both critics
    "learners": lambda: _named(*DELTA, "gp_mean", "gp_joint"),
    "explore-posterior": lambda: _named(*DELTA, "gp_mean", "gp_ucb", "gp_thompson", "gp_hybrid"),
    "explore-noise": lambda: _named(*DELTA, "gp_mean", "gp_softmax", "gp_softmax_horizon"),
    "explore-bonus": lambda: _named(*DELTA, "gp_mean", "gp_curious", "gp_peek", "gp_curious_peek", "gp_ars"),
    "delta-noise": lambda: _named(*DELTA, "softmax", "softmax_horizon"),
    "delta-bonus": lambda: _named(*DELTA, "curious", "peek", "curious_peek", "ars"),
    # the ladder from the exact GP to the delta rule, one difference at a time (the reversion value fixed at 0.1, every bush weighted alike, the prior and noise
    # fixed, the delta rule's own features as the kernel: `gp_matched` differs from `learner` in the update rule alone), and the matched GP's regularisation
    "critic-ladder": lambda: _named(*DELTA, "gp_mean", "gp_fixmean", "gp_equalw", "gp_fixhyper", "gp_matched"),
    "scan-matched-noise": lambda: _scan(DELTA + ("gp_matched",), "matched_noise", (0.1, 1.0, 3.0),
                                        lambda v: GPAgent(kernel=FeatureKernel(RBFFeatures()), prior_mean=0.1, weight_by_count=False, prior_std=1.0, noise_std=v)),
    # replay in the delta-rule critic, during the session: extra passes over everything stored after each bush (does it converge to the exact fit,
    # `gp_matched`?) and other ways of choosing what to replay
    "scan-replay-epochs": lambda: _scan(DELTA + ("gp_matched",), "replay_epochs", (1, 5, 20, 100), lambda v: LearnerAgent(UtilityActor(), replay=FullSweeps(v))),
    "scan-replay-policy": lambda: _named(*DELTA, "gp_matched", replay_sampled20=lambda: LearnerAgent(UtilityActor(), replay=SampledReplay(20)),
                                         replay_sampled100=lambda: LearnerAgent(UtilityActor(), replay=SampledReplay(100)),
                                         replay_top5=lambda: LearnerAgent(UtilityActor(), replay=PrioritizedReplay(5)),
                                         replay_top20=lambda: LearnerAgent(UtilityActor(), replay=PrioritizedReplay(20))),
    # one parameter of the GP critic or of an exploration policy on it, against `gp_mean`
    "scan-gp-kernel": _gp_kernel,
    "scan-gp-prior": lambda: _named(*GP, **{"gp_mean0.1": lambda: GPAgent(prior_mean=0.1), "gp_mean0.5": lambda: GPAgent(prior_mean=0.5),
                                            "gp_std0.5": lambda: GPAgent(initial_std=0.5), "gp_std2": lambda: GPAgent(initial_std=2.0)}),
    "scan-ucb-beta": lambda: _scan(GP, "ucb_beta", (0.1, 0.25, 0.5, 1.0), lambda v: GPAgent(PosteriorActor(v, temperature=0.05))),
    "scan-ucb-temp": lambda: _scan(GP, "ucb_temp", (0.02, 0.05, 0.1), lambda v: GPAgent(PosteriorActor(temperature=v))),
    "scan-hybrid-beta": lambda: _scan(GP, "hybrid_beta", (0.1, 0.25, 0.5, 1.0), lambda v: GPAgent(PosteriorActor(v, sample=True))),
    "scan-softmax-temp": lambda: _scan(GP, "softmax_temp", (0.01, 0.02, 0.05, 0.1), lambda v: GPAgent(SoftmaxActor(v))),
    "scan-horizon-temp": lambda: _scan(GP, "horizon_temp", (0.05, 0.1, 0.2, 0.4), lambda v: GPAgent(SoftmaxActor(v, horizon=True))),
    "scan-curious-beta": lambda: _scan(GP, "curious_beta", (0.1, 0.3, 1.0, 2.0), lambda v: GPAgent(CuriousActor(beta=v))),
    "scan-curious-high": lambda: {**_scan(GP, "curious_beta", (2.0, 4.0, 8.0), lambda v: GPAgent(CuriousActor(beta=v))), "learner": REGISTRY["learner"]},
    "scan-peek": lambda: _scan(GP, "peek_k", (1, 2, 3, 5), lambda v: GPAgent(CuriousActor(beta=0.0, peek_fruits=v))),
    "scan-ars-radius": lambda: _scan(GP, "ars_radius", (0.3, 0.5, 0.8), lambda v: GPAgent(AreaRestrictedActor(radius=v, growth=2.0))),
    "scan-ars-growth": lambda: _scan(GP, "ars_growth", (1.5, 2.0, 3.0), lambda v: GPAgent(AreaRestrictedActor(radius=0.5, growth=v))),
    # one parameter of an exploration policy on the delta-rule critic, against that policy's default
    "scan-delta-horizon-temp": lambda: _scan(DELTA + ("softmax_horizon",), "dhorizon_temp", (0.02, 0.05, 0.2), lambda v: LearnerAgent(SoftmaxActor(v, horizon=True))),
    "scan-delta-curious-beta": lambda: _scan(DELTA + ("curious",), "dcurious_beta", (1.0, 2.0, 4.0), lambda v: LearnerAgent(CuriousActor(beta=v))),
    "scan-delta-peek-margin": lambda: _scan(DELTA + ("peek",), "dpeek_margin", (0.5, 1.5, 2.0), lambda v: LearnerAgent(CuriousActor(beta=0.0, peek_fruits=2, margin=v))),
}

# Agents a population records but its figures leave out: the scans compare their learners with one another, so the floor and the ceiling
# (still in the population for `scores`) would only crowd the plots. Some figures still hold 6 or 7 agents (a warning above 5; the palette has 8).
FIGURE_OMITS = {name: ("nearest", "oracle") for name in POPULATIONS if name.startswith(("scan-", "explore-", "delta-", "critic-")) or name == "learners"}
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
