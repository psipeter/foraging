"""What a set of sessions looks like, to design a pilot's three sessions (low, medium, high of one knob) before they are built.

    ./venv/bin/python scripts/pilot_report.py preview PCX [--workers 3] [--agents] [--out results/pilot_PCX_preview.png]
    ./venv/bin/python scripts/pilot_report.py report  PCX [--workers 3] [--no-agents] [--out docs/pilots/PCX.png]

`preview` reads the table `design/tables/<code>.json` and needs no simulation: each cell's map is calibrated to its Gini, interaction and class (`value_maps.calibrate_map`), given the gain that makes the
mean bush value `TARGET_MEAN` (the independence runs held the anchor with a mean bush value of 2.2, within about 12 percent over every class and Gini: an approximation, `cells.py realize` solves the real gain),
and its world is generated (`factors.PLACEMENT`, the cell's world seed) and measured. `report` reads the realised file `design/realized/<code>.json` (gain, layout and world seed as realised) and measures
its worlds. Agents (nearest, learner, oracle) run on the cell's own world only, one world each: a few percent of noise for the learner, no 40 world check.

The figure has a panel per session: the map on the fixed 0 to 9 fruit scale (the world's bushes over it, a contour at half the peak). The table lists the map's descriptors (Gini, interaction, log interaction, nonlinearity, shape share, share of the plane above half the peak, peak, gain) and the world's (travel time, bush Gini,
mean bush value, diversity within patches, contrast between them, the deviation of a patch total, agents' points), then the **span and hold** check of the pilot (`PILOTS`): the metrics the knob
should move (increasing from the first session to the last, by at least a span) and the ones that must stay put (within a tolerance). A flag means the three sessions do not yet differ as intended.
"""

import argparse
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np

import cells
import factors
import tiles
import value_maps
import world

ROOT = Path(__file__).resolve().parent.parent
TARGET_MEAN = 2.2               # the mean bush value of a session at its realised gain, over the independence runs (2.1 to 2.3 in the means of every class)
AGENTS = ("nearest", "learner", "oracle")

# What a pilot's sessions must do, in session order: `vary` {metric: the least span, rising}; `hold` {metric: (kind, tolerance)} with kind "abs" (max - min), "rel" (that over the mean) or "max"; `limit` {metric: upper bound}.
HOLD_ALL = {"mean_bush_value": ("rel", 0.10), "tile_sum_dev": ("max", 1.0), "learner": ("rel", 0.20)}
PILOTS = {
    "PCX": {"title": "Pilot: Complexity", "vary": {"interaction": 0.30}, "hold": {"gini": ("abs", 0.03), "travel_time": ("abs", 0.5), **HOLD_ALL}, "limit": {"max": factors.MAX_PEAK}},
    "PSP": {"title": "Pilot: Sparsity", "vary": {"gini": 0.20}, "hold": {"travel_time": ("abs", 0.5), "interaction": ("abs", 0.15), **HOLD_ALL}, "limit": {"max": factors.MAX_PEAK}},
    "PEF": {"title": "Pilot: Efficiency", "vary": {"travel_time": 3.0}, "hold": {"gini": ("abs", 0.03), "interaction": ("abs", 0.05), **HOLD_ALL}, "limit": {"max": factors.MAX_PEAK}},
}

ROWS = (                         # (key, label, format); a key a record lacks is left out
    ("map", None, None),
    ("gini", "map Gini", "{:.3f}"), ("interaction", "interaction", "{:.3f}"), ("log_interaction", "log interaction", "{:.3f}"), ("nonlinearity", "nonlinearity", "{:.3f}"),
    ("shape_share", "shape share", "{:.2f}"), ("fraction_above_half_max", "share above half peak", "{:.3f}"), ("max", "peak (bush)", "{:.2f}"), ("gain", "gain", "{:.3f}"),
    ("world", None, None),
    ("travel_time", "travel time (s)", "{:.2f}"), ("walk_visits", "walk visits ceiling", "{:.1f}"), ("n_tiles", "tiles", "{:.0f}"), ("bush_gini", "bush Gini", "{:.3f}"),
    ("mean_bush_value", "mean bush value", "{:.3f}"), ("diversity", "diversity within patches (SD)", "{:.3f}"), ("contrast", "contrast between patches (SD of means)", "{:.3f}"),
    ("tile_sum_dev", "largest patch total deviation", "{:.2f}"),
    ("share_fruit_over_cap", "share of fruits paying over 9", "{:.4f}"), ("max_fruit", "largest fruit pay", "{:.0f}"),
    ("agents", None, None),
    ("nearest", "nearest, own world", "{:.0f}"), ("learner", "learner, own world", "{:.0f}"), ("oracle", "oracle, own world", "{:.0f}"), ("anchor", "anchor (learner)", "{:.0f}"),
)


def _valuemap(d):
    return value_maps.ValueMap(tuple(value_maps.Bump(**b) for b in d["bumps"]), d["noise"], d["equaliser"])


