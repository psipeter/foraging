"""Figures for the results database (matplotlib and seaborn, saved as PNG; nothing here queries the database).

Every figure is a grid of panels, one per session (2 x 2 for S1 to S4; one panel for a single selection), with one line per agent drawn by
`seaborn.lineplot` from the per-seed curves: the mean over seeds and a 95% bootstrap interval, `hue` = the agent's name. An agent keeps the
same colour in every panel and in every figure of the same agent group (a `glasbey` colour-blind-safe palette in a fixed order; at most
8 agents per figure, with a warning above 5), each with its own linestyle, the legend is shared, and the footer states tag, engine hash and whether the tree was dirty.

    plot_cumulative_reward(panels, path)   panels: {title: analysis.CumulativeCurves}  reward so far, or the lead over the baseline
    plot_learning_curve(panels, path)      panels: {title: analysis.LearningCurves}    Interlude score against training time

`panels` may also be a single curves object (one panel, titled by its session). `names` maps agent ids to the names to show (default: the
labels `specs.labels` generated); `order` fixes the order of the legend and the colours.
"""

import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

INK_MUTED = ".5"   # seaborn grey for annotations and the footer
SERIES = ["#1b4cff", "#c92100", "#ffc300", "#ce98ff", "#00726d", "#e4825c", "#21f4c9", "#0bae92"]   # glasbey, colour-blind safe (deuteranopia, severity 100); the first MAX_DISTINCT are the default
# matplotlib's named linestyles (solid, dashed, dashdot, dotted) plus a dash-dot-dot, then three extras; an agent's style goes with its colour
STYLES = ["-", (0, (3.7, 1.6)), (0, (6.4, 1.6, 1, 1.6)), (0, (1, 1.65)), (0, (3, 1, 1, 1, 1, 1)), (0, (5, 10)), (0, (5, 1)), (0, (1, 10))]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]   # an agent's (or participant's) marker in the Interlude strip of `figure_points`, in the order of the colours
ERRORBAR = ("ci", 95)
MAX_DISTINCT = 5   # lines per figure that colour alone separates for most viewers, colour-blind ones included


# Sizes follow the evidence_integration project (utils/plot_style.py, scripts/make_figures.py): a paper figure is the textwidth of a letter page
# (6.5 in) with 9 pt text; a presentation figure is the 10.6 in slide width with 15 pt text. `panel_height` and `extra_height` (title, legend and
# footer, in inches) are foraging's own: a figure is `rows * panel_height + extra_height` tall.
MODES = {
    "paper": {"width": 6.5, "panel_height": 2.5, "extra_height": 1.1, "dpi": 300,
              "rc": {"font.size": 9, "axes.labelsize": 9, "axes.titlesize": 10, "xtick.labelsize": 8, "ytick.labelsize": 8,
                     "legend.fontsize": 8, "axes.linewidth": 0.8, "xtick.major.width": 0.8, "ytick.major.width": 0.8}},
    "presentation": {"width": 10.6, "panel_height": 3.8, "extra_height": 1.6, "dpi": 200,
                     "rc": {"font.size": 15, "axes.labelsize": 17, "axes.titlesize": 18, "xtick.labelsize": 13, "ytick.labelsize": 13,
                            "legend.fontsize": 14, "axes.linewidth": 1.2, "xtick.major.width": 1.2, "ytick.major.width": 1.2}},
}
DEFAULT_MODE = "paper"


def _style(mode):
    """Seaborn's ticks theme (white, no grid) with the mode's font and line sizes; returns the mode's entry of `MODES`."""
    if mode not in MODES:
        raise ValueError(f"mode {mode!r}; choose from {sorted(MODES)}")
    sns.set_theme(style="ticks")
    plt.rcParams.update({"font.family": "sans-serif", "savefig.dpi": MODES[mode]["dpi"], **MODES[mode]["rc"]})
    return MODES[mode]


def _small():
    """Font size of annotations, subtitles and footers: the tick labels'."""
    return plt.rcParams["xtick.labelsize"]


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
    if len(seen) > MAX_DISTINCT:
        warnings.warn(f"{len(seen)} agents in one figure; more than {MAX_DISTINCT} lines are hard to tell apart by colour, "
                      f"especially for colour-blind readers (plot a group of them)", stacklevel=3)
    return seen, dict(zip(seen, SERIES))


