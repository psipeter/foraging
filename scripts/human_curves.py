"""Participants' curves in the data classes of the agents' (`analysis.CumulativeCurves`, `analysis.LearningCurves`), so `plots.py` draws them
with the same code. Each participant is a series of their own (named p1, p2, ... in the order they started, one seed each), so each has
its own colour, linestyle and marker in the figures; a group mean and interval can come later, once there are enough participants.

    reward_curves(humans)      {session: CumulativeCurves}   points so far against session time, one series per finished participant
    interlude_curves(humans)   {session: LearningCurves}     Interlude accuracy at the end of the session (a participant is scored once,
                                                             so each series has a single time, the session's length)

`humans` is `human_data.load(...)`. A session is named by its block (`human_data`'s `block`: CF_S1 for CF_S1 and its Interlude CF_I1; the names before
experiments, S1 to S5, work for the pilot data), so sessions of different experiments are never pooled. Only completed sessions of finished runs are used. Each curves object carries a `footer` and a `note` that
`plots.py` prints instead of the agents' tag and engine hash.

    agent_curves(store, tag)   (reward, interlude)           the same two kinds of curves for the agents recorded in the humans' worlds
                                                             (a run per session at the world seed the participants played, with the Interlude the
                                                             participants saw); each series is named after its `battery.POPULATIONS["main"]` agent

The command line draws the participants and then the agents, with `plots.figure_points`, on the same axis limits (`plots.point_limits`) so that
the two figures can be laid side by side: `humans_points.png` and `agents_points.png`.

    ./venv/bin/python scripts/human_curves.py [--sessions CF_S1,CF_S2,...] [--agents-tag human-worlds] [--exclude STRING ...] [--mode paper|presentation] [--out DIR]
"""

import argparse
import json
import sys

import numpy as np

import analysis
import human_data
import interlude
import plots

def experiment_sessions(code):
    """The session names of an experiment (`<code>_S<n>` assets in its folder), in order of their number."""
    from world import EXPERIMENTS_DIR
    found = [p.stem for p in (EXPERIMENTS_DIR / code).glob(f"{code}_S*.asset")]
    return tuple(sorted(found, key=lambda name: int(name.rsplit("_S", 1)[1])))


SESSIONS = experiment_sessions("FN")      # the default experiment; the Tutorial's TUT_S1 is left out


def _footer(h, run_ids):
    people = h.participants[h.participants["run_id"].isin(run_ids)]
    commits = ", ".join(sorted({c[:7] for c in people["build_commit"]}))
    dirty = bool(people["build_dirty"].any())
    return f"humans: {len(people)} finished run(s), build {commits}{', dirty tree' if dirty else ''}"


def _names(h):
    """{run_id: p1, p2, ...} in the order the runs started."""
    return {run: f"p{i + 1}" for i, run in enumerate(h.participants.sort_values("started_at")["run_id"])}


def _series(name, curve):
    """One participant's series: a single seed, so no interval (NaN)."""
    curve = np.asarray(curve, dtype=float)
    return {"label": name, "n": 1, "mean": curve, "lo": np.full_like(curve, np.nan), "hi": np.full_like(curve, np.nan),
            "per_seed": curve[None], "seeds": [name]}


def _completed(h, name, kind, names):
    """The completed rows of a session block (the session itself or its Interlude), in the order the participants started."""
    s = h.sessions
    rows = s[(s["block"] == name) & (s["kind"] == kind) & (s["completed"] == 1)]
    return rows.assign(person=rows["run_id"].map(names)).sort_values("person", key=lambda p: p.str[1:].astype(int))


def reward_curves(h, sessions=SESSIONS, step=1.0, confidence=0.95):
    """{session: CumulativeCurves}: each participant's points so far on a grid of `step` seconds (the value at t counts the fruits taken up to
    and including t, as for the agents), from the logged `fruit` events."""
    names, out = _names(h), {}
    for name in sessions:
        rows = _completed(h, name, "session", names)
        if rows.empty:
            continue
        duration = float(rows["duration_s"].iloc[0])
        grid = np.linspace(0.0, duration, int(round(duration / step)) + 1)
        series = {}
        for r in rows.itertuples():
            f = h.fruits[(h.fruits["run_id"] == r.run_id) & (h.fruits["session_index"] == r.session_index)].sort_values("seq")
            t, reward = f["t"].to_numpy(float), f["reward"].to_numpy(float)
            series[r.person] = _series(r.person, np.concatenate([[0.0], np.cumsum(reward)])[np.searchsorted(t, grid, side="right")])
        out[name] = analysis.CumulativeCurves(grid, duration, confidence, series)
        out[name].footer = _footer(h, rows["run_id"])
        out[name].note = "one line per participant; the marker on the right is the Interlude accuracy at the end of the session"
    return out


