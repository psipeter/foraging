"""The agent screen of FI (docs/EXPERIMENTS.md, "Implementation plan"): how easy or hard each cell of the ladder is for the simulated agents, on many worlds per cell.

A cell is one of `design.FI.CELLS` (a kind of Gaussian); `--extras` adds control cells (an axis-aligned elongated Gaussian, a rotated one at 22 degrees and a more elongated one); a world is a draw of `fi_terms.draw_instance` at the design's target sparsity, built through the real session asset (`FI_S1` with the drawn
reward function), so the world is the game's own kind. Each agent plays each world for the longest length (180 s) and the score at each shorter length is read from the same episode (none of the agents depends on the
session's length), then is scored on the Interlude the game would show for that world (the design's 20 typed trials) with its critic frozen. What is recorded, per episode:

    score_<t>            points collected by t seconds
    first_high           the time of the first fruit from a high bush (one paying at least HIGH of the best), empty if none
    high_share           the share of the last third of the fruits that came from high bushes (settling on the good region)
    interlude_acc        the share of Interlude picks that were right, and `acc_<class>` for each class of trial (`interlude.INTERACTION_PLANS`)

    fi_screen.py run --tag fi1 [--worlds 40] [--workers 14] [--agents a,b,...]
    fi_screen.py report --tag fi1

Files in results/ (flat, like the RW screen's): fi_screen_<tag>_episodes.csv, _instances.csv, _fruits.jsonl.gz, _plan.json.
"""

import argparse
import csv
import gzip
import json
import subprocess
import time
from multiprocessing import Pool

import numpy as np

import agents
import fi_terms
import interlude
import sim
import world
from design import FI
from world import PROJECT_ROOT

RESULTS = PROJECT_ROOT / "results"
DURATIONS = (60, 90, 120, 150, 180)                 # seconds: the lengths the score is read at (the longest is played)
WORLDS_PER_CELL = 40
BASE_SESSION = "FI_S1"                               # the built session asset the worlds copy (terrain, lighting, hexagonal lattice, plane coverage)
INTERLUDE_ASSET = "FI_I1"
INTERLUDE_SAMPLES = 20                               # picks per trial (the choice is greedy for every actor, so a pick has no noise of its own)
CLASSES = ("HL", "HM", "ML", "MM", "S", "C", "R", "along", "across")
MAX_ATTEMPTS = 20
MAX_ERROR_SHARE = 0.05

class JointShapeColor(agents.Features):
    """Gaussian bumps of width `length_scale` on a joint grid of `n_centers` x `n_centers` over (shape, colour) only: it can represent an interaction of the two features and, unlike
    `RBFFeatures(additive=False)` (a grid over shape, colour and moisture, 512 centres), spends no data on moisture, which pays nothing in FI."""

    def __init__(self, length_scale=0.3, n_centers=8):
        self.length_scale = float(length_scale)
        axis = np.linspace(0.0, 1.0, int(n_centers))
        self._centers = np.stack([g.ravel() for g in np.meshgrid(axis, axis, indexing="ij")], axis=1)

    def _raw(self, attrs):
        d2 = ((attrs[:, None, :2] - self._centers[None, :, :]) ** 2).sum(-1)
        return np.exp(-d2 / (2.0 * self.length_scale ** 2))


class AdditiveShapeColor(agents.Features):
    """The additive twin of `JointShapeColor`: the same 1-D Gaussian bumps (`n_centers` per feature, spread `length_scale`) over shape and colour only, concatenated, so that the kernel is a sum of the
    two 1-D kernels where the joint one is their product. Same smoothness prior, same centres, same learning rule: only the separability differs (unlike `RBFFeatures`, which adds a block for moisture)."""

    def __init__(self, length_scale=0.3, n_centers=8):
        self.length_scale = float(length_scale)
        self._centers = np.linspace(0.0, 1.0, int(n_centers))

    def _raw(self, attrs):
        d = attrs[:, :2, None] - self._centers[None, None, :]
        return np.exp(-d ** 2 / (2.0 * self.length_scale ** 2)).reshape(len(attrs), -1)


