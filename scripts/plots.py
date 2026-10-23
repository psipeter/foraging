"""Figures for the results database (matplotlib and seaborn, saved as PNG; nothing here queries the database).

Every figure is a grid of panels, one per session (2 x 2 for S1 to S4; one panel for a single selection), with one line per agent drawn by
`seaborn.lineplot` from the per-seed curves: the mean over seeds and a 95% bootstrap interval, `hue` = the agent's name. An agent keeps the
same colour in every panel and in every figure of the same agent group (the first slots of the dataviz palette, in a fixed order; at most
8 agents per figure), the legend is shared, and the footer states tag, engine hash and whether the tree was dirty.

    plot_cumulative_reward(panels, path)   panels: {title: analysis.CumulativeCurves}  reward so far, or the lead over the baseline
    plot_learning_curve(panels, path)      panels: {title: analysis.LearningCurves}    Interlude score against training time

`panels` may also be a single curves object (one panel, titled by its session). `names` maps agent ids to the names to show (default: the
labels `specs.labels` generated); `order` fixes the order of the legend and the colours.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

SURFACE, INK, INK_SECONDARY, INK_MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e7e6e2"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]   # light-mode categorical order
ERRORBAR = ("ci", 95)


def _style():
    sns.set_theme(style="white")
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                         "text.color": INK_SECONDARY, "axes.labelcolor": INK_SECONDARY, "xtick.color": INK_SECONDARY,
                         "ytick.color": INK_SECONDARY, "axes.edgecolor": GRID, "font.size": 10})


def _as_panels(panels):
    """{title: curves}; a single curves object becomes one panel titled by its session."""
    if hasattr(panels, "agents"):
        return {panels.sel.env["session"]: panels}
    return dict(panels)


def _shown_names(curves, names):
    return {aid: (names or {}).get(aid, c["label"]) for aid, c in curves.agents.items()}


def long_form(curves, names=None):
    """The per-seed curves as a long-form DataFrame (agent, seed, t, value), the input of `seaborn.lineplot`."""
    shown = _shown_names(curves, names)
    frames = []
    for aid, c in curves.agents.items():
        m = np.asarray(c["per_seed"], dtype=float)
        frames.append(pd.DataFrame({"agent": shown[aid], "seed": np.repeat(c["seeds"], m.shape[1]),
                                    "t": np.tile(np.asarray(curves.t, dtype=float), m.shape[0]), "value": m.ravel()}))
    return pd.concat(frames, ignore_index=True)


def _palette(panels, names, order):
    """{agent name: colour}: the order given, else the order of first appearance across the panels (a name keeps its colour everywhere)."""
    seen = list(order) if order else []
    for curves in panels.values():
        for name in _shown_names(curves, names).values():
            if name not in seen:
                seen.append(name)
    if len(seen) > len(SERIES):
        raise ValueError(f"{len(seen)} agents in one figure; the palette holds {len(SERIES)} (plot a group of them)")
    return seen, dict(zip(seen, SERIES))


def _grid(n):
    if n == 1:
        return 1, 1
    cols = 2 if n <= 4 else 3
    return int(np.ceil(n / cols)), cols


def _finish(fig, axes, panels, seen, palette, footer_extra=""):
    for ax in axes.flat[len(panels):]:
        ax.set_visible(False)
    handles = [Line2D([0], [0], color=palette[n], lw=2) for n in seen]
    fig.legend(handles, seen, loc="lower center", ncol=min(3, len(seen)), frameon=False, fontsize=9, labelcolor=INK_SECONDARY,
               bbox_to_anchor=(0.5, 0.02))
    first = next(iter(panels.values()))
    code = first.sel.code
    tags = ", ".join(sorted({t.split("/")[0] for panel in panels.values() for t in panel.sel.tags})) or "any"
    foot = f"tag {tags}; engine {code['engine_hash']}{', dirty tree' if code['dirty'] else ''}{footer_extra}"
    fig.text(0.01, 0.005, foot, fontsize=7.5, color=INK_MUTED)


def _axis_style(ax, title):
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold")
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    sns.despine(ax=ax, left=True)
    ax.tick_params(length=0)


def _lineplot(ax, df, seen, palette, **kw):
    present = [n for n in seen if n in set(df["agent"])]
    sns.lineplot(data=df, x="t", y="value", hue="agent", hue_order=present, palette=palette, errorbar=ERRORBAR, n_boot=1000, seed=0,
                 linewidth=2, legend=False, ax=ax, **kw)


def figure_cumulative(panels, names=None, order=None, title=None):
    """The matplotlib figure of cumulative reward (or, when the curves are advantages, the lead over each session's baseline)."""
    panels = _as_panels(panels)
    _style()
    seen, palette = _palette(panels, names, order)
    rows, cols = _grid(len(panels))
    fig, axes = plt.subplots(rows, cols, figsize=(5.6 * cols, 3.9 * rows + 0.9), squeeze=False, sharex=False)
    advantage = False
    for ax, (name, curves) in zip(axes.flat, panels.items()):
        _lineplot(ax, long_form(curves, names), seen, palette)
        _axis_style(ax, name)
        ax.set_xlim(0, curves.duration)
        ax.set_xlabel("time in session (s)")
        if curves.quantity == "advantage":
            advantage = True
            ax.axhline(0, color=INK_MUTED, linewidth=1)
            ax.text(0.99, 0.02, f"baseline: {(names or {}).get(curves.baseline_id, curves.baseline)}", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=8, color=INK_MUTED)
        else:
            ax.set_ylim(bottom=0)
        ax.set_ylabel("reward ahead of baseline" if curves.quantity == "advantage" else "cumulative reward")
    heading = title or ("Lead over the lowest-performing agent in cumulative reward" if advantage else "Cumulative reward over the session")
    fig.suptitle(heading, x=0.01, ha="left", color=INK, fontsize=13, fontweight="bold")
    note = ("paired difference to the lowest-performing agent of each session; " if advantage else "") + "mean and 95% bootstrap interval across seeds"
    fig.text(0.01, 0.945 if rows > 1 else 0.915, note, fontsize=9, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.1, 1, 0.93 if rows > 1 else 0.9))
    _finish(fig, axes, panels, seen, palette)
    return fig


