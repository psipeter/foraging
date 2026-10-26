"""Queries over the results database (scripts/results.py): paired comparisons, tables, the gap an agent closes, and the effect of one
component. Everything here only reads; open the file with `results.Store(path, readonly=True)`.

    sel = analysis.select(store, tag="alpha-sweep-1")           # one environment, one code version, every agent in the tag
    rows = analysis.table(sel, baseline="nearest")               # mean, std, se and the paired difference to the baseline
    print(analysis.format_table(rows, sel))
    analysis.component_effect(sel, "critic.alpha")               # agents that differ in nothing but alpha, compared pairwise

A `Selection` is guaranteed to be comparable: exactly one environment, and for each agent one episode per seed (one code version
each). By default only results from the current engine code are used (`engine="current"`); pass an engine hash or "any" to look
at older ones, and the selection says so in `notes`. The metric is chosen at query time (a column, "interlude:<trial type>", or a
function of the episode row). There is deliberately no normalised score: the paired lead over a baseline (`paired`, `table`) is the
quantity to optimise, in reward points; scores per session are in battery.py (`scores`).

CLI:  ./venv/bin/python scripts/analysis.py {runs,table,effect,curve,learning} ...   (see --help)
"""

import argparse
import json
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

import fingerprint
import specs
from agents import REGISTRY
from results import DEFAULT_PATH, Store


class SelectionError(ValueError):
    """The requested episodes do not form one comparable set (several environments or code versions, or nothing)."""


# --------------------------------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------------------------------

@dataclass
class Selection:
    env: dict                    # the environment (fingerprint.environment) of every episode
    env_id: str
    code: dict                   # {engine_hash, agents_hash(es), commit, dirty}: provenance of the episodes
    agents: dict                 # agent_id -> spec
    rows: dict                   # agent_id -> {seed: episode row (with `by_type`)}
    tags: list
    notes: list = field(default_factory=list)

    def seeds(self, agent_id):
        return sorted(self.rows[agent_id])

    def values(self, agent_id, metric="total"):
        """{seed: metric value} for an agent (episodes where the metric is missing are left out)."""
        fn = metric_function(metric)
        out = {}
        for seed, row in self.rows[agent_id].items():
            v = fn(row)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                out[seed] = float(v)
        return out


def metric_function(metric):
    """A function of an episode row: a column name (`total`, `interlude_accuracy`, `n_visits`...), `interlude:<trial type>`, or a
    callable taken as is."""
    if callable(metric):
        return metric
    if metric.startswith("interlude:"):
        trial_type = metric.split(":", 1)[1]
        return lambda row: row["by_type"].get(trial_type)
    return lambda row: row.get(metric)


def resolve_agent(store, agent):
    """An agent id from an id, a registry name (`nearest`) or a spec dict."""
    if hasattr(agent, "spec"):
        agent = agent.spec()
    if isinstance(agent, dict):
        return specs.spec_hash(agent)
    if agent in REGISTRY:
        return REGISTRY[agent]().spec_hash()
    if store.select("SELECT 1 FROM agents WHERE agent_id = ?", (agent,)):
        return agent
    raise KeyError(f"no agent '{agent}' (not a registry name, a spec, or a recorded agent id)")


