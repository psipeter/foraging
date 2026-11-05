"""Idle windows in participants' play: when are they not doing anything, for how long, and what comes before and after.

Exploratory (the question: the simulated agents act without delay, participants do not; what would a fair "human-like"
down time look like?). Reads the local layout of rundata.py (ForagingData/<run>/<session>/) through replay.load_session_log.

Two definitions of "not acting", both computed from trajectory.csv (one row per rendered frame; keys: 1 forward, 2 back, 4 harvest):
  strict      no key held and the view not turning (mouse still): the participant is doing nothing the game can see.
  stationary  no key held (turning the view is allowed): not walking or harvesting, though possibly looking around.
Turning is a *burst*: frames whose view moved (yaw/pitch changed), joined while less than BURST_GAP apart; a burst whose total
angle is below `min_turn` degrees is treated as hand tremor and is not activity (`--min-turn`, default 0.5 deg).
A window runs from the last frame of activity to the first frame of the next one; the first window of a session starts at 0
(prev "start") and the last ends with the session (next "end", censored). Only windows of at least `--min-dur` seconds are kept.

    ./venv/bin/python scripts/idle_analysis.py [--runs ID,ID] [--min-dur 0.3] [--min-turn 0.5] [--interludes] [--save]

`--save` writes results/idle_windows_<mode>.csv and results/idle_pauses.png (from the stationary windows). Session time `t` excludes every pause the game held
(instructions, uploads), so held time is never counted as idle.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "ForagingData"
BURST_GAP = 0.1        # s: look movement this close together is one burst
TOL = 0.02             # s: slack when matching a frame to a harvest bout's press and release
MAIN = ("P", "S1", "S2", "S3", "S4", "S5")


def finished_runs():
    """{participant: run_id} of the finished online runs (run.json status), in the order of their start."""
    out = {}
    for run in sorted(DATA.glob("*/run.json"), key=lambda p: p.stat().st_mtime):
        info = replay.json.loads(run.read_text())
        if info.get("status") == "finished":
            out[info.get("participant") or run.parent.name[:8]] = run.parent.name
    return out


def bouts_of(events, n_fruits):
    """Harvest bouts: dicts press, release, tree, n (fruits), mean (reward per fruit), exhausted."""
    fruits = {}
    for e in events:
        if e["type"] == "fruit":
            fruits.setdefault(e["tree_id"], []).append((e["t"], e["reward"]))
    out, open_ = [], None
    for e in events:
        if e["type"] == "harvest_press":
            open_ = e
        elif e["type"] == "harvest_release" and open_ is not None:
            got = [r for t, r in fruits.get(open_["tree_id"], []) if open_["t"] - TOL <= t <= e["t"] + TOL]
            total_taken = sum(1 for t, _ in fruits.get(open_["tree_id"], []) if t <= e["t"] + TOL)
            out.append({"press": open_["t"], "release": e["t"], "tree": open_["tree_id"], "n": len(got),
                        "mean": float(np.mean(got)) if got else np.nan, "exhausted": total_taken >= n_fruits})
            open_ = None
    return out


def activity(traj, look_counts, min_turn):
    """Per-frame boolean activity and the per-frame view movement (degrees)."""
    t, keys = traj[:, 0], traj[:, 5].astype(int)
    move = np.r_[0.0, np.hypot(np.diff(traj[:, 3]), np.diff(traj[:, 4]))]
    key_active = keys > 0
    look = np.zeros(len(t), dtype=bool)
    if look_counts:
        idx = np.flatnonzero(move > 0)
        groups, cur = [], [idx[0]] if len(idx) else []
        for j in idx[1:]:
            if t[j] - t[cur[-1]] <= BURST_GAP:
                cur.append(j)
            else:
                groups.append(cur)
                cur = [j]
        if cur:
            groups.append(cur)
        for g in groups:
            if move[g].sum() >= min_turn:
                look[g[0]:g[-1] + 1] = True
    return key_active | look, move, keys


def nearest_bush_state(log, x, z, yaw, taken):
    """(state, edge distance of the nearest unspent bush, bearing excess of the closest-in-range one) of a pose."""
    cfg = log.config
    b = log.bushes
    live = np.flatnonzero(taken < b.fruit_reward.shape[1])
    edge, excess = replay._measure(b, live, x, z, yaw)
    gap = cfg["harvestRangeGapBase"] + cfg["harvestRangeGapPerRadius"] * b.canopy_radius[live]
    inr = edge <= gap
    if inr.any() and (excess[inr] <= cfg["harvestMaxAngle"]).any():
        return "ready", float(edge.min())
    return ("in range, not facing" if inr.any() else "no bush in range"), float(edge.min())


def windows_of(log, look_counts, min_dur, min_turn):
    tr = log.traj
    t = tr[:, 0]
    act, move, keys = activity(tr, look_counts, min_turn)
    n_fruits = log.bushes.fruit_reward.shape[1]
    bouts = bouts_of(log.events, n_fruits)
    fruit_t = np.array([(e["t"], e["tree_id"]) for e in log.events if e["type"] == "fruit"])
    rows = []

    def kind(i):
        if keys[i] & 4:
            return "harvest" if any(b["press"] - TOL <= t[i] <= b["release"] + TOL for b in bouts) else "tap"
        return "walk" if keys[i] & 3 else "look"

    edges = np.flatnonzero(np.diff(act.astype(int)) != 0) + 1          # frames where the activity flag flips
    starts = list(edges[~act[edges]]) if len(edges) else []            # first frame of each inactive run
    if not act[0]:
        starts = [0] + [s for s in starts if s != 0]
    for s in starts:
        e = s
        while e < len(t) and not act[e]:
            e += 1
        t0 = t[s - 1] if s > 0 else 0.0
        end = e < len(t)
        t1 = t[e] if end else t[-1]
        if t1 - t0 < min_dur:
            continue
        prev = "start" if s == 0 else kind(s - 1)
        nxt = kind(e) if end else "end"
        b_prev = [b for b in bouts if b["release"] <= t0 + TOL]
        b_prev = b_prev[-1] if b_prev else None
        taken = np.zeros(len(log.bushes.pos), dtype=int)
        for tt, tid in fruit_t:
            if tt <= t0:
                taken[int(tid)] += 1
        ref = max(s - 1, 0)
        state0, edge0 = nearest_bush_state(log, tr[ref, 1], tr[ref, 2], tr[ref, 3], taken)
        ie = min(e, len(t) - 1)
        state1, _ = nearest_bush_state(log, tr[ie, 1], tr[ie, 2], tr[ie, 3], taken)
        inside = (t > t0) & (t <= t1)
        rows.append({
            "t0": t0, "t1": t1, "dur": t1 - t0, "prev": prev, "next": nxt, "censored": not end,
            "turned": float(move[inside].sum()), "ready_start": state0, "ready_end": state1, "edge_start": edge0,
            "bout_mean": b_prev["mean"] if b_prev else np.nan, "bout_n": b_prev["n"] if b_prev else np.nan,
            "bout_exhausted": b_prev["exhausted"] if b_prev else np.nan,
            "since_bout": t0 - b_prev["release"] if b_prev else np.nan})
    return rows


def collect(runs, sessions, look_counts, min_dur, min_turn):
    out, span = [], []
    for who, run in runs.items():
        for folder in sorted((DATA / run).glob("[0-9][0-9]")):
            log = replay.load_session_log(folder)
            if log.name not in sessions:
                continue
            for w in windows_of(log, look_counts, min_dur, min_turn):
                out.append({"who": who, "session": log.name, "length": float(log.traj[-1, 0]), **w})
            span.append({"who": who, "session": log.name, "length": float(log.traj[-1, 0]), "score": log.final_score})
    return pd.DataFrame(out), pd.DataFrame(span)


def budget(runs, sessions, min_turn):
    """Where every frame's time goes, per participant and session: harvesting (inside a bout), walking (W held outside a bout),
    wasted taps (Space held outside a bout), turning (no key, the view moving), still (no key, nothing moving); plus bouts."""
    rows = []
    for who, run in runs.items():
        for folder in sorted((DATA / run).glob("[0-9][0-9]")):
            log = replay.load_session_log(folder)
            if log.name not in sessions:
                continue
            tr = log.traj
            t, keys = tr[:, 0], tr[:, 5].astype(int)
            dt = np.r_[np.diff(t), 0.0]
            bouts = bouts_of(log.events, log.bushes.fruit_reward.shape[1])
            inb = np.zeros(len(t), dtype=bool)
            for b in bouts:
                inb |= (t >= b["press"] - TOL) & (t <= b["release"] + TOL)
            turning, *_ = activity(tr, True, min_turn)
            turning &= keys == 0
            cls = {"harvest": inb | ((keys & 4 > 0) & inb), "walk": (keys & 3 > 0) & ~inb, "tap": (keys & 4 > 0) & ~inb & (keys & 3 == 0)}
            cls["turn"] = turning & ~inb
            cls["still"] = ~(cls["harvest"] | cls["walk"] | cls["tap"] | cls["turn"])
            row = {"who": who, "session": log.name, "length": float(t[-1]), "score": log.final_score, "bouts": len(bouts),
                   "fruits": sum(b["n"] for b in bouts), "full_bouts": sum(b["exhausted"] for b in bouts)}
            row.update({k: float(dt[v].sum() / t[-1]) for k, v in cls.items()})
            rows.append(row)
    return pd.DataFrame(rows)


def report_budget(b):
    print("\n=== time budget (share of session time; harvest = inside a bout, walk = W held, tap = Space held outside a bout, "
          "turn = no key but the view moving, still = nothing)")
    cols = ["harvest", "walk", "tap", "turn", "still"]
    pooled = b.groupby("who").apply(lambda g: pd.Series({c: (g[c] * g.length).sum() / g.length.sum() for c in cols}), include_groups=False)
    print((pooled * 100).round(1).to_string())
    print("\n-- by session (pooled over participants)")
    by = b.groupby("session").apply(lambda g: pd.Series({c: (g[c] * g.length).sum() / g.length.sum() for c in cols}), include_groups=False)
    print((by.reindex([m for m in MAIN if m in by.index]) * 100).round(1).to_string())
    b = b.assign(fruits_per_bout=b.fruits / b.bouts, full_share=b.full_bouts / b.bouts, fruits_per_min=b.fruits / b.length * 60)
    print("\n-- bouts, fruits per bout, share of bouts that took every fruit, fruits per minute, score")
    print(b[["who", "session", "bouts", "fruits_per_bout", "full_share", "fruits_per_min", "score"]].round(2).to_string(index=False))


def quant(x, qs=(0.25, 0.5, 0.75, 0.9, 0.99)):
    return "  ".join(f"p{int(q * 100)} {np.quantile(x, q):.2f}" for q in qs)


def report(df, span, label):
    d = df[~df.censored]
    print(f"\n=== {label}: {len(df)} windows ({len(df) - len(d)} cut by the session's end), {len(span)} sessions, "
          f"{span.length.sum():.0f} s of play")
    tot = df.groupby(["who", "session"]).dur.sum().reindex(pd.MultiIndex.from_frame(span[["who", "session"]]), fill_value=0)
    share = tot.values / span.length.values
    print(f"idle share of session time: mean {share.mean():.1%}   (all windows: {df.dur.sum() / span.length.sum():.1%} of play time)")
    print(f"duration, all windows: mean {df.dur.mean():.2f}  median {df.dur.median():.2f}  {quant(df.dur)}  max {df.dur.max():.1f}")
    print(f"windows per minute of play: {len(df) / span.length.sum() * 60:.1f}")

    print("\n-- per participant (all sessions pooled)")
    g = df.groupby("who").dur
    s = span.groupby("who").length.sum()
    t = pd.DataFrame({"n": g.size(), "per_min": g.size() / s * 60, "share": g.sum() / s, "mean": g.mean(), "median": g.median(),
                      "p90": g.quantile(0.9), "max": g.max()})
    print(t.round(2).to_string())

    print("\n-- per session (all participants), idle share, windows per minute")
    g = df.groupby("session").dur
    s = span.groupby("session").length.sum()
    t = pd.DataFrame({"n": g.size(), "per_min": g.size() / s * 60, "share": g.sum() / s, "median": g.median(), "p90": g.quantile(0.9)})
    print(t.reindex([m for m in MAIN if m in t.index]).round(2).to_string())

    print("\n-- participant x session: idle share of the session")
    a = (df.groupby(["who", "session"]).dur.sum() / span.set_index(["who", "session"]).length).unstack()
    print((a.reindex(columns=[m for m in MAIN if m in a.columns]) * 100).round(1).to_string())

    print("\n-- what comes before (rows) and after (columns): share of windows, then median duration (s)")
    pn = pd.crosstab(df.prev, df.next)
    print((pn / len(df) * 100).round(1).to_string())
    print(df.pivot_table(index="prev", columns="next", values="dur", aggfunc="median").round(2).to_string())

    print("\n-- by previous action: n, median, mean, p90, total time share of all idle")
    g = df.groupby("prev").dur
    print(pd.DataFrame({"n": g.size(), "median": g.median(), "mean": g.mean(), "p90": g.quantile(0.9), "idle_time_share": g.sum() / df.dur.sum()}).round(2).to_string())
    print("\n-- by next action")
    g = df.groupby("next").dur
    print(pd.DataFrame({"n": g.size(), "median": g.median(), "mean": g.mean(), "p90": g.quantile(0.9), "idle_time_share": g.sum() / df.dur.sum()}).round(2).to_string())

    print("\n-- where the participant stood when the window began / ended (nearest unspent bush)")
    print(pd.crosstab(df.ready_start, df.ready_end).to_string())
    g = df.groupby("ready_start").dur
    print(pd.DataFrame({"n": g.size(), "median": g.median(), "mean": g.mean(), "idle_time_share": g.sum() / df.dur.sum()}).round(2).to_string())

    print("\n-- windows that follow a harvest bout (prev = harvest): by whether it emptied the bush and by its mean reward")
    h = df[df.prev == "harvest"]
    print(h.groupby("bout_exhausted").dur.agg(["size", "median", "mean"]).round(2).to_string())
    h = h.assign(rwd=pd.cut(h.bout_mean, [-0.01, 1, 2, 3, 10], labels=["<=1", "1-2", "2-3", ">3"]))
    print(h.groupby("rwd", observed=True).dur.agg(["size", "median", "mean"]).round(2).to_string())
    from scipy import stats
    ok = h.dropna(subset=["bout_mean"])
    if len(ok) > 5:
        r = stats.spearmanr(ok.bout_mean, ok.dur)
        print(f"Spearman(duration, last bout's mean reward) = {r.statistic:.2f} (p = {r.pvalue:.3f}, n = {len(ok)})")

    print("\n-- time in the session: windows per minute and median duration by session-time quarter (pooled)")
    q = pd.cut(df.t0 / df.length, [0, .25, .5, .75, 1.0001], labels=["Q1", "Q2", "Q3", "Q4"], include_lowest=True)
    print(df.groupby(q, observed=True).dur.agg(["size", "median", "mean", "sum"]).round(2).to_string())
    print(f"first window of each session (prev = start): median {df[df.prev == 'start'].dur.median():.2f} s, "
          f"max {df[df.prev == 'start'].dur.max():.1f} s")

    print("\n-- survival: share of windows lasting at least")
    for m in (0.3, 0.5, 1, 2, 3, 5, 10):
        print(f"  >= {m:>4} s: {(df.dur >= m).mean():.1%} of windows, {df.dur[df.dur >= m].sum() / df.dur.sum():.1%} of idle time")


def figure(df, span, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    import plots
    cfg = plots.MODES["paper"]
    sns.set_theme(style="ticks", rc={**cfg["rc"], "axes.grid": False})
    who = list(df.who.unique())
    color = {w: plots.SERIES[i] for i, w in enumerate(who)}
    style = {w: plots.STYLES[i] for i, w in enumerate(who)}
    fig, ax = plt.subplots(2, 2, figsize=(cfg["width"], 2 * cfg["panel_height"] + 0.6))
    bins = np.geomspace(df.dur.min(), df.dur.max(), 24)
    for w in who:
        x = df[df.who == w].dur
        h, _ = np.histogram(x, bins)
        ax[0, 0].step(bins[:-1], h / h.sum(), where="post", color=color[w], ls=style[w], label=w)
    ax[0, 0].set(xscale="log", xlabel="idle window (s)", ylabel="share of windows", title="Duration, by participant")
    ax[0, 0].legend(frameon=False)
    sh = (df.groupby(["who", "session"]).dur.sum() / span.set_index(["who", "session"]).length).unstack()
    sh = sh.reindex(columns=[m for m in MAIN if m in sh.columns])
    for w in who:
        ax[0, 1].plot(range(sh.shape[1]), sh.loc[w] * 100, color=color[w], ls=style[w], marker="o", ms=3)
    ax[0, 1].set(xticks=range(sh.shape[1]), xticklabels=list(sh.columns), ylabel="idle share of session (%)", title="Idle time by session")
    order = df.groupby("prev").dur.median().sort_values().index
    sns.boxplot(data=df, y="prev", x="dur", order=order, ax=ax[1, 0], color="0.85", fliersize=1.5, linewidth=0.8)
    ax[1, 0].set(xscale="log", xlabel="idle window (s)", ylabel="what came before", title="Duration by previous action")
    h = df[(df.prev == "harvest") & df.bout_mean.notna()]
    for w in who:
        ax[1, 1].scatter(h[h.who == w].bout_mean, h[h.who == w].dur, s=5, color=color[w], alpha=0.6)
    ax[1, 1].set(yscale="log", xlabel="mean reward per fruit of the bout before", ylabel="idle window (s)", title="After a harvest")
    fig.tight_layout()
    fig.savefig(path, dpi=cfg["dpi"])
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", help="comma-separated run ids (default: every finished run)")
    ap.add_argument("--min-dur", type=float, default=0.3)
    ap.add_argument("--min-turn", type=float, default=0.5)
    ap.add_argument("--interludes", action="store_true", help="the Interlude sessions instead of P, S1-S5")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--budget", action="store_true", help="also print the time budget (where every frame's time goes)")
    ap.add_argument("--mode", choices=("strict", "stationary", "both"), default="both")
    a = ap.parse_args()
    runs = finished_runs() if not a.runs else {r[:8]: r for r in a.runs.split(",")}
    sessions = tuple(f"{m}_Interlude" for m in MAIN) if a.interludes else MAIN
    print("participants:", ", ".join(f"{w} ({r[:8]})" for w, r in runs.items()))
    out = ROOT / "results"
    if a.budget:
        report_budget(budget(runs, sessions, a.min_turn))
    for mode in (("strict", "stationary") if a.mode == "both" else (a.mode,)):
        df, span = collect(runs, sessions, mode == "strict", a.min_dur, a.min_turn)
        report(df, span, f"{mode} idle, windows >= {a.min_dur} s, turns < {a.min_turn} deg ignored" if mode == "strict" else f"{mode} (no key held), windows >= {a.min_dur} s")
        if a.save:
            out.mkdir(exist_ok=True)
            df.to_csv(out / f"idle_windows_{mode}.csv", index=False)
            if mode == "stationary":      # the larger sample
                figure(df, span, out / "idle_pauses.png")


if __name__ == "__main__":
    main()