def figure_learning(panels, names=None, order=None, title=None, chance=0.5):
    """The matplotlib figure of the Interlude score against training time, one panel per session."""
    panels = _as_panels(panels)
    _style()
    seen, palette = _palette(panels, names, order)
    rows, cols = _grid(len(panels))
    fig, axes = plt.subplots(rows, cols, figsize=(5.6 * cols, 3.9 * rows + 0.9), squeeze=False, sharex=False)
    for ax, (name, curves) in zip(axes.flat, panels.items()):
        accuracy = curves.metric == "interlude_accuracy"
        _lineplot(ax, long_form(curves, names), seen, palette, marker="o", markersize=5, markeredgecolor=SURFACE)
        _axis_style(ax, name)
        ax.set_xlim(curves.t[0], curves.t[-1])
        ax.set_xticks(curves.t)
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlabel("training time in the session (s)")
        if accuracy:
            ax.axhline(chance, color=INK_MUTED, linewidth=1)
            ax.text(curves.t[-1], chance, "chance", ha="right", va="bottom", fontsize=8, color=INK_MUTED)
            ax.set_ylim(0.3, 1.02)
            ax.set_ylabel("Interlude accuracy")
        else:
            ax.set_ylim(bottom=0)
            ax.set_ylabel(curves.metric.replace("_", " "))
    fig.suptitle(title or "Interlude score against training time", x=0.01, ha="left", color=INK, fontsize=13, fontweight="bold")
    env = next(iter(panels.values())).sel.env
    fig.text(0.01, 0.945 if rows > 1 else 0.915, f"{env.get('interlude_mode', '?')} Interlude, {env.get('n_samples', '?')} pick per trial; a copy of the agent as it was "
             "at each time; mean and 95% bootstrap interval across seeds", fontsize=9, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.1, 1, 0.93 if rows > 1 else 0.9))
    _finish(fig, axes, panels, seen, palette)
    return fig


def _save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_cumulative_reward(panels, path, **kw):
    """Save `figure_cumulative`; returns the path."""
    return _save(figure_cumulative(panels, **kw), path)


def plot_learning_curve(panels, path, **kw):
    """Save `figure_learning`; returns the path."""
    return _save(figure_learning(panels, **kw), path)