def select(store, *, tag=None, session=None, kind="session", env_id=None, overrides=None, agents=None, engine="current"):
    """The episodes matching the filters as one comparable set.

    tag        episodes used by the runs with this tag (a string, or a list of tags)
    session    session name; kind "session" or "interlude"; env_id an exact environment; overrides: the environment's session
               overrides must equal this dict
    agents     agent ids, registry names or specs to keep
    engine     "current" (the engine code now), an engine hash, or "any"

    Raises SelectionError when more than one environment remains, or an agent has two episodes for one seed from different code."""
    where, params = ["1 = 1"], []
    if tag is not None:
        tags = [tag] if isinstance(tag, str) else list(tag)
        where.append(f"e.episode_id IN (SELECT episode_id FROM run_episodes JOIN runs USING (run_id) WHERE tag IN ({','.join('?' * len(tags))}))")
        params += tags
    if session is not None:
        where.append("v.session = ?")
        params.append(session)
    if kind is not None:
        where.append("v.kind = ?")
        params.append(kind)
    if env_id is not None:
        where.append("e.env_id = ?")
        params.append(env_id)
    if overrides is not None:
        where.append("v.overrides_json = ?")
        params.append(specs.canonical_json(overrides))
    if agents is not None:
        ids = [resolve_agent(store, a) for a in agents]
        where.append(f"e.agent_id IN ({','.join('?' * len(ids))})")
        params += ids
    current = fingerprint.code_version()
    if engine == "current":
        where.append("c.engine_hash = ?")
        params.append(current["engine_hash"])
    elif engine != "any":
        where.append("c.engine_hash = ?")
        params.append(engine)
    rows = store.select(
        "SELECT e.*, a.spec_json, v.env_json, c.engine_hash, c.agents_hash, c.commit_hash, c.dirty FROM episodes e "
        "JOIN agents a USING (agent_id) JOIN environments v USING (env_id) JOIN code_versions c USING (code_id) "
        f"WHERE {' AND '.join(where)} ORDER BY e.agent_id, e.seed", params)
    if not rows:
        raise SelectionError("no recorded episodes match" + ("" if engine != "current" else " (only the current engine code is searched: "
                                                                f"engine {current['engine_hash']}; pass engine='any' to look further)"))
    envs = sorted({r["env_id"] for r in rows})
    if len(envs) > 1:
        shown = [f"{e}: {json.loads(next(r for r in rows if r['env_id'] == e)['env_json'])['overrides']}" for e in envs]
        raise SelectionError(f"{len(envs)} environments match; narrow with session=, kind=, overrides= or env_id= ({'; '.join(shown)})")
    by_agent, specs_by, code_ids = {}, {}, {}
    for r in rows:
        slot = by_agent.setdefault(r["agent_id"], {})
        if r["seed"] in slot:
            raise SelectionError(f"agent {r['agent_id']} has seed {r['seed']} from more than one code version "
                                 f"(engine {slot[r['seed']]['engine_hash']} and {r['engine_hash']}); pass engine=<hash>")
        r["by_type"] = {}
        slot[r["seed"]] = r
        specs_by[r["agent_id"]] = json.loads(r["spec_json"])
        code_ids[r["code_id"]] = r
    types = store.select("SELECT t.episode_id, t.trial_type, t.accuracy FROM episode_types t JOIN episodes e USING (episode_id) "
                         "WHERE e.env_id = ?", (envs[0],))
    index = {r["episode_id"]: r for slot in by_agent.values() for r in slot.values()}
    for t in types:
        if t["episode_id"] in index:
            index[t["episode_id"]]["by_type"][t["trial_type"]] = t["accuracy"]
    engines = sorted({r["engine_hash"] for r in code_ids.values()})
    agent_hashes = sorted({r["agents_hash"] for r in code_ids.values()})
    dirty = any(r["dirty"] for r in code_ids.values() if r["dirty"] is not None)
    commits = sorted({r["commit_hash"] for r in code_ids.values() if r["commit_hash"]})
    code = {"engine_hash": engines[0] if len(engines) == 1 else engines, "agents_hash": agent_hashes[0] if len(agent_hashes) == 1 else agent_hashes,
            "commit": commits, "dirty": dirty}
    notes = []
    if engines != [current["engine_hash"]]:
        notes.append(f"engine code {','.join(engines)} is not the current engine {current['engine_hash']}: these results are stale")
    if agent_hashes != [current["agents_hash"]]:
        notes.append(f"agents.py/specs.py have changed since these were recorded ({','.join(agent_hashes)} vs {current['agents_hash']}); "
                     "an agent's behavior under an unchanged spec may differ")
    if dirty:
        notes.append("some results were computed on a dirty tree (uncommitted changes in the hashed files)")
    tags = []
    if tag is not None:
        tags = [tag] if isinstance(tag, str) else list(tag)
    return Selection(json.loads(rows[0]["env_json"]), envs[0], code, specs_by, by_agent, tags, notes)