AGENT_FACTORIES = {
    "nearest": agents.REGISTRY["nearest"],
    "oracle": agents.REGISTRY["oracle"],                                                                       # true values, map from the view cone: the ceiling
    "learner": agents.REGISTRY["learner"],                                                                     # delta rule, additive (separable) RBF features
    "learner_add2": lambda: agents.DeltaRuleAgent(features=AdditiveShapeColor()),                               # the same 1-D bumps summed over shape and colour: the additive twin of learner_joint
    "learner_joint": lambda: agents.DeltaRuleAgent(features=JointShapeColor()),                                # the same on a joint grid over shape and colour: it can represent an interaction
}
EPISODE_FIELDS = (["instance", "agent", "cell", "kind", "elongation", "tilt"] + [f"score_{d}" for d in DURATIONS] + ["fruits", "first_high", "high_share", "interlude_acc"]
                  + [f"acc_{c}" for c in CLASSES])
INSTANCE_FIELDS = ["instance", "cell", "k", "status", "world_seed", "attempts", "n_bushes", "sparsity30", "sparsity40", "sparsity50", "nonzero", "n_high", "n_mid", "n_low", "record"]


EXTRA_CELLS = (("ALIGNED", "elongated", FI.ELONGATION, 0.0), ("ROTATED22", "elongated", FI.ELONGATION, 22.0), ("ROTATED_E5", "elongated", 5.0, FI.TILT_DEGREES))      # controls and variants for choosing the design's parameters


def cells(extras=False):
    """The cells of the screen: FI's table (the design's elongation and tilt for its elongated kind), with the control cells when `extras`; each with an index."""
    out = [{"id": cid, "kind": kind, "elongation": FI.ELONGATION if kind == "elongated" else 1.0, "tilt": FI.TILT_DEGREES if kind == "elongated" else 0.0} for cid, kind, _ in FI.CELLS]
    if extras:
        out += [{"id": cid, "kind": kind, "elongation": e, "tilt": t} for cid, kind, e, t in EXTRA_CELLS]
    return [{**c, "index": i} for i, c in enumerate(out)]


def build_instance(cell, k):
    """(world seed, attempts, instance, world) of the k-th world of a cell: the first seed whose draw reaches the target and whose world populates every part of the reward."""
    for attempt in range(MAX_ATTEMPTS):
        seed = 20_000 + 100 * cell["index"] + k + 1_000_000 * attempt
        rng = np.random.default_rng([seed, 11])
        inst = fi_terms.draw_instance(rng, cell["kind"], target=FI.TARGET_SPARSITY, x=FI.X_PERCENT, elongation=cell["elongation"], tilt=cell["tilt"])
        w = world.generate_world(session(inst), seed)
        if fi_terms.check_regions(inst, w.shape, w.color):
            return seed, attempt, inst, w
    return None


def session(inst):
    return world.load_session(BASE_SESSION, reward_function=inst.reward_function(), session_duration=float(max(DURATIONS)))


def class_accuracy(sidecar, score):
    """The accuracy per class of Interlude trial from `sim.evaluate_interlude`'s per-trial share of left picks."""
    by_class = {}
    for t, p_left in zip(sidecar["trials"], score.p_left):
        right = p_left if t["correct"] == "left" else 1.0 - p_left if t["correct"] == "right" else 1.0
        by_class.setdefault(t["varied"], []).append(right)
    return {c: float(np.mean(v)) for c, v in by_class.items()}


