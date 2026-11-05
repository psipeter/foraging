"""Where the gap between participants and the simulated agents comes from, on the very worlds the participants played.

Exploratory. For every finished online run and each of P, S1-S5 it replays the participant's harvest bouts (a visit = one bout)
and runs the registry agents (`--agents`, default nearest, oracle, learner) on the same world (same seed, same session asset, so the
same bushes and per-fruit rewards: checked against the archived world file; the session duration is the asset's).

The total of a session factors exactly as  total = visits x fruits per visit x reward per fruit, and a visit's time as
harvest + walk + the rest, so the gap is attributed to
  visits           how many bushes were harvested (time per visit: the walk between bushes, the turns, the pauses),
  fruits per visit leaving a bush before it is empty,
  reward per fruit which bushes were chosen (their true value) and how much of each was taken.
Bush choice is also read directly: the true value of each visited bush, the rank of its distance among the bushes still unspent
(1 = the nearest), and the walk to it against the shortest walk available at that moment.

    ./venv/bin/python scripts/human_gap.py [--agents nearest,oracle,learner] [--save]

Walking distances for both humans and agents are straight lines between bushes, to the edge of the harvest range, the way the
engine walks (sim._walk); the participants' own path length is reported separately. `--save` writes results/human_visits.csv.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay  # noqa: E402
import sim  # noqa: E402
from agents import REGISTRY  # noqa: E402
from idle_analysis import DATA, MAIN, ROOT, bouts_of, finished_runs  # noqa: E402
from world import load_session, make_world  # noqa: E402

LOCAL = 40.0     # world units: the neighbourhood in which a chosen bush's value is ranked


def walk_to(pos, w, j):
    """(distance still to walk to bush j's harvest range from `pos`, the position then): the engine's straight walk to the edge."""
    d = float(np.hypot(*(w.pos[j] - pos)))
    reach = float(w.reach[j])
    if d <= reach:
        return 0.0, pos
    return d - reach, w.pos[j] + (pos - w.pos[j]) / d * reach


def visit_rows(w, sequence, who, session):
    """One row per visit from the ordered bush ids (and fruits taken per visit), choice measured against what was still unspent."""
    taken = np.zeros(w.n, dtype=int)
    pos = np.zeros(2)
    rows = []
    for v, (j, n) in enumerate(sequence):
        live = np.flatnonzero(taken < w.fruit_count)
        walks = np.array([walk_to(pos, w, k)[0] for k in live])
        centre = np.hypot(*(w.pos[live] - pos).T)
        near = live[centre <= LOCAL]
        hop, new = walk_to(pos, w, j)
        rows.append({"who": who, "session": session, "visit": v, "bush": j, "fruits": n, "value": float(w.value[j]),
                     "hop": hop, "shortest_hop": float(walks.min()), "excess_hop": hop - float(walks.min()),
                     "dist_rank": int((walks < hop - 1e-9).sum()) + 1,
                     "value_pct": float((w.value[near] < w.value[j]).mean()) if len(near) > 1 else np.nan,
                     "revisit": bool(taken[j] > 0), "left_with": int(w.fruit_count - taken[j] - n)})
        taken[j] += n
        pos = new
    return rows


def human_sessions(runs):
    out, per = [], []
    for who, run in runs.items():
        for folder in sorted((DATA / run).glob("[0-9][0-9]")):
            log = replay.load_session_log(folder)
            if log.name not in MAIN:
                continue
            w = make_world(log.name, log.manifest["world_seed"])
            if not (np.allclose(log.bushes.pos, w.pos, atol=1e-3) and np.array_equal(log.bushes.fruit_reward, w.fruit_reward)):
                print(f"warning: {who} {log.name}: the archived world differs from the current asset; skipped")
                continue
            tr = log.traj
            t, keys = tr[:, 0], tr[:, 5].astype(int)
            bouts = bouts_of(log.events, w.fruit_count)
            rows = visit_rows(w, [(b["tree"], b["n"]) for b in bouts], who, log.name)
            for r, b in zip(rows, bouts):
                r["bout_time"] = b["release"] - b["press"]
            dt = np.r_[np.diff(t), 0.0]
            inb = np.zeros(len(t), dtype=bool)
            for b in bouts:
                inb |= (t >= b["press"] - 0.02) & (t <= b["release"] + 0.02)
            step = np.r_[0.0, np.hypot(np.diff(tr[:, 1]), np.diff(tr[:, 2]))]
            out += rows
            per.append({"who": who, "session": log.name, "length": float(t[-1]), "total": log.final_score, "visits": len(bouts),
                        "fruits": sum(b["n"] for b in bouts), "harvest_t": float(dt[inb].sum()),
                        "walk_t": float(dt[(keys & 3 > 0) & ~inb].sum()), "path": float(step[~inb].sum()),
                        "straight": sum(r["hop"] for r in rows)})
    return pd.DataFrame(out), pd.DataFrame(per)


def agent_sessions(names, seeds_by_session):
    out, per = [], []
    for name in names:
        for session, seed in seeds_by_session.items():
            w = make_world(session, seed)
            res = sim.run_episode(REGISTRY[name](), w)
            rows = visit_rows(w, [(j, n) for j, n, _ in res.trace], name, session)
            out += rows
            per.append({"who": name, "session": session, "length": w.session_duration, "total": res.total, "visits": res.n_visits,
                        "fruits": res.n_fruits, "harvest_t": res.harvest_time, "walk_t": res.walk_time,
                        "look_t": res.look_time, "press_t": res.press_time, "idle_t": res.idle_time,
                        "straight": sum(r["hop"] for r in rows)})
    return pd.DataFrame(out), pd.DataFrame(per)


def summarize(per, visits, group):
    """One row per (group, session): means over participants (agents have one world, so one row each)."""
    g = per.groupby([group, "session"])
    t = g.agg(total=("total", "mean"), visits=("visits", "mean"), fruits=("fruits", "mean"), length=("length", "mean"),
              harvest_t=("harvest_t", "mean"), walk_t=("walk_t", "mean"), straight=("straight", "mean")).reset_index()
    t["fruits_per_visit"] = t.fruits / t.visits
    t["reward_per_fruit"] = t.total / t.fruits
    t["sec_per_visit"] = t.length / t.visits
    t["harvest_per_visit"] = t.harvest_t / t.visits
    t["walk_per_visit"] = t.walk_t / t.visits
    t["other_per_visit"] = t.sec_per_visit - t.harvest_per_visit - t.walk_per_visit
    t["hop_per_visit"] = t.straight / t.visits
    first = visits[~visits.revisit].groupby([group, "session"]).agg(value=("value", "mean"), value_pct=("value_pct", "mean"),
                                                                   dist_rank=("dist_rank", "mean"), excess=("excess_hop", "mean"))
    return t.merge(first.reset_index(), on=[group, "session"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--agents", default="nearest,oracle,learner")
    ap.add_argument("--runs", help="comma-separated run ids (default: every finished run)")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    runs = finished_runs() if not a.runs else {r[:8]: r for r in a.runs.split(",")}
    hv, hp = human_sessions(runs)
    seeds = {s: load_session(s).world_seed for s in MAIN}
    av, ap_ = agent_sessions(a.agents.split(","), seeds)
    pd.set_option("display.width", 220)
    hs = summarize(hp, hv, "who").assign(kind="human")
    hs_all = hs.groupby("session").mean(numeric_only=True)
    ag = summarize(ap_, av, "who")
    order = [s for s in MAIN]
    print("participants:", ", ".join(runs), "| agents:", a.agents)

    print("\n=== per session: humans (mean over participants, and each participant's total) vs agents")
    for s in order:
        h = hs[hs.session == s]
        line = hs_all.loc[s]
        print(f"\n{s} ({line.length:.0f} s)   human totals: " + ", ".join(f"{r.who} {r.total:.0f}" for r in h.itertuples()))
        cols = ["total", "visits", "fruits_per_visit", "reward_per_fruit", "sec_per_visit", "harvest_per_visit", "walk_per_visit",
                "other_per_visit", "hop_per_visit", "value", "value_pct", "dist_rank", "excess"]
        tab = pd.concat([line[cols].to_frame("humans").T, ag[ag.session == s].set_index("who")[cols]])
        print(tab.round(2).to_string())

    print("\n=== gap of the humans to each agent, as log-ratio of total = visits x fruits/visit x reward/fruit "
          "(positive: the agent is ahead), mean of the log-ratios over S1-S5")
    main_s = [s for s in order if s != "P"]
    h = hs_all.loc[main_s]
    for name in a.agents.split(","):
        g = ag[(ag.who == name) & ag.session.isin(main_s)].set_index("session").loc[main_s]
        parts = {"visits": np.log(g.visits / h.visits).mean(), "fruits/visit": np.log(g.fruits_per_visit / h.fruits_per_visit).mean(),
                 "reward/fruit": np.log(g.reward_per_fruit / h.reward_per_fruit).mean()}
        tot = np.log(g.total / h.total).mean()
        print(f"{name:8s} total {tot:+.2f} (x{np.exp(tot):.2f}) = " + "  ".join(f"{k} {v:+.2f}" for k, v in parts.items()))

    print("\n=== the same, per session: log(agent / humans) of each factor; the three add up to the total")
    for name in a.agents.split(","):
        for s in order:
            g = ag[(ag.who == name) & (ag.session == s)].iloc[0]
            hh = hs_all.loc[s]
            f = (np.log(g.visits / hh.visits), np.log(g.fruits_per_visit / hh.fruits_per_visit), np.log(g.reward_per_fruit / hh.reward_per_fruit))
            print(f"{name:8s} {s:3s} total {np.log(g.total / hh.total):+.2f} = visits {f[0]:+.2f}  fruits/visit {f[1]:+.2f}  reward/fruit {f[2]:+.2f}")
    print("\n=== per participant, S1-S5: visits, fruits/visit, reward/fruit, bush value, seconds per visit split, hop")
    p = hs[hs.session.isin(main_s)].groupby("who").mean(numeric_only=True)
    print(p[["total", "visits", "fruits_per_visit", "reward_per_fruit", "value", "value_pct", "dist_rank", "excess", "sec_per_visit",
             "harvest_per_visit", "walk_per_visit", "other_per_visit", "hop_per_visit"]].round(2).to_string())

    print("\n=== visit choice, humans (S1-S5 visits pooled) vs nearest")
    hv_m = hv[hv.session.isin(main_s)]
    av_m = av[av.session.isin(main_s) & (av.who == "nearest")] if "nearest" in a.agents else None
    for label, d in (("humans", hv_m), ("nearest", av_m)):
        if d is None:
            continue
        f = d[~d.revisit]
        print(f"{label:8s} visits {len(d)}  revisits {d.revisit.mean():.1%}  nearest-bush choices (rank 1) {(f.dist_rank == 1).mean():.0%}  "
              f"rank<=3 {(f.dist_rank <= 3).mean():.0%}  excess walk {f.excess_hop.mean():.1f} u (median {f.excess_hop.median():.1f})  "
              f"value pct {f.value_pct.mean():.2f}  full harvests {(d.left_with == 0).mean():.0%}  fruits/visit {d.fruits.mean():.2f}")
    print("\n-- humans: fruits taken per visit by the bush's true value (how selective is the leaving?), S1-S5")
    b = pd.cut(hv_m.value, [-0.01, 1, 2, 3, 5])
    print(hv_m.groupby(b, observed=True).fruits.agg(["size", "mean", lambda x: (x == 10).mean()]).rename(columns={"<lambda_0>": "share_full"}).round(2).to_string())
    if av_m is not None:
        b = pd.cut(av_m.value, [-0.01, 1, 2, 3, 5])
        print("-- nearest, same bins")
        print(av_m.groupby(b, observed=True).fruits.agg(["size", "mean", lambda x: (x == 10).mean()]).rename(columns={"<lambda_0>": "share_full"}).round(2).to_string())
    pr = hp[hp.session.isin(main_s)]
    print(f"\nparticipants' own path vs the straight hops: path / straight = {pr.path.sum() / pr.straight.sum():.2f} "
          f"(path {pr.path.sum() / len(pr):.0f} u per session, straight {pr.straight.sum() / len(pr):.0f} u)")
    if a.save:
        out = ROOT / "results"
        out.mkdir(exist_ok=True)
        hv.to_csv(out / "human_visits.csv", index=False)
        av.to_csv(out / "agent_visits.csv", index=False)
        print(f"wrote {out}/human_visits.csv, agent_visits.csv")


if __name__ == "__main__":
    main()