def fruit_events(store, sel, agent, seed):
    """The fruits one agent took in one world, in order: {'t', 'bush', 'k', 'reward', 'running_total'} as numpy arrays (t in session
    seconds). The agent's counterpart of the human `fruit` events in events.csv; `agent` is an id, registry name or spec."""
    agent_id = resolve_agent_in(sel, agent)
    if seed not in sel.rows[agent_id]:
        raise KeyError(f"agent {agent_id} has no episode for seed {seed} in this selection")
    rows = store.fruits(sel.rows[agent_id][seed]["episode_id"])
    return {key: np.array([r[key] for r in rows], dtype=float if key in ("t", "reward", "running_total") else int)
            for key in ("t", "bush", "k", "reward", "running_total")}


# --------------------------------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------------------------------

def _se(x):
    x = np.asarray(x, dtype=float)
    return float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("nan")


def paired(sel, agent_id, baseline_id, metric="total"):
    """(n, mean difference, standard error of it) of `agent` minus `baseline` over the seeds both have."""
    a, b = sel.values(agent_id, metric), sel.values(baseline_id, metric)
    common = sorted(set(a) & set(b))
    d = np.array([a[s] - b[s] for s in common])
    return len(common), (float(d.mean()) if len(d) else float("nan")), _se(d)


def resolve_agent_in(sel, agent):
    """An agent id of this selection from an id, a registry name or a spec."""
    if hasattr(agent, "spec"):
        agent = agent.spec()
    if isinstance(agent, dict):
        agent_id = specs.spec_hash(agent)
    elif agent in sel.agents:
        return agent
    elif agent in REGISTRY:
        agent_id = REGISTRY[agent]().spec_hash()
    else:
        raise KeyError(f"agent '{agent}' is not in this selection")
    if agent_id not in sel.agents:
        raise KeyError(f"agent '{agent}' ({agent_id}) is not in this selection")
    return agent_id


# --------------------------------------------------------------------------------------------------
# Table
# --------------------------------------------------------------------------------------------------

def table(sel, metric="total", baseline=None, sort=True):
    """One row per agent: label (only the fields that differ among the agents), agent id, n seeds, mean, std, se and, with a
    `baseline` (id, registry name or spec), the paired difference to it with its standard error and number of pairs."""
    ids = list(sel.agents)
    labels = specs.labels([sel.agents[i] for i in ids])
    base = resolve_agent_in(sel, baseline) if baseline is not None else None
    rows = []
    for i, label in zip(ids, labels):
        v = np.array(list(sel.values(i, metric).values()))
        row = {"label": label, "agent_id": i, "n": len(v), "mean": float(v.mean()) if len(v) else float("nan"),
               "std": float(v.std(ddof=1)) if len(v) > 1 else float("nan"), "se": _se(v), "diff": None, "diff_se": None, "pairs": None}
        if base is not None and i != base:
            row["pairs"], row["diff"], row["diff_se"] = paired(sel, i, base, metric)
        rows.append(row)
    if sort:
        rows.sort(key=lambda r: (np.isnan(r["mean"]), -r["mean"] if not np.isnan(r["mean"]) else 0.0))
    return rows


def describe(sel, metric="total"):
    """The header every report states: session and overrides, kind, seeds, tags, metric, engine and agents hashes, commit, dirty."""
    env = sel.env
    seeds = sorted({s for slot in sel.rows.values() for s in slot})
    code = sel.code
    commits = code["commit"]
    lines = [f"{env['session']} ({env['kind']}), overrides {env['overrides'] or 'none'}, "
             f"{'sensor ' + json.dumps(env['percept']) if env['percept'] else 'default sensor'}, "
             f"seeds {seeds[0]}-{seeds[-1]} ({len(seeds)}), metric {metric if isinstance(metric, str) else getattr(metric, '__name__', 'custom')}",
             f"tag {', '.join(sel.tags) or 'any'}, environment {sel.env_id}, engine {code['engine_hash']}, agents {code['agents_hash']}, "
             f"commit {', '.join(commits) or '?'}{' (dirty)' if code['dirty'] else ''}"]
    lines += [f"NOTE: {n}" for n in sel.notes]
    return "\n".join(lines)