def interlude_curves(h, sessions=SESSIONS, confidence=0.95):
    """{session: LearningCurves}: each participant's Interlude accuracy (correct trials over trials) at the end of the session."""
    names, out = _names(h), {}
    for name in sessions:
        rows = _completed(h, name, "interlude", names)
        if rows.empty:
            continue
        duration = float(_completed(h, name, "session", names)["duration_s"].iloc[0])
        mode = interlude.MODE_CODES[json.loads(rows["config"].iloc[0])["interludeMode"]]
        series = {r.person: _series(r.person, [r.n_correct / r.n_trials]) for r in rows.itertuples()}
        out[name] = analysis.LearningCurves(np.array([duration]), "interlude_accuracy", confidence, series)
        out[name].footer = _footer(h, rows["run_id"])
        out[name].note = f"{mode} Interlude, {int(rows['n_trials'].iloc[0])} trials, scored once at the end of each session"
    return out


def agent_curves(store, tag="human-worlds", sessions=SESSIONS):
    """({session: CumulativeCurves}, {session: LearningCurves}) of the agents recorded under `tag` (kind interlude, with checkpoints): the
    points over time and the Interlude accuracy at the end of the session, one series per agent, named as in the main population."""
    import battery
    names = {factory().spec_hash(): name for name, factory in battery.POPULATIONS["main"]().items()}
    reward, learned = {}, {}
    for session in sessions:
        sel = analysis.select(store, tag=tag, session=session, kind="interlude")
        reward[session], learned[session] = analysis.cumulative_curve(store, sel), analysis.checkpoint_curve(store, sel)
        for curves in (reward[session], learned[session]):
            for aid, c in curves.agents.items():
                c["label"] = names.get(aid, c["label"])
        reward[session].note = "agents run once in each world the participants played; the marker on the right is the Interlude accuracy at the end of the session"
    return reward, learned


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--experiment", default=None, help="draw this experiment's sessions (its code, e.g. FN) instead of the default")
    parser.add_argument("--sessions", default=None, help="comma-separated session names (overrides --experiment)")
    parser.add_argument("--agents-tag", default="human-worlds", help="tag of the agents recorded in the humans' worlds ('' to draw the participants only)")
    parser.add_argument("--exclude", nargs="*", default=[], help="leave out participants whose ID or signed name contains any of these")
    parser.add_argument("--mode", default=plots.DEFAULT_MODE, choices=sorted(plots.MODES))
    parser.add_argument("--out", default=None, help="output directory (default results/)")
    args = parser.parse_args(argv)
    import results
    out = args.out or results.DEFAULT_PATH.parent
    h = human_data.load(exclude=args.exclude, status="finished")
    sessions = tuple(args.sessions.split(",")) if args.sessions else experiment_sessions(args.experiment) if args.experiment else SESSIONS
    people = (reward_curves(h, sessions), interlude_curves(h, sessions))
    figures = [(people, "humans_points", "humans: points", None)]
    if args.agents_tag:
        with results.Store(results.DEFAULT_PATH, readonly=True) as store:
            agents = agent_curves(store, args.agents_tag, sessions)
        figures.append((agents, "agents_points", f"agents in the human worlds ({args.agents_tag}): points", ["nearest", "oracle", "learner"]))
    limits = plots.point_limits(*[pair for pair, *_ in figures])      # the axes of the figures are the same
    for (reward, learned), name, title, order in figures:
        print(plots.plot_points(reward, learned, f"{out}/{name}.png", title=title, mode=args.mode, limits=limits, order=order))


if __name__ == "__main__":
    sys.exit(main())
