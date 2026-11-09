"""human_curves.py: participants' curves from the tidy tables, and how plots.py draws them (first colour and style, thin line per participant)."""

import numpy as np
import pytest
import pandas as pd

import human_curves
import human_data
import plots

pytestmark = pytest.mark.frozen_sessions        # the old session aliases resolve to frozen copies (conftest.py)


def _humans():
    """Two finished participants, S1 (10 s long) and its Interlude: participant a takes fruits worth 5, 5 and 10 at t = 2, 4 and 8."""
    runs = ["run-a", "run-b"]
    people = pd.DataFrame({"run_id": runs, "started_at": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True), "build_commit": ["abcdef012"] * 2,
                           "build_dirty": [1, 0]})
    config = '{"interludeMode": 4}'
    sessions = pd.DataFrame([
        {"run_id": r, "session_index": i, "name": n, "block": "S1", "kind": k, "completed": 1, "duration_s": d, "n_trials": nt, "n_correct": nc, "config": config}
        for r, nc in zip(runs, (15, 4)) for i, (n, k, d, nt) in enumerate((("S1", "session", 10.0, np.nan), ("S1_Interlude", "interlude", np.nan, 20)))])
    sessions.loc[sessions["kind"] == "session", "n_correct"] = np.nan
    fruits = pd.DataFrame({"run_id": ["run-a"] * 3 + ["run-b"] * 1, "session_index": 0, "seq": [0, 1, 2, 0], "t": [2.0, 4.0, 8.0, 3.0],
                           "reward": [5.0, 5.0, 10.0, 7.0]})
    return human_data.Humans(people, sessions, pd.DataFrame(), fruits, pd.DataFrame(), None)


def test_reward_curves_are_the_running_sum_of_each_participants_fruits():
    curves = human_curves.reward_curves(_humans(), sessions=("S1",))["S1"]
    assert list(curves.agents) == ["p1", "p2"] and curves.duration == 10.0 and len(curves.t) == 11
    assert curves.agents["p1"]["mean"].tolist() == [0, 0, 5, 5, 10, 10, 10, 10, 20, 20, 20]       # the value at t counts the fruit taken at t
    assert curves.agents["p2"]["mean"][-1] == 7 and curves.agents["p2"]["mean"][2] == 0 and curves.agents["p2"]["n"] == 1
    assert curves.footer == "humans: 2 finished run(s), build abcdef0, dirty tree"


def test_interlude_curves_are_one_accuracy_per_participant_at_the_end_of_the_session():
    curves = human_curves.interlude_curves(_humans(), sessions=("S1",))["S1"]
    assert curves.t.tolist() == [10.0] and [curves.agents[p]["mean"].tolist() for p in ("p1", "p2")] == [[0.75], [0.2]]
    assert curves.note.startswith("hybrid Interlude, 20 trials")


def test_each_participant_is_a_series_with_its_own_colour_style_and_marker():
    h = _humans()
    reward, learned = human_curves.reward_curves(h, sessions=("S1",)), human_curves.interlude_curves(h, sessions=("S1",))
    seen, palette = plots._palette(reward, None, None)
    assert seen == ["p1", "p2"] and [palette[n] for n in seen] == plots.SERIES[:2]
    fig = plots.figure_points(reward, learned)
    lines = [a for a in fig.axes if a.get_title() == "S1"][0]
    twin = [a for a in fig.axes if a.get_ylabel() == "Interlude accuracy (%)"][0]
    assert len(lines.get_lines()) == 2 and twin.get_ylim()[1] > 100
    markers = [(line.get_marker(), line.get_color(), line.get_ydata()[0], line.get_xdata()[0] > 10.0) for line in twin.get_lines()
               if line.get_marker() in plots.MARKERS[:2]]
    assert markers == [("o", plots.SERIES[0], 75.0, True), ("s", plots.SERIES[1], 20.0, True)]   # at the accuracy in %, right of where the line ends


def test_figures_given_the_same_limits_have_the_same_axes():
    h = _humans()
    people = (human_curves.reward_curves(h, sessions=("S1",)), human_curves.interlude_curves(h, sessions=("S1",)))
    agents = (human_curves.reward_curves(h, sessions=("S1",)), human_curves.interlude_curves(h, sessions=("S1",)))
    for c in agents[0]["S1"].agents.values():
        c["mean"] = c["mean"] * 10                                           # the agents collect ten times more points
    limits = plots.point_limits(people, agents)
    assert abs(limits["points"]["S1"] - 1.05 * 200) < 1e-9 and limits["longest"] == 10.0 and limits["accuracy_low"] == 20
    drawn = [plots.figure_points(*pair, limits=limits) for pair in (people, agents)]
    axes = [{a.get_ylabel(): (a.get_ylim(), a.get_xlim()) for a in fig.axes} for fig in drawn]
    assert axes[0] == axes[1] and axes[0]["points"][0] == (0, limits["points"]["S1"])