def format_table(rows, sel=None, metric="total"):
    """Text of `table(...)` rows, with the report header when the selection is given."""
    has_diff = any(r["diff"] is not None for r in rows)
    width = max([len(r["label"]) for r in rows] + [5])
    lines = [f"{'agent':<{width}}{'n':>5}{'mean':>10}{'std':>9}{'se':>8}" + (f"{'paired diff':>24}" if has_diff else "")]
    for r in rows:
        line = f"{r['label']:<{width}}{r['n']:>5}{r['mean']:>10.2f}{r['std']:>9.2f}{r['se']:>8.2f}"
        if r["diff"] is not None:
            line += f"{r['diff']:>14.2f} ± {r['diff_se']:.2f} (n={r['pairs']})"
        elif has_diff:
            line += f"{'(baseline)':>24}"
        lines.append(line)
    text = "\n".join(lines)
    return (describe(sel, metric) + "\n" + text) if sel is not None else text


# --------------------------------------------------------------------------------------------------
# Effect of one component
# --------------------------------------------------------------------------------------------------

def _under(path, key):
    return key == path or key.startswith(path + ".")


def _at(spec, path):
    node = spec
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@dataclass
class Effect:
    factor: str
    reference: str                    # canonical JSON of the reference level
    groups: list                      # per matched group: {"levels": {level: agent_id}, "means": {level: mean}, "diffs": {level: (n, diff, se)}}
    levels: dict                      # level key -> label
    summary: dict                     # level key -> {"groups": n, "mean_diff": ..., "se": ... (across groups), "pooled_se": ...}


def component_effect(sel, factor, metric="total", reference=None):
    """What changing one component does, holding everything else fixed.

    `factor` is a path into the agent spec ('critic.alpha', 'critic.features', 'actor.choice', 'critic'); everything under the path
    belongs to the factor (so `critic.features` compares RBF with SSP features whatever their own parameters), and its value is
    the level. Agents are grouped by all the parameters outside the factor; a group with two or more levels yields paired
    differences of each level to the group's `reference` level (default: the level that occurs in the most groups). The summary
    averages those differences over the groups (the standard error is across groups, so it needs two or more). A level that
    a spec does not have (an oracle has no `critic.alpha`) is the level None."""
    flat = {i: specs.flatten(s) for i, s in sel.agents.items()}
    groups = {}
    for i, spec in sel.agents.items():
        rest = tuple(sorted((k, json.dumps(v, sort_keys=True)) for k, v in flat[i].items() if not _under(factor, k)))
        level = specs.canonical_json(_at(spec, factor))
        groups.setdefault(rest, {})[level] = i
    groups = [g for g in groups.values() if len(g) > 1]
    if not groups:
        raise SelectionError(f"no two agents in this selection differ only in '{factor}'")
    counts = {}
    for g in groups:
        for level in g:
            counts[level] = counts.get(level, 0) + 1
    ref = specs.canonical_json(reference) if reference is not None else max(sorted(counts), key=lambda k: counts[k])
    values = [json.loads(k) for k in sorted(counts)]
    last = factor.rsplit(".", 1)[-1]
    if all(isinstance(v, dict) for v in values):
        names = specs.labels(values)
    else:
        names = ["absent" if v is None else f"{last}={v}" for v in values]
    labels = dict(zip(sorted(counts), names))
    out_groups = []
    for g in groups:
        means = {lv: float(np.mean(list(sel.values(i, metric).values()))) for lv, i in g.items()}
        diffs = {lv: paired(sel, i, g[ref], metric) for lv, i in g.items() if ref in g and lv != ref}
        out_groups.append({"levels": g, "means": means, "diffs": diffs})
    summary = {}
    for lv in sorted(counts):
        if lv == ref:
            continue
        ds = [(g["diffs"][lv][1], g["diffs"][lv][0]) for g in out_groups if lv in g["diffs"]]
        if not ds:
            continue
        diffs = np.array([d for d, _ in ds])
        summary[lv] = {"groups": len(ds), "mean_diff": float(diffs.mean()), "se": _se(diffs)}
    return Effect(factor, ref, out_groups, labels, summary)