def _legend_rows(n_agents):
    return int(np.ceil(n_agents / min(3, n_agents)))


def _margins(n_agents):
    """Inches above the panels (title, subtitle) and below them (legend, footer), from the font sizes, so the text never overlaps."""
    title, small, legend = plt.rcParams["axes.titlesize"], _small(), plt.rcParams["legend.fontsize"]
    top = 0.08 + (title + small) * 1.3 / 72 + 0.12
    footer = 0.06 + (small - 1) * 1.3 / 72
    return top, footer, footer + 0.05 + _legend_rows(n_agents) * legend * 1.6 / 72 + 0.1


def _figsize(cfg, rows, n_agents):
    """Width and height in inches: the panels, the mode's margins, and a row of legend for each three agents."""
    extra = (_legend_rows(n_agents) - 1) * plt.rcParams["legend.fontsize"] * 1.6 / 72
    return cfg["width"], cfg["panel_height"] * rows + cfg["extra_height"] + extra


def _header(fig, heading, note, n_agents, **layout):
    """Title and subtitle at the top left, and the panels laid out between the margins."""
    top, footer, bottom = _margins(n_agents)
    height = fig.get_figheight()
    fig.text(0.01, 1 - 0.08 / height, heading, ha="left", va="top", fontsize=plt.rcParams["axes.titlesize"], fontweight="bold")   # not suptitle: tight_layout would reserve room for it
    fig.text(0.01, 1 - (0.08 + plt.rcParams["axes.titlesize"] * 1.3 / 72) / height, note, va="top", fontsize=_small(), color=INK_MUTED)
    fig.tight_layout(rect=(0, bottom / height, 1, 1 - top / height), **layout)


def _grid(n):
    if n == 1:
        return 1, 1
    cols = 2 if n <= 4 else 3
    return int(np.ceil(n / cols)), cols


def _finish(fig, axes, panels, seen, palette, footer_extra="", markers=None):
    for ax in axes.flat[len(panels):]:
        ax.set_visible(False)
    handles = [Line2D([0], [0], color=palette[n], lw=2, ls=ls, marker=m, markersize=6, markeredgecolor="white")
               for n, ls, m in zip(seen, STYLES, markers or [None] * len(seen))]
    fig.legend(handles, seen, loc="lower center", ncol=min(3, len(seen)), frameon=False,
               bbox_to_anchor=(0.5, (_margins(len(seen))[1] + 0.05) / fig.get_figheight()))
    first = next(iter(panels.values()))
    foot = []
    if first.sel is not None:
        code = first.sel.code
        tags = ", ".join(sorted({t.split("/")[0] for panel in panels.values() for t in panel.sel.tags})) or "any"
        foot.append(f"tag {tags}; engine {code['engine_hash']}{', dirty tree' if code['dirty'] else ''}")
    foot += [f for f in dict.fromkeys(getattr(panel, "footer", None) for panel in panels.values()) if f]
    foot = "; ".join(foot) + footer_extra
    fig.text(0.01, 0.06 / fig.get_figheight(), foot, va="bottom", fontsize=_small() - 1, color=INK_MUTED)


def _axis_style(ax, title):
    ax.set_title(title)
    sns.despine(ax=ax)


def _lineplot(ax, df, seen, palette, **kw):
    """Each series as its mean and interval over seeds (a series of one seed, such as a participant, is a plain line)."""
    present = [n for n in seen if n in set(df["agent"])]
    dashes = {n: ("" if ls == "-" else ls[1]) for n, ls in zip(seen, STYLES)}   # seaborn spells solid "" and a dash pattern as its (on, off, ...)
    sns.lineplot(data=df, x="t", y="value", hue="agent", hue_order=present, palette=palette, style="agent", style_order=present, dashes=dashes,
                 errorbar=ERRORBAR, n_boot=1000, seed=0, linewidth=2, legend=False, ax=ax, **kw)