def episode_row(w, inst, result):
    """The score at each length, the first high fruit, the high share of the last third of the fruits, and the fruit log in compact form."""
    fruits = np.array(result.fruits, dtype=float).reshape(-1, 5)                       # (t, bush, k, reward, running total)
    t, bush, reward = fruits[:, 0], fruits[:, 1].astype(int), fruits[:, 3]
    top = float(inst.record["max_reward"])
    high = np.asarray(inst.value(w.shape, w.color), dtype=float) >= fi_terms.HIGH * top
    row = {f"score_{d}": float(reward[t <= d].sum()) for d in DURATIONS}
    row["fruits"] = int(len(t))
    from_high = high[bush] if len(bush) else np.zeros(0, dtype=bool)
    row["first_high"] = float(t[from_high].min()) if from_high.any() else ""
    last = from_high[2 * len(from_high) // 3:]
    row["high_share"] = float(last.mean()) if len(last) else ""
    log = {"t": [round(float(v), 2) for v in t], "bush": [int(v) for v in bush], "reward": [float(v) for v in reward], "high": [int(v) for v in from_high]}
    return row, log


def run_instance(task):
    """Worker: one world of a cell, every agent on it, then its Interlude. Returns (instance row, episode rows, fruit logs)."""
    cell, k, agent_names = task
    instance = f"{cell['id']}_w{k}"
    try:
        built = build_instance(cell, k)
        if built is None:
            return {"instance": instance, "cell": cell["id"], "k": k, "status": "no world with every part of the reward populated"}, [], []
        seed, attempts, inst, w = built
        counts = fi_terms.region_counts(inst, w.shape, w.color)
        info = {"instance": instance, "cell": cell["id"], "k": k, "status": "ok", "world_seed": seed, "attempts": attempts + 1, "n_bushes": w.n,
                **{f"sparsity{x}": v for x, v in inst.record["sparsity"].items()}, "nonzero": inst.record["nonzero"],
                "n_high": counts["high"], "n_mid": counts["mid"], "n_low": counts["low"], "record": json.dumps(inst.record)}
        sidecar, bonus, practice = _interlude(inst, seed)
        rows, logs = [], []
        for name in agent_names:
            agent = AGENT_FACTORIES[name]()
            result = sim.run_episode(agent, w)
            row, log = episode_row(w, inst, result)
            score = sim.evaluate_interlude(agent, sidecar, bonus, practice, n_samples=INTERLUDE_SAMPLES)
            row["interlude_acc"] = score.accuracy
            row.update({f"acc_{c}": a for c, a in class_accuracy(sidecar, score).items()})
            rows.append({"instance": instance, "agent": name, "cell": cell["id"], "kind": cell["kind"], "elongation": cell["elongation"], "tilt": cell["tilt"], **row})
            logs.append({"instance": instance, "agent": name, **log})
        return info, rows, logs
    except Exception as error:                                       # one bad instance must not end a long unattended run: it is recorded and the run goes on
        return {"instance": instance, "cell": cell["id"], "k": k, "status": f"error: {type(error).__name__}: {error}"}, [], []


def _interlude(inst, seed):
    """The Interlude the game shows for this world: the design's asset with the drawn reward function and the world's seed."""
    sidecar, params, _ = interlude.generate_interlude(INTERLUDE_ASSET, seed=seed, reward_function=inst.reward_function())
    return sidecar, float(params.interlude_bonus_per_correct), bool(params.is_practice)


def files(tag, directory=RESULTS):
    return {kind: directory / f"fi_screen_{tag}_{kind}" for kind in ("instances.csv", "episodes.csv", "fruits.jsonl.gz")}


def _append(path, rows, fields):
    new = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval="")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def done_instances(tag, directory=RESULTS):
    path = files(tag, directory)["instances.csv"]
    if not path.exists():
        return set()
    with open(path, newline="") as f:
        return {row["instance"] for row in csv.DictReader(f) if not row["status"].startswith("error")}