def format_effect(effect, sel=None, metric="total"):
    lines = [f"effect of {effect.factor} against {effect.levels.get(effect.reference, effect.reference)}:"]
    for lv, s in effect.summary.items():
        se = f"{s['se']:.2f}" if not np.isnan(s["se"]) else "n/a (one group)"
        lines.append(f"  {effect.levels[lv]:<28}{s['mean_diff']:>10.2f} ± {se:<16} over {s['groups']} matched group(s)")
    for k, g in enumerate(effect.groups, 1):
        means = ", ".join(f"{effect.levels[lv]}: {m:.1f}" for lv, m in g["means"].items())
        lines.append(f"  group {k}: {means}")
    text = "\n".join(lines)
    return (describe(sel, metric) + "\n" + text) if sel is not None else text


# --------------------------------------------------------------------------------------------------
# Cumulative reward over the session
# --------------------------------------------------------------------------------------------------

def session_seconds(sel):
    """The session length of a selection (the `session_duration` override if there is one, else the session asset's)."""
    from world import load_session
    over = sel.env["overrides"]
    return float(over["session_duration"]) if "session_duration" in over else float(load_session(sel.env["session"]).session_duration)


@dataclass
class CumulativeCurves:
    t: np.ndarray                 # (n_t,) session seconds
    duration: float
    confidence: float
    agents: dict                  # agent_id -> {"label", "n", "mean", "lo", "hi", "per_seed" (n, n_t), "seeds"}
    sel: Selection = None
    quantity: str = "cumulative"  # "cumulative" (reward so far) or "advantage" (cumulative reward over a baseline's)
    baseline: str = None          # the baseline's label (quantity "advantage")
    baseline_id: str = None       # and its agent id


def _fruit_series(store, sel):
    """{episode_id: (times, rewards)} for every episode of the selection (refusing episodes recorded without fruit events)."""
    episodes = {row["episode_id"]: (aid, seed) for aid, slot in sel.rows.items() for seed, row in slot.items()}
    series = {}
    ids = list(episodes)
    for chunk in range(0, len(ids), 500):
        part = ids[chunk:chunk + 500]
        for r in store.select(f"SELECT episode_id, t, reward FROM episode_fruits WHERE episode_id IN ({','.join('?' * len(part))}) ORDER BY episode_id, seq", part):
            series.setdefault(r["episode_id"], ([], []))
            series[r["episode_id"]][0].append(r["t"])
            series[r["episode_id"]][1].append(r["reward"])
    missing = [e for e in episodes if e not in series and sel.rows[episodes[e][0]][episodes[e][1]]["n_fruits"]]
    if missing:
        raise SelectionError(f"{len(missing)} episode(s) have no stored fruit events (recorded before schema v2?): re-record them")
    return series


def _interval(m, confidence):
    """(mean, half-width of the t-interval of the mean) over the rows of `m` (NaN with one row)."""
    mean = m.mean(axis=0)
    if len(m) > 1:
        return mean, stats.t.ppf(0.5 + confidence / 2.0, len(m) - 1) * m.std(axis=0, ddof=1) / np.sqrt(len(m))
    return mean, np.full_like(mean, np.nan)


def lowest_performing(sel, metric="total"):
    """The id of the agent of the selection with the lowest mean `metric` (the first by id on a tie): the baseline that needs no choosing."""
    means = {aid: np.mean(list(sel.values(aid, metric).values())) for aid in sel.agents}
    return min(means, key=lambda aid: (means[aid], aid))