def session_metrics(valuemap, w, agents=()):
    """The metrics of one session: the map's descriptors at its gain, the world's measured factors and patch statistics, and the points of the registry agents `agents` on this one world."""
    d = valuemap.descriptors()
    f = factors.measure(w)
    s = tiles.stats(w.params, w.pos, w.shape, w.color, w.terrain.tiles, world.bush_value)
    m = {k: d[k] for k in ("gini", "interaction", "log_interaction", "nonlinearity", "shape_share", "fraction_above_half_max", "max")}
    m["gain"] = valuemap.gain()
    m.update({k: f[k] for k in ("travel_time", "walk_visits", "n_tiles", "bush_gini", "mean_bush_value", "max_fruit", "share_fruit_over_cap")})
    m.update({"diversity": f["diversity"], "contrast": f["contrast"], "tile_sum_dev": s["tile_sum_dev"]})
    if agents:
        import sim
        from agents import REGISTRY
        for a in agents:
            m[a] = float(sim.run_n(REGISTRY[a], worlds=[w]).totals[0])
        m["anchor"] = factors.anchor_points(w.params.session_duration)
    return m


def span_and_hold(spec, metrics):
    """The check of a pilot: for each `vary` metric rising from the first session to the last by at least its span, each `hold` metric within its tolerance, each `limit` metric at most its bound.
    `metrics` is the list of sessions' metric dicts in play order; a metric some session lacks is not checked. Returns [(metric, role, values, summary, flag or "")]."""
    out = []
    have = lambda k: all(k in m for m in metrics)
    for k, least in spec.get("vary", {}).items():
        if have(k):
            v = [m[k] for m in metrics]
            rising = all(b > a for a, b in zip(v, v[1:]))
            out.append((k, "vary", v, f"span {v[-1] - v[0]:+.3f}", "" if rising and v[-1] - v[0] >= least else (f"not rising" if not rising else f"span below {least}")))
    for k, (kind, tol) in spec.get("hold", {}).items():
        if have(k):
            v = [m[k] for m in metrics]
            dev = {"abs": max(v) - min(v), "rel": (max(v) - min(v)) / max(np.mean(v), 1e-9), "max": max(v)}[kind]
            out.append((k, "hold", v, f"{'max' if kind == 'max' else 'spread'} {dev:.3f}", "" if dev <= tol else f"over {tol}"))
    for k, bound in spec.get("limit", {}).items():
        if have(k):
            v = [m[k] for m in metrics]
            out.append((k, "limit", v, f"max {max(v):.3f}", "" if max(v) <= bound else f"over {bound}"))
    return out


def _record(job):
    """One session of the set: (the calibrated or realised map, its gain and layout, the world) to a record of numbers and arrays; an inaccessible cell gives {"error": ...}."""
    session, duration, name, cell, realised, agents = job
    try:
        if realised is None:
            kind, gini = cell["class"], float(cell["gini"])
            cid = int(cell["id"])
            interaction = cell["interaction"] if "interaction" in cell else value_maps.default_interaction(kind, gini)
            corner = tuple(float(x) for x in cell["corner"]) if "corner" in cell else cells.corner_of(cid, 0)
            aspect = float(cell["aspect"]) if "aspect" in cell else cells.aspect_of(cid, 0)
            base = world.load_session(session, session_duration=float(duration))
            shaped = value_maps.calibrate_map(gini, interaction, value_maps.CLASS_KLASS[kind], std=float(base.reward_std), corner=corner, aspect=aspect, center=cell.get("center", (0.0, 1.0)), seed=0)
            valuemap = value_maps.ValueMap(shaped.bumps, shaped.noise, {"type": "gain", "value": TARGET_MEAN / shaped.descriptors()["mean"]})
            settings = {**factors.calibrate(world.load_session(session, session_duration=float(duration), **valuemap.compile()), float(cell["travel_time"])), **factors.PLACEMENT}
            seed = int(cell.get("world_seed", cells.FIRST_WORLD_SEED + 100 * cid))
            planner = None
        else:
            valuemap, settings, seed = _valuemap(realised["map"]), realised["settings"], int(realised["world_seed"])
            planner = (realised.get("planner") or {}).get("text")
        w = world.generate_world(world.load_session(session, session_duration=float(duration), **settings, **valuemap.compile()), seed)
        metrics = session_metrics(valuemap, w, AGENTS if agents else ())
        ts = tiles.TileSet(w.terrain.tiles, w.pos)
        means = np.array([w.value[ts.tile_of == t].mean() for t in range(ts.n_tiles)])
        sds = np.array([w.value[ts.tile_of == t].std(ddof=1) for t in range(ts.n_tiles)])
        axis, grid = valuemap.grid()
        return {"name": name, "knobs": cell, "world_seed": seed, "metrics": metrics, "grid": grid, "shape": np.asarray(w.shape), "color": np.asarray(w.color), "value": np.asarray(w.value),
                "tile_means": means, "tile_sds": sds, "planner": planner}
    except ValueError as e:
        return {"name": name, "knobs": cell, "error": str(e)[:300]}