def run(tag, worlds=WORLDS_PER_CELL, agent_names=tuple(AGENT_FACTORIES), workers=1, directory=RESULTS, extras=False):
    """Play every agent on every world not yet in the files, appending as worlds finish. Worlds go round the cells (world 0 of every cell, then world 1, ...), so a run stopped early has the same
    number of worlds in every cell."""
    for name in agent_names:
        if getattr(AGENT_FACTORIES[name](), "deadline_dependent", False):
            raise ValueError(f"{name} depends on the session's length: the screen reads shorter sessions from one long run")
    directory.mkdir(parents=True, exist_ok=True)
    paths = files(tag, directory)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()
    with open(directory / f"fi_screen_{tag}_plan.json", "a") as f:
        f.write(json.dumps({"started": time.strftime("%Y-%m-%d %H:%M:%S"), "commit": commit, "worlds_per_cell": worlds, "agents": list(agent_names), "durations": list(DURATIONS),
                            "target_sparsity": FI.TARGET_SPARSITY, "x_percent": FI.X_PERCENT, "cells": [c["id"] for c in cells(extras)], "interlude_samples": INTERLUDE_SAMPLES}) + "\n")
    skip = done_instances(tag, directory)
    tasks = [(c, k, tuple(agent_names)) for k in range(worlds) for c in cells(extras) if f"{c['id']}_w{k}" not in skip]
    print(f"{len(tasks)} worlds to play ({len(skip)} already done), {len(agent_names)} agents each, lengths {DURATIONS}", flush=True)
    start, played, errors = time.time(), 0, 0

    def store(result):
        nonlocal played, errors
        info, rows, logs = result
        if rows:
            _append(paths["episodes.csv"], rows, EPISODE_FIELDS)
            with gzip.open(paths["fruits.jsonl.gz"], "at") as f:
                f.writelines(json.dumps(entry) + "\n" for entry in logs)
        _append(paths["instances.csv"], [info], INSTANCE_FIELDS)          # last: a world is done only when its episodes are stored
        played += 1
        if info["status"].startswith("error"):
            errors += 1
            if errors <= 3:
                print(f"  {info['instance']}: {info['status']}", flush=True)
            if played >= 40 and errors / played > MAX_ERROR_SHARE:
                raise RuntimeError(f"{errors} of {played} worlds failed: stopping ({info['status']})")
        if played % 20 == 0 or played == len(tasks):
            elapsed = time.time() - start
            print(f"  {played}/{len(tasks)} worlds, {elapsed:.0f} s, about {elapsed * (len(tasks) - played) / played:.0f} s to go", flush=True)

    if workers > 1:
        with Pool(workers) as pool:
            for result in pool.imap_unordered(run_instance, tasks, chunksize=1):
                store(result)
    else:
        for task in tasks:
            store(run_instance(task))
    print(f"done: {played} worlds, {errors} errors", flush=True)


def episodes(tag, directory=RESULTS):
    import pandas as pd
    return pd.read_csv(files(tag, directory)["episodes.csv"])


def report(tag, directory=RESULTS, extras=False):
    """Per cell and agent: the mean score at each length, the share of the oracle's score (paired by world) at 120 and 150 s, the share that found a high bush by 60 and 120 s, the high share of the
    last third, and the Interlude accuracy overall and by class."""
    import pandas as pd
    pd.set_option("display.width", 250, "display.max_columns", 30)
    e = episodes(tag, directory)
    oracle = e[e.agent == "oracle"].set_index("instance")
    for d in (120, 150):
        e[f"of_oracle_{d}"] = e.apply(lambda r: r[f"score_{d}"] / oracle[f"score_{d}"].get(r["instance"], np.nan) if oracle[f"score_{d}"].get(r["instance"], 0) > 0 else np.nan, axis=1)
    order = [c["id"] for c in cells(extras)]
    e["cell"] = pd.Categorical(e["cell"], order, ordered=True)
    for label, columns in (("points (mean) at each length", [f"score_{d}" for d in DURATIONS]),
                           ("share of the oracle's score (paired by world), at 120 and 150 s", ["of_oracle_120", "of_oracle_150"]),
                           ("Interlude accuracy", ["interlude_acc"])):
        print(f"\n== {label}")
        print(e.groupby(["cell", "agent"], observed=True)[columns].mean().round(2).unstack("agent").to_string())
    found = e.assign(h60=e.first_high.le(60), h120=e.first_high.le(120))
    print("\n== found a high bush by 60 s / by 120 s, and the high share of the last third of the fruits")
    print(found.groupby(["cell", "agent"], observed=True)[["h60", "h120", "high_share"]].mean().round(2).unstack("agent").to_string())
    classes = [f"acc_{c}" for c in CLASSES if f"acc_{c}" in e]
    print("\n== Interlude accuracy by class, learners only (mean over cells and worlds of each kind)")
    print(e[e.agent.isin(["learner", "learner_joint"])].groupby(["kind", "agent"])[classes].mean().round(2).to_string())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tag", required=True)
    r.add_argument("--worlds", type=int, default=WORLDS_PER_CELL)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--agents", default=",".join(AGENT_FACTORIES))
    r.add_argument("--extras", action="store_true", help="also play the control cells (EXTRA_CELLS)")
    p = sub.add_parser("report")
    p.add_argument("--tag", required=True)
    p.add_argument("--extras", action="store_true")
    args = ap.parse_args()
    if args.command == "run":
        run(args.tag, args.worlds, tuple(args.agents.split(",")), args.workers, extras=args.extras)
    else:
        report(args.tag, extras=args.extras)


if __name__ == "__main__":
    main()