def cumulative_curve(store, sel, step=1.0, confidence=0.95, baseline=None):
    """Reward collected so far against session time, one curve per agent: the mean over its seeds and a `confidence` t-interval. The
    curve ends at the episode's total reward (the value at time T is the total). With a `baseline` (an agent of the selection) each
    curve is instead the paired difference to the baseline's cumulative reward in the same world ("advantage": how far ahead of it
    the agent is by each time), the baseline itself is left out, and the interval is of the paired difference. `baseline="lowest"` takes the
    lowest-performing agent of the selection (by mean total reward) as the baseline."""
    duration = session_seconds(sel)
    grid = np.linspace(0.0, duration, int(round(duration / step)) + 1)
    series = _fruit_series(store, sel)

    def cumulative(episode_id):
        t, reward = series.get(episode_id, ([], []))
        return np.concatenate([[0.0], np.cumsum(reward)])[np.searchsorted(np.asarray(t, dtype=float), grid, side="right")]

    labels = dict(zip(sel.agents, specs.labels(list(sel.agents.values()))))
    base = (lowest_performing(sel) if baseline == "lowest" else resolve_agent_in(sel, baseline)) if baseline is not None else None
    out = {}
    for aid, slot in sel.rows.items():
        if aid == base:
            continue
        seeds = sorted(slot if base is None else set(slot) & set(sel.rows[base]))
        m = np.array([cumulative(slot[s]["episode_id"]) - (cumulative(sel.rows[base][s]["episode_id"]) if base else 0.0) for s in seeds])
        mean, half = _interval(m, confidence)
        out[aid] = {"label": labels[aid], "n": len(m), "mean": mean, "lo": mean - half, "hi": mean + half, "per_seed": m, "seeds": seeds}
    if not out:
        raise SelectionError("nothing to plot: the baseline is the only agent in the selection")
    return CumulativeCurves(grid, duration, confidence, out, sel, "advantage" if base else "cumulative", labels[base] if base else None, base)


# --------------------------------------------------------------------------------------------------
# Interlude score against training time
# --------------------------------------------------------------------------------------------------

@dataclass
class LearningCurves:
    t: np.ndarray                 # (n_t,) checkpoint times: seconds of training in the session
    metric: str
    confidence: float
    agents: dict                  # agent_id -> {"label", "n", "mean", "lo", "hi", "per_seed" (n, n_t), "seeds"}
    sel: Selection = None


def checkpoint_curve(store, sel, metric="interlude_accuracy", confidence=0.95):
    """The Interlude score of each agent against how long it had trained in the session, from a run recorded with checkpoints (a copy
    of the agent scored at each checkpoint time): the mean over seeds and a `confidence` t-interval, one curve per agent. `metric` is
    interlude_accuracy, interlude_bonus or interlude_trials."""
    times = sel.env.get("checkpoints")
    if not times:
        raise SelectionError("this selection was recorded without checkpoints (record with --interlude --checkpoints T1,T2,...)")
    if metric not in ("interlude_accuracy", "interlude_bonus", "interlude_trials"):
        raise ValueError(f"unknown checkpoint metric '{metric}'")
    by_episode = {}
    ids = [row["episode_id"] for slot in sel.rows.values() for row in slot.values()]
    for chunk in range(0, len(ids), 500):
        part = ids[chunk:chunk + 500]
        for r in store.select(f"SELECT episode_id, t, {metric} AS v FROM episode_checkpoints WHERE episode_id IN ({','.join('?' * len(part))})", part):
            by_episode.setdefault(r["episode_id"], {})[r["t"]] = r["v"]
    labels = dict(zip(sel.agents, specs.labels(list(sel.agents.values()))))
    out = {}
    for aid, slot in sel.rows.items():
        seeds = sorted(slot)
        rows = []
        for seed in seeds:
            got = by_episode.get(slot[seed]["episode_id"], {})
            if sorted(got) != sorted(times):
                raise SelectionError(f"agent {aid} seed {seed} has checkpoints {sorted(got)}, expected {times}")
            rows.append([got[t] for t in times])
        m = np.array(rows, dtype=float)
        mean = m.mean(axis=0)
        half = (stats.t.ppf(0.5 + confidence / 2.0, len(m) - 1) * m.std(axis=0, ddof=1) / np.sqrt(len(m))
                if len(m) > 1 else np.full_like(mean, np.nan))
        out[aid] = {"label": labels[aid], "n": len(m), "mean": mean, "lo": mean - half, "hi": mean + half, "per_seed": m, "seeds": seeds}
    return LearningCurves(np.array(times, dtype=float), metric, confidence, out, sel)


# --------------------------------------------------------------------------------------------------
# Runs and command line
# --------------------------------------------------------------------------------------------------