def records(code, mode, workers=3, agents=False):
    """The sessions' records of experiment `code`, in play order: the table's calibrated cells (`preview`) or the realised cells (`report`)."""
    if mode == "preview":
        data = json.loads((cells.TABLES / f"{code}.json").read_text())
        jobs = [(data.get("session", "FOR_S1"), data.get("duration", 120.0), f"{code}_S{i}", c, None, agents) for i, c in enumerate(data["cells"], 1)]
    else:
        data = json.loads((cells.REALIZED / f"{code}.json").read_text())
        jobs = [(data.get("session", "FOR_S1"), c.get("duration", data.get("duration", 120.0)), f"{code}_S{i}", c["knobs"] | {"id": c["id"]}, c, agents)
                for i, c in enumerate([c for c in data["cells"] if c["status"] == "ok"], 1)]
    with mp.Pool(max(1, min(workers, len(jobs)))) as pool:
        return pool.map(_record, jobs)


def format_report(code, mode, recs):
    """The metrics table and the span-and-hold check as text."""
    spec = PILOTS.get(code, {})
    ok = [r for r in recs if "error" not in r]
    names = [r["name"] for r in recs]
    lines = [f"{spec.get('title', code)} ({mode}): the sessions of {code} in play order", ""]
    lines.append(f"{'':42s}" + "".join(f"{n:>12s}" for n in names))
    for key, label, fmt in ROWS:
        if label is None:
            if ok:
                lines.append(f"-- {key}")
            continue
        if not ok or not any(label and key in r["metrics"] for r in ok):
            continue
        lines.append(f"{label:42s}" + "".join(f"{(fmt.format(r['metrics'][key]) if 'error' not in r and key in r['metrics'] else 'n/a'):>12s}" for r in recs))
    for r in recs:
        if "error" in r:
            lines.append(f"{r['name']}: INACCESSIBLE: {r['error']}")
        elif r.get("planner"):
            lines.append(f"{r['name']} planner: {r['planner']}")
    if spec and len(ok) == len(recs) and len(ok) > 1:
        lines += ["", "Span and hold (the knob must rise by its span; the rest stay within tolerance):"]
        for k, role, v, summary, flag in span_and_hold(spec, [r["metrics"] for r in ok]):
            lines.append(f"  {role:5s} {k:18s} " + "  ".join(f"{x:8.3f}" for x in v) + f"   {summary:16s} {'FLAG: ' + flag if flag else 'ok'}")
    return "\n".join(lines)


def plot(code, mode, recs, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(recs)
    fig, axes = plt.subplots(1, n, figsize=(3.3 * n + 0.6, 3.9), squeeze=False)
    for ax, r in zip(axes[0], recs):
        if "error" in r:
            ax.text(0.5, 0.5, f"{r['name']}\ninaccessible:\n{r['error'][:120]}", ha="center", va="center", fontsize=7, wrap=True)
            ax.axis("off")
            continue
        m = r["metrics"]
        ax.imshow(r["grid"].T, origin="lower", extent=(0, 1, 0, 1), cmap="Blues", vmin=0, vmax=9)
        ax.contour(np.linspace(0, 1, r["grid"].shape[0]), np.linspace(0, 1, r["grid"].shape[0]), r["grid"].T, levels=[0.5 * m["max"]], colors="k", linewidths=0.8)
        ax.scatter(r["shape"], r["color"], s=5, c="k", alpha=0.35, linewidths=0)
        ax.set_title(f"{r['name']}\nGini {m['gini']:.2f}, interaction {m['interaction']:.2f}, nonlinearity {m['nonlinearity']:.2f}", fontsize=7.5, loc="left")
        ax.set_xlabel("shape", fontsize=7)
        ax.set_ylabel("colour", fontsize=7)
        ax.tick_params(labelsize=7)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle(f"{PILOTS.get(code, {}).get('title', code)} ({mode})", fontsize=10)
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["preview", "report"])
    ap.add_argument("code")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--agents", dest="agents", action="store_true", default=None, help="run nearest, learner and oracle on each cell's own world (default for report)")
    ap.add_argument("--no-agents", dest="agents", action="store_false")
    ap.add_argument("--out", default=None, help="the figure (a .png); the table goes next to it as .txt")
    args = ap.parse_args()
    agents = (args.mode == "report") if args.agents is None else args.agents
    recs = records(args.code, args.mode, args.workers, agents)
    out = Path(args.out) if args.out else ROOT / "results" / f"pilot_{args.code}_{args.mode}.png"
    text = format_report(args.code, args.mode, recs)
    plot(args.code, args.mode, recs, out)
    out.with_suffix(".txt").write_text(text + "\n")
    print(text)
    print(f"\nfigure {out}, table {out.with_suffix('.txt')}")


if __name__ == "__main__":
    main()