def _lowest_tick(*panel_sets):
    """The lowest accuracy tick: 0.5 (chance) unless a series (a participant, or an agent's mean) goes below it."""
    low = min((c["per_seed"] if c["n"] == 1 else c["mean"]).min() for panels in panel_sets for curves in panels.values() for c in curves.agents.values())
    return 0.5 if low > 0.44 else np.floor(low * 10 + 1e-9) / 10


def figure_cumulative(panels, names=None, order=None, title=None, mode=DEFAULT_MODE):
    """The matplotlib figure of cumulative reward (or, when the curves are advantages, the lead over each session's baseline)."""
    panels = _as_panels(panels)
    cfg = _style(mode)
    seen, palette = _palette(panels, names, order)
    rows, cols = _grid(len(panels))
    fig, axes = plt.subplots(rows, cols, figsize=_figsize(cfg, rows, len(seen)), squeeze=False, sharex=True)
    advantage = False
    for ax, (name, curves) in zip(axes.flat, panels.items()):
        _lineplot(ax, long_form(curves, names), seen, palette)
        _axis_style(ax, name)
        if curves.quantity == "advantage":
            advantage = True
            ax.axhline(0, color=INK_MUTED, linewidth=1)
            ax.text(0.02, 0.97, f"baseline: {(names or {}).get(curves.baseline_id, curves.baseline)}", transform=ax.transAxes,
                    ha="left", va="top", fontsize=_small(), color=INK_MUTED)
            ax.set_ylabel("reward ahead of baseline")
        else:
            ax.set_ylim(bottom=0)
            ax.set_ylabel("cumulative reward")
    axes.flat[0].set_xlim(0, max(curves.duration for curves in panels.values()))   # the x axis is shared, each panel has its own y axis
    for i, ax in enumerate(axes.flat[:len(panels)]):
        if i + cols >= len(panels):
            ax.set_xlabel("time in session (s)")
    heading = title or ("Lead over the lowest-performing agent in cumulative reward" if advantage else "Cumulative reward over the session")
    note = getattr(next(iter(panels.values())), "note", None) or (
        ("paired difference to the lowest-performing agent of each session; " if advantage else "") + "mean and 95% bootstrap interval across seeds")
    _header(fig, heading, note, len(seen))
    _finish(fig, axes, panels, seen, palette)
    return fig


def figure_learning(panels, names=None, order=None, title=None, mode=DEFAULT_MODE):
    """The matplotlib figure of the Interlude score against training time, one panel per session."""
    panels = _as_panels(panels)
    cfg = _style(mode)
    seen, palette = _palette(panels, names, order)
    rows, cols = _grid(len(panels))
    fig, axes = plt.subplots(rows, cols, figsize=_figsize(cfg, rows, len(seen)), squeeze=False, sharex=True, sharey=True)
    lowest_tick = _lowest_tick(panels)
    for ax, (name, curves) in zip(axes.flat, panels.items()):
        accuracy = curves.metric == "interlude_accuracy"
        _lineplot(ax, long_form(curves, names), seen, palette, marker="o", markersize=5, markeredgecolor="white")
        _axis_style(ax, name)
        ax.set_xlabel("training time in the session (s)")
        if accuracy:
            ax.set_ylim(lowest_tick - 0.05, 1.02)   # chance is 0.5: room below it for the line and its interval only
            ax.set_yticks(np.arange(lowest_tick, 1.001, 0.1))
            ax.set_ylabel("Interlude accuracy")
        else:
            ax.set_ylim(bottom=0)
            ax.set_ylabel(curves.metric.replace("_", " "))
    axes.flat[0].set_xlim(0, 1.03 * max(curves.t[-1] for curves in panels.values()))   # the x axis is shared; room for the last markers
    for ax in axes.flat:
        ax.label_outer()
    first = next(iter(panels.values()))
    if getattr(first, "note", None):
        note = first.note
    else:
        env = first.sel.env
        note = (f"{env.get('interlude_mode', '?')} Interlude, {env.get('n_samples', '?')} pick per trial; a copy of the agent as it was "
                "at each time; mean and 95% bootstrap interval across seeds")
    _header(fig, title or "Interlude score against training time", note, len(seen))
    _finish(fig, axes, panels, seen, palette)
    return fig