def list_runs(store, tag=None):
    """The runs recorded (newest first), with the agent, session and what each computed or reused."""
    where, params = ("WHERE r.tag = ?", (tag,)) if tag else ("", ())
    return store.select(
        "SELECT r.run_id, r.tag, r.note, r.created, r.n_seeds, r.n_computed, r.n_reused, v.session, v.kind, v.overrides_json, "
        f"r.agent_id, a.critic, a.actor, c.engine_hash, c.dirty FROM runs r JOIN agents a USING (agent_id) JOIN environments v USING (env_id) "
        f"JOIN code_versions c USING (code_id) {where} ORDER BY r.run_id DESC", params)


def _common_filters(ap):
    ap.add_argument("--tag", action="append", help="select the runs with this tag (repeatable)")
    ap.add_argument("--session")
    ap.add_argument("--kind", default="session", choices=["session", "interlude"])
    ap.add_argument("--env", dest="env_id")
    ap.add_argument("--engine", default="current", help="'current' (default), 'any' or an engine hash")
    ap.add_argument("--metric", default="total")
    ap.add_argument("--db", default=None)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query the results database.")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("runs", help="list recorded runs")
    p.add_argument("--tag")
    p.add_argument("--db", default=None)
    p = sub.add_parser("table", help="compare the agents of a selection")
    _common_filters(p)
    p.add_argument("--baseline", default=None, help="agent id or registry name for paired differences")
    p = sub.add_parser("curve", help="cumulative reward against time in the session, one curve per agent (saves a figure)")
    _common_filters(p)
    p.add_argument("--baseline", default=None, help="agent id or registry name, or 'lowest' (the lowest-performing agent): plot each agent's paired lead over it instead")
    p.add_argument("--out", default=None, help="figure path (default results/<tag>_reward.png, or _advantage.png with --baseline)")
    p = sub.add_parser("learning", help="Interlude score against training time (a run recorded with --checkpoints); saves a figure")
    _common_filters(p)
    p.add_argument("--out", default=None, help="figure path (default results/<tag>_interlude.png)")
    p = sub.add_parser("effect", help="the effect of one component, holding the rest fixed")
    _common_filters(p)
    p.add_argument("--factor", required=True, help="path into the agent spec, e.g. critic.alpha or critic.features")
    p.add_argument("--reference", default=None, help="the reference level (JSON, e.g. 0.5 or '{\"type\": \"RBFFeatures\"}')")
    args = ap.parse_args(argv)
    db = args.db or DEFAULT_PATH
    with Store(db, readonly=True) as store:
        if args.command == "runs":
            for r in list_runs(store, args.tag):
                print(f"{r['run_id']:>4} {r['tag']:<20} {r['session']} {r['kind']} {r['overrides_json']} agent {r['agent_id']} "
                      f"({r['critic']}/{r['actor']}) seeds {r['n_seeds']} computed {r['n_computed']} reused {r['n_reused']} "
                      f"engine {r['engine_hash']}{' dirty' if r['dirty'] else ''}")
            return
        sel = select(store, tag=args.tag, session=args.session, kind=args.kind, env_id=args.env_id, engine=args.engine)
        if args.command == "learning":
            import plots
            curves = checkpoint_curve(store, sel, "interlude_accuracy" if args.metric == "total" else args.metric)
            out = args.out or DEFAULT_PATH.parent / f"{'+'.join(args.tag or ['all'])}_interlude.png"
            print(plots.plot_learning_curve(curves, out))
            print(describe(sel, curves.metric))
        elif args.command == "curve":
            import plots
            curves = cumulative_curve(store, sel, baseline=args.baseline)
            name = "advantage" if args.baseline else "reward"
            what = "advantage in cumulative reward" if args.baseline else "cumulative reward"
            out = args.out or DEFAULT_PATH.parent / f"{'+'.join(args.tag or ['all'])}_{name}.png"
            print(plots.plot_cumulative_reward(curves, out))
            print(describe(sel, what))
        elif args.command == "table":
            print(format_table(table(sel, args.metric, args.baseline), sel, args.metric))
        else:
            reference = json.loads(args.reference) if args.reference is not None else None
            print(format_effect(component_effect(sel, args.factor, args.metric, reference), sel, args.metric))


if __name__ == "__main__":
    main()
