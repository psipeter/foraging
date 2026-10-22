"""Figures for the results database (matplotlib, saved as PNG; nothing here queries the database).

Style follows the dataviz skill: thin 2 px lines, the first categorical slots in a fixed order (blue, orange, aqua, ...), a 95% band in the
same hue at low opacity, hairline recessive grid, text in ink (never the series color), a legend for two or more series plus direct
labels at the line ends where they do not collide. Aqua is below 3:1 against the light surface, so the legend and direct labels are
the relief the palette needs."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402

SURFACE, INK, INK_SECONDARY, INK_MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e7e6e2"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]   # light-mode categorical order


def _style():
    sns.set_theme(style="white")
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                         "text.color": INK_SECONDARY, "axes.labelcolor": INK_SECONDARY, "xtick.color": INK_SECONDARY,
                         "ytick.color": INK_SECONDARY, "axes.edgecolor": GRID, "font.size": 10})


def plot_reward_rate(curves, path, title=None, colors=None):
    """Save the figure of `analysis.RateCurves`: mean reward per second against session time, one line per agent with its
    confidence band. Returns the path written."""
    _style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ids = list(curves.agents)
    colors = colors or {a: SERIES[i % len(SERIES)] for i, a in enumerate(ids)}
    ends = []
    for a in ids:
        c = curves.agents[a]
        ax.fill_between(curves.t, c["lo"], c["hi"], color=colors[a], alpha=0.16, linewidth=0)
        ax.plot(curves.t, c["mean"], color=colors[a], linewidth=2, solid_capstyle="round", solid_joinstyle="round", label=f"{c['label']} (n={c['n']})")
        ends.append((c["mean"][-1], a))
    ax.set_xlim(0, curves.duration)
    quantity = getattr(curves, "quantity", "rate")
    if quantity == "advantage":
        ax.axhline(0, color=INK_MUTED, linewidth=1)
        ax.text(curves.duration, 0, f"{curves.baseline}", ha="right", va="bottom", fontsize=8, color=INK_MUTED)
    else:
        ax.set_ylim(bottom=0)
    ax.set_xlabel("time in session (s)")
    ax.set_ylabel({"rate": "reward per second", "cumulative": "cumulative reward", "advantage": "cumulative reward ahead of the baseline"}[quantity])
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    sns.despine(ax=ax, left=True)
    ax.tick_params(length=0)
    # direct labels at the line ends, only where neighbours are far enough apart (otherwise the legend carries identity)
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    ends.sort()
    for i, (y, a) in enumerate(ends):
        gaps = [abs(y - o) for j, (o, _) in enumerate(ends) if j != i]
        if not gaps or min(gaps) > 0.07 * span:
            ax.plot([curves.t[-1]], [y], marker="o", markersize=7, color=colors[a], markeredgecolor=SURFACE, markeredgewidth=2, clip_on=False)
    if len(ids) > 1:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1, frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    sel = curves.sel
    if quantity == "rate":
        smoothing = f"; {curves.params['bin_seconds']:g} s bins" if curves.smoothing == "bin" else f"; Gaussian low-pass, sigma {curves.params['sigma']:g} s"
        heading, note = f"Reward rate over the session: {sel.env['session']}", f"mean and {curves.confidence:.0%} interval across seeds{smoothing}"
    elif quantity == "cumulative":
        heading, note = f"Cumulative reward over the session: {sel.env['session']}", f"mean and {curves.confidence:.0%} interval across seeds"
    else:
        heading = f"Lead over the baseline in cumulative reward: {sel.env['session']}"
        note = f"paired difference to the baseline in the same worlds; mean and {curves.confidence:.0%} interval across seeds"
    ax.set_title(title or heading, loc="left", color=INK, fontsize=12, fontweight="bold", pad=22)
    ax.text(0, 1.03, note, transform=ax.transAxes, fontsize=9, color=INK_MUTED)
    code = sel.code
    foot = f"engine {code['engine_hash']}, environment {sel.env_id}{', dirty tree' if code['dirty'] else ''}" + (f"; tag {', '.join(sel.tags)}" if sel.tags else "")
    fig.text(0.01, 0.005, foot, fontsize=7.5, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_learning_curve(curves, path, title=None, colors=None, chance=0.5):
    """Save the figure of `analysis.LearningCurves`: the Interlude score of a copy of each agent against the seconds it had trained, mean
    and confidence band across seeds. A thin reference line marks chance for an accuracy metric. Returns the path written."""
    _style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ids = list(curves.agents)
    colors = colors or {a: SERIES[i % len(SERIES)] for i, a in enumerate(ids)}
    accuracy = curves.metric == "interlude_accuracy"
    for a in ids:
        c = curves.agents[a]
        ax.fill_between(curves.t, c["lo"], c["hi"], color=colors[a], alpha=0.16, linewidth=0)
        ax.plot(curves.t, c["mean"], color=colors[a], linewidth=2, marker="o", markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5,
                solid_capstyle="round", solid_joinstyle="round", label=f"{c['label']} (n={c['n']})")
    if accuracy:
        ax.axhline(chance, color=INK_MUTED, linewidth=1)
        ax.text(curves.t[-1], chance, "chance", ha="right", va="bottom", fontsize=8, color=INK_MUTED)
        import numpy as np
        ax.set_ylim(min(0.4, float(np.nanmin([c['lo'] for c in curves.agents.values()])) - 0.02), 1.02)
    else:
        ax.set_ylim(bottom=0)
    ax.set_xlim(curves.t[0], curves.t[-1])
    ax.set_xticks(curves.t)
    ax.set_xlabel("training time in the session (s)")
    ax.set_ylabel("Interlude accuracy" if accuracy else curves.metric.replace("_", " "))
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    sns.despine(ax=ax, left=True)
    ax.tick_params(length=0)
    if len(ids) > 1:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1, frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    sel = curves.sel
    env = sel.env
    ax.set_title(title or f"Learning curve: {env['session']}", loc="left", color=INK, fontsize=12, fontweight="bold", pad=22)
    ax.text(0, 1.03, f"{env.get('interlude_mode', '?')} Interlude, {env.get('n_samples', '?')} samples per trial; mean and {curves.confidence:.0%} "
            "interval across seeds; a copy of the agent as it was at each time", transform=ax.transAxes, fontsize=9, color=INK_MUTED)
    code = sel.code
    foot = f"engine {code['engine_hash']}, environment {sel.env_id}{', dirty tree' if code['dirty'] else ''}" + (f"; tag {', '.join(sel.tags)}" if sel.tags else "")
    fig.text(0.01, 0.005, foot, fontsize=7.5, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