def point_limits(*figures):
    """Axis limits for `figure_points` shared by several figures, so that they can be compared: `figures` are (panels, interlude) pairs. Returns
    {"points": {session: top of the points axis}, "longest": the longest session, "accuracy_low": the lowest accuracy tick, in %}."""
    top, longest = {}, 0.0
    for panels, _ in figures:
        for session, curves in panels.items():
            longest = max(longest, curves.duration)
            for c in curves.agents.values():
                interval = c["hi"][np.isfinite(c["hi"])]
                top[session] = max(top.get(session, 0.0), float(np.max(c["mean"])), float(interval.max()) if len(interval) else 0.0)
    return {"points": {session: 1.05 * value for session, value in top.items()}, "longest": longest,
            "accuracy_low": 100 * _lowest_tick(*[interlude for _, interlude in figures])}


def figure_points(panels, interlude, names=None, order=None, title=None, mode=DEFAULT_MODE, limits=None):
    """One row per session: the points collected so far against session time, and on a twinned y axis (right, Interlude accuracy in %) the
    Interlude accuracy of the end of the session, a marker just right of where the line ends (all at the same x, so equal scores overlap). A series
    has one colour and linestyle in its line and one marker on the twin axis; a series of several seeds is its mean and 95% interval there.
    `panels`: {session: CumulativeCurves}; `interlude`: {session: LearningCurves} (only the last checkpoint of each series is drawn).
    `limits` (from `point_limits`): the axis limits, to share them with another figure; by default those of this figure's data."""
    panels = _as_panels(panels)
    limits = limits or point_limits((panels, interlude))
    cfg = _style(mode)
    seen, palette = _palette(panels, names, order)
    rows = len(panels)
    fig, axes = plt.subplots(rows, 1, figsize=_figsize(dict(cfg, panel_height=0.8 * cfg["panel_height"]), rows, len(seen)), squeeze=False, sharex=True)
    longest = limits["longest"]
    step = 0.04 * longest                                    # the gap between where a session ends and its Interlude markers (all at one x)
    lowest_tick = limits["accuracy_low"]
    for i, (ax, (session, curves)) in enumerate(zip(axes[:, 0], panels.items())):
        _lineplot(ax, long_form(curves, names), seen, palette)
        _axis_style(ax, session)
        ax.set_ylim(0, limits["points"][session])
        ax.set_ylabel("points")
        ax.set_xlabel("time in session (s)" if i == rows - 1 else "")
        twin = ax.twinx()
        learned = {names.get(aid, c["label"]) if names else c["label"]: c for aid, c in interlude[session].agents.items()} if session in interlude else {}
        for k, name in enumerate(seen):
            if name not in learned:
                continue
            c = learned[name]
            y, lo, hi = 100 * c["mean"][-1], 100 * c["lo"][-1], 100 * c["hi"][-1]
            err = [[y - lo], [hi - y]] if c["n"] > 1 and np.isfinite(lo) else None
            twin.errorbar(curves.duration + step, y, yerr=err, fmt=MARKERS[k], color=palette[name], markersize=6, markeredgecolor="white",
                          elinewidth=1.5, capsize=0)
        twin.set_ylim(lowest_tick - 5, 102)
        twin.set_yticks(np.arange(lowest_tick, 100.1, 10))
        twin.set_ylabel("Interlude accuracy (%)")
        sns.despine(ax=twin, left=True, right=False)
    axes[0, 0].set_xlim(0, longest + 2 * step)
    axes[0, 0].set_xticks([t for t in axes[0, 0].get_xticks() if 0 <= t <= longest])
    note = getattr(next(iter(panels.values())), "note", None) or "mean and 95% bootstrap interval across seeds"
    _header(fig, title or "Points over the session and Interlude accuracy", note, len(seen))
    _finish(fig, axes, panels, seen, palette, markers=MARKERS)
    return fig


def _save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_cumulative_reward(panels, path, **kw):
    """Save `figure_cumulative`; returns the path."""
    return _save(figure_cumulative(panels, **kw), path)


def plot_learning_curve(panels, path, **kw):
    """Save `figure_learning`; returns the path."""
    return _save(figure_learning(panels, **kw), path)


def plot_points(panels, interlude, path, **kw):
    """Save `figure_points`; returns the path."""
    return _save(figure_points(panels, interlude, **kw), path)
